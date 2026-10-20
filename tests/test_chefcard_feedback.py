"""The allergy chef card and the anonymous feedback form."""
import pytest

from gonuts import chefcard
from gonuts.db import DB

SEVERE = {"allergens": ["Peanuts", "All tree nuts"], "severity": "Severe (anaphylaxis, carry epinephrine)"}


def test_card_names_every_nut_and_the_severity():
    text = " ".join(chefcard.card_lines(SEVERE, "en")["lines"])
    for nut in ("peanuts", "almonds", "cashews", "walnuts", "pistachios", "hazelnuts", "pecans"):
        assert nut in text
    assert "anaphylaxis" in text and "epinephrine" in text and "cross-contact" in text


def test_card_examples_match_the_diners_nuts():
    text = " ".join(chefcard.card_lines({"allergens": ["Cashews"], "severity": "Mild"}, "en")["lines"])
    assert "cashew-based vegan cheese" in text and "marzipan" not in text  # marzipan is almond
    assert "anaphylaxis" not in text                                      # only for severe allergies
    peanut_only = " ".join(chefcard.card_lines({"allergens": ["Peanuts"], "severity": "Moderate"}, "en")["lines"])
    assert "peanut sauce" in peanut_only and "pesto" not in peanut_only


def test_spanish_card_is_complete_and_fixed_text():
    es = chefcard.card_lines(SEVERE, "es")
    assert es["title"] == "Alergia alimentaria"
    assert "cacahuates" in es["lines"][0] and "frutos secos de árbol" in es["lines"][0]
    assert any("contaminación cruzada" in line for line in es["lines"])
    assert any("anafilaxia" in line for line in es["lines"])


def test_printable_card_has_both_languages_and_no_personal_details():
    html = chefcard.printable_html(SEVERE)
    assert "Food allergy" in html and "Alergia alimentaria" in html
    assert "<script" not in html and "http" not in html  # self-contained, nothing loaded from elsewhere


def test_feedback_needs_consent_and_stores_no_identity(tmp_path):
    db = DB(tmp_path / "t.db")
    with pytest.raises(ValueError):
        db.add_feedback({"relation": "Myself", "helpful": 5, "would_use": "Yes", "consent": False})
    db.add_feedback({"relation": "Myself: I have a nut allergy", "minutes_without": 15, "minutes_with": 3,
                     "helpful": 5, "would_use": "Yes", "comment": "Loved the chef card", "consent": True})
    (row,) = db.feedback_rows()
    assert row["minutes_without"] - row["minutes_with"] == 12
    assert len(row["created"]) == 10  # a date only, no time of day
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(feedback)")}
    assert not cols & {"name", "email", "ip", "session", "nickname", "location"}


def test_feedback_comments_with_personal_information_are_rejected(make_team):
    team, _ = make_team()
    assert team.send("user", "verifier", "moderate_post", {"text": "Email me at sam@yale.edu"})["ok"] is False


def test_every_language_has_every_phrase_and_nut():
    for code in chefcard.LANGUAGES:
        assert set(chefcard.TEXT[code]) == set(chefcard.TEXT["en"]), code
        assert len(chefcard.TEXT[code]["tree_examples"]) == len(chefcard.EXAMPLE_NUTS), code
        for nut, names in chefcard.NAMES.items():
            assert names.get(code), (nut, code)
        lines = chefcard.card_lines(SEVERE, code)["lines"]
        assert len(lines) == 5 and all(line.strip() for line in lines), code


def test_arabic_card_reads_right_to_left_and_others_left_to_right():
    assert "dir='rtl'" in chefcard.card_html(SEVERE, "ar")
    assert "dir='ltr'" in chefcard.card_html(SEVERE, "zh")
    assert 'dir=\'rtl\'' in chefcard.printable_html(SEVERE, "ar")


def test_chinese_list_uses_chinese_punctuation():
    first = chefcard.card_lines({"allergens": ["Peanuts", "Cashews", "Walnuts"], "severity": "Mild"}, "zh")["lines"][0]
    assert first == "我对以下食物过敏：花生、腰果和核桃。"


def test_printable_page_pairs_english_with_the_chosen_language():
    html = chefcard.printable_html(SEVERE, "fr")
    assert "Food allergy" in html and "Allergie alimentaire" in html and "Alergia alimentaria" not in html
    assert chefcard.printable_html(SEVERE, "en").count("<section") == 1
