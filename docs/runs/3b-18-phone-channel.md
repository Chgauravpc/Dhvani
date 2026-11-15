# 3B-18 — Saaras through an 8 kHz mu-law phone leg

**Run:** 2026-11-15. **Preregistration:** `docs/runs/3b-18-preregistration.md` (committed `1a1212b`,
before any real-row call). **Code:** `src/dhvani/eval/pstn.py`, `scripts/run_f3_channel.py`,
`scripts/score_channel.py`. **Results:** `results/f3_channel_sarvam.json`,
`results/transcripts/f3_{svarah,indicvoices-hindi}_sarvam_pstn.jsonl` (65 + 225 rows, each sent
once, no failed or retried call), `results/preflight_3b-18.json`. Saaras `saaras:v3`,
`transcribe` mode, 8 kHz mono WAV of the band-limited, mu-law-companded audio; clean transcripts are
the committed 3B-4 ones for the same rows.

## Results (paired by unit, clean → `pstn`)

| | Digit-string exact match | Entity recognition (mentions recognised) | WER, number-normalised |
|---|---|---|---|
| Svarah (English), 65 rows | 43/44 = 97.7% → 42/44 = 95.5% (drop 2.3 pp; 1 worse, 0 better; p = 1) | 66/66 = 100% → 65/66 = 98.5% (drop 1.5 pp; 1 worse, 0 better; p = 1) | 11.1% → 13.1% (raw 11.1% → 15.0%) |
| IndicVoices (Hindi), 225 rows | 147/179 = 82.1% → 147/179 = 82.1% (drop 0.0 pp; 2 worse, 2 better; p = 1) | 231/242 = 95.5% → 230/242 = 95.0% (drop 0.4 pp; 2 worse, 1 better; p = 1) | 12.6% → 14.1% (raw 29.6% → 29.9%) |

Wilson 95% intervals (pstn): Svarah digits 84.9–98.7%, entities 91.9–99.7%; Hindi digits
75.9–87.0%, entities 91.5–97.1%. By the preregistered rule ("degrades" = drop ≥ 5 points and exact
McNemar p < 0.05) **nothing degrades**.

## Against the preregistered predictions

All held: digit-string match dropped by 2.3 and 0.0 points (under 5); entity recognition error rose
by 1.5 and 0.4 (under 5); number-normalised WER rose by 2.0 and 1.5 points (under 3). The
preregistered sentence is the first row of §5: **"A phone codec alone does not hurt a strong Indic
ASR on these utterances."**

## What it says, and what it does not

- A simulated G.711 phone leg, with no packet loss or jitter, costs Saaras little on these read-speech
  utterances: digits and entities hold, WER rises by under 2 points once numbers are normalised.
- The Hindi digit-string rate is the same 82.1% as clean; the 17.9% not reproduced is not a channel
  effect (it is the clean-audio number plus the normaliser limits in 3B-17).
- This says nothing about real telephone speech (accent, background noise, spontaneous talk: 3B-21),
  about packet loss or jitter (not run), or about a real PSTN/Twilio path (never tested).

## Caveats that stay

- The codec is simulated, and 65 Svarah rows with 44 digit strings give wide intervals: a true drop
  of a few points is not excluded, only a drop of 5 points that the paired test can see.
- Read speech; clustered samples (intervals and McNemar tests optimistic); Saaras may have trained
  on IndicVoices `train`; one draw per clip, and Saaras's run-to-run determinism was not checked.
- The response does not echo the model string, so `saaras:v3` is pinned by the request, not verified.
- **Spend:** the agent cannot read the Sarvam balance (no API); 65.05 minutes of audio were sent,
  about Rs 32.5 at the plan's rate. The owner reads the dashboard balance before and after
  (plan §4); the Rs 40 stop rule is the owner's check on that rate.
