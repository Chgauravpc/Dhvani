# Dhvani

[![CI](https://github.com/Chgauravpc/Dhvani/actions/workflows/ci.yml/badge.svg)](https://github.com/Chgauravpc/Dhvani/actions/workflows/ci.yml)

> **Measurement audit in progress (Sep 23 2026).** A review found that the F2
> Entity Error Rate numbers below, and the degradation sweep's jitter latency
> result, do not measure what they claim: entity mentions were matched as raw
> substrings ("pan" inside "company" counted as a PAN-card mention), the
> scorer only accepted the Latin canonical spelling (so a correct Devanagari
> "आधार" was scored as an ASR error — LAHAJA's 100% is an artifact), and the
> channel simulator's "jitter" accumulates as a slowdown. Those numbers are
> kept below for the record but **should not be quoted** until the re-run in
> [`docs/specs/phase-3b.md`](docs/specs/phase-3b.md) lands. F1's numbers are
> unaffected by these bugs.

Indic voice-agent research project. See [`ROADMAP.md`](ROADMAP.md) for the
thesis and phase plan, and [`docs/specs/`](docs/specs/) for per-phase
implementation specs.

**Phase 0** (instrumentation spine — telemetry, provider protocols, mock
providers, sequential baseline runner) and **Phase 1** (real providers,
streaming overlap, VAD + barge-in, voice-safe prompt guards, WebRTC
transport) are implemented — see
[`docs/specs/phase-0.md`](docs/specs/phase-0.md) and
[`docs/specs/phase-1.md`](docs/specs/phase-1.md).

**Phase 2** (F1 ASR-ablation harness, F2 `dhvani-entity` post-ASR entity
correction) is implemented, wired into the live demo, and run for real
against real datasets — see [`docs/specs/phase-2.md`](docs/specs/phase-2.md)
(read it before quoting any number below in isolation; every one carries a
real caveat spelled out there).

- **F1**: the agent loses **27.5%** (English) / **10.0%** (Hindi) of task
  success to transcription alone versus a ground-truth transcript
  (section 12 — lower-bound caveat, speed-optimized models).
- **F2**: Entity Error Rate before/after `dhvani-entity` correction, on
  real Svarah/LAHAJA audio with the real default `small` Whisper model —
  **Svarah 59.4% → 49.0%** (10.4-point recovery, 2.9% corruption on clean
  text, n=143 test mentions) and **LAHAJA 100% → 46.4%** (53.6-point
  recovery, but 19.4% corruption on test vs 0% on dev — a real dev/test
  discrepancy at this thin a scale, not glossed over; sections 14–15).
  `small` Whisper getting every single LAHAJA entity mention wrong before
  correction is itself the clearest evidence for this project's own
  thesis produced anywhere in this phase.

## Setup

```
uv sync
uv run pytest                 # unit tests only (no network, no model downloads)
uv run pytest -m integration  # + real Whisper/Piper/Groq/WebRTC round trips
uv run python -m dhvani.demo  # mock-provider waterfall + percentile report
```

## Phase 2 evaluation harnesses

```
uv run python scripts/run_f1_ablation.py                # F1: real ASR vs ground truth
uv run python scripts/entity_density_gate.py             # F2 go/no-go gate (needs HF access)
uv run python scripts/run_f2_entity_eval.py --dataset lahaja  # F2 dev sweep + test report (needs HF access)
```

Svarah and LAHAJA are gated Hugging Face datasets — accept each dataset's
terms on huggingface.co with your account, then `huggingface-cli login`
(or set `HF_TOKEN`) before the last two commands above will work.

## Phase 2B — Indic ASR baseline, model sweep, CI

See [`docs/specs/phase-2b.md`](docs/specs/phase-2b.md). `SarvamSTT` (Saaras)
is a drop-in `STTProvider` for `WhisperSTT`, so the same F1/F2 eval scripts
re-run against it via `--stt sarvam`; needs a free
[Sarvam API key](https://dashboard.sarvam.ai/) exported as `SARVAM_API_KEY`.

```
uv run python scripts/run_f2_entity_eval.py --dataset svarah --stt sarvam
uv run python scripts/run_f1_ablation.py --stt sarvam
uv run python scripts/run_model_sweep.py --dataset svarah --n-examples 30
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
on first run. Default STT is `tiny`/`int8` (`DHVANI_WHISPER_MODEL` /
`DHVANI_WHISPER_COMPUTE_TYPE` to override) — a phase-3 decision
(`docs/specs/phase-3.md` §2.3): the real model sweep measured `small`/`int8`
at p50=7.46s (Svarah) to 13.7s (LAHAJA) STT latency, far too slow for a
live conversation. `int8` over `float32` because the LAHAJA sweep showed
`float32` isn't even a tradeoff there — it's strictly worse than `int8` on
both WER and latency.

The full chain (real browser → WebRTC → Silero VAD → faster-whisper → Groq
→ Piper → audio back to the browser) has been verified end-to-end with an
automated real Chrome session and a synthesized microphone input — see
`docs/specs/phase-1.md` section 11 for exactly what that confirmed and the
three real bugs it found, and `docs/specs/phase-2.md` section 13 for a
Phase 2 re-verification (with `dhvani-entity` now in the pipeline) that
found and fixed a real test-methodology bug along the way. What that can't
replace is a human actually listening and talking to it, including judging
response quality and barge-in feel — that's still on you.
