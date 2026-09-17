"""Core data model: audio, transcripts, LLM deltas, and messages.

All types are frozen and slotted. Time fields elsewhere in the codebase follow
the `_ns` (int, internal) / `_ms` (float, at API boundaries) naming convention;
nothing in this module carries a time field directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Stage(StrEnum):
    """A pipeline stage that telemetry spans and latency budgets key on."""

    CAPTURE = "capture"
    ENDPOINT = "endpoint"
    STT = "stt"
    LLM = "llm"
    TOOL = "tool"
    TTS = "tts"
    PLAYBACK = "playback"


def _validate_unit_interval(name: str, value: float | None) -> None:
    if value is not None and not (0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be within 0..1, got {value}")


@dataclass(frozen=True, slots=True)
class AudioChunk:
    """One chunk of 16-bit signed little-endian, mono PCM audio."""

    pcm: bytes
    sample_rate: int
    seq: int
    is_last: bool = False

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError(f"sample_rate must be positive, got {self.sample_rate}")
        if len(self.pcm) % 2 != 0:
            raise ValueError(f"pcm length must be even (16-bit samples), got {len(self.pcm)}")

    @property
    def duration_ms(self) -> float:
        """Duration of this chunk in milliseconds."""
        return self.n_samples / self.sample_rate * 1000

    @property
    def n_samples(self) -> int:
        """Number of 16-bit samples in this chunk."""
        return len(self.pcm) // 2


@dataclass(frozen=True, slots=True)
class Transcript:
    """A partial or final speech-to-text result.

    `language` is a BCP-47 tag (e.g. "hi-IN", "en-IN"). `stability` applies to
    partials only and is None on final transcripts.
    """

    text: str
    is_final: bool
    language: str | None = None
    confidence: float | None = None
    stability: float | None = None

    def __post_init__(self) -> None:
        _validate_unit_interval("confidence", self.confidence)
        _validate_unit_interval("stability", self.stability)


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A single tool invocation requested by the LLM."""

    id: str
    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class LLMDelta:
    """One incremental unit of LLM output: text, a tool call, or the final marker."""

    text: str = ""
    tool_call: ToolCall | None = None
    is_final: bool = False


@dataclass(frozen=True, slots=True)
class Message:
    """One turn of conversation history sent to the LLM."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
