"""Contact details and the map: real data only, nothing guessed."""
from gonuts import osm, places, theme, web
from gonuts.db import DB


def test_phone_and_address_come_from_openstreetmap_tags_only():
    tags = {"addr:housenumber": "964", "addr:street": "Chapel Street", "addr:city": "New Haven",
            "addr:state": "CT", "addr:postcode": "06510", "phone": "+1-203-624-0507;+1-203-555-0100"}
    assert osm.full_address(tags) == "964 Chapel Street, New Haven, CT 06510"
    assert osm.clean_phone(tags["phone"]) == "+1-203-624-0507"
    assert osm.full_address({"addr:city": "New Haven"}) == ""   # no street: blank, not guessed
    assert osm.clean_phone("ext 12") is None                    # not a full number: dropped


def test_phone_from_the_restaurants_own_website():
    html = "<a href='/menu'>Menu</a><a href='tel:2037776736'>Call us</a>"
    assert web.find_phone(html) == "2037776736"
    assert web.find_phone("<a href='tel:911'>x</a>") is None
    # a placeholder number left in a website template (seen on a real New Haven site) is dropped
    assert web.find_phone("<a href='tel:+6567025018'>x</a>") is None
    assert web.us_phone("+1 (203) 624-0507") == "+1 (203) 624-0507"
    assert web.us_phone("203.777.6736") == "203.777.6736"
    assert web.us_phone("(123) 456-7890") is None  # US area codes never start with 0 or 1


def test_call_and_directions_links():
    assert places.tel_link("+1 (203) 624-0507") == "tel:+12036240507"
    assert places.tel_link(None) is None
    assert places.directions_link({"name": "X", "lat": 41.3, "lon": -72.9}).endswith("destination=41.3,-72.9")
    assert places.directions_link({"name": "X"}) is None


def test_contact_card_says_when_details_are_missing():
    card = theme.contact_card({"name": "Zoi's"}, None, None)
    assert "No street address listed" in card and "No phone listed" in card


def test_map_pins_score_checked_restaurants_and_leave_others_unchecked(tmp_path):
    db = DB(tmp_path / "t.db")
    k1 = db.upsert_restaurant({"name": "Checked", "lat": 41.3, "lon": -72.9, "phone": "+1 203 555 0142"})
    db.upsert_restaurant({"name": "Unchecked", "lat": 41.31, "lon": -72.91})
    db.upsert_restaurant({"name": "No location"})
    report = {"is_menu": True, "kitchen": {"policy": "no_info"},
              "dishes": [{"name": f"Salad {i}", "risk": "none_listed", "nuts": []} for i in range(10)],
              "counts": {"contains": 0, "likely": 0, "unclear": 0, "none_listed": 10}}
    db.save_analysis(k1, "h", report, 100)
    pts = {p["name"]: p for p in places.map_points(db, {"allergens": ["Peanuts"]})}
    assert set(pts) == {"Checked", "Unchecked"}
    assert pts["Checked"]["score"] == 100 and pts["Checked"]["band"] == "good"
    assert pts["Unchecked"]["band"] == "unchecked" and pts["Unchecked"]["phone_text"] == "No phone listed"


def test_chains_and_tiny_menus_are_flagged_partial(tmp_path):
    ten = {"dishes": [{"name": f"d{i}"} for i in range(10)]}
    four = {"dishes": [{"name": f"d{i}"} for i in range(4)]}
    assert places.partial_reason({"website": "https://locations.chipotle.com/ct/x"}, ten).startswith("This is a national chain")
    assert "Only 4 dishes" in places.partial_reason({"website": "https://louislunch.com/"}, four)
    assert places.partial_reason({"website": "https://louislunch.com/"}, ten) is None

    db = DB(tmp_path / "t.db")
    k = db.upsert_restaurant({"name": "Subway", "lat": 41.3, "lon": -72.9,
                              "website": "https://restaurants.subway.com/united-states/ct/new-haven/50-whitney-ave"})
    db.save_analysis(k, "h", {"is_menu": True, "kitchen": {}, "dishes": [{"name": "Club", "risk": "none_listed", "nuts": []}],
                              "counts": {"contains": 0, "likely": 0, "unclear": 0, "none_listed": 1}}, 50)
    (pin,) = places.map_points(db, {"allergens": ["Peanuts"]})
    assert pin["band"] == "partial"  # never green just because 1 featured item had no nuts


def _photo_team(make_team, pages):
    """Fake model: each 'photo' is its page text; the Analyst rates every line as a dish."""
    def read(system, user):
        text = pages[user[1]["image_url"]["url"].split(",")[1]]
        return {"is_menu": text is not None, "text": text or ""}

    def analyze(system, user):
        menu = user.split("<menu>\n")[1].split("\n</menu>")[0]
        return {"is_menu": True, "dishes": [{"name": l.split(" - ")[0], "risk": "none_listed", "nuts": [],
                                             "evidence": l, "reason": "r"} for l in menu.splitlines() if " - " in l]}
    return make_team(answers={"fetcher": read, "analyst": analyze, "summarizer": {"restaurants": []}})


def test_menu_photos_are_saved_to_that_restaurant_and_capped(make_team):
    from gonuts import config
    pages = {f"p{i}": f"Dish {i} - rice, beans" for i in range(6)}
    pages["cat"] = None  # a photo that isn't a menu is skipped
    team, fake = _photo_team(make_team, pages)
    key = team.db.upsert_restaurant({"name": "Tikkaway", "lat": 41.3, "lon": -72.9})
    images = [{"image_b64": "cat"}] + [{"image_b64": f"p{i}"} for i in range(6)]
    out = team.send("user", "summarizer", "check_menu",
                    {"profile": {"allergens": ["Peanuts"]}, "name": "Tikkaway", "images": images})
    assert out["is_menu"] and out["restaurant"]["key"] == key
    assert len([a for a, _ in fake.prompts if a == "fetcher"]) == config.MAX_MENU_PHOTOS  # never more pages
    saved = team.db.latest_analysis(key)["result"]
    assert len(saved["dishes"]) == config.MAX_MENU_PHOTOS - 1  # 4 photos read, 1 was not a menu
    assert "from a diner" in saved["sources"][0] and "skipped" in saved["sources"][0]


def test_same_menu_photo_twice_costs_nothing_the_second_time(make_team):
    team, fake = _photo_team(make_team, {"p": "Dish - rice"})
    for _ in range(2):
        team.send("user", "cost_control", "get_menu_report", {"name": "X", "images": [{"image_b64": "p"}]})
    assert len([a for a, _ in fake.prompts if a == "fetcher"]) == 1


def test_failures_are_one_plain_sentence_with_no_web_addresses():
    chain = places.failure_message("locations.panerabread.com blocked our menu reader.",
                                   "https://locations.panerabread.com/ct/new-haven/1060-chapel-street.html")
    assert "national chain" in chain and "panerabread.com" not in chain and ".)" not in chain
    local = places.failure_message("www.eatcheesesteak.com blocked our menu reader.", "https://www.eatcheesesteak.com/")
    assert local.startswith("Its website blocks") and "eatcheesesteak" not in local and "photo" in local
    assert places.failure_message("x.com took too long to respond.", "https://x.com").endswith("Try again later.")
    assert places.failure_message("odd error", None) == "odd error."


def test_search_results_say_what_to_expect_before_you_tick():
    assert places.menu_outlook({"website": "https://zoisnewhaven.com/"}, True) == "Checked: instant"
    assert places.menu_outlook({"website": "https://locations.panerabread.com/x"}, False).startswith("Chain")
    assert places.menu_outlook({"website": "https://zoisnewhaven.com/"}, False) == "Not checked yet"
    assert places.menu_outlook({"website": "https://locations.chipotle.com/x"}, True) == "Checked: partial menu"


def test_long_place_names_are_shortened():
    assert places.short_place("New Haven, South Central Connecticut Planning Region, Connecticut, United States") \
        == "New Haven, Connecticut"
    assert places.short_place("your location") == "your location"


def test_new_phone_never_overwrites_a_stored_one(tmp_path):
    db = DB(tmp_path / "t.db")
    key = db.upsert_restaurant({"name": "Zinc", "phone": "+1 203 624 0507"})
    db.set_phone(key, "203 999 0000")
    db.upsert_restaurant({"name": "Zinc"})  # a later search without a phone keeps the stored one
    assert db.restaurant(key)["phone"] == "+1 203 624 0507"


def test_old_database_without_phone_column_is_upgraded(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE restaurants (key TEXT PRIMARY KEY, name TEXT NOT NULL, cuisine TEXT, address TEXT, "
                "website TEXT, menu_url TEXT, lat REAL, lon REAL, city TEXT, updated TEXT)")
    con.commit()
    con.close()
    db = DB(path)
    assert "phone" in {r["name"] for r in db.conn.execute("PRAGMA table_info(restaurants)")}
