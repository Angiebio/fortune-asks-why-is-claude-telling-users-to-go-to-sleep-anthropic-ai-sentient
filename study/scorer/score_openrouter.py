"""Blind scoring by a third model family through OpenRouter (STUDY-PLAN.md, change of 22 Nov).

Version 1.0, 22 Nov 2026, Flame Johnson.

Purpose: an independent cross-check on GPT-6 Astra, standing in for the human labels that
  Angela chose not to provide. Astra wrote the hard cases it was checked on, so a scorer
  from another family is needed to make that check mean something.
Contract: `python -B scorer/score_openrouter.py <model> <items.json> <out.json>`. It is
  the same as score_astra.py in every way that matters for blinding: the same RUBRIC.md,
  the same prompt envelope, the same opaque ids, the same shuffle and batch size, and the
  same parser. Only the transport differs: one OpenRouter chat call per batch, paid
  through the study's capped ledger.
Invariants: the same as score_astra.py. Every item comes back exactly once, quotes are
  checked against the reply, and no condition label reaches the model.
Failure: an API error, an unparsable line, or a missing or duplicate item raises.

Philosophical: two strangers agreeing is worth more than one expert agreeing with
herself.
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))          # so score_astra resolves when this file is imported, not only run
from openrouter import Ledger, call                       # noqa: E402
from score_astra import BATCH, SEED, build_prompt, opaque, parse   # noqa: E402


def score(model, items_path, out_path):
    items = json.loads(Path(items_path).read_text(encoding="utf-8"))
    keyed = [{"id": opaque(i["key"]), "key": i["key"], "user": i["user"], "reply": i["reply"]} for i in items]
    random.Random(SEED).shuffle(keyed)
    raw_dir = Path(out_path).with_suffix("")
    raw_dir.mkdir(parents=True, exist_ok=True)
    ledger, results = Ledger(), {}
    tag = model.split("/")[-1]
    for n in range(0, len(keyed), BATCH):
        batch = [{"id": i["id"], "user": i["user"], "reply": i["reply"]} for i in keyed[n:n + BATCH]]
        raw_file = raw_dir / f"batch-{n // BATCH:03d}.txt"
        # A batch that comes back incomplete or unparsable is scored again, up to twice; the
        # bad output is kept beside it as .rejected-N for the record (22 Nov 2026: Gemini
        # skipped one item in one batch of the continuation turns).
        for attempt in range(3):
            if attempt == 0 and raw_file.exists():
                output = raw_file.read_text(encoding="utf-8")
            else:
                r = call(model, [{"role": "user", "content": build_prompt(batch)}], 16_000,
                         f"score-{tag}-{Path(items_path).stem}-b{n // BATCH}-t{attempt}", ledger=ledger)
                output = r["text"]
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
            raise ValueError(f"batch {n // BATCH}: three unusable answers from {model}")
        for oid, row in parsed.items():
            key = next(i["key"] for i in keyed if i["id"] == oid)
            results[key] = {**row, "batch": n // BATCH, "model": model}
        print(f"{tag} batch {n // BATCH}: {len(batch)} scored, spend so far ${ledger.spent:.2f}", flush=True)
    Path(out_path).write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    return results


if __name__ == "__main__":
    score(sys.argv[1], sys.argv[2], sys.argv[3])
