# 3B-21 — real telephone Hindi (Gram Vaani)

**Run:** 2026-11-15. **Preregistration:** `docs/runs/3b-21-preregistration.md` (committed `c8e916c`,
before any transcription; deviations A, B and 1 there). **Code:** `scripts/preflight_3b21.py`,
`scripts/run_f3_gramvaani.py`, `scripts/score_gramvaani.py`. **Results:** `results/f3_gramvaani.json`,
`results/preflight_3b-21.json`, `results/gramvaani_sample.json` (ids, durations, rates only),
`results/transcripts/f3_gramvaani_{sarvam,groq-whisper}.jsonl` (hypotheses only: the references are
Gram Vaani's and are re-read from the OpenSLR 118 archive). Data: `GV_Dev_5h` (OpenSLR 118), seed-0
sample of 221 utterances, 34.96 minutes; Saaras `saaras:v3` and Groq Whisper `large-v3` (Hindi forced),
each utterance once. One utterance (`01-04866-01`) was rejected by Saaras as over the API's 30-second
limit, so **220 utterances (5,486 reference words)** are scored for both ASRs.

## Results (corpus WER; 95% bootstrap interval over utterances)

| ASR | Telephone, raw | Telephone, number-normalised | Clean read Hindi (3B-17), normalised | Gap, normalised |
|---|---|---|---|---|
| Saaras | 27.2% | **26.5%** (24.7 – 28.5) | 12.6% | +13.9 pp |
| Whisper `large-v3` (*broken baseline on the clean rows, 3B-20*) | 55.5% | 54.5% (51.8 – 57.3) | 34.7% | +19.8 pp |

The codec's share from 3B-18 (simulated, Saaras, Hindi, normalised): **+1.5 pp**.

## Against the preregistration

1. Saaras normalised WER between 15% and 35%: **held** (26.5%).
2. `large-v3` worse than Saaras on the same sample: **held** (54.5% vs 26.5%).
3. The telephone-minus-clean gap for Saaras exceeds the 3B-18 codec change: **held** (13.9 pp against 1.5 pp).

By the §6 rule the gap is at least 10 points for both ASRs, so the row is "far above", whose sentence is:
*On real telephone Hindi Saaras goes from 12.6% to 26.5% WER; the simulated codec accounts for 1.5 of
that.*

## Read this before quoting the sentence

- The **raw** WERs hardly differ: Saaras 26.4% on the clean IndicVoices rows, 27.2% on this telephone
  sample. The 14-point gap appears only after number normalisation, because the clean IndicVoices rows
  were chosen for entity density (Aadhaar, PAN and phone numbers spelled out in the reference, digits in
  Saaras's output), so normalisation removes about 14 points there, while this general-speech sample
  has only 14 digit strings. The corpora differ in content as well as channel, so **the gap is not a
  channel effect**, and the preregistered rule (a threshold on the normalised gap) fires partly
  because of that difference, not only because the speech is real telephone speech.
- What is safe to say: Saaras's WER on real telephone Hindi is 26.5% (interval 24.7 – 28.5); the
  simulated codec alone moved it 1.5 points on read speech; Whisper `large-v3` is about twice as bad.
- What is not: that "real phone speech costs 14 points". It confounds dialect, spontaneity, topic,
  channel and corpus.

## Caveats that stay

- Not paired with the clean rows; one 35-minute sample; the dev split of a challenge set Saaras or
  Whisper may have seen; the 44.1 kHz files (80 of 221) are telephone-collected audio stored at a high
  rate; interval over utterances only; one draw per clip.
- Digit strings (14) were too few to measure (pre-flight density rule, plan §3).
- Licence: Gram Vaani data is free for academic use; commercial use needs permission. Only ids,
  hypotheses and scores are committed.
- Spend: about 35 minutes of Saaras audio (about Rs 17.5 at the plan's rate) on top of 3B-18's 65
  minutes; the agent cannot read the Sarvam balance, so the owner reads the dashboard and records the
  real cost.
