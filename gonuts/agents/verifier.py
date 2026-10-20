"""Verifier: checks the Analyst's work with plain code. No model calls, so it can't be talked into anything.

- screen_text:      removes lines that try to give the AI instructions (prompt injection)
- verify_analysis:  every evidence quote must really be on the menu; re-scans for nut words the
                    Analyst missed; applies the community hidden-nut list; can only make ratings
                    MORE cautious. Sends unverifiable dishes back to the Analyst once.
- moderate_post:    screens community reviews and warnings before they are saved
- check_answer:     checks a Food Guide chat answer: dishes it names must be on that restaurant's
                    menu, no "safe"/"nut-free" claims, and emergency steps whenever someone says
                    they already ate something or describes a reaction
"""
import re

from .. import config
from ..nuts import (NAMED_RE, find_pii, RISK_LEVELS, RISK_ORDER, find_injections, normalize, quote_in_text,
                    remove_injections, word_regex)
from ..team import Agent

KITCHEN_POLICIES = ("accommodates", "cross_contact_warning", "no_info")
URL_RE = re.compile(r"https?://|www\.", re.I)

# Chat answers: words that promise too much, and signs the diner may be having a reaction now.
SAFE_CLAIM_RE = re.compile(r"\b(?:(?:100\s*%|completely|totally|perfectly|definitely|guaranteed)\s+)?"
                           r"(?:safe|nut[- ]free|allergen[- ]free|peanut[- ]free)\b", re.I)
ALREADY_ATE_RE = re.compile(r"\b(?:i|we|my \w+|he|she|they)\s+(?:just\s+|already\s+)?(?:ate|eaten|had|tried|drank)\b|"
                            r"\b(?:itch\w*|hives|swell\w*|throat|tingl\w*|wheez\w*|vomit\w*|can'?t breathe|"
                            r"trouble breathing|reaction|anaphyla\w*|dizz\w*|rash)\b", re.I)
EMERGENCY_LINE = ("If you have any signs of a reaction (itching, hives, swelling, trouble breathing, vomiting, "
                  "dizziness), use your epinephrine if it's prescribed and call 911 now.")


def dedupe_dishes(dishes: list[dict]) -> list[dict]:
    """One entry per dish name, most cautious first. Restaurants repeat dishes across lunch and
    dinner pages; if the copies disagree, the riskier rating is kept (safety rule: never lower risk)."""
    ordered = sorted(dishes, key=lambda d: (RISK_ORDER.index(d["risk"]), not d.get("verified", False)))
    seen, out = set(), []
    for d in ordered:
        name = normalize(d["name"])
        if name in seen:
            continue
        seen.add(name)
        out.append(d)
    return out


class Verifier(Agent):
    name = "verifier"
    title = "Verifier"
    description = "Checks evidence quotes in code, blocks prompt injection, and screens community posts."
    skills = {
        "screen_text": "payload {text}. Remove lines that try to instruct the AI. Returns {clean_text, removed_lines}.",
        "verify_analysis": "payload {raw, menu_text}. Check an Analyst result against the menu text.",
        "check_nickname": "payload {nickname}. Rejects nicknames with contact details or AI instructions.",
        "moderate_post": "payload {text}. Screen a community review or warning before saving it.",
        "check_answer": "payload {answer, dishes_cited, restaurants, question}. Check a Food Guide chat answer.",
    }

    # ------------------------------------------------------------ prompt injection

    def screen_text(self, text: str):
        return {"clean_text": remove_injections(text).replace("</menu>", ""),
                "removed_lines": find_injections(text)}

    # ------------------------------------------------------------ analysis checks

    def _hidden_lexicon(self) -> list[tuple[re.Pattern, dict]]:
        return [(word_regex([h["item"]]), h) for h in self.db.hidden_nuts()]

    def _check_dish(self, d: dict, menu_text: str, lexicon) -> dict:
        risk = d.get("risk") if d.get("risk") in RISK_LEVELS else "unclear"
        evidence = str(d.get("evidence") or "")
        nuts = [str(n) for n in d.get("nuts") or []]
        notes = []
        verified = quote_in_text(evidence, menu_text) or quote_in_text(str(d["name"]), menu_text)
        if not verified:
            notes.append("Could not find this dish in the menu text. The AI may have invented it.")

        own_text = f"{d['name']} {evidence}"
        named = NAMED_RE.search(own_text)
        if named and risk != "contains":
            notes.append(f"Raised to 'contains': the menu says '{named.group(0)}'.")
            risk = "contains"
            nuts = nuts or [named.group(0).lower()]
        if risk in ("unclear", "none_listed"):
            for pattern, h in lexicon:
                m = pattern.search(own_text)
                if m:
                    who = "Community warning" if h["source"] == "community" else "Hidden-nut list"
                    notes.append(f"Raised to 'likely'. {who}: '{m.group(0)}' often contains {h['nuts']}.")
                    risk = "likely"
                    nuts = nuts or [n.strip() for n in h["nuts"].split(",")]
                    break
        if not verified and risk == "none_listed":
            risk = "unclear"
        return {"name": str(d["name"]), "section": d.get("section"), "risk": risk, "nuts": nuts,
                "evidence": evidence, "reason": str(d.get("reason") or ""), "verified": verified,
                "verifier_notes": notes}

    def verify_analysis(self, raw: dict, menu_text: str):
        lexicon = self._hidden_lexicon()
        dishes = [self._check_dish(d, menu_text, lexicon)
                  for d in raw.get("dishes") or [] if isinstance(d, dict) and d.get("name")]

        # Send unverifiable dishes back to the Analyst, once.
        unverified = [d for d in dishes if not d["verified"]]
        rechecked = 0
        if unverified:
            try:
                fixes = self.delegate("analyst", "recheck_dishes", dishes=unverified, menu_text=menu_text)
            except Exception as e:  # budget or loop guard: keep the cautious flags we have
                fixes = {"dishes": []}
                for d in unverified:
                    d["verifier_notes"].append(f"Re-check skipped: {e}")
            by_name = {normalize(f["name"]): f for f in fixes.get("dishes", [])}
            kept = []
            for d in dishes:
                fix = by_name.get(normalize(d["name"])) if not d["verified"] else None
                if fix and fix.get("not_on_menu"):
                    rechecked += 1
                    continue  # the Analyst agreed it invented this dish: drop it
                if fix:
                    new = self._check_dish(fix, menu_text, lexicon)
                    if new["verified"]:
                        rechecked += 1
                        new["verifier_notes"].insert(0, "Evidence corrected after the Verifier sent it back.")
                        # A re-check may never lower the risk.
                        if RISK_ORDER.index(new["risk"]) > RISK_ORDER.index(d["risk"]):
                            new["risk"] = d["risk"]
                        d = new
                kept.append(d)
            dishes = kept
        dishes = dedupe_dishes(dishes)

        # Nut words on the menu that no flagged dish covers.
        flagged = [d for d in dishes if d["risk"] in ("contains", "likely")]
        covered = normalize(" ".join(d["name"] + " " + d["evidence"] for d in flagged))
        flagged_names = [normalize(d["name"]) for d in flagged]
        missed = []
        for line in menu_text.splitlines():
            line = line.strip()
            if not (NAMED_RE.search(line) or any(p.search(line) for p, _ in lexicon)):
                continue
            norm = normalize(line)
            if norm in covered or any(n and n in norm for n in flagged_names):
                continue
            missed.append(line[:200])

        kitchen_raw = raw.get("kitchen") if isinstance(raw.get("kitchen"), dict) else {}
        statements = [str(s) for s in kitchen_raw.get("statements") or []]
        verified_statements = [s for s in statements if quote_in_text(s, menu_text)]
        policy = kitchen_raw.get("policy") if kitchen_raw.get("policy") in KITCHEN_POLICIES else "no_info"
        if policy != "no_info" and not verified_statements:
            policy = "no_info"  # a policy claim needs a real quote behind it
        shared_fryer = kitchen_raw.get("shared_fryer")
        if re.search(r"shared fryer|same fryer|peanut oil", menu_text, re.I):
            shared_fryer = True

        counts = {level: sum(d["risk"] == level for d in dishes) for level in RISK_LEVELS}
        return {
            "restaurant_name": raw.get("restaurant_name"),
            "is_menu": bool(raw.get("is_menu", True)) and bool(dishes),
            "dishes": dishes,
            "counts": counts,
            "kitchen": {"policy": policy, "statements": verified_statements,
                        "shared_fryer": shared_fryer if isinstance(shared_fryer, bool) else None,
                        "notes": str(kitchen_raw.get("notes") or "")},
            "suspicious_text": [str(s) for s in raw.get("suspicious_text") or []],
            "unflagged_nut_mentions": missed[:20],
            "rechecked_dishes": rechecked,
            "summary": str(raw.get("summary") or ""),
        }

    # ------------------------------------------------------------ community posts

    def moderate_post(self, text: str):
        text = (text or "").strip()
        if len(text) > config.MAX_POST_CHARS:
            return {"ok": False, "reason": f"Please keep posts under {config.MAX_POST_CHARS} characters."}
        if find_injections(text):
            return {"ok": False, "reason": "This post looks like instructions to an AI, so it wasn't saved."}
        if len(URL_RE.findall(text)) > 1:
            return {"ok": False, "reason": "Posts can include at most one link."}
        pii = find_pii(text)
        if pii:
            return {"ok": False, "reason": f"Please remove {pii[0]}. Go Nuts doesn't store personal "
                                           "information about you or anyone else."}
        return {"ok": True, "clean_text": text}

    def check_nickname(self, nickname: str):
        nickname = (nickname or "").strip()
        if len(nickname) > 30:
            return {"ok": False, "reason": "Please keep your nickname under 30 characters."}
        if find_pii(nickname) or find_injections(nickname):
            return {"ok": False, "reason": "Please use a nickname without contact details."}
        return {"ok": True, "nickname": nickname or None}

    # ------------------------------------------------------------ Food Guide answers

    def check_answer(self, answer: str, dishes_cited: list, restaurants: list, question: str = ""):
        """Plain-code checks on a chat answer. Returns the answer to show plus what was changed."""
        notes = []
        on_menu = {}
        for r in restaurants:  # the full saved menu, not just the excerpt the model saw
            saved = self.db.latest_analysis(r["key"])
            on_menu[r["key"]] = {normalize(d["name"]) for d in (saved["result"].get("dishes", []) if saved else [])}
        verified, unverified = [], []
        for c in dishes_cited if isinstance(dishes_cited, list) else []:
            if not isinstance(c, dict):
                continue
            key, dish = str(c.get("restaurant_key") or ""), str(c.get("dish") or "")
            (verified if dish and normalize(dish) in on_menu.get(key, set()) else unverified).append(
                {"restaurant_key": key, "dish": dish})
        if unverified:
            names = ", ".join(sorted({u["dish"] for u in unverified if u["dish"]}))[:200]
            answer += f"\n\n(Go Nuts couldn't find {names} on that menu, so treat it as unconfirmed.)"
            notes.append("unverified dishes flagged")
        def reword(m):
            before = answer[max(0, m.start() - 30):m.start()].lower()
            if re.search(r"\b(?:not|never|no|isn't|aren't|can't|cannot|can never)\b[^.]*$", before):
                return m.group(0)  # "never call food safe", "can't be guaranteed nut-free": keep
            return "lower-risk (still ask staff)" if m.group(0).lower().endswith("safe") else "listed without nuts (still ask staff)"

        softened = SAFE_CLAIM_RE.sub(reword, answer)
        if softened != answer:
            notes.append("safety claim reworded")
            answer = softened
        if ALREADY_ATE_RE.search(question):
            # Emergency steps always come first, in the same words every time.
            rest = re.sub(r"[^.!?\n]*911[^.!?\n]*[.!?]?[ \t]*", "", answer)  # drop the model's own version
            answer = EMERGENCY_LINE + "\n\n" + rest
            notes.append("emergency steps put first")
        return {"answer": answer.strip(), "verified_dishes": verified, "unverified_dishes": unverified, "notes": notes}
