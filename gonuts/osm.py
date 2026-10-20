"""OpenStreetMap lookups: nearby restaurants from OpenStreetMap. Free, no API key, no tokens."""
import hashlib
import json
import math
import time

import requests

from . import config
from .web import us_phone

HEADERS = {"User-Agent": "GoNuts/0.2 (student project, Yale MGT 409)"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
# The public Overpass servers are often overloaded (502/504/429), so try mirrors in turn.
OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


OVERPASS_CACHE_DIR = config.DATA_DIR / "osm_cache"


class PlacesError(Exception):
    pass


def geocode(place: str) -> tuple[float, float, str]:
    """Address or neighborhood -> (lat, lon, display name)."""
    try:
        r = requests.get(NOMINATIM, params={"q": place, "format": "json", "limit": 1},
                         headers=HEADERS, timeout=15)
        r.raise_for_status()
        hits = r.json()
    except (requests.RequestException, ValueError):
        raise PlacesError("The map service couldn't look up that location right now. Please try again in a minute.")
    if not hits:
        raise PlacesError(f"Could not find '{place}'. Try a street address or city.")
    return float(hits[0]["lat"]), float(hits[0]["lon"]), hits[0]["display_name"]


def distance_km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def _overpass(query: str) -> list[dict]:
    """Run an Overpass query, trying each server in turn. Results are cached on disk."""
    cache_file = OVERPASS_CACHE_DIR / (hashlib.sha256(query.encode()).hexdigest()[:16] + ".json")
    if cache_file.is_file() and time.time() - cache_file.stat().st_mtime < config.CACHE_TTL_DAYS * 86400:
        return json.loads(cache_file.read_text())

    errors = []
    for server in OVERPASS_SERVERS:
        try:
            r = requests.post(server, data={"data": query}, headers=HEADERS, timeout=90)
            r.raise_for_status()
            elements = r.json().get("elements", [])
        except (requests.RequestException, ValueError) as e:  # ValueError: busy server sent HTML, not JSON
            errors.append(f"{server.split('/')[2]}: {e}")
            continue
        OVERPASS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(elements))
        return elements
    print("Overpass failures:", "; ".join(errors))  # details for the server log, not the user
    raise PlacesError("The map service (OpenStreetMap) is busy right now, so restaurants couldn't be listed. "
                      "Please try again in a minute, or browse restaurants we've already checked.")


def tidy_street(housenumber: str | None, street: str | None) -> str:
    """OpenStreetMap lists several values with ';' ("324;326" or "Beers Street;Chapel Street").
    Several numbers on one street become a range ("324–326"); a corner building on two streets
    keeps its first number and first street."""
    numbers = [n.strip() for n in (housenumber or "").split(";") if n.strip()]
    streets = [x.strip() for x in (street or "").split(";") if x.strip()]
    if not streets:
        return ""
    if len(streets) > 1 or len(numbers) <= 1:
        number = numbers[0] if numbers else ""
    else:
        number = f"{numbers[0]}–{numbers[-1]}"
    return " ".join(filter(None, [number, streets[0]]))


def full_address(tags: dict) -> str:
    """'1060 Chapel Street, New Haven, CT 06510' from OpenStreetMap tags; blank parts are left out.
    Never guessed: if OpenStreetMap has no street, the address is blank."""
    street = tidy_street(tags.get("addr:housenumber"), tags.get("addr:street"))
    if not street:
        return ""
    region = " ".join(filter(None, [tags.get("addr:state"), tags.get("addr:postcode")]))
    return ", ".join(filter(None, [street, tags.get("addr:city"), region]))


def clean_phone(raw: str | None) -> str | None:
    """The restaurant's first listed US phone number, as OpenStreetMap has it. None if not listed."""
    if not raw:
        return None
    return us_phone(raw.split(";")[0])


def nearby_restaurants(lat: float, lon: float, radius_m: int = 1500, limit: int = 30) -> list[dict]:
    """Restaurants and cafes within radius that list a website (we need it to read the menu)."""
    query = f"""
    [out:json][timeout:60];
    (
      nwr["amenity"~"^(restaurant|cafe|fast_food)$"](around:{radius_m},{lat},{lon});
    );
    out center tags;
    """
    elements = _overpass(query)

    results = []
    for el in elements:
        tags = el.get("tags", {})
        website = tags.get("website") or tags.get("contact:website") or tags.get("url")
        name = tags.get("name")
        if not name:
            continue
        elat = el.get("lat") or el.get("center", {}).get("lat")
        elon = el.get("lon") or el.get("center", {}).get("lon")
        if elat is None:
            continue
        if website and not website.startswith("http"):
            website = "https://" + website
        results.append({
            "name": name,
            "cuisine": tags.get("cuisine", "").replace(";", ", ").replace("_", " "),
            "address": full_address(tags),
            "phone": clean_phone(tags.get("phone") or tags.get("contact:phone")),
            "website": website,
            "menu_url": tags.get("website:menu"),
            "lat": elat,
            "lon": elon,
            "distance_km": round(distance_km(lat, lon, elat, elon), 2),
        })
    results.sort(key=lambda r: (r["website"] is None and r["menu_url"] is None, r["distance_km"]))
    return results[:limit]


def reverse_address(lat: float, lon: float) -> str | None:
    """The street address OpenStreetMap has at a map point (nearest building), or None.
    This is approximate: the pin may sit on a neighboring building. Callers must label it so.
    OpenStreetMap's usage policy allows at most 1 request per second; callers must pause."""
    try:
        r = requests.get(NOMINATIM_REVERSE, params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18,
                                                    "addressdetails": 1}, headers=HEADERS, timeout=15)
        r.raise_for_status()
        a = r.json().get("address") or {}
    except (requests.RequestException, ValueError):
        return None
    street = tidy_street(a.get("house_number"), a.get("road"))
    if not street:
        return None
    city = a.get("city") or a.get("town") or a.get("village") or a.get("hamlet")
    state = {"Connecticut": "CT"}.get(a.get("state"), a.get("state"))
    postcode = a.get("postcode") or ""
    if state == "CT" and not postcode.startswith("06"):
        postcode = ""  # a typo in the map data (e.g. 05610): leave it out rather than guess
    region = " ".join(filter(None, [state, postcode]))
    return ", ".join(filter(None, [street, city, region]))


def numbered_addresses(lat: float, lon: float, radius_m: int = 3500) -> list[tuple[float, float, str]]:
    """Every OpenStreetMap feature with a house number near a point: [(lat, lon, address)].
    One request (cached for CACHE_TTL_DAYS), used to give street-only addresses a number."""
    query = f"""
    [out:json][timeout:90];
    nwr["addr:housenumber"]["addr:street"](around:{radius_m},{lat},{lon});
    out center tags;
    """
    out = []
    for el in _overpass(query):
        tags = el.get("tags", {})
        elat = el.get("lat") or el.get("center", {}).get("lat")
        elon = el.get("lon") or el.get("center", {}).get("lon")
        address = full_address(tags)
        if elat is not None and address:
            out.append((elat, elon, address))
    return out


def nearest_address(lat: float, lon: float, addresses: list[tuple[float, float, str]],
                    max_m: float = 25) -> str | None:
    """The numbered address closest to a point, if one is within max_m metres."""
    best, best_d = None, max_m / 1000
    for alat, alon, address in addresses:
        if abs(alat - lat) > 0.001 or abs(alon - lon) > 0.0013:  # quick box check (~110 m)
            continue
        d = distance_km(lat, lon, alat, alon)
        if d <= best_d:
            best, best_d = address, d
    return best
