# 3B-19 (b), (c), (d) — the meaning-level judge, agreement, and the three-judge re-score

**Run:** 2026-11-15. **Preregistration:** `docs/runs/3b-19-preregistration.md` (§8
deviations 1–2 were written before the first judge call). **Code:**
`src/dhvani/eval/meaning_judge.py`, `scripts/run_f1_meaning_judge.py`,
`scripts/analyze_f1_meaning_judge.py`. **Results:** `results/f1_meaning_judge.json`,
`results/f1_meaning_judge/verdicts.jsonl`. **Owner labels:**
`results/f1_judge_labels_owner.csv` (commit `9301dec`, before any verdict existed).

## What ran

- Judge: Groq `openai/gpt-oss-120b`, `reasoning_effort=low`, no temperature or seed.
  Same model family as the agent (`gpt-oss-20b`), which is the self-grading risk the
  preregistration names; the owner labels are the check on it.
- 624 judge calls: the 50 owner-labelled items first (agreement computed and committed,
  `a2dd7e6`), then the other 574. Every item scored: 0 unparsed, 0 incomplete.
- Population: every list-aware `value_mismatch` parameter across `gt`, `whisper`,
  `sarvam`, de-duplicated (209 English, 415 Hindi items from 1,013 cells).
  Exact matches pass with no call.

## Agreement with the owner's 50 labels (the gate)

| | Value |
|---|---|
| Cohen's kappa | **0.682** (bootstrap 95% CI 0.465 – 0.878) |
| Raw agreement | 84.0% (42 of 50); English 20/25, Hindi 22/25 |
| Judge "equivalent", owner "not" | 2 |
| Judge "not", owner "equivalent" | 6 |

The threshold is kappa ≥ 0.6: met by the point estimate. The interval's lower end
(0.465) is below it, so one annotator and 50 labels cannot rule out a kappa under
0.6; the preregistration said the interval would be wide.

The judge is **stricter** than the owner: 6 of its 8 disagreements are cases it
rejects and the owner accepted. Reading them: items 6 (`3287000` vs `328700`), 21 and 46
(returned lists whose values differ from the accepted ones), 41 (`vegan` for
`vegetarian`) and 40 (`Owner` for `Landlord`) look like real differences of number or
meaning, so these may be label slips rather than judge errors; item 15 (a time as an
ISO timestamp) is a format difference the owner accepted. Items 17 (`वाराणसी, वाराणसी`
for `Varanasi, Uttar Pradesh`) and 36 (`Riyal` for `SAR`) are the two where the judge
accepted and the owner did not. **The labels were not changed.** The owner may want to
re-read items 6, 21, 40, 41 and 46; any change would be a numbered deviation, with the
kappa recomputed and both versions reported.

## Ground-truth ceiling (`gt` pass rate)

| | Registered exact match | List-aware | List-aware + meaning judge |
|---|---|---|---|
| English | 53.2% | 65.0% | **73.3%** |
| Hindi | 32.1% | 38.6% | **64.7%** |

## ASR loss under each judge (GT minus real, mean over 3 runs, paired-bootstrap 95% CI; majority-vote McNemar; §10.6 rule)

| Judge | Language / ASR | Noise floor | Loss (pp) | CI | GT-only / real-only | p | Verdict |
|---|---|---|---|---|---|---|---|
| exact (as run) | English / Whisper | 6.4 | 19.6 | 13.2, 26.5 | 29 / 2 | 5e-7 | costs |
| | English / Saaras | 6.4 | 12.3 | 7.1, 17.7 | 20 / 3 | 5e-4 | costs |
| | Hindi / Whisper | 1.5 | 10.2 | 3.7, 16.9 | 25 / 7 | 0.002 | costs |
| | Hindi / Saaras | 1.5 | 6.0 | 1.0, 10.9 | 16 / 7 | 0.093 | not distinguishable |
| list-aware | English / Whisper | 7.8 | 24.3 | 17.0, 31.9 | 37 / 3 | 2e-8 | costs |
| | English / Saaras | 7.8 | 13.5 | 7.6, 19.9 | 23 / 5 | 9e-4 | costs |
| | Hindi / Whisper | 3.7 | 12.2 | 5.2, 19.4 | 29 / 8 | 8e-4 | costs |
| | Hindi / Saaras | 3.7 | 6.7 | 1.5, 11.9 | 17 / 7 | 0.064 | not distinguishable |
| list-aware + meaning | English / Whisper | 5.0 | 20.6 | 13.7, 27.9 | 31 / 3 | 8e-7 | costs |
| | English / Saaras | 5.0 | 10.4 | 4.7, 16.3 | 18 / 5 | 0.011 | costs |
| | Hindi / Whisper | 3.7 | 22.9 | 15.2, 30.8 | 41 / 7 | 6e-7 | costs |
| | Hindi / Saaras | 3.7 | 7.7 | 2.2, 13.4 | 19 / 9 | 0.087 | not distinguishable |

## What it says, by the plan's Q2 table

- **Kappa ≥ 0.6 and the ceiling ≥ 60% in both languages under the meaning judge**
  (73.3% English, 64.7% Hindi): the row that reads "the exact-match judge was a fourth
  measurement bug". The Hindi ceiling moves from 32.1% to 64.7%. How much of that comes from the
  judge accepting Devanagari values for English-expected arguments was not broken down.
- **ASR loss is detected in three of four arms under every judge; Hindi/Saaras is
  "not distinguishable from LLM sampling noise" under all three** (McNemar p 0.06–0.09).
  Under the meaning judge the Hindi/Whisper loss doubles (10.2 → 22.9 pp): with the
  judge bug gone, Whisper's Hindi transcripts cost more, not less.
- Nothing here is "X% of the gap is the ear". The measured quantity is the loss in
  task success from replacing ground-truth text with an ASR transcript, per arm.

## Caveats that stay

- The judge is the agent's model family; one annotator, 50 labels; kappa CI 0.465–0.878.
  The judge is stricter than the owner, so the meaning-judge ceiling may be a lower
  bound on a human-judged ceiling, and a few owner labels look like slips (above).
- The benchmark's own system instruction (English-only arguments plus a one-shot
  example) is never sent by this harness; every number here is under that deviation.
- VoiceAgentBench audio is synthesized: ASR losses stay a lower bound.
- Whisper transcripts are single draws from a non-deterministic ASR (3B-5 run note);
  that variance is in no CI.
- McNemar and the bootstrap resample examples, not the clusters of arguments within
  them; Groq's served model can change between days.
- **Status:** 3B-19 is `[?]` here: the owner's review, and the decision on the README's F1
  wording, are the owner's. The README still says F1 is under repair.
