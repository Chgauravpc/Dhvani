"""3B-19 step (b): the meaning-level judge for argument-value mismatches.

Protocol: `docs/runs/3b-19-preregistration.md` section 5. The rubric below is
committed before the first call. The judge sees the function name, the parameter
name, the user's query, the accepted value(s) and the returned value, and answers
`{"equivalent": true|false}`. Nothing else (no ASR condition, no outcome).

Infrastructure errors (429, 5xx, timeouts) are retried and never scored; an
answer that cannot be parsed after `MAX_PARSE_TRIES` tries is `unparsed`, also
never scored, and is reported.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

import groq

from dhvani.eval.noise_floor import QUOTA_WAIT_LIMIT_S, FatalProviderError, QuotaExhausted

JUDGE_MODEL = "openai/gpt-oss-120b"
REASONING_EFFORT: Literal["low"] = "low"
MAX_COMPLETION_TOKENS = 2048
MAX_TRIES = 6
MAX_PARSE_TRIES = 3

RUBRIC = (
    "You compare two values given for one parameter of a function call.\n"
    "The user's request and the function/parameter are context. Decide whether the "
    "RETURNED value means the same thing as an ACCEPTED value.\n"
    "- equivalent: the two values denote the same thing, in any script, language or "
    "surface form (for example a name written in Devanagari and in Latin letters, a "
    "transliteration, a translation, a different spelling or casing, or a trivially "
    "different format of the same quantity).\n"
    "- not equivalent: they differ in referent, number, quantity, unit or meaning, or "
    "the returned value is a different thing, a narrower or broader thing, or a "
    "different place, person or item.\n"
    "If several values are accepted, the returned value is equivalent if it matches "
    "any one of them.\n"
    'Answer with JSON only: {"equivalent": true} or {"equivalent": false}.'
)


@dataclass(frozen=True, slots=True)
class JudgeItem:
    query: str
    function: str
    parameter: str
    accepted_values: str
    returned_value: str


def build_messages(item: JudgeItem) -> list[dict[str, str]]:
    user = (
        f"User request: {item.query}\n"
        f"Function: {item.function}\n"
        f"Parameter: {item.parameter}\n"
        f"ACCEPTED value(s): {item.accepted_values}\n"
        f"RETURNED value: {item.returned_value}"
    )
    return [{"role": "system", "content": RUBRIC}, {"role": "user", "content": user}]


_JSON = re.compile(r"\{[^{}]*\}")


def parse_verdict(text: str | None) -> bool | None:
    """True/False from `{"equivalent": ...}`; None if the answer is not that."""
    if not text:
        return None
    for chunk in _JSON.findall(text):
        try:
            value = json.loads(chunk).get("equivalent")
        except (json.JSONDecodeError, AttributeError):
            continue
        if isinstance(value, bool):
            return value
    return None


@dataclass(frozen=True, slots=True)
class Verdict:
    equivalent: bool | None
    """None means unscored (`unparsed` or `incomplete`)."""
    status: str  # "scored" | "unparsed" | "incomplete"
    error_class: str = ""


async def judge_item(
    client: groq.AsyncGroq,
    item: JudgeItem,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Verdict:
    last_error = ""
    parse_failures = 0
    attempt = 0
    while attempt < MAX_TRIES:
        try:
            response = await client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=cast("Any", build_messages(item)),
                reasoning_effort=REASONING_EFFORT,
                max_completion_tokens=MAX_COMPLETION_TOKENS,
                response_format=cast("Any", {"type": "json_object"}),
            )
        except groq.APIStatusError as exc:
            status = exc.status_code
            if status in (408, 429) or status >= 500:
                last_error = f"http_{status}"
                raw = exc.response.headers.get("retry-after")
                wait = float(raw) if raw and raw.replace(".", "", 1).isdigit() else None
                if status == 429 and wait is not None and wait > QUOTA_WAIT_LIMIT_S:
                    raise QuotaExhausted(f"429 asked to wait {wait:.0f}s") from exc
                await sleep(wait if wait is not None else min(60.0, 2.0 * 2**attempt))
                attempt += 1
                continue
            raise FatalProviderError(f"HTTP {status}: {exc}") from exc
        except groq.APIConnectionError:
            last_error = "connection"
            await sleep(min(60.0, 2.0 * 2**attempt))
            attempt += 1
            continue
        verdict = parse_verdict(response.choices[0].message.content)
        if verdict is not None:
            return Verdict(verdict, "scored")
        parse_failures += 1
        if parse_failures >= MAX_PARSE_TRIES:
            return Verdict(None, "unparsed", "unparsed")
    return Verdict(None, "incomplete", last_error or "unknown")


# ---------------------------------------------------------------- agreement


def cohens_kappa(a: Sequence[bool], b: Sequence[bool]) -> float:
    """Cohen's kappa for two binary raters; 1.0 when both are constant and equal."""
    n = len(a)
    if n == 0 or n != len(b):
        raise ValueError("need two equal-length, non-empty label lists")
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pa, pb = sum(a) / n, sum(b) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def agreement(
    judge: Sequence[bool], owner: Sequence[bool], *, resamples: int = 10_000, seed: int = 0
) -> dict[str, Any]:
    """Kappa and raw agreement, with percentile bootstrap 95% intervals over items."""
    n = len(judge)
    rng = random.Random(seed)
    kappas: list[float] = []
    raws: list[float] = []
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        j = [judge[i] for i in idx]
        o = [owner[i] for i in idx]
        kappas.append(cohens_kappa(j, o))
        raws.append(sum(x == y for x, y in zip(j, o, strict=True)) / n)
    kappas.sort()
    raws.sort()
    lo, hi = int(0.025 * resamples), int(0.975 * resamples) - 1
    return {
        "n": n,
        "kappa": cohens_kappa(judge, owner),
        "kappa_ci95": [kappas[lo], kappas[hi]],
        "raw_agreement": sum(x == y for x, y in zip(judge, owner, strict=True)) / n,
        "raw_agreement_ci95": [raws[lo], raws[hi]],
        "judge_equivalent": sum(judge),
        "owner_equivalent": sum(owner),
        "both_equivalent": sum(1 for x, y in zip(judge, owner, strict=True) if x and y),
        "both_not_equivalent": sum(1 for x, y in zip(judge, owner, strict=True) if not x and not y),
        "judge_yes_owner_no": sum(1 for x, y in zip(judge, owner, strict=True) if x and not y),
        "judge_no_owner_yes": sum(1 for x, y in zip(judge, owner, strict=True) if not x and y),
        "bootstrap": {"resamples": resamples, "seed": seed},
    }
