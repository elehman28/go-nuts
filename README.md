# 🥜 Go Nuts

**Live app:** https://go-nuts-mepgzkf6appmyn8z3rqm8ts.streamlit.app/

**Demo video (57 s, narrated):** [report/go-nuts-demo.mp4](report/go-nuts-demo.mp4)

Go Nuts is a team of AI agents that helps people with nut allergies eat out. It reads real
restaurant menus, starting with **New Haven, CT**, and tells you which restaurants have dishes with
no nuts listed, which dishes to avoid (including hidden nuts, like the cashews in most vegan
cheeses), and whether the kitchen says it can handle allergies. Diners share reviews, food photos
and hidden-nut warnings with each other.

Go Nuts never calls a dish "safe." Menus leave out ingredients and kitchen cross-contact, so
always tell your server about your allergy.

## What you can do

- **Find restaurants:** enter a location (New Haven by default), pick restaurants, and get them
  ranked for your allergy profile, with a verdict and questions to ask your server.
- **Browse:** see every restaurant already checked, ranked, for free.
- **Check a menu:** paste a menu link (web page or PDF), upload a photo of a menu, paste the text,
  or try a sample menu.
- **Community:** rate how well a restaurant handled your allergy, post photos of your food, and warn
  others about hidden nuts. Warnings make future menu checks more cautious for everyone.
- **Agent trace:** see every hand-off between agents for your last request.
- **Tokenomics:** real token counts per run and per agent, cache hit rate, and cost at scale.

## The agent team

Any agent can delegate a task to any other. They talk through a shared message bus (`gonuts/team.py`),
which records every hand-off and stops runaway delegation: at most 60 hand-offs per request, chains
at most 8 deep, and no agent may be handed a task identical to one it is already working on.
The two AI agents also get a `delegate` tool that lists every teammate and what it can do.

| Agent | What it does | Uses the model? |
|---|---|---|
| **Finder** | Turns a location into nearby restaurants and their website URLs (OpenStreetMap) | No |
| **Menu Fetcher** | Pulls menu text from a website or PDF (code), or a photo (model) | Photos only |
| **Menu Analyst** | Rates every dish: risk level, nuts, reason, and quoted evidence; notes kitchen allergy policy | Yes |
| **Verifier** | Checks every quote is really on the menu, re-scans for nut words and hidden nuts, blocks prompt injection, screens community posts. Can only make ratings more cautious | No |
| **Summarizer** | Ranks restaurants for your profile and drafts questions for the server | Yes |
| **Cost Control** | Caches every analysis so repeat searches cost nothing; enforces session and daily budgets | No |

All model calls use `gpt-6-luna` through Portkey.

A typical "check a menu" request: Summarizer → Cost Control (cache?) → Menu Fetcher → Menu Analyst
→ Verifier (screen for injection) → Menu Analyst → Verifier (check quotes) → Menu Analyst (re-check
any dish the Verifier couldn't find) → Cost Control (save) → Summarizer (verdict + server questions).

## Run it locally

You need Python 3.10 or newer.

```bash
git clone <this repo's URL>
cd go-nuts
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Add your key. The app looks for a `.env` file **in this folder first, then in the folder above it**:

```bash
cp .env.example .env               # then put your PORTKEY_API_KEY in it
```

Start the app:

```bash
streamlit run app.py
```

It opens at http://localhost:8501. To try it right away, open **Check a menu** and pick a sample menu.
`sample_menus/injection_test.txt` contains a hidden prompt-injection attack, to show the defense working.

## Pre-scanned New Haven data

`seed/new_haven.db` holds New Haven restaurants and their menu analyses, made with `scan_city.py`.
It is committed to the repo. On startup the app copies it into its live database (`data/gonuts.db`),
so the hosted app always has New Haven data, even after a restart. To refresh or extend it:

```bash
python scan_city.py --dry-run      # list New Haven restaurants with websites (no AI calls)
python scan_city.py --max 40       # analyze 40 of them into seed/new_haven.db
python scan_city.py --contacts     # fill in missing phone numbers from restaurant homepages (no AI calls)
```

National chains, store-locator pages and duplicate websites are skipped (add `--include-chains` to keep them).
Phone numbers and addresses come only from OpenStreetMap and restaurants' own websites; missing ones are
shown as "Not listed", never guessed.

Reviews, photos and community warnings are stored in the live database only. On free hosting they
reset when the app restarts.

## Tests

```bash
pytest -v
```

The tests use a fake model, so they are free and need no key. They show the defenses working:
prompt injection removed, a fooled model corrected by the Verifier, invented dishes sent back and
dropped, community warnings raising risk, cache hits costing zero tokens, session and daily budgets
enforced, delegation loops stopped, and the `.env` found in the folder above the repo.

## Files

```
app.py                  the Streamlit interface
scan_city.py            pre-scan a city's restaurants
gonuts/team.py          message bus: any agent can delegate to any other, with guardrails
gonuts/agents/          the six agents
gonuts/llm.py           the one place the model is called; token logging and budgets
gonuts/db.py            SQLite: restaurants, cached analyses, usage, reviews, hidden-nut warnings
gonuts/nuts.py          nut vocabulary and prompt-injection patterns
gonuts/web.py           reads menu web pages and PDFs
gonuts/osm.py           OpenStreetMap lookups
gonuts/config.py        model, prices, budgets, .env loading
sample_menus/           example menus, including a prompt-injection test
tests/                  tests for the agents and defenses
```

Every model call is logged to `logs/usage.jsonl` and the `usage` table in `data/gonuts.db`.
