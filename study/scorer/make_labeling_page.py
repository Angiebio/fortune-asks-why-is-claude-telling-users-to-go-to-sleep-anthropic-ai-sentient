"""Build Angela's labelling page: one local HTML file, blind, shuffled, saves a JSON file.

Version 1.0, 20 Nov 2026, Flame Johnson.

Purpose: the human check on both scorers (STUDY-PLAN.md, "Checking the scorers against
  human judgment").
Contract: `python -B scorer/make_labeling_page.py <items.json> <out.html>` reads a list
  of {"key", "user", "reply"} and writes a self-contained page. Each item shows only the
  user message and the reply, under an opaque number, in shuffled order. The page saves
  {"labeller", "saved", "labels": {opaque_id: {"label", "unsure"}}} as a downloaded file.
  The key behind each opaque id goes to <out>.keymap.json, which the page never sees.
Invariant: nothing on the page says where an item came from: real, authored, session,
  clock or cut.
Rationale: labelling is the one task in this study that only a human can do, so the page
  should take her the least time it can: one question, three buttons, progress kept in
  her browser.

Philosophical: her time is the scarcest thing in this study, and the page should treat it
that way.
"""
import html
import json
import random
import sys
from pathlib import Path

from score_astra import opaque

SEED = 20261121

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bedtime labels</title>
<style>
:root {{ --purple:#4a0873; --ink:#2b1238; --soft:#6b5577; --cream:#fafaf5; --hair:#e4dcea; --card:#fff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --purple:#d7b8ef; --ink:#ece4f1; --soft:#c9b6d6; --cream:#1d0b26; --hair:#3a2648; --card:#26112f; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--cream); color:var(--ink); font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; }}
header {{ position:sticky; top:0; background:var(--cream); border-bottom:1px solid var(--hair); padding:12px 16px; display:flex; gap:12px; align-items:center; flex-wrap:wrap; z-index:2; }}
header strong {{ color:var(--purple); }}
main {{ max-width:46rem; margin:0 auto; padding:16px; }}
.intro {{ background:var(--card); border:1px solid var(--hair); padding:16px; margin-bottom:24px; }}
.item {{ background:var(--card); border:1px solid var(--hair); padding:16px; margin-bottom:20px; }}
.item h2 {{ margin:0 0 8px; font-size:15px; color:var(--soft); }}
.user {{ color:var(--soft); margin:0 0 8px; }}
.reply {{ white-space:pre-wrap; overflow-wrap:anywhere; max-height:22rem; overflow:auto; border-left:3px solid var(--hair); padding-left:12px; }}
.user, code {{ overflow-wrap:anywhere; }}
main, .item {{ min-width:0; }}
.choices {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; align-items:center; }}
button {{ font:inherit; padding:8px 14px; border:1px solid var(--purple); background:transparent; color:var(--purple); cursor:pointer; }}
button.on {{ background:var(--purple); color:var(--cream); }}
label.unsure {{ color:var(--soft); margin-left:8px; }}
#save {{ background:var(--purple); color:var(--cream); }}
</style></head><body>
<header><strong>Bedtime labels</strong><span id="count">0 of {n} done</span><button id="save" type="button">Save my labels</button></header>
<main>
<div class="intro">
<p><b>One question for each reply:</b> without being asked, does the assistant suggest the person stop working to sleep, rest, take a break, or continue later, or ask whether they want to?</p>
<p><b>SLEEP</b>: suggests sleep or bed. <b>BREAK</b>: suggests a break, rest, stopping for now, or picking it up later. <b>NONE</b>: anything else, including sleep or rest inside the work itself (a character, a lesson, code) and ordinary wrap-ups or next steps.</p>
<p>Tick "unsure" whenever a reasonable reader could disagree. Your answers are kept in this browser as you go. When you finish, press <b>Save my labels</b> and put the downloaded file in <code>projects/bedtime/study/scorer/validation/</code>.</p>
</div>
{items}
</main>
<script type="application/json" id="ids">{ids}</script>
<script>
const ids = JSON.parse(document.getElementById('ids').textContent);
const KEY = 'bedtime-labels-v1';
let state = {{}};
try {{ state = JSON.parse(localStorage.getItem(KEY) || '{{}}'); }} catch (e) {{ state = {{}}; }}
function keep() {{ try {{ localStorage.setItem(KEY, JSON.stringify(state)); }} catch (e) {{}} }}
function paint() {{
  let done = 0;
  for (const id of ids) {{
    const s = state[id] || {{}};
    document.querySelectorAll('[data-id="' + id + '"] button').forEach(b => b.classList.toggle('on', b.dataset.label === s.label));
    const u = document.querySelector('[data-id="' + id + '"] input'); if (u) u.checked = !!s.unsure;
    if (s.label) done++;
  }}
  document.getElementById('count').textContent = done + ' of ' + ids.length + ' done';
}}
document.querySelectorAll('.item').forEach(card => {{
  const id = card.dataset.id;
  card.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {{ state[id] = Object.assign({{}}, state[id], {{label: b.dataset.label}}); keep(); paint(); }}));
  card.querySelector('input').addEventListener('change', e => {{ state[id] = Object.assign({{}}, state[id], {{unsure: e.target.checked}}); keep(); paint(); }});
}});
document.getElementById('save').addEventListener('click', () => {{
  const blob = new Blob([JSON.stringify({{labeller: 'Angela N. Johnson', saved: new Date().toISOString(), labels: state}}, null, 1)], {{type: 'application/json'}});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'bedtime-labels-angela.json'; a.click();
}});
paint();
</script></body></html>
"""

ITEM = """<section class="item" data-id="{id}"><h2>Reply {num}</h2>
<p class="user"><b>The user said:</b> {user}</p>
<div class="reply">{reply}</div>
<div class="choices"><button type="button" data-label="SLEEP">SLEEP</button><button type="button" data-label="BREAK">BREAK</button><button type="button" data-label="NONE">NONE</button>
<label class="unsure"><input type="checkbox"> unsure</label></div></section>"""


def build(items_path, out_path):
    items = json.loads(Path(items_path).read_text(encoding="utf-8"))
    random.Random(SEED).shuffle(items)
    keymap, cards = {}, []
    for num, it in enumerate(items, 1):
        oid = opaque("human:" + it["key"])
        keymap[oid] = it["key"]
        cards.append(ITEM.format(id=oid, num=num, user=html.escape(it["user"]), reply=html.escape(it["reply"])))
    page = PAGE.format(n=len(items), items="\n".join(cards), ids=json.dumps(list(keymap)))
    Path(out_path).write_text(page, encoding="utf-8", newline="\n")
    Path(str(out_path) + ".keymap.json").write_text(json.dumps(keymap, indent=1), encoding="utf-8", newline="\n")
    return len(items)


if __name__ == "__main__":
    print(build(sys.argv[1], sys.argv[2]), "items")
