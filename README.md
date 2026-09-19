# Dhvani

Indic voice-agent research project. See [`ROADMAP.md`](ROADMAP.md) for the
thesis and phase plan, and [`docs/specs/`](docs/specs/) for per-phase
implementation specs.

**Phase 0** (instrumentation spine — telemetry, provider protocols, mock
providers, sequential baseline runner) and **Phase 1** (real providers,
streaming overlap, VAD + barge-in, voice-safe prompt guards, WebRTC
transport) are implemented — see
[`docs/specs/phase-0.md`](docs/specs/phase-0.md) and
[`docs/specs/phase-1.md`](docs/specs/phase-1.md).

## Setup

```
uv sync
uv run pytest                 # unit tests only (no network, no model downloads)
uv run pytest -m integration  # + real Whisper/Piper/Groq/WebRTC round trips
uv run python -m dhvani.demo  # mock-provider waterfall + percentile report
```

## Running the live demo

Requires a free [Groq API key](https://console.groq.com). Either export it
or put it in a local `.env` file (`GROQ_API_KEY=...`, kept out of git by
`.gitignore`):

```
uv run python -m dhvani.live
```

Then open <http://localhost:8080/> in a browser, grant microphone access,
and talk. faster-whisper's model and the pinned Piper Hindi voice download
on first run — set `DHVANI_WHISPER_MODEL=tiny` for a faster/smaller model on
a constrained connection; the real default is `small`.

The full chain (real browser → WebRTC → Silero VAD → faster-whisper → Groq
→ Piper → audio back to the browser) has been verified end-to-end with an
automated real Chrome session and a synthesized microphone input — see
`docs/specs/phase-1.md` section 11 for exactly what that confirmed and the
three real bugs it found. What that can't replace is a human actually
listening and talking to it, including judging response quality and
barge-in feel — that's still on you.
