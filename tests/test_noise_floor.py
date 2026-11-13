"""3B-5 machinery: error classification, resumable log, analysis (no network)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import groq
import httpx
import pytest

from dhvani.clock import RealClock
from dhvani.eval.datasets import ExpectedToolCall, VoiceAgentBenchExample
from dhvani.eval.noise_floor import (
    FatalProviderError,
    Outcome,
    QuotaExhausted,
    RunLog,
    RunRecord,
    analyze,
    call_llm_with_retries,
)
from dhvani.eval.stats import paired_bootstrap_ci
from dhvani.telemetry.span import TurnTrace
from dhvani.types import LLMDelta, Message, ToolCall


def _status_error(
    cls: type[groq.APIStatusError], status: int, retry_after: str | None = None
) -> groq.APIStatusError:
    headers = {"retry-after": retry_after} if retry_after else {}
    request = httpx.Request("POST", "http://groq.test")
    response = httpx.Response(status, headers=headers, request=request)
    return cls("boom", response=response, body=None)


class ScriptedLLM:
    """Yields scripted outcomes: a ToolCall, None (no call), or an exception."""

    name = "scripted"

    def __init__(self, script: Sequence[ToolCall | Exception | None]) -> None:
        self._script = list(script)
        self.calls = 0

    async def stream(
        self, messages: Sequence[Message], *, trace: TurnTrace, tools: Sequence[object] = ()
    ) -> AsyncIterator[LLMDelta]:
        del messages, trace, tools
        item = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        if item is not None:
            yield LLMDelta(tool_call=item)
        yield LLMDelta(is_final=True)


EXAMPLE = VoiceAgentBenchExample(
    id="single_tool_1",
    language="english",
    query="book a table",
    audio_path=Path("unused.wav"),
    functions=[],
    expected_tool_call=ExpectedToolCall(name="book", arguments={"city": ["pune"]}),
)
GOOD = ToolCall(id="1", name="book", arguments={"city": "Pune"})
WRONG = ToolCall(id="1", name="other", arguments={})


async def _no_sleep(_: float) -> None:
    return None


@pytest.mark.asyncio
async def test_success_and_wrong_call_are_scored() -> None:
    clock = RealClock()
    ok = await call_llm_with_retries(ScriptedLLM([GOOD]), EXAMPLE, "x", clock, sleep=_no_sleep)
    bad = await call_llm_with_retries(ScriptedLLM([WRONG]), EXAMPLE, "x", clock, sleep=_no_sleep)
    none = await call_llm_with_retries(ScriptedLLM([None]), EXAMPLE, "x", clock, sleep=_no_sleep)
    assert (ok.outcome, bad.outcome, none.outcome) == ("pass", "fail", "fail")


@pytest.mark.asyncio
async def test_400_is_a_task_failure() -> None:
    llm = ScriptedLLM([_status_error(groq.BadRequestError, 400)])
    attempt = await call_llm_with_retries(llm, EXAMPLE, "x", RealClock(), sleep=_no_sleep)
    assert (attempt.outcome, attempt.error_class, llm.calls) == ("fail", "http_400", 1)


@pytest.mark.asyncio
async def test_429_is_retried_not_scored() -> None:
    llm = ScriptedLLM([_status_error(groq.RateLimitError, 429, "2"), GOOD])
    attempt = await call_llm_with_retries(llm, EXAMPLE, "x", RealClock(), sleep=_no_sleep)
    assert (attempt.outcome, llm.calls) == ("pass", 2)


@pytest.mark.asyncio
async def test_persistent_5xx_is_incomplete_never_failure() -> None:
    llm = ScriptedLLM([_status_error(groq.InternalServerError, 503)])
    attempt = await call_llm_with_retries(
        llm, EXAMPLE, "x", RealClock(), sleep=_no_sleep, max_tries=3
    )
    assert (attempt.outcome, attempt.error_class, llm.calls) == ("incomplete", "http_503", 3)


@pytest.mark.asyncio
async def test_daily_quota_429_stops_the_run() -> None:
    llm = ScriptedLLM([_status_error(groq.RateLimitError, 429, "3600")])
    with pytest.raises(QuotaExhausted):
        await call_llm_with_retries(llm, EXAMPLE, "x", RealClock(), sleep=_no_sleep)


@pytest.mark.asyncio
async def test_bad_key_is_fatal_not_a_failure() -> None:
    llm = ScriptedLLM([_status_error(groq.AuthenticationError, 401)])
    with pytest.raises(FatalProviderError):
        await call_llm_with_retries(llm, EXAMPLE, "x", RealClock(), sleep=_no_sleep)


def _rec(lang: str, ex: int, cond: str, run: int, ok: bool | None) -> RunRecord:
    outcome: Outcome = "incomplete" if ok is None else ("pass" if ok else "fail")
    return RunRecord(f"single_tool_{ex}", lang, ex, cond, run, outcome, None, "", "m", "t")


def test_run_log_resumes_and_keeps_languages_apart(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    log = RunLog(path)
    log.append(_rec("english", 1, "gt", 1, True))
    log.append(_rec("hindi", 1, "gt", 1, None))  # same id, other language, incomplete
    log.close()
    again = RunLog(path)
    assert again.done("english", "single_tool_1", "gt", 1)
    assert not again.done("hindi", "single_tool_1", "gt", 1)  # incomplete is retried
    assert not again.done("english", "single_tool_1", "gt", 2)


def _records(gt_runs: list[list[bool]], real_runs: list[list[bool]]) -> list[RunRecord]:
    out = []
    for j, (g, r) in enumerate(zip(gt_runs, real_runs, strict=True), start=1):
        for i, (gv, rv) in enumerate(zip(g, r, strict=True)):
            out.append(_rec("english", i, "gt", j, gv))
            out.append(_rec("english", i, "whisper", j, rv))
    return out


def test_analysis_finds_a_real_loss_and_a_noise_floor() -> None:
    n = 100
    gt = [[True] * n, [True] * n, [True] * n]
    # ASR fails the first 40 examples on every run: a genuine, stable 40 pp loss.
    real = [[i >= 40 for i in range(n)] for _ in range(3)]
    result = analyze(_records(gt, real), real_conditions=("whisper",), n_resamples=500)
    arm = result["languages"]["english"]["arms"]["whisper"]
    assert result["languages"]["english"]["noise_floor_pp"] == 0.0
    assert arm["mean_loss_pp"] == pytest.approx(40.0)
    assert arm["majority_gt_pass_real_fail"] == 40
    assert arm["majority_gt_fail_real_pass"] == 0
    assert arm["verdict"] == "ASR costs task success"
    assert arm["first_n_subset"]["n"] == 40


def test_analysis_calls_pure_sampling_noise_noise() -> None:
    n = 100
    # GT and ASR are the same process: both flip a few examples between runs.
    gt = [[(i + j * 7) % 10 != 0 for i in range(n)] for j in range(3)]
    real = [[(i + j * 7 + 3) % 10 != 0 for i in range(n)] for j in range(3)]
    result = analyze(_records(gt, real), real_conditions=("whisper",), n_resamples=500)
    arm = result["languages"]["english"]["arms"]["whisper"]
    assert arm["verdict"] == "not distinguishable from LLM sampling noise"


def test_analysis_excludes_incomplete_examples_from_loss() -> None:
    gt = [[True] * 4] * 3
    real = [[True, True, True, False]] * 3
    records = [
        r
        for r in _records(gt, real)
        if not (r.example_id == "single_tool_3" and r.run == 2 and r.condition == "whisper")
    ]
    records.append(_rec("english", 3, "whisper", 2, None))
    result = analyze(records, real_conditions=("whisper",), n_resamples=100)
    assert result["languages"]["english"]["arms"]["whisper"]["n"] == 3
    assert result["incomplete_cells"] == {"english/whisper": 1}


def test_paired_bootstrap_is_deterministic_and_brackets_the_mean() -> None:
    values = [0.0, 1.0] * 50
    lo, hi = paired_bootstrap_ci(values, n_resamples=2000, seed=0)
    assert (lo, hi) == paired_bootstrap_ci(values, n_resamples=2000, seed=0)
    assert lo < 0.5 < hi
    assert paired_bootstrap_ci([], n_resamples=10) == (0.0, 0.0)
