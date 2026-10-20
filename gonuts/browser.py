"""Tiny browser helpers: remember the allergy profile on this device, and 'Near me'.

Privacy (safety rule 3): allergy details and location are health and personal data, so they never
go in the page address and are never stored on the server. The profile is kept in a cookie on the
diner's own device, and only when they tick "Remember". Location is rounded to about 100 m and
handed straight to this session's search; it is not stored anywhere, not even in a cookie.
"""
import json
from urllib.parse import quote, unquote

import streamlit as st

PROFILE_COOKIE = "gonuts_profile"
NEAR_LABEL = "gn-near-coords"   # hidden text box the Near me button fills in


def _set_cookie(name: str, value: str, max_age: int):
    st.iframe(
        f"<script>parent.document.cookie = {json.dumps(f'{name}={quote(value)}')} + "
        f"'; max-age={max_age}; path=/; SameSite=Strict';</script>", height=1)


def _cookie(name: str) -> str:
    """A cookie's text, or "" if there is none (or the browser sent something that isn't text)."""
    try:
        raw = st.context.cookies.get(name)
    except Exception:
        return ""
    return raw if isinstance(raw, str) else ""


def load_profile() -> dict | None:
    raw = _cookie(PROFILE_COOKIE)
    if not raw:
        return None
    try:
        data = json.loads(unquote(raw))
        return {"allergens": [str(a) for a in data.get("allergens", [])][:20],
                "severity": str(data.get("severity", ""))[:60]}
    except (ValueError, AttributeError):
        return None


def save_profile(profile: dict):
    _set_cookie(PROFILE_COOKIE, json.dumps({"allergens": profile["allergens"], "severity": profile["severity"]}),
                max_age=365 * 86400)


def forget_profile():
    _set_cookie(PROFILE_COOKIE, "", max_age=0)


LIST_COOKIE = "gonuts_list"
MAX_SAVED = 50   # restaurants on "Your list" (keeps the cookie well under the browser's 4 KB limit)


def load_list() -> list[str]:
    """Saved restaurant keys from this device (only names of restaurants, nothing about the diner)."""
    raw = unquote(_cookie(LIST_COOKIE))
    keys = [k for k in raw.split(",") if k and len(k) <= 60 and all(c.isalnum() or c in "-_" for c in k)]
    return list(dict.fromkeys(keys))[:MAX_SAVED]


def save_list(keys: list[str]):
    _set_cookie(LIST_COOKIE, ",".join(keys[:MAX_SAVED]), max_age=365 * 86400)


def forget_list():
    _set_cookie(LIST_COOKIE, "", max_age=0)


def parse_coords(raw: str) -> tuple[float, float] | None:
    try:
        lat, lon = (float(x) for x in (raw or "").split(","))
    except ValueError:
        return None
    return (round(lat, 3), round(lon, 3)) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def near_me_button(label: str = "Near me"):
    """A button that asks the browser for its location (the browser shows its own permission prompt),
    rounds it to ~100 m and types it into the hidden NEAR_LABEL box, which starts the search."""
    st.iframe(f"""
<style>
  body {{ margin: 0; }}
  @font-face {{ font-family: "Libre Franklin"; font-weight: 100 900;
               src: url("/app/static/fonts/LibreFranklin-variable.woff2") format("woff2"); }}
  button {{ font: 500 12px "Libre Franklin", "Helvetica Neue", Arial, sans-serif; letter-spacing: 2px;
           text-transform: uppercase; width: 100%; height: 40px; border-radius: 2px; border: 1px solid #484848;
           background: #fff; color: #484848; cursor: pointer; }}
  button:hover {{ background: #484848; color: #fff; }}
  small {{ display: block; font: 12px "Libre Franklin", Arial, sans-serif; color: #757575; margin-top: 4px;
          text-align: center; }}
</style>
<button id="b">◎&nbsp; {label}</button><small id="m"></small>
<script>
  const b = document.getElementById('b'), m = document.getElementById('m');
  function send(v) {{
    const box = parent.document.querySelector('input[aria-label="{NEAR_LABEL}"]');
    if (!box) {{ m.textContent = 'Please try again.'; return; }}
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(box, v);
    box.dispatchEvent(new Event('input', {{ bubbles: true }}));
    box.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
  }}
  b.onclick = () => {{
    if (!navigator.geolocation) {{ m.textContent = 'This browser can\\'t share location.'; return; }}
    m.textContent = 'Asking your browser…';
    navigator.geolocation.getCurrentPosition(
      p => {{ m.textContent = ''; send(p.coords.latitude.toFixed(3) + ',' + p.coords.longitude.toFixed(3)); }},
      () => {{ m.textContent = 'Location not shared. Type an area instead.'; }},
      {{ enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }});
  }};
</script>""", height=62)
