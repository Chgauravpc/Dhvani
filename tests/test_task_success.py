from __future__ import annotations

import wave
from pathlib import Path

import pytest

from dhvani.clock import FakeClock
from dhvani.eval.datasets import ExpectedToolCall, VoiceAgentBenchExample
from dhvani.eval.task_success import (
    GroundTruthSTT,
    _iter_chunks,
    _json_schema_fix_types,
    judge_tool_call,
    run_ablation,
)
from dhvani.providers.mock import MockLLM, MockSTT, MockTiming
from dhvani.telemetry.span import TurnTrace
from dhvani.types import ToolCall


def _write_silence_wav(path: Path, seconds: float = 0.1, sample_rate: int = 16000) -> None:
    n_samples = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * n_samples)


# -- judge_tool_call ---------------------------------------------------------


def test_judge_tool_call_exact_match() -> None:
    expected = ExpectedToolCall(name="book", arguments={"time": ("7pm",)})
    actual = ToolCall(id="1", name="book", arguments={"time": "7pm"})
    assert judge_tool_call(actual, expected) is True


def test_judge_tool_call_normalizes_case_whitespace_and_comma_spacing() -> None:
    """Regression: a real ablation run against VoiceAgentBench found
    "Bandra,Mumbai" (expected) vs "Bandra, Mumbai" (a correct real answer)
    counted as a false negative before comma spacing was normalized."""
    expected = ExpectedToolCall(name="find", arguments={"location": ("Bandra,Mumbai",)})
    actual = ToolCall(id="1", name="find", arguments={"location": "  BANDRA,  Mumbai "})
    assert judge_tool_call(actual, expected) is True


def test_judge_tool_call_accepts_any_listed_variant() -> None:
    expected = ExpectedToolCall(name="find", arguments={"cuisine": ("South Indian", "Tamil")})
    actual = ToolCall(id="1", name="find", arguments={"cuisine": "tamil"})
    assert judge_tool_call(actual, expected) is True


def test_judge_tool_call_rejects_wrong_function_name() -> None:
    expected = ExpectedToolCall(name="book", arguments={})
    actual = ToolCall(id="1", name="cancel", arguments={})
    assert judge_tool_call(actual, expected) is False


def test_judge_tool_call_rejects_missing_argument() -> None:
    expected = ExpectedToolCall(name="book", arguments={"time": ("7pm",)})
    actual = ToolCall(id="1", name="book", arguments={})
    assert judge_tool_call(actual, expected) is False


def test_judge_tool_call_rejects_wrong_value() -> None:
    expected = ExpectedToolCall(name="book", arguments={"time": ("7pm",)})
    actual = ToolCall(id="1", name="book", arguments={"time": "8pm"})
    assert judge_tool_call(actual, expected) is False


def test_judge_tool_call_ignores_extra_actual_arguments() -> None:
    expected = ExpectedToolCall(name="book", arguments={"time": ("7pm",)})
    actual = ToolCall(id="1", name="book", arguments={"time": "7pm", "party_size": 4})
    assert judge_tool_call(actual, expected) is True


def test_judge_tool_call_none_is_never_a_match() -> None:
    expected = ExpectedToolCall(name="book", arguments={})
    assert judge_tool_call(None, expected) is False


# -- _json_schema_fix_types ---------------------------------------------------


def test_json_schema_fix_types_maps_dict_and_float_to_json_schema_names() -> None:
    """Regression: VoiceAgentBench's own `parameters` specs use Python-style
    type names ("dict", "float") that a real Groq call rejects (400:
    invalid JSON schema) -- "object"/"number" are what JSON Schema wants,
    and were the only two non-standard values found scanning 50 real
    examples' function specs."""
    functions = [
        {
            "name": "find",
            "parameters": {
                "type": "dict",
                "properties": {
                    "filters": {"type": "dict", "properties": {"x": {"type": "string"}}},
                    "rating": {"type": "float"},
                },
            },
        }
    ]
    fixed = _json_schema_fix_types(functions)
    assert isinstance(fixed, list)
    assert fixed[0]["parameters"]["type"] == "object"
    assert fixed[0]["parameters"]["properties"]["filters"]["type"] == "object"
    assert fixed[0]["parameters"]["properties"]["rating"]["type"] == "number"


# -- GroundTruthSTT ------------------------------------------------------------


@pytest.mark.asyncio
async def test_ground_truth_stt_ignores_audio_and_yields_given_text() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock)
    stt = GroundTruthSTT("the real transcript")

    transcripts = [t async for t in stt.stream(_iter_chunks([]), trace=trace)]

    assert len(transcripts) == 1
    assert transcripts[0].text == "the real transcript"
    assert transcripts[0].is_final


# -- run_ablation --------------------------------------------------------------


def _example(
    example_id: str, language: str, audio_path: Path, tool_name: str, arg_value: str
) -> VoiceAgentBenchExample:
    return VoiceAgentBenchExample(
        id=example_id,
        language=language,
        query="irrelevant with a mock LLM",
        audio_path=audio_path,
        functions=[
            {
                "name": tool_name,
                "parameters": {"type": "dict", "properties": {"time": {"type": "string"}}},
            }
        ],
        expected_tool_call=ExpectedToolCall(name=tool_name, arguments={"time": (arg_value,)}),
    )


@pytest.mark.asyncio
async def test_run_ablation_aggregates_per_language(tmp_path: Path) -> None:
    """With a MockLLM (fixed output regardless of input transcript), an
    example's ground-truth and real-ASR conditions necessarily agree --
    this test covers run_ablation's per-language grouping and success-rate
    math, not whether transcript quality changes the outcome (that's what
    the real integration run against Groq/Whisper demonstrates)."""
    wav_path = tmp_path / "silence.wav"
    _write_silence_wav(wav_path)
    clock = FakeClock()
    timing = MockTiming(ttfb_ms=1.0, per_unit_ms=1.0)

    # The single shared MockLLM always emits this one tool call.
    llm = MockLLM(
        response="",
        timing=timing,
        clock=clock,
        tool_calls=(ToolCall(id="1", name="book", arguments={"time": "7pm"}),),
    )

    examples = [
        _example("h1", "hindi", wav_path, "book", "7pm"),  # matches -> success
        _example("h2", "hindi", wav_path, "book", "8pm"),  # mismatched value -> failure
        _example("e1", "english", wav_path, "book", "7pm"),  # matches -> success
    ]

    report = await run_ablation(
        examples,
        make_real_stt=lambda: MockSTT(partials=[], final="whatever", timing=timing, clock=clock),
        llm=llm,
        clock=clock,
    )

    assert report.per_language["hindi"].n == 2
    assert report.per_language["hindi"].success_rate_ground_truth == pytest.approx(0.5)
    assert report.per_language["hindi"].success_rate_real_asr == pytest.approx(0.5)
    assert report.per_language["hindi"].success_rate_corrected_asr is None
    assert report.per_language["english"].n == 1
    assert report.per_language["english"].success_rate_ground_truth == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_run_ablation_includes_corrected_condition_when_given(tmp_path: Path) -> None:
    wav_path = tmp_path / "silence.wav"
    _write_silence_wav(wav_path)
    clock = FakeClock()
    timing = MockTiming(ttfb_ms=1.0, per_unit_ms=1.0)
    llm = MockLLM(
        response="",
        timing=timing,
        clock=clock,
        tool_calls=(ToolCall(id="1", name="book", arguments={"time": "7pm"}),),
    )
    examples = [_example("h1", "hindi", wav_path, "book", "7pm")]

    report = await run_ablation(
        examples,
        make_real_stt=lambda: MockSTT(partials=[], final="x", timing=timing, clock=clock),
        llm=llm,
        clock=clock,
        make_corrected_stt=lambda: MockSTT(partials=[], final="y", timing=timing, clock=clock),
    )

    assert report.per_language["hindi"].success_rate_corrected_asr == pytest.approx(1.0)
