# 3B-20 preregistration — the Whisper `large-v3` reference arm, clean audio

**Written:** 2026-11-15, committed before any 3B-20 transcription of the real rows.
**Plan:** `docs/specs/phase-4.md` §5.2 Q1, item 3B-20. Nothing below is edited after this
commit; a forced change becomes a numbered entry in §6. **Scope today:** the clean half only
(the 3B-4 rows). The `pstn` half needs the 3B-18 rows and is not started, so this item stays
`[~]` until it is done.

## 1. Question

Is "a strong ASR already recognises the entities" (3B-4: Saaras) a fact about Saaras or about
strong ASR? Hosted open-weights Whisper `large-v3` (Groq), language forced, is the reference
arm: not Indic-specialised, far larger than the local `small`.

## 2. Pre-flight, committed with this file (`results/preflight_3b-20.json`)

| Check | Result |
|---|---|
| Rows | the 243 Svarah and 464 IndicVoices rows are exactly the ids in the committed Saaras logs |
| Audio, measured | Svarah 1,597 s, IndicVoices 5,608 s (total 7,205 s, longest clip 29.5 s); free tier is 7,200 audio s per hour, 28,800 per day, 2,000 requests per day: fits in a day, paced across two hours |
| API reality | model `whisper-large-v3`, WAV accepted, `language` forced, `temperature` 0; 429s are retried after `Retry-After` (up to 3,700 s) |
| Baseline sanity, 20 rows each, raw WER | Svarah **11.4%**, Latin script: passes. IndicVoices Hindi **43.0%**, Devanagari: **above the 40% line, so it fails the check as written** |

By plan §3 check 2, Hindi/`large-v3` is therefore labelled a **broken baseline and not a
comparison arm**. It is still transcribed (it costs nothing and the log is reusable) and its
numbers are shown with that label, not interpreted as a comparison. The raw WER includes the
number-formatting inflation 3B-17 found, so the label may be harsher than the audio deserves;
that is stated, not used to bend the rule.

## 3. Protocol — identical to 3B-4, 3B-15 and 3B-17

- Same rows and splits (row split for Svarah, speaker split for IndicVoices), same dev-chosen
  fuzzy threshold procedure, `scripts/run_f2_entity_eval.py --stt groq-whisper`; each clip
  transcribed once, logged to `results/transcripts/f2_<dataset>_groq-whisper.jsonl`.
- Scored exactly as the other arms: recognition error, canonical-form miss, corruption on clean
  rows, raw / exact lookup / exact + fuzzy, Wilson intervals, exact McNemar
  (`scripts/f2_three_way_table.py`, extended to these arms); digit-string exact match and WER
  raw vs number-normalised (`scripts/score_digits.py`, extended).
- Noise: Whisper at temperature 0 on a hosted GPU may still not be deterministic (3B-5 found
  the local one is not); each clip is one draw and that variance is in no interval.

## 4. Predictions (recorded so they can be wrong)

1. Svarah/`large-v3` recognition error on test ≤ 10% (local `small`: 25.8%; Saaras: 0.0%).
2. Svarah digit-string exact match ≥ 85%.
3. Hindi/`large-v3` test canonical miss after exact lookup ≤ 30% (`small`: 93.8%; Saaras: 4.5%).

## 5. Outcomes, written first

| Observation | README sentence | Next step |
|---|---|---|
| Svarah recognition error ≤ 15% | "Open Whisper `large-v3` also recognises the entities on clean English: *X*%, so strong ASR, not Saaras alone, removes the entity problem." | none |
| Svarah recognition error > 15% | "Open Whisper `large-v3` still misses *X*% of the entities on clean English where Saaras misses 0%: the ASR choice decides." | the 3B-15 three-way table on these transcripts is where fuzzy repair is judged |
| Hindi arm (labelled broken baseline) | its numbers are listed with the label and no comparison sentence | none |

## 6. Deviations

None yet.
