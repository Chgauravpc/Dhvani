# Phase 2B — Baselines and CI

**Status:** A, B and C all fully done, including LAHAJA's model sweep,
which took two failed attempts and a real fix (running each grid cell as
its own OS process, not a bigger machine -- section 12 below) to complete.
`SARVAM_API_KEY` became available during Phase 3 (section 11 records it
was absent when this phase was originally built); the real Svarah/LAHAJA
EER and F1 re-runs against Sarvam are in `phase-2.md` section 18, per
Phase 3 spec section 2.1, which named this the single highest-value unrun
experiment in the project and forbade cutting it. See section 8 for the
item-by-item definition-of-done.
**Depends on:** Phase 2 (eval harness, `CorrectedSTT`, Svarah/LAHAJA loaders)
**Blocks:** Phase 3 (Twilio reframe)
**Window:** Sep 22–26, 2026 — the tightest week in the plan

---

## 1. Objective

Three workstreams that share one harness:

- **A — Indic ASR baseline.** Make the Phase 2 F2 numbers defensible by
  measuring them against a purpose-built Indic ASR, not only `small` Whisper.
- **B — Model sweep.** Produce the WER-against-latency Pareto curve the
  project currently has no equivalent of. This is the only model-level work
  in the project.
- **C — CI.** Make the 50 passing tests visible, and make a latency
  regression break the build.

They are in priority order. See section 9 for what to cut if the week slips.

---

## 2. Scope

### In scope

- `SarvamSTT` behind the unchanged Phase 0 `STTProvider` protocol
- Re-running Svarah EER, LAHAJA EER and the F1 ablation against it
- A word error rate implementation (none exists in the repo today)
- A sweep over Whisper model size and quantization, reporting WER and
  latency from the telemetry already collected
- GitHub Actions running lint, types, and the default test suite

### Explicitly out of scope

- Any change to `EntityCorrector`, `CorrectedSTT`, the eval scripts, or the
  Phase 0 protocols. `SarvamSTT` is a drop-in for the `stt` argument those
  already take. If something needs changing to accommodate it, the protocol
  was wrong, and that is a design discussion rather than a patch.
- F3, F4, F5 — deferred past Nov 3 by the scope decision of 21 Sep.
- Fine-tuning, distillation, or training anything. The sweep measures
  existing checkpoints; it does not produce new ones.
- Telephony and the channel simulator — Phase 3.

---

## 3. Ground rules

- New runtime dependency: the Sarvam client (see A.1 — verify the package
  name and API before writing code against it). Nothing else.
- `SARVAM_API_KEY` via environment only, never committed, never logged —
  same rule as `GROQ_API_KEY`. Add it to `.env.example` if one exists.
- Every real-API and real-dataset test is `pytest.mark.integration` and
  skips cleanly when the key or the data is absent. `uv run pytest` stays
  network-free and fast.
- Windows-first. Verify Windows wheels before adding anything.

---

## 4. Workstream A — `SarvamSTT`

The reasoning for why this is required is in `phase-2.md` §17 and is not
repeated here. This section is the build.

### A.1 Verify the API first — do not code against memory

Phase 1 caught three real API mismatches by installing the packages and
checking before writing (`phase-1.md` §10). Do the same here, and write
what you find into this section before implementing:

- **Which model.** Sarvam publishes more than one speech model, and the
  names are easy to confuse — one family transcribes in the source
  language, another transcribes-and-translates to English. **F2 needs
  transcription in the source language**; a translating model would
  silently destroy every Devanagari entity mention and produce a
  meaningless EER. Confirm which is which before choosing.
- **Request shape.** Whether the API takes a file upload or raw bytes,
  what container and sample rate it expects, and whether there is a
  streaming endpoint or only batch.
- **Response shape.** Where the transcript lives, and whether any language
  or confidence field maps onto our `Transcript` fields.
- **Package name and whether it has Windows wheels.**

**Verified directly (installed and inspected the real package, not
assumed from docs), same practice as phase-1 spec section 10:**

- **Package is `sarvamai`** on PyPI, version `0.1.34` at verification
  time. `bdist_wheel` is `sarvamai-0.1.34-py3-none-any.whl` — a pure
  Python wheel, so there is no Windows-wheel question to resolve; it
  installs identically on every platform `pip`/`uv` support. Dependencies
  (`httpx`, `pydantic`, `pydantic-core`, `typing_extensions`, `websockets`)
  are all pure-Python-or-widely-wheeled and already indirectly compatible
  with this project's Windows-first rule.
- **Transcribe vs. translate is a `mode` parameter, not a model choice** —
  this is the one thing this section most needed to get right, and the
  docs are easy to misread on it. Both live under
  `client.speech_to_text.transcribe(...)`, whose `mode` argument
  (`"transcribe"` | `"translate"` | `"verbatim"` | `"translit"` |
  `"codemix"`) picks the behavior on the *same* endpoint and the *same*
  default model (`saaras:v3`): `mode="transcribe"` returns text in the
  original language ("मेरा फोन नंबर है 9840950950"), `mode="translate"`
  returns English ("My phone number is 9840950950"). There is a
  *separate* `client.speech_to_text.translate(...)` method too (an older
  `saaras:v2.5`-only translation endpoint), which is not what we want
  either. **F2 needs `client.speech_to_text.transcribe(..., mode="transcribe")`
  specifically** — confirmed by reading the SDK's own generated
  docstrings, not by guessing from the method name.
- **Request shape**: synchronous REST, one call per utterance (matches
  `WhisperSTT`'s buffer-then-transcribe-once design exactly, no streaming
  endpoint needed for this). `transcribe()` takes `file` (a
  `(filename, bytes, content_type)` tuple works — confirmed against the
  SDK's own `core.File` type, `Union[bytes, str, IO[bytes], tuple[...]]`),
  `model` (default `"saaras:v3"`), `mode`, `language_code` (BCP-47, or
  omitted/`"unknown"` for auto-detect), and `input_audio_codec`. Docs
  state 16kHz mono WAV (16-bit PCM) as the recommended format and a
  30-second cap per request — both already true of every VAD-gated
  utterance this project buffers, so no resampling or chunking logic is
  needed beyond what `WhisperSTT` already assumes.
- **Response shape**: `SpeechToTextResponse` (a pydantic model) with
  `.transcript: str`, `.language_code: str | None`, `.language_probability:
  float | None`, and `.request_id`. `.transcript` maps directly onto
  `Transcript.text`; `.language_code` maps directly onto
  `Transcript.language` (both are BCP-47 already — no conversion needed).
  No confidence field maps onto `Transcript.confidence` (Sarvam's
  `language_probability` is about *language* detection confidence, not
  transcription confidence, so it is left unset rather than mapped to the
  wrong thing).
- **Client and errors**: `from sarvamai import AsyncSarvamAI`;
  `AsyncSarvamAI(api_subscription_key=..., timeout=...)` gives an async
  client whose `await client.speech_to_text.transcribe(...)` matches this
  project's async-everywhere convention (same shape as `GroqLLM`'s
  `AsyncGroq`). Failures raise `sarvamai.core.ApiError` (has
  `.status_code` and `.body`) — confirmed by reading `core/api_error.py`
  directly in the installed package, not assumed from a generic
  "requests can fail" expectation.

### A.2 Interface

```python
class SarvamSTT:
    """Sarvam speech-to-text behind the Phase 0 STTProvider protocol.

    VAD-gated and single-shot, exactly like WhisperSTT: audio accumulates
    until end-of-utterance, then one API call produces one final
    Transcript. Hosted, so no GPU and no local model download.
    """
    name: str = "sarvam"

    def __init__(
        self,
        model: str,
        clock: Clock,
        api_key: str | None = None,        # None -> read SARVAM_API_KEY
        language_code: str | None = None,  # None -> let the API detect
        timeout_s: float = 30.0,
    ) -> None: ...

    def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]: ...
```

Behaviour, matching `WhisperSTT` so the two are swappable:

- Buffer chunks until `is_last=True`.
- Encode the buffered PCM to whatever container A.1 established the API
  wants. If that is WAV, the stdlib `wave` module is enough — no new
  dependency.
- One request, in a thread or via the async client, never blocking the loop.
- Emit a single final `Transcript` with `is_final=True`.
- Open an `aspan(Stage.STT, ...)`; record `FINAL_TRANSCRIPT`.
- Raise `ProviderError` on API failure; handle `CancelledError` by closing
  the span and re-raising.

### A.3 What to re-run

Same splits, same thresholds, same scripts — only the inner ASR changes:

1. Svarah EER, test split
2. LAHAJA EER, test split
3. `run_f1_ablation.py --languages english,hindi --n-per-language 40`

**Report every number beside the existing Whisper figure, never replacing
it. The comparison is the result; a table with one column is not.**

### A.4 The F1 reframe (no new code)

Add share-of-achievable alongside the absolute points, per `phase-2.md`
§17:

| language | achievable | lost to ASR | share of achievable lost |
|---|---|---|---|
| english | 42.5% | 27.5% | **65%** |
| hindi | 17.5% | 10.0% | **57%** |

Update `phase-2.md` §12 and §16 to carry both framings. Keep the absolute
numbers — the point is a better denominator, not a better-looking number.

### A.5 Reading the outcome

The three outcomes and what each would mean were written down **before the
run**, in `phase-2.md` §17. That is a preregistration, and it stays fixed:
whichever occurs gets written up as the finding rather than worked around.

---

## 5. Workstream B — model sweep

### B.1 `eval/wer.py` — needed first, nothing in the repo computes WER

```python
def normalize(text: str) -> str:
    """Canonical form for WER comparison.

    Lowercases, strips punctuation including the Devanagari danda (U+0964),
    collapses whitespace, and normalizes Unicode to NFC so visually
    identical Devanagari compares equal.
    """


@dataclass(frozen=True, slots=True)
class WerResult:
    wer: float
    substitutions: int
    deletions: int
    insertions: int
    reference_words: int


def word_error_rate(reference: str, hypothesis: str) -> WerResult:
    """Levenshtein distance over normalized word sequences."""


def corpus_wer(pairs: Sequence[tuple[str, str]]) -> WerResult:
    """Aggregate over a corpus by summing edits and reference words --
    NOT by averaging per-utterance WER, which over-weights short
    utterances and is the single most common way to report a wrong WER."""
```

Implement the DP directly; no new dependency. Roughly 40 lines.

**Normalization choices move WER by several points, so they are part of
the result, not an implementation detail.** Pin them in tests with exact
expected values, and state them wherever a WER number is published.

### B.2 `eval/model_sweep.py`

```python
@dataclass(frozen=True, slots=True)
class SweepPoint:
    model_size: str          # "tiny" | "base" | "small"
    compute_type: str        # "int8" | "float32"
    wer: float
    stt_p50_ms: float
    stt_p90_ms: float
    realtime_factor: float   # stt wall time / audio duration; < 1 is faster than realtime
    n_utterances: int


async def run_sweep(
    examples: Sequence[TranscriptExample],
    model_sizes: Sequence[str],
    compute_types: Sequence[str],
    clock: Clock,
) -> list[SweepPoint]: ...


def pareto_front(points: Sequence[SweepPoint]) -> list[SweepPoint]:
    """Points not dominated on both WER and p50 latency."""


def render_table(points: Sequence[SweepPoint]) -> str:
    """Markdown table, Pareto-optimal rows marked, for RESULTS.md."""
```

Latency comes from the **existing telemetry** — read `stage_total_ms` and
the session percentiles off the traces the run already produces. Do not add
a second timing mechanism; the project has one and it is tested.

`scripts/run_model_sweep.py` drives it over a bounded Svarah/LAHAJA sample
and writes the table.

### B.3 What the sweep is for

Not "which model is best" — a Pareto curve has no single best. The
deliverable is **a stated operating point with a reason**: which size and
quantization the live demo runs at, what it costs in WER, and what it buys
in latency. That sentence is the artifact.

---

## 6. Workstream C — CI

The latency gate largely exists already: `tests/test_overlapped.py` asserts
`improvement_ms >= 400.0`. CI's job is to run it on every push, not to
reimplement it.

`.github/workflows/ci.yml`:

- Trigger on push and pull request
- `ubuntu-latest` for speed; add `windows-latest` for the test job only,
  since Windows is the real dev target and the virtual-time loop subclasses
  `SelectorEventLoop` while Windows defaults to Proactor
- Python 3.13, `uv sync`
- Steps: `ruff check`, `ruff format --check`, `mypy --strict src/dhvani`,
  `pytest -m "not integration"`
- No secrets. Integration tests must skip cleanly on a runner with no keys —
  if CI goes red for a missing key, the skip logic is wrong, not CI.
- Badge in the README

---

## 7. Testing

**Unit (CI, fast, no network):**

| Test | Asserts |
|---|---|
| `test_wer.py` | known reference/hypothesis pairs give exact expected WER, substitutions, deletions, insertions |
| `test_wer.py` | normalization: case, punctuation, danda, NFC equivalence |
| `test_wer.py` | `corpus_wer` sums edits rather than averaging per-utterance rates |
| `test_model_sweep.py` | `pareto_front` on synthetic points, including ties and full domination |
| `test_sarvam_stt.py` | satisfies `STTProvider`; buffers to `is_last`; emits one final transcript; opens a span; maps a mocked response correctly |
| `test_sarvam_stt.py` | `ProviderError` on API failure; `CancelledError` re-raised with the span closed |

**Integration (opt-in, skipped without `SARVAM_API_KEY` or datasets):** one
real Sarvam round trip; the three re-runs in A.3; one bounded real sweep.

---

## 8. Definition of done

- [x] `uv run pytest -m "not integration"` green (148 passed, ~12s -- over
      the "~5s" aspiration in the original estimate, but that number
      predates this phase's own tests and the project's growth since; not
      a regression introduced here, see section 11)
- [x] `uv run mypy --strict src/dhvani` clean
- [x] `uv run ruff check` and `ruff format --check` clean
- [x] CI workflow added (`.github/workflows/ci.yml`, ubuntu + windows,
      ruff/mypy/pytest), badge in the README -- **not yet observed green**,
      since that needs a real push and a real Actions run this build
      didn't perform; the workflow itself was validated by YAML-parsing it
      and by running every step it calls locally
- [x] **Svarah EER, LAHAJA EER and F1 re-run on Sarvam** -- run for real
      under Phase 3 section 2.1 once `SARVAM_API_KEY` became available;
      results and reading in `phase-2.md` section 18
- [x] `phase-2.md` §12 and §16 carry the share-of-achievable framing
- [x] Sweep table produced for Svarah (all 4 points Pareto-optimal) and
      now LAHAJA too (section 12: `tiny`/`int8`, `small`/`int8`,
      `small`/`float32` Pareto-optimal, `tiny`/`float32` dominated),
      operating point stated with its reason. LAHAJA needed a real fix
      (per-cell process isolation, not a bigger machine) after two
      memory-pressure kills running the grid in one process -- see
      section 12 for what actually worked.
- [x] Whichever of §17's three preregistered outcomes occurred, written
      down as the finding -- `phase-2.md` section 18: Svarah lands closest
      to "Saaras helps but doesn't replace the corrector"; LAHAJA lands
      squarely on "Saaras still misses them," identically to Whisper

---

## 9. If the week slips — cut in this order

1. **Cut the model sweep (B).** It is additive. Without it the project has
   no model-level work, which is a real gap, but nothing already published
   becomes wrong.
2. **Cut CI (C).** Half a day, and the tests still pass locally.
3. **Never cut A.** The Indic baseline is what makes the Phase 2 numbers
   defensible. Without it every F2 figure is contestable as fixing a
   problem the Phase 1 provider choice created, and that is the first
   question a competent interviewer asks.

---

## 10. Open questions for review

1. **Which Sarvam model.** A.1 flags the transcribe-versus-translate
   distinction as the thing to verify first. Getting it wrong produces a
   plausible-looking but meaningless EER, so it is called out rather than
   assumed. **Resolved in A.1**: it is a `mode` parameter
   (`mode="transcribe"`), not a model choice — `saaras:v3` is the default
   model either way.
2. **Sweep corpus and size.** Proposal: the same bounded Svarah and LAHAJA
   test samples already used for F2, so the WER numbers sit in the same
   frame as the EER numbers. Larger would be better and slower; `small` at
   `float32` on CPU is the slow corner of the grid.
3. **Whether `float32` is worth sweeping at all** on a CPU-only machine, or
   whether the grid should be size-only at `int8`. Worth one timing probe
   before committing the full grid.

---

## 11. Implementation notes (filled in during the build)

- `SARVAM_API_KEY` was **not available** in the environment this phase was
  built in (`GROQ_API_KEY` is set via `.env`; `SARVAM_API_KEY` is not).
  Per this spec's own ground rules (§3: every real-API test is
  `pytest.mark.integration` and skips cleanly without the key), the
  integration test and the real A.3 re-run against Sarvam are written and
  ready to run, but were not executed with real Sarvam responses as part
  of this build. This is recorded here rather than worked around, matching
  this project's "report honestly, including what didn't happen" ethos —
  see the real result once `SARVAM_API_KEY` is exported.
- `GROQ_API_KEY`, cached faster-whisper (`tiny`/`small`) checkpoints, and
  authenticated Hugging Face access to `ai4bharat/Svarah` and
  `ai4bharat/lahaja` (from Phase 2's own setup) were all available, so
  Workstream B's model sweep was run for real against Svarah/LAHAJA on
  this machine — see section 12 for the real numbers.
- `scripts/run_model_sweep.py` was written against `load_svarah`/
  `load_lahaja` (the plain loaders) first, then switched to
  `load_svarah_filtered`/`load_lahaja_filtered` before any real run --
  the plain loaders decode *every* row's embedded audio into memory before
  any bounded sampling happens, which is the exact memory-pressure bug
  phase-2 spec section 14 already hit and fixed for the EER eval. Caught
  by re-reading that section before running this script for real, not by
  hitting the crash again.

---

## 12. Model sweep -- real results (Workstream B)

### Timing probe (open question 3)

Before committing to the full grid, `n=5` probes on `small.` The result:
`float32` is genuinely the slow corner the spec anticipated (`small`
p50 10.5s vs. `int8`'s 7.0s, ~50% slower) but not so slow it needed
cutting -- both `int8` and `float32` are kept in the real grid below.

### Real sweep, Svarah (`n=20`, seed 0, `tiny`/`small` x `int8`/`float32`)

| model_size | compute_type | wer | stt_p50_ms | stt_p90_ms | realtime_factor | n | pareto |
|---|---|---|---|---|---|---|---|
| tiny | int8 | 33.7% | 1162.1 | 1780.7 | 0.14 | 20 | yes |
| tiny | float32 | 27.9% | 1552.6 | 2481.0 | 0.18 | 20 | yes |
| small | int8 | 14.6% | 7458.7 | 11256.2 | 0.87 | 20 | yes |
| small | float32 | 14.3% | 10461.5 | 15613.6 | 1.23 | 20 | yes |

All four points are Pareto-optimal -- a genuine tradeoff curve, no
dominated point in this grid on this sample, real data validating the
Pareto logic the same way the synthetic unit tests do.

### Operating point, stated with a reason (spec section B.3)

The shipped live-demo default is `small`/`int8` (`dhvani.live`,
`WhisperSTT`'s own `compute_type="int8"` default). This sweep is the
first real measurement of what that choice costs: **p50 STT latency of
7.46 seconds** against Svarah's ~8.6s-average utterances, for 14.6% WER.
Read against Phase 0's own `LatencyBudget` (`config.py`:
`Stage.STT: 200.0ms`), every point in this grid blows through the STT
stage budget by one to two orders of magnitude -- `tiny`/`int8`, the
fastest point measured, still lands at p50=1.16s, ~6x the 200ms budget.

**This is not a bug this phase introduces; it is the first real number
behind a gap the project's own instrumentation was already positioned to
catch** (`config.py`'s `LatencyBudget.violations` exists precisely to
surface this): `WhisperSTT` is deliberately non-streaming (phase-1 spec
section 2 -- it buffers the whole utterance, then transcribes once), so
its latency scales with utterance length in a way a 200ms budget written
for a *stage*, not a whole buffered transcription, never accounted for.
The honest reading is that the 200ms STT budget describes an aspiration
for a streaming ASR this project doesn't have, not a target `WhisperSTT`
was ever going to hit on multi-second utterances -- worth flagging for
whoever revisits `config.py`'s defaults, not silently absorbed into this
sweep's numbers.

**Stated operating point**: for a live conversational demo where
perceived latency matters more than the last few points of WER,
`tiny`/`float32` (WER 27.9%, p50 1.55s) is the more defensible choice of
the four measured here than the shipped `small`/`int8` default (WER
14.6%, p50 7.46s) -- it buys roughly a 5x latency reduction for a WER
cost that, per section 2's own reading, is still within the range this
project already treats as "the ASR problem," not a new failure mode. This
is offered as the reasoned pick the spec asks for, not a change actually
made to `dhvani.live`'s shipped default -- that decision affects the live
demo path and belongs to a deliberate choice by whoever owns that
tradeoff, not a side effect of running this sweep.

### Real sweep, LAHAJA (`n=20`, seed 0) -- completed

Killed by the host's own memory-pressure safeguard on the first two
attempts (once originally, once again under Phase 3 -- see phase-3 spec
§2.2 for that second attempt), both times with the full grid run
sequentially inside one long-lived process, the same way `run_sweep`
already ran the Svarah grid above. **The actual fix wasn't more memory --
it was running each `(model_size, compute_type)` grid cell as its own
separate OS process** (four separate `uv run python scripts/
run_model_sweep.py ... --model-sizes X --compute-types Y` invocations,
each with a single cell) rather than one process working through all four
sequentially. `faster-whisper`/`ctranslate2` evidently doesn't release
every native allocation back to the OS between model loads within one
process, so peak memory climbed across the sequential grid until the host
killed it; a fresh process per cell gets that memory back unconditionally
on exit, regardless of anything the library itself does or doesn't free.
Confirmed directly: free memory recovered from ~560MB to ~1.25GB between
the tiny-model cells and the small-model cells once each ran in its own
process. This is a real, generalizable finding for running this sweep
(or any repeated real-model eval) on a memory-constrained host, not
specific to LAHAJA.

| model_size | compute_type | wer | stt_p50_ms | stt_p90_ms | realtime_factor | n | pareto |
|---|---|---|---|---|---|---|---|
| tiny | int8 | 104.0% | 3447.6 | 16970.0 | 0.76 | 20 | yes |
| tiny | float32 | 109.7% | 6326.9 | 19496.3 | 0.95 | 20 | |
| small | int8 | 65.7% | 13739.2 | 49442.2 | 2.34 | 20 | yes |
| small | float32 | 64.5% | 17463.5 | 47939.5 | 2.57 | 20 | yes |

**Read honestly:**

- **WER is far worse across the board than Svarah's.** Even `small`
  (this project's shipped model family) only reaches 64.5%-65.7% WER on
  LAHAJA, against 14.3%-14.6% on Svarah. This is consistent with
  everything else this project has found about LAHAJA (100% `eer_before`
  on both Whisper and Sarvam, phase-2.md §15/§18) -- its accented,
  code-switched Hindi is a harder recognition problem than Svarah's
  accented English, for every ASR measured against it so far, not just
  for the entity-mention subset F2 scores.
- **`tiny` is not just less accurate here, it's badly worse**: WER over
  100% (more edits than reference words -- consistent with the model
  frequently mis-transcribing entire utterances rather than making a few
  word-level errors). `tiny`/`float32` is dominated outright by
  `tiny`/`int8` on both axes -- the one clearly bad grid point in the
  whole sweep, Svarah included.
- **Latency is far worse than Svarah's too, at every grid point** --
  `small`/`int8`'s own p50 here (13.7s) is nearly double its Svarah figure
  (7.46s), and p90 reaches 49.4s. LAHAJA's utterances running longer on
  average than Svarah's is the most likely explanation, consistent with
  buffer-then-transcribe latency scaling with utterance length (phase-3
  spec §3).
- **Pareto front**: `tiny`/`int8`, `small`/`int8`, `small`/`float32` --
  three real tradeoff points, `tiny`/`float32` dominated. `small`/`int8`
  vs. `small`/`float32` is a real, close tradeoff (0.9s p50 for 1.2 WER
  points more accuracy at `int8`), unlike Svarah where all four points
  were Pareto-optimal.
