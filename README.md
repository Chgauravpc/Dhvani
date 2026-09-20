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

**Phase 2** (F1 ASR-ablation harness, F2 `dhvani-entity` post-ASR entity
correction) is implemented and wired into the live demo — see
[`docs/specs/phase-2.md`](docs/specs/phase-2.md). F1's real measured
numbers: the agent loses **27.5%** (English) / **10.0%** (Hindi) of task
success to transcription alone versus a ground-truth transcript (read the
spec's section 12 before quoting these — there are real caveats: a
lower-bound caveat on the ASR penalty, and the models used here were
chosen for speed over accuracy). F2's real entity-recovery number (the "Y%
recovered" half of the milestone) isn't measured yet — it needs Hugging
Face access to Svarah/LAHAJA, both of which turned out to be gated; F2's
code and unit tests are done and ready to run once that access exists.

## Setup

```
uv sync
uv run pytest                 # unit tests only (no network, no model downloads)
uv run pytest -m integration  # + real Whisper/Piper/Groq/WebRTC round trips
uv run python -m dhvani.demo  # mock-provider waterfall + percentile report
```

## Phase 2 evaluation harnesses

```
uv run python scripts/run_f1_ablation.py                    # F1: real ASR vs ground truth
uv run python scripts/entity_density_gate.py                # F2 go/no-go gate (needs HF access)
uv run python scripts/run_f2_entity_eval.py --dataset lahaja --split test  # F2 (needs HF access)
```

Svarah and LAHAJA are gated Hugging Face datasets — accept each dataset's
terms on huggingface.co with your account, then `huggingface-cli login`
(or set `HF_TOKEN`) before the last two commands above will work.

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
