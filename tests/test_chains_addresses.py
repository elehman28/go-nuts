"""Official chain allergen data and address filling. Offline: downloads are faked."""
import json

from gonuts import chains, osm, places, web


class FakeResp:
    def __init__(self, url, text="", content=b"", ctype="text/html"):
        self.url, self.text, self.content = url, text, content or text.encode()
        self.headers = {"Content-Type": ctype}


def test_every_chain_links_to_its_own_allergen_page():
    assert chains.guide_url("https://locations.chipotle.com/ct/new-haven/910-chapel-st") == "https://www.chipotle.com/allergens"
    assert chains.guide_url("https://zoisnewhaven.com/") is None
    for domain, url in chains.GUIDES.items():
        assert domain in url  # only the company's own website, never a third party


def test_official_statement_is_used_only_if_still_on_the_page(monkeypatch):
    page = f"<html><p>{chains.CHIPOTLE['quote']}</p></html>"
    monkeypatch.setattr(web, "_download", lambda url: FakeResp(url, page))
    report = chains.official_report("https://locations.chipotle.com/ct/x")
    assert report["official_source"]["url"] == chains.CHIPOTLE["url"]
    assert report["kitchen"]["statements"] == [chains.CHIPOTLE["quote"]]
    assert places.partial_reason({"website": "https://locations.chipotle.com/x"}, report) is None
    assert all(d.get("source") == "official" for d in report["dishes"])

    monkeypatch.setattr(web, "_download", lambda url: FakeResp(url, "<html>New allergen policy</html>"))
    assert chains.official_report("https://locations.chipotle.com/ct/x") is None  # changed: not trusted


def test_official_data_never_drops_dishes_already_flagged(monkeypatch):
    page = f"<html><p>{chains.CHIPOTLE['quote']}</p></html>"
    monkeypatch.setattr(web, "_download", lambda url: FakeResp(url, page))
    store = {"dishes": [{"name": "Quesadilla", "risk": "unclear", "nuts": ["unknown"]}]}
    report = chains.official_report("https://locations.chipotle.com/ct/x", store)
    assert [d["risk"] for d in report["dishes"] if d["name"] == "Quesadilla"] == ["unclear"]


def test_words_are_split_by_gaps_between_characters():
    row = [(0, x, x + 5, 100, ch, "Arial") for x, ch in zip(range(0, 20, 5), "Nuts")]
    row += [(0, 40 + x, 45 + x, 100, ch, "Arial") for x, ch in zip(range(0, 30, 5), "Sesame")]
    assert [w[2] for w in chains._words(row)] == ["Nuts", "Sesame"]


def test_address_from_the_restaurants_own_website(monkeypatch):
    ld = {"@type": "Restaurant", "address": {"@type": "PostalAddress", "streetAddress": "63 Grove Street",
                                             "addressLocality": "New Haven", "addressRegion": "CT", "postalCode": "06510"}}
    hq = {"@type": "Organization", "address": {"streetAddress": "1401 Wynkoop St", "addressRegion": "CO",
                                               "postalCode": "80202"}}
    html = f'<script type="application/ld+json">{json.dumps([hq, ld])}</script>'
    monkeypatch.setattr(web, "_download", lambda url: FakeResp(url, html))
    assert web.website_address("https://zois.example/") == "63 Grove Street, New Haven, CT 06510"  # not the HQ


def test_reverse_lookup_drops_impossible_postcodes(monkeypatch):
    class R:
        def raise_for_status(self): pass
        def json(self): return {"address": {"road": "Long Wharf Trail", "city": "New Haven", "state": "Connecticut",
                                            "postcode": "05610"}}
    monkeypatch.setattr(osm.requests, "get", lambda *a, **k: R())
    assert osm.reverse_address(41.29, -72.92) == "Long Wharf Trail, New Haven, CT"


def test_nearest_numbered_address_within_25_metres_only():
    addrs = [(41.30800, -72.92800, "1 Near St, New Haven, CT 06510"), (41.31000, -72.92800, "9 Far St")]
    assert osm.nearest_address(41.30810, -72.92805, addrs) == "1 Near St, New Haven, CT 06510"  # ~12 m away
    assert osm.nearest_address(41.30900, -72.92800, addrs) is None                               # ~110 m away


def test_multi_value_addresses_are_tidied():
    assert osm.tidy_street("324;326", "Shelton Avenue") == "324–326 Shelton Avenue"
    assert osm.tidy_street("15;1407;1415", "Beers Street;Chapel Street") == "15 Beers Street"
    assert osm.tidy_street("1000", "Chapel Street") == "1000 Chapel Street"
