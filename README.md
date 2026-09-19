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

Requires a free [Groq API key](https://console.groq.com):

```
export GROQ_API_KEY=...       # PowerShell: $env:GROQ_API_KEY = "..."
uv run python -m dhvani.live
```

Then open <http://localhost:8080/> in a browser, grant microphone access,
and talk. faster-whisper's model and the pinned Piper Hindi voice download
on first run.

This is the one part of the project that needs manual verification (a real
browser and microphone) — everything it assembles (the overlapped runner,
barge-in, the WebRTC audio path) is otherwise verified against mocks or a
Python-only WebRTC loopback; see `docs/specs/phase-1.md` section 7.
