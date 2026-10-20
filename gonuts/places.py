"""Restaurant contact details and map pins. Plain code, no model calls.

Safety rule: phone numbers and addresses are only ever shown as stored (from OpenStreetMap or the
restaurant's own website). Missing details stay missing; nothing is guessed.
"""
from urllib.parse import quote_plus, urlparse

from .agents.summarizer import apply_profile, score

CALL_TIP = ("Have a question about an ingredient? Call the restaurant before you go. "
            "Phone numbers are on the Map tab and on every restaurant result.")

# Pin colors (RGB) by Go Nuts score. For sorting only; never means safe.
# Okabe-Ito colors (readable with color blindness), plus a symbol on every pin so color is
# never the only signal.
PIN_COLORS = {
    "good": (0, 140, 102),      # score 60+: most dishes have no nuts listed
    "mixed": (222, 143, 5),     # 30-59
    "hard": (204, 78, 0),       # under 30: many dishes contain or likely contain nuts
    "partial": (148, 103, 189), # too few dishes read, or a national chain: the score isn't reliable
    "unchecked": (150, 150, 150),
}
PIN_SYMBOLS = {"good": "+", "mixed": "!", "hard": "x", "partial": "~", "unchecked": "?"}
PIN_LABELS = {
    "good": "Many dishes with no nuts listed (score 60+)",
    "mixed": "Some options, ask carefully (score 30-59)",
    "hard": "Mostly nuts or unclear (score under 30)",
    "partial": "Only part of the menu was read",
    "unchecked": "Menu not checked yet: tap to add a photo",
}

# Fewer dishes than this and we probably read a page of featured items, not the whole menu.
MIN_DISHES_FULL_MENU = 10

# National chains: their store pages show a few featured items and their full menus are built
# with JavaScript, so Go Nuts never sees the whole menu.
CHAIN_DOMAINS = {
    "bk.com", "chipotle.com", "dairyqueen.com", "dominos.com", "dunkindonuts.com", "kfc.com",
    "mcdonalds.com", "panerabread.com", "papajohns.com", "popeyes.com", "starbucks.com",
    "subway.com", "wendys.com",
}


def is_chain(website: str | None) -> bool:
    host = urlparse(website or "").netloc.lower()
    return any(host == d or host.endswith("." + d) for d in CHAIN_DOMAINS)


# Why a menu couldn't be read, in plain words (no web addresses or error codes on screen).
_FAILURES = [
    ("blocked our menu reader", "Its website blocks automated menu readers."),
    ("took too long", "Its website took too long to respond. Try again later."),
    ("could not connect", "Its website seems to be down right now. Try again later."),
    ("could not find the website", "Its website no longer exists."),
    ("doesn't exist (404)", "The menu page on its website is missing."),
    ("server problems", "Its website is having problems right now. Try again later."),
    ("almost no readable text", "Its menu is a picture, or built in a way Go Nuts can't read."),
    ("no menu found", "We couldn't find a menu on its website."),
    ("too large", "Its menu file is too large to read."),
    ("no website listed", "It doesn't list a website."),
]
_PHOTO_HINT = " You can add a photo of its menu from the Map tab."


def failure_message(error: str, website: str | None = None) -> str:
    """One plain sentence for a menu that couldn't be checked, with what to do next."""
    if is_chain(website):
        return ("This is a national chain, and its website doesn't let Go Nuts read the full menu. "
                "Check the chain's official allergen guide, or call to ask.")
    low = (error or "").lower()
    for pattern, sentence in _FAILURES:
        if pattern in low:
            hint = "" if "try again" in sentence.lower() else _PHOTO_HINT
            return sentence + hint
    text = (error or "We couldn't read this menu.").strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def menu_outlook(r: dict, already_checked: bool) -> str:
    """What to expect before you tick a restaurant in search results."""
    chain = is_chain(r.get("website") or r.get("menu_url"))
    if already_checked:
        return "Checked: partial menu" if chain else "Checked: instant"
    if chain:
        return "Chain: often unreadable"
    return "Not checked yet"


US_STATES = {"Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware",
             "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
             "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri",
             "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York",
             "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
             "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
             "West Virginia", "Wisconsin", "Wyoming", "District of Columbia"}


def short_place(where: str) -> str:
    """'New Haven, South Central Connecticut Planning Region, Connecticut, United States'
    -> 'New Haven, Connecticut'. Short names are returned as they are."""
    parts = [p.strip() for p in (where or "").split(",") if p.strip()]
    if len(parts) <= 2:
        return ", ".join(parts)
    state = next((p for p in parts[1:] if p in US_STATES), parts[-2])
    return f"{parts[0]}, {state}"


def partial_reason(r: dict, report: dict) -> str | None:
    """Why this result covers only part of the menu, or None if it looks complete."""
    if report.get("official_source"):
        return None  # built from the chain's own allergen chart or statement, which covers the menu
    if is_chain(r.get("website") or r.get("menu_url")):
        return ("This is a national chain. Go Nuts could only read a few featured items from its store "
                "page, not the full menu. Check the chain's official allergen guide, and ask staff.")
    n = len(report.get("dishes") or [])
    if n < MIN_DISHES_FULL_MENU:
        return (f"Only {n} dish{'es' if n != 1 else ''} could be read from the website, so this may not be "
                "the full menu. Ask about anything not listed here.")
    return None


def tel_link(phone: str | None) -> str | None:
    """tel: link for a stored phone number, or None. Keeps only digits and a leading +."""
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 10:
        return None
    return "tel:" + ("+" if phone.strip().startswith("+") else "") + digits


def directions_link(r: dict) -> str | None:
    """Google Maps directions to the restaurant: its map location if known, else its address."""
    if r.get("lat") is not None and r.get("lon") is not None:
        return f"https://www.google.com/maps/dir/?api=1&destination={r['lat']},{r['lon']}"
    if r.get("address"):
        return "https://www.google.com/maps/dir/?api=1&destination=" + quote_plus(f"{r['name']}, {r['address']}")
    return None


def score_band(s: int | None) -> str:
    if s is None:
        return "unchecked"
    return "good" if s >= 60 else "mixed" if s >= 30 else "hard"


def map_points(db, profile: dict) -> list[dict]:
    """One pin per restaurant with a known location, scored for this diner's profile."""
    points = []
    for r in db.restaurants():
        if r.get("lat") is None or r.get("lon") is None:
            continue
        cached = db.latest_analysis(r["key"])
        s, partial = None, None
        if cached and cached["result"].get("is_menu"):
            acc, _ = db.accommodation_score(r["key"])
            s = score(apply_profile(cached["result"], profile), acc)
            partial = partial_reason(r, cached["result"])
        band = "partial" if partial else score_band(s)
        points.append({
            "key": r["key"],
            "name": r["name"],
            "cuisine": r.get("cuisine") or "",
            "lat": r["lat"],
            "lon": r["lon"],
            "address": r.get("address") or "",
            "address_source": r.get("address_source") or "",
            "address_text": (r.get("address") or "No street address listed")
                            + (" (approximate)" if r.get("address_source") == "map" and r.get("address") else ""),
            "phone": r.get("phone") or "",
            "phone_text": r.get("phone") or "No phone listed",
            "website": r.get("website") or "",
            "score": s,
            "score_text": (PIN_LABELS["partial"] if partial else f"Go Nuts score {s}/100" if s is not None
                           else PIN_LABELS["unchecked"]),
            "partial": bool(partial),
            "band": band,
            "symbol": PIN_SYMBOLS[band],
            "color": list(PIN_COLORS[band]) + [235],
        })
    return points
