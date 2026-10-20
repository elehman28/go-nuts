"""National chains: official allergen information from the companies' own websites.

Chains' store pages show only a few featured items, but chains publish allergen guides. Most of
those guides load through JavaScript apps or block automated downloads, so for every chain we link
to the official guide, and for the ones a program can read reliably we build the report with plain
code (no AI), re-checking the official source each time:

  - Chipotle: an official statement that peanuts and tree nuts are not used as ingredients.
  - Domino's: the US allergen chart PDF. Read by POSITION on the page (which column each mark sits
    in), because plain PDF text loses columns. It marks no item in its "Nuts" column, but marks two
    desserts as made in a facility that handles peanuts and tree nuts.

Safety rule 2: every fact below is checked against the live official source at scan time. If the
source changed (quote or items no longer found), nothing is saved and the chain stays "partial".
"""
import io
import re
from datetime import date

from pypdf import PdfReader

from . import web
from .nuts import RISK_LEVELS

# Official allergen pages (company websites only; found Oct 19 2026). No page found for KFC US.
GUIDES = {
    "mcdonalds.com": "https://www.mcdonalds.com/us/en-us/contact-us/help-center/nutrition.html",
    "dunkindonuts.com": "https://www.dunkindonuts.com/nutrition/",
    "subway.com": "https://www.subway.com/en-us/menunutrition/nutrition",
    "chipotle.com": "https://www.chipotle.com/allergens",
    "starbucks.com": "https://www.starbucks.com/menu",
    "panerabread.com": "https://www.panerabread.com/en-us/menu/nutritious-eating/allergen-and-nutrition-information.html",
    "wendys.com": "https://www.wendys.com/nutrition-allergens",
    "popeyes.com": "https://www.popeyes.com/nutritional-information",
    "bk.com": "https://www.bk.com/nutrition-explorer",
    "dominos.com": "https://www.dominos.com/en/pages/content/nutritional/nutrition",
    "papajohns.com": "https://www.papajohns.com/company/nutrition-allergen-information.html",
    "dairyqueen.com": "https://www.dairyqueen.com/en-us/nutrition/",
}

CHIPOTLE = {
    "url": "https://www.chipotle.com/allergens",
    "quote": "Although we do not use eggs, mustard, peanuts, tree nuts, sesame, shellfish, or fish as ingredients "
             "in our food, Chipotle cannot guarantee the complete absence of these allergens in its restaurants.",
}
DOMINOS = {
    "url": "https://cache.dominos.com/olo/6_168_0/assets/build/market/US/_en/pdf/DominosNutritionGuide.pdf",
    "facility_note": "Manufactured in a facility that handles peanuts and tree nuts.",
}


def _domain(website: str | None) -> str | None:
    host = re.sub(r"^https?://", "", (website or "").lower()).split("/")[0]
    return next((d for d in GUIDES if host == d or host.endswith("." + d)), None)


def guide_url(website: str | None) -> str | None:
    """The chain's official allergen page, or None if it isn't a chain we know."""
    d = _domain(website)
    return GUIDES.get(d) if d else None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


# ---- Domino's: read the chart by position

def _page_chars(pdf_bytes: bytes):
    """Every character on every page with its position and font: [(page, x0, x1, y, text, font)]."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar
    out = []

    def walk(o, pno):
        if isinstance(o, LTChar):
            out.append((pno, o.x0, o.x1, o.y0, o.get_text(), o.fontname))
        elif hasattr(o, "__iter__"):
            for c in o:
                walk(c, pno)
    for pno, layout in enumerate(extract_pages(io.BytesIO(pdf_bytes))):
        walk(layout, pno)
    return out


def _words(chars) -> list[tuple[float, float, str]]:
    """Group characters on one line into words: [(x0, x1, word)], left to right."""
    words, cur = [], None
    for _, x0, x1, _, t, _ in sorted(chars, key=lambda c: c[1]):
        if cur and (x0 - cur[1] > 1.5 or t == " "):
            words.append(cur)
            cur = None
        if t.strip():
            cur = [x0, x1, t] if not cur else [cur[0], x1, cur[2] + t]
    if cur:
        words.append(cur)
    return [tuple(w) for w in words]


def dominos_nut_marks(pdf_bytes: bytes) -> dict:
    """Marks in the 'Nuts' columns of Domino's English allergen chart, read by position.
    ✓ (Wingdings 'ü') = contains; ■ (Wingdings 'n') = made in a facility with peanuts and tree nuts.
    Item names come only from their own table's Item column (the PDF merges side-by-side rows).
    Returns {"pages": n, "contains": [item names], "facility": [item names]}."""
    chars = _page_chars(pdf_bytes)
    out = {"pages": 0, "contains": [], "facility": []}
    for pno in sorted({c[0] for c in chars}):
        page = [c for c in chars if c[0] == pno]
        marks = [c for c in page if "Wingdings" in c[5] and c[4] in ("ü", "n")]
        if not marks:
            continue
        top = max(c[3] for c in marks)
        header = None
        for y in sorted({round(c[3], 1) for c in page if c[3] > top + 2})[:12]:  # nearest lines above the marks
            words = _words([c for c in page if abs(c[3] - y) < 0.6 and "Wingdings" not in c[5]])
            if {"Item", "Nuts"} <= {w[2] for w in words}:
                header = words
                break
        if not header:
            continue  # not the English chart
        out["pages"] += 1
        nuts_cols = [(w[0] + w[1]) / 2 for w in header if w[2] == "Nuts"]
        tables = []  # (item column start, item column end)
        for i, w in enumerate(header):
            if w[2] == "Item":
                nxt = next((v for v in header[i + 1:] if v[2] != "Item"), None)
                tables.append((w[0] - 2, (nxt[0] if nxt else w[1] + 100) - 2))
        for m in marks:
            mx = (m[1] + m[2]) / 2
            if not any(abs(mx - nx) < 9 for nx in nuts_cols):
                continue  # a mark in another allergen's column
            start, end = max((t for t in tables if t[0] <= mx), key=lambda t: t[0])
            row = [c for c in page if abs(c[3] - m[3]) < 2.5 and start <= c[1] < end and "Wingdings" not in c[5]]
            name = " ".join(w[2] for w in _words(row)).strip()
            if name:
                out["contains" if m[4] == "ü" else "facility"].append(name)
    return out


def _dominos_report() -> dict | None:
    resp = web._download(DOMINOS["url"])
    text = web.pdf_to_text(resp.content)
    if _norm(DOMINOS["facility_note"]) not in _norm(text):
        return None  # the chart changed: don't trust old facts
    marks = dominos_nut_marks(resp.content)
    if not marks["pages"]:
        return None
    dishes = []
    for row in marks["contains"]:
        dishes.append({"name": row[:80], "risk": "contains", "nuts": ["unknown"], "evidence": row,
                       "reason": "Domino's allergen chart marks this item in its Nuts column."})
    for row in marks["facility"]:
        dishes.append({"name": row[:80], "risk": "unclear", "nuts": ["peanut", "tree nut"], "evidence": row,
                       "reason": "Domino's allergen chart marks this as made in a facility that handles peanuts "
                                 "and tree nuts."})
    summary = (f"Domino's official US allergen chart marks {len(marks['contains']) or 'no'} item"
               f"{'s' if len(marks['contains']) != 1 else ''} as containing nuts, and "
               f"{len(marks['facility'])} as made in a facility that handles peanuts and tree nuts.")
    return {"dishes": dishes, "statements": [DOMINOS["facility_note"]], "summary": summary,
            "source": {"name": "Domino's Nutrition Guide allergen chart", "url": DOMINOS["url"]}}


def _chipotle_report() -> dict | None:
    text = web.html_to_text(web._download(CHIPOTLE["url"]).text)
    if _norm(CHIPOTLE["quote"]) not in _norm(text):
        return None
    return {"dishes": [], "statements": [CHIPOTLE["quote"]],
            "summary": "Chipotle says it does not use peanuts or tree nuts as ingredients, but cannot guarantee "
                       "their complete absence.",
            "source": {"name": "Chipotle allergen page", "url": CHIPOTLE["url"]}}


READERS = {"dominos.com": _dominos_report, "chipotle.com": _chipotle_report}


def official_report(website: str | None, store_report: dict | None = None) -> dict | None:
    """A full report built from the chain's official allergen information, plain code only.
    Featured items already read from the store page are kept. None if not available or unverified."""
    d = _domain(website)
    if d not in READERS:
        return None
    try:
        official = READERS[d]()
    except web.FetchError:
        return None
    if not official:
        return None
    dishes = [dict(x, verified=True, verifier_notes=[], source="official") for x in official["dishes"]]
    names = {_norm(x["name"]) for x in dishes}
    dishes += [x for x in (store_report or {}).get("dishes", []) if _norm(x["name"]) not in names]
    if not dishes:  # a statement covering the whole menu, with no item list
        dishes = [{"name": "Whole menu (official statement)", "risk": "none_listed", "nuts": [], "verified": True,
                   "source": "official",
                   "evidence": official["statements"][0], "verifier_notes": [],
                   "reason": "The chain states no peanut or tree nut ingredients are used. Cross-contact is possible."}]
    counts = {level: sum(x["risk"] == level for x in dishes) for level in RISK_LEVELS}
    return {
        "restaurant_name": None, "is_menu": True, "dishes": dishes, "counts": counts,
        "kitchen": {"policy": "cross_contact_warning", "statements": official["statements"], "shared_fryer": None,
                    "notes": ""},
        "suspicious_text": [], "unflagged_nut_mentions": [], "rechecked_dishes": 0,
        "summary": official["summary"],
        "sources": [official["source"]["url"]],
        "official_source": {**official["source"], "checked": date.today().isoformat()},
    }
