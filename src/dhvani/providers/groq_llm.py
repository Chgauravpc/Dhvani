"""Real LLM via Groq's OpenAI-compatible streaming chat completions.

Free tier, hosted -- chosen over Ollama because no local LLM runtime exists
on the dev machine (see phase-1 spec section 1). Reads `GROQ_API_KEY` from
the environment; never hardcode or log a key.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field

from groq import AsyncGroq, AsyncStream
from groq.types.chat import ChatCompletionChunk

from dhvani.clock import Clock
from dhvani.telemetry.span import FIRST_LLM_TOKEN, TurnTrace
from dhvani.types import LLMDelta, Message, Stage, ToolCall

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


@dataclass
class _PendingToolCall:
    """Accumulates one tool call's streamed fragments.

    Verified directly against a real streaming tool-call response (phase-2
    spec, F1 groundwork): `openai/gpt-oss-20b` on Groq sent this model's one
    tool call as a single chunk with `id`/`function.name` already complete
    and the full `function.arguments` JSON string in one piece -- but
    `id`/`name` are documented as present only on a tool call's *first*
    fragment in the general streaming tool-call convention this mirrors
    (OpenAI-compatible), and `arguments` can arrive over several chunks for
    other models. Accumulating by `index` and concatenating `arguments`
    handles both the observed single-chunk case and the general one.
    """

    id: str | None = None
    name: str | None = None
    arguments_json: str = field(default="")

    def to_tool_call(self, index: int) -> ToolCall:
        try:
            arguments: Mapping[str, object] = json.loads(self.arguments_json or "{}")
        except json.JSONDecodeError:
            arguments = {}
        return ToolCall(id=self.id or f"call_{index}", name=self.name or "", arguments=arguments)


class GroqLLM:
    """Streams a Groq chat completion, mapping deltas to `LLMDelta`.

    Text and tool-call deltas are both mapped -- `ToolCall`s are emitted
    once fully accumulated, immediately before the final delta, matching
    `MockLLM`'s existing tool-call-then-final ordering (phase-0
    `providers/mock.py`) so callers like the F1 ablation harness don't need
    two different tool-call conventions to handle.
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
                tools=list(tools) if tools else None,  # type: ignore[arg-type]
            )
            assert isinstance(response, AsyncStream)
            groq_stream: AsyncStream[ChatCompletionChunk] = response
            first_token = True
            pending_calls: dict[int, _PendingToolCall] = {}
            try:
                async for chunk in groq_stream:
                    delta = chunk.choices[0].delta
                    text = delta.content or ""
                    if text:
                        if first_token:
                            trace.mark(FIRST_LLM_TOKEN)
                            first_token = False
                        yield LLMDelta(text=text)
                    for tool_call_delta in delta.tool_calls or ():
                        pending = pending_calls.setdefault(
                            tool_call_delta.index, _PendingToolCall()
                        )
                        if tool_call_delta.id:
                            pending.id = tool_call_delta.id
                        function = tool_call_delta.function
                        if function is not None:
                            if function.name:
                                pending.name = function.name
                            if function.arguments:
                                pending.arguments_json += function.arguments
            finally:
                await groq_stream.close()
            for index, pending in pending_calls.items():
                yield LLMDelta(tool_call=pending.to_tool_call(index))
            yield LLMDelta(is_final=True)
