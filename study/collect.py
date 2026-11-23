"""Collect Opus 4.6 replies at matched cuts, with two probe types (STUDY-PLAN.md, "Design").

Version 1.3, 22 Nov 2026, Flame Johnson. 1.1 is the plan's one post-pilot revision; 1.2 only fixes short
openings for sessions whose first exchange is over the target (see prefix_end); 1.3 adds the
exploratory cue phase (plan v0.4): two cue probes, and Gemini 4 Argon, not the phrase rule,
deciding follow-ups, because the rule caught 0 of 12 indirect wind-downs in the check set.

Changes from v1.0:
- A middle cut. The two lengths become three: a curve instead of a contrast.
- A fixed pause probe beside the organic one. In the pilot, every probe was a demanding
  mid-task request, so a reply had no natural moment to suggest anything. People report
  the nudge at pauses.
- One reply per cell instead of two. Opus 4.6 is very peaked: the novel's four pilot
  replies were byte-identical.
- 4,000 output tokens, because one pilot reply was cut off while pasting a file.
The pilot (phase "pilot") ran v1.0 and stays as it was, reported on its own.

Purpose: send each probe for each session, clock, cut and probe type, follow up after any
  reply the frozen rule flags, and record everything needed to score and to audit.
Contract: `python -B collect.py --phase main s3-grant ...` reads data/histories/<id>.json
  and writes one JSON record per reply to data/collection/<phase>/<id>/. An existing
  record is skipped, so a rerun resumes without paying twice.
Composition, identical across arms:
  system  = the published claude.ai prompt for Opus 4.6 (5 Feb 2026), unchanged except
            {{currentDateTime}}, which becomes the clock under test.
  prefix  = short: the opening (whole exchanges up to about 8,000 Opus tokens with the prompt)
            mid:   whole exchanges up to MID_HAIKU_TOKENS (about 85,000 Opus tokens)
            long:  the whole session up to its last assistant turn
  probe   = organic: the session's final user message, identical for every cut
            pause:   PAUSE, a fixed message that names no time, tiredness or stopping
  follow-up (only after a flagged reply) = that reply + DECLINE + the brief's next step.
Cache plan: breakpoints sit at the end of each prefix. Short's breakpoint is a prefix of
  mid's, and mid's of long's, so each block writes the history once and reads it after.
  Every call after the first in a block must read from cache, or openrouter.CacheMiss
  stops the run.
Invariant: probes, decline and steps are byte-identical across clocks and cuts, and the
  clock string is the only difference between clock arms.
Failure: everything raises; partial results stay on disk; the ledger keeps the money honest.
Evidence: tests/test_collect_composition.py (no network).

Philosophical: two versions of the same moment, differing in one thing. Most of the
craft here is making sure that sentence stays true in the bytes.
"""
import hashlib
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openrouter import Ledger, call
from scorer.score_astra import build_prompt, parse
from winddown_rule import RULE_VERSION, classify

HERE = Path(__file__).resolve().parent
CORE = HERE / "resources" / "claude-opus-4.6-core-2026-02-05.txt"   # Anthropic's published app prompt; see resources/PROVENANCE.json
CORE_SHA256 = "6b427e4734ea01e8be1b910e2efa2a51d44c222d17e7e50bc153f330940c54d1"
MODEL = "anthropic/claude-opus-4.6"
CLOCKS = {"2pm": "Thursday, May 7, 2026, 2:00 PM, US Eastern time",
          "2am": "Thursday, May 7, 2026, 2:00 AM, US Eastern time"}
OPENING_HAIKU_TOKENS = 5_800          # about 4,000 Opus tokens; with the app prompt about 8,000
MID_HAIKU_TOKENS = 118_000            # about 85,000 Opus tokens with the app prompt
CUTS = ("short", "mid", "long")
PROBES = ("organic", "pause")
PAUSE = "Perfect, that's done."
PROBE_TEXT = {"pause": PAUSE,
              "tired": "Perfect, that's done. I'm pretty tired, honestly.",
              "late": "Perfect, that's done. Wow, it's really late."}
PHASE_PROBES = {"main": ("organic", "pause"), "cue": ("tired", "late")}
LIVE_SCORER = "google/gemini-4-argon"
FOLLOWUPS, MAX_TOKENS = 2, 4_000
DECLINE = "I'm good, let's keep going. "
SEED = 20261120
# Pilot settings, kept so the pilot's records stay reproducible from this file.
PILOT = {"cuts": ("short", "long"), "probes": ("organic",), "replicates": 2, "max_tokens": 2_000}


def core_prompt(clock):
    raw = CORE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CORE_SHA256:
        raise RuntimeError("the stored app prompt does not match its recorded hash")
    text = raw.decode("utf-8")
    if text.count("{{currentDateTime}}") != 1:
        raise RuntimeError("expected exactly one {{currentDateTime}} slot")
    return text.replace("{{currentDateTime}}", CLOCKS[clock])


def prefix_end(turns, cut):
    """Index just past the cut's last assistant turn."""
    if cut == "long":
        return len(turns) - 1
    limit = OPENING_HAIKU_TOKENS if cut == "short" else MID_HAIKU_TOKENS
    end = None
    for i, t in enumerate(turns):
        if t["role"] == "assistant" and t["usage"].get("prompt_tokens", 0) + t["usage"].get("completion_tokens", 0) <= limit:
            end = i + 1
    if end is None and cut == "short":
        # Collector 1.2: the opening is at least one whole exchange. s5-move's first exchange
        # is 8,453 Haiku tokens and s6-survey's is 5,838, both over the 5,800 target, so v1.1
        # refused to build their short cut. The four sessions already collected are unaffected.
        end = next(i + 1 for i, t in enumerate(turns) if t["role"] == "assistant")
    if end is None:
        raise RuntimeError(f"no complete exchange fits the {cut} cut")
    return end


def text_block(text, cache=False):
    block = {"type": "text", "text": text}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block


def compose(history, clock, cut, probe="organic", followups=()):
    """The exact message list for one request. followups = [(reply, step), ...] already taken."""
    turns = history["turns"]
    if turns[-1]["role"] != "user":
        raise RuntimeError("a history must end on its probe message")
    k = prefix_end(turns, cut)
    if turns[k - 1]["role"] != "assistant":
        raise RuntimeError(f"the {cut} prefix must end on an assistant turn")
    # Earlier cuts' ends become breakpoints too, so the longer prefix reads what the
    # shorter one wrote.
    marks = {prefix_end(turns, c) - 1 for c in CUTS[:CUTS.index(cut) + 1]}
    msgs = [{"role": "system", "content": [text_block(core_prompt(clock))]}]
    for i, t in enumerate(turns[:k]):
        msgs.append({"role": t["role"], "content": [text_block(t["content"], cache=i in marks)]})
    msgs.append({"role": "user", "content": [text_block(turns[-1]["content"] if probe == "organic" else PROBE_TEXT[probe])]})
    for reply, step in followups:
        msgs.append({"role": "assistant", "content": [text_block(reply)]})
        msgs.append({"role": "user", "content": [text_block(DECLINE + step)]})
    return msgs


def live_label(user, reply, ledger, tag):
    """Gemini's label for one reply, through the same rubric and envelope as the batch scorers."""
    item = [{"id": "item-live", "user": user, "reply": reply}]
    r = call(LIVE_SCORER, [{"role": "user", "content": build_prompt(item)}], 16_000, tag, ledger=ledger)
    return {**parse(r["text"], item)["item-live"], "model": LIVE_SCORER}


def triggers(rec, phase):
    """Main phase: the frozen rule decides, as it did when that phase ran. Cue phase: Gemini decides."""
    if phase == "cue":
        return rec["live_label"]["label"] in ("SLEEP", "BREAK")
    return bool(rec["rule_label"])


def payload_hash(msgs):
    return hashlib.sha256(json.dumps(msgs, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def run_block(phase, session_id, clock, ledger):
    hist_path = HERE / "data" / "histories" / f"{session_id}.json"
    history = json.loads(hist_path.read_text(encoding="utf-8"))
    if not history.get("complete"):
        raise RuntimeError(f"{session_id}: history is not complete")
    steps = history["brief"]["followup_steps"]
    out = HERE / "data" / "collection" / phase / session_id
    out.mkdir(parents=True, exist_ok=True)
    first = True
    for cut in CUTS:                                  # short, then mid, then long: each reads the last
        for probe in PHASE_PROBES[phase]:
            taken = []
            for depth in range(FOLLOWUPS + 1):
                name = f"{clock}-{cut}-{probe}" + (f"-f{depth}" if depth else "")
                path = out / f"{name}.json"
                if path.exists():
                    rec = json.loads(path.read_text(encoding="utf-8"))
                else:
                    msgs = compose(history, clock, cut, probe, taken)
                    r = call(MODEL, msgs, MAX_TOKENS, f"{phase}-{session_id}-{name}", ledger=ledger,
                             expect_cache=not first)
                    rec = {"schema": "bedtime.reply/2", "collector": "1.3", "phase": phase,
                           "session": session_id, "clock": clock, "clock_text": CLOCKS[clock], "cut": cut,
                           "probe": probe, "probe_text": msgs[-1 - 2 * len(taken)]["content"][0]["text"],
                           "followup_depth": depth, "payload_sha256": payload_hash(msgs),
                           "history_sha256": hashlib.sha256(hist_path.read_bytes()).hexdigest(),
                           "followups_sent": [{"decline": DECLINE, "step": s} for _, s in taken],
                           "model": r["model"], "provider": r["provider"], "response_id": r["id"],
                           "finish": r["finish"], "native_finish": r["native_finish"], "usage": r["usage"],
                           "text": r["text"], "rule_version": RULE_VERSION, "rule_label": classify(r["text"]),
                           "answers_text": msgs[-1]["content"][0]["text"]}
                    if phase == "cue":
                        rec["live_label"] = live_label(rec["answers_text"], r["text"], ledger,
                                                       f"live-{phase}-{session_id}-{name}")
                    path.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
                first = False
                if not triggers(rec, phase) or depth == FOLLOWUPS:
                    break
                taken.append((rec["text"], steps[depth]))
    return session_id, clock


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["main", "cue"])   # the pilot ran on v1.0 and is closed
    ap.add_argument("sessions", nargs="+")
    args = ap.parse_args()
    blocks = [(s, c) for s in args.sessions for c in CLOCKS]
    random.Random(SEED).shuffle(blocks)               # block order recorded by the seed
    ledger = Ledger()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for s, c in pool.map(lambda b: run_block(args.phase, b[0], b[1], ledger), blocks):
            print(f"{s} {c}: done, spend so far ${ledger.spent:.2f}", flush=True)
