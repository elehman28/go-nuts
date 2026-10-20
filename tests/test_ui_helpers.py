"""The helpers behind the redesign: progress, free cached results, Near me, and safe HTML."""
from gonuts import browser, osm, theme


def test_near_me_coordinates_are_checked_and_rounded():
    assert browser.parse_coords("41.30834,-72.92791") == (41.308, -72.928)  # ~100 m, never more precise
    assert browser.parse_coords("") is None
    assert browser.parse_coords("hello") is None
    assert browser.parse_coords("91,0") is None


def test_near_me_search_skips_the_address_lookup(make_team, monkeypatch):
    def no_geocode(place):
        raise AssertionError("Near me must not send anything to the address lookup")
    monkeypatch.setattr(osm, "geocode", no_geocode)
    monkeypatch.setattr(osm, "nearby_restaurants", lambda lat, lon, radius_m, limit=30: [
        {"name": "Zinc", "cuisine": "", "address": "", "phone": None, "website": "https://zincnewhaven.com",
         "menu_url": None, "lat": lat, "lon": lon, "distance_km": 0.1}])
    team, _ = make_team()
    out = team.send("user", "finder", "find_restaurants", {"lat": 41.308, "lon": -72.928, "radius_km": 1})
    assert out["where"] == "your location" and out["restaurants"][0]["name"] == "Zinc"
    assert team.db.restaurant(out["restaurants"][0]["key"])["city"] == "New Haven, CT"


def test_cached_entry_is_free_and_uses_the_profile(make_team):
    team, fake = make_team()
    key = team.db.upsert_restaurant({"name": "Olea"})
    team.db.save_analysis(key, "h", {"is_menu": True, "kitchen": {}, "counts": {}, "dishes": [
        {"name": "Almond cake", "risk": "contains", "nuts": ["almond"]}]}, 100)
    entry = team.send("user", "summarizer", "cached_entry", {"key": key, "profile": {"allergens": ["Peanuts"]}})
    assert fake.prompts == []                                      # no model call
    assert entry["report"]["profile_counts"]["unclear"] == 1      # almond isn't in a peanut-only profile
    assert team.send("user", "summarizer", "cached_entry", {"key": "nope", "profile": {}}) is None


def test_every_hand_off_is_reported_for_live_progress(make_team):
    team, _ = make_team()
    seen = []
    team.on_step = lambda step: seen.append((step["to"], step["task"]))
    team.send("user", "verifier", "moderate_post", {"text": "Great pad see ew."})
    assert seen == [("verifier", "moderate_post")]
    team.on_step = lambda step: 1 / 0  # a broken progress display never breaks the work
    assert team.send("user", "verifier", "moderate_post", {"text": "ok"})["ok"] is True


def test_text_from_websites_is_escaped_before_it_reaches_the_page():
    evil = {"name": "x", "address": "<script>alert(1)</script>", "phone": "203-555-0142",
            "website": "javascript:alert(1)'><img src=x onerror=alert(1)>"}
    card = theme.contact_card(evil, "tel:2035550142", None)
    assert "<script>" not in card and "<img" not in card
    assert "javascript:" not in card  # a javascript: "website" is never turned into a link
    assert "<b>" not in theme.note("AI", "<b>bold</b>") and "&lt;span&gt;" in theme.badge("contains", "<span>")
