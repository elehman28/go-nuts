"""SQLite storage: restaurants, cached analyses, token usage, reviews, photos, hidden-nut warnings."""
import json
import re
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config


def _phone(raw: str | None) -> str | None:
    from .web import us_phone  # imported here: web pulls in requests, PDF and image libraries
    return us_phone(raw)

SCHEMA = """
CREATE TABLE IF NOT EXISTS restaurants (
    key TEXT PRIMARY KEY,           -- normalized name, used to link reviews and analyses
    name TEXT NOT NULL,
    cuisine TEXT, address TEXT, website TEXT, menu_url TEXT,
    lat REAL, lon REAL, city TEXT,
    updated TEXT,
    phone TEXT                      -- the restaurant's public business phone, from OpenStreetMap
);
CREATE TABLE IF NOT EXISTS analyses (
    restaurant_key TEXT,
    menu_hash TEXT,                 -- same menu text = same analysis, even if the restaurant differs
    result TEXT NOT NULL,           -- JSON from the Analyst + Verifier
    tokens INTEGER,                 -- tokens it cost to make, so we can report tokens saved
    created TEXT,
    PRIMARY KEY (restaurant_key, menu_hash)
);
CREATE TABLE IF NOT EXISTS usage (
    time TEXT, run_id TEXT, agent TEXT, model TEXT,
    input_tokens INTEGER, cached_input_tokens INTEGER, output_tokens INTEGER, seconds REAL
);
CREATE TABLE IF NOT EXISTS cache_events (
    time TEXT, restaurant_key TEXT, hit INTEGER, tokens_saved INTEGER
);
CREATE TABLE IF NOT EXISTS memo (
    key TEXT PRIMARY KEY,           -- hash of an agent's input
    value TEXT, tokens INTEGER, created TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_key TEXT, restaurant_name TEXT,
    nickname TEXT, accommodation INTEGER,   -- 1-5: how well the kitchen handled the allergy
    dish TEXT, text TEXT, photo TEXT,
    created TEXT
);
CREATE TABLE IF NOT EXISTS scan_failures (
    restaurant_key TEXT PRIMARY KEY,
    reason TEXT,
    created TEXT                    -- scans skip a failed site for CACHE_TTL_DAYS instead of paying again
);
CREATE TABLE IF NOT EXISTS feedback (
    -- Anonymous user-trial answers. Saved only with consent; no name, contact, cookie, IP or session id.
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT,                   -- date only (no time), so answers can't be matched to visits
    relation TEXT,                  -- "I have a nut allergy" / "for someone I eat with" / "no"
    minutes_without REAL,           -- usual minutes to check a menu for nuts, without Go Nuts
    minutes_with REAL,              -- minutes it took with Go Nuts
    helpful INTEGER,                -- 1-5
    would_use TEXT,                 -- yes / maybe / no
    comment TEXT,                   -- screened for personal information before saving
    consent INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS hidden_nuts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item TEXT NOT NULL,             -- e.g. "vegan cheese"
    nuts TEXT NOT NULL,             -- e.g. "cashew"
    note TEXT,
    restaurant_key TEXT,            -- optional: a warning about one restaurant's dish
    source TEXT,                    -- "seed" or "community"
    created TEXT
);
"""

# Starting list of foods that often hide nuts. The community adds to it.
SEED_HIDDEN_NUTS = [
    ("vegan cheese", "cashew", "Most vegan cheeses are cashew-based."),
    ("vegan parmesan", "cashew, walnut", "Often made from cashews or walnuts."),
    ("cashew cream", "cashew", "Used in vegan sauces, soups and desserts."),
    ("vegan dessert", "cashew, almond", "Vegan cheesecakes and creams are often cashew-based."),
    ("pesto", "pine nut, walnut", "Traditional pesto uses pine nuts; some use walnuts."),
    ("romesco", "almond, hazelnut", "Spanish sauce made with almonds or hazelnuts."),
    ("mole", "peanut, almond", "Many moles are thickened with nuts."),
    ("satay", "peanut", "Satay sauce is peanut-based."),
    ("pad thai", "peanut", "Often topped with or cooked with peanuts."),
    ("kung pao", "peanut", "Made with peanuts."),
    ("massaman", "peanut", "Massaman curry usually contains peanuts."),
    ("korma", "cashew, almond", "Often thickened with cashew or almond paste."),
    ("butter chicken", "cashew", "Many recipes use cashew paste."),
    ("tikka masala", "cashew, almond", "Some recipes use nut paste."),
    ("baklava", "walnut, pistachio", "Layered with chopped nuts."),
    ("macaron", "almond", "Made with almond flour."),
    ("frangipane", "almond", "Almond cream filling."),
    ("marzipan", "almond", "Almond paste."),
    ("praline", "hazelnut, pecan, almond", "Made with nuts."),
    ("nougat", "almond, hazelnut", "Usually contains nuts."),
    ("gianduja", "hazelnut", "Chocolate-hazelnut paste."),
    ("biscotti", "almond", "Often contain almonds."),
    ("gluten-free", "almond", "Gluten-free baked goods often use almond flour."),
    ("granola", "almond, walnut, pecan", "Usually contains nuts."),
    ("dukkah", "hazelnut", "Egyptian spice and nut blend."),
    ("muhammara", "walnut", "Red pepper and walnut dip."),
    ("salsa macha", "peanut", "Chili oil salsa usually made with peanuts."),
    ("chili crisp", "peanut", "Some brands contain peanuts."),
    ("picada", "almond, hazelnut", "Catalan sauce of ground nuts."),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def restaurant_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


class DB:
    def __init__(self, path: Path | str = config.DB_PATH, seed: Path | str | None = None):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        new_db = not Path(path).exists()
        if seed and new_db and Path(seed).is_file():
            shutil.copy(seed, path)  # start from the pre-scanned restaurants
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        if not self.conn.execute("SELECT 1 FROM hidden_nuts WHERE source='seed' LIMIT 1").fetchone():
            self.conn.executemany(
                "INSERT INTO hidden_nuts (item, nuts, note, source, created) VALUES (?,?,?,'seed',?)",
                [(i, n, note, now()) for i, n, note in SEED_HIDDEN_NUTS])
        self.conn.commit()
        if seed and not new_db and Path(seed).is_file() and Path(seed).resolve() != Path(path).resolve():
            self.import_seed(seed)

    def _migrate(self):
        """Add columns that older databases (including an older seed) don't have yet."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(restaurants)")}
        if "phone" not in cols:
            self.conn.execute("ALTER TABLE restaurants ADD COLUMN phone TEXT")
        if "address_source" not in cols:  # osm | website | map (approximate, from the pin's location)
            self.conn.execute("ALTER TABLE restaurants ADD COLUMN address_source TEXT")

    def import_seed(self, seed: Path | str):
        """Add restaurants and analyses from the seed database that this one doesn't have yet.
        Restaurants already here get contact details (phone, address, location) the seed has."""
        self.conn.execute("ATTACH DATABASE ? AS seed", (str(seed),))
        try:
            for table in ("restaurants", "analyses"):
                ours = [r["name"] for r in self.conn.execute(f"PRAGMA main.table_info({table})")]
                theirs = {r["name"] for r in self.conn.execute(f"PRAGMA seed.table_info({table})")}
                cols = ", ".join(c for c in ours if c in theirs)
                self.conn.execute(f"INSERT OR IGNORE INTO main.{table} ({cols}) SELECT {cols} FROM seed.{table}")
            seed_cols = {r["name"] for r in self.conn.execute("PRAGMA seed.table_info(restaurants)")}
            if {"address", "address_source"} <= seed_cols:
                # A saved address with a house number beats a street-only one here.
                self.conn.execute("""UPDATE main.restaurants SET
                    address = (SELECT s.address FROM seed.restaurants s WHERE s.key = main.restaurants.key),
                    address_source = (SELECT s.address_source FROM seed.restaurants s WHERE s.key = main.restaurants.key)
                    WHERE (address IS NULL OR address = '' OR substr(address, 1, 1) NOT GLOB '[0-9]')
                      AND EXISTS (SELECT 1 FROM seed.restaurants s WHERE s.key = main.restaurants.key
                                  AND substr(s.address, 1, 1) GLOB '[0-9]')""")
            for col in ("phone", "address", "address_source", "lat", "lon"):
                if col in seed_cols:
                    self.conn.execute(f"""UPDATE main.restaurants SET {col} = (SELECT s.{col} FROM seed.restaurants s
                                          WHERE s.key = main.restaurants.key)
                                          WHERE ({col} IS NULL OR {col} = '') AND EXISTS (SELECT 1 FROM seed.restaurants s
                                          WHERE s.key = main.restaurants.key AND s.{col} IS NOT NULL AND s.{col} != '')""")
            self.conn.commit()
        finally:
            self.conn.execute("DETACH DATABASE seed")
        self.format_phones()

    def format_phones(self):
        """Rewrite stored phone numbers in one format (+1-203-287-9286); older rows kept the source's."""
        for row in self.conn.execute("SELECT key, phone FROM restaurants WHERE phone IS NOT NULL AND phone != ''").fetchall():
            if _phone(row["phone"]) != row["phone"]:
                self.conn.execute("UPDATE restaurants SET phone=? WHERE key=?", (_phone(row["phone"]), row["key"]))
        self.conn.commit()

    def _rows(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    # ---- restaurants
    def upsert_restaurant(self, r: dict) -> str:
        key = r.get("key") or restaurant_key(r["name"])
        self.conn.execute(
            """INSERT INTO restaurants (key,name,cuisine,address,website,menu_url,lat,lon,city,updated,phone)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET name=excluded.name, cuisine=excluded.cuisine,
                 address=COALESCE(NULLIF(excluded.address, ''), address),
                 website=COALESCE(excluded.website, website),
                 menu_url=COALESCE(excluded.menu_url, menu_url),
                 lat=COALESCE(excluded.lat, lat), lon=COALESCE(excluded.lon, lon),
                 city=COALESCE(excluded.city, city), updated=excluded.updated,
                 phone=COALESCE(excluded.phone, phone)""",
            (key, r["name"], r.get("cuisine"), r.get("address"), r.get("website"), r.get("menu_url"),
             r.get("lat"), r.get("lon"), r.get("city"), now(), _phone(r.get("phone"))))
        self.conn.commit()
        return key

    def set_address(self, key: str, address: str, source: str):
        """Fill in an address only where none is stored yet, and remember where it came from."""
        self.conn.execute("UPDATE restaurants SET address=?, address_source=? WHERE key=? AND "
                          "(address IS NULL OR address='')", (address, source, key))
        self.conn.commit()

    def set_phone(self, key: str, phone: str):
        """Fill in a phone number only where none is stored yet."""
        self.conn.execute("UPDATE restaurants SET phone=? WHERE key=? AND (phone IS NULL OR phone='')",
                          (_phone(phone), key))
        self.conn.commit()

    def restaurant(self, key: str) -> dict | None:
        rows = self._rows("SELECT * FROM restaurants WHERE key=?", (key,))
        return rows[0] if rows else None

    def restaurants(self, city: str | None = None) -> list[dict]:
        if city:
            return self._rows("SELECT * FROM restaurants WHERE city=? ORDER BY name", (city,))
        return self._rows("SELECT * FROM restaurants ORDER BY name")

    # ---- analysis cache
    def latest_analysis(self, key: str, max_age_days: int | None = None) -> dict | None:
        row = self.conn.execute(
            "SELECT result, created, tokens FROM analyses WHERE restaurant_key=? ORDER BY created DESC LIMIT 1",
            (key,)).fetchone()
        if not row:
            return None
        if max_age_days is not None:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(row["created"])
            if age > timedelta(days=max_age_days):
                return None
        return {"result": json.loads(row["result"]), "created": row["created"], "tokens": row["tokens"]}

    def analysis_by_hash(self, menu_hash: str) -> dict | None:
        row = self.conn.execute(
            "SELECT result, tokens FROM analyses WHERE menu_hash=? ORDER BY created DESC LIMIT 1",
            (menu_hash,)).fetchone()
        return {"result": json.loads(row["result"]), "tokens": row["tokens"]} if row else None

    def save_analysis(self, key: str, menu_hash: str, result: dict, tokens: int):
        self.conn.execute(
            "INSERT OR REPLACE INTO analyses (restaurant_key, menu_hash, result, tokens, created) VALUES (?,?,?,?,?)",
            (key, menu_hash, json.dumps(result), tokens, now()))
        self.conn.commit()

    def log_cache(self, key: str, hit: bool, tokens_saved: int = 0):
        self.conn.execute("INSERT INTO cache_events VALUES (?,?,?,?)", (now(), key, int(hit), tokens_saved))
        self.conn.commit()

    def recall(self, key: str) -> dict | None:
        row = self.conn.execute("SELECT value, tokens FROM memo WHERE key=?", (key,)).fetchone()
        return {"value": json.loads(row["value"]), "tokens": row["tokens"]} if row else None

    def remember(self, key: str, value, tokens: int):
        self.conn.execute("INSERT OR REPLACE INTO memo VALUES (?,?,?,?)", (key, json.dumps(value), tokens, now()))
        self.conn.commit()

    # ---- token usage
    def log_usage(self, rec: dict):
        self.conn.execute(
            "INSERT INTO usage VALUES (?,?,?,?,?,?,?,?)",
            (rec["time"], rec.get("run_id"), rec["agent"], rec["model"], rec["input_tokens"],
             rec["cached_input_tokens"], rec["output_tokens"], rec["seconds"]))
        self.conn.commit()

    def tokens_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM usage WHERE time >= ?", (today,)).fetchone()
        return row[0]

    def usage_rows(self) -> list[dict]:
        return self._rows("SELECT * FROM usage ORDER BY time")

    def cache_rows(self) -> list[dict]:
        return self._rows("SELECT * FROM cache_events ORDER BY time")

    # ---- community
    def record_scan_failure(self, key: str, reason: str):
        self.conn.execute("INSERT OR REPLACE INTO scan_failures VALUES (?,?,?)", (key, reason[:300], now()))
        self.conn.commit()

    def recent_scan_failure(self, key: str, max_age_days: int = config.CACHE_TTL_DAYS) -> str | None:
        row = self.conn.execute("SELECT reason, created FROM scan_failures WHERE restaurant_key=?", (key,)).fetchone()
        if not row:
            return None
        age = datetime.now(timezone.utc) - datetime.fromisoformat(row["created"])
        return row["reason"] if age.days < max_age_days else None

    def add_feedback(self, f: dict) -> int:
        """Store one anonymous feedback answer. Refuses anything without consent."""
        if not f.get("consent"):
            raise ValueError("Feedback is only saved with consent.")
        cur = self.conn.execute(
            "INSERT INTO feedback (created, relation, minutes_without, minutes_with, helpful, would_use, comment, consent) "
            "VALUES (?,?,?,?,?,?,?,1)",
            (now()[:10], f.get("relation"), f.get("minutes_without"), f.get("minutes_with"), f.get("helpful"),
             f.get("would_use"), (f.get("comment") or "").strip() or None))
        self.conn.commit()
        return cur.lastrowid

    def feedback_rows(self) -> list[dict]:
        return self._rows("SELECT created, relation, minutes_without, minutes_with, helpful, would_use, comment "
                          "FROM feedback ORDER BY id")

    def add_review(self, r: dict) -> int:
        cur = self.conn.execute(
            """INSERT INTO reviews (restaurant_key, restaurant_name, nickname, accommodation, dish, text, photo, created)
               VALUES (?,?,?,?,?,?,?,?)""",
            (restaurant_key(r["restaurant_name"]), r["restaurant_name"], r.get("nickname"),
             r.get("accommodation"), r.get("dish"), r.get("text"), r.get("photo"), now()))
        self.conn.commit()
        return cur.lastrowid

    def reviews(self, key: str | None = None, limit: int = 50) -> list[dict]:
        if key:
            return self._rows("SELECT * FROM reviews WHERE restaurant_key=? ORDER BY created DESC LIMIT ?", (key, limit))
        return self._rows("SELECT * FROM reviews ORDER BY created DESC LIMIT ?", (limit,))

    def accommodation_score(self, key: str) -> tuple[float | None, int]:
        row = self.conn.execute(
            "SELECT AVG(accommodation), COUNT(accommodation) FROM reviews WHERE restaurant_key=? AND accommodation IS NOT NULL",
            (key,)).fetchone()
        return (round(row[0], 1) if row[0] is not None else None), row[1]

    def add_hidden_nut(self, item: str, nuts: str, note: str = "", restaurant_name: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO hidden_nuts (item, nuts, note, restaurant_key, source, created) VALUES (?,?,?,?,'community',?)",
            (item.strip().lower(), nuts.strip().lower(), note.strip(),
             restaurant_key(restaurant_name) if restaurant_name else None, now()))
        self.conn.commit()
        return cur.lastrowid

    def hidden_nuts(self) -> list[dict]:
        return self._rows("SELECT * FROM hidden_nuts ORDER BY source DESC, created DESC")
