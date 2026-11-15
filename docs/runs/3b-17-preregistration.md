# 3B-17 preregistration — digit strings and number-normalised WER

**Written:** 2026-11-15, committed before any 3B-17 scoring run. **Plan:** `docs/specs/phase-4.md`
§5.2 Q1, item 3B-17. Nothing below is edited after this commit; a forced change becomes a
numbered entry in §6.

## 1. Question

Does a strong Indic ASR keep **digit strings** (phone, Aadhaar, account numbers) on **clean**
audio, and how much of its Hindi WER is only number formatting? Both are measured from the
committed F2 transcript logs: no API call, no new audio.

## 2. Data and what the pre-flight found

`results/transcripts/f2_{svarah,indicvoices-hindi}_{whisper,sarvam}.jsonl` (243 / 464 rows per arm,
all splits: nothing is tuned here, so no dev/test split is needed; the test-split rows are also
reported). Pre-flight, `results/preflight_3b-17.json` (committed with this file):

| Corpus | Rows with a digit string | Digit strings (≥ 4 digits) | Density rule |
|---|---|---|---|
| Svarah (English) | 66 of 243 | 75 | 30–100: **intervals reported** |
| IndicVoices (Hindi) | 162 of 464 | 236 | ≥ 100: pass |

The Hindi references spell digit strings **word by word** ("पाँच एक नौ तीन …"); Saaras writes them
as numerals (205 of 464 Saaras outputs contain a digit, 57 of 464 Whisper outputs do). That is
why WER and the digit measure both need the normaliser. Baseline sanity (plan §3 check 2, from the
3B-14 re-score): Whisper `small` on Hindi has 66.5% WER on all rows, above the 40% line, so it is
a **broken baseline**: its digit results are reported, labelled, and **not used as a comparison
arm**. Svarah/Whisper (17.7%), Svarah/Saaras (8.6%) and Hindi/Saaras (26.4%) pass.

## 3. Measures

- **Normaliser:** `dhvani.eval.numbers.to_digit_tokens` (rules in its docstring, 16 unit tests,
  committed with this file). No Whisper-style normaliser. `indic-numtowords` was not installed
  (the sandbox declined an ad-hoc install, and it converts the other direction); the hand-written
  tables are the plan's fallback.
- **Digit-string unit:** each maximal digit run of at least four digits in the normalised
  *reference*.
- **Digit-string exact match:** a unit is recognised iff an identical maximal run of at least four
  digits appears in the normalised hypothesis (each hypothesis run used at most once). Equality
  of the whole run, never a substring. Rate with a Wilson 95% interval per arm. Paired comparison
  of Whisper and Saaras on Svarah by exact McNemar.
- **WER:** `dhvani.eval.wer.corpus_wer` on the raw texts, and on the texts after
  `to_digit_tokens` (both sides), all rows, per arm; the difference is "formatting inflation".

## 4. Predictions (recorded so they can be wrong)

1. Svarah/Saaras digit-string exact match ≥ 90%; Svarah/Whisper `small` ≥ 80%.
2. Hindi/Saaras digit-string exact match ≥ 70% after normalisation.
3. Normalising numbers lowers Hindi/Saaras WER by at least 2 points absolute (the inflation
   suspected in `phase-3b.md` §11 B6, not yet tested), and lowers Svarah WERs by less than 1 point.

## 5. Outcomes, written first

| Observation (non-broken arms) | README sentence |
|---|---|
| any arm's digit-string exact match below 90% (point estimate) | "Digit strings are lost even on clean audio: *X*% exact (95% interval *a*–*b*)." |
| every non-broken arm at or above 90% | "On clean audio the digit strings survive: *X*% exact." |
| Hindi/Saaras WER falls by at least 2 points after normalisation | "*Y* points of Saaras's Hindi WER are number formatting, not recognition." |
| it falls by less than 2 points | "Number formatting accounts for little of Saaras's Hindi WER." |

Whatever the result, 3B-18 (the phone channel) still runs as planned (plan §5.2).

## 6. Caveats that travel with these numbers, and deviations

- Read speech, clustered samples (intervals optimistic), clean audio only; the Hindi reference
  spells digits as words, so "digit-string match" there depends on the normaliser's word tables.
- Merging adjacent digit tokens (rule 6) can join two unrelated numbers; both sides are normalised
  identically, but a hypothesis that groups digits differently from the reference can still be
  mis-scored either way.
- Deviations:
  1. **(2026-11-15, after the first scoring run, which is kept as
     `results/f2_digits_v1_as_registered.json`.)** Reading ten of the 51 Hindi/Saaras misses
     showed most were the normaliser failing on the *reference*, not the ASR failing: the Hindi
     references write "डबल ऐट" (double eight) and spellings the tables lacked ("ऐट", "फाइफ",
     "सेवेन"). The normaliser was amended (rule 6: double/triple, spelling variants; 5 new unit
     tests) and the scoring re-run: `results/f2_digits.json`. Both results are reported. The
     amendment was made **after seeing misses on this same data**, so the amended figures are
     tuned to it and are not an out-of-sample accuracy. Further misses remain that look like
     normaliser limits too (reference dates such as "दो हजार चौबीस ज़ीरो एक पन्द्रह" read as one
     number, two consecutive years merged, the variant "छ" for six); they were **not** patched.
     So the digit-string rates are likely *under*estimates of the ASR's accuracy.
