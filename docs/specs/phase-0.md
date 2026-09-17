# Phase 0 — Instrumentation Spine

**Status:** ready to implement
**Depends on:** nothing
**Blocks:** every later phase
**Estimated size:** ~900–1,200 LOC including tests

---

## 1. Objective

Build the measurement layer and provider contracts that every later phase
reports into. Nothing in this phase talks to a network or loads a model.

The deliverable is answering one question precisely: **where did the
milliseconds go?** Phase 1 makes the agent fast; Phase 0 makes "fast" a number
you can assert in a test.

### In scope

- Typed core data model (audio, transcripts, LLM deltas, tool calls)
- Telemetry: spans, turn traces, session percentiles, ASCII waterfall rendering
- Provider protocols for STT / LLM / TTS
- Mock providers with declared, reproducible timing
- A deliberately sequential runner — the baseline Phase 1 must beat
- A latency budget that can flag violations
- Test suite, type checking, lint

### Explicitly out of scope

Do not build these. They belong to later phases, and building them now will
force rework.

- Any real provider (faster-whisper, Piper, Groq, Ollama, Sarvam)
- Overlapped / streaming orchestration — Phase 1
- VAD, endpointing, barge-in — Phase 1
- WebRTC or any transport — Phase 1
- Memory, entity correction, code-switch handling, safety — Phases 2–4
- A CLI beyond one trivial demo entry point
- Any persistence layer, database, or config file format beyond env vars

---

## 2. Ground rules

- **Python 3.13.** Modern syntax: `X | None`, `list[T]`, `StrEnum`,
  `@dataclass(frozen=True, slots=True)`, PEP 695 generics where natural.
- **Tooling:** `uv` for env and runs; `pytest` + `pytest-asyncio`; `mypy --strict`;
  `ruff` for lint and format.
- **Runtime dependencies: none.** Standard library only. Test and dev
  dependencies are fine. If a runtime dependency seems unavoidable, stop and
  flag it in the PR description rather than adding it.
- **Windows is the primary dev machine.** No POSIX-only assumptions: no
  `os.fork`, no signal handling that needs SIGALRM, no hardcoded `/tmp`, no path
  string concatenation — use `pathlib`.
- **Everything async** that will eventually touch I/O. Providers are async
  iterators even when mocked.
- **Public API gets docstrings.** One line on what it does, plus a note on units
  for anything time-related. Private helpers do not need them.
- **All times in nanoseconds internally** (`int`), exposed in milliseconds
  (`float`) at API boundaries. Name every float field with a `_ms` suffix and
  every int field with a `_ns` suffix. Keep this consistent — mixed units are
  the single most likely source of wrong numbers in this project.

---

## 3. Repo layout

```
pyproject.toml
README.md
ROADMAP.md
docs/specs/phase-0.md
src/dhvani/
    __init__.py
    types.py                  core data model
    clock.py                  Clock protocol, RealClock, FakeClock
    config.py                 settings + LatencyBudget
    telemetry/
        __init__.py
        span.py               Stage, Span, TurnTrace
        session.py            SessionTrace, percentiles
        waterfall.py          ASCII rendering
    providers/
        __init__.py
        base.py               STTProvider, LLMProvider, TTSProvider protocols
        mock.py               MockSTT, MockLLM, MockTTS
    pipeline/
        __init__.py
        sequential.py         SequentialRunner (baseline)
    demo.py                   python -m dhvani.demo -> prints a waterfall
tests/
    test_clock.py
    test_span.py
    test_session.py
    test_waterfall.py
    test_mock_providers.py
    test_sequential.py
    test_budget.py
```

Use a `src/` layout. Package name `dhvani`.

---

## 4. Core data model — `types.py`

All frozen dataclasses with `slots=True`.

```python
class Stage(StrEnum):
    CAPTURE   = "capture"     # audio arriving from transport
    ENDPOINT  = "endpoint"    # deciding the user stopped speaking
    STT       = "stt"
    LLM       = "llm"
    TOOL      = "tool"
    TTS       = "tts"
    PLAYBACK  = "playback"    # audio leaving toward the user


@dataclass(frozen=True, slots=True)
class AudioChunk:
    pcm: bytes          # 16-bit signed little-endian, mono
    sample_rate: int
    seq: int            # monotonic per stream, starts at 0
    is_last: bool = False

    @property
    def duration_ms(self) -> float: ...     # len(pcm) / 2 / sample_rate * 1000
    @property
    def n_samples(self) -> int: ...


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    is_final: bool
    language: str | None = None       # BCP-47, e.g. "hi-IN", "en-IN"
    confidence: float | None = None   # 0..1
    stability: float | None = None    # 0..1, partials only


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class LLMDelta:
    text: str = ""
    tool_call: ToolCall | None = None
    is_final: bool = False


@dataclass(frozen=True, slots=True)
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
```

Validate in `__post_init__` where it is cheap: `sample_rate > 0`,
`len(pcm) % 2 == 0`, confidence within `0..1`. Raise `ValueError` with a message
naming the offending field.

---

## 5. Time — `clock.py`

```python
class Clock(Protocol):
    def now_ns(self) -> int: ...
    async def sleep(self, seconds: float) -> None: ...
```

`RealClock` — backed by `time.perf_counter_ns()` and `asyncio.sleep`.

`FakeClock` — deterministic virtual time for tests. Requirement: a test that
simulates an 800 ms turn must complete in single-digit milliseconds of real
time, and must produce exactly reproducible recorded durations across runs.

**This is the one genuinely tricky part of Phase 0.** The recommended approach
is a custom `asyncio` event loop subclass that overrides `time()` so
`loop.call_later` and `asyncio.sleep` read virtual time, with the loop advancing
virtual time to the next scheduled callback when it would otherwise idle. That
is the standard technique and is how the asyncio test utilities work.

If it proves fragile, the acceptable fallback is a `ScaledClock` that sleeps
`seconds / factor` in real time while reporting virtual nanoseconds, with tests
asserting within a stated tolerance of ±5 ms virtual. **State in the PR
description which approach you used and why** — this is a specific review item.

Never call `time.perf_counter()` or `asyncio.sleep` directly outside
`clock.py`. Everything takes a `Clock`.

---

## 6. Telemetry

### 6.1 `telemetry/span.py`

```python
@dataclass(slots=True)
class Span:
    stage: Stage
    name: str
    start_ns: int
    end_ns: int | None = None
    attrs: dict[str, object] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None: ...
    @property
    def is_open(self) -> bool: ...


@dataclass(slots=True)
class Mark:
    name: str
    at_ns: int


class TurnTrace:
    """Timing record for one user-utterance to agent-response cycle."""

    turn_id: str
    t0_ns: int          # reference zero: end of user speech
    spans: list[Span]
    marks: list[Mark]

    def __init__(self, clock: Clock, turn_id: str | None = None) -> None: ...

    @contextmanager
    def span(self, stage: Stage, name: str, **attrs: object) -> Iterator[Span]: ...

    @asynccontextmanager
    async def aspan(self, stage: Stage, name: str, **attrs: object) -> AsyncIterator[Span]: ...

    def mark(self, name: str) -> None: ...

    def set_t0(self) -> None:
        """Pin the reference zero to now. Called at end-of-user-speech."""

    @property
    def ttfa_ms(self) -> float | None:
        """Time To First Audio: t0 to the FIRST_AUDIO_OUT mark. The number that
        matters. None if that mark was never recorded."""

    @property
    def total_ms(self) -> float | None: ...

    def critical_path(self) -> list[Span]:
        """Spans on the longest dependency chain from t0 to first audio."""

    def stage_total_ms(self, stage: Stage) -> float:
        """Wall-clock time covered by spans of this stage, counting overlapping
        spans ONCE — the union of intervals, not the sum of durations."""
```

Reserved mark names, defined as module constants:

- `USER_SPEECH_END` — sets `t0`
- `FIRST_PARTIAL` — first partial transcript available
- `FINAL_TRANSCRIPT`
- `FIRST_LLM_TOKEN`
- `FIRST_AUDIO_OUT` — defines TTFA

**Spans may overlap.** That is the entire point of the project — Phase 1 runs
STT, LLM and TTS concurrently. Never assume spans nest, never compute a total by
summing durations, and make `stage_total_ms` a true interval union. A test must
cover the overlapping case.

Both `span()` and `aspan()` must close the span on exception and re-raise, and
record `attrs["error"] = repr(exc)`.

### 6.2 `telemetry/session.py`

```python
class SessionTrace:
    session_id: str
    turns: list[TurnTrace]

    def add(self, turn: TurnTrace) -> None: ...

    def percentiles(self, stage: Stage) -> Percentiles: ...
    def ttfa_percentiles(self) -> Percentiles: ...

    def report(self) -> str:
        """Human-readable per-stage table: n, p50, p90, p99, max."""


@dataclass(frozen=True, slots=True)
class Percentiles:
    n: int
    p50_ms: float
    p90_ms: float
    p99_ms: float
    max_ms: float
```

Use `statistics.quantiles` with `method="inclusive"`, or nearest-rank for small
n. With fewer than two samples, p50 = p90 = p99 = the single value. Never crash
on an empty list — return `n=0` and zeros.

### 6.3 `telemetry/waterfall.py`

```python
def render(trace: TurnTrace, width: int = 72) -> str: ...
```

An ASCII Gantt of one turn, with spans positioned by **absolute time** so
overlap is visible. Roughly:

```
turn 7c2a  t0=0.0ms  TTFA=612.4ms
                    0ms      200ms     400ms     600ms
  stt      partial  |####....................        |  148.2ms
  stt      final    |    ###.....................    |   92.0ms
  llm      generate |      ##############.....       |  301.7ms
  tts      synth    |                 ########       |  160.5ms  <- critical
  ^ FIRST_AUDIO_OUT at 612.4ms
```

Requirements: pure ASCII, so it renders in a Windows terminal and in a GitHub
README code block; the critical path marked; marks shown on their own line; and
deterministic output for a given trace so it can be snapshot-tested.

---

## 7. Providers — `providers/base.py`

```python
class STTProvider(Protocol):
    name: str
    def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]: ...


class LLMProvider(Protocol):
    name: str
    def stream(
        self, messages: Sequence[Message], *, trace: TurnTrace,
        tools: Sequence[Mapping[str, object]] = (),
    ) -> AsyncIterator[LLMDelta]: ...


class TTSProvider(Protocol):
    name: str
    sample_rate: int
    def stream(
        self, text: AsyncIterator[str], *, trace: TurnTrace
    ) -> AsyncIterator[AudioChunk]: ...
```

Three contracts every implementation must honour:

1. **Emit telemetry.** Open an `aspan` for the provider stage, and record the
   relevant first-output mark (`FIRST_PARTIAL`, `FIRST_LLM_TOKEN`,
   `FIRST_AUDIO_OUT`).
2. **Be cancellable.** Phase 1 barge-in cancels a live TTS stream mid-sentence.
   Handle `asyncio.CancelledError`, close the span, release resources, re-raise.
   Never swallow it.
3. **`TTSProvider.stream` takes an async iterator of text, not a string.** This
   is what lets Phase 1 start synthesis on the first sentence while the LLM is
   still generating. Do not add a string convenience overload — it will get used,
   and it will silently destroy the overlap.

---

## 8. Mock providers — `providers/mock.py`

Timing is **declared, not measured**, so tests are reproducible.

```python
@dataclass(frozen=True, slots=True)
class MockTiming:
    ttfb_ms: float        # first output, measured from stream start
    per_unit_ms: float    # per partial / token / audio chunk thereafter
```

- `MockSTT(partials, final, timing, clock)` — emits each partial, then one final
  transcript.
- `MockLLM(response, timing, clock, tool_calls=())` — emits `response` split on
  whitespace, one `LLMDelta` per token, then a final delta. If `tool_calls` is
  non-empty, emit those before the final.
- `MockTTS(timing, clock, sample_rate=16000, chunk_ms=20)` — consumes the text
  iterator and emits silence chunks (zeroed PCM), one chunk per `chunk_ms` of
  synthetic audio.

Mocks must also be **scriptable to fail**: a `fail_after: int | None` parameter
that raises `ProviderError` after N outputs. Phase 1 needs failure paths, and
adding this later means touching every call site.

---

## 9. Baseline runner — `pipeline/sequential.py`

```python
class SequentialRunner:
    """Deliberately sequential: STT completes, then LLM completes, then TTS.
    No overlap. Exists to validate the telemetry end to end, and to be the
    baseline number the Phase 1 overlapped runner must beat. Do not optimize."""

    def __init__(self, stt, llm, tts, clock, budget: LatencyBudget) -> None: ...
    async def run_turn(self, audio: AsyncIterator[AudioChunk]) -> TurnResult: ...


@dataclass(frozen=True, slots=True)
class TurnResult:
    transcript: str
    response_text: str
    audio: list[AudioChunk]
    trace: TurnTrace
```

Because it is sequential, TTFA should land within a few milliseconds of the sum
of the three mock stage times. That property is the acceptance test for the
whole telemetry layer — if it does not hold, the instrumentation is wrong.

---

## 10. Config — `config.py`

```python
@dataclass(frozen=True, slots=True)
class LatencyBudget:
    ttfa_target_ms: float = 800.0
    stage_budgets_ms: Mapping[Stage, float] = ...   # endpoint 300, stt 200,
                                                    # llm 300, tts 150
    def violations(self, trace: TurnTrace) -> list[BudgetViolation]: ...


@dataclass(frozen=True, slots=True)
class BudgetViolation:
    stage: Stage | None       # None means the overall TTFA target
    budget_ms: float
    actual_ms: float

    @property
    def over_by_ms(self) -> float: ...
```

Settings come from environment variables prefixed `DHVANI_`, read through a
single `Settings.from_env()`. No config file format in Phase 0.

---

## 11. Tests

`pytest-asyncio` in strict mode. **No network, no model downloads, and no
sleeping longer than about 50 ms of real time across the entire suite.**

Required cases:

| File | Case | Asserts |
|---|---|---|
| `test_clock.py` | fake clock determinism | two identical runs give identical recorded ns |
| `test_clock.py` | sleep ordering | concurrent sleepers wake in the right order |
| `test_span.py` | span records duration | within tolerance of declared |
| `test_span.py` | **overlapping spans** | `stage_total_ms` is the interval union, not the sum |
| `test_span.py` | exception closes span | span closed, `attrs["error"]` set, exception propagates |
| `test_span.py` | ttfa from t0 | measured from `USER_SPEECH_END` to `FIRST_AUDIO_OUT` |
| `test_span.py` | ttfa is None | when `FIRST_AUDIO_OUT` never fires |
| `test_session.py` | percentiles | known inputs, known p50 / p90 / p99 |
| `test_session.py` | degenerate n | n=0 and n=1 do not crash |
| `test_waterfall.py` | snapshot | deterministic ASCII for a fixed trace |
| `test_waterfall.py` | overlap visible | two concurrent spans render on overlapping columns |
| `test_mock_providers.py` | declared timing honoured | each mock emits its first output at `ttfb_ms` |
| `test_mock_providers.py` | cancellation | cancelling mid-stream closes the span and re-raises |
| `test_mock_providers.py` | `fail_after` | raises `ProviderError` at the right point |
| `test_sequential.py` | **baseline TTFA** | approximately the sum of the three mock stage times |
| `test_sequential.py` | trace completeness | all five reserved marks present, in order |
| `test_budget.py` | violation detection | over-budget stage reported with correct `over_by_ms` |

---

## 12. Definition of done

All of these pass on Windows:

- [ ] `uv run pytest` — green, whole suite under 5 seconds
- [ ] `uv run mypy --strict src/dhvani` — clean, and no `# type: ignore` without
      a comment explaining why
- [ ] `uv run ruff check` and `uv run ruff format --check` — clean
- [ ] `uv run python -m dhvani.demo` — runs a mock turn, prints a waterfall and
      a percentile table
- [ ] `src/dhvani` imports nothing outside the standard library
- [ ] No test touches the network, or the filesystem outside `tmp_path`

Commit in logical units — types, clock, telemetry, providers, runner, demo —
rather than one large commit. No attribution or co-author trailers in commit
messages.

---

## 13. Do not box in Phase 1

Phase 1 adds the overlapped runner, VAD, barge-in and WebRTC. Four properties
must survive this phase, or Phase 1 becomes a rewrite:

1. STT yields **partials before the final**, so the overlapped runner can start
   the LLM on a stable partial instead of waiting for the final transcript.
2. TTS consumes an **async text iterator**, so synthesis begins on the first
   sentence.
3. Every stream is **cancellable**, so barge-in can abort a turn mid-flight.
4. `TurnTrace` tolerates **concurrent open spans**, and nothing anywhere assumes
   spans nest or that durations sum to a total.

---

## 14. Open question for review

The `FakeClock` design in section 5 is the one place this spec does not fully
settle the approach. Implement it, note in the PR which technique you chose and
what broke if you fell back, and leave it flagged for review.
