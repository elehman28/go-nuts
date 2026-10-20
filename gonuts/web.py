"""Menu Fetcher: turn a restaurant URL (web page or PDF) into plain menu text.

No model calls happen here, so fetching costs no tokens.
"""
import base64
import io
import json
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image
from pypdf import PdfReader

from . import config

HEADERS = {"User-Agent": "Mozilla/5.0 (Go Nuts student project; menu reader)"}
MAX_DOWNLOAD_BYTES = 5_000_000
MENU_WORDS = ("menu", "food", "dinner", "lunch", "brunch", "eat")


class FetchError(Exception):
    pass


def _check_public_url(url: str):
    """Only allow http(s) URLs that point at the public internet (the app is hosted publicly)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise FetchError("Please enter a full web address starting with http:// or https://")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise FetchError(f"Could not find the website {parsed.hostname}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise FetchError("That address is not a public website.")


def _friendly(url: str, e: requests.RequestException) -> str:
    """A short, plain-English reason a website couldn't be read."""
    host = urlparse(url).hostname or url
    if isinstance(e, requests.Timeout):
        return f"{host} took too long to respond."
    if isinstance(e, requests.ConnectionError):
        return f"Could not connect to {host}. The website may be down."
    code = getattr(e.response, "status_code", None)
    if code in (401, 403):
        return f"{host} blocked our menu reader."
    if code == 404:
        return f"{host} says that page doesn't exist (404)."
    if code and code >= 500:
        return f"{host} is having server problems (error {code})."
    return f"Could not load {host}" + (f" (error {code})." if code else ".")


def _is_pdf(resp: requests.Response) -> bool:
    return "pdf" in resp.headers.get("Content-Type", "") or resp.url.lower().split("?")[0].endswith(".pdf")


def _download(url: str) -> requests.Response:
    _check_public_url(url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, stream=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise FetchError(_friendly(url, e))
    limit = config.MAX_PDF_BYTES if _is_pdf(resp) else MAX_DOWNLOAD_BYTES
    content = resp.raw.read(limit + 1, decode_content=True)
    if len(content) > limit:
        raise FetchError(f"{urlparse(url).hostname} sent a file too large to read ({limit // 1_000_000} MB max).")
    resp._content = content
    return resp


def pdf_to_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "nav", "footer"]):
        tag.decompose()
    lines = (line.strip() for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


SKIP_LINK_WORDS = ("location", "gift", "career", "job", "login", "account", "cart", "press", "news",
                   "blog", "event", "reserv", "contact", "privacy", "terms", "facebook", "instagram")


def _site(host: str) -> str:
    """The company's domain: locations.chipotle.com and www.chipotle.com are both chipotle.com,
    so a chain's store page can lead to its main menu. Other companies' sites still don't count."""
    labels = (host or "").lower().rstrip(".").split(".")
    keep = 3 if len(labels) >= 3 and ".".join(labels[-2:]) in ("co.uk", "com.au", "co.nz") else 2
    return ".".join(labels[-keep:])


def find_menu_links(html: str, base_url: str, limit: int = config.MAX_MENU_LINKS) -> list[str]:
    """Links on a homepage most likely to be the menu, best first.

    Only links on the restaurant's own website are followed (a hacked or expired site can be full
    of spam links), plus PDFs, which are where many restaurants keep their real menu."""
    soup = BeautifulSoup(html, "html.parser")
    home = _site(urlparse(base_url).hostname)
    scored = {}
    for a in soup.find_all("a", href=True):
        full = urljoin(base_url, a["href"]).split("#")[0]
        u = urlparse(full)
        if u.scheme not in ("http", "https") or full.rstrip("/") == base_url.split("#")[0].rstrip("/"):
            continue
        path, label = u.path.lower(), a.get_text(" ", strip=True).lower()
        is_pdf = path.endswith(".pdf")
        if _site(u.hostname) != home and not is_pdf:
            continue
        if any(w in path for w in SKIP_LINK_WORDS):
            continue
        score = 0
        if "menu" in path or "menu" in label:
            score += 50
        elif any(w in path or w in label for w in MENU_WORDS):
            score += 20
        if score and is_pdf:
            score += 40
        if label in ("menu", "menus", "food", "food menu", "dinner", "lunch"):
            score += 10
        if score:
            scored[full] = max(score, scored.get(full, 0))
    return sorted(scored, key=lambda link: -scored[link])[:limit]


def _page_text(resp: requests.Response) -> str:
    if _is_pdf(resp):
        try:
            return pdf_to_text(resp.content)
        except Exception:
            return ""  # a broken or scanned PDF: treat as no text
    return html_to_text(resp.text)


def us_phone(raw: str | None) -> str | None:
    """The number as written if it is a valid US number, else None. Website templates sometimes
    ship placeholder numbers (one New Haven site linked to a Singapore number), so anything that
    isn't a US number is dropped rather than shown."""
    if not raw:
        return None
    raw = raw.strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if raw.startswith("+") and not digits.startswith("1"):
        return None
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01" or digits[3] in "01":
        return None
    return raw


def find_phone(html: str) -> str | None:
    """The first US phone number the restaurant's own page links to (tel: links). Never guessed."""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if a["href"].lower().startswith("tel:"):
            number = us_phone(a["href"][4:])
            if number:
                return number
    return None


def fetch_phone(url: str) -> str | None:
    """Read just the restaurant's homepage for a phone number. Free: no model call."""
    resp = _download(url)
    return None if _is_pdf(resp) else find_phone(resp.text)


# ---- GoNation: a Connecticut restaurant-website platform. The page is built with JavaScript, but the
# menu is public JSON ("power lists"), so it can be read as plain text with no model call.
GONATION_API = "https://data.prod.gonation.com/pl/get"
# Food first, then cocktails (nut liqueurs like Frangelico and amaretto matter), then wine, beer and
# soft drinks last: tasting notes ("hints of almond") would add noise and crowd out dishes.
_LATE_SECTIONS = ("wine", "beer", "sake", "soda", "juice", "water", "coffee", "tea", "bottle", "on tap", "cane")
_DRINK_SECTIONS = ("drink", "cocktail", "spritz", "stirred", "martini", "mocktail", "bar", "non-alcoholic")


def gonation_id(html: str, base_url: str) -> str | None:
    """The site's GoNation profile id, or None if it isn't a GoNation site."""
    if "gonation" not in html.lower() and "gatsby-theme-minimal" not in html:
        return None
    id_re = re.compile(r"""gonationID["']?\s*[:=]\s*["'](bzn-[A-Za-z0-9_-]+)["']""")
    m = id_re.search(html)
    if m:
        return m.group(1)
    # Newer sites (Gatsby) keep it in page data; older ones in one of the site's own scripts.
    home = _site(urlparse(base_url).hostname)
    candidates = [urljoin(base_url, "/page-data/index/page-data.json")] + [
        u for u in (urljoin(base_url, s) for s in re.findall(r'<script[^>]+src="([^"]+)"', html))
        if _site(urlparse(u).hostname) == home][:3]  # loop limit: 3 scripts
    for u in candidates:
        try:
            m = id_re.search(_download(u).text)
        except FetchError:
            continue
        if m:
            return m.group(1)
    return None


def _gonation_item(item: dict) -> str:
    name = " ".join(str(item.get("name") or "").split())
    desc = " ".join(str(item.get("desc") or "").split())
    prices = [f"${v['price']}" for v in item.get("variants") or [] if str(v.get("price") or "").strip()]
    return " - ".join(x for x in (name, desc) if x) + (f"  {' / '.join(prices)}" if prices else "")


def gonation_menu_text(profile_id: str) -> str | None:
    """All of a GoNation restaurant's menu lists as plain text, food first. None if empty."""
    sections, seen = [], set()  # (priority, heading, lines)

    def walk(node, path):
        for child in node.get("inventory") or []:
            if "section" in child:
                sec = child["section"]
                name = " ".join(str(sec.get("name") or "").split())
                items = []
                for c in child.get("inventory") or []:
                    if "item" not in c:
                        continue
                    line = _gonation_item(c["item"])
                    ident = c["item"].get("_id") or line  # lists repeat items; some items have no id
                    if line and ident not in seen:
                        seen.add(ident)
                        items.append(line)
                heading = " > ".join(p for p in path + [name] if p)
                low = heading.lower()
                prio = 2 if any(w in low for w in _LATE_SECTIONS) else 1 if any(w in low for w in _DRINK_SECTIONS) else 0
                if items:
                    sections.append((prio, heading, items))
                walk(child, path + [name])

    for n in range(1, config.MAX_GONATION_LISTS + 1):  # loop limit: a fixed number of lists
        try:
            resp = _download(f"{GONATION_API}?profile_id={profile_id}&powerlistId=powered-list-{n}")
            lists = resp.json()
        except (FetchError, ValueError):
            continue
        for pl in lists if isinstance(lists, list) else []:
            walk(pl, [])
    if not sections:
        return None
    sections.sort(key=lambda s: s[0])  # stable: keeps the restaurant's own order within each group
    return "\n\n".join(f"{heading}\n" + "\n".join(lines) for _, heading, lines in sections)


# ---- Menus posted as pictures: the Menu Fetcher can read up to MAX_MENU_IMAGES of them with the model.
_SKIP_IMAGE_WORDS = ("logo", "icon", "favicon", "sprite", "badge", "avatar", "banner-ad")


def find_menu_images(html: str, base_url: str, limit: int = 8) -> list[str]:
    """Images that look like pictures of the menu (the word 'menu' in the file name or alt text)."""
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if img.get("srcset") and not src:
            src = img["srcset"].split(",")[-1].strip().split(" ")[0]
        label = (src + " " + (img.get("alt") or "") + " " + (img.get("title") or "")).lower()
        if "menu" not in label or any(w in label for w in _SKIP_IMAGE_WORDS) or src.startswith("data:"):
            continue
        full = urljoin(base_url, src)
        if full.startswith("http") and full not in found:
            found.append(full)
    return found[:limit]


def image_for_model(url: str, min_side: int = 500) -> dict | None:
    """Download one menu image and shrink it for the model. None if it's too small to be a menu."""
    try:
        resp = _download(url)
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception:
        return None
    if max(img.size) < min_side:
        return None
    img.thumbnail((2000, 2000))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return {"image_b64": base64.b64encode(buf.getvalue()).decode(), "mime": "image/jpeg", "url": resp.url}


THIN_TEXT_MESSAGE = ("This website has almost no readable text. Its menu is probably built with JavaScript "
                     "or shown as images. Try uploading a photo of the menu or pasting the text.")
PRICE_RE = re.compile(r"\$\s?\d|\b\d{1,3}\.\d{2}\b")


def fetch_menu_page(url: str) -> dict:
    """Everything the Menu Fetcher needs from a restaurant website, without any model calls:
    {text, sources, phone, images, platform}. `images` are menu pictures to read if the text
    doesn't look like a menu."""
    resp = _download(url)
    if _is_pdf(resp):
        return {"text": truncate(_page_text(resp)), "sources": [resp.url], "phone": None, "images": [],
                "platform": "pdf"}
    phone = find_phone(resp.text)

    gid = gonation_id(resp.text, resp.url)
    if gid:
        text = gonation_menu_text(gid)
        if text:
            return {"text": truncate(text), "sources": [resp.url + " (GoNation menu data)"], "phone": phone,
                    "images": [], "platform": "gonation"}

    home_text = _page_text(resp)
    images = find_menu_images(resp.text, resp.url)
    menu_parts, sources = [], []
    for link in find_menu_links(resp.text, resp.url):
        try:
            sub = _download(link)
        except FetchError:
            continue
        text = _page_text(sub)
        if text.strip():
            menu_parts.append(text)
            sources.append(sub.url)
        if not _is_pdf(sub):
            images += [i for i in find_menu_images(sub.text, sub.url) if i not in images]
    sources.append(resp.url)
    text = "\n\n".join(p for p in menu_parts + [home_text] if p.strip())
    return {"text": truncate(text), "sources": sources, "phone": phone, "images": images[:8], "platform": "html"}


TEXT_ADDRESS_RE = re.compile(
    r"(?P<street>\b\d{1,5}[A-Za-z]?\s+(?:[A-Z][\w.'’-]*\s+){1,4}?"
    r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Drive|Dr\.?|Lane|Ln\.?|Way|Place|Pl\.?|Court|Ct\.?|"
    r"Square|Sq\.?|Turnpike|Tpke\.?|Highway|Hwy\.?)(?:\s*(?:#|Suite|Ste\.?|Unit)\s*\w+)?)"
    r"[,\s]+(?P<town>New Haven|Hamden|West Haven|East Haven|North Haven|Woodbridge|Orange|Branford)"
    r"(?:,?\s*(?:CT|Connecticut))?(?:,?\s*(?P<zip>06\d{3}))?")


def website_address(url: str) -> str | None:
    """The street address a restaurant's own website publishes in machine-readable form
    (schema.org JSON-LD, or GoNation business data). Only Connecticut addresses are accepted, so a
    chain's head-office address can't be mistaken for the local restaurant. None if not found."""
    resp = _download(url)
    if _is_pdf(resp):
        return None
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack and len(found) < 20:  # loop limit
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                addr = node.get("address")
                if isinstance(addr, dict) and addr.get("streetAddress"):
                    found.append((addr.get("streetAddress"), addr.get("addressLocality"),
                                  addr.get("addressRegion"), addr.get("postalCode")))
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    # Addresses printed as plain text ("754 State St, New Haven, CT 06511"), from the site itself.
    text = " ".join(BeautifulSoup(html, "html.parser").get_text(" ").split())
    for m in TEXT_ADDRESS_RE.finditer(text):
        found.append((m.group("street"), m.group("town"), "CT", m.group("zip") or ""))
    m = re.search(r'"street":"([^"]+)","zip":"(\d{5})"', html)  # GoNation business data
    if m:
        found.append((m.group(1), None, "CT", m.group(2)))
    for street, city, region, postcode in found:
        street = " ".join(str(street).split())
        region, postcode = str(region or "").strip(), str(postcode or "").strip()
        if not re.match(r"^\d", street):
            continue  # needs a house number
        if not (region.upper() in ("CT", "CONNECTICUT") or postcode.startswith("06")):
            continue  # not a Connecticut address: probably a head office
        state = "CT" if region.upper() in ("CT", "CONNECTICUT", "") else region
        return ", ".join(filter(None, [street, str(city or "").strip(), " ".join(filter(None, [state, postcode]))]))
    return None


def looks_like_menu_text(text: str) -> bool:
    """Enough text, with prices, to be worth sending to the Menu Analyst."""
    return len(text.strip()) >= config.MIN_MENU_CHARS and len(PRICE_RE.findall(text)) >= 5


def fetch_menu_text(url: str) -> tuple[str, list[str], str | None]:
    """Text-only menu reading (no pictures). Return (menu text, URLs read, phone or None)."""
    page = fetch_menu_page(url)
    if len(page["text"].strip()) < config.MIN_MENU_CHARS:
        raise FetchError(THIN_TEXT_MESSAGE)
    return page["text"], page["sources"], page["phone"]


def truncate(text: str) -> str:
    if len(text) <= config.MAX_MENU_CHARS:
        return text
    return text[: config.MAX_MENU_CHARS] + "\n[...menu cut off for length...]"
