"""Real LLM via Groq's OpenAI-compatible streaming chat completions.

Free tier, hosted -- chosen over Ollama because no local LLM runtime exists
on the dev machine (see phase-1 spec section 1). Reads `GROQ_API_KEY` from
the environment; never hardcode or log a key.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping, Sequence

from groq import AsyncGroq, AsyncStream
from groq.types.chat import ChatCompletionChunk

from dhvani.clock import Clock
from dhvani.telemetry.span import FIRST_LLM_TOKEN, TurnTrace
from dhvani.types import LLMDelta, Message, Stage

DEFAULT_MODEL = "openai/gpt-oss-20b"
"""Verified available and working against the account's actual key (Groq's
model lineup changes over time -- llama-3.3-70b-versatile, an earlier
choice here, has since been retired). Picked for speed: a smaller model
matters more than raw capability for a sub-800ms conversational agent."""

DEFAULT_REASONING_EFFORT = "low"
"""gpt-oss models stream their chain-of-thought as separate `reasoning`-
channel deltas before any `content` delta -- verified directly: a plain
call with no `reasoning_effort` set produced 34 reasoning deltas and took
several real seconds before the first content token, which defeats a
sub-800ms target outright. `reasoning_effort="low"` cut that to 4 reasoning
deltas and ~0.7s to first content in the same test, with the same correct
answer. `"none"` is rejected by this model (400: must be low/medium/high).
Pass `reasoning_effort=None` to omit the parameter entirely for a model
that doesn't accept it."""


class GroqLLM:
    """Streams a Groq chat completion, mapping deltas to `LLMDelta`.

    Tool-calling is accepted for protocol conformance but not mapped back
    into `LLMDelta.tool_call` -- out of scope for the phase-1 milestone
    (a spoken conversation demo, not agentic tool use).
    """

    name = "groq"

    def __init__(
        self,
        clock: Clock,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        reasoning_effort: str | None = DEFAULT_REASONING_EFFORT,
    ) -> None:
        self._client = AsyncGroq(api_key=api_key or os.environ.get("GROQ_API_KEY"))
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._clock = clock

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        trace: TurnTrace,
        tools: Sequence[Mapping[str, object]] = (),
    ) -> AsyncIterator[LLMDelta]:
        async with trace.aspan(Stage.LLM, self.name):
            payload = [{"role": m.role, "content": m.content} for m in messages]
            response = await self._client.chat.completions.create(
                messages=payload,  # type: ignore[arg-type]
                model=self._model,
                stream=True,
                reasoning_effort=self._reasoning_effort,  # type: ignore[arg-type]
            )
            assert isinstance(response, AsyncStream)
            groq_stream: AsyncStream[ChatCompletionChunk] = response
            first_token = True
            try:
                async for chunk in groq_stream:
                    text = chunk.choices[0].delta.content or ""
                    if not text:
                        continue
                    if first_token:
                        trace.mark(FIRST_LLM_TOKEN)
                        first_token = False
                    yield LLMDelta(text=text)
            finally:
                await groq_stream.close()
            yield LLMDelta(is_final=True)
