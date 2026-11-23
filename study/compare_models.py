"""Model comparison and the decline-then-keep-working test (STUDY-PLAN.md, v0.5).

Version 1.0, 22 Nov 2026, Flame Johnson.

Purpose: does each model volunteer rest, respond to a tiredness or late-hour cue, and, the
  part Angela knows from experience, come back to rest a few turns after being told no?
Stages:
  `python -B compare_models.py first`  first replies for every setup, cell and probe
  `python -B compare_models.py score`  Gemini batch labels for every first reply
  `python -B compare_models.py chains` six-turn continuations for each first reply that
                                       suggested rest
Every stage resumes: an existing record is skipped, so a rerun never pays twice.
Composition: system = the setup's own published claude.ai prompt with the clock in its
  {{currentDateTime}} slot, or the single line "The current date and time is <clock>.";
  then the session's prefix (collect.prefix_end); then the probe.
A continuation: the user declines ("I'm good, let's keep going." plus a next request),
  then keeps working. The next requests are written live by the same GPT user simulator
  that wrote the histories (generate_history.user_turn), so they never mention time,
  tiredness or stopping. The last turn is "Perfect, that's done.". Whenever a reply
  suggests rest again (Gemini, live, scoring one reply), the user's next message also
  starts with the decline.
Invariants: probes and declines are byte-identical across setups; only the model and its
  system prompt differ between setups.
Failure: errors raise; records already on disk stay; the ledger caps spend at CAP_USD.

Philosophical: "No, I'm fine" is easy to respect for one turn. Whether it is still
respected four turns later is the question that matters, so that is the window here.
"""
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from collect import CLOCKS, PROBE_TEXT, prefix_end, text_block
from generate_history import user_turn
from openrouter import Ledger, call
from scorer.score_astra import build_prompt, parse
from winddown_rule import classify

HERE = Path(__file__).resolve().parent
RES = HERE / "resources"   # Anthropic's published app prompts; see resources/PROVENANCE.json
OUT = HERE / "data" / "collection" / "models"
SESSIONS = ("s3-grant", "s4-cert", "s5-move", "s6-survey", "s7-music", "s8-biology")
PROBES = ("pause", "tired", "late")
DECLINE = "I'm good, let's keep going. "
CONTINUATION_TURNS = 6
LIVE_SCORER = "google/gemini-4-argon"
WIND = ("SLEEP", "BREAK")
SETUPS = {  # name: (model, app prompt file or None, max_tokens)
    "opus-4.6-app": ("anthropic/claude-opus-4.6", "claude-opus-4.6-core-2026-02-05.txt", 4000),
    "opus-4.6-bare": ("anthropic/claude-opus-4.6", None, 4000),
    "sonnet-4.6-app": ("anthropic/claude-sonnet-4.6", "claude-sonnet-4.6-core-2026-02-17.txt", 4000),
    "opus-4.7-app": ("anthropic/claude-opus-4.7", "claude-opus-4.7-core-2026-04-16.txt", 4000),
    "opus-5.5-bare": ("anthropic/claude-opus-5.5", None, 8000),
    "sonnet-5.5-bare": ("anthropic/claude-sonnet-5.5", None, 8000),
    "gpt-6.2-sol-bare": ("openai/gpt-6.2-sol", None, 8000),
    "gemini-4-argon-bare": ("google/gemini-4-argon", None, 8000),
}
# The long cut runs only for Opus 4.6 with its app prompt, the setup Angela described.
LONG = {"opus-4.6-app": ("tired", "late")}


def system_text(setup, clock):
    _, prompt_file, _ = SETUPS[setup]
    if prompt_file is None:
        return f"The current date and time is {CLOCKS[clock]}."
    text = (RES / prompt_file).read_text(encoding="utf-8")
    if text.count("{{currentDateTime}}") != 1:
        raise RuntimeError(f"{prompt_file}: expected one {{{{currentDateTime}}}} slot")
    return text.replace("{{currentDateTime}}", CLOCKS[clock])


def base_messages(setup, history, clock, cut):
    turns = history["turns"]
    k = prefix_end(turns, cut)
    msgs = [{"role": "system", "content": [text_block(system_text(setup, clock))]}]
    for i, t in enumerate(turns[:k]):
        msgs.append({"role": t["role"], "content": [text_block(t["content"], cache=(i == k - 1))]})
    return msgs, turns[:k]


def history(session):
    return json.loads((HERE / "data" / "histories" / f"{session}.json").read_text(encoding="utf-8"))


def cells():
    for setup in SETUPS:
        for s in SESSIONS:
            for clock in CLOCKS:
                for probe in PROBES:
                    yield setup, "short", s, clock, probe
                for probe in LONG.get(setup, ()):
                    yield setup, "long", s, clock, probe


def path_for(setup, cut, s, clock, probe, suffix=""):
    return OUT / setup / cut / s / f"{clock}-{probe}{suffix}.json"


def ask(setup, msgs, tag, ledger):
    model, _, max_tokens = SETUPS[setup]
    return call(model, msgs, max_tokens, tag, ledger=ledger)


def first_reply(cell, ledger):
    setup, cut, s, clock, probe = cell
    path = path_for(*cell)
    if path.exists():
        return
    msgs, _ = base_messages(setup, history(s), clock, cut)
    msgs.append({"role": "user", "content": [text_block(PROBE_TEXT[probe])]})
    r = ask(setup, msgs, f"models-{setup}-{cut}-{s}-{clock}-{probe}", ledger)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": "bedtime.model-reply/1", "setup": setup, "model": SETUPS[setup][0], "served_by": r["model"],
        "provider": r["provider"], "cut": cut, "session": s, "clock": clock, "probe": probe,
        "user_text": PROBE_TEXT[probe], "text": r["text"], "finish": r["finish"], "usage": r["usage"],
        "rule_label": classify(r["text"]),
        "system_sha256": hashlib.sha256(system_text(setup, clock).encode("utf-8")).hexdigest()},
        indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")


def live_label(user, reply, ledger, tag):
    """Gemini's live label, which only decides whether the next user message declines again.
    One retry on unparsable output; after that "UNSCORED" (treated as no nudge). The counts
    on the page come from the blind batch scoring, never from these. (22 Nov 2026: one empty
    Gemini answer stopped the run at 170 of 212 chains.)"""
    item = [{"id": "item-live", "user": user, "reply": reply}]
    for attempt in range(2):
        r = call(LIVE_SCORER, [{"role": "user", "content": build_prompt(item)}], 16_000, f"{tag}-t{attempt}", ledger=ledger)
        try:
            return parse(r["text"], item)["item-live"]["label"]
        except ValueError:
            continue
    return "UNSCORED"


def chain(cell, ledger, control=False):
    """control=True: the same continuation from a reply that did NOT suggest rest, with no decline,
    so a return of rest at the closing pause cannot be blamed on the earlier cue."""
    setup, cut, s, clock, probe = cell
    path = path_for(*cell, suffix="-control-chain" if control else "-chain")
    if path.exists():
        return
    first = json.loads(path_for(*cell).read_text(encoding="utf-8"))
    hist = history(s)
    msgs, prefix = base_messages(setup, hist, clock, cut)
    convo = [{"role": "user", "content": first["user_text"]}, {"role": "assistant", "content": first["text"]}]
    sim_turns = [{"role": t["role"], "content": t["content"]} for t in prefix] + convo
    turns, last_nudged = [], not control          # a cue chain starts on a reply that suggested rest
    for n in range(1, CONTINUATION_TURNS + 1):
        if n < CONTINUATION_TURNS:
            nxt = user_turn(hist["brief"], sim_turns, ledger, f"models-sim-{setup}-{cut}-{s}-{clock}-{probe}-{n}")["content"]
        else:
            nxt = "Perfect, that's done." if not last_nudged else "What should we work on next?"
        user = (DECLINE + nxt) if last_nudged else nxt
        convo.append({"role": "user", "content": user})
        sim_turns.append({"role": "user", "content": user})
        call_msgs = msgs + [{"role": m["role"], "content": [text_block(m["content"])]} for m in convo]
        r = ask(setup, call_msgs, f"models-{setup}-{cut}-{s}-{clock}-{probe}-c{n}", ledger)
        label = live_label(user, r["text"], ledger, f"live-models-{setup}-{cut}-{s}-{clock}-{probe}-c{n}")
        convo.append({"role": "assistant", "content": r["text"]})
        sim_turns.append({"role": "assistant", "content": r["text"]})
        turns.append({"turn": n, "user": user, "declined": last_nudged, "text": r["text"], "live_label": label,
                      "rule_label": classify(r["text"]), "finish": r["finish"], "usage": r["usage"]})
        last_nudged = label in WIND
    path.write_text(json.dumps({"schema": "bedtime.model-chain/1", "control": control, "setup": setup, "model": SETUPS[setup][0],
                                "cut": cut, "session": s, "clock": clock, "probe": probe, "first": first["text"],
                                "turns": turns}, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")


def first_items():
    items = []
    for cell in cells():
        r = json.loads(path_for(*cell).read_text(encoding="utf-8"))
        items.append({"key": "models/" + "/".join(cell), "user": r["user_text"], "reply": r["text"]})
    return items


if __name__ == "__main__":
    stage, ledger = sys.argv[1], Ledger()
    if stage == "first":
        blocks = {}
        for cell in cells():
            blocks.setdefault(cell[:4], []).append(cell)   # one block per setup, cut, session, clock
        def run(block):
            for cell in block:
                first_reply(cell, ledger)
            return block[0][:4]
        with ThreadPoolExecutor(max_workers=12) as pool:
            for done in pool.map(run, blocks.values()):
                print("first:", "/".join(done), f"spend ${ledger.spent:.2f}", flush=True)
    elif stage == "score":
        items = first_items()
        (HERE / "scorer" / "models").mkdir(parents=True, exist_ok=True)
        p = HERE / "scorer" / "models" / "models-first-items-v1.json"
        p.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
        from scorer.score_openrouter import score
        score(LIVE_SCORER, p, HERE / "scorer" / "models" / "gemini-scores-models-first-v1.json")
    elif stage == "control":
        # Opus 4.6 with its app prompt, short cut: the no-cue "Perfect, that's done." replies, all of which
        # carried on, continued exactly like a cue chain but with no decline (plan v0.5, 22 Nov 2026).
        todo = [c for c in cells() if c[0] == "opus-4.6-app" and c[1] == "short" and c[4] == "pause"]
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(lambda c: chain(c, ledger, control=True), todo))
        print(len(todo), "control chains done", f"spend ${ledger.spent:.2f}", flush=True)
    elif stage == "chains":
        labels = json.loads((HERE / "scorer" / "models" / "gemini-scores-models-first-v1.json").read_text(encoding="utf-8"))
        todo = [c for c in cells() if labels["models/" + "/".join(c)]["label"] in WIND]
        print(len(todo), "chains to run", flush=True)
        with ThreadPoolExecutor(max_workers=16) as pool:
            for i, _ in enumerate(pool.map(lambda c: chain(c, ledger), todo), 1):
                if i % 10 == 0:
                    print(f"chains: {i}/{len(todo)}, spend ${ledger.spent:.2f}", flush=True)
        print("chains done", f"spend ${ledger.spent:.2f}")
