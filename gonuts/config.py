"""Settings and API key loading.

Keys are looked up in this order:
  1. a .env file in this repo's folder
  2. a .env file in the folder ABOVE this repo (where the teaching staff keep theirs)
  3. Streamlit secrets (used when the app is hosted online)
"""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_DIR = Path(__file__).resolve().parent.parent

# The only model this app is allowed to use (course rule).
MODEL = "gpt-6-luna"

# gpt-6-luna price per 1 million tokens in US dollars (standard tier, prompts under 272K tokens).
# Source: published API pricing as reported by eesel.ai and anotherwrapper.com, October 2026.
# Check against OpenAI's pricing page or your Portkey dashboard before quoting in the report.
PRICE_INPUT_PER_M: float | None = 0.10
PRICE_CACHED_INPUT_PER_M: float | None = 0.01
PRICE_OUTPUT_PER_M: float | None = 0.50

# The city we start with.
DEFAULT_CITY = "New Haven, CT"
DEFAULT_CENTER = (41.3083, -72.9279)  # New Haven Green

# ---- Spending guards
MAX_MENU_CHARS = 15_000            # longer menus are cut off before they reach the model
MAX_OUTPUT_TOKENS = 8_000          # per model call (counts hidden reasoning tokens too)
# Reasoning per agent. Measured Oct 19 on a 5,958-char piece of a real menu: default reasoning used
# 5,493 output tokens (2,133 hidden reasoning) in 39.6 s; "none" used 3,248 in 24.6 s with a
# similar answer. The Verifier's plain-code nut scan backs up the Analyst, and can only raise risk.
REASONING_EFFORT = {"analyst": "none", "analyst:recheck": "none"}
MODEL_TIMEOUT_SECONDS = 90         # give up on a stalled model call (the SDK retries once)
SESSION_TOKEN_BUDGET = 150_000     # per browser session, across all agents
DAILY_TOKEN_BUDGET = 2_000_000     # whole app, per UTC day (protects the shared key)
MAX_RESTAURANTS_PER_SEARCH = 5     # menus read per search
MAX_TOOL_ROUNDS = 3                # delegate calls an AI agent may make in one task

# ---- Loop limits (safety rule: nothing retries or re-processes without a cap)
ANALYST_CHUNK_CHARS = 4_000        # ~2,200 answer tokens per piece, well under MAX_OUTPUT_TOKENS
MAX_MENU_CHUNKS = 4                # 4 x 4,000 >= MAX_MENU_CHARS; more pieces are never analyzed
MAX_CUTOFF_SPLITS = 1              # a piece whose answer was cut off is split in half at most once
MAX_RECHECK_ROUNDS = 1             # the Verifier sends unverified dishes back to the Analyst once
MAX_MENU_LINKS = 4                 # menu pages/PDFs followed from a restaurant's homepage
MAX_MENU_IMAGES = 4                # menu pictures on a website read by the model (~2-3K tokens each)
MAX_GONATION_LISTS = 6             # GoNation menu lists tried per restaurant
# MODEL_TIMEOUT_SECONDS above: one stalled call is retried once by the SDK, then gives up

# ---- Delegation guards (any agent may delegate to any other)
MAX_HOPS_PER_RUN = 60              # total hand-offs in one user request
MAX_DELEGATION_DEPTH = 8           # how deep a chain of hand-offs may go

# ---- Cache
CACHE_TTL_DAYS = 14                # re-read a restaurant's website after this many days

# ---- Community
MAX_PHOTO_BYTES = 5_000_000
MAX_MENU_PHOTOS = 4                # pages of menu photos per upload (loop limit; ~2-3K tokens per page)
MAX_PDF_BYTES = 20_000_000          # menu PDFs are often big because of photos
MIN_MENU_CHARS = 300               # less text than this is a JavaScript-only or parked site: skip the model
MAX_POST_CHARS = 1_500

DATA_DIR = REPO_DIR / "data"
DB_PATH = DATA_DIR / "gonuts.db"              # the live database (not committed)
SEED_DB_PATH = REPO_DIR / "seed" / "new_haven.db"  # pre-scanned New Haven restaurants (committed)
PHOTO_DIR = DATA_DIR / "photos"
LOG_DIR = REPO_DIR / "logs"


def load_env() -> str | None:
    """Load .env from the repo folder, then its parent. Return the path that was used."""
    for candidate in (REPO_DIR / ".env", REPO_DIR.parent / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return str(candidate)
    return None


def get_portkey_key() -> str | None:
    load_env()
    key = os.getenv("PORTKEY_API_KEY")
    if key:
        return key
    try:  # hosted on Streamlit Community Cloud
        import streamlit as st
        return st.secrets.get("PORTKEY_API_KEY")
    except Exception:
        return None


def cost_usd(input_tokens: int, cached_input_tokens: int, output_tokens: int) -> float | None:
    if None in (PRICE_INPUT_PER_M, PRICE_CACHED_INPUT_PER_M, PRICE_OUTPUT_PER_M):
        return None
    uncached = input_tokens - cached_input_tokens
    return (uncached * PRICE_INPUT_PER_M + cached_input_tokens * PRICE_CACHED_INPUT_PER_M
            + output_tokens * PRICE_OUTPUT_PER_M) / 1_000_000
