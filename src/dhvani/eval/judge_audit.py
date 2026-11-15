"""3B-19 steps (a) and (a2): audit the F1 judge against the 3B-5 run log.

Protocol: `docs/runs/3b-19-preregistration.md` (committed before this module).
Nothing here calls an API.

- `mismatching_params` / `judge_list_aware`: the registered exact-match rule and
  the list-aware fix. For a parameter whose function schema says `type: array`,
  VoiceAgentBench's expected strings are the required *elements*; the registered
  judge reads them as alternative values and compares the whole returned list
  against each, so a correct list can never pass.
- `classify_failure`: which check a failing cell failed first.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from dhvani.eval.datasets import ExpectedToolCall
from dhvani.eval.task_success import _normalize
from dhvani.types import ToolCall

_DEVANAGARI = re.compile("[ऀ-ॿ]")

PROVIDER_REJECTED = "provider_rejected"
NO_CALL = "no_call"
WRONG_FUNCTION = "wrong_function"
MISSING_ARGUMENT = "missing_argument"
VALUE_MISMATCH = "value_mismatch"


def array_params(functions: Sequence[Mapping[str, Any]], function_name: str) -> frozenset[str]:
    """Parameters the example's schema for `function_name` declares `type: array`."""
    found: set[str] = set()
    for function in functions:
        if function.get("name") != function_name:
            continue
        properties = (function.get("parameters") or {}).get("properties") or {}
        for param, spec in properties.items():
            if isinstance(spec, Mapping) and spec.get("type") == "array":
                found.add(str(param))
    return frozenset(found)


def _elements(value: object) -> frozenset[str]:
    """Normalised elements of a returned value; a scalar is a one-element list."""
    items = value if isinstance(value, (list, tuple)) else [value]
    return frozenset(_normalize(str(item)) for item in items)


def _param_ok(
    value: object, acceptable: Sequence[str], is_array: bool, *, list_aware: bool
) -> bool:
    if list_aware and is_array:
        return _elements(value) == frozenset(_normalize(a) for a in acceptable)
    actual = _normalize(str(value))
    return any(actual == _normalize(a) for a in acceptable)


def mismatching_params(
    actual: ToolCall,
    expected: ExpectedToolCall,
    arrays: frozenset[str],
    *,
    list_aware: bool,
) -> list[str]:
    """Expected parameters present in `actual` whose value is not accepted."""
    return [
        param
        for param, acceptable in expected.arguments.items()
        if param in actual.arguments
        and not _param_ok(
            actual.arguments[param], acceptable, param in arrays, list_aware=list_aware
        )
    ]


def judge_list_aware(
    actual: ToolCall | None, expected: ExpectedToolCall, arrays: frozenset[str]
) -> bool:
    """The registered judge with array parameters compared as element sets."""
    if actual is None or actual.name != expected.name:
        return False
    if any(param not in actual.arguments for param in expected.arguments):
        return False
    return not mismatching_params(actual, expected, arrays, list_aware=True)


@dataclass(frozen=True, slots=True)
class FailureClass:
    category: str
    list_valued: bool = False
    devanagari: bool = False

    @property
    def other(self) -> bool:
        return self.category == VALUE_MISMATCH and not (self.list_valued or self.devanagari)


def classify_failure(
    actual: ToolCall | None,
    error_class: str,
    expected: ExpectedToolCall,
    arrays: frozenset[str],
    *,
    list_aware: bool = False,
) -> FailureClass:
    """The first check a failing cell fails, in the judge's own order."""
    if error_class == "tool_validation_failed":
        return FailureClass(PROVIDER_REJECTED)
    if actual is None:
        return FailureClass(NO_CALL)
    if actual.name != expected.name:
        return FailureClass(WRONG_FUNCTION)
    if any(param not in actual.arguments for param in expected.arguments):
        return FailureClass(MISSING_ARGUMENT)
    bad = mismatching_params(actual, expected, arrays, list_aware=list_aware)
    return FailureClass(
        VALUE_MISMATCH,
        list_valued=any(param in arrays for param in bad),
        devanagari=any(_DEVANAGARI.search(str(actual.arguments[param])) for param in bad),
    )
