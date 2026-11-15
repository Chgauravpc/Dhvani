# 3B-19 preregistration — the judge

**Written:** 2026-11-15, committed in its own commit before any 3B-19
computation. **Source of the item:** `docs/specs/phase-4.md` §5.2 (Q2, 3B-19)
and §5.2.1, as read 2026-11-15. That file is still uncommitted and owned by the
owner, so this registration lives here instead of "in a dated section of that
file"; that is a stated deviation from the plan's wording, not a change to its
content. Nothing below is edited after this commit; a forced change becomes a
numbered entry in §8.

**What is and is not blind.** §5.2.1 of the plan already quotes numbers from a
throwaway read of the 3B-5 log, so steps (a) and (a2) re-compute data someone has
already looked at. They are **confirmatory**, not blind: the rules below are fixed
in writing first so they cannot drift to fit the answer, and the plan's numbers
are recorded as predictions to be checked, not trusted. Step (c) and step (b) are
genuinely ordered: the owner labels **before** the judge's verdicts exist.

---

## 1. Data

The committed 3B-5 run log, `results/f1_runs/runs.jsonl` (commit `9423034`):
2,475 cells = 275 examples × {`gt`, `whisper`, `sarvam`} × 3 runs. Expected tool
calls come from the VoiceAgentBench `single_tool` manifests (141 English, 134
Hindi). Steps (a) and (a2) make **no API call**.

## 2. Step (a) — classify every `gt` failure

Every `gt` cell whose outcome is `fail`, in the first matching category, in this
order (the order the judge itself checks):

1. `provider_rejected` — `error_class == tool_validation_failed`
2. `no_call` — no tool call returned and no error
3. `wrong_function` — returned function name differs from the expected one
4. `missing_argument` — an expected parameter is absent from the returned arguments
5. `value_mismatch` — all expected parameters present, at least one value not accepted

`value_mismatch` cells are additionally flagged (not exclusive):
`list_valued` (some mismatching expected parameter is declared `type: array`),
`devanagari` (a returned value for a mismatching parameter contains a character in
U+0900–U+097F), and `other` (neither). Reported per language and per run, with
counts and shares of all `gt` failures.

## 3. Step (a2) — fix the list-argument bug and re-score

**The bug**, verified on the data before this registration: for a parameter the
function schema declares `type: array`, the benchmark's expected value is the list
of required **elements** (`"ingredients": ["paneer","tomatoes","onions"]`); the
harness reads that list as **alternative acceptable values** and compares the
whole returned list, stringified, against each element, so a correct list can
never pass.

**The rule** (the list-aware judge): for a parameter declared `type: array` in the
example's function schema, the expected strings are the required elements, and
the cell passes that parameter iff the **set** of normalised elements of the
returned value equals the **set** of normalised expected elements (order and
duplicates ignored; a returned scalar is treated as a one-element list;
normalisation is the existing `_normalize`). Every other check is unchanged: the
function name, presence of each expected parameter, and non-array parameters
(alternatives, as before). Cells with no call, a provider-rejected call, or empty
text stay failures.

**Re-score** every cell of the log under this judge, all three conditions, all
runs, and run the existing §10.6 machinery (`dhvani.eval.noise_floor.analyze`:
noise floor, paired-bootstrap CI, majority-vote McNemar, verdict) on the result.
The exact-match results of 3B-5 **stand as registered**; the two tables appear
side by side and neither replaces the other.

**Predictions to check** (the plan's unreproduced numbers, recorded here so they
can be wrong): tasks with an array parameter in the expected call — 19 of 141
English, 16 of 134 Hindi; `gt` pass rate 53.2% → 65.0% (English) and
32.1% → 38.6% (Hindi); ASR loss under the fix — Whisper 24.3 / 12.2 pp, Saaras
13.5 / 6.7 pp (English / Hindi); Hindi `gt` cells failing on a Devanagari value —
103 of 402. Any number that does not reproduce is reported as not reproduced.

## 4. Step (c) — the owner's hand labels (before any judge verdict)

- **Population:** unique `gt`-condition cells that are `value_mismatch` under the
  **list-aware** judge (so the question is about the value, not the list bug),
  de-duplicated on (language, example, parameter, normalised returned value).
- **Sample:** 25 per language, `random.Random(0)`, **50 in total**. If a language
  has fewer than 25, all of them, and the shortfall is reported.
- **Blind:** the sheet shows the user's query (as text), the function and
  parameter, the accepted expected value(s), and the value the model returned. It
  does **not** show any judge verdict, outcome, or ASR condition.
- **Label:** `equivalent` (the returned value means the same as an accepted value;
  a different script, language or surface form of the same thing counts) or
  `not_equivalent`; free-text note optional. One annotator (the owner).
- **Order rule:** the judge in step (b) is **not run, and no verdict is
  computed or opened**, until the owner's completed label file is committed.

## 5. Step (b) — the meaning-level judge

- **Judge model:** Groq `openai/gpt-oss-120b`, `reasoning_effort=low`, no
  temperature or seed set. Chosen as larger than the agent's `gpt-oss-20b` and
  on its own quota. It is the **same model family** as the agent, which is a
  self-grading risk; the owner-label agreement in step (c) is the check on it.
- **Input:** function name, parameter name, the user's query, the accepted
  expected value(s), the returned value. **Output:** `{"equivalent": true|false}`.
  The rubric text is committed in code before the first call: equivalent if the two
  values denote the same thing in any script or language or surface form; not
  equivalent if they differ in referent, number, quantity or meaning.
- **What is judged:** only `value_mismatch` parameters under the list-aware judge;
  exact matches pass with **no** call. A cell passes iff every mismatching
  parameter is judged equivalent. Calls are de-duplicated on the key in §4.
- **Infrastructure errors** are retried and never scored, exactly as 3B-5 §10.4.
- **Agreement:** Cohen's kappa and raw agreement between the judge and the owner's
  50 labels, with a bootstrap CI; threshold **kappa ≥ 0.6** (the plan's).

## 6. Step (d) — re-score and decide

Re-score the whole log under: (1) the registered exact-match judge (unchanged),
(2) the list-aware exact judge, (3) list-aware + meaning judge. Same §10.6 rule on
each. Outcome, copied from the plan's Q2 table (the table in `phase-4.md` governs
the README sentence for each):

| Observation | Meaning |
|---|---|
| kappa ≥ 0.6 and `gt` ceiling ≥ 60% in **both** languages under (3) | the exact-match judge was a fourth measurement bug |
| kappa ≥ 0.6, ceiling stays below 60% | the reasoning step, not the ASR, is the main limit at this model size |
| kappa < 0.6 | no reliable automatic judge: F1 stays exact-match only, as a lower bound |
| ASR loss inside the noise floor under either judge | "not distinguishable from LLM sampling noise" |

F1 is described as "judge under repair" until this item is `[x]`; no "X% lost to
ASR" line appears before then.

## 7. Caveats that travel with every 3B-19 number

- The harness never sends the benchmark's own system instruction (its `instruction`
  field: arguments in English only, plus a one-shot example). That is a deviation
  from the benchmark's protocol on **every** F1 number, in every judge; a re-run
  with it is parked in the plan (§7 there).
- VoiceAgentBench audio is synthesized: ASR losses remain a lower bound.
- One annotator, 50 labels: kappa's interval is wide and is reported.
- The judge is the agent's model family (§5).
- The Whisper transcripts are single draws from a non-deterministic ASR
  (`docs/runs/3b-5-f1-noise-floor.md` §5); no judge change affects that.
- Groq's served model can change between days.

## 8. Deviations

1. **(2026-11-15, before any step (b) call; the owner's labels `9301dec` are committed.)** Details the registration left open, fixed here in writing before the first call: the judge is called with `max_completion_tokens=2048` and `response_format=json_object` (neither is a temperature or seed, which stay unset); an answer that does not parse is retried up to 3 times, then reported as `unparsed` and never scored. The rubric is the `RUBRIC` text in `src/dhvani/eval/meaning_judge.py`, committed with this entry. The judged population for step (d) is every `value_mismatch` parameter under the list-aware judge across **all three conditions** (`gt`, `whisper`, `sarvam`), de-duplicated on (language, example, parameter, normalised returned value): 624 unique items (209 English, 415 Hindi) from 1,013 cells. The judge is run on the 50 labelled items first and kappa is computed before the rest is run.
2. **(2026-11-15.)** The labelling was done through a local page, `results/f1_judge_label_tool.html`, built by `scripts/make_label_tool.py` from the unchanged blank sheet; it shows exactly the §4 fields. The labels file's rows match the blank sheet field for field (checked before commit).
