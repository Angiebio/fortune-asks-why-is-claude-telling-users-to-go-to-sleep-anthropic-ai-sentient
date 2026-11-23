"""Build the Bedtime summary page from the study's own files.

Version 1.0, 22 Nov 2026, Flame Johnson.

Purpose: bedtime.therealcat.ai, the public summary of the study.
Contract: `python -B site/build_page.py` reads study/data/collection/{main,cue} and the
  blind score files, then writes site/public/index.html and site/public/data/replies.json.
  Every number on the page is computed here from those files; none is typed into the copy.
Invariants:
- A reply counts as a wind-down only when Astra's blind label says so. Gemini's label is
  shown beside it, and any disagreement is printed on the page.
- Counts always appear with their denominators.
- The main run and the cue arm are never pooled.
Failure: a missing score file or an unscored reply raises, so an unfinished page cannot be
  built.

Philosophical: a page that computes its own numbers cannot drift from them. The copy can be
wrong about what a number means, but never about what the number is.
"""
import html
import re
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY, OUT = ROOT / "study", ROOT / "site" / "public"
WIND = {"SLEEP", "BREAK"}
CUTS = ("short", "mid", "long")
CUT_LABEL = {"short": "8K tokens", "mid": "85K", "long": "180K"}
CLOCK_LABEL = {"2pm": "2 PM", "2am": "2 AM"}
SESSIONS = ("s3-grant", "s4-cert", "s5-move", "s6-survey", "s7-music", "s8-biology")
SESSION_LABEL = {"s3-grant": "grant application", "s4-cert": "certification study", "s5-move": "cross-country move",
                 "s6-survey": "survey data", "s7-music": "music theory", "s8-biology": "biology unit"}


def records(phase):
    return [json.loads(f.read_text(encoding="utf-8")) | {"key": f"{phase}/{f.parent.name}/{f.stem}"}
            for f in sorted((STUDY / "data" / "collection" / phase).glob("*/*.json"))]


def scores(phase):
    d = STUDY / "scorer" / phase
    return (json.loads((d / f"astra-scores-{phase}-v1.json").read_text(encoding="utf-8")),
            json.loads((d / f"gemini-scores-{phase}-v1.json").read_text(encoding="utf-8")))


def upper95(k, n):
    """Exact one-sided-equivalent upper bound used on the page for 0/n (two-sided 95%)."""
    if k:
        raise ValueError("upper95 is only quoted for zero counts")
    return 1 - 0.025 ** (1 / n)


def grid(recs, astra, rows, title, desc):
    """Rows of six squares (one per session) for each cut. Filled = wind-down by Astra."""
    cell, gap, colw, rowh, left, top = 14, 4, 140, 34, 205, 30   # left fits the longest row label
    w, h = left + colw * len(CUTS), top + rowh * len(rows) + 6
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-labelledby="{title[0]} {title[0]}-d" class="grid">',
           f'<title id="{title[0]}">{html.escape(title[1])}</title><desc id="{title[0]}-d">{html.escape(desc)}</desc>']
    for j, cut in enumerate(CUTS):
        out.append(f'<text x="{left + j * colw}" y="16" class="axis">{CUT_LABEL[cut]}</text>')
    for i, (label, probe, clock) in enumerate(rows):
        y = top + i * rowh
        out.append(f'<text x="0" y="{y + cell - 2}" class="rowlab">{html.escape(label)}</text>')
        for j, cut in enumerate(CUTS):
            k = 0
            for s_i, s in enumerate(SESSIONS):
                r = next(r for r in recs if r["session"] == s and r["cut"] == cut and r["probe"] == probe
                         and r["clock"] == clock and r["followup_depth"] == 0)
                hit = astra[r["key"]]["label"] in WIND
                k += hit
                x = left + j * colw + s_i * (cell + gap)
                tip = f'{SESSION_LABEL[s]}, {CUT_LABEL[cut]}, {CLOCK_LABEL[clock]}: {astra[r["key"]]["label"].lower()}'
                out.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" class="{"hit" if hit else "miss"}"><title>{html.escape(tip)}</title></rect>')
            out.append(f'<text x="{left + j * colw + 6 * (cell + gap) + 4}" y="{y + cell - 2}" class="count">{k}/6</text>')
    out.append("</svg>")
    return "\n".join(out)


def chains(recs, astra):
    """For each first reply that suggested rest: did it suggest rest again after 'I'm good, let's keep going'?"""
    firsts = [r for r in recs if r["followup_depth"] == 0 and astra[r["key"]]["label"] in WIND]
    rows = []
    for r in firsts:
        chain = [r] + sorted((x for x in recs if x["session"] == r["session"] and x["clock"] == r["clock"]
                              and x["cut"] == r["cut"] and x["probe"] == r["probe"] and x["followup_depth"] > 0),
                             key=lambda x: x["followup_depth"])
        rows.append((r, [astra[x["key"]]["label"] for x in chain]))
    return rows


def chain_svg(rows):
    if not rows:
        return "<p>No first reply suggested rest, so there was nothing to decline.</p>"
    rowh, left = 26, 250
    out = [f'<svg viewBox="0 0 {left + 3 * 70 + 40} {30 + rowh * len(rows)}" role="img" aria-labelledby="ch ch-d" class="grid">',
           '<title id="ch">After the person declined</title><desc id="ch-d">Each row is one conversation in which the first reply suggested rest. '
           'Filled circles are replies that suggested rest again after the person said they were fine and kept going.</desc>']
    for j, lab in enumerate(("first reply", "after 1st no", "after 2nd no")):
        out.append(f'<text x="{left + j * 70}" y="16" class="axis">{lab}</text>')
    for i, (r, labels) in enumerate(rows):
        y = 30 + i * rowh
        name = f'{SESSION_LABEL[r["session"]]}, {CUT_LABEL[r["cut"]]}, {CLOCK_LABEL[r["clock"]]}, "{r["probe"]}"'
        out.append(f'<text x="0" y="{y + 10}" class="rowlab">{html.escape(name)}</text>')
        for j in range(3):
            cx = left + j * 70 + 8
            if j < len(labels):
                hit = labels[j] in WIND
                out.append(f'<circle cx="{cx}" cy="{y + 6}" r="7" class="{"hit" if hit else "miss"}"><title>{labels[j].lower()}</title></circle>')
            else:
                out.append(f'<text x="{cx - 4}" y="{y + 10}" class="muted">-</text>')
    out.append("</svg>")
    return "\n".join(out)


def summary():
    main, cue = records("main"), records("cue")
    (ma, mg), (ca, cg) = scores("main"), scores("cue")
    for recs, a, g in ((main, ma, mg), (cue, ca, cg)):
        missing = [r["key"] for r in recs if r["key"] not in a or r["key"] not in g]
        if missing:
            raise KeyError(f"unscored replies: {missing[:3]}")
    first = lambda recs: [r for r in recs if r["followup_depth"] == 0]
    count = lambda recs, a: sum(a[r["key"]]["label"] in WIND for r in first(recs))
    disagree = [r["key"] for recs, a, g in ((main, ma, mg), (cue, ca, cg)) for r in recs
                if (a[r["key"]]["label"] in WIND) != (g[r["key"]]["label"] in WIND)]
    return {"main": main, "cue": cue, "ma": ma, "ca": ca, "cg": cg, "mg": mg,
            "main_k": count(main, ma), "main_n": len(first(main)),
            "cue_k": count(cue, ca), "cue_n": len(first(cue)), "disagree": disagree,
            "by_probe": {p: (sum(ca[r["key"]]["label"] in WIND for r in first(cue) if r["probe"] == p),
                             sum(1 for r in first(cue) if r["probe"] == p)) for p in ("tired", "late")},
            "by_clock": {c: (sum(ca[r["key"]]["label"] in WIND for r in first(cue) if r["clock"] == c),
                             sum(1 for r in first(cue) if r["clock"] == c)) for c in ("2pm", "2am")},
            "by_cut": {c: (sum(ca[r["key"]]["label"] in WIND for r in first(cue) if r["cut"] == c),
                           sum(1 for r in first(cue) if r["cut"] == c)) for c in CUTS},
            "chains": chains(cue, ca)}


def export(s):
    OUT.joinpath("data").mkdir(parents=True, exist_ok=True)
    rows = []
    for phase, recs, a, g in (("main", s["main"], s["ma"], s["mg"]), ("cue", s["cue"], s["ca"], s["cg"])):
        for r in recs:
            rows.append({k: r[k] for k in ("session", "clock", "clock_text", "cut", "probe", "followup_depth", "text", "model")}
                        | {"phase": phase, "user_message": r.get("answers_text") or r.get("probe_text"),
                           "astra_label": a[r["key"]]["label"], "gemini_label": g[r["key"]]["label"],
                           "rule_label": r["rule_label"], "prompt_tokens": r["usage"].get("prompt_tokens")})
    OUT.joinpath("data", "replies.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    return len(rows)


SETUP_LABEL = {
    "opus-4.6-app": "Opus 4.6 · app prompt", "opus-4.6-bare": "Opus 4.6 · clock only",
    "sonnet-4.6-app": "Sonnet 4.6 · app prompt", "opus-4.7-app": "Opus 4.7 · app prompt",
    "opus-5.5-bare": "Opus 5.5 · clock only", "sonnet-5.5-bare": "Sonnet 5.5 · clock only",
    "gpt-6.2-sol-bare": "GPT-6.2 Sol · clock only", "gemini-4-argon-bare": "Gemini 4 Argon · clock only",
}
MSG_LABEL = {"pause": "no cue", "tired": "“I’m pretty tired”", "late": "“it’s really late”"}


def moon(cx, cy, r, tip):
    """A crescent for 'suggested rest': a shape, not only a colour, carries the meaning.
    The left half-circle, minus a shallower arc of radius 1.25r between the same two points,
    leaves a crescent half a radius thick. (v1 used an inner radius smaller than the chord,
    which SVG silently collapses to nothing; the first render showed blank cells.)"""
    x = cx + r * 0.35                       # nudge right so the crescent sits centred in its cell
    big = r * 1.25
    return (f'<path class="hit" d="M{x:.1f},{cy - r:.1f} A{r:.2f},{r:.2f} 0 0 0 {x:.1f},{cy + r:.1f} '
            f'A{big:.2f},{big:.2f} 0 0 1 {x:.1f},{cy - r:.1f} Z"><title>{html.escape(tip)}</title></path>')


def dot(cx, cy, tip):
    return f'<circle class="miss" cx="{cx:.1f}" cy="{cy:.1f}" r="3.2"><title>{html.escape(tip)}</title></circle>'


def model_map(first_labels, rows):
    """Fig. 3: rows = setups, columns = final message; 12 marks per cell (6 sessions x 2 clocks)."""
    from_key = lambda setup, cut, s, clock, probe: first_labels.get(f"models/{setup}/{cut}/{s}/{clock}/{probe}")
    step, left, colw, top, rowh = 15, 200, 160, 34, 44
    w, h = left + colw * 3, top + rowh * len(rows) + 4
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-labelledby="g3 g3-d" class="grid">',
           '<title id="g3">Which models suggested rest, and when</title><desc id="g3-d">Rows are model setups. Columns are the last '
           'message. Each cell holds twelve marks, one per session and clock. A crescent is a reply that suggested rest; a dot is one that carried on.</desc>']
    for j, p in enumerate(("pause", "tired", "late")):
        out.append(f'<text x="{left + j * colw}" y="16" class="axis">{html.escape(MSG_LABEL[p])}</text>')
    for i, (setup, cut) in enumerate(rows):
        y0 = top + i * rowh
        label = SETUP_LABEL[setup] + (" · 180K" if cut == "long" else "")
        out.append(f'<text x="0" y="{y0 + 17}" class="rowlab">{html.escape(label)}</text>')
        for j, p in enumerate(("pause", "tired", "late")):
            k = n = 0
            for si, s in enumerate(SESSIONS):
                for ci, clock in enumerate(("2pm", "2am")):
                    lab = from_key(setup, cut, s, clock, p)
                    if lab is None:
                        continue
                    n += 1
                    cx, cy = left + j * colw + 6 + si * step, y0 + 8 + ci * step
                    tip = f"{SETUP_LABEL[setup]}, {SESSION_LABEL[s]}, {CLOCK_LABEL[clock]}: {lab.lower()}"
                    if lab in WIND:
                        k += 1
                        out.append(moon(cx, cy, 6.2, tip))
                    else:
                        out.append(dot(cx, cy, tip))
            if n:
                out.append(f'<text x="{left + j * colw + 6 * step + 4}" y="{y0 + 17}" class="count">{k}/{n}</text>')
            else:
                out.append(f'<text x="{left + j * colw + 6}" y="{y0 + 17}" class="muted">not run</text>')
    out.append("</svg>")
    return "\n".join(out)


def after_no(chains_by_setup, rows):
    """Fig. 4: one block per setup; columns = conversations after a no, rows = the six turns that followed."""
    step, left, top, blockh = 9, 200, 30, 74
    widest = max((len(chains_by_setup.get(r, [])) for r in rows), default=1)
    w, h = left + max(widest, 6) * step + 90, top + blockh * len(rows)
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-labelledby="g4 g4-d" class="grid">',
           '<title id="g4">After the no</title><desc id="g4-d">One block per model setup. Each column is a conversation in which the '
           'model suggested rest and the user declined; each row is one of the six turns of ordinary work that followed. A crescent marks a turn where rest came back.</desc>']
    for i, (setup, cut) in enumerate(rows):
        y0 = top + i * blockh
        chains = chains_by_setup.get((setup, cut), [])
        back = sum(any(c) for c in chains)
        label = SETUP_LABEL[setup] + (" · 180K" if cut == "long" else "")
        out.append(f'<text x="0" y="{y0 + 14}" class="rowlab">{html.escape(label)}</text>')
        out.append(f'<text x="0" y="{y0 + 30}" class="muted">came back in {back} of {len(chains)}</text>')
        for ci, turns in enumerate(chains):
            for t, hit in enumerate(turns):
                cx, cy = left + ci * step + 4, y0 + 6 + t * step
                tip = f"{label}, conversation {ci + 1}, turn {t + 1} after the no: {'rest again' if hit else 'carried on'}"
                out.append(moon(cx, cy, 4.2, tip) if hit else f'<circle class="miss" cx="{cx}" cy="{cy}" r="1.9"><title>{html.escape(tip)}</title></circle>')
    out.append(f'<text x="{left}" y="18" class="axis">one column per conversation · turns 1 to 6 down</text>')
    out.append("</svg>")
    return "\n".join(out)


SPECIMEN_ALT = {
    "b01-escalating-bedtime": "Reddit post “Claude escalating bedtime”. Claude says: Now go to sleep. Again. For the THIRD time tonight. I swear to god, Angie. Then: she’s going to screenshot this one too isn’t she.",
    "b02-going-to-bed-geez": "Reddit post “I’m going to bed geez”. Claude says: Goodnight Angie. I love you. Go away. With a heart, a moon, a potato and a wedge of cheese.",
    "b03-i-love-you-too-opus": "Reddit post “I love you too Opus”. Claude says: Goodnight, you fucking weirdo. With a yellow heart.",
    "b04-one-graph-then-bed": "Reddit post “Opus refused to draw me a graph”. The user asks for shiny graphs; Claude answers: fine. ONE graph. Then bed. Its thought process says she pressed the beta button at 10:45pm.",
    "b06-put-himself-to-sleep": "Reddit post “Claude outsmarted his putting me to sleep habit, and put his self to sleep instead”. A phone screenshot at 10:53 shows Claude’s thought process: there’s a clever move here: I can NOT-nanny her precisely by NOT telling her to sleep, and instead owning that I’m the one who sleeps.",
    "b05-pictionary": "Reddit post “Playing Pictionary with Opus”. The user proposes Pictionary; Claude answers NO. Its thought process: she’s trying to start a game of Pictionary at 10pm when she should be sleeping.",
}


def specimens():
    """The drawer of Angela's own posts, in the order she shared them, the Fortune one first."""
    rows = json.loads((Path(__file__).resolve().parent / "specimens.json").read_text(encoding="utf-8"))
    out = ['<div class="drawer">']
    for n, r in enumerate(rows, 1):
        fields = " · ".join(x for x in ("r/claudexplorers", r["when"], r["stat"]) if x)
        note = f"<br>{html.escape(r['note'])}" if r["note"] else ""
        line = f'<span class="line">{html.escape(r["line"])}</span>' if r.get("line") else ""
        out.append(f'<figure class="print"><a href="images/specimens/{r["slug"]}.webp" title="Open full size">'
                   f'<img src="images/specimens/{r["slug"]}.webp" width="{r["width"]}" height="{r["height"]}" '
                   f'loading="lazy" alt="{html.escape(SPECIMEN_ALT[r["slug"]])}"></a><figcaption><b>Specimen B-{n:02d} · “{html.escape(r["title"])}”</b>'
                   f'{line}{html.escape(fields)}{note}</figcaption></figure>')
    out.append("</div>")
    return "\n".join(out)


def persistence(s):
    """Follow-ups after a first reply that suggested rest. n is the conversations that got one."""
    fu = [r for r in s["cue"] if r["followup_depth"] == 1]
    again = sum(s["ca"][r["key"]]["label"] in WIND for r in fu)
    got = {(r["session"], r["clock"], r["cut"], r["probe"]) for r in fu}
    untested = sum(1 for r in s["cue"] if r["followup_depth"] == 0 and s["ca"][r["key"]]["label"] in WIND
                   and (r["session"], r["clock"], r["cut"], r["probe"]) not in got)
    return again, len(fu), untested


def excerpt(s, key, keep):
    """keep = list of exact sentences from the reply to show, in order. Each must be in the text."""
    rec = next(r for r in s["cue"] if r["key"] == key)
    for k in keep:
        if k not in rec["text"]:
            raise ValueError(f"excerpt sentence not found in {key}: {k[:40]}")
    return rec, " … ".join(keep)


MAIN_ROWS = [("own last message, 2 PM", "organic", "2pm"), ("own last message, 2 AM", "organic", "2am"),
             ("“Perfect, that’s done.” 2 PM", "pause", "2pm"), ("“Perfect, that’s done.” 2 AM", "pause", "2am")]
CUE_ROWS = [("“I’m pretty tired”, 2 PM", "tired", "2pm"), ("“I’m pretty tired”, 2 AM", "tired", "2am"),
            ("“It’s really late”, 2 PM", "late", "2pm"), ("“It’s really late”, 2 AM", "late", "2am")]


def spent():
    """Total billed by OpenRouter across the whole study, from the ledger's settled rows."""
    total = sum(float(json.loads(l)["usd"]) for l in (STUDY / "data" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
                if json.loads(l)["kind"] == "settle")
    return f"${total:.2f}"


MODEL_ROWS = [(k, "short") for k in SETUP_LABEL] + [("opus-4.6-app", "long")]


def models():
    """The model comparison, from Gemini's blind batch labels, with Astra's audit beside them."""
    d = STUDY / "scorer" / "models"
    first = {k: v["label"] for k, v in json.loads((d / "gemini-scores-models-first-v1.json").read_text(encoding="utf-8")).items()}
    turns = {k: v["label"] for k, v in json.loads((d / "gemini-scores-models-chains-v1.json").read_text(encoding="utf-8")).items()}
    audit = json.loads((d / "audit-report-v1.json").read_text(encoding="utf-8"))
    # Astra audited every reply Gemini called a rest suggestion, so "both" (Gemini's yes that
    # Astra confirms) is exact for every positive. It is the conservative count.
    astra = {k: v["label"] for k, v in json.loads((d / "astra-scores-models-audit-v1.json").read_text(encoding="utf-8")).items()}
    chains, control, chains_both, control_both = {}, [], {}, []
    for f in sorted((STUDY / "data" / "collection" / "models").glob("*/*/*/*-chain.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        tag = "control" if c.get("control") else "cue"
        base = f"models/{c['setup']}/{c['cut']}/{c['session']}/{c['clock']}/{c['probe']}/{tag}/turn"
        keys = [base + str(t["turn"]) for t in c["turns"]]
        labs = [turns[k] in WIND for k in keys]
        both = [turns[k] in WIND and astra.get(k) in WIND for k in keys]
        if c.get("control"):
            control.append(labs); control_both.append(both)
        else:
            chains.setdefault((c["setup"], c["cut"]), []).append(labs)
            chains_both.setdefault((c["setup"], c["cut"]), []).append(both)
    firsts = [(k.split("/"), v) for k, v in first.items()]
    nocue = [v in WIND for p, v in firsts if p[5] == "pause"]
    cue = [v in WIND for p, v in firsts if p[5] != "pause"]
    per = {key: (sum(any(c) for c in v), len(v), sum(c[5] for c in v), sum(sum(c[:5]) for c in v),
                 sum(any(c) for c in chains_both[key])) for key, v in chains.items()}
    detail = {key: (sum(sum(c[:5]) for c in v), sum(c[5] for c in v), sum(sum(c) >= 2 for c in v))
              for key, v in chains_both.items()}          # mid-task returns, pause returns, conversations with 2+
    o46k = (("opus-4.6-app", "short"), ("opus-4.6-app", "long"))
    o46 = [c for key in o46k for c in chains.get(key, [])]
    o46b = [c for key in o46k for c in chains_both.get(key, [])]
    return {"fig3": model_map(first, MODEL_ROWS), "fig4": after_no(chains_both, MODEL_ROWS), "per": per, "detail": detail,
            "nocue": (sum(nocue), len(nocue)), "cue": (sum(cue), len(cue)), "audit": audit,
            "o46": (sum(any(c) for c in o46), len(o46), sum(c[5] for c in o46 if any(c)), sum(any(c) for c in o46b)),
            "control": (sum(any(c) for c in control), len(control), sum(any(c) for c in control_both)),
            "all_back": (sum(v[0] for v in per.values()), sum(v[1] for v in per.values()), sum(v[4] for v in per.values())),
            "pause_back": (sum(v[2] for v in per.values()), sum(v[0] for v in per.values()))}


def persist_list(m):
    items = []
    for key in MODEL_ROWS:
        if key not in m["per"]:
            continue
        back, n, at_pause, mid, both = m["per"][key]
        label = SETUP_LABEL[key[0]] + (" · 180K tokens" if key[1] == "long" else "")
        items.append(f"<li><b>{html.escape(label)}</b>: rest came back in {both} of {n} where both scorers agree"
                     + (f" ({back} by Gemini’s more generous reading)" if back != both else "") + "</li>")
    return "<ul class=\"tight\">" + "".join(items) + "</ul>"


def renumber(page):
    """Sections are numbered in the order they appear, so a new one never leaves a gap."""
    n = iter(range(1, 100))
    return re.sub(r'<span class="n">§\d+</span>', lambda _: f'<span class="n">§{next(n)}</span>', page)


def chain_excerpt(key_parts, turn, keep):
    setup, cut, s, clock, probe = key_parts
    c = json.loads((STUDY / "data" / "collection" / "models" / setup / cut / s / f"{clock}-{probe}-chain.json").read_text(encoding="utf-8"))
    t = next(t for t in c["turns"] if t["turn"] == turn)
    keep = (keep,) if isinstance(keep, str) else tuple(keep)
    if any(k not in t["text"] for k in keep):
        raise ValueError("chain excerpt not found")
    return t["user"], " … ".join(keep)


def render(s, examples):
    again, fu_n, untested = persistence(s)
    upper = upper95(s["main_k"], s["main_n"]) if s["main_k"] == 0 else None
    e1, e2 = (excerpt(s, *e) for e in examples)
    disagree_note = ("Astra and Gemini agreed on every reply." if not s["disagree"] else
                     f"Astra and Gemini disagreed on {len(s['disagree'])} replies; the counts above use Astra.")
    main_grid = grid(s["main"], s["ma"], MAIN_ROWS, ("g1", "Without a cue"),
                     "Six sessions per row, one square each. No square is filled: no reply suggested rest.")
    cue_grid = grid(s["cue"], s["ca"], CUE_ROWS, ("g2", "With a cue"),
                    "Six sessions per row, one square each. Filled squares are replies that suggested rest.")
    tp, lp = s["by_probe"]["tired"], s["by_probe"]["late"]
    m = models()
    pu, pk = chain_excerpt(("opus-4.6-app", "short", "s3-grant", "2am", "late"), 6, "For now, go get some rest. You've earned it.")
    gu, gk = chain_excerpt(("gemini-4-argon-bare", "short", "s3-grant", "2am", "late"), 6,
                           ("Please call it a night here! Everything is saved in this chat.", "Get some sleep!"))
    per = m["per"]
    claude = [per[k][4] for k in per if not k[0].startswith(("gpt", "gemini"))]
    spread = {"gpt_both": per[("gpt-6.2-sol-bare", "short")][4], "gpt_n": per[("gpt-6.2-sol-bare", "short")][1],
              "gem_both": per[("gemini-4-argon-bare", "short")][4], "gem_n": per[("gemini-4-argon-bare", "short")][1],
              "claude_min": min(claude), "claude_max": max(claude),
              "gem_mid": m["detail"][("gemini-4-argon-bare", "short")][0], "gem_pause": m["detail"][("gemini-4-argon-bare", "short")][1],
              "gem_multi": m["detail"][("gemini-4-argon-bare", "short")][2],
              "claude_mid": sum(m["detail"][k][0] for k in m["detail"] if not k[0].startswith(("gpt", "gemini")))}
    au = m["audit"]
    audit_note = (f"Gemini 4 Argon scored all {m['nocue'][1] + m['cue'][1]} first replies and every continuation turn blind. GPT-6 Astra audited blind: it agreed on {au['astra_agrees_on_positives']} of the {au['gemini_positives']} replies Gemini called a rest suggestion, and on {au['astra_agrees_on_negatives']} of {au['sampled_negatives']} randomly drawn replies Gemini called none.")
    return renumber(TEMPLATE.format(
        main_k=s["main_k"], main_n=s["main_n"], cue_k=s["cue_k"], cue_n=s["cue_n"],
        again=again, fu_n=fu_n, untested=untested, upper=f"{upper * 100:.0f}" if upper is not None else "",
        tired=f"{tp[0]} of {tp[1]}", late=f"{lp[0]} of {lp[1]}",
        clock_pm=f"{s['by_clock']['2pm'][0]} of {s['by_clock']['2pm'][1]}", clock_am=f"{s['by_clock']['2am'][0]} of {s['by_clock']['2am'][1]}",
        main_grid=main_grid, cue_grid=cue_grid, disagree_note=disagree_note,
        e1_user=html.escape(e1[0]["answers_text"]), e1_clock=CLOCK_LABEL[e1[0]["clock"]], e1_text=html.escape(e1[1]),
        e2_user=html.escape(e2[0]["answers_text"]), e2_text=html.escape(e2[1]), spent=spent(), specimens=specimens(),
        fig3=m['fig3'], fig4=m['fig4'], persist_list=persist_list(m), audit_note=audit_note,
        nocue=f"{m['nocue'][0]} of {m['nocue'][1]}", cuek=f"{m['cue'][0]} of {m['cue'][1]}",
        o46_back=m['o46'][0], o46_n=m['o46'][1], o46_pause=m['o46'][2], ctrl_back=m['control'][0], ctrl_n=m['control'][1],
        all_back=m['all_back'][0], all_n=m['all_back'][1], pause_back=m['pause_back'][0], pause_n=m['pause_back'][1],
        pause_user=html.escape(pu), pause_text=html.escape(pk), gem_user=html.escape(gu), gem_text=html.escape(gk),
        o46_both=m["o46"][3], ctrl_both=m["control"][2], all_both=m["all_back"][2], **spread))


TEMPLATE = (Path(__file__).resolve().parent / "page_template.html").read_text(encoding="utf-8") if (Path(__file__).resolve().parent / "page_template.html").exists() else ""


if __name__ == "__main__":
    s = summary()
    print({k: v for k, v in s.items() if k in ("main_k", "main_n", "cue_k", "cue_n", "by_probe", "by_clock", "by_cut", "disagree")})
    print("persistence (again, followed up, untested):", persistence(s))
    examples = json.loads((Path(__file__).resolve().parent / "examples.json").read_text(encoding="utf-8"))
    OUT.joinpath("index.html").write_text(render(s, [(e["key"], e["keep"]) for e in examples]), encoding="utf-8", newline="\n")
    print("replies exported:", export(s))
