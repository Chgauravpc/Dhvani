# Phase 2 — F1 + F2

**Status:** F1 implemented and run for real (milestone numbers captured,
section 12). F2's code is implemented and unit-tested; the real
Svarah/LAHAJA-backed entity-density gate (section 2A) and EER numbers are
blocked on Hugging Face access -- see section 11.
**Depends on:** Phase 0 (instrumentation), Phase 1 (real providers,
overlapped runner, WebRTC transport)
**Blocks:** Phase 3 (F3 + channel robustness)

---

## 1. Objective

Measure the ASR bottleneck on our own stack (F1), then show
`dhvani-entity` recovers a measured share of it (F2). The milestone this
phase exists to produce, verbatim from `ROADMAP.md`:

> "the agent loses X% of task success to transcription alone, and
> `dhvani-entity` recovers Y% of it."

F1 is nearly free once Phase 1 exists — it's an ablation over the
pipeline that already runs. F2 is the flagship deliverable.

---

## 2. Research grounding (checked, not assumed)

- **VoiceAgentBench** (`krutrim-ai-labs/VoiceAgentBench` on Hugging Face,
  arXiv 2510.07978) is the actual paper `ROADMAP.md`'s thesis cites for
  the ASR-bottleneck and refusal-collapse numbers. Confirmed directly: it
  ships **real audio** (`.wav`) per example, not just text, plus an
  `expected_tool_call` ground truth and a `functions` tool spec, across
  English + 6 Indic languages including Hindi. Downloadable without gated
  access. This lets F1's ablation harness use a real subset of the actual
  benchmark the project's own thesis cites, instead of a synthetic
  stand-in — directly validating the cited claim "on our own stack."
  **Caveat that must reach the report:** VoiceAgentBench's audio is
  synthesized (text queries run through TTS, with voice diversity drawn by
  farthest-point sampling over speaker embeddings). Whisper handles clean
  synthetic speech better than real accented speakers, so F1's measured ASR
  penalty is a **lower bound** on the real-world penalty, not an estimate of
  it. Say so wherever the F1 number is quoted.
- **Svarah** (AI4Bharat): 9.6 hours, Indic-accented **English**, 117
  speakers, 19 states. `.wav` + manifest JSON (`audio_filepath`,
  `duration`, `text`, speaker metadata). Open, no gating.
- **LAHAJA** (AI4Bharat, arXiv 2408.11440): 12.5 hours, multi-accent
  **Hindi**, 132 speakers, 83 districts. CC BY 4.0. Its own paper reports
  that ASR "performance declines... especially with content heavy in
  named entities and specialized terminology" — the dataset's own authors
  already flag the exact failure mode F2 targets. Gated on Hugging Face
  (accept conditions); also available via AI4Bharat's dataset portal and
  IndiaAI.
- **Neither dataset ships entity-span annotations.** Evaluation has to
  derive them: filter each dataset's ground-truth transcripts for mentions
  of lexicon entities (keyword/regex search over the known variant
  strings), and treat those hits as the entity ground truth for Entity
  Error Rate.
- **Cross-script phonetic matching**: `indic-transliteration` (PyPI)
  converts Devanagari/Tamil/etc. to a romanized scheme (ITRANS/HK/SLP1),
  which combined with `rapidfuzz` (fast approximate string matching) gives
  cross-script fuzzy entity matching without a heavy NLP dependency.
  `aksharamukha` (120 scripts) is a heavier alternative not needed here.
  **Not yet verified against the real installed API** — see open
  questions; do that before writing `phonetic.py`, the way Phase 1
  verified every real provider API before coding against it.

---

## 2A. Gate: entity density — run this before writing any code

F2's entire headline number is an Entity Error Rate computed over the
examples in Svarah and LAHAJA whose transcripts mention a lexicon entity.
Neither dataset was built around civic terminology: Svarah's domains are
history, culture and tourism plus some use-case audio, and LAHAJA is
general read and spontaneous speech. There is no guarantee that a ~20-entry
civic lexicon finds enough mentions to compute a meaningful rate.

**This is a go/no-go gate, not a risk to note and move past.** An EER over
eight mentions is not a result, and discovering that after building the
corrector wastes the phase.

Do this first, in this order:

1. Download the Svarah and LAHAJA manifests only (no audio yet).
2. Grep the ground-truth transcripts for every variant of every candidate
   lexicon entry.
3. Report mentions per entity and total mentions per dataset.

Decision rule:

- **≥100 total mentions** across a dataset: proceed as planned.
- **30-100**: proceed, but report a confidence interval alongside the EER
  and expand the lexicon toward whatever terms the data actually contains.
- **<30**: stop and change corpus. Options, in preference order: widen the
  lexicon to the entity types these datasets do carry (place names,
  institutions, personal names — all still cross-script matching problems);
  or use the IndicVoices use-case split, which was recorded around digital
  payments, government services and grocery ordering and is far likelier to
  be entity-dense.

Whichever way it goes, the mention counts are themselves a result worth
keeping — they say something real about what public Indic speech corpora
cover.

---

## 3. In scope / explicitly out of scope

**In scope:**
- F1 — ASR ablation harness on a VoiceAgentBench subset: real ASR vs
  ground-truth transcript, task-success delta, per language.
- F2 — `dhvani-entity`: domain lexicon + cross-script phonetic matching +
  corrector, evaluated as Entity Error Rate before/after on Svarah and
  LAHAJA.
- Tying F1 and F2 together for the milestone number: of the task-success
  failures F1 attributes to transcription, how many are entity-driven, and
  how many does `dhvani-entity` recover.
- Wiring `CorrectedSTT` into the live demo (`dhvani.live`) — cheap, since
  it's a drop-in `STTProvider` wrapper, and worth showing live rather than
  only in a report.

**Explicitly out of scope (do not build these here):**
- F3 (code-switching), F4 (safety), F5 (turn-taking) — later phases.
- Exhaustive replication of VoiceAgentBench across all 7 languages — a
  deliberate subset only (see open questions).
- Extending the lexicon beyond Devanagari/Latin/Tamil — `ROADMAP.md` puts
  Tamil/Telugu/Bengali/Marathi/Malayalam expansion in "Beyond."
- Publishing `dhvani-entity` to PyPI — also "Beyond."
- Any change to the overlapped runner, barge-in, or transport contracts
  from Phase 1.

---

## 4. New ground rules

- New runtime dependencies: `indic-transliteration`, `rapidfuzz`.
- Dataset access via `huggingface_hub` (already a dependency since Phase
  1) for manual manifest/audio download — not the heavier `datasets`
  library, which this project has no other use for.
- Real-dataset tests (VoiceAgentBench, Svarah, LAHAJA downloads and any
  run against them) are `pytest.mark.integration`, keeping default
  `uv run pytest` network- and download-free, matching Phase 0/1.
- `CorrectedSTT` must satisfy the exact `STTProvider` protocol from Phase
  0, unchanged.

---

## 5. Repo layout additions

```
src/dhvani/
    entity/
        __init__.py
        lexicon.py            DomainLexicon, LexiconEntry
        phonetic.py           script-aware phonetic key generation
        corrector.py          EntityCorrector
    providers/
        corrected_stt.py      CorrectedSTT (wraps any STTProvider)
    eval/
        __init__.py
        datasets.py           manifest loaders: VoiceAgentBench subset, Svarah, LAHAJA
        task_success.py       F1 harness + tool-call judge
        entity_error_rate.py  F2 EER computation
        report.py             produces the milestone numbers
scripts/
    run_f1_ablation.py
    run_f2_entity_eval.py
```

---

## 6. Design per module

### 6.1 `entity/lexicon.py`

```python
@dataclass(frozen=True, slots=True)
class LexiconEntry:
    canonical: str                              # e.g. "Aadhaar"
    variants: Mapping[str, Sequence[str]]       # script -> known spellings/mentions
    # e.g. {"devanagari": ["आधार"], "latin": ["aadhar", "adhaar", "aadhaar"]}


class DomainLexicon:
    def __init__(self, entries: Sequence[LexiconEntry]) -> None: ...
    def all_variants(self) -> Iterator[tuple[str, str, str]]:
        """Yields (canonical, script, variant) for every entry."""
    def find(self, canonical: str) -> LexiconEntry | None: ...
```

Starter set: ~15-30 curated civic/government/finance entities (Aadhaar,
PAN, EPFO, Ayushman Bharat, Pradhan Mantri Awas Yojana, UPI, IFSC, etc. —
matching `ROADMAP.md`'s own examples), across Devanagari, Latin, and
Tamil variants. Exact count/list is an open question (section 9).

### 6.2 `entity/phonetic.py`

```python
def phonetic_key(text: str, script: str) -> str:
    """Transliterate `text` to a common romanized form and normalize
    (case, common Indic-English spelling variance) for fuzzy comparison."""
```

Implementation depends on verifying `indic-transliteration`'s real API
first (open question).

### 6.3 `entity/corrector.py`

```python
@dataclass(frozen=True, slots=True)
class Correction:
    span: tuple[int, int]      # character offsets in the original text
    original: str
    corrected: str
    canonical_entity: str


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    text: str                  # corrected transcript
    corrections: list[Correction]


class EntityCorrector:
    def __init__(self, lexicon: DomainLexicon, threshold: float = 0.82) -> None: ...
    def correct(self, text: str, script: str = "latin") -> CorrectionResult:
        """Slides a small n-gram window over `text`, phonetic-key-matches
        each window against the lexicon via rapidfuzz, replaces windows
        scoring above `threshold` with the canonical form."""
```

`threshold` is the single knob that trades recovery against corruption, and
0.82 is a starting guess with nothing behind it. **Tune it on a dev split
and report on a test split.** Splitting the entity-bearing examples
roughly 30/70 dev/test, sweeping the threshold on dev, then running test
once is the difference between a measured result and a number fitted to
its own evaluation set.

Record the chosen threshold and the dev sweep in the report. A reader
should be able to see the recovery-versus-corruption tradeoff, not just
the point that was picked from it.

### 6.4 `providers/corrected_stt.py`

```python
class CorrectedSTT:
    """Wraps any STTProvider, applying EntityCorrector to its output.
    Satisfies STTProvider exactly -- Phase 0's contract, unchanged."""

    def __init__(self, inner: STTProvider, corrector: EntityCorrector) -> None: ...

    @property
    def name(self) -> str: ...  # f"{inner.name}+dhvani-entity"

    def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]:
        """Passes through inner.stream()'s transcripts with `.text` run
        through `corrector.correct()`.

        Opens its own span, nested inside the inner provider's. Correction
        is O(windows x lexicon) under rapidfuzz, which is cheap but not
        free on a long transcript, and a project whose whole argument is
        per-stage measurement should not have an unmeasured stage. The
        span also makes it possible to say later whether correction is
        worth its own latency."""
```

### 6.5 `eval/datasets.py`

Manifest loaders, each returning a small dataclass sequence (no `datasets`
library dependency):

```python
@dataclass(frozen=True, slots=True)
class VoiceAgentBenchExample:
    id: str
    audio_path: Path
    language: str
    functions: list[Mapping[str, object]]
    expected_tool_call: Mapping[str, object]


def load_voiceagentbench_subset(
    languages: Sequence[str], n_per_language: int, cache_dir: Path | None = None
) -> list[VoiceAgentBenchExample]: ...


@dataclass(frozen=True, slots=True)
class TranscriptExample:
    audio_path: Path
    ground_truth_text: str


def load_svarah(cache_dir: Path | None = None) -> list[TranscriptExample]: ...
def load_lahaja(cache_dir: Path | None = None) -> list[TranscriptExample]: ...
```

### 6.6 `eval/task_success.py` (F1)

```python
class GroundTruthSTT:
    """Test-only STTProvider: yields a single final Transcript equal to a
    pre-supplied ground-truth string, ignoring the audio entirely. This is
    the "if ASR were perfect" arm of the ablation."""

    def __init__(self, ground_truth_text: str) -> None: ...
    def stream(self, audio, *, trace) -> AsyncIterator[Transcript]: ...


@dataclass(frozen=True, slots=True)
class AblationReport:
    per_language: Mapping[str, "LanguageResult"]


@dataclass(frozen=True, slots=True)
class LanguageResult:
    n: int
    success_rate_ground_truth: float
    success_rate_real_asr: float
    success_rate_corrected_asr: float


async def run_ablation(
    examples: Sequence[VoiceAgentBenchExample],
    make_real_stt: Callable[[], STTProvider],
    make_corrected_stt: Callable[[], STTProvider],
    llm: LLMProvider,
    clock: Clock,
) -> AblationReport:
    """For each example, runs the LLM against (a) GroundTruthSTT, (b) the
    real STT, and (c) the corrected STT, given the example's `functions`
    spec as available tools. Scores each condition's tool call against
    `expected_tool_call` (function name + argument match) via
    `judge_tool_call`. Aggregates success rate per language per condition.
    """


def judge_tool_call(
    actual: Mapping[str, object] | None, expected: Mapping[str, object]
) -> bool:
    """Exact match on function name; argument values compared with light
    normalization (case-insensitive, whitespace-trimmed) since ASR/LLM
    phrasing varies even when the intent is right."""
```

Note on comparability: VoiceAgentBench scores parameter filling with an
LLM judge validated against human labels. Exact-match-plus-normalization
is stricter, so these success rates will read lower than the paper's.
That is fine — the ablation only needs the *delta* between conditions to
be meaningful, and a deterministic judge makes that delta reproducible.
But do not put our absolute numbers next to the paper's as if they
measured the same thing.

### 6.7 `eval/entity_error_rate.py` (F2)

```python
@dataclass(frozen=True, slots=True)
class EerReport:
    split: str                # "dev" while tuning, "test" for the reported run
    threshold: float          # the value this run used

    n_entity_mentions: int
    eer_before: float         # fraction of mentions ASR got wrong, uncorrected
    eer_after: float          # fraction still wrong after correction

    n_clean_examples: int     # examples containing NO lexicon entity
    corruption_rate: float    # fraction of those the corrector altered


async def compute_entity_error_rate(
    examples: Sequence[TranscriptExample],
    lexicon: DomainLexicon,
    stt: STTProvider,
    corrector: EntityCorrector,
    clock: Clock,
    split: str,
) -> EerReport:
    """Transcribes `examples`, scores entity recovery, and measures the
    damage the corrector does to text it should not touch.

    Entity-bearing arm: examples whose ground truth contains a lexicon
    variant. For each mention, check whether the canonical form is present
    in the raw transcript and in the corrected transcript.

    Clean arm: examples whose ground truth contains no lexicon variant at
    all. Run the corrector over them and count how many come back changed.
    """
```

**Score with exact match on the canonical form, never with
`phonetic_key`.** The corrector matches by phonetic key; if the scorer
also matches by phonetic key, the same component both makes and grades the
correction. A weak key then fails both steps together and a strong one
passes both, and the measurement cannot tell the two apart. Case-folded
exact string comparison against the canonical is independent of the
mechanism under test, which is the whole point of a scorer.

**Always report `corruption_rate` beside the EER.** `eer_before` and
`eer_after` measure recall only: how many entities came back. A fuzzy
matcher sliding an n-gram window over every transcript will also rewrite
text that was already correct, and nothing in the entity-bearing arm would
ever notice. A corrector that recovers 7 points of EER while altering 3%
of clean transcripts is not an improvement, and the pair of numbers is the
only way to see that.

**Tune on dev, report on test.** The threshold sweep runs against
`split="dev"`. The number that goes in the README comes from a single
`split="test"` run at the chosen threshold. Re-running test to pick a
better-looking threshold turns the result into a fit.

### 6.8 `eval/report.py`

Combines an `AblationReport` and an `EerReport` into the milestone's
X%/Y% framing: task-success lost to transcription (ground-truth rate minus
real-ASR rate), and the share of that loss recovered by `dhvani-entity`
(real-ASR rate vs corrected-ASR rate, as a fraction of the gap to
ground-truth). Renders a short markdown summary for the README.

---

## 7. Testing strategy

Same tiering as Phase 1:

- **Unit tests (CI, fast, no network/model):** lexicon lookup, phonetic
  key generation (once `indic-transliteration`'s real output format is
  verified — pin exact expected values, not approximate ones),
  `EntityCorrector.correct()` replacement logic against synthetic
  ASR-error-shaped strings, `CorrectedSTT` wrapping Phase 0's existing
  `MockSTT`, `judge_tool_call`'s matching logic against synthetic
  actual/expected pairs.
- **Integration tests (opt-in, `pytest.mark.integration`):** real
  VoiceAgentBench/Svarah/LAHAJA downloads, and real end-to-end
  `run_ablation`/`compute_entity_error_rate` runs (the latter needs a real
  `GROQ_API_KEY` for the LLM side of F1, same as Phase 1's Groq
  integration test).
- **Milestone verification:** the reproducible eval commands (section 8)
  run once, the numbers captured for the README, same spirit as Phase 1's
  live-demo verification being manual/one-off rather than a CI assertion.

---

## 8. Definition of done

- `uv run pytest` (default, no `-m integration`) green and fast — no new
  network/download dependency in the default suite.
- `uv run mypy --strict` clean on all new modules.
- `uv run ruff check` / `ruff format --check` clean.
- `uv run python -m dhvani.eval.task_success --languages hi,en` (or
  equivalent CLI) reproduces the F1 numbers.
- `uv run python -m dhvani.eval.entity_error_rate --dataset lahaja` (and
  `svarah`) reproduces the F2 numbers.
- The milestone's X%/Y% numbers captured, honestly, including if the
  recovery is smaller than hoped — matching this project's "report the
  waterfall honestly" ethos from Phase 0.
- The section 2A entity-density gate run and its mention counts recorded,
  before any corrector code exists.
- `corruption_rate` reported next to every EER figure, never on its own.
- The threshold sweep run on dev and the reported EER produced by a single
  test-split run, with both the sweep and the chosen value in the report.
- Every quoted F1 number carries the note that VoiceAgentBench audio is
  synthesized, so the figure is a lower bound on the real ASR penalty.

---

## 9. Open questions for review

1. **VoiceAgentBench subset size/languages for F1.** Default proposal:
   Hindi (primary) + English (baseline), ~30-50 examples each — not the
   full 5,500+, which would make the harness slow and expensive (real Groq
   calls) for marginal additional signal at this stage.
2. **Exact starter lexicon entries for F2.** Default proposal: ~20 common
   civic/government/finance terms across Devanagari/Latin/Tamil (Aadhaar,
   PAN, EPFO, Ayushman Bharat, Pradhan Mantri Awas Yojana, UPI, IFSC, and
   similar). Needs a concrete curated list before `lexicon.py` is written.
3. **`indic-transliteration` vs alternatives.** Verify at implementation
   time that it installs cleanly and its real output format fits the
   fuzzy-match approach — not yet checked against the actual package, the
   way every Phase 1 provider API was checked before code was written
   against it.

---

## 10. Open questions — resolved

1. **VoiceAgentBench subset:** Hindi + English, restricted to
   `category == "single_tool"` (~40 examples/language, checked directly:
   the dataset has 6 category subsets across 7,663 files; `single_tool`'s
   `expected_tool_call` is a single call, which is what `judge_tool_call`'s
   design can score — `parallel_tool`/`seqdep_tool` carry ordered lists of
   calls and `multi_turn` needs chat-history plumbing, neither of which
   this judge handles).
2. **Starter lexicon:** 20 civic/government/finance entries, implemented
   in `entity/lexicon.py`. Devanagari and Latin variants hand-curated;
   Tamil variants machine-generated from a verified ITRANS seed for 8 of
   the 20 (acronyms and English-loanword phrases carry no Tamil variant —
   transliterating those phonetically through Sanskrit-oriented ITRANS
   rules is guesswork, not what the scheme is for). Flagged in the module
   for a native Tamil speaker's sanity check.
3. **`indic-transliteration`:** installs cleanly (`2.3.82`). Its casual-
   Latin interpretation needs the **ITRANS** scheme specifically, not HK —
   verified directly: `sanscript.transliterate("aadhaar", HK, DEVANAGARI)`
   gives "अअधअर्", not "आधार", because HK expects capitalized long vowels.
   See `entity/phonetic.py`'s docstring for the full verification.

---

## 11. Corrections found while implementing (verified, not assumed)

Same practice as phase-1 spec section 10: checked against the actual
installed packages and real API responses, not assumed from documentation.

- **Both Svarah and LAHAJA are gated on Hugging Face**, not just LAHAJA as
  this spec originally assumed from secondary sources. A real
  `hf_hub_download` attempt against `ai4bharat/Svarah` returned
  `GatedRepoError`. Both need an authenticated `huggingface_hub` login that
  has accepted each dataset's terms before `load_svarah`/`load_lahaja` (or
  `scripts/entity_density_gate.py`) will work.
- **Svarah and LAHAJA ship as Hugging Face parquet with embedded audio**,
  not the raw `.wav` + JSON-manifest layout this spec's citation of
  Svarah's own README manifest format described — that format is what the
  *original* (non-Hugging-Face) Svarah release uses. Reading parquet still
  doesn't need the `datasets` library, just `pyarrow` (added as a
  dependency instead).
- **VoiceAgentBench's `expected_tool_call` is not the flat
  `{"name": ..., "arguments": ...}` shape section 6.6 sketched.** The real
  shape, checked directly: a list containing exactly one
  `{function_name: {param: [acceptable value variants]}}` dict.
- **VoiceAgentBench's `functions` specs use Python-style type names**
  (`"dict"`, `"float"`) where JSON Schema wants `"object"`/`"number"` —
  found by scanning every `type` value across 50 real examples. A real
  Groq call rejects the raw values with a 400 (metaschema validation
  failure) until normalized.
- **A VoiceAgentBench audio file named `.wav` is actually MP3** — `ID3`
  tag, `Lavf60.16.100` encoder signature, confirmed by reading the file's
  own bytes. Decoded via `av` (PyAV), already a transitive dependency, the
  same way `transport/webrtc.py` already resamples live audio.
- **`GroqLLM` accepted `tools` for protocol conformance but never mapped
  tool-call deltas back into `LLMDelta`** (a real Phase 1 gap, not a
  Phase 2 quirk) — closed, since F1 needs real tool calls to judge.
  Verified Groq's real streaming shape: for `openai/gpt-oss-20b` a tool
  call arrived as one complete chunk, but `id`/`function.name` are only
  guaranteed on a call's *first* fragment in the general streaming
  convention this mirrors, so the fix accumulates by `index` rather than
  assuming single-chunk delivery.
- **A real ablation run surfaced two distinct Groq failure modes** beyond
  the schema issues above: a false negative from comma-spacing variance
  ("Bandra,Mumbai" vs "Bandra, Mumbai", fixed in `judge_tool_call`'s
  normalization) and a genuine intermittent `groq.APIError` when the
  *model's own* generated tool call failed Groq's server-side schema
  validation (`expected integer, but got number`) — the harness now counts
  a provider failure as a task failure for that one example rather than
  aborting the whole run.
- **ASR output script cannot be assumed from the spoken language.** Real
  Hindi audio (VoiceAgentBench, multiple examples) transcribed through
  `WhisperSTT`'s `tiny` model came back romanized ("Varanasi mein Achesh
  Shaka Hari restaurant batao...", not Devanagari), reproducibly, not as a
  one-off. Whether the project's real default (`small`) behaves the same
  way is unverified — this sandboxed environment cannot download it (same
  restriction phase-1 spec section 11 hit). `EntityCorrector` therefore
  detects each candidate window's script independently
  (`phonetic.detect_script`) instead of trusting a single script for the
  whole transcript.

---

## 12. F1 milestone numbers (real run)

Captured via `uv run python scripts/run_f1_ablation.py --languages
english,hindi --n-per-language 40`, `DHVANI_WHISPER_MODEL=tiny` (this
sandboxed environment cannot download the real default `small` model —
same restriction as phase-1; the shipped default in `dhvani.live` is
unaffected). Real Groq (`openai/gpt-oss-20b`), real `faster-whisper`.

| language | n  | ground truth | real ASR | loss to ASR |
|----------|----|--------------|----------|--------------|
| english  | 40 | 42.5%        | 15.0%    | 27.5%        |
| hindi    | 40 | 17.5%        | 7.5%     | 10.0%        |

**Read honestly, not favorably:**

- Both numbers carry the lower-bound caveat from section 2:
  VoiceAgentBench's audio is synthesized, so real-world accented speech
  would very likely show a larger ASR penalty than this.
- The ground-truth condition itself is well under 100% (42.5% / 17.5%),
  which is expected given `judge_tool_call`'s exact-match-plus-
  normalization design (section 6.6: stricter than VoiceAgentBench's own
  LLM-judge scoring) and this run's speed-optimized model choices
  (`tiny` Whisper, `openai/gpt-oss-20b` at `reasoning_effort="low"`) — not
  a claim that the underlying agent is only ~20-40% competent.
- Hindi's loss-to-ASR (10.0%) reading *smaller* than English's (27.5%) is
  counterintuitive given the project's own thesis (Indic ASR is the
  weaker link) and is most likely an artifact of Hindi's ground-truth
  success rate already being low (17.5%) — there is less headroom left
  for ASR to lose. Re-running with the real `small` Whisper model, on a
  machine that can download it, is needed before reading anything into
  this specific comparison.
- F2's real numbers (entity recovery) are not yet available -- see
  section 11's Hugging Face access note.

---

## 13. Live re-verification with `CorrectedSTT` in the pipeline (real browser)

Re-ran phase-1 spec section 11's methodology (real system Chrome via
Playwright, `channel="chrome"`, fake-microphone flags feeding a real
Piper-synthesized question) to confirm Phase 2's changes to `dhvani.live`
(wiring `CorrectedSTT` in) didn't break the live path. Playwright was
added as a dev dependency for this, then removed afterward, same as
phase-1 didn't keep it either — this is a one-off verification tool, not
a permanent test dependency.

**Found and fixed a real methodology bug, not a product bug**: the first
run showed real non-silent audio reaching the server (confirmed via a
temporary RMS diagnostic) but no turn ever completed, even after 60+
seconds. Cause: Chrome's `--use-file-for-fake-audio-capture` loops the
input file back-to-back with no gap, and the synthesized WAV had no
trailing silence — so the endpointer's VAD never saw the 500ms of quiet it
needs to fire `SPEECH_ENDED`, and `WhisperSTT` (which just buffers until
its audio iterator ends) buffered forever. Padding 1.5s of silence onto
the test WAV fixed it: each loop cycle then has a real speech-then-silence
boundary.

**With that fixed, confirmed working end-to-end**, independently at each
layer, same spirit as phase-1's original verification: real captured
audio (RMS in the thousands, not silence) → Silero firing `SPEECH_STARTED`
/`SPEECH_ENDED` → `faster-whisper` transcribing (`tiny` model, since this
sandboxed environment still can't download `small`) → a real
`POST api.groq.com/.../chat/completions` returning `200 OK` → Piper
synthesizing → that audio arriving back at the browser (Chrome's own
`inbound-rtp` `totalAudioEnergy` > 0, not a custom analyser script).
`CorrectedSTT` ran on every transcript with no crash (confirmed via the
new per-turn log line — see below) — the entity-density gate hasn't run
yet, so no assertion is made here about whether it *changed* the
transcript, only that it doesn't break the pipeline.

**Also found, and this one's real**: the looping test audio repeatedly
triggered barge-in (a new `SPEECH_STARTED` arriving while the previous
turn's TTS was still playing back, since the loop restarts before a slow
`tiny`-model turn finishes) — the barge-in path was exercised for real,
unintentionally, and handled without crashing. Separately, `tiny`
Whisper's language detection was unreliable on this audio (`en` at
0.22-0.73 confidence, never `hi`, despite the input being Hindi) and one
transcript came back as a clear hallucination ("Thank you for watching.")
— a known `tiny`-model failure mode on ambiguous/foreign audio, not a
Phase 2 regression. (Update, section 14: `small` was re-tried directly
right after this and downloaded and loaded fine -- whatever caused
phase-1's "small" download failures in this sandbox is no longer
happening, so this specific "unverified" note turned out to be
short-lived.)

**Kept from this exercise**: `pipeline/session.py` now logs each
completed turn's transcript and TTFA, and each barge-in interruption, at
INFO level (previously a crashed session logged nothing about what it was
even doing) — this is genuinely useful live-demo observability, not a
test-only artifact, so it stayed in the code after the temporary RMS
diagnostic was removed.

---

## 14. F2 real numbers -- the entity-density gate and EER (real run)

**Hugging Face access**: granted (both `ai4bharat/Svarah` and
`ai4bharat/Lahaja` accepted). Worth recording precisely what that took,
since it tripped up the first attempt: a valid token is not the same as
approved access. `huggingface_hub.login(token=...)` succeeds and
`whoami()` returns the account regardless of dataset access; an actual
`hf_hub_download` against a gated repo still 403s with `GatedRepoError`
("not in the authorized list") until the account has separately clicked
"request access" on that specific dataset's page on huggingface.co and
been approved. Confirmed both ways: failed before that step, succeeded
after.

**Section 2A entity-density gate, run for real**
(`scripts/entity_density_gate.py`, text-only, no audio downloaded for the
gate itself):

| dataset | transcripts | total mentions | top entities | decision |
|---|---|---|---|---|
| Svarah | 6,656 | 212 | PAN card 69, ESIC 35, Provident Fund 31, EPFO 23 | **PROCEED** (>=100) |
| LAHAJA | 6,152 | 40 | Aadhaar 23, CoWIN 17 | **PROCEED with a confidence interval** (30-100) |

**A real memory-pressure bug, found and fixed before the real EER run**:
the first attempt at loading Svarah/LAHAJA for the EER eval was killed by
the harness for system memory pressure. Cause: the filtered loader used
`pyarrow.parquet.read_table()`, which decodes *every* row's embedded audio
bytes into one in-memory table before any entity/clean filtering happens
-- for a ~6,000+ row shard, almost all of that decoded audio was for rows
about to be thrown away. Fixed by switching to
`ParquetFile.iter_batches()`: a first text-only pass picks the row indices
actually wanted (entity-bearing, plus a bounded random clean sample), a
second pass streams small batches and only decodes audio for a batch that
contains at least one wanted row, via `RecordBatch.take()`.

**`small` Whisper now downloads in this sandbox.** Re-tried directly after
the memory fix, using the real default model rather than `tiny`: it
downloaded and loaded without the 0-byte-incomplete-file failure phase-1
spec section 11 documented. Whatever caused that restriction is no longer
in effect here. The real EER run below used `small`.

**F2 threshold sweep and result, Svarah** (179 entity-bearing rows + 150
clean sample; 30/70 dev/test split; dev: 54 entity-bearing/45 clean, test:
125 entity-bearing/105 clean; threshold grid 0.70-0.95; selection rule:
minimize `eer_after + corruption_rate` on dev, ties toward the higher
threshold):

| threshold (dev) | eer_after | corruption_rate | combined cost |
|---|---|---|---|
| 0.70 | 45.8% | 17.8% | 63.6% |
| 0.75 | 57.6% | 13.3% | 70.9% |
| **0.80** | **57.6%** | **2.2%** | **59.8%** ← chosen |
| 0.82 | 61.0% | 0.0% | 61.0% |
| 0.85 | 61.0% | 0.0% | 61.0% |
| 0.90 | 64.4% | 0.0% | 64.4% |
| 0.95 | 66.1% | 0.0% | 66.1% |

**Test split, single run at threshold=0.80 (never re-run to chase a
number)**: 143 entity mentions, **EER 59.4% → 49.0%** (95% CI on
`eer_after`: [40.9%, 57.1%]), corruption_rate **2.9%** on 105 clean
examples.

**Read honestly**: `dhvani-entity` recovers 10.4 points of EER on Svarah
(59.4% → 49.0%, a ~17.5% relative reduction) at a real but small cost
(2.9% of clean transcripts altered). `eer_before` itself is high --
`small` Whisper gets nearly 6 in 10 entity mentions wrong on Svarah's
accented English even before any ASR-quality argument about Indic
languages specifically, which is itself evidence for this project's
thesis. The dev sweep table above is not a footnote: a reader who prefers
recall over precision could reasonably pick threshold 0.70 instead (recovers
to 45.8%, roughly 22 points, at 17.8% corruption) -- the milestone number
depends on that choice, and both the choice and the alternative are shown,
not just the winner.

LAHAJA's result is in section 15 (its 40-mention gate result puts it in
the spec's own "report a confidence interval, and expect it to be wide"
bucket -- section 6.7's own warning, not an excuse added after the fact).
