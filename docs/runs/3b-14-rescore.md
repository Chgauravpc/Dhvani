# 3B-14 — the F2 re-score: what reproduced and what did not

**Computed:** 2026-11-15. **Script:** `scripts/rescore_f2_transcripts.py`.
**Results:** `results/f2_rescore.json`. **Inputs:** the four committed F2 transcript
logs (`results/transcripts/f2_{svarah,indicvoices-hindi}_{whisper,sarvam}.jsonl`)
and the committed `results/f2_eer_*.json`. **No API call, no audio.** Re-running
the script gives a byte-identical JSON.

## Self-check

For all four arms the fuzzy corrector, scored from the logs at each arm's
dev-chosen threshold, equals the committed 3B-4 test report on every field
(`sanity.reproduces_committed_results: true`). So the re-score and the shipped
scorer agree exactly; anything that differs below is a difference in what was
counted, not in the scoring.

## The Nov 14 review's numbers (`phase-3b.md` §11.1) against the re-score

| Review | Claim | Re-score | |
|---|---|---|---|
| B1 | Whisper `small` Hindi WER 66.5% (Saaras 26.4%) | 66.5% / 26.4% (all 464 rows; test 66.6% / 25.8%) | reproduced |
| B1 | Svarah WER 17.7% vs 8.6% | 17.7% / 8.6% (test 18.4% / 8.7%) | reproduced |
| B1 | 41 of 464 Hindi/Whisper rows not in Devanagari: 33 Latin + 8 Arabic | dominant-script count: Latin **27**, Arabic 8, and 7 others (Tamil 1, CJK 2, no letters 4); Devanagari 422 | **Arabic reproduced; Latin 27, not 33.** 42 rows are not Devanagari-dominant in total, 4 of them with no letters at all (3 empty); the review's split depends on a script rule I do not have |
| B2 | Saaras recognises 66/66 Svarah and 231/242 Hindi test mentions unaided | recognition error 0.0% on 66; 4.5% on 242 (11 missed, so 231 recognised) | reproduced |
| B3 | exact lookup canonicalises 231/242 (Hindi) and 66/66 (Svarah) with Saaras | canonical miss after exact lookup: 4.5% (231/242) and 0.0% (66/66) | reproduced |
| B3 | fuzzy matching adds 9 mentions (Hindi) and 0 (Svarah) | fuzzy layer over exact lookup makes 9 and 0 mentions canonical, and breaks 0 | reproduced |
| B4 | false rewrites such as `play`/`many` → PMAY, `coming`/`known`/`loving`/`growing` → CoWIN, `number`/`large number` → PAN card, `हर`/`बाहर`/`शान्दार`/`दार` → Aadhaar | all present in the false-rewrite lists (below) | reproduced |
| B4 | causes: `fuzz.ratio` on very short keys, fuzzy matching of acronyms and aliases, widest-window-wins | **not tested here**: this script lists the rewrites, it does not attribute them to a mechanism | still a hypothesis |
| B6 | Hindi WER is inflated by number formatting | **not tested here**: `eval/wer.py` is unchanged; that is 3B-17 | still open |

## What the table of arms shows

Test split, at each arm's dev-chosen threshold (the committed one for fuzzy):

| Arm | | recognition error | canonical miss | corruption on clean rows |
|---|---|---|---|---|
| Svarah / Whisper (n = 66) | raw | 25.8% | 28.8% | |
| | exact lookup | 25.8% | 25.8% | **0 / 105** |
| | fuzzy (as committed) | 12.1% | 12.1% | 12 / 105 |
| Svarah / Saaras (n = 66) | raw | 0.0% | 1.5% | |
| | exact lookup | 0.0% | 0.0% | **0 / 105** |
| | fuzzy (as committed) | 0.0% | 0.0% | 0 / 105 |
| Hindi / Whisper (n = 242) | raw | 93.8% | 100% | |
| | exact lookup | 93.8% | 93.8% | **0 / 115** |
| | fuzzy (as committed) | 17.4% | 17.4% | 17 / 115 |
| Hindi / Saaras (n = 242) | raw | 4.5% | 99.6% | |
| | exact lookup | 4.5% | **4.5%** | **0 / 115** |
| | fuzzy (as committed) | 0.8% | 0.8% | 0 / 115 |

Exact-then-fuzzy gives the same numbers as fuzzy alone in every arm.

- **Exact lookup does the canonicalisation.** With Saaras it takes the canonical
  miss from 99.6% to 4.5% on Hindi and to 0.0% on Svarah, with zero corruption.
  The fuzzy corrector's extra gain over exact lookup is 9 Hindi mentions (4.5% →
  0.8%) and 0 Svarah mentions with Saaras.
- **Exact lookup cannot repair a misrecognition.** With Whisper it leaves the
  recognition error where it was (25.8%, 93.8%); only the fuzzy layer moves it
  (9 Svarah and 185 Hindi mentions made canonical beyond exact lookup), and it
  costs 11.4% and 14.8% corruption. Whisper `small` on Hindi is the broken
  baseline of B1 (66.5% WER, 42 rows not in Devanagari), so the 185 are a repair of
  a model that is not working, not evidence about Indic ASR.
- **The corruption comes from the fuzzy layer.** Exact lookup rewrote nothing it
  should not have in any arm (0 of 105 and 0 of 115 clean rows). The fuzzy layer's
  false rewrites on the Whisper arms (full lists in the JSON): Svarah — `play` (×2)
  and `many` → "Pradhan Mantri Awas Yojana"; `coming`, `known`, `loving`,
  `growing`, `Clown` → "CoWIN"; `number`, `large number`, `speak 5 numbers` → "PAN
  card"; `rupees.` → "UPI" (not in the review's list). Hindi — "Aadhaar" for `हर`
  (×2), `हरा`, `दे हरा`, `दार`, `बाहर`, `अहाँ`, `माद्वारा`, `अफर`, `बदार्द`, `कवर कर`,
  `शान्दार`, `रहार`, `रहार का`, `Laddhaar,`; "CoWIN" for `किन`, `कोईन`; "PAN card" for
  `पानी बना कर`, `प्रासिन काल`; and others. That is 17 of the 115 clean rows.

## Caveats that stay

- The Svarah test split is 66 mentions, and 43 of them are ESIC (29) or EPFO (14),
  checked in `per_entity_test`: two acronyms carry that arm. The Hindi test split is
  similarly concentrated: Aadhaar (110) and PAN card (53) are 163 of 242 mentions.
- IndicVoices rows are from `train`, and Saaras may have trained on them; its
  near-zero recognition error is potentially in-distribution.
- Mostly read speech; clustered samples, so the intervals in the 3B-4 files are
  optimistic. WER here is the existing `eval.wer` (B6 unresolved).
- These are the **same** test rows 3B-4 reported: nothing was re-split or re-tuned,
  and the exact-lookup baseline has no tuned parameter to leak test information.
