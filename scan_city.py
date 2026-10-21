"""Pre-scan a city's restaurants so the app's searches are fast and nearly free.

Results go into seed/new_haven.db, which is committed to the repo. The app copies it into its live
database on startup, so the hosted app has New Haven data even after a restart.

The Finder lists restaurants from OpenStreetMap, then Cost Control gets each restaurant's report
(reading the website and asking the Menu Analyst only if it isn't cached yet).

Examples:
    python scan_city.py --dry-run                 # list New Haven restaurants with websites, no AI calls
    python scan_city.py --max 10                  # analyze the 10 closest to the Green
    python scan_city.py --location "Wooster Square, New Haven, CT" --radius 1 --max 20
    python scan_city.py --contacts                # fill in missing phone numbers from homepages, no AI calls
"""
import argparse
import re
import time
from urllib.parse import urlparse

from gonuts import chains, config, places, web
from gonuts.agents import build_team
from gonuts.db import DB
from gonuts.llm import BudgetExceeded, UsageTracker


def skip_reason(website: str) -> str | None:
    """Why a website isn't worth scanning by default, or None if it is. National chains' store
    pages show only a few featured items (see places.CHAIN_DOMAINS); --only-chains scans them."""
    u = urlparse(website)
    host = u.netloc.lower().removeprefix("www.")
    if places.is_chain(website):
        return "national chain"
    if host.startswith("locations.") or "store-locator" in u.path:
        return "store-locator page"
    return None


def site_key(website: str) -> str:
    """Same website, ignoring http/https, www, trailing slash and #anchors."""
    u = urlparse(website)
    return u.netloc.lower().removeprefix("www.") + u.path.rstrip("/").lower()


def pick_restaurants(restaurants: list[dict], include_chains: bool = False) -> tuple[list[dict], list[tuple]]:
    """Restaurants worth scanning, plus (restaurant, reason) for the ones skipped."""
    keep, skipped, seen = [], [], set()
    for r in restaurants:
        site = r["website"] or r["menu_url"]
        if not site:
            continue
        reason = None if include_chains else skip_reason(site)
        if reason is None and site_key(site) in seen:
            reason = "duplicate website"
        if reason:
            skipped.append((r, reason))
            continue
        seen.add(site_key(site))
        keep.append(r)
    return keep, skipped


AGGREGATORS = ("yelp.", "google.", "tripadvisor.", "facebook.", "instagram.", "doordash.", "grubhub.", "ubereats.",
               "seamless.", "allmenus.", "menupages.", "zmenu.", "restaurantji.", "menupix.", "opentable.", "tiktok.",
               "twitter.", "x.com", "foursquare.", "mapquest.", "postmates.", "slicelife.", "beyondmenu.")
_GENERIC = {"restaurant", "restaurants", "cafe", "café", "kitchen", "bar", "grill", "the", "and", "pizza", "new",
            "haven", "house", "food", "co", "shop", "eatery", "deli", "coffee", "bakery", "express", "of", "at"}


def import_websites(db: DB, paths: list[str]):
    """Websites found by web search for restaurants OpenStreetMap lists without one. Each is used only if
    the page itself shows the restaurant's name and a New Haven location (safety rule 2: never guessed)."""
    import json
    added = rejected = 0
    for path in paths:
        for item in json.load(open(path)):
            url = (item.get("website") or "").strip()
            r = db.restaurant(item.get("key", ""))
            if not url or not r or (r.get("website") or "").strip():
                continue
            host = re.sub(r"^https?://", "", url.lower()).split("/")[0]
            why = None
            if not url.lower().startswith(("http://", "https://")):
                why = "not a web address"
            elif any(a in host for a in AGGREGATORS):
                why = "a review, delivery or directory site, not the restaurant's own"
            if not why:
                try:
                    resp = web._download(url)
                    page = (web.html_to_text(resp.text) if "html" in resp.headers.get("Content-Type", "html") else "").lower()
                except web.FetchError as e:
                    page, why = "", f"didn't load ({e})"
            if not why:
                words = [w for w in re.findall(r"[a-z0-9']+", r["name"].lower()) if w not in _GENERIC and len(w) > 2]
                street = re.sub(r"^[\d–;-]+\s+", "", (r.get("address") or "").split(",")[0]).lower()
                name_ok = any(w in page or w in host for w in words) if words else r["name"].lower() in page
                towns = ("new haven", "east haven", "west haven", "north haven", "hamden", "woodbridge", "orange",
                         "branford")
                place_ok = any(t in page for t in towns) or (street and street.split()[0] in page) \
                    or re.search(r"\b06[45]\d\d\b", page)
                if not name_ok:
                    why = "the page doesn't show the restaurant's name"
                elif not place_ok:
                    why = "the page doesn't show a New Haven-area location"
            if why:
                rejected += 1
                print(f"  ✗ {r['name']:<34} {url[:60]:<60} {why}")
                continue
            db.conn.execute("UPDATE restaurants SET website=? WHERE key=? AND (website IS NULL OR website='')",
                            (url, r["key"]))
            db.conn.commit()
            added += 1
            print(f"  ✓ {r['name']:<34} {url}")
    print(f"\nWebsites added: {added}. Rejected after checking the page: {rejected}.")


def fill_addresses(db: DB):
    """Every restaurant on the map gets an address, from real sources only: the restaurant's own
    website first (exact), otherwise OpenStreetMap's lookup of the pin's location (approximate,
    labeled so in the app). Free: no AI calls. OpenStreetMap allows 1 request per second."""
    from gonuts import osm
    # Missing, or only a street name from the map: try again (the restaurant's website first).
    todo = [r for r in db.restaurants() if r.get("lat") is not None and (not (r.get("address") or "").strip()
            or (r.get("address_source") == "map" and not re.match(r"^\d", r.get("address") or "")))]
    print(f"{len(todo)} restaurants on the map have no address or only a street name.\n")
    counts = {"website": 0, "map": 0, "none": 0}
    for r in todo:
        address, source = None, None
        site = r.get("website") or r.get("menu_url")
        if site:
            try:
                address, source = web.website_address(site), "website"
            except web.FetchError:
                address = None
        if not address:
            time.sleep(1.1)  # OpenStreetMap usage policy: at most 1 request per second
            address, source = osm.reverse_address(r["lat"], r["lon"]), "map"
        if address and source == "map" and (r.get("address") or "").strip():
            continue  # already has this street-only address; the numbered pass below may improve it
        if address:
            if source == "website":  # exact, from the restaurant itself: replaces a map estimate
                db.conn.execute("UPDATE restaurants SET address=NULL WHERE key=? AND address_source='map'", (r["key"],))
            db.set_address(r["key"], address, source)
            counts[source] += 1
            print(f"  ✓ {r['name']:<36} {address:<52} ({'website' if source == 'website' else 'approx., from map'})")
        else:
            counts["none"] += 1
            print(f"  ✗ {r['name']:<36} no address found")
    print(f"\nFrom websites: {counts['website']}, from the map location: {counts['map']}, not found: {counts['none']}.")

    # Second pass: give street-only addresses ("Chapel Street") the nearest house number on the map.
    vague = [r for r in db.restaurants() if r.get("lat") is not None and r.get("address_source") == "map"
             and not re.match(r"^\d", r.get("address") or "")]
    if vague:
        print(f"\n{len(vague)} addresses have a street but no house number. Looking up nearby numbered addresses...")
        try:
            # Cover the farthest street-only restaurant (plus a margin), up to 19 km out.
            far_km = max(osm.distance_km(*config.DEFAULT_CENTER, r["lat"], r["lon"]) for r in vague)
            numbered = osm.numbered_addresses(*config.DEFAULT_CENTER, radius_m=min(int(far_km * 1000) + 500, 19000))
        except osm.PlacesError as e:
            print(f"  Couldn't load numbered addresses: {e}")
            return
        better = 0
        for r in vague:
            address = osm.nearest_address(r["lat"], r["lon"], numbered) or \
                osm.nearest_address(r["lat"], r["lon"], numbered, max_m=40)
            if address:
                db.conn.execute("UPDATE restaurants SET address=? WHERE key=? AND address_source='map'", (address, r["key"]))
                better += 1
                print(f"  ✓ {r['name']:<36} {address}  (approx., nearest numbered address)")
        db.conn.commit()
        print(f"\n{better} of {len(vague)} now have a house number; the rest keep their street name.")
    # Map estimates for restaurants with a website: the website's own address is exact, so prefer it.
    estimated = [r for r in db.restaurants() if r.get("address_source") == "map" and (r.get("website") or r.get("menu_url"))]
    if estimated:
        print(f"\nChecking {len(estimated)} approximate addresses against the restaurants' own websites...")
        confirmed = 0
        for r in estimated:
            try:
                address = web.website_address(r.get("website") or r.get("menu_url"))
            except web.FetchError:
                continue
            if address:
                db.conn.execute("UPDATE restaurants SET address=?, address_source='website' WHERE key=?",
                                (address, r["key"]))
                confirmed += 1
                print(f"  ✓ {r['name']:<36} {address}  (from its website; was: {r['address']})")
        db.conn.commit()
        print(f"\n{confirmed} addresses now come from the restaurant's own website.")

    # Impossible postcodes in stored map addresses (e.g. "CT 05610"): drop them rather than guess.
    for r in db.restaurants():
        a = r.get("address") or ""
        fixed = re.sub(r"(,\s*CT)\s+(?!06)\d{5}$", r"\1", a)
        if fixed != a:
            db.conn.execute("UPDATE restaurants SET address=? WHERE key=?", (fixed, r["key"]))
    db.conn.commit()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--location", default=config.DEFAULT_CITY)
    p.add_argument("--radius", type=float, default=3.0, help="km around the location")
    p.add_argument("--max", type=int, default=10, help="most restaurants to analyze this run")
    p.add_argument("--budget", type=int, default=300_000, help="token budget for this scan")
    p.add_argument("--dry-run", action="store_true", help="list restaurants only, no AI calls")
    p.add_argument("--contacts", action="store_true",
                   help="only fill in missing phone numbers from each restaurant's homepage (free, no AI calls)")
    p.add_argument("--include-chains", action="store_true",
                   help="also scan national chains and store-locator pages (duplicates are always skipped)")
    p.add_argument("--import-websites", nargs="+", metavar="JSON",
                   help="add websites found by web search (each checked against the live page first)")
    p.add_argument("--retry-failed", action="store_true",
                   help="also retry restaurants whose website failed in the last 14 days")
    p.add_argument("--addresses", action="store_true",
                   help="fill in missing addresses for every mapped restaurant (website first, then OpenStreetMap)")
    p.add_argument("--new-readers", action="store_true",
                   help="re-check only unchecked restaurants whose menu is GoNation data or menu pictures")
    p.add_argument("--only-chains", action="store_true",
                   help="scan only the national chains, one location per chain (they share one menu)")
    p.add_argument("--db", default=str(config.SEED_DB_PATH),
                   help="database to fill (default: the committed New Haven seed, seed/new_haven.db)")
    args = p.parse_args()

    db = DB(args.db)
    if args.addresses:
        fill_addresses(db)
        return
    if args.import_websites:
        import_websites(db, args.import_websites)
        return
    team = build_team(UsageTracker(budget=args.budget), db)
    team.start_run()
    found = team.send("user", "finder", "find_restaurants",
                      {"location": args.location, "radius_km": args.radius, "limit": 1500})  # cap: nearest 1,500
    for r in found["restaurants"]:  # websites found by search (--import-websites) live in our database
        stored = db.restaurant(r["key"]) or {}
        r["website"] = r.get("website") or stored.get("website")
    with_site, skipped = pick_restaurants(found["restaurants"], args.include_chains)
    if args.only_chains:
        one_each = {}
        for r, reason in skipped:
            if reason != "duplicate website":
                one_each.setdefault(r["key"], r)  # every Dunkin' shares one key, so one try covers all
        with_site, skipped = list(one_each.values()), []
        for r in list(with_site):  # official allergen data: plain code, no AI
            cached = db.latest_analysis(r["key"])
            report = chains.official_report(r.get("website"), cached["result"] if cached else None)
            if report:
                db.save_analysis(r["key"], "official:" + r["key"], report, 0)
                with_site.remove(r)
                print(f"  ✓ {r['name']:<40} official allergen data · {len(report['dishes'])} items · 0 tokens")
            else:
                print(f"  · {r['name']:<40} official guide: {chains.guide_url(r.get('website')) or 'none found'}")
    print(f"{found['where']}\n{len(found['restaurants'])} restaurants, {len(with_site) + len(skipped)} with a website, "
          f"{len(skipped)} skipped, {len(with_site)} to scan.\n")

    if args.new_readers:
        picked = []
        for r in with_site:
            cached = db.latest_analysis(r["key"])
            if cached and cached["result"].get("is_menu"):
                continue
            try:
                page = web.fetch_menu_page(r["website"] or r["menu_url"])  # plain code, no tokens
            except web.FetchError:
                continue
            if page["platform"] == "gonation" or (page["images"] and not web.looks_like_menu_text(page["text"])):
                picked.append(r)
                print(f"  → {r['name']:<40} {page['platform']}, {len(page['images'])} menu pictures")
        with_site = picked
        print(f"\n{len(picked)} restaurants can be read by the new readers.\n")

    if args.contacts:
        added = 0
        for r in with_site:
            if r.get("phone"):
                continue
            try:
                phone = web.fetch_phone(r["website"] or r["menu_url"])
            except web.FetchError as e:
                print(f"  ✗ {r['name']}: {e}")
                continue
            if phone:
                db.set_phone(r["key"], phone)
                added += 1
                print(f"  ✓ {r['name']:<40} {phone}")
        have = sum(1 for r in db.restaurants() if r.get("phone"))
        print(f"\nAdded {added} phone numbers from restaurant websites. {have} restaurants now have a phone.")
        return

    if args.dry_run:
        for r in with_site:
            print(f"  {r['distance_km']:>5} km  {r['name']:<40} {r['website'] or r['menu_url']}")
        if skipped:
            print("\nSkipped:")
            for r, reason in skipped:
                print(f"  {r['distance_km']:>5} km  {r['name']:<40} {reason}")
        return

    done = cached = failed = 0
    if not args.retry_failed:
        before = len(with_site)
        with_site = [r for r in with_site if not db.recent_scan_failure(r["key"])]
        if before - len(with_site):
            print(f"Skipping {before - len(with_site)} restaurants that failed in the last "
                  f"{config.CACHE_TTL_DAYS} days (use --retry-failed to try them again).\n")
    for r in with_site[: args.max]:
        team.start_run()
        start = time.time()
        try:
            rep = team.send("user", "cost_control", "get_report", {"restaurant": r})
        except BudgetExceeded as e:
            print(f"\nStopped: {e}")
            break
        except Exception as e:
            failed += 1
            db.record_scan_failure(r["key"], str(e))
            print(f"  ✗ {r['name']}: {e}")
            continue
        if rep.get("error") or not rep.get("is_menu"):
            failed += 1
            db.record_scan_failure(r["key"], rep.get("error") or "no menu found on the website")
            print(f"  ✗ {r['name']}: {rep.get('error') or 'no menu found on the website'}")
            continue
        done += 1
        cached += rep.get("from_cache", False)
        c = rep["counts"]
        cost = "cached" if rep.get("from_cache") else f"{rep['cost_tokens']:,} tokens"
        print(f"  ✓ {r['name']:<40} {sum(c.values()):>3} dishes, {c['contains'] + c['likely']:>2} with nuts · "
              f"{cost} · {time.time() - start:.1f}s")

    t = team.llm.tracker.totals()
    print(f"\nAnalyzed {done} ({cached} from cache), {failed} failed.")
    print(f"Tokens: {t['input_tokens']:,} input ({t['cached_input_tokens']:,} cached), {t['output_tokens']:,} output, "
          f"{t['calls']} model calls.")
    cost = config.cost_usd(t["input_tokens"], t["cached_input_tokens"], t["output_tokens"])
    if cost is not None:
        print(f"Cost: ${cost:.4f}")


if __name__ == "__main__":
    main()
