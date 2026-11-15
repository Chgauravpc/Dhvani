# 3B-17 — digit strings and number-normalised WER, clean audio

**Computed:** 2026-11-15. **Preregistration:** `docs/runs/3b-17-preregistration.md` (committed
`6d862df`, before any scoring; deviation 1 there). **Code:** `src/dhvani/eval/numbers.py`
(21 tests), `scripts/score_digits.py`, `scripts/preflight_3b17.py`. **Results:**
`results/f2_digits.json` (amended normaliser), `results/f2_digits_v1_as_registered.json` (first run),
`results/preflight_3b-17.json`. **No API call**: it reads the committed F2 transcript logs.

## Results (all rows; digit string = maximal run of at least 4 digits in the reference)

| Arm | Digit-string exact match | 95% interval | WER raw → number-normalised |
|---|---|---|---|
| Svarah (English) / Whisper `small` | 61 / 75 = **81.3%** | 71.1 – 88.5 | 17.7% → 16.2% (1.6 pp) |
| Svarah (English) / Saaras | 69 / 75 = **92.0%** | 83.6 – 96.3 | 8.6% → 8.6% (0.1 pp) |
| IndicVoices (Hindi) / Saaras | 207 / 246 = **84.1%** | 79.1 – 88.2 | 26.4% → 12.6% (**13.7 pp**) |
| IndicVoices (Hindi) / Whisper `small` — *broken baseline, not a comparison arm* | 37 / 246 = 15.0% | 11.1 – 20.0 | 66.5% → 72.9% |

As first registered (before the normaliser amendment): Hindi/Saaras 185 / 236 = 78.4% and WER
26.4% → 13.5%; the Svarah rows and the paired test did not change. Svarah Whisper vs Saaras, paired
on the same 75 units: Whisper only right 3, Saaras only right 11, exact McNemar p = 0.057, not
significant.

## Against the preregistered predictions

1. Svarah/Saaras ≥ 90% (92.0%) and Svarah/Whisper ≥ 80% (81.3%): **held**, narrowly for Whisper.
2. Hindi/Saaras ≥ 70% after normalisation (84.1%; 78.4% as first registered): **held**.
3. Normalising lowers Hindi/Saaras WER by at least 2 points (13.7 pp): **held**, by far. It lowers
   Svarah/Saaras by under 1 point (0.1 pp, held) but Svarah/Whisper by 1.6 pp: **that half
   was wrong**.

By the §5 rules: two non-broken arms are below 90% (Svarah/Whisper, Hindi/Saaras), so the README
sentence is the "lost even on clean audio" one, with each arm's number and interval; and
Hindi/Saaras WER fell by more than 2 points, so "most of the gap in Saaras's Hindi WER was number
formatting" is supported.

## What it says

- The Hindi WER inflation suspected since the Nov 14 review (B6) is real and large: Saaras writes
  digits where the reference spells words, and half of its measured Hindi WER (26.4%) disappears
  (to 12.6%) when both sides are reduced to digit strings. The earlier Hindi-WER figures were not
  all recognition errors.
- Even Saaras on **clean** audio does not reproduce 8% of the English and 16% of the Hindi digit
  strings exactly. That is a clean-audio number: it is not yet a phone
  number (3B-18 measures the channel).

## Caveats that stay

- **The amendment was made after reading misses on this same data**, so the amended Hindi figures
  are tuned to it. Misses that remain look like the normaliser too (a reference date read as one
  number, two consecutive years merged, the variant "छ" for six), and were not patched, so 84.1% most likely understates
  Saaras. Of the ten misses read, about seven were on the normaliser side.
- The Whisper `small` Hindi row is a broken baseline (66.5% raw WER): shown, not compared. Its
  WER *rises* when normalised, which was not investigated.
- Svarah has only 75 digit strings (intervals are wide and the Whisper–Saaras difference is not
  significant); read speech; samples are clustered, so intervals are optimistic.
- The merge rule (rule 6 as registered, rule 7 after the amendment) can merge unrelated adjacent numbers, and rule 5 turns a lone "एक"/"one" into "1" on both
  sides; both are symmetric but can mis-score either way.
