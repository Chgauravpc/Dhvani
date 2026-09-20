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


async def test_groq_llm_maps_a_real_tool_call() -> None:
    """The F1 ablation harness needs real ToolCall deltas, not just text --
    verifies the accumulation-by-index logic against a real streamed
    response (see providers/groq_llm.py's `_PendingToolCall`)."""
    clock = RealClock()
    llm = GroqLLM(clock)
    trace = TurnTrace(clock, turn_id="integration-tools")
    messages = [Message(role="user", content="Book me a table for 4 at 7pm tonight.")]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "book_table",
                "description": "Reserve a restaurant table.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "party_size": {"type": "integer"},
                        "time": {"type": "string"},
                    },
                    "required": ["party_size", "time"],
                },
            },
        }
    ]

    deltas = [d async for d in llm.stream(messages, trace=trace, tools=tools)]

    tool_calls = [d.tool_call for d in deltas if d.tool_call is not None]
    assert len(tool_calls) == 1
    call = tool_calls[0]
    assert call.name == "book_table"
    assert call.arguments.get("party_size") in (4, "4")
    assert deltas[-1].is_final
