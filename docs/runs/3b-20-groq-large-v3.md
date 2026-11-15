# 3B-20 (clean half) — hosted Whisper `large-v3` as the reference arm

**Run:** 2026-11-15. **Preregistration:** `docs/runs/3b-20-preregistration.md` (committed
`2b52ff2`, before any real-row transcription). **Code:** `src/dhvani/providers/groq_stt.py`,
`scripts/run_f2_entity_eval.py --stt groq-whisper`, `scripts/preflight_3b20.py`.
**Results:** `results/f2_eer_{svarah,indicvoices-hindi}_groq-whisper.json`, the two transcript
logs, `results/preflight_3b-20.json`, and the new arms in `results/f2_three_way.json`,
`results/f2_rescore.json`, `results/f2_digits.json`. Groq `whisper-large-v3`, language forced
(`en` Svarah, `hi` IndicVoices), temperature 0, the same 243 / 464 rows as 3B-4, each clip
transcribed once. The run never hit a rate limit. The `pstn` half is at the end of this note.

## Results (test split; recognition error / canonical miss; corruption on clean rows)

| Arm | raw | exact lookup | exact + fuzzy |
|---|---|---|---|
| Svarah / `large-v3` (66 mentions, 105 clean rows) | 16.7% / 18.2% | 16.7% / 16.7%, 0 of 105 | 13.6% / 13.6%, 0 of 105 |
| Hindi / `large-v3` — **broken baseline, not compared** (242, 115) | 65.7% / 99.6% | 65.7% / 65.7%, 0 of 115 | 7.4% / 7.4%, 16 of 115 |

Svarah recognition error 16.7%, 95% interval 9.6 to 27.4% (11 of 66 mentions; 6 of the 8 CoWIN
mentions, 2 of 14 EPFO, 1 of 29 ESIC, 1 of 3 Jan Dhan Yojana, 1 of 2 Provident Fund). Fuzzy over
exact: +2 / −0 (p = 0.5). For comparison: local `small` 25.8%, Saaras 0.0%.

| Arm (all rows) | Digit-string exact match | WER raw → number-normalised |
|---|---|---|
| Svarah / `large-v3` | 66 / 75 = 88.0% (78.7 – 93.6) | 10.1% → 9.9% |
| Hindi / `large-v3` (broken baseline) | 176 / 246 = 71.5% (65.6 – 76.8) | 44.3% → 34.7% |

## Against the preregistration

- **Pre-flight:** Hindi `large-v3` scored 43.0% raw WER on the 20 sanity rows (44.3% on all rows),
  over the 40% line, so by plan §3 check 2 it is a **broken baseline and not a comparison arm**;
  shown with that label only. Its number-normalised WER is 34.7%, so the label is harsher than the
  audio deserves, which is said here and not used to bend the rule.
- **Prediction 1** (Svarah recognition error ≤ 10%): **wrong**, 16.7%. **Prediction 2** (Svarah
  digit-string match ≥ 85%): held, 88.0%. **Prediction 3** (Hindi canonical miss after exact
  ≤ 30%): wrong, 65.7%.
- **Outcome row:** Svarah recognition error is above 15%, so the preregistered sentence is "Open
  Whisper `large-v3` still misses *X*% of the entities on clean English where Saaras misses 0%:
  the ASR choice decides." The README says that, and no longer says the thesis is refuted for every
  strong ASR, only for Saaras.

## What it says

- "A strong ASR recognises the entities" is not a property of strong ASR in general: `large-v3`
  recognises most Svarah entities (83.3%) but not as many as Saaras (100%), and loses CoWIN
  almost completely (6 of 8). The interval (9.6 – 27.4%) is wide at 66 mentions, one corpus, one
  clean-read condition.
- Exact lookup does nothing for a missed entity (it only canonicalises ones already recognised);
  fuzzy repair recovers 2 of 11 here at no measured corruption. On the broken Hindi arm fuzzy repair
  is large (+143 / −2 mentions) and costs 16 of 115 clean rows; that repairs a weak transcript and is
  not a claim about `large-v3`.

## Caveats that stay

- The F2 JSON for these two arms was produced by `mode="fuzzy"` (exact pass then fuzzy), so the
  3B-14 "fuzzy-only reproduces the committed report" flag is `False` for Hindi/`large-v3` (the legacy
  fuzzy-only path is not what generated it); the exact-plus-fuzzy report is reproduced exactly (the
  re-score aborts otherwise) and `sanity.matches_f2_rescore` is `true`.
- The Groq endpoint at temperature 0 was not checked for determinism (the local Whisper was not
  deterministic, 3B-5); each transcript is one draw and that variance is in no interval.
- Read speech, clustered samples (intervals optimistic), 66 Svarah mentions, a lexicon this project
  wrote. The 40 pre-flight clips were sent to Groq as well (owner decision 5 of the plan, default
  yes) and are not part of the results.

## The `pstn` half (added 2026-11-15, after 3B-18)

Same 290 test entity rows through `dhvani.eval.pstn.to_pstn` (8 kHz mu-law, no loss or jitter),
Groq `whisper-large-v3`, language forced, once each: `results/f3_channel_groq-whisper.json`,
`results/transcripts/f3_*_groq-whisper_pstn.jsonl`, protocol `docs/runs/3b-18-preregistration.md`
(the same rules as Saaras). Clean transcripts are the 3B-20 clean-half ones.

| | Digit-string exact match | Entity recognition | WER, number-normalised |
|---|---|---|---|
| Svarah / `large-v3` | 39/44 = 88.6% → 40/44 = 90.9% (1 worse, 2 better; p = 1) | 55/66 = 83.3% → 56/66 = 84.8% (0 worse, 1 better; p = 1) | 15.1% → 14.9% |
| Hindi / `large-v3` — *broken baseline, not compared* | 123/179 = 68.7% → 121/179 = 67.6% (8 worse, 6 better; p = 0.79) | 83/242 = 34.3% → 81/242 = 33.5% (12 worse, 10 better; p = 0.83) | 35.5% → 36.4% |

By the preregistered rule **nothing degrades** for `large-v3` either (the largest drop is 1.1 points).
So the codec alone does not hurt this reference arm on these utterances, in the same sense as
Saaras. The Hindi row inherits the broken-baseline label and is not interpreted. Same caveats:
simulated codec, read speech, one draw per clip, clustered samples. With both clean and `pstn`
halves done, **3B-20 is `[?]`**.
