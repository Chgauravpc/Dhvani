# Dhvani

Indic voice-agent research project. See [`ROADMAP.md`](ROADMAP.md) for the
thesis and phase plan, and [`docs/specs/`](docs/specs/) for per-phase
implementation specs.

Phase 0 (instrumentation spine) is in progress: telemetry, provider
protocols, mock providers, and a sequential baseline runner. No real
providers, streaming overlap, or transport yet — see
[`docs/specs/phase-0.md`](docs/specs/phase-0.md).

```
uv sync
uv run pytest
uv run python -m dhvani.demo
```
