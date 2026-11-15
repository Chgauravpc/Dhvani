"""F1 noise floor (phase-3b 3B-5, protocol: `docs/specs/phase-3b.md` section 10).

Re-runs the F1 task-success measurement with k independent LLM runs per
condition per example, so the run-to-run variance of the LLM itself -- the
noise floor -- is measured instead of ignored (audit finding A4).

Three parts:

- `RunLog`: an append-only, resumable JSONL of every LLM outcome.
- `call_llm_with_retries`: one LLM tool-call attempt. **Infrastructure errors
  are never scored** (section 10.4): the Phase 2 harness counted every
  exception as a task failure, which would turn a Groq rate limit into fake
  ASR loss.
- `analyze`: A/A noise floor, paired bootstrap CI of the ASR loss, majority-
  vote McNemar, and the section 10.6 decision rule.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Literal, TextIO

import groq

from dhvani.clock import Clock
from dhvani.eval.datasets import VoiceAgentBenchExample
from dhvani.eval.stats import mcnemar_exact_p, paired_bootstrap_ci
from dhvani.eval.task_success import _to_groq_tools, judge_tool_call
from dhvani.providers.base import LLMProvider
from dhvani.telemetry.span import TurnTrace
from dhvani.types import Message, ToolCall

Outcome = Literal["pass", "fail", "incomplete"]
GT = "gt"
MAX_TRIES = 6
QUOTA_WAIT_LIMIT_S = 120.0
"""A 429 asking us to wait longer than this is the daily request quota, not a
per-minute limit: stop the invocation and resume on a later day."""


class QuotaExhausted(RuntimeError):
    """The provider asked for a wait too long to sit through (daily quota)."""


class FatalProviderError(RuntimeError):
    """A non-retryable error that must never be scored (bad key, 404, ...)."""


@dataclass(frozen=True, slots=True)
class RunRecord:
    example_id: str
    language: str
    index: int
    """Position of the example within its language's manifest."""
    condition: str
    run: int
    outcome: Outcome
    tool_call: Mapping[str, Any] | None
    error_class: str
    model: str
    ts: str

    def key(self) -> tuple[str, str, str, int]:
        # Ids repeat across languages (133 of them do), so the language is
        # part of the key.
        return (self.language, self.example_id, self.condition, self.run)


class RunLog:
    """Append-only JSONL of LLM outcomes; resumable.

    `done` is true only for a scored outcome (`pass` / `fail`); an
    `incomplete` cell is retried on the next invocation. The latest record
    for a key wins.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._latest: dict[tuple[str, str, str, int], RunRecord] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = _record_from_dict(json.loads(line))
                    self._latest[record.key()] = record
        self._handle: TextIO | None = None

    def done(self, language: str, example_id: str, condition: str, run: int) -> bool:
        record = self._latest.get((language, example_id, condition, run))
        return record is not None and record.outcome != "incomplete"

    def records(self) -> list[RunRecord]:
        return list(self._latest.values())

    def append(self, record: RunRecord) -> None:
        if self._handle is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a", encoding="utf-8")
        self._handle.write(json.dumps(_record_to_dict(record), ensure_ascii=False) + "\n")
        self._handle.flush()
        self._latest[record.key()] = record

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def _record_to_dict(r: RunRecord) -> dict[str, Any]:
    return {
        "example_id": r.example_id,
        "language": r.language,
        "index": r.index,
        "condition": r.condition,
        "run": r.run,
        "outcome": r.outcome,
        "tool_call": r.tool_call,
        "error_class": r.error_class,
        "model": r.model,
        "ts": r.ts,
    }


def _record_from_dict(d: Mapping[str, Any]) -> RunRecord:
    return RunRecord(
        example_id=str(d["example_id"]),
        language=str(d["language"]),
        index=int(d["index"]),
        condition=str(d["condition"]),
        run=int(d["run"]),
        outcome=d["outcome"],
        tool_call=d.get("tool_call"),
        error_class=str(d.get("error_class", "")),
        model=str(d.get("model", "")),
        ts=str(d.get("ts", "")),
    )


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _retry_after_seconds(exc: groq.APIStatusError) -> float | None:
    raw = exc.response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class LlmAttempt:
    outcome: Outcome
    tool_call: ToolCall | None
    error_class: str


async def call_llm_with_retries(
    llm: LLMProvider,
    example: VoiceAgentBenchExample,
    text: str,
    clock: Clock,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_tries: int = MAX_TRIES,
) -> LlmAttempt:
    """One scored LLM attempt on `text`.

    - success path: the judged tool call -> `pass` / `fail`.
    - HTTP 400 (Groq rejecting its own malformed tool call, the documented
      Phase 2 behaviour) -> `fail`.
    - a mid-stream "Tool call validation failed" APIError (Groq rejecting its own
      generated call) -> `fail`, the same documented Phase 2 behaviour.
    - 408 / 429 / 5xx / connection errors -> retried with backoff, then
      `incomplete` (never scored). A 429 whose Retry-After exceeds
      `QUOTA_WAIT_LIMIT_S` raises `QuotaExhausted`.
    - any other API status (401, 403, 404, 413, ...) -> `FatalProviderError`:
      scoring it would silently turn a config problem into ASR loss.
    """
    last_error = ""
    for attempt in range(max_tries):
        try:
            trace = TurnTrace(clock)
            tools = _to_groq_tools(example.functions)
            messages = [Message(role="user", content=text)]
            tool_call: ToolCall | None = None
            async for delta in llm.stream(messages, trace=trace, tools=tools):
                if delta.tool_call is not None:
                    tool_call = delta.tool_call
            ok = judge_tool_call(tool_call, example.expected_tool_call)
            return LlmAttempt("pass" if ok else "fail", tool_call, "")
        except groq.BadRequestError:
            return LlmAttempt("fail", None, "http_400")
        except groq.APIStatusError as exc:
            status = exc.status_code
            if status in (408, 429) or status >= 500:
                last_error = f"http_{status}"
                wait = _retry_after_seconds(exc)
                if status == 429 and wait is not None and wait > QUOTA_WAIT_LIMIT_S:
                    raise QuotaExhausted(
                        f"429 asked to wait {wait:.0f}s -- daily quota, resume later"
                    ) from exc
                await sleep(wait if wait is not None else min(60.0, 2.0 * 2**attempt))
                continue
            raise FatalProviderError(f"HTTP {status}: {exc}") from exc
        except groq.APIConnectionError:
            last_error = "connection"
            await sleep(min(60.0, 2.0 * 2**attempt))
        except groq.APIError as exc:
            # A bare APIError (no status code) is how Groq reports an error event
            # mid-stream. Its rejection of its own generated tool call is the
            # documented Phase 2 failure, scored as one (section 10.4); anything
            # else mid-stream is treated as infrastructure and retried.
            if "tool call validation failed" in str(exc).lower():
                return LlmAttempt("fail", None, "tool_validation_failed")
            last_error = "api_error"
            await sleep(min(60.0, 2.0 * 2**attempt))
    return LlmAttempt("incomplete", None, last_error or "unknown")


# ---------------------------------------------------------------- analysis


@dataclass(frozen=True, slots=True)
class PairStat:
    runs: tuple[int, int]
    diff_pp: float
    flip_rate: float


def _rate(outcomes: Sequence[bool]) -> float:
    return sum(outcomes) / len(outcomes) if outcomes else 0.0


def _pairs(per_run: Mapping[int, Sequence[bool]]) -> list[PairStat]:
    out: list[PairStat] = []
    for i, j in combinations(sorted(per_run), 2):
        a, b = per_run[i], per_run[j]
        n = len(a)
        out.append(
            PairStat(
                (i, j),
                100.0 * (_rate(a) - _rate(b)),
                (sum(x != y for x, y in zip(a, b, strict=True)) / n) if n else 0.0,
            )
        )
    return out


def _outcomes_by_cell(
    records: Sequence[RunRecord], k: int
) -> dict[tuple[str, str], dict[str, list[bool]]]:
    """(language, condition) -> example_id -> the k outcomes in run order,
    only for examples with all k runs scored."""
    cells: dict[tuple[str, str], dict[str, dict[int, bool]]] = {}
    for r in records:
        if r.outcome == "incomplete":
            continue
        cells.setdefault((r.language, r.condition), {}).setdefault(r.example_id, {})[r.run] = (
            r.outcome == "pass"
        )
    result: dict[tuple[str, str], dict[str, list[bool]]] = {}
    for cell, by_example in cells.items():
        result[cell] = {
            ex: [runs[j] for j in range(1, k + 1)]
            for ex, runs in by_example.items()
            if all(j in runs for j in range(1, k + 1))
        }
    return result


def _majority(outcomes: Sequence[bool]) -> bool:
    return sum(outcomes) * 2 > len(outcomes)


def _pair_dict(p: PairStat) -> dict[str, Any]:
    return {"runs": list(p.runs), "diff_pp": p.diff_pp, "flip_rate": p.flip_rate}


def analyze(
    records: Sequence[RunRecord],
    *,
    k: int = 3,
    real_conditions: Sequence[str] = ("whisper", "sarvam"),
    first_n: int = 40,
    n_resamples: int = 10_000,
    seed: int = 0,
) -> dict[str, Any]:
    """Section 10.5 / 10.6 over the committed run log."""
    index_of = {(r.language, r.example_id): r.index for r in records}
    languages = sorted({r.language for r in records})
    cells = _outcomes_by_cell(records, k)
    incomplete: dict[str, int] = {}
    for r in records:
        if r.outcome == "incomplete":
            incomplete[f"{r.language}/{r.condition}"] = (
                incomplete.get(f"{r.language}/{r.condition}", 0) + 1
            )

    def block(
        gt: Mapping[str, list[bool]], real: Mapping[str, list[bool]], ids: Sequence[str]
    ) -> dict[str, Any]:
        d = [_rate(gt[e]) - _rate(real[e]) for e in ids]
        lo, hi = paired_bootstrap_ci(d, n_resamples=n_resamples, seed=seed)
        loss_pass = sum(1 for e in ids if _majority(gt[e]) and not _majority(real[e]))
        loss_fail = sum(1 for e in ids if not _majority(gt[e]) and _majority(real[e]))
        return {
            "n": len(ids),
            "mean_loss_pp": 100.0 * (sum(d) / len(d)) if d else 0.0,
            "loss_ci_pp": [100.0 * lo, 100.0 * hi],
            "majority_gt_pass_real_fail": loss_pass,
            "majority_gt_fail_real_pass": loss_fail,
            "mcnemar_p": mcnemar_exact_p(loss_pass, loss_fail),
        }

    out: dict[str, Any] = {"k": k, "incomplete_cells": incomplete, "languages": {}}
    pooled_inputs: dict[str, tuple[dict[str, list[bool]], dict[str, list[bool]]]] = {}
    for language in languages:
        gt = cells.get((language, GT), {})
        runs_gt = {j: [gt[e][j - 1] for e in sorted(gt)] for j in range(1, k + 1)}
        gt_pairs = _pairs(runs_gt)
        noise_floor = max((abs(p.diff_pp) for p in gt_pairs), default=0.0)
        lang_out: dict[str, Any] = {
            "n_gt_complete": len(gt),
            "gt_rate_per_run_pct": {str(j): 100.0 * _rate(v) for j, v in runs_gt.items()},
            "gt_aa_pairs": [_pair_dict(p) for p in gt_pairs],
            "noise_floor_pp": noise_floor,
            "arms": {},
        }
        for cond in real_conditions:
            real = cells.get((language, cond), {})
            ids = sorted(set(gt) & set(real))
            if not ids:
                lang_out["arms"][cond] = {"n": 0, "verdict": "no complete data"}
                continue
            runs_real = {j: [real[e][j - 1] for e in ids] for j in range(1, k + 1)}
            arm = block(gt, real, ids)
            arm["real_rate_per_run_pct"] = {str(j): 100.0 * _rate(v) for j, v in runs_real.items()}
            arm["real_aa_pairs"] = [_pair_dict(p) for p in _pairs(runs_real)]
            subset = [e for e in ids if index_of[(language, e)] < first_n]
            arm["first_n_subset"] = block(gt, real, subset)
            ci_excludes_zero = arm["loss_ci_pp"][0] > 0 or arm["loss_ci_pp"][1] < 0
            arm["rule_a_ci_excludes_zero"] = ci_excludes_zero
            arm["rule_b_mcnemar_p_lt_0.05"] = arm["mcnemar_p"] < 0.05
            arm["rule_c_loss_exceeds_noise_floor"] = arm["mean_loss_pp"] > noise_floor
            arm["verdict"] = (
                "ASR costs task success"
                if ci_excludes_zero
                and arm["mcnemar_p"] < 0.05
                and arm["mean_loss_pp"] > noise_floor
                else "not distinguishable from LLM sampling noise"
            )
            lang_out["arms"][cond] = arm
            pooled_inputs.setdefault(cond, ({}, {}))
            pooled_inputs[cond][0].update({f"{language}:{e}": gt[e] for e in ids})
            pooled_inputs[cond][1].update({f"{language}:{e}": real[e] for e in ids})
        out["languages"][language] = lang_out
    out["pooled_secondary"] = {
        cond: block(gtp, realp, sorted(gtp)) for cond, (gtp, realp) in pooled_inputs.items()
    }
    return out
