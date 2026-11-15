# 3B-9 — end of speech to first agent audio byte, real providers

**Run:** 2026-11-15. **Preregistration:** `docs/runs/3b-9-preregistration.md` (committed `68d8e0c`,
before the timing run). **Code:** `src/dhvani/providers/sarvam_realtime_stt.py`,
`src/dhvani/eval/latency.py`, `scripts/run_latency.py`, `scripts/score_latency.py`,
`scripts/preflight_3b9.py`. **Results:** `results/latency/3b9_{whisper-tiny,sarvam-realtime}.jsonl`
(per-utterance timings, no text), `results/latency_3b9.json`, `results/preflight_3b-9.json`.
50 real telephone Hindi utterances (Gram Vaani sample, ≤ 10 s each, 5.96 minutes) plus an excluded
warm-up, played at real time as 8 kHz mu-law; both arms use the same Groq LLM and local Piper Hindi
voice; the arms ran one after the other.

## Results (ms; p50 / p90; stages are consecutive and sum to the total)

| Arm | Turns | Endpoint | STT | LLM (to first sentence) | TTS (to first audio) | **Total** |
|---|---|---|---|---|---|---|
| **Sarvam realtime** (server VAD, 500 ms silence) | 50 | 583 / 660 | 115 / 171 | 551 / 734 | 564 / 1,969 | **1,800 / 3,286** |
| **Local Whisper `tiny`** (Silero endpointer, 500 ms) | 44 of 50 | 507 / 546 | 4,579 / 11,947 | 493 / 638 | 585 / 15,996 | **7,818 / 22,572** |

Same numbers over turns with no premature endpoint (below): Sarvam 40 turns, total 1,987 / 3,419;
Whisper 32 turns, total 10,157 / 25,313.

## Against the preregistered predictions

1. Sarvam total p50 between 1.0 and 2.5 s: **held** (1.80 s).
2. Whisper `tiny` total p50 between 3 and 6 s with STT the largest stage: **half wrong**. STT was the
   largest stage (4.6 s), but total p50 is **7.8 s**, above the predicted range.
3. Endpoint stage at least 500 ms in both arms and the largest stage in the Sarvam arm: **held**, narrowly
   at p50 (endpoint 583 ms, TTS 564, LLM 551); at p90 the TTS stage is the largest (1,969 ms).
4. Neither arm under the mock-based 800 ms: **held**.

## What it says

- With a streaming STT the agent's first audio comes about **1.8 s** after the user stops (p90 3.3 s);
  almost all of it is three roughly equal ~550–600 ms stages (waiting out the silence, the LLM's first
  sentence, Piper's first audio). The streaming STT itself adds only about 115 ms after the endpoint,
  because it transcribes while the user is still talking.
- Local Whisper `tiny` on this CPU is far slower: **7.8 s** p50 and **22.6 s** p90, dominated by
  transcription (4.6 s p50, 11.9 s p90), and it returned an empty transcript on 6 of 50 telephone
  clips (excluded, counted).
- The earlier "sub-800 ms p50" came from mock providers and is not supported by any real measurement:
  the best real arm is more than twice that.

## Read these before quoting a number

- **Premature endpoints.** In 10 of 50 Sarvam turns and 12 of 44 completed Whisper turns the endpoint
  fired before the clip's last speech: the speaker paused longer than the 500 ms silence rule, so the
  agent started to answer while the user was still talking. Their end-of-speech instant falls *after* the
  endpoint, so the affected stages are clamped to 0 and those totals are understated. The table above
  includes them (as preregistered); the no-premature-endpoint figures are the second line. That is
  itself a finding: a 500 ms silence rule cuts off this speech about one turn in five.
- **The Whisper TTS tail is unexplained.** Piper's first-audio time has a p90 of 16 s in the Whisper arm
  (up to 35 s) against 2 s in the Sarvam arm. Piper is the same local model in both; CPU contention with
  Whisper is the obvious suspect and was not investigated or shown.
- Timings, not transcripts: transcript quality of either arm was not measured here.

## Caveats that stay

One machine (CPU only), one home network, one Groq key at variable server load, 50 utterances, one pass
each; the LLM's first sentence varies in length and is not controlled; replayed recorded speech, not a
live microphone or a real call; the local endpointer (threshold 0.5) and Sarvam's server VAD (0.3) are
not the same model, so the endpoint stage is not a like-for-like comparison; first sentence only;
Sarvam's server resolved the model to `saaras:v4`, not the `saaras:v3` of the accuracy runs.
**Spend:** 5.96 minutes of audio plus one warm-up clip, about Rs 3 at the plan's rate; the agent cannot
read the balance, so the owner records the real cost.
