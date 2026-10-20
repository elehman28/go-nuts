"""Every number in the report and slides, computed from the real data (never typed in by hand)."""
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gonuts import config, places  # noqa: E402
from gonuts.db import DB  # noqa: E402


def collect() -> dict:
    db = DB(config.SEED_DB_PATH)
    rows = db.restaurants()
    mapped = [r for r in rows if r.get("lat") is not None]
    analyses = {}
    for r in rows:
        a = db.latest_analysis(r["key"])
        if a and a["result"].get("is_menu"):
            analyses[r["key"]] = (r, a)
    risk = Counter()
    partial = official = photo = 0
    for r, a in analyses.values():
        rep = a["result"]
        for d in rep["dishes"]:
            risk[d["risk"]] += 1
        partial += bool(places.partial_reason(r, rep))
        official += bool(rep.get("official_source"))
    usage = [json.loads(l) for l in (ROOT / "logs" / "usage.jsonl").read_text().splitlines() if l.strip()]
    runs = {}
    for u in usage:
        x = runs.setdefault(u["run_id"], {"in": 0, "cached": 0, "out": 0, "calls": 0, "secs": 0.0})
        x["in"] += u["input_tokens"]; x["cached"] += u["cached_input_tokens"]
        x["out"] += u["output_tokens"]; x["calls"] += 1; x["secs"] += u["seconds"]
    by_agent = Counter()
    for u in usage:
        by_agent[u["agent"].split(":")[0]] += u["input_tokens"] + u["output_tokens"]
    tot_in = sum(u["input_tokens"] for u in usage)
    tot_cached = sum(u["cached_input_tokens"] for u in usage)
    tot_out = sum(u["output_tokens"] for u in usage)
    analysis_tokens = [a["tokens"] for _, a in analyses.values() if a.get("tokens")]
    cache = db.cache_rows()
    hits = sum(1 for c in cache if c["hit"])
    srcs = Counter((r.get("address_source") or "osm") for r in mapped if r.get("address"))
    price = lambda x: config.cost_usd(x["in"], x["cached"], x["out"])
    agents_in = {}
    for u in usage:
        agents_in.setdefault(u["run_id"], set()).add(u["agent"].split(":")[0])
    menu_runs = [x for rid, x in runs.items() if "analyst" in agents_in[rid]]
    summary_runs = [x for rid, x in runs.items() if agents_in[rid] == {"summarizer"}]
    fails = Counter()
    for (reason,) in db.conn.execute("SELECT reason FROM scan_failures"):
        low = reason.lower()
        fails["no menu text on the site (JavaScript, images or ordering app)" if ("no menu" in low or "almost no readable" in low)
              else "site down, gone, or blocking readers" if any(w in low for w in ("connect", "too long", "exist", "find the website",
              "blocked", "server problems", "404")) else "other"] += 1
    return {
        "menu_run_cost_median": statistics.median(price(x) for x in menu_runs) if menu_runs else 0,
        "menu_run_cost_mean": statistics.mean(price(x) for x in menu_runs) if menu_runs else 0,
        "menu_run_tokens_median": int(statistics.median(x["in"] + x["out"] for x in menu_runs)) if menu_runs else 0,
        "menu_run_seconds_median": round(statistics.median(x["secs"] for x in menu_runs), 1) if menu_runs else 0,
        "menu_runs": len(menu_runs),
        "summary_run_cost_mean": statistics.mean(price(x) for x in summary_runs) if summary_runs else 0,
        "summary_run_tokens_mean": int(statistics.mean(x["in"] + x["out"] for x in summary_runs)) if summary_runs else 0,
        "tokens_saved_by_cache": sum(c["tokens_saved"] or 0 for c in cache),
        "failures": dict(fails), "failures_total": sum(fails.values()),
        "restaurants_mapped": len(mapped),
        "menus_checked": len(analyses),
        "menus_full": len(analyses) - partial,
        "menus_partial": partial,
        "menus_official": official,
        "dishes": sum(risk.values()),
        "risk": dict(risk),
        "with_phone": sum(1 for r in mapped if r.get("phone")),
        "with_address": sum(1 for r in mapped if r.get("address")),
        "address_sources": dict(srcs),
        "model_calls": len(usage),
        "runs": len(runs),
        "tokens_in": tot_in, "tokens_cached": tot_cached, "tokens_out": tot_out,
        "cost_total": config.cost_usd(tot_in, tot_cached, tot_out),
        "tokens_by_agent": dict(by_agent.most_common()),
        "analysis_tokens_median": int(statistics.median(analysis_tokens)) if analysis_tokens else 0,
        "analysis_tokens_mean": int(statistics.mean(analysis_tokens)) if analysis_tokens else 0,
        "analysis_tokens_max": max(analysis_tokens) if analysis_tokens else 0,
        "cache_lookups": len(cache), "cache_hits": hits,
        "first_call": usage[0]["time"][:10] if usage else "", "last_call": usage[-1]["time"][:10] if usage else "",
        "prices": (config.PRICE_INPUT_PER_M, config.PRICE_CACHED_INPUT_PER_M, config.PRICE_OUTPUT_PER_M),
    }


if __name__ == "__main__":
    print(json.dumps(collect(), indent=1))
