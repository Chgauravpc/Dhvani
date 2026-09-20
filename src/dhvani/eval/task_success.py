"""F1 -- the ASR-ablation harness.

Runs the same VoiceAgentBench examples through an LLM three ways -- ground-
truth transcript, real ASR, and (once F2 exists) corrected ASR -- and scores
each condition by whether the LLM's tool call matches VoiceAgentBench's own
`expected_tool_call`. The *delta* between conditions is what F1 reports, not
the absolute success rate: VoiceAgentBench itself scores parameter filling
with an LLM judge validated against human labels, while `judge_tool_call`
below is exact-match-plus-normalization, which is stricter and reads lower
in absolute terms (phase-2 spec section 6.6). Don't compare our absolute
numbers to the paper's -- they don't measure the same thing.

**Lower-bound caveat that must travel with every quoted F1 number**:
VoiceAgentBench's audio is synthesized (TTS over text queries), so Whisper
handles it better than real accented speech would. The measured ASR penalty
here is a floor on the real-world penalty, not an estimate of it (phase-2
spec section 2).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass

from dhvani.clock import Clock
from dhvani.eval.audio_io import decode_audio_file_to_chunks
from dhvani.eval.datasets import ExpectedToolCall, VoiceAgentBenchExample
from dhvani.providers.base import LLMProvider, STTProvider
from dhvani.telemetry.span import TurnTrace
from dhvani.types import AudioChunk, Message, ToolCall, Transcript


class GroundTruthSTT:
    """Test/eval-only STTProvider: yields a single final Transcript equal to
    a pre-supplied ground-truth string, ignoring the audio entirely --
    the "if ASR were perfect" arm of the ablation. Not a real provider, so
    it does not open a telemetry span or enforce cancellation semantics;
    `run_ablation` never puts it on the live conversational path.
    """

    name = "ground-truth"

    def __init__(self, ground_truth_text: str) -> None:
        self._text = ground_truth_text

    async def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]:
        del audio, trace
        yield Transcript(text=self._text, is_final=True)


_COMMA_SPACING_RE = re.compile(r"\s*,\s*")


def _normalize(value: str) -> str:
    """Case-insensitive, whitespace-trimmed comparison per phase-2 spec
    section 6.6 -- extended to comma spacing after a real false negative:
    VoiceAgentBench's own `expected_tool_call` writes "Bandra,Mumbai" (no
    space) while a correct LLM answer wrote "Bandra, Mumbai" (with one).
    That's the same location, and light normalization should say so.
    """
    collapsed = " ".join(value.split()).strip().lower()
    return _COMMA_SPACING_RE.sub(", ", collapsed)


def judge_tool_call(actual: ToolCall | None, expected: ExpectedToolCall) -> bool:
    """Exact match on function name; every expected argument's value must
    match (case-insensitive, whitespace-trimmed) at least one of the
    acceptable variants VoiceAgentBench lists for it. `actual` carrying
    extra arguments beyond what's expected does not fail the match --
    VoiceAgentBench's own scoring is about correct parameter filling, not
    argument-set exhaustiveness.
    """
    if actual is None or actual.name != expected.name:
        return False
    for param, acceptable in expected.arguments.items():
        if param not in actual.arguments:
            return False
        actual_value = _normalize(str(actual.arguments[param]))
        if not any(actual_value == _normalize(v) for v in acceptable):
            return False
    return True


_TYPE_NAME_FIXES = {"dict": "object", "float": "number"}
"""Fixes real VoiceAgentBench `parameters` quirks: its schemas use Python-
style type names, not JSON Schema ones, for at least these two -- verified
directly by scanning every `type` value across 50 real English examples'
`functions` (only `dict`/`float` turned up as non-standard; `array`,
`boolean`, `integer`, `string` already match). A real Groq call rejects
both raw values with a 400 (metaschema validation: "value must be one of
'array', 'boolean', 'integer', 'null', 'number', 'object', 'string'")."""


def _json_schema_fix_types(node: object) -> object:
    """Recursively applies `_TYPE_NAME_FIXES` to every `type` field. Nested
    because a schema property can itself be object- or array-typed with
    its own nested `type` fields.
    """
    if isinstance(node, Mapping):
        fixed = {k: _json_schema_fix_types(v) for k, v in node.items()}
        type_value = fixed.get("type")
        if isinstance(type_value, str) and type_value in _TYPE_NAME_FIXES:
            fixed["type"] = _TYPE_NAME_FIXES[type_value]
        return fixed
    if isinstance(node, list):
        return [_json_schema_fix_types(v) for v in node]
    return node


def _to_groq_tools(functions: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    fixed = _json_schema_fix_types(list(functions))
    assert isinstance(fixed, list)
    return [{"type": "function", "function": fn} for fn in fixed]


async def _iter_chunks(chunks: Sequence[AudioChunk]) -> AsyncIterator[AudioChunk]:
    for chunk in chunks:
        yield chunk


async def _run_condition(
    example: VoiceAgentBenchExample,
    audio_chunks: Sequence[AudioChunk],
    stt: STTProvider,
    llm: LLMProvider,
    clock: Clock,
) -> bool:
    trace = TurnTrace(clock)
    final_transcript = ""
    async for transcript in stt.stream(_iter_chunks(audio_chunks), trace=trace):
        if transcript.is_final:
            final_transcript = transcript.text

    tools = _to_groq_tools(example.functions)
    messages = [Message(role="user", content=final_transcript)]
    tool_call: ToolCall | None = None
    async for delta in llm.stream(messages, trace=trace, tools=tools):
        if delta.tool_call is not None:
            tool_call = delta.tool_call

    return judge_tool_call(tool_call, example.expected_tool_call)


@dataclass(frozen=True, slots=True)
class LanguageResult:
    n: int
    success_rate_ground_truth: float
    success_rate_real_asr: float
    success_rate_corrected_asr: float | None


@dataclass(frozen=True, slots=True)
class AblationReport:
    per_language: Mapping[str, LanguageResult]


async def run_ablation(
    examples: Sequence[VoiceAgentBenchExample],
    make_real_stt: Callable[[], STTProvider],
    llm: LLMProvider,
    clock: Clock,
    make_corrected_stt: Callable[[], STTProvider] | None = None,
) -> AblationReport:
    """For each example, runs the LLM against (a) `GroundTruthSTT`, (b) a
    fresh real STT, and (c), if `make_corrected_stt` is given, a fresh
    corrected STT -- each condition gets its own STT instance because
    `WhisperSTT` and `CorrectedSTT` are not guaranteed reusable across
    concurrent/sequential streams with independent state. Aggregates task
    success (`judge_tool_call`) per language per condition.
    """
    by_language: dict[str, list[VoiceAgentBenchExample]] = {}
    for example in examples:
        by_language.setdefault(example.language, []).append(example)

    per_language: dict[str, LanguageResult] = {}
    for language, lang_examples in by_language.items():
        gt_successes = 0
        real_successes = 0
        corrected_successes = 0
        for example in lang_examples:
            audio_chunks = decode_audio_file_to_chunks(example.audio_path)

            gt = GroundTruthSTT(example.query)
            if await _run_condition(example, audio_chunks, gt, llm, clock):
                gt_successes += 1

            real_stt = make_real_stt()
            if await _run_condition(example, audio_chunks, real_stt, llm, clock):
                real_successes += 1

            if make_corrected_stt is not None:
                corrected_stt = make_corrected_stt()
                if await _run_condition(example, audio_chunks, corrected_stt, llm, clock):
                    corrected_successes += 1

        n = len(lang_examples)
        per_language[language] = LanguageResult(
            n=n,
            success_rate_ground_truth=gt_successes / n,
            success_rate_real_asr=real_successes / n,
            success_rate_corrected_asr=(corrected_successes / n) if make_corrected_stt else None,
        )

    return AblationReport(per_language=per_language)
