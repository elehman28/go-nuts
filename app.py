"""Go Nuts: a team of AI agents that finds nut-allergy-friendly restaurants and dishes.

Run with:  streamlit run app.py
"""
import base64
import io
import traceback
import uuid
from html import escape
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st
from PIL import Image

from gonuts import browser, chains, chefcard, config, places, theme
from gonuts.agents import build_team
from gonuts.db import DB, restaurant_key
from gonuts.llm import BudgetExceeded, MissingKey, ModelError, UsageTracker
from gonuts.nuts import RISK_LEVELS
from gonuts.osm import PlacesError
from gonuts.team import DelegationError
from gonuts.web import FetchError, truncate

st.set_page_config(page_title="Go Nuts · Eat out with a nut allergy", page_icon="🥜", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown(theme.CSS, unsafe_allow_html=True)

ALLERGENS = ["Peanuts", "All tree nuts", "Almonds", "Cashews", "Walnuts", "Pecans", "Pistachios",
             "Hazelnuts", "Macadamias", "Brazil nuts", "Pine nuts", "Coconut"]
SEVERITIES = ["Severe (anaphylaxis, carry epinephrine)", "Moderate", "Mild", "Prefer not to say"]
KITCHEN_LABEL = {
    "accommodates": "The menu says the kitchen can accommodate allergies.",
    "cross_contact_warning": "The menu warns that nuts are used in the kitchen.",
    "no_info": "The menu says nothing about allergies.",
}
RISK_HELP = {
    "contains": "A nut, peanut, nut butter, oil, flour or milk is named in the dish.",
    "likely": "No nut is named, but dishes like this usually contain nuts (pesto, mole, satay, baklava…).",
    "unclear": "Not enough information: sauces, dressings, desserts, or nuts outside your profile "
               "that could mean cross-contact.",
    "none_listed": "No nut ingredient is listed and dishes like this rarely contain nuts. "
                   "This is not a promise. Always ask staff.",
}
# Plain-English progress for each hand-off between agents.
STEP_TEXT = {
    ("finder", "find_restaurants"): "Finding restaurants on the map",
    ("cost_control", "get_report"): "Checking results we've already saved",
    ("cost_control", "get_menu_report"): "Checking results we've already saved",
    ("fetcher", "fetch_menu"): "Reading the restaurant's website",
    ("fetcher", "read_menu_photo"): "Reading the menu photo",
    ("fetcher", "screen_photo"): "Checking the photo shows no people",
    ("verifier", "screen_text"): "Removing any hidden instructions to the AI",
    ("analyst", "analyze_menu"): "Rating every dish for nuts (big menus take up to a minute)",
    ("verifier", "verify_analysis"): "Checking every quote against the real menu",
    ("analyst", "recheck_dishes"): "Re-checking dishes the Verifier sent back",
    ("summarizer", "rank_restaurants"): "Ranking restaurants for your profile",
    ("summarizer", "check_menu"): "Starting the menu check",
    ("guide", "answer_question"): "Looking that up",
    ("summarizer", "cached_entry"): "Reading that restaurant's checked menu",
    ("verifier", "check_answer"): "Checking the answer against the menu",
}
ASK_EXAMPLES = ["I just ate pad thai. Are there usually nuts in it?",  # shown in the chat box, one at a time
                "What could I order at September in Bangkok?",
                "Is pesto usually made with nuts?",
                "Is there usually peanut in satay sauce?"]
SAMPLE_DIR = Path(__file__).parent / "sample_menus"


@st.cache_resource
def get_db() -> DB:
    return DB(config.DB_PATH, seed=config.SEED_DB_PATH)


db = get_db()
if "team" not in st.session_state:
    st.session_state.team = build_team(UsageTracker(), db)
team = st.session_state.team
tracker: UsageTracker = team.llm.tracker
ss = st.session_state


def run(sender_to: str, task: str, payload: dict, progress: str | None = None):
    """Start a new run on the team, show live progress, keep its trace, and show friendly errors."""
    team.start_run()
    slot = st.empty()
    status = slot.status(progress, expanded=True) if progress else None
    shown = []

    def on_step(step):
        text = STEP_TEXT.get((step["to"], step["task"]))
        if status and text and (not shown or shown[-1] != text):
            shown.append(text)
            status.update(label=text + "…")
            status.markdown(f"<div class='gn-note'>{escape(text)}</div>", unsafe_allow_html=True)

    team.on_step = on_step
    try:
        result = team.send("user", sender_to, task, payload)
        slot.empty()  # finished: the results speak for themselves
        return result
    except (MissingKey, BudgetExceeded, FetchError, PlacesError, DelegationError, ModelError) as e:
        if status:
            slot.empty()
        st.error(str(e))
    except Exception:  # keep the app up; full details go to the server log, not the page
        traceback.print_exc()
        if status:
            slot.empty()
        st.error("Something went wrong on our side. Please try again. If it keeps happening, try a different menu.")
    finally:
        team.on_step = None
        ss.last_trace = list(team.trace)
    return None


# ---------------------------------------------------------------- allergy profile (kept on this device only)

if "profile" not in ss:
    saved = browser.load_profile()
    ss.profile = saved or {"allergens": ["Peanuts", "All tree nuts"], "severity": SEVERITIES[0]}
    ss.profile_ready = bool(saved)
    ss.remember = bool(saved)
if "saved" not in ss:
    ss.saved = browser.load_list()  # restaurants on "Your list" (kept on this device only)
profile = ss.profile
# Keep the device cookie in step with the "Remember" choice on every run (saving the same value
# twice is harmless, and a one-off write can be lost if the page redraws first).
if ss.remember:
    browser.save_profile(profile)
    browser.save_list(ss.saved)
elif ss.pop("forget_cookie", False) or browser.load_profile() or browser.load_list():
    browser.forget_profile()
    browser.forget_list()


def toggle_saved(key: str):
    if key in ss.saved:
        ss.saved.remove(key)
    elif len(ss.saved) < browser.MAX_SAVED:
        ss.saved.insert(0, key)


def save_button(key: str, ctx: str):
    saved = key in ss.saved
    full = not saved and len(ss.saved) >= browser.MAX_SAVED
    st.button("★ Saved" if saved else "☆ Save", key=f"fav_{ctx}_{key}", on_click=toggle_saved, args=(key,),
              disabled=full, help=f"Your list is full ({browser.MAX_SAVED})." if full else
              "Remove from Your list" if saved else "Add to Your list")


@st.dialog("Your allergy chef card", width="large")
def chef_card_dialog():
    st.caption("Show this to your server or chef, or download it to print. It's a request to staff, not a "
               "guarantee. It never includes your name.")
    names = {name: code for code, (name, _) in chefcard.LANGUAGES.items()}
    picked = st.segmented_control("Language", list(names), default="English", label_visibility="collapsed")
    lang = names.get(picked or "English", "en")
    st.markdown(chefcard.card_html(profile, lang), unsafe_allow_html=True)
    if lang != "en":
        st.markdown(theme.note("Translation", "Written carefully, but not by a native speaker. If you can, ask a "
                               "fluent speaker to check it before you rely on it."), unsafe_allow_html=True)
    label = "Download to print" + (f" (English + {picked})" if lang != "en" else "")
    st.download_button(label, chefcard.printable_html(profile, lang), file_name=f"food-allergy-card-{lang}.html",
                       mime="text/html", type="primary", width="stretch")
    st.markdown(theme.note("Made from your profile", "Change your allergens in Edit profile and the card updates."),
                unsafe_allow_html=True)


def open_restaurant(key: str):
    ss.search_pick = key


def profile_form(prefix: str) -> tuple[list[str], str, bool]:
    allergens = st.multiselect("I'm allergic to", ALLERGENS, default=[a for a in profile["allergens"] if a in ALLERGENS],
                               key=f"{prefix}_allergens")
    sev = profile["severity"] if profile["severity"] in SEVERITIES else SEVERITIES[0]
    severity = st.selectbox("How severe?", SEVERITIES, index=SEVERITIES.index(sev), key=f"{prefix}_severity")
    remember = st.checkbox("Remember on this device", value=ss.remember, key=f"{prefix}_remember",
                           help="Saved only in this browser, never on our server or in the page address. "
                                "Untick to forget it.")
    return allergens, severity, remember


def save_profile_choice(allergens, severity, remember):
    ss.profile = {"allergens": allergens, "severity": severity}
    ss.profile_ready = True
    if ss.remember and not remember:
        ss.forget_cookie = True
    ss.remember = remember
    st.rerun()


# ---------------------------------------------------------------- display helpers

def link(url: str | None) -> str:
    """A table link cell: blank (not "None") when there's nothing to link to."""
    return url or ""


def badge(risk: str) -> str:
    return theme.badge(risk, RISK_LEVELS[risk])


def show_entry(entry: dict, ctx: str, expanded_dishes: bool = True):
    """One restaurant: contact, verdict, counts, kitchen, server questions, community, dish list.
    `ctx` keeps widget keys unique when the same restaurant appears in two places."""
    rep, r = entry["report"], entry["restaurant"]
    key = r.get("key") or restaurant_key(r["name"])
    stored = db.restaurant(key) or {}
    if stored:  # real restaurants only (not pasted or sample menus)
        save_button(key, ctx)
    contact = {**stored, **{k: v for k, v in r.items() if v not in (None, "")}}
    if contact.get("address") or contact.get("phone") or contact.get("lat") is not None or contact.get("website"):
        st.markdown(theme.contact_card(contact, places.tel_link(contact.get("phone")),
                                       places.directions_link(contact),
                                       chains.guide_url(contact.get("website"))), unsafe_allow_html=True)
    if any("from a diner" in s for s in rep.get("sources") or []):
        st.info("This menu was read from a diner's photo, not the restaurant's website. Menus change, "
                "so ask staff about anything you plan to order.")
    partial = places.partial_reason(contact, rep)
    if partial:
        st.warning(f"**Partial menu.** {partial}")
    if rep.get("injection_lines_removed") or rep.get("suspicious_text"):
        lines = rep.get("injection_lines_removed", []) + rep.get("suspicious_text", [])
        st.error("**Blocked:** this menu contained text that tried to give instructions to the AI. "
                 "It was removed before analysis:\n\n" + "\n".join(f"- `{l[:150]}`" for l in lines))
    official = rep.get("official_source")
    summary = entry.get("verdict") or rep.get("summary")
    if summary:
        label = (theme.note("Official data", f"From the {official['name']}, checked {official.get('checked', '')}.")
                 if official and not entry.get("verdict") else
                 theme.note("AI-written", "Summary based only on the menu text below."))
        st.markdown(f"<p style='font-size:1.05rem;line-height:1.55;margin:.2rem 0 .1rem'>{escape(summary)}</p>" + label,
                    unsafe_allow_html=True)

    counts = rep.get("profile_counts") or rep["counts"]
    st.markdown(theme.score_row(entry["score"], [(badge(level), counts[level]) for level in RISK_LEVELS]),
                unsafe_allow_html=True)
    with st.popover("What do these labels mean?"):
        st.markdown("**The Go Nuts score** (0–100) is for sorting only: the share of dishes with no nuts listed, "
                    "adjusted for the kitchen's allergy statements and community reviews. It never means safe.")
        for level in RISK_LEVELS:
            st.markdown(f"{badge(level)} &nbsp;{escape(RISK_HELP[level])}", unsafe_allow_html=True)

    kitchen = rep.get("kitchen") or {}
    k_text = KITCHEN_LABEL.get(kitchen.get("policy"), KITCHEN_LABEL["no_info"])
    if kitchen.get("shared_fryer"):
        k_text += " A shared fryer or peanut oil is mentioned."
    if official:
        k_text = k_text.replace("The menu", "The chain's allergen information")
    said = f"{official['name'].split(' ')[0]} says" if official else "Menu says"
    st.markdown(theme.note("Kitchen", k_text) + "".join(
        f"<div class='gn-note'>{escape(said)}: “{escape(s)}”</div>" for s in kitchen.get("statements", [])),
        unsafe_allow_html=True)

    if entry.get("accommodation") is not None:
        st.markdown(theme.note("Community", f"Allergy accommodation {entry['accommodation']}/5 from "
                               f"{entry['n_reviews']} review{'s' if entry['n_reviews'] != 1 else ''}."),
                    unsafe_allow_html=True)

    if entry.get("questions"):
        with st.container(border=True):
            st.markdown("**Ask your server**")
            for q in entry["questions"]:
                st.markdown(f"- {escape(q)}")
            st.markdown(theme.note("AI-written", "Questions drafted from this menu."), unsafe_allow_html=True)

    with st.expander(f"Dish by dish ({len(rep['dishes'])})", expanded=expanded_dishes):
        only = st.toggle("Only show dishes with no nuts listed", key=f"only_{ctx}_{key}",
                         help="Dishes where no nut ingredient is listed. Still ask staff before ordering.")
        dishes = [d for d in rep["dishes"] if not only or (d["risk"] == "none_listed" and d.get("relevant", True))]
        if only and not dishes:
            st.caption("No dishes on this menu have no nuts listed for your profile.")
        for d in dishes:
            nuts = f" · {escape(', '.join(d['nuts']))}" if d.get("nuts") else ""
            other = "" if d.get("relevant", True) else " · <i>not in your profile; ask about cross-contact</i>"
            lines = [f"<div style='margin:.9rem 0 .15rem'><b>{escape(d['name'])}</b> &nbsp;{badge(d['risk'])}"
                     f"<span class='gn-muted'>{nuts}{other}</span></div>"]
            if d.get("evidence"):
                lines.append(f"<div class='gn-note' style='color:#3d342e'>Menu says: “{escape(d['evidence'])}”</div>")
            if d.get("risk") in ("likely", "unclear") and "unknown" in (d.get("nuts") or ["unknown"]):
                lines.append(theme.note("AI inference", "The menu doesn't name a nut here; this rating is the AI's judgment."))
            if d.get("reason"):
                lines.append(theme.note("Official" if d.get("source") == "official" else "AI", d["reason"]))
            for n in d.get("verifier_notes", []):
                lines.append(theme.note("Verifier", n))
            st.markdown("".join(lines), unsafe_allow_html=True)
        if rep.get("unflagged_nut_mentions") and not only:
            st.warning("**Other nut mentions on this menu the AI did not flag:**\n\n" +
                       "\n".join(f"- {escape(l)}" for l in rep["unflagged_nut_mentions"]))

    reviews = db.reviews(key, limit=3)
    if reviews:
        with st.expander(f"Community reviews ({len(reviews)})"):
            for rv in reviews:
                show_review(rv)

    cost = "saved result, 0 tokens" if rep.get("from_cache") else f"{rep.get('cost_tokens', 0):,} tokens"
    st.caption(f"Read from: {', '.join(rep.get('sources') or []) or 'saved result'} · {cost}")


def show_review(rv: dict):
    stars = "★" * int(rv["accommodation"]) + "☆" * (5 - int(rv["accommodation"])) if rv.get("accommodation") else ""
    head = f"**{escape(rv['restaurant_name'])}** &nbsp;<span style='color:#b5652b'>{stars}</span>"
    if rv.get("dish"):
        head += f" · {escape(rv['dish'])}"
    st.markdown(head, unsafe_allow_html=True)
    if rv.get("photo") and Path(rv["photo"]).is_file():
        st.image(rv["photo"], width=260)
    if rv.get("text"):
        st.markdown(escape(rv["text"]))
    st.caption(f"{rv.get('nickname') or 'Anonymous'} · {rv['created'][:10]}")


def save_photo(upload) -> str | None | bool:
    """Check it's a real image with no people or personal info, shrink it, and re-save as JPEG
    (drops location data in the file). Returns the path, None if no photo, False if rejected."""
    if upload is None:
        return None
    data = upload.getvalue()
    if len(data) > config.MAX_PHOTO_BYTES:
        st.error("That photo is too large (5 MB max).")
        return False
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        st.error("That file isn't a photo we can read.")
        return False
    img.thumbnail((1200, 1200))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)  # re-saving drops EXIF metadata such as GPS location
    small = img.copy()
    small.thumbnail((768, 768))  # a smaller copy is enough for the check and costs fewer tokens
    sbuf = io.BytesIO()
    small.save(sbuf, "JPEG", quality=80)
    check = run("fetcher", "screen_photo", {"image_b64": base64.b64encode(sbuf.getvalue()).decode(),
                                            "mime": "image/jpeg"})
    if not check or not check.get("ok"):  # fail closed: if the check didn't run, don't save
        st.error((check or {}).get("reason") or "We couldn't check this photo, so it wasn't saved.")
        return False
    config.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    path = config.PHOTO_DIR / f"{uuid.uuid4().hex}.jpg"
    path.write_bytes(buf.getvalue())
    return str(path)


def menu_photo(upload) -> dict | None:
    """A menu page photo, shrunk (text stays readable, fewer tokens) and re-saved without EXIF.
    Only sent to the model, never stored."""
    data = upload.getvalue()
    if len(data) > config.MAX_PHOTO_BYTES:
        st.error(f"{upload.name} is too large (5 MB max).")
        return None
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        st.error(f"{upload.name} isn't a photo we can read.")
        return None
    img.thumbnail((2000, 2000))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return {"image_b64": base64.b64encode(buf.getvalue()).decode(), "mime": "image/jpeg"}


def show_restaurant(p: dict, ctx: str):
    """One restaurant from search or the map: full results if checked (free), else 'Add this menu'."""
    with st.container(border=True):
        st.markdown(f"### {escape(p['name'])}")
        if p.get("cuisine"):
            st.caption(p["cuisine"].capitalize())
        added = ss.get("added_menu")
        if added and added["restaurant"].get("key") == p["key"]:
            if ss.get("added_from") == "photo":
                st.success("Thanks! This menu is saved, so everyone now sees it on the map and in Browse.")
            show_entry(added, ctx=f"{ctx}_added", expanded_dishes=True)
            return
        if p["score"] is not None:
            entry = team.agents["summarizer"].cached_entry(p["key"], profile)
            if entry:
                show_entry(entry, ctx=ctx, expanded_dishes=False)
                return
        save_button(p["key"], ctx)
        st.markdown(theme.contact_card(p, places.tel_link(p["phone"]), places.directions_link(p),
                                       chains.guide_url(p.get("website"))),
                    unsafe_allow_html=True)
        website = theme.safe_url(p.get("website") or p.get("menu_url"))
        if website:
            st.markdown("**This menu hasn't been checked yet.** Go Nuts can read it from the restaurant's website "
                        "now (usually 20–60 seconds).")
            if st.button("Check this menu", type="primary", key=f"check_site_{ctx}_{p['key']}"):
                row = db.restaurant(p["key"]) or {"name": p["name"], "key": p["key"], "website": website}
                out = run("summarizer", "rank_restaurants", {"restaurants": [row], "profile": profile},
                          progress=f"Checking {p['name']}")
                if out and out.get("ranked"):
                    ss.added_menu, ss.added_from = out["ranked"][0], "website"
                    st.rerun()
                for err in (out or {}).get("errors", []):
                    st.warning(places.failure_message(err["error"], err.get("website")))
            st.markdown("<div class='gn-note'>Or, if you're there:</div>", unsafe_allow_html=True)
        st.markdown("**Add this menu.** No menu has been checked here yet. At the restaurant, or have a takeout "
                    "menu? Add a photo of each page. Go Nuts reads it, and everyone sees the results.")
        uploads = st.file_uploader(f"Menu photos (up to {config.MAX_MENU_PHOTOS} pages)",
                                   type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True,
                                   key=f"menu_photos_{ctx}_{p['key']}")
        st.markdown(theme.note("Privacy", "Photograph only the menu, with no people in the shot. Photos are read "
                               "by the AI and then thrown away: never stored or shown to anyone."),
                    unsafe_allow_html=True)
        if uploads and len(uploads) > config.MAX_MENU_PHOTOS:
            st.warning(f"Only the first {config.MAX_MENU_PHOTOS} photos will be read.")
        if st.button("Check and save this menu", type="primary", disabled=not uploads, key=f"add_menu_{ctx}_{p['key']}"):
            images = [img for img in (menu_photo(u) for u in uploads[: config.MAX_MENU_PHOTOS]) if img]
            if images:
                entry = run("summarizer", "check_menu", {"profile": profile, "name": p["name"], "images": images},
                            progress=f"Reading {len(images)} menu page{'s' if len(images) != 1 else ''}")
                if entry and entry.get("is_menu"):
                    ss.added_menu, ss.added_from = entry, "photo"
                    st.rerun()  # redraw so the pin gets its new color
                elif entry:
                    st.warning(entry["summary"])


def restaurant_picker(points: list[dict], key: str, label: str, placeholder: str):
    by_key = {p["key"]: p for p in points}
    options = sorted(by_key, key=lambda k: by_key[k]["name"].lower())
    if ss.get(key) not in options:
        ss[key] = None
    pick = st.selectbox(label, options, key=key, placeholder=placeholder, label_visibility="collapsed",
                        format_func=lambda k: by_key[k]["name"] + ("" if by_key[k]["score"] is not None
                                                                   else "  ·  no menu yet"))
    return by_key.get(pick)


# ---------------------------------------------------------------- page

points = places.map_points(db, profile)
n_checked = sum(1 for p in points if p["score"] is not None)
st.markdown(theme.header(n_checked, len(points)), unsafe_allow_html=True)

# Profile: a short welcome the first time, then a one-line summary with Edit.
if not ss.profile_ready:
    with st.container(border=True):
        st.markdown("### Welcome. What are you allergic to?")
        st.caption("Every score and dish list is tailored to this. You can change it any time.")
        a, s, rem = profile_form("welcome")
        if st.button("Continue", type="primary", disabled=not a):
            save_profile_choice(a, s, rem)
else:
    c1, c4, c2, c3 = st.columns([2.6, 1.3, 1.4, 1.4], vertical_alignment="center")
    if c4.button("Chef card", width="stretch", help="A card to show restaurant staff, in English and Spanish"):
        chef_card_dialog()
    c1.markdown(theme.profile_bar(profile["allergens"], profile["severity"]), unsafe_allow_html=True)
    with c2.popover(f"Your list · {len(ss.saved)}", width="stretch"):
        st.markdown("**Your list**")
        by_key = {p["key"]: p for p in points}
        mine = [by_key[k] for k in ss.saved if k in by_key]
        if not mine:
            st.caption("Tap ☆ Save on any restaurant to keep it here.")
        # Ranked like Browse: full menus by score, then partial menus, then ones not checked yet.
        mine.sort(key=lambda p: (2 if p["score"] is None else 1 if p["partial"] else 0, -(p["score"] or 0)))
        for p in mine:
            label = ("Not checked yet" if p["score"] is None else
                     f"Score {p['score']}/100" + (" · partial menu" if p["partial"] else ""))
            st.markdown(f"<div style='margin-top:.5rem'><b>{escape(p['name'])}</b>"
                        f"<div class='gn-muted'>{escape(label)}</div></div>", unsafe_allow_html=True)
            b1, b2, b3 = st.columns(3)
            b1.button("Open", key=f"open_{p['key']}", on_click=open_restaurant, args=(p["key"],), width="stretch")
            tel = places.tel_link(p["phone"])
            if tel:
                b2.link_button("Call", tel, width="stretch")
            b3.button("Remove", key=f"rm_{p['key']}", on_click=toggle_saved, args=(p["key"],), width="stretch")
        st.markdown(theme.note("Privacy", "Saved on this device only. Tick “Remember on this device” in Edit "
                               "profile to keep it after you leave."), unsafe_allow_html=True)
    with c3.popover("Edit profile", width="stretch"):
        a, s, rem = profile_form("edit")
        if st.button("Save", type="primary", disabled=not a):
            save_profile_choice(a, s, rem)

# Search any restaurant by name.
st.write("")
found_place = restaurant_picker(points, "search_pick", "Search", "Search restaurants by name…")
st.markdown(theme.tip("Questions about an ingredient? Every restaurant has a Call to ask button."),
            unsafe_allow_html=True)
if found_place:
    show_restaurant(found_place, ctx="search")

tab_find, tab_map, tab_menu, tab_community, tab_how = st.tabs(theme.TABS)  # icons: theme.TAB_NUTS

# ---- Find restaurants
with tab_find:
    st.text_input(browser.NEAR_LABEL, key="near_box", label_visibility="collapsed")  # filled by Near me
    c1, c2, c3 = st.columns([3, 1.2, 1.2], vertical_alignment="bottom")
    place = c1.text_input("Where are you?", value=config.DEFAULT_CITY)
    radius_km = c2.select_slider("Within", options=[0.5, 1.0, 1.5, 2.0, 3.0, 5.0], value=1.5,
                                 format_func=lambda v: f"{v} km")
    with c3:
        browser.near_me_button()
    b1, b2 = st.columns(2)
    search = b1.button("Find restaurants", type="primary", width="stretch")
    browse = b2.button(f"Browse all {n_checked} checked restaurants", width="stretch")

    near = browser.parse_coords(ss.get("near_box", ""))
    if near and near != ss.get("near_used"):
        ss.near_used = near  # used once for this search, never stored
        found = run("finder", "find_restaurants", {"lat": near[0], "lon": near[1], "radius_km": radius_km},
                    progress="Finding restaurants near you")
        if found:
            ss.found, ss.ranked = found, None
    if search and place.strip():
        found = run("finder", "find_restaurants", {"location": place.strip(), "radius_km": radius_km},
                    progress="Finding restaurants")
        if found:
            ss.found, ss.ranked = found, None
    if browse:
        ss.ranked = run("summarizer", "rank_cached", {"profile": profile, "city": None})
        ss.found = None

    found = ss.get("found")
    ranked = ss.get("ranked")
    if not found and not ranked:
        st.markdown(theme.note("Start here", f"Search an area, tap Near me, or browse the {n_checked} restaurants "
                               "we've already checked. Browsing is instant and free."), unsafe_allow_html=True)
    if found:
        st.markdown(f"#### Near {escape(places.short_place(found['where']))}")
        readable = [r for r in found["restaurants"] if r["website"] or r["menu_url"]]
        if not readable:
            st.info("None of the restaurants nearby list a website, so there's no menu to read. Try a bigger "
                    "area, or open the Map and add a menu photo for one of them.")
        else:
            df = pd.DataFrame(readable)
            df["menu"] = [places.menu_outlook(r, bool(db.latest_analysis(r["key"], config.CACHE_TTL_DAYS)))
                          for r in readable]
            df["call"] = [link(places.tel_link(r.get("phone"))) for r in readable]
            df["website"] = [link(theme.safe_url(r.get("website") or r.get("menu_url"))) for r in readable]
            df["phone"] = [r.get("phone") or "Not listed" for r in readable]
            df["cuisine"] = df["cuisine"].fillna("")
            st.caption("Click a restaurant's name to open its menu. Tick the boxes on the left to check several "
                       "at once.")
            event = st.dataframe(
                df[["name", "menu", "cuisine", "distance_km", "phone", "call", "website"]],
                key="found_table", on_select="rerun", selection_mode=["multi-row", "single-cell"],
                column_config={
                    "name": st.column_config.TextColumn("Restaurant", help="Click to open the menu"),
                    "menu": st.column_config.TextColumn("Menu", help="Checked: instant and free. Chains' "
                                                        "websites often can't be read."),
                    "cuisine": st.column_config.TextColumn("Cuisine"),
                    "distance_km": st.column_config.NumberColumn("km", format="%.2f"),
                    "phone": st.column_config.TextColumn("Phone"),
                    "call": st.column_config.LinkColumn("Call", display_text="Call to ask"),
                    "website": st.column_config.LinkColumn("Website", display_text="Open"),
                },
                hide_index=True, width="stretch")
            chosen = [readable[i] for i in event.selection.rows if i < len(readable)]
            clicked = [r for r, col in event.selection.cells if col not in ("call", "website") and r < len(readable)]
            if clicked:
                r = readable[clicked[0]]
                p = next((x for x in points if x["key"] == r["key"]), None) or {
                    "key": r["key"], "name": r["name"], "cuisine": r.get("cuisine") or "", "address": r.get("address") or "",
                    "phone": r.get("phone") or "", "website": r.get("website") or r.get("menu_url") or "",
                    "lat": r.get("lat"), "lon": r.get("lon"), "score": None, "partial": False}
                if p["score"] is None and db.latest_analysis(p["key"]):  # checked since the page loaded
                    p = {**p, "score": 0}
                show_restaurant(p, ctx="find")
            limit = config.MAX_RESTAURANTS_PER_SEARCH
            if len(chosen) > limit:
                st.warning(f"Please tick {limit} or fewer.")
            if chosen and st.button(f"Check {len(chosen)} ticked menu{'s' if len(chosen) != 1 else ''}",
                                    type="primary", disabled=len(chosen) > limit):
                ss.ranked = run("summarizer", "rank_restaurants", {"restaurants": chosen, "profile": profile},
                                progress=f"Checking {len(chosen)} menu{'s' if len(chosen) != 1 else ''}")
                ranked = ss.ranked

    if ranked:
        if ranked.get("overall"):
            st.markdown(f"<p style='font-size:1.05rem'>{escape(ranked['overall'])}</p>"
                        + theme.note("AI-written", "Overview of these restaurants."), unsafe_allow_html=True)
        if not ranked["ranked"]:
            st.info("No restaurants have been checked yet. Search an area and tick a few to check.")
        # Full menus first: a few featured items from a chain's store page shouldn't outrank a real menu.
        for e in ranked["ranked"]:
            e["contact"] = {**(db.restaurant(e["restaurant"]["key"]) or {}), **e["restaurant"]}
            e["partial"] = bool(places.partial_reason(e["contact"], e["report"]))
        entries = sorted(ranked["ranked"], key=lambda e: e["partial"])

        if entries and len(entries) <= config.MAX_RESTAURANTS_PER_SEARCH:  # a short search: open cards
            for i, e in enumerate(entries):
                r, c = e["restaurant"], e["report"]["profile_counts"]
                dist = f" · {r['distance_km']} km" if r.get("distance_km") is not None else ""
                label = (f"{r['name']}{dist} · score {e['score']} · {c['none_listed']} with no nuts listed · "
                         f"{c['contains'] + c['likely']} to avoid" + (" · partial menu" if e["partial"] else ""))
                with st.expander(label):
                    show_entry(e, ctx=f"rank{i}", expanded_dishes=False)
        elif entries:  # many restaurants: a fast table, then details for the one you pick
            st.markdown(f"#### {len(entries)} restaurants, ranked for your profile")
            table = pd.DataFrame([{
                "Restaurant": e["restaurant"]["name"],
                "Score": e["score"],
                "No nuts listed": e["report"]["profile_counts"]["none_listed"],
                "Avoid": e["report"]["profile_counts"]["contains"] + e["report"]["profile_counts"]["likely"],
                "Menu": "Partial" if e["partial"] else "Full",
                "Phone": e["contact"].get("phone") or "Not listed",
                "Call": link(places.tel_link(e["contact"].get("phone"))),
            } for e in entries])
            st.caption("Click a restaurant's name to open its menu. Partial: only a few dishes could be read "
                       "(often a national chain's store page), so those come last.")
            event = st.dataframe(table, hide_index=True, width="stretch", key="browse_table", on_select="rerun",
                                 selection_mode=["single-cell", "single-row"], column_config={
                "Restaurant": st.column_config.TextColumn("Restaurant", help="Click to open the menu"),
                "Score": st.column_config.ProgressColumn("Go Nuts score", min_value=0, max_value=100, format="%d",
                                                         help="For sorting only. Never means safe."),
                "Avoid": st.column_config.NumberColumn("Contains / likely nuts"),
                "Call": st.column_config.LinkColumn("Call", display_text="Call to ask"),
            })
            picked = [r for r, col in event.selection.cells if col != "Call"] + list(event.selection.rows)
            if picked and picked[0] < len(entries):
                chosen_entry = entries[picked[0]]
                with st.container(border=True):
                    st.markdown(f"### {escape(chosen_entry['restaurant']['name'])}")
                    show_entry(chosen_entry, ctx="browse", expanded_dishes=True)
            else:
                st.markdown(theme.note("Tip", "Click any restaurant above to see its dish-by-dish menu."),
                            unsafe_allow_html=True)
        for err in ranked.get("errors", []):
            st.warning(f"**{err['name']}**: {places.failure_message(err['error'], err.get('website'))}")

# ---- Map
with tab_map:
    st.markdown("### Every restaurant we know in New Haven")
    st.caption("Tap a pin to open it. Gray pins have no menu checked yet: add a photo of their menu and "
               "everyone sees the results. Pin colors follow your profile and are for sorting only.")
    shown = st.segmented_control("Show", ["All", "Checked", "Needs a menu", "Has a phone"], default="All",
                                 label_visibility="collapsed")
    pts = [p for p in points if shown in (None, "All") or (shown == "Checked" and p["score"] is not None)
           or (shown == "Needs a menu" and p["score"] is None) or (shown == "Has a phone" and p["phone"])]
    if not pts:
        st.info({"Checked": "No restaurants are checked yet.", "Has a phone": "No phone numbers are listed yet."}
                .get(shown, "No restaurants to show yet. Use Find restaurants to add some."))
    else:
        dots = pdk.Layer("ScatterplotLayer", id="restaurants", data=pts, get_position="[lon, lat]",
                         get_fill_color="color", get_radius=40, radius_min_pixels=8, radius_max_pixels=15,
                         pickable=True, stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=2)
        symbols = pdk.Layer("TextLayer", id="symbols", data=pts, get_position="[lon, lat]", get_text="symbol",
                            get_color=[255, 255, 255], get_size=12, font_weight=700,
                            get_text_anchor="'middle'", get_alignment_baseline="'center'", pickable=False)
        view = pdk.ViewState(latitude=sum(p["lat"] for p in pts) / len(pts),
                             longitude=sum(p["lon"] for p in pts) / len(pts), zoom=14)
        tooltip = {"html": "<b>{name}</b><br/>{cuisine}<br/>{address_text}<br/>{phone_text}<br/>{score_text}",
                   "style": {"backgroundColor": "#1f1a17", "color": "white", "borderRadius": "12px",
                             "padding": "10px 12px", "fontSize": "13px"}}
        event = st.pydeck_chart(pdk.Deck(layers=[dots, symbols], initial_view_state=view, tooltip=tooltip,
                                         map_provider="carto", map_style=pdk.map_styles.CARTO_LIGHT),
                                height=520, on_select="rerun", selection_mode="single-object", key="nut_map")
        st.markdown(theme.legend(places.PIN_LABELS, places.PIN_COLORS, places.PIN_SYMBOLS), unsafe_allow_html=True)

        tapped = ((event.selection or {}).get("objects") or {}).get("restaurants") if event else None
        tap_key = tapped[0]["key"] if tapped else None
        if tap_key and tap_key != ss.get("last_tap"):  # a new tap moves the picker
            ss.last_tap = tap_key
            ss.map_pick = tap_key
        picked = restaurant_picker(points, "map_pick", "Restaurant", "Tap a pin, or choose a restaurant…")
        if picked:
            show_restaurant(picked, ctx="map")

        table = pd.DataFrame([{
            "Restaurant": p["name"], "Cuisine": p["cuisine"] or "", "Score": p["score"],
            "Menu": "Partial" if p["partial"] else "Full" if p["score"] is not None else "Needs a menu",
            "Address": (p["address"] + (" (approx.)" if p["address_source"] == "map" else "")) if p["address"]
                       else "Not listed", "Phone": p["phone"] or "Not listed",
            "Call": link(places.tel_link(p["phone"])), "Directions": link(places.directions_link(p)),
            "Website": link(theme.safe_url(p["website"])),
            "_order": 0 if p["score"] is not None and not p["partial"] else 1 if p["partial"] else 2,
        } for p in pts]).sort_values(["_order", "Score"], ascending=[True, False]).drop(columns="_order")
        with st.expander(f"All {len(pts)} as a list"):
            st.dataframe(table, hide_index=True, width="stretch", column_config={
                "Score": st.column_config.ProgressColumn("Go Nuts score", min_value=0, max_value=100, format="%d"),
                "Call": st.column_config.LinkColumn("Call", display_text="Call to ask"),
                "Directions": st.column_config.LinkColumn("Directions", display_text="Go"),
                "Website": st.column_config.LinkColumn("Website", display_text="Open"),
            })
        st.caption("Phone numbers and addresses come from OpenStreetMap and restaurants' own websites. "
                   "We never guess them: missing ones say “Not listed”.")

# ---- Check one menu
with tab_menu:
    st.markdown("### Check any menu")
    st.caption("Paste a link to a menu (web page or PDF), upload a photo, or paste the text. Results are tailored "
               "to your profile.")
    name = st.text_input("Restaurant name (optional)")
    url = st.text_input("Menu link", placeholder="https://www.example.com/menu")
    photo = st.file_uploader("Or a photo of the menu", type=["jpg", "jpeg", "png", "webp"])
    text = st.text_area("Or paste the menu text", height=140)
    samples = sorted(SAMPLE_DIR.glob("*.txt"))
    sample = st.selectbox("Or try a sample menu (made up for testing)", ["(none)"] + [p.stem for p in samples])

    if st.button("Check this menu", type="primary"):
        payload = {"name": name.strip()}
        if url.strip():
            payload["url"] = url.strip()
        elif photo is not None:
            img = menu_photo(photo)
            payload = {**payload, "images": [img]} if img else None
        elif text.strip():
            payload["menu_text"] = truncate(text)
        elif sample != "(none)":
            payload["menu_text"] = (SAMPLE_DIR / f"{sample}.txt").read_text()
        else:
            st.info("Add a menu link, a photo or some text first, or pick a sample menu.")
            payload = None
        # Sample menus are fictional; say so next to the result.
        ss.menu_is_sample = bool(payload) and not (url.strip() or photo or text.strip())
        if payload:
            entry = run("summarizer", "check_menu", {"profile": profile, **payload}, progress="Checking the menu")
            if entry and entry.get("is_menu"):
                ss.menu_entry = entry
            elif entry:
                st.warning(entry["summary"])
    entry = ss.get("menu_entry")
    if entry:
        with st.container(border=True):
            st.markdown(f"### {escape(entry['restaurant']['name'])}")
            if ss.get("menu_is_sample"):
                st.info("Sample menu: this restaurant and its menu are made up for testing. They are not real.")
            show_entry(entry, ctx="menu")

# ---- Ask: the Food Guide chat, a floating button at the bottom right of every page
def _plain(text: str) -> str:
    """Model text shown as plain words: no HTML, no markdown links or images."""
    return escape(text).replace("[", "\\[").replace("](", "\\](").replace("\n", "  \n")


# ---- Community
with tab_community:
    left, right = st.columns([1, 1], gap="large")
    known = sorted({r["name"] for r in db.restaurants()})
    with left:
        st.markdown("### Leave a review")
        with st.form("review", clear_on_submit=True):
            pick = st.selectbox("Restaurant", known, index=None, placeholder="Choose a restaurant…")
            typed = st.text_input("Not in the list?", placeholder="Type the restaurant's name")
            accommodation = st.slider("How well did they handle your nut allergy?", 1, 5, 4,
                                      help="1 = dismissive or unsafe, 5 = careful and knowledgeable")
            dish_name = st.text_input("What did you eat?")
            review_text = st.text_area("Your experience", placeholder="Did staff know the ingredients? "
                                       "Did they change gloves or use a clean pan?")
            review_photo = st.file_uploader("Photo of your food (optional, no people)",
                                            type=["jpg", "jpeg", "png", "webp"])
            nickname = st.text_input("Nickname (optional)", placeholder="Not your full name")
            st.markdown(theme.note("Privacy", "Please don't include names, contact details or photos of anyone, "
                                   "staff included. Posts with emails, phone numbers or addresses are rejected, "
                                   "and photos showing a person are not saved."), unsafe_allow_html=True)
            if st.form_submit_button("Post review", type="primary"):
                rname = typed.strip() or (pick or "")
                check = run("verifier", "moderate_post", {"text": f"{dish_name}\n{review_text}"})
                nick = run("verifier", "check_nickname", {"nickname": nickname})
                if not rname:
                    st.error("Please choose or type a restaurant.")
                elif check and not check["ok"]:
                    st.error(check["reason"])
                elif nick and not nick["ok"]:
                    st.error(nick["reason"])
                elif check and nick:
                    photo_path = save_photo(review_photo)
                    if photo_path is not False:  # False: the photo was rejected and the error is shown
                        db.add_review({"restaurant_name": rname, "nickname": nick["nickname"],
                                       "accommodation": accommodation, "dish": dish_name.strip(),
                                       "text": review_text.strip(), "photo": photo_path})
                        st.success("Thanks! Your review is posted.")

        st.markdown("### Warn others about hidden nuts")
        st.caption("Found nuts somewhere unexpected? Your warning makes future menu checks more cautious for "
                   "everyone. Warnings can only raise a dish's risk, never lower it.")
        with st.form("hidden", clear_on_submit=True):
            item = st.text_input("Food or ingredient", placeholder="e.g. vegan cheese, house green sauce")
            nuts_in = st.text_input("Which nuts?", placeholder="e.g. cashew")
            where = st.text_input("Restaurant (optional)")
            note = st.text_area("Details (optional)", height=80)
            if st.form_submit_button("Add warning"):
                check = run("verifier", "moderate_post", {"text": f"{item}\n{nuts_in}\n{note}"})
                if len(item.strip()) < 3 or not nuts_in.strip():
                    st.error("Please name the food and the nut.")
                elif check and not check["ok"]:
                    st.error(check["reason"])
                elif check:
                    db.add_hidden_nut(item, nuts_in, note, where.strip() or None)
                    st.success(f"Added. Menus mentioning “{item.strip()}” will now be flagged.")

    with right:
        st.markdown("### Recent reviews")
        recent = db.reviews(limit=20)
        if not recent:
            st.markdown(theme.note("No reviews yet", "Be the first: how did a restaurant handle your allergy?"),
                        unsafe_allow_html=True)
        for rv in recent:
            with st.container(border=True):
                show_review(rv)
        st.markdown("### Hidden-nut warnings")
        hn = pd.DataFrame(db.hidden_nuts())
        if not hn.empty:
            hn["from"] = hn["source"].map({"seed": "Go Nuts", "community": "Community"})
            hn = hn.fillna("")
            st.dataframe(hn[["item", "nuts", "note", "from"]], hide_index=True, width="stretch",
                         column_config={"item": "Food", "nuts": "Nuts", "note": "Note", "from": "From"})

    st.markdown("---")
    st.markdown("### Help improve Go Nuts")
    st.caption("Tried Go Nuts at a real restaurant? Two minutes of feedback helps. Answers are anonymous: we don't "
               "ask for or store your name, email, location or anything that could identify you.")
    with st.form("feedback", clear_on_submit=True):
        relation = st.radio("Who are you checking menus for?", ["Myself: I have a nut allergy",
                            "Someone I eat with or cook for", "No one: I'm just trying it out"], index=None)
        f1, f2 = st.columns(2)
        minutes_without = f1.number_input("Usually, how many minutes does it take you to check a menu for nuts "
                                          "WITHOUT Go Nuts?", min_value=0.0, max_value=180.0, value=None, step=1.0)
        minutes_with = f2.number_input("How many minutes did it take WITH Go Nuts?", min_value=0.0,
                                       max_value=180.0, value=None, step=1.0)
        helpful = st.slider("How helpful was it?", 1, 5, 4, help="1 = not at all, 5 = very helpful")
        would_use = st.radio("Would you use Go Nuts before eating out?", ["Yes", "Maybe", "No"], index=None,
                             horizontal=True)
        comment = st.text_area("What would make it better? (optional)", max_chars=500,
                               placeholder="Please don't include names or contact details.")
        consent = st.checkbox("I agree that my anonymous answers may be stored to improve Go Nuts and quoted "
                              "anonymously in a class report about it.")
        if st.form_submit_button("Send feedback", type="primary"):
            if not consent:
                st.error("Please tick the consent box, or leave the form blank. Nothing is saved without it.")
            elif not relation or not would_use:
                st.error("Please answer who you're checking for and whether you'd use it.")
            else:
                check = run("verifier", "moderate_post", {"text": comment}) if comment.strip() else {"ok": True}
                if check and not check["ok"]:
                    st.error(check["reason"])
                elif check:
                    db.add_feedback({"relation": relation, "minutes_without": minutes_without,
                                     "minutes_with": minutes_with, "helpful": helpful, "would_use": would_use,
                                     "comment": comment, "consent": True})
                    st.success("Thank you! Your anonymous feedback is saved.")

# ---- How it works (the agent team, the last request, and costs)
with tab_how:
    st.markdown("### How Go Nuts works")
    ai_agents = [a.title for a in team.agents.values() if a.uses_model]
    st.markdown(f"A team of {len(team.agents)} agents reads each menu. {len(ai_agents)} of them use the AI model "
                f"({', '.join(ai_agents)}; the Menu Fetcher only for photos). The rest are plain code that checks "
                "the AI's work, blocks prompt injection, and keeps costs down. Every dish rating must quote the "
                f"real menu. Model: **{config.MODEL}**.")
    section = st.segmented_control("Section", ["The team", "Your last request", "Costs", "Feedback"],
                                   default="The team", label_visibility="collapsed")
    if section in (None, "The team"):
        cols = st.columns(3)
        for i, a in enumerate(team.agents.values()):
            with cols[i % 3].container(border=True):
                st.markdown(f"**{a.title}**")
                st.markdown(theme.tag(f"Uses {config.MODEL}" if a.uses_model else "Plain code · 0 tokens"),
                            unsafe_allow_html=True)
                st.caption(a.description)
        with st.expander("Every task each agent can do"):
            for a in team.agents.values():
                for task, desc in a.skills.items():
                    st.caption(f"`{a.name}.{task}`: {desc}")
    elif section == "Feedback":
        rows = db.feedback_rows()
        st.caption("Anonymous answers from people who tried Go Nuts and agreed to share them. Real responses only: "
                   "nothing here is estimated or made up.")
        if not rows:
            st.info("No feedback yet. Ask someone with a nut allergy to try Go Nuts at a restaurant, then fill in "
                    "the form in the Community tab.")
        else:
            fb = pd.DataFrame(rows)
            timed = fb.dropna(subset=["minutes_without", "minutes_with"])
            c = st.columns(4)
            c[0].metric("Responses", len(fb))
            c[1].metric("Average helpfulness", f"{fb['helpful'].mean():.1f} / 5")
            c[2].metric("Would use it", f"{(fb['would_use'] == 'Yes').mean():.0%}")
            c[3].metric("Median minutes saved", f"{(timed['minutes_without'] - timed['minutes_with']).median():.0f}"
                        if len(timed) else "n/a", help=f"From {len(timed)} responses that gave both times.")
            st.dataframe(fb, hide_index=True, width="stretch")
            st.download_button("Download as CSV (anonymous)", fb.to_csv(index=False), file_name="go-nuts-feedback.csv",
                               mime="text/csv")
    elif section == "Your last request":
        st.caption(f"Every hand-off between agents in your last request. Any agent can delegate to any other; the "
                   f"team stops loops, chains deeper than {config.MAX_DELEGATION_DEPTH}, and more than "
                   f"{config.MAX_HOPS_PER_RUN} hand-offs.")
        trace = ss.get("last_trace") or []
        if not trace:
            st.info("Search, browse or check a menu, then come back here to see each step.")
        else:
            titles = {name: a.title for name, a in team.agents.items()}
            titles["user"] = "You"
            dot = ["digraph G {", "rankdir=LR;", 'bgcolor="transparent";',
                   'node [shape=box, style="rounded,filled", fillcolor="#ffffff", color="#d9d0c5", '
                   'fontname="Helvetica", fontcolor="#1f1a17"];',
                   'edge [fontname="Helvetica", fontsize=10, color="#8a7f75", fontcolor="#6f655c"];']
            for s in trace:
                dot.append(f'"{titles.get(s["from"], s["from"])}" -> "{titles.get(s["to"], s["to"])}" '
                           f'[label="{s["step"]}. {s["task"]}"{", color=red" if s["status"] == "error" else ""}];')
            dot.append("}")
            st.graphviz_chart("\n".join(dot))
            df = pd.DataFrame(trace)
            df["from"] = df["from"].map(lambda x: titles.get(x, x))
            df["to"] = df["to"].map(lambda x: titles.get(x, x))
            df["task"] = ["  " * d + "↳ " + t if d else t for d, t in zip(df["depth"], df["task"])]
            st.dataframe(df[["step", "from", "to", "task", "status", "tokens", "seconds", "input", "output"]],
                         hide_index=True, width="stretch")
    else:
        t = tracker.totals()
        st.markdown("**This visit**")
        c = st.columns(4)
        c[0].metric("Input tokens", f"{t['input_tokens']:,}")
        c[1].metric("Cached input", f"{t['cached_input_tokens']:,}")
        c[2].metric("Output tokens", f"{t['output_tokens']:,}")
        c[3].metric("Model calls", t["calls"])
        st.progress(min(1.0, tracker.total_tokens / tracker.budget),
                    text=f"{tracker.total_tokens:,} of {tracker.budget:,} tokens allowed per visit")

        usage = pd.DataFrame(db.usage_rows())
        cache = pd.DataFrame(db.cache_rows())
        if usage.empty:
            st.info("No model calls yet. Check a menu to start collecting real token counts.")
        else:
            usage["total"] = usage["input_tokens"] + usage["output_tokens"]
            runs = usage.groupby("run_id").agg(input_tokens=("input_tokens", "sum"),
                                               cached_input_tokens=("cached_input_tokens", "sum"),
                                               output_tokens=("output_tokens", "sum"), calls=("agent", "count"))
            st.markdown("**All time, from the usage log**")
            c = st.columns(4)
            c[0].metric("Model calls", len(usage))
            c[1].metric("Avg input / run", f"{runs['input_tokens'].mean():,.0f}")
            c[2].metric("Avg cached input / run", f"{runs['cached_input_tokens'].mean():,.0f}")
            c[3].metric("Avg output / run", f"{runs['output_tokens'].mean():,.0f}")
            st.markdown("**Tokens by agent**")
            by_agent = usage.groupby("agent")[["input_tokens", "cached_input_tokens", "output_tokens", "total"]].sum()
            by_agent["calls"] = usage.groupby("agent").size()
            st.dataframe(by_agent.sort_values("total", ascending=False), width="stretch")

            cost_run = config.cost_usd(runs["input_tokens"].mean(), runs["cached_input_tokens"].mean(),
                                       runs["output_tokens"].mean())
            st.markdown("**What it costs**")
            if cost_run is None:
                st.caption("Set the gpt-6-luna prices in `gonuts/config.py` to see dollar costs.")
            else:
                hit_rate = cache["hit"].mean() if not cache.empty else 0.0
                per_user = st.number_input("Menu checks per user per month", 1, 200, 12)
                eff = cost_run * (1 - hit_rate)
                st.dataframe(pd.DataFrame({
                    "": ["One run (no cache)", "One run (with today's cache hit rate)", "Per user / month",
                         "100 users / month", "10,000 users / month"],
                    "USD": [cost_run, eff, eff * per_user, eff * per_user * 100, eff * per_user * 10_000],
                }).style.format({"USD": "${:,.4f}"}), hide_index=True)
        if not cache.empty:
            st.markdown("**Cost Control: saved results**")
            c = st.columns(3)
            c[0].metric("Restaurant lookups", len(cache))
            c[1].metric("Served from saved results", f"{cache['hit'].mean():.0%}")
            c[2].metric("Tokens saved", f"{cache['tokens_saved'].sum():,}")
        st.caption("Raw log of every model call: logs/usage.jsonl.")


def _show_chat_message(msg: dict):
    with st.chat_message(msg["role"], avatar="🥜" if msg["role"] == "assistant" else None):
        st.markdown(_plain(msg["text"]))
        if msg["role"] != "assistant":
            return
        meta = msg.get("meta") or {}
        parts = ["AI-written"]
        if meta.get("verified"):
            parts.append("checked against the menu: " + ", ".join(meta["verified"]))
        if meta.get("stats"):
            s_ = meta["stats"]
            parts.append(f"from {s_['dishes_found']} \"{s_['phrase']}\" dishes on {s_['restaurants']} checked menus")
        parts.append("anything else is general knowledge, and recipes vary")
        st.markdown(theme.tip(" · ".join(parts)), unsafe_allow_html=True)
        for r in meta.get("restaurants", []):
            tel = places.tel_link(r.get("phone"))
            if tel:
                st.markdown(f"<a class='gn-btn gn-call' href='{escape(tel)}'>Call {escape(r['name'])} to ask · "
                            f"{escape(r['phone'])}</a>", unsafe_allow_html=True)


def food_guide_chat():
    ss.setdefault("chat", [])
    ss.setdefault("chat_asked", 0)
    with st.container(key="gn_chat_fab"):
        with st.popover("Ask about a dish", icon="💬"):
            with st.container(key="gn_chat_body"):
                st.markdown("#### Ask about a dish or a restaurant")
                st.caption("What usually goes into a dish, or what to order at a restaurant Go Nuts has checked. "
                           "Answers are AI-written. Go Nuts never calls food safe, so always confirm with staff.")
                older = ss.chat[:-6]
                if older:
                    with st.expander(f"Earlier messages ({len(older)})"):
                        for msg in older:
                            _show_chat_message(msg)
                for msg in ss.chat[-6:]:
                    _show_chat_message(msg)
                answer_slot = st.container()
                with st.form("gn_chat_form", clear_on_submit=True, border=False):
                    typed = st.text_input("Your question", max_chars=config.GUIDE_MAX_QUESTION_CHARS,
                                          placeholder="e.g. " + ASK_EXAMPLES[(len(ss.chat) // 2) % len(ASK_EXAMPLES)],
                                          label_visibility="collapsed")
                    c1, c2 = st.columns([3, 1])
                    sent = c2.form_submit_button("Ask", type="primary", width="stretch")
                question = typed.strip() if sent and typed.strip() else None
                if ss.chat and st.button("Clear chat", key="ask_clear"):
                    ss.chat = []
                    st.rerun()
                if not question:
                    return
                with answer_slot:
                    if ss.chat_asked >= config.GUIDE_MAX_QUESTIONS:
                        st.info(f"That's {config.GUIDE_MAX_QUESTIONS} questions this visit, the limit that keeps "
                                "Go Nuts free. Refresh the page to start a new chat.")
                        return
                    history = [{"role": m["role"], "text": m["text"]} for m in ss.chat]
                    user_msg = {"role": "user", "text": question}
                    _show_chat_message(user_msg)
                    out = run("guide", "answer_question", {"question": question, "profile": profile, "history": history},
                              progress="Looking that up")
                    if out:
                        reply = {"role": "assistant", "text": out["answer"], "meta": {
                            "verified": [d["dish"] for d in out.get("verified_dishes", [])][:6],
                            "stats": out.get("dish_stats"), "restaurants": out.get("restaurants", [])}}
                        ss.chat += [user_msg, reply]
                        ss.chat_asked += 1
                        # Redraw the panel (it stays open) so the question box and its example match the chat.
                        st.rerun()


food_guide_chat()
st.markdown(theme.footer(), unsafe_allow_html=True)
