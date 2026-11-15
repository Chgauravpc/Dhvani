# 3B-15 — exact lookup as the shipped corrector, and the three-way table

**Computed:** 2026-11-15. **Code:** `EntityCorrector(mode=...)` in
`src/dhvani/entity/corrector.py`, `src/dhvani/entity/exact.py`.
**Script:** `scripts/f2_three_way_table.py`. **Results:** `results/f2_three_way.json`.
**Inputs:** the committed F2 transcript logs and the committed dev-chosen thresholds.
**No API call.** The script re-runs byte-identically, and its numbers equal the 3B-14
re-score (`sanity.matches_f2_rescore: true`).

## What changed in the code

- `EntityCorrector(mode="exact")` is the **default**: replace each word-bounded,
  hand-curated variant with its canonical form. No phonetic keys, no threshold.
- `EntityCorrector(mode="fuzzy")` is the optional layer: the exact pass, then the
  existing phonetic fuzzy windows over its output. Each `Correction` now carries
  a `stage` (`"exact"` or `"fuzzy"`).
- **Behaviour changes.** The live demo (`dhvani.live`) builds
  `EntityCorrector(DEFAULT_LEXICON)`, so it now runs **exact lookup** instead of the
  fuzzy corrector. Everything that deliberately measures the fuzzy corrector
  (`run_f2_entity_eval.py`, `run_f1_ablation.py --with-corrected-stt`, and the
  tests of fuzzy behaviour) now passes `mode="fuzzy"` explicitly, so those
  experiments mean what they meant before. The F1 `--with-corrected-stt` arm
  therefore still measures the fuzzy corrector, not the new default.
- `exact+fuzzy` reproduces every field of the four committed 3B-4 test reports (rates,
  fixed/broken counts, corrupted rows), as the re-score checks; that is an aggregate
  match, not a row-by-row text comparison with the old fuzzy-only corrector.

## The table — test split, per arm

Fuzzy thresholds are each arm's dev-chosen one (0.70, 0.95, 0.75, 0.85); the exact
column has no parameter. Intervals are Wilson 95%. "+a/−b" is mentions fixed/broken
against the previous column, exact McNemar in the JSON.

| Arm (mentions / clean rows) | Column | Recognition error | Canonical miss | Corruption on clean rows |
|---|---|---|---|---|
| Svarah / Whisper (66 / 105) | raw | 25.8% | 28.8% | |
| | exact | 25.8% | 25.8% | 0.0% [0.0, 3.5] |
| | exact + fuzzy | 12.1% | 12.1% | 11.4% [6.7, 18.9] |
| Svarah / Saaras (66 / 105) | raw | 0.0% | 1.5% | |
| | exact | 0.0% | 0.0% | 0.0% [0.0, 3.5] |
| | exact + fuzzy | 0.0% | 0.0% | 0.0% [0.0, 3.5] |
| Hindi / Whisper (242 / 115) | raw | 93.8% | 100% | |
| | exact | 93.8% | 93.8% | 0.0% [0.0, 3.2] |
| | exact + fuzzy | 17.4% | 17.4% | 14.8% [9.4, 22.4] |
| Hindi / Saaras (242 / 115) | raw | 4.5% | 99.6% | |
| | exact | 4.5% | **4.5%** | 0.0% [0.0, 3.2] |
| | exact + fuzzy | 0.8% | 0.8% | 0.0% [0.0, 3.2] |

| Paired, canonical | exact over raw | fuzzy layer over exact |
|---|---|---|
| Svarah / Whisper | +2 / −0 | **+9 / −0** (p = 0.004), 12 more clean rows corrupted |
| Svarah / Saaras | +1 / −0 | +0 / −0 |
| Hindi / Whisper | +15 / −0 | **+185 / −0**, 17 more clean rows corrupted |
| Hindi / Saaras | **+230 / −0** (p ≈ 1e-69) | **+9 / −0** (p = 0.004), 0 more clean rows corrupted |

## What it says

- **Exact lookup does the canonicalisation, and nothing else.** With Saaras it moves
  the Hindi canonical miss from 99.6% to 4.5% and the Svarah one from 1.5% to 0.0%,
  at no measured corruption in any arm. It cannot change recognition by
  construction: it only rewrites strings that are already curated variants.
- **The fuzzy layer's value is its gain over exact lookup, and it is small with a
  good ASR.** On Saaras it makes 9 more Hindi mentions canonical (4.5% → 0.8%) and
  0 more Svarah mentions, with no additional clean-row corruption measured (0 of
  115, interval up to 3.2%). On Whisper it makes 9 and 185 more mentions
  canonical, at 11.4% and 14.8% corruption.
- **The README sentence, with its numbers filled in** (for 3B-16): fuzzy matching
  adds 9 Hindi and 0 Svarah mentions with Saaras, at 0% corruption measured; with
  local Whisper `small` it adds 9 and 185 mentions at 11.4% and 14.8% corruption.
  Whisper `small` is a CPU-constrained reference row, not an Indic ASR (3B-14: 66.5%
  Hindi WER), so the 185 are a repair of a broken baseline.

## Caveats that stay

- The 9 Saaras-Hindi mentions the fuzzy layer adds are a small, one-sided count
  (+9/−0, p = 0.004); at this size the corruption interval (0–3.2%) does not exclude
  a real cost. Svarah's 66 mentions are 43 ESIC/EPFO; Hindi's 242 are 163 Aadhaar/PAN
  card (3B-14).
- Thresholds were chosen on dev by minimising canonical miss plus corruption, then
  scored once on test; the dev samples are small (28 and 89 entity rows).
- IndicVoices rows are from `train` and Saaras may have trained on them; mostly
  read speech; samples are clustered, so the intervals and McNemar tests, which
  treat mentions as independent, are optimistic.
- This is exact-match scoring against a curated lexicon the corrector itself is built
  from, on a lexicon this project wrote; it says nothing about entities outside it.
