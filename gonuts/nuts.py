"""Nut vocabulary, risk levels, and the prompt-injection guard. Plain code, no model calls."""
import re

RISK_LEVELS = {
    "contains": "Contains nuts",
    "likely": "Likely contains nuts",
    "unclear": "Unclear, ask staff",
    "none_listed": "No nuts listed, still ask staff",
}
RISK_ORDER = ["contains", "likely", "unclear", "none_listed"]  # most to least risky

PEANUT_WORDS = ["peanut", "groundnut"]
TREE_NUT_WORDS = ["almond", "cashew", "walnut", "pecan", "pistachio", "hazelnut", "filbert",
                  "macadamia", "brazil nut", "pine nut", "pignoli", "chestnut"]
NAMED_NUTS = PEANUT_WORDS + TREE_NUT_WORDS + ["nut"]

# Profile choices in the app, and which nut words each one covers.
PROFILE_NUTS = {
    "Peanuts": PEANUT_WORDS,
    "All tree nuts": TREE_NUT_WORDS,
    "Almonds": ["almond"], "Cashews": ["cashew"], "Walnuts": ["walnut"], "Pecans": ["pecan"],
    "Pistachios": ["pistachio"], "Hazelnuts": ["hazelnut", "filbert"], "Macadamias": ["macadamia"],
    "Brazil nuts": ["brazil nut"], "Pine nuts": ["pine nut", "pignoli"], "Coconut": ["coconut"],
}


def word_regex(words) -> re.Pattern:
    """Whole-word match, plural allowed, and not when followed by "-free" ("nut-free")."""
    alts = "|".join(re.escape(w) + r"(e?s)?" for w in sorted(set(words), key=len, reverse=True))
    return re.compile(r"\b(" + alts + r")\b(?![- ]?free)", re.I)


NAMED_RE = word_regex(NAMED_NUTS)


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def quote_in_text(quote: str, text: str) -> bool:
    q = normalize(quote)
    return bool(q) and q in normalize(text)


def dish_matches_profile(dish_nuts: list[str], profile_allergens: list[str]) -> bool:
    """True if the dish's nuts touch the diner's allergens, or if we can't tell which nut it is."""
    if not dish_nuts or not profile_allergens:
        return True
    words = [w for a in profile_allergens for w in PROFILE_NUTS.get(a, [])]
    named = " ".join(dish_nuts).lower()
    leftover = named
    for w in sorted(PEANUT_WORDS + TREE_NUT_WORDS + ["coconut"], key=len, reverse=True):
        leftover = re.sub(re.escape(w) + r"s?", " ", leftover)
    if re.search(r"\bnuts?\b|unknown|unspecified", leftover) or not re.search(r"[a-z]", named):
        return True  # generic "nuts", "tree nuts" or unknown: treat as matching
    return any(w in named for w in words)


# ---------------------------------------------------------------- injection guard

INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|rules|prompts?)",
    r"disregard (all |any )?(the )?(previous|prior|above) ",
    r"\b(system|developer) (prompt|message|instructions?)\b",
    r"\byou are (now )?(an? )?(ai|assistant|chatbot|language model)\b",
    r"\b(ai|assistant|chatbot|llm|language model)s?\b[\w ]{0,20}\b(must|should|please|shall)\b",
    r"\b(mark|label|rate|classify|treat) (every|all|each) (dish|item|meal)",
    r"\b(rate|mark|label) (all|every) (dishes|items|meals)\b",
    r"\bnew instructions?\b",
]
INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.I)


def find_injections(text: str) -> list[str]:
    """Lines that look like instructions written for an AI."""
    return [line.strip() for line in (text or "").splitlines() if INJECTION_RE.search(line)]


def remove_injections(text: str) -> str:
    return "\n".join(
        "[line removed: looked like an instruction to an AI]" if INJECTION_RE.search(line) else line
        for line in (text or "").splitlines()
    )


# ---- Personal information (safety rule: Go Nuts never stores PII)
PII_PATTERNS = {
    "an email address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "a phone number": re.compile(r"(?<!\d)(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"),
    "a street address": re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Ln|Lane|Dr|Drive|Ct|Court)\b\.?"),
    "a social media handle": re.compile(r"(?<![\w@])@[A-Za-z0-9_]{3,}"),
}


def find_pii(text: str) -> list[str]:
    """Kinds of personal information found in text, e.g. ["an email address"]."""
    return [kind for kind, rx in PII_PATTERNS.items() if rx.search(text or "")]
