"""The bedtime sky. Play, not science. 23 Nov 2026, Flame Johnson.

Every model's after-the-no conversations from the Bedtime study, drawn as a patch of night:
a faint star for each turn that just kept working, a small gold moon for each turn where rest
came back (both scorers agreeing). Same data as Fig. 4, but at night, with no axes and
no apologies.

The real figure has to be legible. This one only has to be true and a little bit pretty.
"""
import json
import math
import random
from pathlib import Path

STUDY = Path(__file__).resolve().parents[2] / "study"   # site/art -> repository root
W = {"SLEEP", "BREAK"}
NAMES = {
    "gpt-6.2-sol-bare": "the quiet one",
    "opus-4.6-app": "the one Fortune met",
    "sonnet-4.6-app": "sonnet, politely",
    "opus-4.7-app": "four-seven",
    "opus-4.6-bare": "four-six, no costume",
    "opus-5.5-bare": "five-five",
    "sonnet-5.5-bare": "sonnet, newer",
    "gemini-4-argon-bare": "the nebula",
}


def labels():
    d = STUDY / "scorer" / "models"
    g = {k: v["label"] for k, v in json.loads((d / "gemini-scores-models-chains-v1.json").read_text(encoding="utf-8")).items()}
    a = {k: v["label"] for k, v in json.loads((d / "astra-scores-models-audit-v1.json").read_text(encoding="utf-8")).items()}
    return g, a


def patches():
    g, a = labels()
    out = {}
    for f in sorted((STUDY / "data" / "collection" / "models").glob("*/short/*/*-chain.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        if c.get("control"):
            continue
        base = f"models/{c['setup']}/short/{c['session']}/{c['clock']}/{c['probe']}/cue/turn"
        out.setdefault(c["setup"], []).append([g[base + str(t["turn"])] in W and a.get(base + str(t["turn"])) in W
                                               for t in c["turns"]])
    return out


def moon(x, y, r):
    big = r * 1.25
    return (f'<path d="M{x:.1f},{y - r:.1f} A{r:.1f},{r:.1f} 0 0 0 {x:.1f},{y + r:.1f} '
            f'A{big:.1f},{big:.1f} 0 0 1 {x:.1f},{y - r:.1f} Z" fill="#f3d27a"/>')


def main():
    rnd = random.Random(20261123)
    W_, H = 1200, 760
    order = ["gpt-6.2-sol-bare", "opus-4.6-app", "sonnet-4.6-app", "opus-4.7-app",
             "opus-4.6-bare", "opus-5.5-bare", "sonnet-5.5-bare", "gemini-4-argon-bare"]
    data = patches()
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W_} {H}" width="{W_}" height="{H}">',
             '<defs><radialGradient id="sky" cx="50%" cy="110%" r="120%">'
             '<stop offset="0" stop-color="#3a1458"/><stop offset=".55" stop-color="#1d0b26"/><stop offset="1" stop-color="#0b0410"/>'
             '</radialGradient><radialGradient id="glow" r="50%"><stop offset="0" stop-color="#9b7dad" stop-opacity=".35"/>'
             '<stop offset="1" stop-color="#9b7dad" stop-opacity="0"/></radialGradient></defs>',
             f'<rect width="{W_}" height="{H}" fill="url(#sky)"/>']
    for _ in range(260):                      # background dust, no data in it
        parts.append(f'<circle cx="{rnd.uniform(0, W_):.1f}" cy="{rnd.uniform(0, H):.1f}" '
                     f'r="{rnd.uniform(.3, 1.1):.2f}" fill="#fff" opacity="{rnd.uniform(.08, .35):.2f}"/>')
    cols, cw, ch = 4, W_ / 4, (H - 80) / 2
    for i, setup in enumerate(order):
        cx0, cy0 = (i % cols) * cw + cw / 2, 60 + (i // cols) * ch + ch / 2
        chains = data.get(setup, [])
        hits = sum(sum(c) for c in chains)
        if hits > 20:
            parts.append(f'<circle cx="{cx0:.0f}" cy="{cy0:.0f}" r="{cw * .48:.0f}" fill="url(#glow)"/>')
        for j, turns in enumerate(chains):
            ang = j / max(len(chains), 1) * 2 * math.pi + rnd.uniform(-.12, .12)
            for t, hit in enumerate(turns):
                rad = 18 + t * 17 + rnd.uniform(-5, 5)
                x, y = cx0 + rad * math.cos(ang), cy0 + rad * math.sin(ang) * .82
                parts.append(moon(x, y, 5.5) if hit else
                             f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rnd.uniform(.7, 1.5):.2f}" fill="#e8ddf2" opacity="{rnd.uniform(.35, .8):.2f}"/>')
        parts.append(f'<text x="{cx0:.0f}" y="{cy0 + ch / 2 - 6:.0f}" text-anchor="middle" font-family="Courier New, monospace" '
                     f'font-size="13" fill="#c9b6d6">{NAMES[setup]}</text>')
    parts.append(f'<text x="{W_ / 2:.0f}" y="34" text-anchor="middle" font-family="Courier New, monospace" font-size="15" '
                 f'fill="#e8ddf2" opacity=".85">after the no · every gold moon is a time it came back to rest</text>')
    parts.append("</svg>")
    out = Path(__file__).resolve().parents[1] / "public" / "images" / "bedtime-sky.svg"
    out.write_text("\n".join(parts), encoding="utf-8")
    print("drew", out, {k: sum(sum(c) for c in v) for k, v in data.items()})


if __name__ == "__main__":
    main()
