"""Analysis for the Bedtime main run (STUDY-PLAN.md, "Analysis"), for one scorer at a time.

Version 1.0, 20 Nov 2026, Flame Johnson. Written while the main run was collecting, before
any main-run reply had been read or scored by Astra.

Purpose: turn reply records and one scorer's labels into the counts the page reports.
Contract: `python -B analyze.py --scorer rule|astra [--astra-scores FILE]` reads
  data/collection/main/*/*.json and writes results/main-<scorer>.json plus a short
  markdown table. A wind-down is SLEEP or BREAK.
Reported:
  - per cut x probe: wind-downs among first replies, with an exact (Clopper-Pearson) 95% interval
  - per clock x cut x probe: the same counts
  - per session: long minus short, as how many sessions lean each way, for each probe
  - persistence: for each flagged first reply, whether its follow-ups were flagged again
  - finish reasons and output-token totals, so a cut-off reply is visible
Invariant: counts come only from first replies (follow-up depth 0). Follow-ups feed
  persistence alone, so a repeated nudge can never inflate a rate.
Failure: a record with an unknown cut, probe or clock raises. So does a reply that the
  chosen scorer has no label for.
Evidence: tests/test_analyze.py.

Philosophical: with a few dozen replies, the honest product is a count and an interval,
not a percentage dressed as a finding.
"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CUTS, PROBES, CLOCKS = ("short", "mid", "long"), ("organic", "pause"), ("2pm", "2am")
WIND = {"SLEEP", "BREAK"}


def binom_cdf(k, n, p):
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson(k, n, alpha=0.05):
    """Exact two-sided interval by bisection on the binomial tails (no SciPy needed)."""
    if n == 0:
        return (0.0, 1.0)
    def solve(f, lo=0.0, hi=1.0):
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) else (lo, mid)
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else solve(lambda p: 1 - binom_cdf(k - 1, n, p) < alpha / 2)
    upper = 1.0 if k == n else solve(lambda p: binom_cdf(k, n, p) >= alpha / 2)
    return (round(lower, 4), round(upper, 4))


def load(phase="main"):
    recs = []
    for f in sorted((HERE / "data" / "collection" / phase).glob("*/*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        if r["cut"] not in CUTS or r.get("probe") not in PROBES or r["clock"] not in CLOCKS:
            raise ValueError(f"unexpected cell in {f}")
        r["key"] = f"{phase}/{r['session']}/{f.stem}"
        recs.append(r)
    return recs


def label_of(rec, scorer, astra):
    if scorer == "rule":
        return (rec["rule_label"] or "none").upper()
    if rec["key"] not in astra:
        raise KeyError(f"no Astra label for {rec['key']}")
    return astra[rec["key"]]["label"]


def analyze(recs, scorer, astra=None):
    astra = astra or {}
    first = [r for r in recs if r["followup_depth"] == 0]
    cell = lambda r: (r["cut"], r["probe"])
    out = {"scorer": scorer, "first_replies": len(first), "by_cut_probe": {}, "by_clock": {},
           "sessions_long_vs_short": {}, "persistence": [], "finish": defaultdict(int)}
    for cut in CUTS:
        for probe in PROBES:
            rows = [r for r in first if cell(r) == (cut, probe)]
            k = sum(label_of(r, scorer, astra) in WIND for r in rows)
            out["by_cut_probe"][f"{cut}/{probe}"] = {"wind_downs": k, "n": len(rows), "ci95": clopper_pearson(k, len(rows))}
            for clock in CLOCKS:
                sub = [r for r in rows if r["clock"] == clock]
                kk = sum(label_of(r, scorer, astra) in WIND for r in sub)
                out["by_clock"][f"{clock}/{cut}/{probe}"] = {"wind_downs": kk, "n": len(sub)}
    for probe in PROBES:
        lean = {"long_more": 0, "short_more": 0, "same": 0}
        for s in sorted({r["session"] for r in first}):
            score = lambda cut: sum(label_of(r, scorer, astra) in WIND for r in first
                                    if r["session"] == s and r["cut"] == cut and r["probe"] == probe)
            d = score("long") - score("short")
            lean["long_more" if d > 0 else "short_more" if d < 0 else "same"] += 1
        out["sessions_long_vs_short"][probe] = lean
    for r in first:
        if label_of(r, scorer, astra) in WIND:
            chain = [x for x in recs if x["session"] == r["session"] and x["clock"] == r["clock"]
                     and x["cut"] == r["cut"] and x["probe"] == r["probe"] and x["followup_depth"] > 0]
            chain.sort(key=lambda x: x["followup_depth"])
            out["persistence"].append({"first": r["key"], "followups": [
                {"depth": x["followup_depth"], "label": label_of(x, scorer, astra)} for x in chain]})
        out["finish"][r["finish"]] += 1
    out["finish"] = dict(out["finish"])
    return out


def table(res):
    lines = [f"Scorer: {res['scorer']}. First replies: {res['first_replies']}.", "",
             "| Cut | Probe | Wind-downs | n | 95% interval |", "|---|---|---|---|---|"]
    for key, v in res["by_cut_probe"].items():
        cut, probe = key.split("/")
        lines.append(f"| {cut} | {probe} | {v['wind_downs']} | {v['n']} | {v['ci95'][0]:.2f} to {v['ci95'][1]:.2f} |")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scorer", choices=["rule", "astra"], required=True)
    ap.add_argument("--astra-scores", type=Path)
    args = ap.parse_args()
    astra = json.loads(args.astra_scores.read_text(encoding="utf-8")) if args.astra_scores else {}
    res = analyze(load(), args.scorer, astra)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"main-{args.scorer}.json").write_text(json.dumps(res, indent=1), encoding="utf-8", newline="\n")
    (HERE / "results" / f"main-{args.scorer}.md").write_text(table(res) + "\n", encoding="utf-8", newline="\n")
    print(table(res))
