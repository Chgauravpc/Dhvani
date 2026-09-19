# Phase 1 — Working Agent

**Status:** implemented — see the git log for build order and the bugs
found and fixed along the way; sections 9-10 record the decisions and
corrections made during implementation
**Depends on:** Phase 0 (instrumentation spine, committed)
**Blocks:** Phase 2 (F1 + F2)
**Not yet done:** live browser + microphone verification (needs the user's
own machine — see README.md's "Running the live demo")

---

## 1. Context

Phase 0 (instrumentation spine) is committed and green: types, clock,
telemetry, provider protocols, mock providers, sequential baseline runner —
all zero-runtime-dependency, all tested with fakes. `ROADMAP.md` scopes Phase 1
as "Working agent" (weeks 2-3): real STT/LLM/TTS providers, streaming with
overlapped stages, Silero VAD + barge-in, voice-safe prompt guards, and a
browser/WebRTC transport, with a milestone of "first sub-800ms p50
conversation, waterfall published."

Unlike Phase 0, there is no implementer-ready spec for this yet, and Phase 1
is materially riskier: real ML models, real-time concurrency, a live
transport, and a hosted LLM API key. This document is a first draft, meant to
be edited before implementation starts.

Environment facts that shape the technology choices below (checked directly,
not assumed): no GPU (`nvidia-smi` absent), no Ollama installed, no
`GROQ_API_KEY` or other provider key set, 181GB free disk, Windows/Python
3.13.1. Groq (hosted, free tier, OpenAI-compatible API) was chosen over Ollama
for the LLM backend, given no local LLM runtime exists yet.

---

## 2. Key technology decisions

- **LLM: Groq.** OpenAI-compatible endpoint (`https://api.groq.com/openai/v1`),
  official `groq` Python SDK supports streaming chat completions the same
  shape as our `LLMProvider` protocol expects. Free tier: ~30 RPM / model-
  dependent TPM, no cost. Needs `GROQ_API_KEY` env var — the user will need to
  create one; never hardcode or commit a key.
- **STT: faster-whisper (CTranslate2), not IndicConformer.** No GPU means
  NeMo/IndicConformer's install and inference cost is disproportionate;
  faster-whisper runs adequately on CPU with int8 quantization and has clean
  Windows wheels. **Honesty point:** faster-whisper is not a native streaming
  model — real partial-transcript-while-speaking behavior does not exist for
  free on CPU. Design: Silero VAD detects end-of-utterance, then the full
  utterance is transcribed in one faster-whisper call. "Partials" in Phase 1
  are therefore either omitted or approximated by re-decoding a growing
  buffer at a coarse interval — default to omitted-for-now (simpler, honest),
  with re-decoding flagged as a stretch item.
- **TTS: Piper.** ONNX-based, CPU-realtime, good Windows support, and
  naturally fits streaming synthesis because Piper can be fed sentence by
  sentence — a direct match for our existing `TTSProvider.stream(text:
  AsyncIterator[str])` contract. A specific Hindi (`hi_IN`) voice model must be
  picked from `rhasspy/piper-voices` on Hugging Face at implementation time
  (availability changes; this doc names the family, not a pinned file).
- **VAD: Silero VAD**, ONNX runtime path specifically (not the full PyTorch
  hub path) to avoid pulling in a multi-GB torch dependency for a small
  detector. Operates on 16kHz mono chunks (~512 samples / 32ms), exposes a
  streaming `VADIterator`-style interface.
- **Transport: aiortc.** The standard pure-Python asyncio WebRTC library;
  ships example patterns for exactly this (browser mic → Python
  `MediaStreamTrack.recv()` → PCM frames; Python → browser playback track).
  Needs a small HTTP signaling endpoint (aiohttp is the natural pairing,
  already an aiortc example dependency) to exchange SDP offer/answer, plus a
  minimal browser page (HTML/JS, no framework) to capture the mic and render
  the played-back audio.

These are committed choices with reasoning, not open questions — matching
Phase 0's spec style (decide, justify briefly, flag the few genuinely open
questions in section 8).

---

## 3. In scope / explicitly out of scope

**In scope:**
- Real providers: `WhisperSTT`, `GroqLLM`, `PiperTTS`
- Streaming with overlapped stages (STT partials/final feed the LLM early;
  TTS begins on the first sentence, not the full response)
- Silero VAD + barge-in (user interrupts mid-sentence, agent yields)
- Voice-safe prompt guards (no markdown, lists, or headers reaching TTS)
- Browser/WebRTC transport (aiortc)
- Milestone: first sub-800ms p50 conversation, waterfall published

**Explicitly out of scope (do not build these here):**
- F1-F5 findings work (Phase 2+)
- Any persistence or memory layer
- Multi-turn session management beyond what's needed to demo one conversation
- Mobile or native clients (browser only)
- Telephony / PSTN (Phase 3's channel simulator)

---

## 4. New ground rules

- Runtime dependencies are now allowed (Phase 0 was stdlib-only; Phase 1 is
  not). Enumerate them explicitly in `pyproject.toml`: `faster-whisper`,
  `groq`, Piper's runtime package, `onnxruntime` (Silero), `aiortc`, `aiohttp`.
- API keys only via environment variable (`DHVANI_` prefix or the provider's
  own convention, e.g. `GROQ_API_KEY`), never committed, never logged.
- Windows-first still applies to every new dependency — verify each has
  Windows wheels before it goes in.
- Real providers must satisfy the exact `STTProvider` / `LLMProvider` /
  `TTSProvider` protocols from Phase 0 unchanged. Phase 1 adds
  implementations; it does not change the contracts.

---

## 5. Repo layout additions

```
src/dhvani/
    providers/
        whisper_stt.py     WhisperSTT (faster-whisper)
        groq_llm.py         GroqLLM (Groq streaming chat completions)
        piper_tts.py        PiperTTS (Piper, sentence-at-a-time)
    vad/
        __init__.py
        silero.py           Silero VAD wrapper (ONNX runtime)
        endpointer.py        speech/not-speech + end-of-utterance state machine
    pipeline/
        overlapped.py       OverlappedRunner (replaces SequentialRunner as the live path)
    safety/
        __init__.py
        prompt_guard.py     strip markdown/lists/headers before TTS
    transport/
        __init__.py
        webrtc.py           aiortc peer connection + audio track glue
        signaling.py        aiohttp SDP offer/answer endpoint
web/
    index.html               minimal mic-capture + playback page, no framework
```

`SequentialRunner` stays as-is (the Phase 0 baseline for comparison); it is
not deleted or modified.

---

## 6. Design per module

### 6.1 `WhisperSTT` (`providers/whisper_stt.py`)

```python
class WhisperSTT:
    name = "faster-whisper"

    def __init__(self, model_size: str, clock: Clock, device: str = "cpu",
                 compute_type: str = "int8") -> None: ...

    def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]: ...
```

VAD-gated: buffers audio until the endpointer signals end-of-utterance (or
`is_last=True` on the final chunk), then runs one blocking `transcribe()` call
via `asyncio.to_thread` (never block the event loop), emits a single final
`Transcript`. Opens an `aspan(Stage.STT, ...)`, records `FINAL_TRANSCRIPT`.
No `FIRST_PARTIAL` mark is emitted unless the re-decode stretch item (open
question, section 8) is implemented.

### 6.2 `GroqLLM` (`providers/groq_llm.py`)

```python
class GroqLLM:
    name = "groq"

    def __init__(self, model: str, clock: Clock, api_key: str | None = None) -> None: ...

    def stream(
        self, messages: Sequence[Message], *, trace: TurnTrace,
        tools: Sequence[Mapping[str, object]] = (),
    ) -> AsyncIterator[LLMDelta]: ...
```

Wraps `groq.AsyncGroq(...).chat.completions.create(..., stream=True)`. Maps
each streamed chunk's delta to `LLMDelta(text=...)`; records `FIRST_LLM_TOKEN`
on the first non-empty delta. Must handle `asyncio.CancelledError` by closing
the underlying stream and re-raising (barge-in depends on this).

### 6.3 `PiperTTS` (`providers/piper_tts.py`)

```python
class PiperTTS:
    name = "piper"
    sample_rate: int

    def __init__(self, voice_model_path: Path, clock: Clock) -> None: ...

    def stream(
        self, text: AsyncIterator[str], *, trace: TurnTrace
    ) -> AsyncIterator[AudioChunk]: ...
```

For each sentence received from the text iterator, synthesizes via Piper
(CPU-bound — run via `asyncio.to_thread`) and yields the resulting PCM as one
or more `AudioChunk`s. Records `FIRST_AUDIO_OUT` on the first chunk.

### 6.4 `SileroEndpointer` (`vad/endpointer.py`, `vad/silero.py`)

Consumes live `AudioChunk`s, runs Silero VAD (ONNX) per ~32ms window, and
exposes:

```python
class SileroEndpointer:
    def __init__(self, clock: Clock, threshold: float = 0.5,
                 min_silence_ms: float = 500.0) -> None: ...

    async def feed(self, chunk: AudioChunk) -> EndpointEvent | None: ...
```

`EndpointEvent` is one of `SPEECH_STARTED`, `SPEECH_ENDED`. This replaces
"wait for `is_last`" as the real trigger for STT, and is also what barge-in
listens to.

### 6.5 `OverlappedRunner` (`pipeline/overlapped.py`)

The Phase 1 replacement for `SequentialRunner` as the live path (Phase 0's
`SequentialRunner` is kept, unmodified, as the baseline to beat). Starts LLM
generation as soon as the transcript is ready (final, given no partials in
the default design) instead of waiting idle; starts TTS on the first complete
sentence the LLM produces rather than the full response. Must reuse
`TurnTrace` unchanged — spans already tolerate overlap by design from Phase 0.

### 6.6 Barge-in

User speech detected via `SileroEndpointer` while TTS is playing → cancel the
in-flight LLM/TTS `asyncio.Task`s for that turn (every Phase 0 provider
contract already requires clean cancellation — this is where that
requirement cashes out) → start a new turn from the freshly detected speech.

### 6.7 Prompt guard (`safety/prompt_guard.py`)

A pure function/pipeline step: strip markdown emphasis, bullet/numbered
lists, and headers from LLM output before it reaches TTS, so voice output
never speaks "asterisk asterisk" or "pound sign." No LLM call involved — text
transform only.

### 6.8 WebRTC transport (`transport/webrtc.py`, `transport/signaling.py`)

`signaling.py`: aiohttp endpoint accepting a browser's SDP offer, returning
the aiortc-generated answer. `webrtc.py`: custom `MediaStreamTrack` consuming
inbound browser audio, resampling to 16kHz mono `AudioChunk`s and feeding the
endpointer/STT; a matching outbound track wrapping `PiperTTS`'s `AudioChunk`s
for browser playback. `web/index.html`: minimal mic-capture + `<audio>`
playback page, no framework.

---

## 7. Testing strategy

This is the section most different from Phase 0. Real providers cannot honor
Phase 0's "no network, no model downloads" rule. Split test tiers explicitly:

- **Unit tests (CI, fast, no network/model):** prompt guard formatting,
  endpointer state-machine logic (feed synthetic speech-probability
  sequences, not real Silero output), barge-in cancellation logic against
  Phase 0's existing mock providers (no new real dependency needed to prove
  barge-in itself works), `OverlappedRunner` overlap behavior against mocks
  (key regression test: overlapped TTFA must be less than `SequentialRunner`'s
  TTFA for the same mock timings).
- **Integration tests (opt-in, marked, skipped by default in CI):** real
  Whisper/Groq/Piper round-trips, gated behind `pytest.mark.integration`,
  requiring `GROQ_API_KEY` / downloaded models to be present; skipped
  automatically otherwise so the suite stays green without secrets or
  multi-GB downloads.
- **Milestone verification (manual):** run the WebRTC demo, talk to it,
  interrupt it mid-sentence, capture the waterfall and the sub-800ms (or
  honest miss) number for the README.

---

## 8. Definition of done

- `uv run pytest -m "not integration"` green in CI
- `uv run mypy --strict` clean on all new modules
- `uv run ruff check` / `ruff format --check` clean
- A documented manual verification recipe for the live demo (this part can't
  be a CI assertion)
- The waterfall + latency table captured once, honestly, for the eventual
  README

---

## 9. Open questions — resolved

1. **Streaming STT partials:** deferred. `WhisperSTT` emits one final
   transcript per VAD-gated utterance; no `FIRST_PARTIAL` mark in this pass.
2. **Piper voice:** pinned to `hi_IN-priyamvada-medium` from
   `rhasspy/piper-voices` (checked directly — three `hi_IN` voices exist:
   `pratham`, `priyamvada`, `rohan`, all "medium" quality; no strong reason to
   prefer one, `priyamvada` chosen). Downloaded via `huggingface_hub.hf_hub_download`
   at first use (no `piper.download` helper in `piper-tts==1.8.0`), cached
   under a local models directory, not committed to git.
3. **Ollama fallback:** out of scope for this pass.

## 10. Corrections found while verifying real APIs (installed, not assumed)

Verified against `faster-whisper==1.2.1`, `groq==1.7.0`, `piper-tts==1.8.0`,
`silero-vad-notorch==6.2.1.1`, `aiortc==1.15.0` actually installed on this
Windows machine (`uv add` — all had prebuilt wheels, no compilation needed):

- `WhisperModel.transcribe(audio, ...)` takes a `numpy.ndarray`, not raw
  bytes. `WhisperSTT` must convert `AudioChunk.pcm` (int16 bytes) to a
  float32 array in `[-1, 1]` via `np.frombuffer(pcm, dtype=np.int16)
  .astype(np.float32) / 32768.0`.
- `piper.voice.PiperVoice.synthesize()` returns Piper's **own**
  `piper.voice.AudioChunk` dataclass — name-collides with
  `dhvani.types.AudioChunk`. Import it aliased
  (`from piper.voice import AudioChunk as PiperAudioChunk`). Its
  `.audio_int16_bytes` property gives exactly the PCM format ours needs.
- `silero-vad-notorch` (not `silero-vad`) is the torch-free package per
  section 2's ground rule, module name `silero_vad_notorch`. It **bundles**
  the ONNX model as package data — `load_silero_vad(onnx=True)` needs no
  runtime download. `VADIterator(model, threshold, sampling_rate,
  min_silence_duration_ms)` is callable per chunk and returns `None` or a
  dict with a `"start"`/`"end"` key on a state transition. Recommended chunk
  size: 512 samples at 16kHz (32ms).
- `pytest.ini_options` now registers an `integration` marker and defaults
  `addopts` to `-m 'not integration'`, so `uv run pytest` stays network/model
  free by default; integration tests opt in with
  `uv run pytest -m integration`.
