# 3B-19 steps (a) and (a2) — results note

**Computed:** 2026-11-15. **Protocol:** `docs/runs/3b-19-preregistration.md`
(commit `a6ae348`, before any of this). **Data:** the committed 3B-5 run log
(2,475 cells). **No API call was made.** Script `scripts/audit_f1_judge.py`;
results `results/f1_judge_audit.json`. Steps (b), (c) and (d) are **not done**:
(c) waits for the owner's labels, and (b) must not run before they are committed.

These are **confirmatory**, not blind: the plan (`phase-4.md` §5.2.1) had already
quoted numbers from a throwaway read of the same log (see the registration).

## Sanity checks

- The registered judge, re-applied to every logged tool call, reproduces all 2,475
  logged outcomes (0 disagreements).
- Re-analysing the unchanged log reproduces `results/f1_noise_floor.json` exactly.

## (a) Why ground-truth cells fail (registered judge)

| | English | Hindi |
|---|---|---|
| ground-truth cells | 423 | 402 |
| failures | 198 (46.8%) | 273 (67.9%) |
| `value_mismatch` | 152 | 197 |
| `missing_argument` | 27 | 57 |
| `provider_rejected` | 10 | 8 |
| `no_call` | 9 | 11 |
| `wrong_function` | 0 | 0 |

Most failures (77% English, 72% Hindi) are a returned value the judge does not
accept, not a wrong function or no call. Flags on those `value_mismatch` cells
(not exclusive, so they overlap): English — list-valued 73, other 79, Devanagari 0;
Hindi — Devanagari 94, list-valued 63, other 60.

## (a2) The list-argument bug, and the re-score

For a parameter the schema declares `type: array`, the benchmark's expected strings
are the required elements; the registered judge reads them as alternatives, so a
correct list can never pass. Re-scored with the list-aware rule (set equality of
normalised elements; everything else unchanged):

| Ground-truth pass rate | registered | list-aware |
|---|---|---|
| English | 53.2% | **65.0%** |
| Hindi | 32.1% | **38.6%** |

ASR loss under both judges (mean over three runs; paired-bootstrap 95% CI;
majority-vote McNemar), same §10.6 rule:

| Arm | registered | list-aware |
|---|---|---|
| English / Whisper | 19.6 pp [13.2, 26.5] — costs | 24.3 pp [17.0, 31.9] — costs |
| English / Sarvam | 12.3 pp [7.1, 17.7] — costs | 13.5 pp [7.6, 19.9] — costs |
| Hindi / Whisper | 10.2 pp [3.7, 16.9] — costs | 12.2 pp [5.2, 19.4] — costs |
| Hindi / Sarvam | 6.0 pp [1.0, 10.9] — noise | 6.7 pp [1.5, 11.9] — noise (McNemar p = 0.064) |
| noise floor (GT) | EN 6.4, HI 1.5 pp | EN 7.8, HI 3.7 pp |

**The fix moves the ground-truth ceiling but not the story**: the verdicts are the
same in all four arms, and losses change by 1–5 pp. Hindi ground truth still passes
only 38.6%.

## Predictions from the registration, checked

| Prediction | Result |
|---|---|
| tasks with an array parameter: 19 of 141 English, 16 of 134 Hindi | **reproduced under one definition**: 19 / 16 are tasks whose array parameter has ≥ 2 expected elements; counting any array parameter gives 25 / 22 |
| ground-truth pass 53.2 → 65.0 (English), 32.1 → 38.6 (Hindi) | reproduced |
| ASR loss under the fix: Whisper 24.3 / 12.2, Saaras 13.5 / 6.7 | reproduced |
| Hindi ground-truth failures on a Devanagari value: 103 of 402 | **not reproduced: 94** (my definition: a mismatching parameter whose returned value contains Devanagari; the plan's count may have used a wider one) |

## What this does and does not show

- It shows the exact-match judge had a real, fixable bug (list arguments) that cost
  about 12 points of English and 6 of Hindi ground truth.
- It does **not** show that the remaining ~35% (English) / ~61% (Hindi) failures are
  the judge's fault.
  The `other` value mismatches (English 79, Hindi 60) and the Devanagari ones (94)
  are exactly what step (b) is for; only the owner's labels can say whether the
  meaning judge is trustworthy. Cells failing on a Devanagari value (at most 94 of
  402 Hindi cells, 23 points, and overlapping the list cases) bound how much a
  cross-script rubric could recover; that is an upper bound, not a prediction.
- Not changed by anything here: the harness never sends the benchmark's own system
  instruction (arguments in English only), synthesized audio is a lower bound, and
  Whisper transcripts are single draws from a non-deterministic ASR.

## Next step — the owner's, before anything else

`results/f1_judge_labels_blank.csv`: 50 rows (25 English, 25 Hindi), drawn with seed 0
from 216 unique ground-truth value mismatches (72 English, 144 Hindi) under the
list-aware judge. The sheet shows the user's query, function, parameter, the accepted
value(s) and the returned value, and **no judge verdict, outcome or ASR condition**.
Fill the last two columns (`equivalent` / `not_equivalent`, optional note) and commit
the file as `results/f1_judge_labels_owner.csv`. Step (b) does not run until it is
committed.
