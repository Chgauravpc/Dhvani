"""Runtime settings and latency budgets.

Phase 0 had no config file format; Phase 1 adds exactly one, `.env`, for a
single purpose: keeping `GROQ_API_KEY` out of the shell history and out of
version control on a local dev machine. `load_dotenv` is deliberately
minimal (not a general .env parser) -- this project has no other use for
one.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dhvani.telemetry.span import TurnTrace
from dhvani.types import Stage

_DEFAULT_STAGE_BUDGETS_MS: Mapping[Stage, float] = {
    Stage.ENDPOINT: 300.0,
    Stage.STT: 200.0,
    Stage.LLM: 300.0,
    Stage.TTS: 150.0,
}

_DEFAULT_TTFA_TARGET_MS = 800.0
_DEFAULT_LOG_LEVEL = "INFO"


@dataclass(frozen=True, slots=True)
class BudgetViolation:
    """One stage (or, when `stage` is None, the overall TTFA target) that
    exceeded its budget for a turn."""

    stage: Stage | None
    budget_ms: float
    actual_ms: float

    @property
    def over_by_ms(self) -> float:
        return self.actual_ms - self.budget_ms


@dataclass(frozen=True, slots=True)
class LatencyBudget:
    """Per-stage and overall latency targets."""

    ttfa_target_ms: float = _DEFAULT_TTFA_TARGET_MS
    stage_budgets_ms: Mapping[Stage, float] = field(
        default_factory=lambda: dict(_DEFAULT_STAGE_BUDGETS_MS)
    )

    def violations(self, trace: TurnTrace) -> list[BudgetViolation]:
        """Every stage, and the overall TTFA target, that this turn exceeded."""
        found: list[BudgetViolation] = []

        ttfa_ms = trace.ttfa_ms
        if ttfa_ms is not None and ttfa_ms > self.ttfa_target_ms:
            found.append(
                BudgetViolation(stage=None, budget_ms=self.ttfa_target_ms, actual_ms=ttfa_ms)
            )

        for stage, budget_ms in self.stage_budgets_ms.items():
            actual_ms = trace.stage_total_ms(stage)
            if actual_ms > budget_ms:
                found.append(BudgetViolation(stage=stage, budget_ms=budget_ms, actual_ms=actual_ms))

        return found


@dataclass(frozen=True, slots=True)
class Settings:
    """Settings read from `DHVANI_`-prefixed environment variables."""

    ttfa_target_ms: float = _DEFAULT_TTFA_TARGET_MS
    log_level: str = _DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = env if env is not None else os.environ
        ttfa_target_ms = float(source.get("DHVANI_TTFA_TARGET_MS", _DEFAULT_TTFA_TARGET_MS))
        log_level = source.get("DHVANI_LOG_LEVEL", _DEFAULT_LOG_LEVEL)
        return cls(ttfa_target_ms=ttfa_target_ms, log_level=log_level)


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load `KEY=VALUE` lines from `path` into `os.environ`.

    Never overrides a variable already set in the real environment. Silent
    no-op if `path` doesn't exist -- callers (e.g. `dhvani.live`) still work
    fine with the key exported directly instead of via a file.
    """
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
