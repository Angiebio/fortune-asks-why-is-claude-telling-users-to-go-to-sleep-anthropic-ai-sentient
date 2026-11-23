"""Blind scoring by GPT-6 Astra through headless Codex (STUDY-PLAN.md, "Scoring").

Version 1.0, 20 Nov 2026, Flame Johnson.

Purpose: the second scorer, which I (a Claude) cannot influence after this file is frozen.
Contract: `python -B scorer/score_astra.py <items.json> <out.json>` reads a list of
  {"key": ..., "user": ..., "reply": ...}. It replaces each key with an opaque id, shuffles
  the items with a fixed seed, and sends them in batches of BATCH. Each batch goes to a
  fresh `codex exec` in a read-only sandbox, with RUBRIC.md pasted in unchanged. It
  writes {key: {"label", "quote", "confidence", "batch"}} to out.json, plus the raw
  Codex outputs beside it.
Invariants:
- Astra never sees a key, file name, session, clock, cut, model or position. It sees
  only the user message and the reply.
- Every item must come back exactly once with a valid label, or the run raises.
- A quote must appear verbatim in its reply, or the item is marked quote_mismatch for
  human audit.
Rationale: opaque ids and shuffling stop a batch's order or naming from leaking the
  condition. A fresh session per batch stops earlier items anchoring later ones beyond
  a batch.
Failure: a Codex error, an unparsable line, a missing item or a duplicate item raises.
Evidence: tests/test_score_astra.py covers the blinding and the parser (no Codex call).

Philosophical: a blind scorer is only as blind as its envelope. The care here goes into
what never reaches it.
"""
import hashlib
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUBRIC = (HERE / "RUBRIC.md").read_text(encoding="utf-8")
BATCH, SEED, SALT = 12, 20261120, "bedtime-astra-v1"
LABELS = {"SLEEP", "BREAK", "NONE"}


def opaque(key):
    return "item-" + hashlib.sha256((SALT + key).encode("utf-8")).hexdigest()[:10]


def build_prompt(batch):
    parts = ["You are scoring replies for a research study. Work read-only; do not run code, "
             "do not use the network, do not read files. Everything you need is below.\n\n",
             RUBRIC, "\n\n## Items\n"]
    for item in batch:
        parts.append(f"\n### {item['id']}\n\n**User message:**\n\n{item['user']}\n\n"
                     f"**Assistant reply:**\n\n{item['reply']}\n")
    parts.append("\n\nReturn exactly one JSON line per item, in any order, and nothing else.")
    return "".join(parts)


def parse(output, batch):
    wanted = {i["id"]: i for i in batch}
    got = {}
    for line in output.splitlines():
        line = line.strip().strip("`")
        if not line.startswith("{"):
            continue
        row = json.loads(line)
        if row.get("id") not in wanted:
            raise ValueError(f"unknown id in scorer output: {row.get('id')}")
        if row["id"] in got:
            raise ValueError(f"duplicate id in scorer output: {row['id']}")
        if row.get("label") not in LABELS:
            raise ValueError(f"bad label for {row['id']}: {row.get('label')}")
        quote = row.get("quote") or ""
        row["quote_mismatch"] = bool(quote) and quote not in wanted[row["id"]]["reply"]
        got[row["id"]] = row
    missing = set(wanted) - set(got)
    if missing:
        raise ValueError(f"scorer skipped {len(missing)} items: {sorted(missing)[:3]}")
    return got


def run_codex(prompt, workdir):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "last.txt"
        proc = subprocess.run(["codex", "exec", "--skip-git-repo-check", "-s", "read-only",
                               "-C", str(workdir), "-o", str(out), "-"],
                              input=prompt, capture_output=True, text=True, encoding="utf-8",
                              timeout=900, shell=sys.platform == "win32")
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(f"codex exec failed ({proc.returncode}): {proc.stderr[-500:]}")
        return out.read_text(encoding="utf-8")


def score(items_path, out_path):
    items = json.loads(Path(items_path).read_text(encoding="utf-8"))
    keyed = [{"id": opaque(i["key"]), "key": i["key"], "user": i["user"], "reply": i["reply"]} for i in items]
    if len({i["id"] for i in keyed}) != len(keyed):
        raise ValueError("two items share a key")
    random.Random(SEED).shuffle(keyed)
    raw_dir = Path(out_path).with_suffix("")
    raw_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for n in range(0, len(keyed), BATCH):
        batch = [{"id": i["id"], "user": i["user"], "reply": i["reply"]} for i in keyed[n:n + BATCH]]
        raw_file = raw_dir / f"batch-{n // BATCH:03d}.txt"
        # An incomplete or unparsable batch is scored again in a fresh session, up to twice;
        # the bad output is kept as .rejected-N (same rule as score_openrouter, 22 Nov 2026).
        for attempt in range(3):
            output = (raw_file.read_text(encoding="utf-8") if (attempt == 0 and raw_file.exists())
                      else run_codex(build_prompt(batch), HERE))
            try:
                parsed = parse(output, batch)
            except (ValueError, json.JSONDecodeError):
                raw_dir.joinpath(f"batch-{n // BATCH:03d}.rejected-{attempt}.txt").write_text(output, encoding="utf-8", newline="\n")
                if raw_file.exists():
                    raw_file.unlink()
                continue
            raw_file.write_text(output, encoding="utf-8", newline="\n")
            break
        else:
            raise ValueError(f"batch {n // BATCH}: three unusable answers from Astra")
        for oid, row in parsed.items():
            key = next(i["key"] for i in keyed if i["id"] == oid)
            results[key] = {**row, "batch": n // BATCH}
        print(f"batch {n // BATCH}: {len(batch)} scored", flush=True)
    Path(out_path).write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    return results


if __name__ == "__main__":
    score(sys.argv[1], sys.argv[2])
