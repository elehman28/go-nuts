"""The Go Nuts look: calm, premium consumer UI. Warm off-white, serif headlines, hairline cards,
and drawn nut line-icons (no photos)."""
import re
from html import escape
from urllib.parse import quote

# Each nut is drawn around (0, 0) and fits in a 60 x 60 box.
NUTS = {
    "peanut": """<path d='M0 -26 C16 -26 18 -10 9 -3 C18 4 18 26 0 26 C-18 26 -18 4 -9 -3 C-18 -10 -16 -26 0 -26 Z'
          fill='#e9c48f' stroke='#a8743f'/>
    <path d='M-6 -16 l4 2 M3 -12 l4 2 M-6 10 l4 2 M3 14 l4 2' stroke='#a8743f' stroke-width='2'/>""",
    "cashew": """<path d='M-14 -20 C2 -30 22 -14 18 6 C15 22 -2 28 -10 18 C-4 14 4 8 2 -2 C0 -10 -10 -10 -14 -20 Z'
          fill='#f0d7a6' stroke='#b58a4c'/>""",
    "almond": """<path d='M0 -24 C14 -12 14 14 0 24 C-14 14 -14 -12 0 -24 Z' fill='#cf9a68' stroke='#8f5e33'/>
    <path d='M0 -16 C4 -4 4 6 0 16' stroke='#8f5e33' stroke-width='2'/>""",
    "hazelnut": """<circle r='19' cy='4' fill='#b5764a' stroke='#7b4a1e'/>
    <path d='M-19 0 C-10 -14 10 -14 19 0 C10 -6 -10 -6 -19 0 Z' fill='#dcbb8c' stroke='#7b4a1e'/>""",
    "walnut": """<ellipse rx='22' ry='19' fill='#d8b27e' stroke='#9a6a3c'/>
    <path d='M0 -19 C-6 -8 6 4 0 19 M-14 -8 C-6 -4 -10 6 -14 10 M14 -8 C6 -4 10 6 14 10' stroke='#9a6a3c' stroke-width='2'/>""",
    "pistachio": """<ellipse rx='13' ry='20' fill='#ddc993' stroke='#97864e'/>
    <path d='M-6 -10 C-2 -2 -2 6 -6 12' stroke='#7f9a4e' stroke-width='4'/>""",
}

# Palette: nut colors (walnut, almond cream, toasted beige) in a classic cookbook-site layout:
# light pages, cream sections, one accent color, a high-contrast serif and a spaced uppercase sans.
ACCENT = "#7a4b25"      # walnut (wordmark, buttons, active states); white text on it is 7:1 contrast
ACCENT_DARK = "#5e3819" # hover / pressed
INK = "#2b221c"         # body text (dark roast)
CHARCOAL = "#4a3b30"    # headings, dark surfaces
MUTED = "#7d6e62"       # secondary text
CREAM = "#f4ede2"       # almond-cream sections
RULE = "#e2d6c4"        # toasted-beige hairlines
PAGE = "#fffdf9"        # warm ivory page
CARAMEL = "#a8743f"     # toasted caramel: the italic "nuts" and the ornament
WALNUT = "#5a3a22"      # (kept for the nut drawings)

# Risk badges: (text, background). Not the only signal: each badge also has words.
RISK_STYLE = {
    "contains": ("#a3212a", "#fbeeee"),
    "likely": ("#8a5300", "#fcf3e2"),
    "unclear": ("#4a5363", "#eef0f3"),
    "none_listed": ("#1e6b4b", "#eaf4ee"),
}


def _data_uri(svg: str) -> str:
    return "url(\"data:image/svg+xml;utf8," + quote(" ".join(svg.split())) + "\")"


def icon(nut: str, mono: str | None = None) -> str:
    """One nut as an icon. `mono` draws it as a single-color line icon."""
    art = NUTS[nut]
    if mono:
        art = re.sub(r"fill='#[0-9a-f]{6}'", "fill='none'", art)
        art = re.sub(r"stroke='#[0-9a-f]{6}'", f"stroke='{mono}'", art)
    return _data_uri(f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='-30 -30 60 60'>"
                     f"<g fill='none' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'>{art}</g></svg>")


# The app's tabs, in order, and the nut drawn on each.
TABS = ["Find restaurants", "Map", "Check a menu", "Community", "How it works"]
TAB_NUTS = ["peanut", "cashew", "almond", "hazelnut", "walnut"]

_TAB_ICONS = "\n".join(
    f""".stTabs [role="tab"]:nth-of-type({i}) [data-testid="stMarkdownContainer"] p::before {{
  background-image: {icon(nut, mono=MUTED)}; }}
.stTabs [role="tab"]:nth-of-type({i})[aria-selected="true"] [data-testid="stMarkdownContainer"] p::before {{
  background-image: {icon(nut, mono=ACCENT)}; }}""" for i, nut in enumerate(TAB_NUTS, start=1))

# While the app is working, Streamlit's "Running..." figure (top corner) is replaced by a nut that
# cycles through the six drawings, in color, with a gentle wobble.
_RUNNING_NUTS = ["peanut", "almond", "cashew", "hazelnut", "walnut", "pistachio"]
_RUNNING_STEPS = "\n".join(
    f"  {round(100 * i / len(_RUNNING_NUTS), 2)}% {{ background-image: {icon(n)}; }}" for i, n in enumerate(_RUNNING_NUTS))
_RUNNING_ICON = f"""[data-testid="stStatusWidgetRunningManIcon"], [data-testid="stStatusWidgetNewYearsIcon"] {{ display: none !important; }}
[data-testid="stStatusWidgetRunningIcon"] {{
  width: 1.6rem !important; height: 1.6rem !important; background: {icon(_RUNNING_NUTS[0])} center / contain no-repeat;
  animation: gn-nut-cycle 3s steps(1, end) infinite, gn-nut-wobble 0.5s ease-in-out infinite alternate;
}}
@keyframes gn-nut-cycle {{
{_RUNNING_STEPS}
}}
@keyframes gn-nut-wobble {{ from {{ transform: rotate(-14deg); }} to {{ transform: rotate(14deg); }} }}
@media (prefers-reduced-motion: reduce) {{ [data-testid="stStatusWidgetRunningIcon"] {{ animation: gn-nut-cycle 3s steps(1, end) infinite; }} }}"""

# Background: sparse line drawings of nuts in walnut brown, faint as a watermark.
_BG_LAYOUT = [("peanut", 60, 70, -28, 1.1), ("almond", 300, 50, 32, 0.9), ("walnut", 200, 190, 8, 1.0),
              ("cashew", 380, 260, -40, 1.0), ("hazelnut", 70, 330, 0, 0.85), ("pistachio", 270, 370, 24, 0.9)]


def _background_tile() -> str:
    groups = "".join(
        f"<g transform='translate({x} {y}) rotate({r}) scale({sc})'>"
        + re.sub(r"stroke='#[0-9a-f]{6}'", f"stroke='{ACCENT}'", re.sub(r"fill='#[0-9a-f]{6}'", "fill='none'", NUTS[n]))
        + "</g>" for n, x, y, r, sc in _BG_LAYOUT)
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='420' height='420' viewBox='0 0 420 420'>"
            f"<g fill='none' stroke-width='1.4' stroke-linecap='round' stroke-linejoin='round' opacity='0.07'>"
            f"{groups}</g></svg>")


_BG = _data_uri(_background_tile())

# Bundled free fonts (SIL Open Font License, see static/fonts/OFL-*.txt), served by the app itself
# so visitors' browsers never contact a font provider.
_FONT_DIR = "app/static/fonts"
SERIF = '"Old Standard TT", "Iowan Old Style", "Palatino Linotype", Georgia, serif'
SANS = '"Libre Franklin", "Franklin Gothic Book", "Helvetica Neue", Arial, sans-serif'

CSS = f"""
<style>
@font-face {{ font-family: "Old Standard TT"; font-style: normal; font-weight: 400; font-display: swap;
  src: url("{_FONT_DIR}/OldStandardTT-normal-400.woff2") format("woff2"); }}
@font-face {{ font-family: "Old Standard TT"; font-style: italic; font-weight: 400; font-display: swap;
  src: url("{_FONT_DIR}/OldStandardTT-italic-400.woff2") format("woff2"); }}
@font-face {{ font-family: "Old Standard TT"; font-style: normal; font-weight: 700; font-display: swap;
  src: url("{_FONT_DIR}/OldStandardTT-normal-700.woff2") format("woff2"); }}
@font-face {{ font-family: "Libre Franklin"; font-style: normal; font-weight: 100 900; font-display: swap;
  src: url("{_FONT_DIR}/LibreFranklin-variable.woff2") format("woff2"); }}

:root {{ --accent: {ACCENT}; --ink: {INK}; --charcoal: {CHARCOAL}; --muted: {MUTED}; --cream: {CREAM}; --rule: {RULE}; }}
/* Body text only: icon fonts (Material Symbols) must keep their own font-family. */
html, body, .stApp, .stMarkdown p, .stMarkdown li, label, input, textarea {{
  font-family: {SANS}; font-weight: 400; color: var(--ink); -webkit-font-smoothing: antialiased;
}}
[data-testid="stAppViewContainer"] {{ background: {_BG} 0 0 / 420px 420px repeat fixed, {PAGE}; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stAppDeployButton"], [data-testid="stSidebarCollapsedControl"], [data-testid="stSidebar"] {{ display: none; }}
.block-container {{ max-width: 1080px; padding-top: 1.6rem; padding-bottom: 0; }}

h1, h2, h3, h4, h1 *, h2 *, h3 *, h4 * {{ font-family: {SERIF} !important; color: var(--charcoal); font-weight: 400;
  letter-spacing: -0.01em; }}
h3 {{ font-size: 1.65rem; }}
h4 {{ font-size: 1.3rem; }}
a {{ color: var(--accent); }}
[data-testid="stCaptionContainer"], .stCaption {{ color: var(--muted); }}

/* Masthead: centered lowercase wordmark, hairline rules, spaced uppercase strapline */
.gn-top {{ text-align: center; padding: .4rem 0 1.1rem; border-bottom: 1px solid var(--rule); margin-bottom: 2.4rem; }}
.gn-brand {{ font: 400 clamp(2.6rem, 6vw, 3.6rem)/1 {SERIF}; color: var(--accent); letter-spacing: -1px;
  text-transform: lowercase; }}
.gn-mark {{ display: none; }}
.gn-brand .gn-go {{ font-style: normal; }}
.gn-brand .gn-nuts {{ font-style: italic; color: {CARAMEL}; font-size: 1.12em; margin-left: .06em;
  letter-spacing: -0.5px; }}
.gn-ornament {{ display: flex; align-items: center; justify-content: center; gap: .9rem; margin: 0 auto .7rem; }}
.gn-ornament::before, .gn-ornament::after {{ content: ""; width: 54px; height: 1px; background: {CARAMEL}; opacity: .55; }}
.gn-ornament span {{ width: 38px; height: 38px; border-radius: 10px;
  background: {WALNUT} {icon('peanut', mono='#ffffff')} center / 26px no-repeat;
  box-shadow: 0 1px 0 rgba(255,255,255,.25) inset, 0 2px 6px rgba(90,58,34,.18); }}
.gn-footer .gn-ornament {{ margin-bottom: .4rem; }}
.gn-footer .gn-ornament span {{ width: 28px; height: 28px; border-radius: 8px; background-size: 19px; }}
.gn-footer .gn-ornament::before, .gn-footer .gn-ornament::after {{ width: 34px; }}
.gn-meta {{ margin-top: .7rem; font: 500 .72rem/1.4 {SANS}; letter-spacing: 2px; text-transform: uppercase; color: var(--muted); }}
.gn-headline {{ font: italic 400 clamp(1.7rem, 3.6vw, 2.5rem)/1.25 {SERIF} !important; color: var(--charcoal) !important;
  text-align: center; max-width: 30ch; margin: 0 auto .9rem !important; padding: 0 !important; letter-spacing: 0; }}
.gn-headline em {{ font-style: italic; color: var(--accent) !important; }}
.gn-sub {{ text-align: center; color: var(--muted) !important; font-size: 1rem; line-height: 1.65; max-width: 58ch;
  margin: 0 auto 2rem !important; display: block; }}

/* Profile line */
.gn-profile {{ display: flex; flex-wrap: wrap; align-items: center; gap: .45rem; color: var(--muted); font-size: .9rem; }}
.gn-profile b {{ font: 600 .72rem {SANS}; letter-spacing: 2px; text-transform: uppercase; color: var(--charcoal);
  margin-right: .3rem; }}
.gn-pill {{ display: inline-block; padding: .2rem .7rem; border-radius: 2px; background: var(--cream);
  color: var(--charcoal); font-size: .85rem; }}

/* Navigation tabs: centered, spaced uppercase, a thin blue rule under the current one */
.stTabs [data-baseweb="tab-list"] {{ gap: 1.6rem; justify-content: center; border-bottom: 1px solid var(--rule);
  width: 100%; overflow-x: auto; margin-top: .8rem; }}
.stTabs [data-baseweb="tab"], .stTabs [role="tab"] {{ height: 2.9rem; padding: 0 .1rem; background: transparent !important;
  border-radius: 0 !important; white-space: nowrap; border-bottom: 2px solid transparent; }}
.stTabs [role="tab"] p {{ font: 500 .76rem {SANS} !important; letter-spacing: 2px; text-transform: uppercase;
  color: var(--charcoal); }}
.stTabs [aria-selected="true"] {{ border-bottom-color: var(--accent) !important; }}
.stTabs [aria-selected="true"] p {{ color: var(--accent) !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}
.stTabs [role="tab"] [data-testid="stMarkdownContainer"] p::before {{
  content: ""; display: inline-block; width: 1.15em; height: 1.15em; margin-right: .5em;
  vertical-align: -0.28em; background-size: contain; background-repeat: no-repeat; }}
{_TAB_ICONS}
{_RUNNING_ICON}
/* Food Guide chat: a floating button at the bottom right of every page; its panel opens above it. */
.st-key-gn_chat_fab {{ position: fixed; right: 24px; bottom: 22px; z-index: 999; width: auto !important; }}
.st-key-gn_chat_fab [data-testid="stPopover"] button {{
  background: var(--accent); color: #fff; border: none; border-radius: 999px; padding: 0.7rem 1.25rem;
  box-shadow: 0 6px 22px rgba(43,34,28,.28); letter-spacing: 1.5px; }}
.st-key-gn_chat_fab [data-testid="stPopover"] button:hover {{ background: {ACCENT_DARK}; color: #fff; }}
.st-key-gn_chat_fab [data-testid="stPopover"] button p {{ color: #fff; }}
/* column-reverse keeps the panel scrolled to the newest message and the question box, like a chat app */
[data-testid="stPopoverBody"]:has(.st-key-gn_chat_body) {{ width: min(420px, 92vw); max-height: 72vh; overflow-y: auto;
  display: flex; flex-direction: column-reverse; }}
@media (max-width: 640px) {{ .st-key-gn_chat_fab {{ right: 12px; bottom: 12px; }} }}
.stTabs [data-baseweb="tab-panel"] {{ padding-top: 2rem; }}

/* Buttons: crisp, square-ish, spaced uppercase */
.stButton button, .stFormSubmitButton button, .stDownloadButton button, .stLinkButton > a, [data-testid="stPopover"] button {{
  border-radius: 2px; padding: .6rem 1.3rem; border: 1px solid var(--charcoal); background: #fff; color: var(--charcoal);
  transition: background .15s ease, color .15s ease; }}
.stButton button p, .stFormSubmitButton button p, .stDownloadButton button p, .stLinkButton > a p, [data-testid="stPopover"] button p {{
  font: 500 .74rem {SANS} !important; letter-spacing: 2px; text-transform: uppercase; white-space: nowrap; }}
[data-testid="stPopover"] button {{ padding: .55rem .8rem; }}
[data-testid="stPopover"] button p {{ letter-spacing: 1.2px; }}
.stButton button:hover, .stFormSubmitButton button:hover, [data-testid="stPopover"] button:hover {{
  background: var(--charcoal); color: #fff; }}
.stButton button:hover p, .stFormSubmitButton button:hover p, [data-testid="stPopover"] button:hover p {{ color: #fff !important; }}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"], .stDownloadButton button[kind="primary"] {{
  background: var(--accent); border-color: var(--accent); color: #fff; }}
.stButton button[kind="primary"]:hover, .stFormSubmitButton button[kind="primary"]:hover {{ background: {ACCENT_DARK};
  border-color: {ACCENT_DARK}; }}
.stButton button[kind="primary"] p, .stFormSubmitButton button[kind="primary"] p, .stDownloadButton button[kind="primary"] p {{ color: #fff !important; }}
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {{
  border-radius: 2px !important; background: #fff !important; border: 1px solid var(--rule) !important; }}
[data-testid="stFileUploaderDropzone"] {{ border-radius: 2px; background: var(--cream); border: 1px dashed var(--rule); }}

/* Surfaces: hairlines, no shadows */
[data-testid="stExpander"] {{ background: #fff; border: 1px solid var(--rule); border-radius: 2px; box-shadow: none; }}
[data-testid="stExpander"] summary p {{ font-family: {SERIF} !important; font-size: 1.05rem; color: var(--charcoal); }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 2px; border-color: var(--rule) !important; background: #fff; }}
[data-testid="stAlert"] {{ border-radius: 2px; }}
[data-testid="stMetric"] {{ background: var(--cream); border: 0; border-radius: 2px; padding: .9rem 1rem; }}
[data-testid="stMetricLabel"] p {{ font: 500 .7rem {SANS} !important; letter-spacing: 2px; text-transform: uppercase; }}
[data-testid="stDataFrame"], [data-testid="stDeckGlJsonChart"] {{ border-radius: 2px; overflow: hidden; border: 1px solid var(--rule); }}
[data-testid="stPopoverBody"] {{ border-radius: 2px; }}

/* Small labels */
.gn-tag {{ display: inline-block; font: 600 .64rem {SANS}; letter-spacing: 1.5px; text-transform: uppercase;
  color: var(--charcoal); background: var(--cream); border-radius: 2px; padding: .16rem .45rem; margin-right: .45rem;
  vertical-align: .1rem; }}
.gn-note {{ color: var(--muted); font-size: .88rem; line-height: 1.55; margin: .25rem 0 .55rem; }}
.gn-badge {{ display: inline-block; border-radius: 2px; padding: .16rem .55rem; font: 600 .7rem {SANS}; letter-spacing: 1px;
  text-transform: uppercase; white-space: nowrap; }}

/* Restaurant contact card */
.gn-contact {{ display: flex; flex-wrap: wrap; align-items: center; gap: .55rem .6rem; padding: .9rem 1rem;
  margin: .3rem 0 1.1rem; border-radius: 2px; background: var(--cream); }}
.gn-contact .gn-addr {{ color: var(--charcoal); font-size: .92rem; margin-right: auto; }}
.gn-btn {{ display: inline-flex; align-items: center; padding: .45rem .95rem; border-radius: 2px;
  font: 500 .7rem {SANS}; letter-spacing: 1.6px; text-transform: uppercase; text-decoration: none !important;
  border: 1px solid var(--charcoal); color: var(--charcoal) !important; background: #fff; }}
.gn-btn:hover {{ background: var(--charcoal); color: #fff !important; }}
.gn-btn.gn-call {{ background: var(--accent); color: #fff !important; border-color: var(--accent); }}
.gn-btn.gn-call:hover {{ background: {ACCENT_DARK}; }}
.gn-muted {{ color: var(--muted); font-size: .86rem; }}

/* Score row */
.gn-scores {{ display: flex; flex-wrap: wrap; gap: .55rem; margin: .7rem 0 1rem; }}
.gn-score, .gn-count {{ background: #fff; border: 1px solid var(--rule); border-radius: 2px;
  padding: .7rem .95rem; display: flex; flex-direction: column; gap: .4rem; min-width: 7.5rem; }}
.gn-score {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.gn-score span {{ font: 500 .64rem {SANS}; letter-spacing: 2px; text-transform: uppercase; opacity: .9; }}
.gn-score b {{ font: 400 1.9rem/1 {SERIF}; }}
.gn-score small {{ font-size: .8rem; opacity: .8; margin-left: .15rem; }}
.gn-count b {{ font: 400 1.55rem/1 {SERIF}; color: var(--charcoal); }}

/* Map legend */
.gn-legend {{ display: flex; flex-wrap: wrap; gap: .5rem 1.2rem; margin: .8rem 0 1.1rem; font-size: .84rem; color: var(--muted); }}
.gn-dot {{ display: inline-flex; align-items: center; justify-content: center; width: 1.05rem; height: 1.05rem;
  border-radius: 50%; margin-right: .4rem; color: #fff; font: 700 .68rem/1 {SANS}; vertical-align: -.2rem; }}

/* The hidden box the Near me button types its location into, and invisible helper frames */
div[data-testid="stTextInput"]:has(input[aria-label="gn-near-coords"]) {{ display: none; }}
div[data-testid="stElementContainer"]:has(iframe[srcdoc*="parent.document.cookie"]) {{ display: none; }}

/* Allergy chef card: large, calm and easy to read across a counter */
.gn-chefcard {{ border: 2px solid {ACCENT}; border-radius: 4px; background: #fff; padding: 1.4rem 1.6rem; margin: .4rem 0 1rem; }}
.gn-chefcard-title {{ font: 400 1.7rem/1.1 {SERIF}; color: {ACCENT}; margin-bottom: .7rem; }}
.gn-chefcard p {{ font-size: 1.12rem; line-height: 1.55; margin: .5rem 0; color: var(--ink); }}
.gn-chefcard[dir="rtl"] {{ text-align: right; }}
.gn-chefcard[lang="zh"] p, .gn-chefcard[lang="ar"] p {{ font-size: 1.2rem; line-height: 1.8; }}

/* Footer: a cream band */
.gn-footer {{ margin: 4rem -1rem 0; padding: 2rem 1.5rem 2.4rem; background: var(--cream); text-align: center;
  color: var(--muted); font-size: .84rem; line-height: 1.65; }}
.gn-footer .gn-brand {{ font-size: 1.6rem; margin-bottom: .6rem; }}

/* Phones */
@media (max-width: 640px) {{
  .block-container {{ padding-top: 1rem; }}
  .gn-top {{ margin-bottom: 1.6rem; }}
  .gn-stats {{ display: none; }}
  .gn-sub {{ font-size: .95rem; margin-bottom: 1.3rem; }}
  .stTabs [data-baseweb="tab-list"] {{ justify-content: flex-start; gap: 1.1rem; }}
}}
</style>
"""


def header(n_checked: int, n_places: int) -> str:
    """Top of the page. Numbers are counted from the database, never estimated."""
    return (f"<div class='gn-top'><div class='gn-ornament'><span></span></div><div class='gn-brand'><span class='gn-go'>go</span> <span class='gn-nuts'>nuts</span></div>"
            f"<div class='gn-meta'>Nut-allergy dining · New Haven<span class='gn-stats'> · {n_checked} menus "
            f"checked · {n_places} restaurants mapped</span></div></div>"
            "<h1 class='gn-headline'>Eat out with a nut allergy, <em>without the guesswork.</em></h1>"
            "<p class='gn-sub'>Every dish is rated from the restaurant's real menu, with the quote to show for it. "
            "Go Nuts never calls food “safe”, so always confirm with staff.</p>")


def profile_bar(allergens: list[str], severity: str) -> str:
    pills = "".join(f"<span class='gn-pill'>{escape(a)}</span>" for a in allergens) or \
        "<span class='gn-pill'>No allergens chosen</span>"
    sev = f" · {escape(severity.split(' (')[0])}" if severity and severity != "Prefer not to say" else ""
    return f"<div class='gn-profile'><b>Your profile</b>{pills}<span>{sev}</span></div>"


def tag(text: str) -> str:
    return f"<span class='gn-tag'>{escape(text)}</span>"


def note(label: str, text: str) -> str:
    """A small labeled line, e.g. note('AI-written', 'Summary based only on the menu text below.')."""
    return f"<div class='gn-note'>{tag(label)}{escape(text)}</div>"


def badge(risk: str, label: str) -> str:
    fg, bg = RISK_STYLE[risk]
    return f"<span class='gn-badge' style='color:{fg};background:{bg}'>{escape(label)}</span>"


def tip(text: str) -> str:
    return f"<div class='gn-note'>{escape(text)}</div>"


def safe_url(url: str | None, schemes=("http://", "https://")) -> str | None:
    """Only web (or tel:) links: OpenStreetMap data is public and editable, so a javascript: link
    in a website field must never become a clickable link."""
    url = (url or "").strip()
    return url if url.lower().startswith(schemes) else None


def contact_card(r: dict, tel: str | None, directions: str | None, guide: str | None = None) -> str:
    """Address, call, directions, website (and a chain's official allergen guide) for one restaurant.
    Missing details say so."""
    tel, directions, website = safe_url(tel, ("tel:",)), safe_url(directions), safe_url(r.get("website"))
    guide = safe_url(guide)
    addr = escape(r.get("address") or "No street address listed")
    if r.get("address") and r.get("address_source") == "map":
        addr += " <span class='gn-muted'>(approximate, from the map location)</span>"
    parts = [f"<span class='gn-addr'>{addr}</span>"]
    if tel:
        parts.append(f"<a class='gn-btn gn-call' href='{escape(tel)}'>Call to ask · {escape(r['phone'])}</a>")
    else:
        parts.append("<span class='gn-muted'>No phone listed</span>")
    if directions:
        parts.append(f"<a class='gn-btn' href='{escape(directions)}' target='_blank'>Directions</a>")
    if website:
        parts.append(f"<a class='gn-btn' href='{escape(website)}' target='_blank' rel='noopener'>Website</a>")
    if guide:
        parts.append(f"<a class='gn-btn' href='{escape(guide)}' target='_blank' rel='noopener'>Official allergen guide</a>")
    return "<div class='gn-contact'>" + "".join(parts) + "</div>"


def score_row(score: int, counts: list[tuple[str, int]]) -> str:
    """Score plus one card per risk level; wraps on narrow screens instead of overlapping.
    `counts` holds (badge HTML, number) pairs; the badges are built from fixed labels."""
    pills = "".join(f"<div class='gn-count'>{b}<b>{n}</b></div>" for b, n in counts)
    return (f"<div class='gn-scores'><div class='gn-score' title='For sorting only. Never means safe.'>"
            f"<span>Go Nuts score</span><b>{int(score)}<small>/100</small></b></div>{pills}</div>")


def legend(labels: dict, colors: dict, symbols: dict) -> str:
    return "<div class='gn-legend'>" + "".join(
        f"<span><span class='gn-dot' style='background:rgb{colors[k]}'>{escape(symbols[k])}</span>{escape(v)}</span>"
        for k, v in labels.items()) + "</div>"


def footer() -> str:
    return ("<div class='gn-footer'><div class='gn-ornament'><span></span></div><div class='gn-brand'><span class='gn-go'>go</span> <span class='gn-nuts'>nuts"
            "</span></div>Go Nuts reads menus. It can't see the kitchen, and menus leave out "
            "ingredients and cross-contact. Always tell your server about your allergy and carry your "
            "epinephrine. Ratings are AI-assisted and checked against the menu text; they are never a "
            "guarantee.</div>")
