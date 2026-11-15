# Phase 2 — F1 + F2

**Status:** Complete. F1 and F2 both implemented, tested, and run for real
against real datasets -- sections 12 (F1), 14-15 (F2 Svarah/LAHAJA), 16
(the combined milestone, including the task-success tie-together run,
which came back as an honest negative result -- see section 16 for why
that's the correct reading, not a discouraging one).
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

**Share of achievable success lost to ASR (phase-2b reframe, §17).** The
absolute-points table above reads as if Hindi loses *less* to ASR than
English, which runs backwards from this project's own thesis. Reported as
a share of each language's own ground-truth ceiling instead, the
comparison becomes apples-to-apples and the artifact dissolves:

| language | achievable (ground truth) | lost to ASR | share of achievable lost |
|---|---|---|---|
| english | 42.5% | 27.5% | **65%** |
| hindi | 17.5% | 10.0% | **57%** |

Same underlying numbers, no new run. English and Hindi now read as
comparably damaged by ASR (65% vs. 57% of what was achievable), which is
the reading that actually matches the thesis -- the absolute-points table
undersold Hindi's loss because Hindi had less headroom to lose from in the
first place, not because ASR hurt it less. Both framings are kept: the
absolute points are still the number to check the arithmetic against; the
share-of-achievable number is the one to quote.

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
- Hindi's loss-to-ASR (10.0%) reading *smaller* than English's (27.5%) in
  absolute points is counterintuitive given the project's own thesis
  (Indic ASR is the weaker link) and is exactly the artifact the
  share-of-achievable table above exists to fix: it is an artifact of
  Hindi's ground-truth success rate already being low (17.5%) -- there is
  less headroom left for ASR to lose -- not evidence that ASR hurts Hindi
  less. Re-running with the real `small` Whisper model, on a machine that
  can download it, would still be worth doing before reading anything
  further into this specific comparison.
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

> **Audit note (Sep 23 2026) — invalidated, kept for the record.** The entity counts and EER
> numbers in this section were produced by substring mention matching and a scorer that only
> accepts the Latin canonical form. See `phase-3b.md` §2–3 and §5; superseding numbers will be
> added by item 3B-4, not written over these.

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

---

## 15. F2 real numbers -- LAHAJA

> **Audit note (Sep 23 2026) — invalidated, kept for the record.** The entity counts and EER
> numbers in this section were produced by substring mention matching and a scorer that only
> accepts the Latin canonical form. See `phase-3b.md` §2–3 and §5; superseding numbers will be
> added by item 3B-4, not written over these.

40 entity-bearing rows (all of them; the gate found no more) + 50 clean
sample; 30/70 split gave dev 12 entity-bearing/16 clean, test 28 entity-
bearing/36 clean. First attempt at this run was killed twice for system
memory pressure (not a code bug the second time -- see section 14's
streaming fix, which this run also used); it succeeded on retry with
`--n-clean-sample 50` instead of the default 150, which this thin a
dataset didn't need anyway.

| threshold (dev) | eer_after | corruption_rate | combined cost |
|---|---|---|---|
| 0.70 | 0.0% | 18.8% | 18.8% |
| 0.75 | 0.0% | 12.5% | 12.5% |
| 0.80 | 0.0% | 6.2% | 6.2% |
| **0.82** | **0.0%** | **0.0%** | **0.0%** ← chosen |
| 0.85 | 8.3% | 0.0% | 8.3% |
| 0.90 | 8.3% | 0.0% | 8.3% |
| 0.95 | 50.0% | 0.0% | 50.0% |

`eer_before` on dev is **100.0%** at every threshold -- correctly
threshold-invariant, since it measures the raw, uncorrected transcript.
`small` Whisper got every single one of the 12 dev entity mentions wrong.
Threshold 0.82 recovers all 12 with zero clean-example corruption on dev,
a suspiciously clean result for n=12 -- flagged rather than trusted at
face value, which the test split promptly justified.

**Test split, single run at threshold=0.82**: 28 entity mentions,
`eer_before` again **100.0%** (small Whisper got every one of these 28
wrong too, independently confirming dev's finding wasn't a fluke of which
12 got sampled), `eer_after` **46.4%** (95% CI [29.5%, 64.2%] -- this
interval is wide, as the gate's own decision rule warned it would be for
a 30-100 mention corpus), corruption_rate **19.4%** on 36 clean examples.

**Read honestly, especially the discrepancy**: dev showed 0% corruption
at threshold 0.82; test showed 19.4% at the same threshold. That is not
noise to wave away -- it means the dev-chosen threshold does not
generalize cleanly to test on this corpus, most likely because n=16 (dev
clean) and n=12 (dev mentions) are simply too small for the sweep to have
found a threshold that holds up, exactly the risk the gate's own 30-100
bucket warning was about. The honest summary for LAHAJA is: **`small`
Whisper fails completely (100% EER) on every Hindi entity mention
sampled, in both splits independently** -- the clearest, most reproducible
finding in this phase, and squarely the failure mode F2 exists to
address -- and **`dhvani-entity` recovers roughly half of that (to 46.4%
EER) on test, at a real and non-trivial corruption cost (19.4%) that did
not show up during tuning**. Reporting only the recovery number without
the corruption discrepancy would be exactly the kind of favorable-reading
this project's own evaluation ethos (paired corruption metrics, honest
lower bounds) exists to prevent.

## 16. Milestone, both datasets

> **Audit note (Sep 23 2026) — invalidated, kept for the record.** The entity counts and EER
> numbers in this section were produced by substring mention matching and a scorer that only
> accepts the Latin canonical form. See `phase-3b.md` §2–3 and §5; superseding numbers will be
> added by item 3B-4, not written over these.

Per `ROADMAP.md`'s framing ("the agent loses X% of task success to
transcription alone, and `dhvani-entity` recovers Y% of it"): X is F1's
number (section 12: English 27.5%, Hindi 10.0% task-success loss to ASR,
both lower bounds on VoiceAgentBench's synthesized audio) -- or, in the
share-of-achievable framing section 12 also carries (phase-2b, §17):
**English loses 65% of achievable task success to ASR, Hindi loses 57%**.
The share-of-achievable framing is the one to quote: it is the one that
makes English and Hindi comparable and lands the headline where the
thesis actually is -- ASR destroys roughly 60% of achievable task
success -- rather than making Hindi's loss look smaller than English's
purely because Hindi's ground-truth ceiling left less to lose from. Y, the
entity-level recovery, now has two real numbers instead of zero:

| dataset | eer_before | eer_after | absolute recovery | corruption_rate |
|---|---|---|---|---|
| Svarah (test, n=143) | 59.4% | 49.0% | 10.4 points | 2.9% |
| LAHAJA (test, n=28) | 100.0% | 46.4% | 53.6 points | 19.4% |

**These two rows are `small` Whisper.** Section 18 (Phase 2B carried into
Phase 3) re-runs both against Sarvam's Saaras model, the Indic ASR
baseline section 17 called the "single most important" gap left in this
table -- Svarah improves to 46.9%/39.9%, LAHAJA stays at 100.0%/35.7%.

Both are real `small`-model, real-dataset, dev-tuned/test-reported
numbers -- not projections. Neither should be read as "the" F2 number:
Svarah is Indic-accented English at a corpus scale (143 test mentions)
that supports a real point estimate; LAHAJA is Hindi at a scale (28 test
mentions) the gate itself flagged as needing a confidence interval, and
that interval is wide ([29.5%, 64.2%]) with a real dev/test corruption
discrepancy alongside it.

**The task-success-level tie-together, now run**
(`uv run python scripts/run_f1_ablation.py --with-corrected-stt`,
`n_per_language=40`, `small` Whisper, default threshold 0.82 -- no
VoiceAgentBench-specific dev/test tuning exists, unlike Svarah/LAHAJA):

| language | n | ground truth | real ASR | loss | corrected ASR | recovered |
|---|---|---|---|---|---|---|
| english | 40 | 42.5% | 30.0% | 12.5% | 32.5% | +2.5 pts |
| hindi | 40 | 15.0% | 25.0% | -10.0% | 20.0% | -5.0 pts |

**Read this one especially carefully -- it is mostly noise, and the run
itself proves why.** The script printed, before any condition ran: only
**2 of the 80** example queries mention a lexicon entity at all --
VoiceAgentBench's `single_tool` category is restaurant/recipe/local-
search queries, not `DEFAULT_LEXICON`'s civic/government/finance domain.
For the other 78/80 examples, `CorrectedSTT` is a byte-for-byte no-op: it
transcribes with the same `WhisperSTT` and applies zero corrections, so
the real-ASR and corrected-ASR conditions feed the LLM *identical* text.
Any difference in their success rate on those 78 examples is not
`dhvani-entity` doing anything -- it is two independent, non-deterministic
Groq calls on the same input landing on different tool-call outputs
(the same real, sampling-driven variance section 11 already found once,
in `groq.APIError`'s `walmart.check_price` schema failures reproducing
identically across all three conditions for one example). A same-input
comparison with only 2/80 examples able to differ *should* show
close-to-zero net change with real sampling noise scattered around it,
and that is exactly what these numbers look like (+2.5 points, -5.0
points) -- not a demonstrated recovery, and not a demonstrated harm
either. **The honest conclusion is a negative-but-informative result**:
these two corpora don't overlap enough for `dhvani-entity` to matter at
the task-success level, and the real recovery signal lives entirely in
the EER numbers above, measured on corpora (Svarah, LAHAJA) that actually
contain the entities the corrector targets. Measuring this properly would
need a VoiceAgentBench subset deliberately filtered or constructed to
contain lexicon entities in the query text -- out of scope for what this
phase built.

---

## 17. Phase 2B — Indic ASR baseline (Sep 22-26, plan -- see section 18 for the real run)

### Why this is required before the F2 numbers are quotable

Section 14 measured `eer_before` at 59.4% on Svarah; section 15 measured
it at **100%** on LAHAJA. Those are not measurements of "Indic ASR" --
they are measurements of `small` Whisper, an English-centric general
model, on Indic entity mentions.

That leaves the project's headline result open to one question it cannot
currently answer: **does `dhvani-entity` still help when the ASR is
actually good?** If a purpose-built Indic ASR gets those mentions right
unaided, the corrector is recovering a problem the phase-1 provider choice
created, not a problem in Indic voice agents. Every recovery number in
sections 14-16 is contestable until this is run.

### What to build

- `providers/sarvam_stt.py` -- `SarvamSTT`, satisfying the **unchanged**
  Phase 0 `STTProvider` protocol. Saaras is hosted, so no GPU is needed
  and the no-local-model constraint that forced faster-whisper in phase 1
  does not apply. Key via `SARVAM_API_KEY`, same env-var-only rule as
  `GROQ_API_KEY`.
- No change to `EntityCorrector`, `CorrectedSTT`, or either eval script.
  `SarvamSTT` is a drop-in for the `stt` argument they already take. If
  anything needs changing to accommodate it, the protocol was wrong, and
  that is a design discussion rather than a patch.

### What to re-run

1. Svarah EER, same test split, same threshold, `SarvamSTT` as inner ASR.
2. LAHAJA EER, same.
3. The F1 ablation, `--languages english,hindi --n-per-language 40`.

Report each beside the existing Whisper figure, never replacing it. The
comparison is the result.

### Reading the outcome

All three possibilities are worth having, which is what makes this worth
running rather than a risk to the narrative:

- **Saaras already gets the entities right.** F2 is provider-dependent.
  Say so plainly -- "choose an Indic ASR" is still the F1 thesis, and
  demonstrating that a 10-point corrector gain evaporates against the
  right model is a genuine finding about where effort belongs.
- **Saaras still misses them.** F2 becomes unarguable: the failure
  survives the strongest available Indic ASR.
- **Saaras misses a different set.** The most interesting outcome -- it
  would say entity errors are systematic to the task rather than to any
  one model, and the error sets themselves become the finding.

### The F1 reframe (free, no new code)

Section 12 reports task-success loss in absolute points and then has to
apologise for Hindi's 10.0% reading smaller than English's 27.5%. The
cause is stated correctly there: Hindi's ground-truth ceiling is only
17.5%, so there is less to lose.

Report **share of achievable success lost to ASR** instead:

| language | achievable | lost to ASR | share of achievable lost |
|---|---|---|---|
| english | 42.5% | 27.5% | **65%** |
| hindi | 17.5% | 10.0% | **57%** |

Same data, already collected. The two languages become comparable, the
counterintuitive artifact dissolves, and the headline lands where the
thesis actually is: ASR destroys roughly 60% of achievable task success.
Keep the absolute figures alongside -- the point is a better denominator,
not a better-looking number.

### Definition of done

- [x] `SarvamSTT` satisfies `STTProvider` unchanged; `mypy --strict` clean
- [x] Unit tests against a mocked Sarvam response; integration test marked
      `integration` and skipped without `SARVAM_API_KEY`
- [x] Svarah and LAHAJA EER re-run and tabulated beside the Whisper numbers
      -- see section 18
- [x] F1 ablation re-run and tabulated beside the Whisper numbers -- see
      section 18
- [x] Section 12 and section 16 updated with share-of-achievable framing
- [x] Whichever of the three outcomes occurred, written down as the finding
      rather than worked around -- see section 18

---

## 18. Phase 2B carried into Phase 3 -- the real Sarvam run (Sep 22)

> **Audit note (Sep 23 2026) — invalidated, kept for the record.** The entity counts and EER
> numbers in this section were produced by substring mention matching and a scorer that only
> accepts the Latin canonical form. See `phase-3b.md` §2–3 and §5; superseding numbers will be
> added by item 3B-4, not written over these.

`SARVAM_API_KEY` was unavailable when phase-2b.md was built (its section
11 records that honestly); it became available for phase-3, whose section
2.1 named this "the single highest-value unrun experiment in the project"
and forbade cutting it. Same splits, same thresholds, same scripts as
section 14-16's Whisper runs -- only the inner ASR changed, per this
section's own ground rule.

### Svarah EER, real Sarvam (`saaras:v3`, test split, dev-tuned threshold)

`uv run python scripts/run_f2_entity_eval.py --dataset svarah --stt sarvam`

| dataset | stt | eer_before | eer_after | absolute recovery | corruption_rate | n_mentions |
|---|---|---|---|---|---|---|
| Svarah (test) | whisper (small) | 59.4% | 49.0% | 10.4 points | 2.9% | 143 |
| Svarah (test) | **sarvam** | **46.9%** | **39.9%** | **7.0 points** | **2.9%** | 143 |

Dev-chosen threshold was 0.80 (vs. Whisper's 0.82) -- the sweep is
independent per STT, as it should be; nothing about the threshold-choice
procedure changed.

### LAHAJA EER, real Sarvam

`uv run python scripts/run_f2_entity_eval.py --dataset lahaja --stt sarvam`

| dataset | stt | eer_before | eer_after | absolute recovery | corruption_rate | n_mentions |
|---|---|---|---|---|---|---|
| LAHAJA (test) | whisper (small) | 100.0% | 46.4% | 53.6 points | 19.4% | 28 |
| LAHAJA (test) | **sarvam** | **100.0%** | **35.7%** | **64.3 points** | **0.0%** | 28 |

Dev-chosen threshold was 0.95 (vs. Whisper's implicit default) -- the dev
sweep pushed all the way to the grid's most conservative value, since
lower thresholds bought no extra recovery on only 12 dev mentions but did
cost real corruption (39.1% at 0.70, falling to 0.0% by 0.95). Still n=28
on test; the 30-100-mention "report a confidence interval" bucket from the
section 2A gate still applies (95% CI on `eer_after`: [20.7%, 54.2%]).

### F1 ablation, real Sarvam

`uv run python scripts/run_f1_ablation.py --languages english,hindi --n-per-language 40 --stt sarvam`

| language | n | stt | ground truth | real ASR | loss to ASR |
|---|---|---|---|---|---|
| english | 40 | whisper (tiny) | 42.5% | 15.0% | 27.5% |
| english | 40 | **sarvam** | 40.0% | 32.5% | **7.5%** |
| hindi | 40 | whisper (tiny) | 17.5% | 7.5% | 10.0% |
| hindi | 40 | **sarvam** | 15.0% | 22.5% | **-7.5%** |

One example (`single_tool_19`) failed with a Groq `APIError` (a tool-call
argument schema mismatch on `walmart.check_price`, the same kind of
sampling-driven Groq flakiness section 11 already found once) and was
counted as a task failure per this harness's own design, not excluded.
Ground-truth numbers differ slightly from section 12's Whisper run
(40.0%/15.0% here vs. 42.5%/17.5% there) because Groq's tool-call sampling
is non-deterministic between runs, not because anything about the
ground-truth condition changed.

Hindi's **negative** loss (-7.5 points -- the Sarvam-transcribed condition
scored *better* than ground truth) should not be read as "ASR helps."
Section 16 already established why F1-on-VoiceAgentBench is close to pure
noise for this lexicon: only a handful of the 80 example queries mention
a lexicon entity at all, so almost every difference between conditions is
two independent, non-deterministic Groq tool-call samples landing
differently on the same input, not a real transcription effect. An n=40
per-language sample is nowhere near large enough to distinguish that noise
from a genuine effect in either direction.

### Reading the outcome (section 17's preregistration)

Svarah lands closest to the first preregistered outcome, but only
partially: Saaras is meaningfully better than Whisper unaided (46.9% vs.
59.4% `eer_before`) -- real evidence that ASR choice matters, exactly as
the F1 thesis claims -- but it does **not** get the entities right on its
own (46.9% is still a near-coin-flip miss rate), and `dhvani-entity`
still recovers a further 7.0 points on top of it. So the honest reading is
not "the corrector evaporates against a better model," it's **"a better
model raises the floor `dhvani-entity` corrects from, and does not
replace correcting it."**

LAHAJA lands on the second outcome without qualification: **100.0%
`eer_before` on both Whisper and Sarvam** -- a purpose-built Indic ASR
misses LAHAJA's entity mentions exactly as completely as an
English-centric general model does. That is the strongest single number
in this project for "the failure survives the strongest available Indic
ASR": LAHAJA's accented, code-switched entity mentions defeat two
architecturally different systems identically. `dhvani-entity` recovers
more of it against Sarvam (64.3 points) than against Whisper (53.6
points), at a lower corruption rate (0.0% vs. 19.4%) -- consistent with
Sarvam's transcription being closer to correct everywhere else, giving
the phonetic matcher cleaner context to work from even where it still
misses the entity itself.

**Combined reading**: Sarvam is a genuine improvement over `small`
Whisper on Svarah's accented-English entities, and identical to it (both
total failures) on LAHAJA's Hindi entities. Neither dataset supports "pick
a better ASR and skip the corrector" -- the corrector recovers real,
non-trivial points against Sarvam on both. The project's F2 thesis holds
against the strongest available alternative, which is exactly what this
run was for.
