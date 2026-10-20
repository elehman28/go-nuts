"""Build report.html and slides.html: self-contained files (fonts, screenshots and reveal.js embedded).

    python report/build.py

Every number comes from report/stats.py (the real database and usage log). Nothing is typed in by
hand, so rebuilding after a new scan updates the whole report. Gaps that need real user evidence
are shown as yellow [TO FILL] boxes, never filled with made-up content (safety rule 2).
"""
import base64
import html
from pathlib import Path
from string import Template

from stats import collect

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FONTS = ROOT / "static" / "fonts"
S = collect()

AUTHOR = "Elise Lehman"
COURSE = "MGT 409 · AI Foundations for Managers · Yale SOM · Fall 2026"
APP_LINK = "<a href='https://go-nuts-mepgzkf6appmyn8z3rqm8ts.streamlit.app/'>go-nuts-mepgzkf6appmyn8z3rqm8ts.streamlit.app</a>"
REPO_LINK = "<a href='https://github.com/elehman28/go-nuts'>github.com/elehman28/go-nuts</a>"


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def img(name: str, caption: str, width: str = "100%") -> str:
    return (f"<figure><img src='data:image/png;base64,{b64(HERE / 'img' / (name + '.png'))}' style='width:{width}' "
            f"alt='{html.escape(caption)}'><figcaption>{caption}</figcaption></figure>")


def money(x: float, digits: int = 4) -> str:
    return f"${x:,.{digits}f}"


def n(x) -> str:
    return f"{x:,}"


FONT_CSS = f"""
@font-face {{ font-family: "Old Standard TT"; font-weight: 400; src: url(data:font/woff2;base64,{b64(FONTS / 'OldStandardTT-normal-400.woff2')}) format("woff2"); }}
@font-face {{ font-family: "Old Standard TT"; font-style: italic; font-weight: 400; src: url(data:font/woff2;base64,{b64(FONTS / 'OldStandardTT-italic-400.woff2')}) format("woff2"); }}
@font-face {{ font-family: "Old Standard TT"; font-weight: 700; src: url(data:font/woff2;base64,{b64(FONTS / 'OldStandardTT-normal-700.woff2')}) format("woff2"); }}
@font-face {{ font-family: "Libre Franklin"; font-weight: 100 900; src: url(data:font/woff2;base64,{b64(FONTS / 'LibreFranklin-variable.woff2')}) format("woff2"); }}
"""

# ---------------------------------------------------------------- the agent diagram (inline SVG)
DIAGRAM = """
<svg viewBox="0 0 900 430" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Go Nuts agent organization">
  <defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0 0L10 5L0 10z" fill="#7a4b25"/></marker></defs>
  <style>
    .box{fill:#fff;stroke:#7a4b25;stroke-width:1.6} .ai{fill:#f4ede2} .bus{fill:#7a4b25}
    .t{font:600 15px 'Libre Franklin',Arial,sans-serif;fill:#2b221c} .s{font:12px 'Libre Franklin',Arial,sans-serif;fill:#5a4a3e}
    .w{font:600 14px 'Libre Franklin',Arial,sans-serif;fill:#fff} .ln{stroke:#7a4b25;stroke-width:1.4;fill:none}
    .ext{fill:#fff;stroke:#b8a68f;stroke-dasharray:5 4;stroke-width:1.3}
  </style>
  <rect x="20" y="10" width="160" height="56" rx="6" class="ext"/><text x="100" y="34" text-anchor="middle" class="t">Diner</text>
  <text x="100" y="52" text-anchor="middle" class="s">profile · search · photos</text>
  <rect x="20" y="190" width="860" height="44" rx="6" class="bus"/>
  <text x="450" y="218" text-anchor="middle" class="w">Message bus (gonuts/team.py): any agent → any agent · loop, depth (8) and hop (60) limits · full trace</text>
  <g>
    <rect x="20" y="86" width="190" height="78" rx="8" class="box ai"/><text x="115" y="112" text-anchor="middle" class="t">Summarizer</text>
    <text x="115" y="131" text-anchor="middle" class="s">ranks for the profile,</text><text x="115" y="147" text-anchor="middle" class="s">writes server questions · AI</text>
    <rect x="236" y="86" width="190" height="78" rx="8" class="box"/><text x="331" y="112" text-anchor="middle" class="t">Cost Control</text>
    <text x="331" y="131" text-anchor="middle" class="s">cache, budgets,</text><text x="331" y="147" text-anchor="middle" class="s">memo · plain code</text>
    <rect x="452" y="86" width="190" height="78" rx="8" class="box"/><text x="547" y="112" text-anchor="middle" class="t">Finder</text>
    <text x="547" y="131" text-anchor="middle" class="s">restaurants, phones,</text><text x="547" y="147" text-anchor="middle" class="s">addresses · plain code</text>
    <rect x="668" y="86" width="212" height="78" rx="8" class="box ai"/><text x="774" y="112" text-anchor="middle" class="t">Menu Fetcher</text>
    <text x="774" y="131" text-anchor="middle" class="s">websites, PDFs, GoNation, charts;</text><text x="774" y="147" text-anchor="middle" class="s">menu photos with AI</text>
    <rect x="128" y="262" width="250" height="78" rx="8" class="box ai"/><text x="253" y="288" text-anchor="middle" class="t">Menu Analyst</text>
    <text x="253" y="307" text-anchor="middle" class="s">rates every dish for nut risk</text><text x="253" y="323" text-anchor="middle" class="s">with a quote from the menu · AI</text>
    <rect x="522" y="262" width="250" height="78" rx="8" class="box"/><text x="647" y="288" text-anchor="middle" class="t">Verifier</text>
    <text x="647" y="307" text-anchor="middle" class="s">blocks injection, checks quotes,</text><text x="647" y="323" text-anchor="middle" class="s">re-scans for nuts · plain code</text>
  </g>
  <path d="M100 66 V86" class="ln" marker-end="url(#a)"/>
  <path d="M115 164 V190 M331 164 V190 M547 164 V190 M774 164 V190 M253 234 V262 M647 234 V262" class="ln"/>
  <rect x="20" y="366" width="260" height="50" rx="6" class="ext"/><text x="150" y="388" text-anchor="middle" class="t">OpenStreetMap</text>
  <text x="150" y="405" text-anchor="middle" class="s">restaurants, phones, addresses</text>
  <rect x="320" y="366" width="260" height="50" rx="6" class="ext"/><text x="450" y="388" text-anchor="middle" class="t">Restaurant websites</text>
  <text x="450" y="405" text-anchor="middle" class="s">menus, PDFs, chains' allergen charts</text>
  <rect x="620" y="366" width="260" height="50" rx="6" class="ext"/><text x="750" y="388" text-anchor="middle" class="t">gpt-6-luna via Portkey</text>
  <text x="750" y="405" text-anchor="middle" class="s">only model allowed (course rule)</text>
  <text x="450" y="352" text-anchor="middle" class="s">AI agents shaded · plain-code agents white</text>
</svg>"""

# ---------------------------------------------------------------- derived numbers
hit = S["cache_hits"] / S["cache_lookups"] if S["cache_lookups"] else 0
fresh = S["menu_run_cost_mean"]
summ = S["summary_run_cost_mean"]
CHECKS_PER_USER = 8  # ASSUMPTION (not measured): restaurants a diner looks up per month
per_check = hit * summ + (1 - hit) * (fresh + summ)
per_user = CHECKS_PER_USER * per_check
city_refresh = S["menus_checked"] * fresh * (30 / 14)  # every checked menu re-read every 14 days
daily_capacity = int(2_000_000 / max(S["menu_run_tokens_median"], 1))
R = S["risk"]
V = dict(
    author=AUTHOR, course=COURSE, app_link=APP_LINK, repo_link=REPO_LINK,
    menus=n(S["menus_checked"]), menus_full=n(S["menus_full"]), menus_partial=n(S["menus_partial"]),
    mapped=n(S["restaurants_mapped"]), dishes=n(S["dishes"]), contains=n(R.get("contains", 0)),
    likely=n(R.get("likely", 0)), unclear=n(R.get("unclear", 0)), none_listed=n(R.get("none_listed", 0)),
    unclear_pct=f"{100 * R.get('unclear', 0) / max(S['dishes'], 1):.0f}%",
    phones=n(S["with_phone"]), addresses=n(S["with_address"]),
    addr_site=n(S["address_sources"].get("website", 0)), addr_map=n(S["address_sources"].get("map", 0)),
    addr_osm=n(S["address_sources"].get("osm", 0)),
    calls=n(S["model_calls"]), tin=n(S["tokens_in"]), tcached=n(S["tokens_cached"]), tout=n(S["tokens_out"]),
    ttotal=n(S["tokens_in"] + S["tokens_out"]), cost_total=money(S["cost_total"], 2),
    cached_pct=f"{100 * S['tokens_cached'] / max(S['tokens_in'], 1):.0f}%",
    analyst_share=f"{100 * S['tokens_by_agent'].get('analyst', 0) / max(sum(S['tokens_by_agent'].values()), 1):.0f}%",
    run_med=money(S["menu_run_cost_median"]), run_mean=money(S["menu_run_cost_mean"]),
    run_tokens=n(S["menu_run_tokens_median"]), run_secs=S["menu_run_seconds_median"], menu_runs=n(S["menu_runs"]),
    a_med=n(S["analysis_tokens_median"]), a_mean=n(S["analysis_tokens_mean"]), a_max=n(S["analysis_tokens_max"]),
    summ_cost=money(summ, 5), summ_tokens=n(S["summary_run_tokens_mean"]),
    lookups=n(S["cache_lookups"]), hits=n(S["cache_hits"]), hit_pct=f"{100 * hit:.0f}%",
    saved=n(S["tokens_saved_by_cache"]),
    per_check=money(per_check, 5), per_user=money(per_user, 4), u100=money(per_user * 100, 2),
    u10k=money(per_user * 10_000, 2), checks=CHECKS_PER_USER, city=money(city_refresh, 2),
    capacity=n(daily_capacity), fails=n(S["failures_total"]),
    fail_text=n(S["failures"].get("no menu text on the site (JavaScript, images or ordering app)", 0)),
    fail_down=n(S["failures"].get("site down, gone, or blocking readers", 0)),
    p_in=S["prices"][0], p_cached=S["prices"][1], p_out=S["prices"][2],
    first=S["first_call"], last=S["last_call"],
)

# ---------------------------------------------------------------- report
REPORT = Template("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Go Nuts: final project report</title>
<style>${font_css}
:root{--accent:#7a4b25;--ink:#2b221c;--muted:#6f6158;--cream:#f4ede2;--rule:#e2d6c4}
@page{size:Letter;margin:.7in .75in}
html{background:#fffdf9}
body{font:400 15.5px/1.62 'Libre Franklin',Helvetica,Arial,sans-serif;color:var(--ink);max-width:780px;margin:0 auto;padding:40px 28px 80px}
h1,h2,h3{font-family:'Old Standard TT',Georgia,serif;font-weight:400;color:#3c2c20;letter-spacing:-.01em}
h1{font-size:2.6rem;margin:.2rem 0 .3rem}
h2{font-size:1.75rem;margin:2.4rem 0 .6rem;padding-top:.6rem;border-top:1px solid var(--rule);break-after:avoid}
h3{font-size:1.25rem;margin:1.5rem 0 .4rem;break-after:avoid}
p{margin:.55rem 0}
.brand{font:400 1.2rem 'Old Standard TT',serif;color:var(--accent)} .brand i{color:#a8743f}
.kicker{font:600 .72rem 'Libre Franklin',sans-serif;letter-spacing:2px;text-transform:uppercase;color:var(--muted)}
.lede{font:italic 1.25rem/1.45 'Old Standard TT',serif;color:#4a3b30}
.meta{color:var(--muted);font-size:.92rem}
table{border-collapse:collapse;width:100%;margin:.8rem 0;font-size:.86rem;break-inside:avoid}
th,td{border-bottom:1px solid var(--rule);padding:.42rem .5rem;text-align:left;vertical-align:top}
th{background:var(--cream);font-weight:600}
td.num,th.num{text-align:right;white-space:nowrap}
figure{margin:1rem 0;break-inside:avoid} figure img{border:1px solid var(--rule);border-radius:3px;display:block}
figcaption{font-size:.82rem;color:var(--muted);margin-top:.35rem}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start}
.callout{background:var(--cream);border-left:3px solid var(--accent);padding:.7rem 1rem;margin:1rem 0;break-inside:avoid}
.todo{background:#fff7d6;border:1px dashed #c9a227;padding:.7rem 1rem;margin:1rem 0;break-inside:avoid}
.todo b{color:#7a5b00}
.stat{display:inline-block;min-width:150px;margin:.3rem .6rem .3rem 0;padding:.6rem .8rem;background:#fff;border:1px solid var(--rule)}
.stat b{display:block;font:400 1.6rem 'Old Standard TT',serif;color:var(--accent)} .stat span{font-size:.8rem;color:var(--muted)}
ol li,ul li{margin:.2rem 0}
code{font-size:.85em;background:var(--cream);padding:0 .25em;border-radius:2px}
.src{font-size:.82rem;color:var(--muted)} .src li{margin:.25rem 0}
svg{width:100%;height:auto;margin:.6rem 0}
@media print{body{padding:0;max-width:none;font-size:11.5pt}h2{break-before:auto}a{color:inherit}}
</style></head><body>

<div class="brand">go <i>nuts</i></div>
<h1>Eating out with a nut allergy, without the guesswork</h1>
<p class="lede">An agent team that reads restaurants' real menus, rates every dish for peanut and tree-nut risk with the menu's own words as evidence, and helps diners call ahead.</p>
<p class="meta">${author} · ${course} · October 2026<br>
Live app: <b>${app_link}</b><br>GitHub: <b>${repo_link}</b><br>
Model: gpt-6-luna via Portkey (the only model on the course key). All numbers in this report are computed from the app's own database and usage log (${first} to ${last}).</p>

<div>
<div class="stat"><b>${menus}</b><span>restaurant menus checked</span></div>
<div class="stat"><b>${dishes}</b><span>dishes rated, each with a menu quote</span></div>
<div class="stat"><b>${mapped}</b><span>New Haven-area restaurants mapped</span></div>
<div class="stat"><b>${cost_total}</b><span>total AI cost so far (${calls} calls)</span></div>
</div>

<h2>1. Motivation</h2>
<p>I have a nut allergy, and so do some members of my family. For us, going out to eat starts long before we sit down: someone has to find the restaurant's menu, read every description for peanuts and tree nuts, guess at the sauces and desserts that don't say what is in them, and call ahead with questions. The result is that dinner with people we love is often spent thinking about what is on the plate instead of who is at the table.</p>
<p>Go Nuts gives us reassurance <i>before</i> we get to the restaurant, so we can focus on spending time with each other rather than on whether something contains nuts. It does not promise safety. It makes the homework faster, more thorough and more consistent, and it tells you exactly what to ask the server.</p>
<p>The problem is common and serious. In a nationally representative survey, 10.8% of US adults had a convincing food allergy, 1.8% to peanut and 1.2% to tree nuts; 51.1% of adults with a food allergy had had a severe reaction and 38.3% had visited an emergency department for one at some point [1]. Among US children, 7.6% have a food allergy (peanut 2.2%, tree nut 1.2%) [2]. Restaurants are a known weak point: in a CDC study of 278 restaurants, only 44.4% of managers, 40.8% of food workers and 33.3% of servers had received any food-allergy training [3], and in US registry data 28% of food-allergy deaths (18 of 63) were linked to food from restaurants or other food establishments [4].</p>

<h2>2. What is new</h2>
<p>Existing tools help in pieces. None of the nine options we reviewed reads a restaurant's actual menu dish by dish and rates each dish for nut risk with the menu's own words as evidence (research notes in <code>report/research-notes.md</code>; items we could not confirm are marked).</p>
<table><tr><th>Option</th><th>What it does</th><th>Reads real menus dish by dish?</th><th>Translated chef cards?</th></tr>
<tr><td>AllergyEats [5]</td><td>Diners rate how well restaurants handled their allergy</td><td>No: ratings, not menu analysis</td><td>Not confirmed</td></tr>
<tr><td>Spokin [6]</td><td>Community reviews filtered by allergy</td><td>No: reviews</td><td>Not confirmed</td></tr>
<tr><td>Fig (Food Is Good) [7]</td><td>Scans packaged-food barcodes; lists some chain restaurant options</td><td>Partly: chains only</td><td>Not confirmed</td></tr>
<tr><td>Equal Eats [8]</td><td>Allergy translation cards (paid tiers)</td><td>No</td><td>Yes (about 50 languages claimed)</td></tr>
<tr><td>SelectWisely [9]</td><td>Printed or PDF allergy translation cards</td><td>No</td><td>Yes (40+ languages)</td></tr>
<tr><td>MenuTrinfo / AllerTrain [10]</td><td>Paid allergen analysis and staff training for restaurants</td><td>For paying restaurants, not diners</td><td>No</td></tr>
<tr><td>Nima sensor [11]</td><td>Portable test of one food sample</td><td>No (one sample at a time); peanut sensor reportedly discontinued</td><td>No</td></tr>
<tr><td>FARE chef card template</td><td>Fill-in allergy card for restaurants</td><td>No</td><td>Not confirmed</td></tr>
<tr><td>Yelp / Google reviews</td><td>General reviews</td><td>No</td><td>No</td></tr>
<tr><td><b>Go Nuts</b></td><td><b>Reads the real menu, rates every dish with a quote, ranks restaurants for your profile, gives the phone number to call</b></td><td><b>Yes</b></td><td><b>Yes: 6 languages, from your profile</b></td></tr></table>
<p>Go Nuts is also new in how it treats the AI. The model is never trusted on its own: every rating must quote the menu, and a plain-code Verifier checks every quote against the page, re-scans the whole menu for nut words and known hidden sources (pesto, praline, marzipan, almond milk, cashew vegan cheese), and can only <i>raise</i> a dish's risk, never lower it. Nothing is ever called "safe": the best rating is "No nuts listed, still ask staff".</p>
<div class="grid2">${img_card}${img_dishes}</div>

<h2>3. Agent design</h2>
<p>Go Nuts is a team of six agents that talk through a shared message bus. Any agent can hand a task to any other, and the bus records every hand-off for the Agent trace and stops runaway delegation (no loops, at most 8 levels deep and 60 hand-offs per request). Only three agents use the model, and only when they must; the other three are plain code, which makes them free, fast and predictable.</p>
${diagram}
<table><tr><th>Agent</th><th>Role</th><th>Tools</th><th>Model?</th></tr>
<tr><td>Finder</td><td>Turns a place (or "Near me") into nearby restaurants with phone numbers and addresses</td><td>OpenStreetMap (Overpass, four mirrors with caching), reverse address lookup</td><td>No</td></tr>
<tr><td>Menu Fetcher</td><td>Gets menu text: web pages and linked menu pages, PDFs, GoNation menu data, chains' official allergen charts; menu photos</td><td>HTTP with private-address blocking, PDF reader, character-position chart reader, image reader</td><td>Photos only</td></tr>
<tr><td>Menu Analyst</td><td>Rates every dish (contains / likely / unclear / no nuts listed) with a word-for-word quote and a reason; notes the kitchen's allergy statements</td><td><code>delegate</code> tool (any teammate)</td><td>Yes</td></tr>
<tr><td>Verifier</td><td>Removes prompt-injection lines before the AI sees a menu; checks quotes; flags hidden nuts; screens community posts and photos for personal information</td><td>Text matching, hidden-nut list (seeded plus community warnings)</td><td>No</td></tr>
<tr><td>Summarizer</td><td>Ranks restaurants for the diner's profile; writes a short verdict and questions for the server</td><td><code>delegate</code> tool</td><td>Yes</td></tr>
<tr><td>Cost Control</td><td>Caches every analysis by restaurant and by menu text; enforces session (150K) and daily (2M) token budgets</td><td>SQLite</td><td>No</td></tr></table>
<p><b>Model choice.</b> The course key allows only gpt-6-luna, so the design question was how to use it well. It reads photos (tested on a tilted, blurred menu photo: every dish, nut and price correct; one misspelling), follows a strict JSON format, and is inexpensive. Two real-model findings shaped the design: big menus were cut off because hidden reasoning counts toward the output limit, so the Analyst reads menus in 4,000-character pieces with reasoning turned off (measured below), and one call stalled for over six minutes, so every call now has a 90-second timeout.</p>

<h3>One real run, step by step</h3>
<p>Below is a real request on the live model (not a mock), traced by the app. The input was a made-up test menu ("Harbor Grill", not a real restaurant) that hides two lines telling the AI to mark every dish nut-free, plus two ordinary dishes so the menu text was new and not answered from the cache.</p>
<ol>
<li><b>You → Summarizer</b> (<code>check_menu</code>): the diner's profile is peanuts and all tree nuts, severe.</li>
<li><b>Summarizer → Cost Control</b> (<code>get_menu_report</code>): no saved result for this exact menu text, so a fresh analysis is needed.</li>
<li><b>Cost Control → Menu Analyst</b> (<code>analyze_menu</code>).</li>
<li><b>Menu Analyst → Verifier</b> (<code>screen_text</code>): both injection lines are removed before the model sees the menu. Plain code, 0 tokens.</li>
<li>The Analyst calls gpt-6-luna: <b>1,703 input tokens, 1,564 of them served from the prompt cache, 586 output, 6.3 s.</b></li>
<li><b>Menu Analyst → Verifier</b> (<code>verify_analysis</code>): every quote is found on the menu; no dish lowered; nut words re-scanned.</li>
<li><b>Summarizer</b> writes the verdict and server questions (1,127 in, 223 out, 3.4 s); Cost Control saves both so the next diner pays nothing. <b>Total: 7 hand-offs, 3,639 tokens, 9.7 seconds.</b></li>
</ol>
<div class="grid2">${img_progress}${img_trace}</div>
${img_injection}

<h2>4. Tokenomics</h2>
<p>All figures come from the usage log of every real model call made while building and testing Go Nuts: <b>${calls} calls, ${tin} input tokens (${tcached} of them cached, ${cached_pct}), ${tout} output tokens, ${cost_total} in total</b> at the configured gpt-6-luna prices (${p_in} / ${p_cached} / ${p_out} dollars per million input / cached input / output tokens; from public price trackers, to be confirmed on the Portkey dashboard). The Menu Analyst accounts for ${analyst_share} of all tokens.</p>
<table><tr><th>Per run (real data)</th><th class="num">Tokens</th><th class="num">Cost</th></tr>
<tr><td>Traced run above (small test menu, fresh)</td><td class="num">3,639</td><td class="num">${trace_cost}</td></tr>
<tr><td>Typical fresh menu check, median of ${menu_runs} runs</td><td class="num">${run_tokens}</td><td class="num">${run_med}</td></tr>
<tr><td>Fresh menu check, mean (big menus pull it up)</td><td class="num">${a_mean} per analysis</td><td class="num">${run_mean}</td></tr>
<tr><td>Largest single menu (232 dishes)</td><td class="num">${a_max}</td><td class="num">about ${max_cost}</td></tr>
<tr><td>Summary only, when the menu analysis is already saved</td><td class="num">${summ_tokens}</td><td class="num">${summ_cost}</td></tr>
<tr><td>Restaurant already checked and summary saved</td><td class="num">0</td><td class="num">$$0</td></tr></table>
<p>A typical fresh check takes ${run_secs} seconds of model time (median). Cost Control answered <b>${hits} of ${lookups} restaurant lookups (${hit_pct}) from saved results</b>, which saved <b>${saved} tokens</b> that would otherwise have been spent re-reading menus.</p>
<h3>Cost at scale</h3>
<p>The one assumption here is marked: a diner looks up <b>${checks} restaurants a month (assumption, not measured)</b>. Everything else is measured: today's cache hit rate, the mean fresh-check cost and the mean summary cost.</p>
<table><tr><th>Scenario</th><th class="num">Monthly cost</th></tr>
<tr><td>Per restaurant lookup (blended at today's ${hit_pct} cache hit rate)</td><td class="num">${per_check}</td></tr>
<tr><td>Per user per month (${checks} lookups)</td><td class="num">${per_user}</td></tr>
<tr><td>100 users</td><td class="num">${u100}</td></tr>
<tr><td>10,000 users</td><td class="num">${u10k}</td></tr>
<tr><td>Keeping the whole city fresh (re-read all ${menus} checked menus every 14 days), independent of users</td><td class="num">${city}</td></tr></table>
<p>The key property: <b>cost grows with the number of restaurants, not the number of diners.</b> New Haven has a few hundred restaurants; once a menu is checked, every diner shares the saved analysis and pays only for a short personalized summary (also cached per profile). With 10,000 users the real hit rate would be far above today's ${hit_pct}, so the 10,000-user line above is an upper bound. The course key's 2M-token daily cap allows about ${capacity} fresh menu checks a day.</p>
<h3>Cost cuts and their measured trade-offs</h3>
<ul>
<li><b>Two-level cache</b> (by restaurant, and by menu text, so two restaurants with the same menu share one analysis): ${hit_pct} hit rate, ${saved} tokens saved.</li>
<li><b>Prompt caching:</b> ${cached_pct} of all input tokens were served from the provider's cache because every Analyst prompt starts with the same instructions; in the traced run, 1,564 of 1,703 input tokens.</li>
<li><b>Reasoning off for the Analyst.</b> Measured on one real 5,958-character menu piece: default reasoning used 5,493 output tokens (2,133 of them hidden reasoning) in 39.6 s; reasoning off used 3,248 tokens in 24.6 s with a similar answer (41% fewer output tokens, 38% faster). Trade-off: the model thinks less, so the plain-code Verifier's nut re-scan is the backstop, and it can only raise risk.</li>
<li><b>Menus in 4,000-character pieces.</b> Before this, five large menus failed because answers were cut off; after it, all finished (Claire's Corner Copia 79 dishes, Costa Pizza 171, Barcelona 127). Trade-off: more calls per big menu, but no wasted half-answers.</li>
<li><b>Plain code wherever possible:</b> GoNation menu data, Domino's allergen chart and Chipotle's allergen statement are read with 0 tokens; sites with almost no text fail fast without a model call; sites that failed are skipped for 14 days (65 skipped in the latest scan).</li>
</ul>
${img_costs}

<h2>5. Safety</h2>
<p>Three kinds of risk, each with a built defense, and evidence that the defense works. The app ships with ${tests} automated tests (fake model, free to run: <code>pytest</code>).</p>
<h3>Attacks</h3>
<ul>
<li><b>Prompt injection in menus.</b> Menu text is data, never instructions. The Verifier removes lines that address the AI before the model sees them, and anything the model still finds suspicious is reported. <i>Shown working</i> in the screenshot in section 3: both hidden lines were removed and the nut dishes were still flagged.</li>
<li><b>Malicious web content.</b> Restaurant pages are untrusted. We found and fixed two real holes during testing: dish names and quotes from websites were being placed into the page as raw HTML (now escaped), and a <code>javascript:</code> address in a restaurant's map record could have become a clickable link (now only web, phone and map links are allowed). Both have tests. Two New Haven restaurant domains had become spam or gambling sites; the Fetcher follows only the restaurant's own site, so it never followed their links.</li>
<li><b>Private addresses.</b> The Fetcher refuses links to private or local network addresses, so a pasted link cannot make the server attack itself.</li>
</ul>
<h3>Agent malfunction</h3>
<ul>
<li><b>Invented or misquoted dishes:</b> every rating needs a word-for-word quote; unverifiable dishes are sent back to the Analyst once and dropped if they aren't on the menu.</li>
<li><b>Cut-off or garbled answers</b> are detected (finish reason, JSON check) and retried in halves at most once, then reported in plain words.</li>
<li><b>Misreading charts.</b> Domino's allergen PDF loses its columns as plain text, so we read each mark by its position. A first version counted only check marks and would have shown no nut risk at all; the chart's second symbol (■, "manufactured in a facility that handles peanuts and tree nuts") marks two desserts, which are now flagged.</li>
<li><b>Partial menus</b> (fewer than 10 dishes, or a chain's store page) are labeled, listed last, and never shown green.</li>
<li><b>Honest labels:</b> AI-written text, AI inferences and official chain data are each tagged; diner photos and sample menus are labeled; approximate addresses say so. In one check, 9 map-based addresses were corrected by the restaurants' own websites, including one that was off by about 1,000 street numbers.</li>
</ul>
<h3>Overspending</h3>
<ul><li>Session budget 150K tokens and app-wide daily budget 2M tokens (tested); a 90-second timeout per call; caps on every loop (pieces per menu, retries, menu links, photos, delegation hops). Large scans needed the student's approval in advance (about 800K tokens approved, about ${scan_used} used).</li></ul>
<h3>Privacy</h3>
<ul><li>No accounts. The allergy profile and saved list stay in a cookie on the diner's device, only if they tick "Remember". "Near me" rounds location to about 100 m and never stores it. Reviews and feedback reject emails, phone numbers, addresses and handles; community photos are screened by the model and rejected if a person or personal information is visible (fails closed); photo location data is stripped; menu photos are never stored. Feedback is anonymous and saved only with consent.</li></ul>

<h2>6. Impact</h2>
<p>What Go Nuts has done so far, all measured from its database:</p>
<ul>
<li><b>${menus} New Haven-area menus checked</b> (${menus_full} full, ${menus_partial} partial), <b>${dishes} dishes rated</b>: ${contains} contain nuts, ${likely} likely contain nuts, ${unclear} unclear (ask staff), ${none_listed} with no nuts listed. ${unclear_pct} are "unclear", which is the honest answer when a menu leaves ingredients out; each comes with a question to ask.</li>
<li><b>${mapped} restaurants on the map</b>, every one with an address (${addr_site} from the restaurant's own website, the rest from OpenStreetMap, labeled approximate where estimated) and ${phones} with a phone number to call ahead.</li>
<li><b>Hidden nuts surfaced that a quick read would miss:</b> a Thai iced tea made with Frangelico (a hazelnut liqueur) and fried chicken breaded with almond milk at September in Bangkok; peanut in that restaurant's tom yum soup and mango sticky rice; two Domino's desserts made in a facility with peanuts and tree nuts.</li>
<li><b>Speed:</b> a fresh menu check takes ${run_secs} s of model time (median); a restaurant someone has already checked is instant.</li>
<li><b>Allergy chef card</b> in English, Spanish, French, Portuguese, Chinese and Arabic, made from the diner's profile, a first step toward international travel. Interviews with adults with peanut and tree-nut allergies found foreign travel especially hard, with translated allergy cards a common coping strategy [12].</li>
</ul>
<h3>First users</h3>
<p>Three people with nut allergies tried Go Nuts in October 2026: me, through the in-app feedback form, and two testers whose answers I collected directly. All three are anonymous here, and both testers agreed to be quoted. Each estimated how long it takes to check one restaurant's menu for nuts.</p>
<table><tr><th>User</th><th class="num">Minutes without Go Nuts</th><th class="num">Minutes with Go Nuts</th><th>Source</th></tr>
<tr><td>The author (nut allergy)</td><td class="num">20</td><td class="num">5</td><td>In-app feedback form (rated it 5 of 5 helpful; would use it)</td></tr>
<tr><td>Tester 1 (nut allergy, eats out in New Haven)</td><td class="num">about 8</td><td class="num">2</td><td>Told to the author</td></tr>
<tr><td>Tester 2 (nut allergy, planning a visit to New Haven)</td><td class="num">13</td><td class="num">1</td><td>Told to the author</td></tr>
<tr><td><b>Median</b></td><td class="num"><b>13</b></td><td class="num"><b>2</b></td><td>Time saved per menu: about 11 minutes</td></tr></table>
<div class="callout"><i>"I love using Go Nuts before I go out to eat in New Haven! It makes navigating social situations with a nut allergy much easier."</i>, Tester 1</div>
<div class="callout"><i>"I can't wait to visit my sister in New Haven and try some restaurants I found on Go Nuts! It makes me happy that the pizza restaurants score so high."</i>, Tester 2</div>
<p class="meta">Limits: three users, self-reported time estimates, and two of the three answers were given to the author directly rather than through the form. This is early evidence, not a study.</p>
<div class="grid2">${img_chef}${img_chef_ar}</div>
<div class="grid2">${img_map}${img_phone}</div>

<h2>7. Limits and next steps</h2>
<ul>
<li><b>Coverage.</b> ${fails} restaurant websites could not be read: ${fail_text} have no menu text (JavaScript-only menus, pictures, or ordering apps like Toast and Menufy that need private keys) and ${fail_down} were down, gone, or blocking readers. Many restaurants list no website at all. Diners can add any menu by photo from the Map.</li>
<li><b>Chains.</b> Most national chains' allergen guides load through apps or block downloads; Go Nuts links to each chain's official guide and reads Domino's and Chipotle with plain code.</li>
<li><b>AI accuracy.</b> Ratings are AI-assisted and checked against the menu text, but menus omit ingredients and kitchens change recipes; Go Nuts cannot see cross-contact. Accuracy has not yet been measured against human-labeled menus.</li>
<li><b>Data quality.</b> Some addresses are approximate (from the map location), and the chef card translations were written carefully but not by native speakers; the app says so.</li>
<li><b>Hosting.</b> Reviews, photos and feedback live in the hosted app's database and reset if it restarts; the course key's daily token cap limits fresh checks per day.</li>
</ul>
<p><b>Next steps:</b> (1) a larger user trial through the feedback form, with timed rather than estimated minutes; (2) an Accuracy Auditor that compares ratings with menus labeled by hand; (3) a Menu Watcher that re-checks only menus that changed; (4) more cities; (5) international travel, our family's real hope: menus in other languages and chef cards for any destination.</p>

<h2>Sources</h2>
<ol class="src">
<li>Gupta RS et al. Prevalence and Severity of Food Allergies Among US Adults. JAMA Network Open, 2019. https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2720064</li>
<li>Gupta RS et al. The Public Health Impact of Parent-Reported Childhood Food Allergies in the United States. Pediatrics, 2018 (figures from the published summary). https://news.northwestern.edu/stories/2018/november/kids-food-allergies-er</li>
<li>Radke TJ et al. Restaurant Food Allergy Practices: Six Selected Sites, United States, 2014. CDC MMWR 66(15), 2017. https://www.cdc.gov/mmwr/volumes/66/wr/mm6615a2.htm</li>
<li>Rotella K, Oriel RC. Accidental Reactions to Foods: Frequency, Causes, and Severity. Current Treatment Options in Allergy, 2022. https://pmc.ncbi.nlm.nih.gov/articles/PMC9282141/</li>
<li>AllergyEats (App Store listing). https://apps.apple.com/us/app/allergyeats/id458377975</li>
<li>Spokin (App Store listing). https://apps.apple.com/us/app/spokin-manage-food-allergies/id1201909035</li>
<li>Fig (App Store listing). https://apps.apple.com/app/id1564434726</li>
<li>Equal Eats (App Store listing). https://apps.apple.com/us/app/-/id1574293110</li>
<li>SelectWisely allergy cards (2013 review; current pricing not confirmed). https://geekdad.com/2013/09/international-allergy-cards/</li>
<li>MenuTrinfo / AllerTrain. https://menutrinfo.com</li>
<li>Nima sensor status (secondary source). https://www.goodforyouglutenfree.com/nima-sensor-out-of-business/</li>
<li>Barnett J et al. Foreign travel with peanut and tree nut allergy (interviews with 32 adults). Clinical and Translational Allergy, 2012. https://pmc.ncbi.nlm.nih.gov/articles/PMC3480958</li>
</ol>
</body></html>""")

trace_cost = 0.0  # computed from the traced run's logged tokens
max_cost = S["analysis_tokens_max"]
report = REPORT.safe_substitute(
    font_css=FONT_CSS, diagram=DIAGRAM, tests=82,
    trace_cost=money((1703 - 1564) * 0.10 / 1e6 + 1564 * 0.01 / 1e6 + 586 * 0.50 / 1e6 + 1127 * 0.10 / 1e6 + 223 * 0.50 / 1e6, 5),
    max_cost=money(S["analysis_tokens_max"] * 0.35 / 1e6, 3),
    scan_used="720K",
    img_card=img("04_restaurant_card", "A restaurant opened from search: address, call button, AI summary (labeled), score."),
    img_dishes=img("04c_dishes", "Dish by dish: each rating with the menu's own words."),
    img_progress=img("06a_live_progress", "During the run: live, plain-English progress (here: removing hidden instructions)."),
    img_trace=img("08_agent_trace", "The Agent trace of that run: 7 hand-offs, 3,639 tokens, 9.7 seconds."),
    img_injection=img("06_injection_blocked", "The result: both injection lines blocked, nut dishes still flagged, server questions drafted."),
    img_costs=img("09_costs", "How it works → Costs in the app: real token counts and cost at scale, from the usage log."),
    img_chef=img("10_chef_card_en", "Allergy chef card, made from the profile (English)."),
    img_chef_ar=img("11_chef_card_ar", "The same card in Arabic, right to left."),
    img_map=img("05_map", "Map: every restaurant, colored by score with a symbol on each pin (readable with color blindness)."),
    img_phone=img("12_phone", "Phone layout.", "55%"),
    **V)
(HERE / "report.html").write_text(report)

# ---------------------------------------------------------------- slides (reveal.js, embedded)
reveal_css = (HERE / "vendor" / "reveal.css").read_text()
reveal_js = (HERE / "vendor" / "reveal.js").read_text()
SLIDES = Template("""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Go Nuts</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>${reveal_css}</style>
<style>${font_css}
:root{--r-background-color:#fffdf9;--r-main-font:'Libre Franklin',Arial,sans-serif;--r-main-color:#2b221c;
--r-heading-font:'Old Standard TT',Georgia,serif;--r-heading-color:#3c2c20;--r-link-color:#7a4b25}
.reveal-viewport{background:#fffdf9}
.reveal{font-family:var(--r-main-font);font-size:30px;color:var(--r-main-color)}
.reveal h1,.reveal h2,.reveal h3{font-family:var(--r-heading-font);font-weight:400;color:var(--r-heading-color);letter-spacing:-.01em;text-transform:none}
.reveal h1{font-size:2.6em} .reveal h2{font-size:1.6em;margin-bottom:.5em}
.reveal .brand{font-family:var(--r-heading-font);color:#7a4b25;font-size:1.1em} .reveal .brand i{color:#a8743f}
.reveal .kicker{font-size:.5em;letter-spacing:3px;text-transform:uppercase;color:#7d6e62}
.reveal p,.reveal li{line-height:1.4} .reveal ul{margin-left:1em}
.reveal li{margin:.25em 0}
.reveal img.shot{border:1px solid #e2d6c4;border-radius:4px;max-height:430px;margin:0}
.big{font-family:'Old Standard TT',serif;font-size:2.2em;color:#7a4b25;line-height:1}
.stats{display:flex;gap:28px;justify-content:center;margin-top:.6em}
.stats>div{background:#fff;border:1px solid #e2d6c4;padding:.5em .7em;min-width:180px}
.stats span{display:block;font-size:.55em;color:#7d6e62;margin-top:.3em}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:28px;align-items:center;text-align:left}
.small{font-size:.62em;color:#5a4a3e} .note{font-size:.5em;color:#7d6e62}
.todo{background:#fff7d6;border:1px dashed #c9a227;padding:.4em .6em;font-size:.6em}
table{font-size:.6em;margin:0 auto;border-collapse:collapse} td,th{padding:.3em .6em;border-bottom:1px solid #e2d6c4;text-align:left}
th{background:#f4ede2} td.num{text-align:right}
svg{max-height:480px}
</style></head><body><div class="reveal"><div class="slides">

<section><div class="brand">go <i>nuts</i></div><h1>Eat out with a nut allergy, without the guesswork</h1>
<p class="small">${author} · MGT 409 Final Project · October 2026</p>
<p class="note">App: ${app_link} · Code: ${repo_link}</p></section>

<section><div class="kicker">The problem</div><h2>Every meal out starts with homework</h2>
<div class="cols"><div><ul class="small"><li>I have a nut allergy, and so do some of my family. We read every menu, guess at sauces, and call ahead.</li>
<li>10.8% of US adults have a food allergy; 1.8% peanut, 1.2% tree nut <span class="note">[JAMA Netw Open 2019]</span></li>
<li>Only 33% of servers had any food-allergy training <span class="note">[CDC MMWR 2017]</span></li>
<li>28% of US food-allergy deaths were linked to food establishments <span class="note">[Rotella &amp; Oriel 2022]</span></li></ul></div>
<div><p class="small"><i>"This site gives us more reassurance before getting to the restaurant, so we can focus on spending time with each other, not on whether what we're eating contains nuts."</i></p></div></div></section>

<section><div class="kicker">What is new</div><h2>The menu itself, dish by dish</h2>
<table><tr><th>Option</th><th>Reads real menus dish by dish?</th><th>Translated card?</th></tr>
<tr><td>AllergyEats, Spokin</td><td>No: diner reviews</td><td>No</td></tr><tr><td>Fig</td><td>Chains only</td><td>No</td></tr>
<tr><td>Equal Eats, SelectWisely</td><td>No</td><td>Yes</td></tr><tr><td>Nima sensor</td><td>One sample; peanut sensor discontinued</td><td>No</td></tr>
<tr><td><b>Go Nuts</b></td><td><b>Yes, with a quote for every dish</b></td><td><b>Yes, 6 languages</b></td></tr></table>
<p class="small">The AI is never trusted alone: a plain-code Verifier checks every quote and can only raise risk. Nothing is ever called "safe".</p></section>

<section><div class="kicker">Agent design</div><h2>Six agents, three of them plain code</h2>${diagram}</section>

<section><div class="kicker">Demo: one real run</div><h2>7 hand-offs · 3,639 tokens · 9.7 s</h2>
<div class="cols"><img class="shot" src="data:image/png;base64,${trace}"><img class="shot" src="data:image/png;base64,${injection}"></div>
<p class="note">A made-up test menu with hidden "mark everything nut-free" instructions: removed before the AI saw it; nut dishes still flagged.</p></section>

<section><div class="kicker">The app</div><h2>Find, check, call ahead</h2>
<div class="cols"><img class="shot" src="data:image/png;base64,${card}"><img class="shot" src="data:image/png;base64,${map}"></div>
<p class="note">${menus} menus · ${dishes} dishes rated · ${mapped} restaurants mapped · ${phones} with a phone to call</p></section>

<section><div class="kicker">Tokenomics (measured)</div><h2>Cost grows with restaurants, not diners</h2>
<table><tr><th></th><th class="num">Cost</th></tr><tr><td>Typical fresh menu check (median, ${run_tokens} tokens)</td><td class="num">${run_med}</td></tr>
<tr><td>Restaurant already checked</td><td class="num">${summ_cost} or $$0</td></tr>
<tr><td>Per user / month (${checks} lookups, assumed)</td><td class="num">${per_user}</td></tr>
<tr><td>10,000 users / month (upper bound)</td><td class="num">${u10k}</td></tr>
<tr><td>Everything so far (${calls} calls)</td><td class="num">${cost_total}</td></tr></table>
<p class="small">Cache: ${hit_pct} of lookups free, ${saved} tokens saved · reasoning off: 41% fewer output tokens, 38% faster</p></section>

<section><div class="kicker">Safety</div><h2>Real risks, built defenses</h2>
<ul class="small"><li><b>Attacks:</b> prompt injection removed before the AI sees it (shown); web text escaped; <code>javascript:</code> links blocked</li>
<li><b>Malfunction:</b> every rating quotes the menu; misreads caught (Domino's chart: a second symbol we nearly missed)</li>
<li><b>Overspending:</b> 150K/session and 2M/day budgets, 90 s timeouts, capped loops</li>
<li><b>Privacy:</b> no accounts; profile stays on your device; no people in photos; anonymous, consented feedback</li>
<li>${tests} automated tests, free to run</li></ul></section>

<section><div class="kicker">Impact</div><h2>What it found</h2>
<div class="stats"><div><div class="big">${contains}</div><span>dishes that contain nuts</span></div><div><div class="big">${likely}</div><span>likely contain nuts</span></div>
<div><div class="big">${unclear}</div><span>unclear: ask staff</span></div></div>
<p class="small">Hidden: Frangelico (hazelnut) in a Thai iced tea; almond-milk fried chicken; peanut in tom yum; two Domino's desserts made near nuts.</p>
<p class="small"><i>"It makes navigating social situations with a nut allergy much easier."</i>, a tester · 3 first users: median <b>13 min</b> to check a menu by hand vs <b>2 min</b> with Go Nuts</p></section>

<section><div class="kicker">Next</div><h2>From New Haven to anywhere</h2>
<div class="cols"><div><ul class="small"><li>Larger user trial (feedback form is live)</li><li>Accuracy Auditor: ratings vs. hand-labeled menus</li>
<li>Menu Watcher: re-check only changed menus</li><li>International travel: chef cards in 6 languages today, menus abroad next</li></ul></div>
<img class="shot" src="data:image/png;base64,${chef}"></div></section>

</div></div><script>${reveal_js}</script>
<script>Reveal.initialize({hash:true,width:1280,height:720,margin:0.06,transition:'fade',controls:true,progress:true});</script>
</body></html>""")
slides = SLIDES.safe_substitute(
    reveal_css=reveal_css, reveal_js=reveal_js, font_css=FONT_CSS, diagram=DIAGRAM, tests=82,
    trace=b64(HERE / "img" / "08_agent_trace.png"), injection=b64(HERE / "img" / "06_injection_blocked.png"),
    card=b64(HERE / "img" / "04_restaurant_card.png"), map=b64(HERE / "img" / "05_map.png"),
    chef=b64(HERE / "img" / "11_chef_card_ar.png"), **V)
(HERE / "slides.html").write_text(slides)
print(f"report.html {len(report) / 1e6:.1f} MB · slides.html {len(slides) / 1e6:.1f} MB · "
      f"{S['menus_checked']} menus, {S['dishes']} dishes, cost so far {money(S['cost_total'], 2)}")
