# 3B-9 preregistration — end of speech to first agent audio byte

**Written:** 2026-11-15, committed before any 3B-9 timing run (a one-utterance smoke test of the
Whisper arm preceded it; its output was discarded and led to the end-of-speech definition in §3).
**Plan:** `docs/specs/phase-4.md` §5.2 Q3, item 3B-9. Nothing below is edited after this commit; a
forced change becomes a numbered entry in §8.

## 1. Question

How long after the user stops speaking does the agent's first audio byte come out, with real
providers and real time, and where does the time go? The figure it replaces is the mock-based
"sub-800 ms p50" the README withdrew (mock providers sleep for a configured time).

## 2. Setup

- **Utterances:** the first 50 of the committed Gram Vaani sample (`results/gramvaani_sample.json`,
  container duration ≤ 10 s; 5.96 minutes in total), plus the first eligible one as a warm-up that is
  logged and excluded (model load, connection set-up). Each is played at **real time as 8 kHz mu-law
  telephone audio** (the 3B-18 `pstn` leg) in 20 ms chunks, then silence until the endpoint fires.
  Only timings are committed, never transcript text (Gram Vaani licence, 3B-21 deviation B).
- **Two STT arms, same LLM and TTS:** (a) `whisper-tiny`: local Silero endpointer (500 ms of silence),
  then local faster-whisper `tiny`/`int8` on the collected audio; (b) `sarvam-realtime`: audio streamed
  live to Sarvam's realtime WebSocket (mu-law, 8 kHz) with server-side VAD, `silence_duration_ms=500`,
  first `transcript.final`. LLM: Groq, the repository's default model. TTS: local Piper Hindi voice,
  first complete LLM sentence only; the first audio chunk is the "first byte".
- **Pre-flight** (`results/preflight_3b-9.json`, committed with this file): the realtime endpoint works as
  documented in `sarvam_realtime_stt.py`; the server resolves the model to `saaras:v4`, VAD threshold
  0.3 (the local endpointer uses 0.5; the two are not identical); event sequence `session.begin`,
  `vad.speech_start`, `transcript.partial`…, `vad.speech_end`, `transcript.final`. Cost: 5.96 minutes
  of audio, **about Rs 3.0** at the plan's Rs 30/hour, plus one warm-up clip.
- **Spend gate:** the Sarvam arm stops at the first HTTP 402 / WebSocket 1003; the Whisper arm is free.

## 3. Measures

Five monotonic instants per turn, giving four consecutive stages that sum to the total:
**end of speech** (the end of the last 32 ms window Silero scores ≥ 0.5, computed offline over the whole
clip; trailing silence after it is the user being quiet) → **endpoint decision** (local endpointer, or
Sarvam's `vad.speech_end`) → **final transcript** (Whisper returns, or Sarvam's `transcript.final`) →
**first complete LLM sentence** → **first TTS audio byte**. Stages: `endpoint`, `stt`, `llm`, `tts`.
Report p50 and p90 (linear-interpolated) of each stage and the total, per arm, over completed turns;
failed turns (empty transcript, provider error) are counted and excluded, never imputed. An instant
earlier than its predecessor is clamped to it and the clamped count is reported.

## 4. Predictions (recorded so they can be wrong)

1. Sarvam realtime arm: total p50 between 1.0 and 2.5 s.
2. Whisper `tiny` arm: total p50 between 3 and 6 s, with the STT stage the largest.
3. The endpoint stage is at least 500 ms in both arms (the silence rule) and is the largest stage in
   the Sarvam arm.
4. Neither arm's p50 is under the mock-based 800 ms.

## 5. Outcomes, written first

There is **no pass mark**; the number is reported whatever it is, beside the figure it replaces. README
sentence: "End of speech to first agent audio byte, real providers at real time on 50 telephone-quality
utterances: *A* ms p50 (*B* ms p90) with Sarvam realtime STT, *C* ms p50 (*D* ms p90) with local Whisper
`tiny`; the largest stage is *X* (*E* ms p50). The earlier sub-800 ms figure came from mock providers."

## 6. Fallbacks (plan §5.2)

If the realtime endpoint fails its pre-flight: the legacy streaming endpoint (final transcripts only),
then REST with the request time measured. The realtime endpoint passed, so none is taken.

## 7. Caveats that travel with every number

One machine (CPU, no GPU), one home network, one Groq key (shared quota and variable server load), 50
utterances, one pass each; the LLM reply and its first sentence are not controlled (length varies); Piper
runs locally; replayed recorded speech, not a live microphone or a real call; the two endpointers differ
(local threshold 0.5, server 0.3), so the endpoint stage is not a like-for-like comparison of models;
transcript quality is not measured here; the first sentence only, not the whole reply; the Sarvam server
model (`saaras:v4`) differs from the `saaras:v3` used in 3B-4/3B-18/3B-21.

## 8. Deviations

None yet.
