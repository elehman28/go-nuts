"""GoNation menu data, menu pictures, and Your list. Offline, with fake downloads and the fake model."""
import json

from gonuts import browser, config, web


class FakeResp:
    def __init__(self, url, text="", content=b"", ctype="text/html"):
        self.url, self.text, self.content = url, text, content or text.encode()
        self.headers = {"Content-Type": ctype}

    def json(self):
        return json.loads(self.text)


GONATION_LIST = [{"name": "powered-list-1", "section": {"name": ""}, "inventory": [
    {"section": {"name": "Drinks"}, "inventory": [
        {"section": {"name": "Cocktails"}, "inventory": [
            {"item": {"_id": "c1", "name": "Thai Ice Tea", "desc": "Frangelico | Amaretto", "variants": [{"price": "12"}]}}]},
        {"section": {"name": "Wine"}, "inventory": [
            {"item": {"name": "Chardonnay", "desc": "notes of almond", "variants": [{"price": "11"}]}}]}]},
    {"section": {"name": "Main Menu"}, "inventory": [
        {"item": {"name": "Pad Thai", "desc": "rice noodles, crushed peanuts", "variants": [{"price": "16"}]}},
        {"item": {"name": "Green Curry", "desc": "coconut milk, Thai basil", "variants": [{"price": "17"}]}}]}]}]


def fake_gonation_site(monkeypatch):
    home = '<html><script>var gonationID = "bzn-TEST123456789";</script>Loading…</html>'

    def download(url):
        if "data.prod.gonation.com" in url:
            return FakeResp(url, json.dumps(GONATION_LIST if url.endswith("powered-list-1") else []), ctype="text/plain")
        return FakeResp(url, home)
    monkeypatch.setattr(web, "_download", download)


def test_gonation_menu_is_read_food_first_without_the_model(monkeypatch):
    fake_gonation_site(monkeypatch)
    page = web.fetch_menu_page("https://september.example/")
    assert page["platform"] == "gonation"
    text = page["text"]
    assert text.index("Pad Thai") < text.index("Thai Ice Tea") < text.index("Chardonnay")  # food, cocktails, wine
    assert "Green Curry - coconut milk, Thai basil  $17" in text      # items without an id are all kept
    assert "Frangelico" in text                                      # nut liqueurs in cocktails are not lost


def test_menu_pictures_are_found_but_logos_are_not():
    html = """<img src="/img/logo-menu.png"><img src="/media/dinner-menu-p1.jpg" alt="Dinner">
              <img data-src="https://cdn.example/x.jpg" alt="Our lunch menu"><img src="/hero.jpg">"""
    assert web.find_menu_images(html, "https://r.example/") == [
        "https://r.example/media/dinner-menu-p1.jpg", "https://cdn.example/x.jpg"]


def test_picture_menus_are_read_with_a_capped_number_of_model_calls(make_team, monkeypatch):
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (900, 1200), "white").save(buf, "JPEG")
    pics = [f"https://r.example/menu-{i}.jpg" for i in range(7)]
    home = "<html>" + "".join(f'<img src="{u}">' for u in pics) + "Welcome! Call us.</html>" + "x" * 400

    def download(url):
        if url.endswith(".jpg"):
            return FakeResp(url, content=buf.getvalue(), ctype="image/jpeg")
        return FakeResp(url, home)
    monkeypatch.setattr(web, "_download", download)
    team, fake = make_team(answers={"fetcher": {"is_menu": True, "text": "Satay - peanut sauce $9"}})
    out = team.send("user", "fetcher", "fetch_menu", {"url": "https://r.example/"})
    assert len([a for a, _ in fake.prompts if a == "fetcher"]) == config.MAX_MENU_IMAGES
    assert "Satay - peanut sauce" in out["text"] and out["sources"][0].startswith("4 menu pictures")


def test_your_list_cookie_only_accepts_restaurant_keys(monkeypatch):
    class Ctx:
        cookies = {browser.LIST_COOKIE: "zinc-new-haven,olea,<script>,zinc-new-haven," + ",".join(f"r{i}" for i in range(80))}
    monkeypatch.setattr(browser.st, "context", Ctx)
    keys = browser.load_list()
    assert keys[:2] == ["zinc-new-haven", "olea"] and "<script>" not in keys
    assert len(keys) == browser.MAX_SAVED and len(set(keys)) == len(keys)
