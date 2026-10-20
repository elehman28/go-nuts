"""Cost Control: caches each restaurant's analysis so repeat searches cost almost nothing.

Every request for a restaurant report goes through here first:
  1. fresh analysis for this restaurant in the database?   -> return it, 0 tokens
  2. read the menu (free); same menu text analyzed before? -> return it, 0 tokens
  3. otherwise ask the Menu Analyst, then save the result and what it cost
It also answers "how much budget is left?" and keeps the numbers for the Tokenomics tab.
"""
import hashlib
import json

from .. import config
from ..db import restaurant_key
from ..team import Agent


def text_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).lower().encode()).hexdigest()[:24]


class CostControl(Agent):
    name = "cost_control"
    title = "Cost Control"
    description = "Caches every analysis so repeat searches cost almost nothing; enforces budgets."
    skills = {
        "get_report": "payload {restaurant, force}. Nut report for a restaurant dict (needs website or menu_url). Cache first.",
        "get_menu_report": "payload {menu_text | url | image_b64+mime | images[], name}. Nut report for one menu "
                           "(images: up to 4 pages of menu photos). Saved under the restaurant's name. Cache first.",
        "recall": "payload {key}. Look up a saved agent answer.",
        "remember": "payload {key, value, tokens}. Save an agent answer for reuse.",
        "budget_status": "payload {}. Tokens used and left this session and today.",
    }

    def _analyze(self, key: str, menu_text: str, name: str, sources: list[str]):
        h = text_hash(menu_text)
        cached = self.db.analysis_by_hash(h)
        if cached:
            self.db.save_analysis(key, h, cached["result"], cached["tokens"])
            self.db.log_cache(key, True, cached["tokens"] or 0)
            return {**cached["result"], "from_cache": True, "cost_tokens": 0, "sources": sources}
        before = self.llm.tracker.total_tokens
        result = self.delegate("analyst", "analyze_menu", menu_text=menu_text, restaurant_name=name)
        tokens = self.llm.tracker.total_tokens - before
        result["sources"] = sources
        if result.get("is_menu"):
            self.db.save_analysis(key, h, result, tokens)
        self.db.log_cache(key, False, 0)
        return {**result, "from_cache": False, "cost_tokens": tokens}

    def get_report(self, restaurant: dict, force: bool = False):
        key = restaurant.get("key") or restaurant_key(restaurant["name"])
        if not force:
            cached = self.db.latest_analysis(key, max_age_days=config.CACHE_TTL_DAYS)
            if cached:
                self.db.log_cache(key, True, cached["tokens"] or 0)
                return {**cached["result"], "from_cache": True, "cost_tokens": 0, "analyzed": cached["created"]}
        url = restaurant.get("menu_url") or restaurant.get("website")
        if not url:
            return {"error": "No website listed for this restaurant."}
        page = self.delegate("fetcher", "fetch_menu", url=url)
        if page.get("phone") and not restaurant.get("phone"):
            self.db.set_phone(key, page["phone"])  # from the restaurant's own website
        return self._analyze(key, page["text"], restaurant["name"], page["sources"])

    def _read_photo(self, image_b64: str, mime: str) -> dict:
        """Transcribe one menu photo, once: the same photo again costs 0 tokens."""
        photo_key = "photo:" + hashlib.sha256(image_b64.encode()).hexdigest()[:24]
        memo = self.db.recall(photo_key)
        if memo:
            return memo["value"]
        before = self.llm.tracker.total_tokens
        page = self.delegate("fetcher", "read_menu_photo", image_b64=image_b64, mime=mime)
        self.db.remember(photo_key, page, self.llm.tracker.total_tokens - before)
        return page

    def get_menu_report(self, menu_text: str = "", url: str = "", image_b64: str = "",
                        mime: str = "image/jpeg", name: str = "", images: list | None = None):
        sources = []
        photos = list(images or []) + ([{"image_b64": image_b64, "mime": mime}] if image_b64 else [])
        if photos:
            # Multi-page menus: up to MAX_MENU_PHOTOS pages, read in order (loop limit).
            pages = [self._read_photo(p["image_b64"], p.get("mime") or "image/jpeg")
                     for p in photos[: config.MAX_MENU_PHOTOS]]
            texts = [p["text"] for p in pages if p.get("is_menu") and p.get("text", "").strip()]
            if not texts:
                return {"is_menu": False, "dishes": [],
                        "summary": "That photo doesn't look like a menu." if len(pages) == 1
                        else "None of those photos look like a menu."}
            menu_text = "\n\n".join(texts)
            skipped = len(pages) - len(texts)
            sources = [f"{len(texts)} menu photo{'s' if len(texts) != 1 else ''} from a diner"
                       + (f" ({skipped} photo{'s' if skipped != 1 else ''} skipped: not a menu)" if skipped else "")]
        elif url:
            page = self.delegate("fetcher", "fetch_menu", url=url)
            menu_text, sources = page["text"], page["sources"]
        else:
            sources = ["pasted text"]
        if not menu_text.strip():
            return {"is_menu": False, "summary": "No menu text to check.", "dishes": []}
        key = restaurant_key(name) if name else "menu-" + text_hash(menu_text)[:10]
        return self._analyze(key, menu_text, name, sources)

    def recall(self, key: str):
        return self.db.recall(key)

    def remember(self, key: str, value, tokens: int = 0):
        self.db.remember(key, value, tokens)
        return {"saved": key}

    def budget_status(self):
        t = self.llm.tracker
        return {"session_used": t.total_tokens, "session_budget": t.budget,
                "today_used": self.db.tokens_today(), "daily_budget": config.DAILY_TOKEN_BUDGET}

    # Used by the Summarizer: cache any model answer by a hash of its input.
    def memo_key(self, agent: str, payload) -> str:
        return agent + ":" + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:24]
