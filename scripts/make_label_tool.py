"""Build a one-page local labelling tool for the 3B-19 owner labels.

    uv run python scripts/make_label_tool.py
    # then open results/f1_judge_label_tool.html in a browser

Reads results/f1_judge_labels_blank.csv (the blind sheet: query, function,
parameter, accepted value, returned value -- no judge verdict, no ASR condition)
and writes a self-contained HTML page. Keys: E = equivalent, N = not_equivalent,
arrows / Enter move, progress autosaves in the browser. "Download CSV" writes a
file with the same columns as the blank sheet; save it as
results/f1_judge_labels_owner.csv and commit it. The page makes no network call.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

SRC = Path("results/f1_judge_labels_blank.csv")
OUT = Path("results/f1_judge_label_tool.html")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>3B-19 labels</title>
<style>
body{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:1.5rem auto;padding:0 1rem}
.card{border:1px solid #8886;border-radius:8px;padding:1rem 1.25rem}
.k{font-size:.8rem;text-transform:uppercase;opacity:.65;margin-top:.7rem}
.v{font-size:1.25rem;word-break:break-word}
button{font:inherit;padding:.5rem 1rem;margin:.25rem .25rem 0 0;cursor:pointer}
.on{outline:3px solid #2a7;font-weight:600}
#bar{height:8px;background:#8883;border-radius:4px;margin:.5rem 0}
#bar div{height:8px;background:#2a7;border-radius:4px}
textarea{width:100%;font:inherit}
</style></head><body>
<h2>3B-19: is the returned value equivalent to an accepted value?</h2>
<p><b>equivalent</b>: the returned value means the same as an accepted value (a
different script, language or surface form of the same thing counts).
<b>not_equivalent</b>: it does not. Keys: <b>E</b> / <b>N</b>, <b>&larr; &rarr;</b> to move.</p>
<div id="bar"><div></div></div><div id="count"></div>
<div class="card" id="card"></div>
<p><button id="e">E: equivalent</button><button id="n">N: not equivalent</button>
<button id="prev">&larr; prev</button><button id="next">next &rarr;</button></p>
<p>Note (optional)<br><textarea id="note" rows="2"></textarea></p>
<p><button id="dl">Download CSV</button> <span id="warn"></span></p>
<script>
const ROWS = __ROWS__;
const KEY = "dhvani-3b19-labels";
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
let i = 0;
for (let j = 0; j < ROWS.length; j++) if (!(st[ROWS[j].item] || {}).label) { i = j; break; }
const $ = (id) => document.getElementById(id);
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} };
function esc(s) { return s.replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function show() {
  const r = ROWS[i], s = st[r.item] || {};
  $("card").innerHTML =
    `<div class="k">item ${r.item} of ${ROWS.length} &middot; ${r.language}</div>` +
    `<div class="k">user query</div><div class="v">${esc(r.user_query)}</div>` +
    `<div class="k">function &middot; parameter</div><div class="v">${esc(r.function)} &middot; <b>${esc(r.parameter)}</b></div>` +
    `<div class="k">accepted value(s)</div><div class="v">${esc(r.accepted_values)}</div>` +
    `<div class="k">model returned</div><div class="v">${esc(r.returned_value)}</div>`;
  $("e").className = s.label === "equivalent" ? "on" : "";
  $("n").className = s.label === "not_equivalent" ? "on" : "";
  $("note").value = s.note || "";
  const done = ROWS.filter(x => (st[x.item] || {}).label).length;
  $("count").textContent = `${done} / ${ROWS.length} labelled`;
  $("bar").firstChild.style.width = (100 * done / ROWS.length) + "%";
}
function set(label) {
  const r = ROWS[i]; st[r.item] = Object.assign(st[r.item] || {}, {label});
  save(); if (i < ROWS.length - 1) i++; show();
}
const go = (d) => { i = Math.max(0, Math.min(ROWS.length - 1, i + d)); show(); };
$("e").onclick = () => set("equivalent"); $("n").onclick = () => set("not_equivalent");
$("prev").onclick = () => go(-1); $("next").onclick = () => go(1);
$("note").oninput = (ev) => { const r = ROWS[i]; st[r.item] = Object.assign(st[r.item] || {}, {note: ev.target.value}); save(); };
document.addEventListener("keydown", (ev) => {
  if (ev.target.tagName === "TEXTAREA") return;
  const k = ev.key.toLowerCase();
  if (k === "e") set("equivalent"); else if (k === "n") set("not_equivalent");
  else if (k === "arrowleft") go(-1); else if (k === "arrowright" || k === "enter") go(1);
});
const q = (s) => '"' + String(s).replace(/"/g, '""') + '"';
$("dl").onclick = () => {
  const missing = ROWS.filter(r => !(st[r.item] || {}).label).length;
  $("warn").textContent = missing ? `${missing} still unlabelled` : "";
  const head = "item,language,user_query,function,parameter,accepted_values,returned_value,label (equivalent / not_equivalent),note";
  const lines = ROWS.map(r => [r.item, r.language, q(r.user_query), q(r.function), q(r.parameter),
    q(r.accepted_values), q(r.returned_value), (st[r.item] || {}).label || "", q((st[r.item] || {}).note || "")].join(","));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([head + "\\n" + lines.join("\\n") + "\\n"], {type: "text/csv"}));
  a.download = "f1_judge_labels_owner.csv"; a.click();
};
show();
</script></body></html>
"""


def main() -> None:
    with SRC.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader)
        rows = [
            {
                "item": r[0],
                "language": r[1],
                "user_query": r[2],
                "function": r[3],
                "parameter": r[4],
                "accepted_values": r[5],
                "returned_value": r[6],
            }
            for r in reader
        ]
    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(PAGE.replace("__ROWS__", payload), encoding="utf-8")
    print(f"wrote {OUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
