"""Real Groq round-trip. Requires GROQ_API_KEY -- opt-in only (marker) and
skipped even under `-m integration` if no key is configured, per phase-1
spec section 7.
"""

from __future__ import annotations

import os

import pytest

from dhvani.clock import RealClock
from dhvani.config import load_dotenv
from dhvani.providers.groq_llm import GroqLLM
from dhvani.telemetry.span import FIRST_LLM_TOKEN, TurnTrace
from dhvani.types import Message, Stage

load_dotenv()  # picks up GROQ_API_KEY from a local .env, same as dhvani.live

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.real_time_loop,  # real network I/O -- see tests/conftest.py
    pytest.mark.skipif(not os.environ.get("GROQ_API_KEY"), reason="GROQ_API_KEY not set"),
]


async def test_groq_llm_round_trip_shape() -> None:
    clock = RealClock()
    llm = GroqLLM(clock)
    trace = TurnTrace(clock, turn_id="integration")
    messages = [Message(role="user", content="Reply with exactly the word: pong")]

    deltas = [d async for d in llm.stream(messages, trace=trace)]

    text = "".join(d.text for d in deltas if d.text)
    assert "pong" in text.lower()
    assert deltas[-1].is_final
    llm_span = next(s for s in trace.spans if s.stage == Stage.LLM)
    assert not llm_span.is_open
    assert any(m.name == FIRST_LLM_TOKEN for m in trace.marks)
