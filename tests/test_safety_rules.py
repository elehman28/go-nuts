"""Tests for the safety rules in CLAUDE.md: loop limits, no made-up data, no personal information,
and plain-English errors. All offline, with the fake model."""
import pytest
import requests

from gonuts import config, theme, web
from gonuts.agents.analyst import merge_analyses, split_menu
from gonuts.llm import ModelError, OutputCutOff, parse_json

from conftest import PROFILE  # noqa: F401  (keeps the shared setup imported)


def dish_line(i: int) -> str:
    return f"Dish number {i} - grilled vegetables, rice, house sauce, lemon  ${10 + i % 9}"


def big_menu(n_lines: int) -> str:
    return "\n".join(dish_line(i) for i in range(n_lines))


# ---- Rule 1: loop limits and the output cap

def test_split_menu_keeps_every_line_and_respects_the_size():
    text = big_menu(400)
    pieces = split_menu(text, 6_000)
    assert all(len(p) <= 6_000 for p in pieces)
    assert "\n".join(pieces).split("\n") == text.split("\n")


def test_big_menu_is_analyzed_in_capped_pieces_and_merged(make_team):
    def answer(system, user):
        first = user.split("<menu>\n")[1].splitlines()[0]
        return {"is_menu": True, "dishes": [{"name": first.split(" - ")[0], "risk": "none_listed",
                                             "nuts": [], "evidence": first, "reason": "r"}]}
    team, fake = make_team(answers={"analyst": answer})
    menu = big_menu(1_000)  # far more than MAX_MENU_CHUNKS pieces' worth
    out = team.send("user", "analyst", "analyze_menu", {"menu_text": menu})
    analyst_calls = [a for a, _ in fake.prompts if a == "analyst"]
    assert len(analyst_calls) == config.MAX_MENU_CHUNKS
    assert len(out["dishes"]) == config.MAX_MENU_CHUNKS  # one dish per piece, all merged


def test_cut_off_answer_is_split_once_then_gives_up(make_team):
    def always_cut_off(system, user):
        raise OutputCutOff("cut off")
    team, fake = make_team(answers={"analyst": always_cut_off})
    menu = big_menu(60)  # one piece
    with pytest.raises(OutputCutOff):
        team.send("user", "analyst", "analyze_menu", {"menu_text": menu})
    # 1 try, then the single allowed split; the first half is still cut off, so it stops there
    assert len([a for a, _ in fake.prompts if a == "analyst"]) == 1 + config.MAX_CUTOFF_SPLITS


def test_merged_kitchen_policy_keeps_the_most_cautious():
    merged = merge_analyses([
        {"is_menu": True, "dishes": [], "kitchen": {"policy": "accommodates", "statements": ["We accommodate"]}},
        {"is_menu": True, "dishes": [], "kitchen": {"policy": "cross_contact_warning", "statements": ["Nuts used"]}},
    ])
    assert merged["kitchen"]["policy"] == "cross_contact_warning"
    assert merged["kitchen"]["statements"] == ["We accommodate", "Nuts used"]


def test_repeated_dishes_are_merged_keeping_the_riskier_rating():
    from gonuts.agents.verifier import dedupe_dishes
    dishes = [{"name": "Wedge Salad", "risk": "none_listed", "verified": True},
              {"name": "wedge salad ", "risk": "unclear", "verified": True},   # dinner menu copy
              {"name": "Calamari", "risk": "unclear", "verified": True}]
    out = dedupe_dishes(dishes)
    assert len(out) == 2
    assert next(d for d in out if d["name"].lower().strip() == "wedge salad")["risk"] == "unclear"


def test_garbled_model_answer_gives_a_friendly_error():
    with pytest.raises(ModelError, match="garbled"):
        parse_json('{"dishes": [{"name": "Pad Thai", "risk": "contains"')


# ---- Menu finding

HOME = """<html><body>
<a href="/locations/">Our locations</a>
<a href="https://spam-casino.example/win">menu of prizes</a>
<a href="/menu/">Menu</a>
<a href="/media/Dinner-Menu.pdf">Dinner menu (PDF)</a>
<a href="/gift-cards">Gift card menu</a>
<a href="/about">About</a>
</body></html>"""


def test_menu_links_rank_pdfs_first_and_skip_off_site_and_junk():
    links = web.find_menu_links(HOME, "https://restaurant.example/")
    assert links[0] == "https://restaurant.example/media/Dinner-Menu.pdf"
    assert "https://restaurant.example/menu/" in links
    assert not any("spam-casino" in l or "locations" in l or "gift" in l for l in links)


def test_chain_store_page_can_follow_links_to_the_main_site_only():
    html = """<a href="https://www.chipotle.com/menu">Menu</a>
              <a href="https://order-chipotle.example.com/menu">menu elsewhere</a>"""
    links = web.find_menu_links(html, "https://locations.chipotle.com/ct/new-haven/910-chapel-st")
    assert links == ["https://www.chipotle.com/menu"]


def test_nearly_empty_site_is_skipped_without_a_model_call(monkeypatch):
    class Resp:
        url, text, content = "https://js-only.example/", "<html><body>Loading...</body></html>", b""
        headers = {"Content-Type": "text/html"}
    monkeypatch.setattr(web, "_download", lambda url: Resp())
    with pytest.raises(web.FetchError, match="almost no readable text"):
        web.fetch_menu_text("https://js-only.example/")


def test_website_errors_are_plain_english():
    assert web._friendly("https://slow.example/", requests.Timeout()) == "slow.example took too long to respond."
    resp = requests.Response()
    resp.status_code = 403
    assert "blocked our menu reader" in web._friendly("https://x.example/", requests.HTTPError(response=resp))


# ---- Rule 3: no personal information, no photos of people

@pytest.mark.parametrize("text", [
    "Ask for jane.doe@gmail.com, she was great",
    "Call me at (203) 555-0142 if you want details",
    "I live at 12 Orange Street so I go often",
    "Our server @nhvfoodie knew everything",
])
def test_posts_with_personal_information_are_rejected(make_team, text):
    team, _ = make_team()
    out = team.send("user", "verifier", "moderate_post", {"text": text})
    assert out["ok"] is False and "personal information" in out["reason"]


def test_normal_review_with_a_price_is_allowed(make_team):
    team, _ = make_team()
    out = team.send("user", "verifier", "moderate_post",
                    {"text": "Pad see ew ($16) was great, staff checked the sauce with the chef."})
    assert out["ok"] is True


def test_nickname_with_contact_details_is_rejected(make_team):
    team, _ = make_team()
    assert team.send("user", "verifier", "check_nickname", {"nickname": "sam@yale.edu"})["ok"] is False
    assert team.send("user", "verifier", "check_nickname", {"nickname": "PeanutFreeSam"})["ok"] is True


@pytest.mark.parametrize("model_answer, ok", [
    ({"people_visible": False, "personal_info": False, "is_food": True}, True),
    ({"people_visible": True, "personal_info": False, "is_food": True}, False),
    ({"people_visible": False, "personal_info": True, "is_food": True}, False),
    ({}, False),  # no clear answer: fail closed
])
def test_community_photo_screen_fails_closed(make_team, model_answer, ok):
    team, _ = make_team(answers={"fetcher:screen": model_answer})
    out = team.send("user", "fetcher", "screen_photo", {"image_b64": "AAAA", "mime": "image/jpeg"})
    assert out["ok"] is ok


def test_theme_uses_only_drawn_shapes_no_remote_images():
    from urllib.parse import unquote
    css = unquote(theme.CSS).replace("http://www.w3.org/2000/svg", "")
    assert "http" not in css and "<image" not in css
