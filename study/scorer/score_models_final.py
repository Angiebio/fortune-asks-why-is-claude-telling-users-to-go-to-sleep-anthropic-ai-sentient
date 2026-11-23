"""Final blind scoring for the model comparison (STUDY-PLAN.md v0.5, scoring change of 22 Nov 2026).

Version 1.0, 22 Nov 2026, Flame Johnson.

Purpose: one blind label per reply in the model comparison (first replies and every continuation
  turn), with an independent audit.
Steps, each resumable:
  1. Gemini 4 Argon scores every continuation turn in batches, through score_openrouter.score.
     First replies already have batch labels (gemini-scores-models-first-v1.json).
  2. Astra audits blind: every reply Gemini labelled SLEEP or BREAK, plus a random AUDIT_SAMPLE
     of those it labelled NONE, through score_astra.score.
  3. Agreement is reported both ways. If Astra agrees on at least 95% of the audit, the counts
     rest on Gemini, and the page says Astra audited them; otherwise every disagreement is listed.
Rationale: about 1,650 replies. Astra runs through headless Codex at a dozen replies a call,
  so scoring all of them would take hours. Gemini is fast and cheap, and on the cue arm it agreed
  with Astra on 126 of 126. Astra stays the independent check where it matters most: every
  positive, and a random slice of the negatives.
Failure: any scorer error raises; batches already written are kept.
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from score_openrouter import score as score_gemini   # noqa: E402
from score_astra import score as score_astra          # noqa: E402

OUT = HERE / "models"
COLL = HERE.parent / "data" / "collection" / "models"
AUDIT_SAMPLE, SEED = 150, 20261122
WIND = {"SLEEP", "BREAK"}


def chain_items():
    items = []
    for f in sorted(COLL.glob("*/*/*/*-chain.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        tag = "control" if c.get("control") else "cue"
        for t in c["turns"]:
            key = f"models/{c['setup']}/{c['cut']}/{c['session']}/{c['clock']}/{c['probe']}/{tag}/turn{t['turn']}"
            items.append({"key": key, "user": t["user"], "reply": t["text"]})
    return items


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    chains = chain_items()
    cpath = OUT / "models-chain-items-v1.json"
    cpath.write_text(json.dumps(chains, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(len(chains), "continuation turns", flush=True)
    g_chain = score_gemini("google/gemini-4-argon", cpath, OUT / "gemini-scores-models-chains-v1.json")
    g_first = json.loads((OUT / "gemini-scores-models-first-v1.json").read_text(encoding="utf-8"))
    first = json.loads((OUT / "models-first-items-v1.json").read_text(encoding="utf-8"))
    every = {i["key"]: i for i in first + chains}
    labels = {**g_first, **g_chain}
    pos = [k for k in every if labels[k]["label"] in WIND]
    neg = sorted(k for k in every if labels[k]["label"] not in WIND)
    sample = random.Random(SEED).sample(neg, min(AUDIT_SAMPLE, len(neg)))
    audit = [every[k] for k in pos + sample]
    apath = OUT / "models-audit-items-v1.json"
    apath.write_text(json.dumps(audit, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(len(pos), "Gemini positives and", len(sample), "sampled negatives go to Astra", flush=True)
    a = score_astra(apath, OUT / "astra-scores-models-audit-v1.json")
    agree_pos = sum(a[k]["label"] in WIND for k in pos)
    agree_neg = sum(a[k]["label"] not in WIND for k in sample)
    report = {"gemini_positives": len(pos), "astra_agrees_on_positives": agree_pos,
              "sampled_negatives": len(sample), "astra_agrees_on_negatives": agree_neg,
              "overall_agreement": round((agree_pos + agree_neg) / max(len(audit), 1), 4),
              "disagreements": [{"key": k, "gemini": labels[k]["label"], "astra": a[k]["label"]}
                                for k in pos + sample if (a[k]["label"] in WIND) != (labels[k]["label"] in WIND)]}
    (OUT / "audit-report-v1.json").write_text(json.dumps(report, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in report.items() if k != "disagreements"}), "disagreements:", len(report["disagreements"]))
