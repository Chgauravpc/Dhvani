"""Spans, marks, and per-turn timing traces.

Spans may overlap — Phase 1 runs STT, LLM, and TTS concurrently. Nothing here
assumes spans nest, and no total is ever computed by summing durations;
`stage_total_ms` is a true interval union.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field

from dhvani.clock import Clock
from dhvani.types import Stage

# Reserved mark names. USER_SPEECH_END also pins TurnTrace.t0_ns when recorded.
USER_SPEECH_END = "user_speech_end"
FIRST_PARTIAL = "first_partial"
FINAL_TRANSCRIPT = "final_transcript"
FIRST_LLM_TOKEN = "first_llm_token"
FIRST_AUDIO_OUT = "first_audio_out"


@dataclass(slots=True)
class Span:
    """One timed unit of work within a turn. Mutable: closed by `end_ns`."""

    stage: Stage
    name: str
    start_ns: int
    end_ns: int | None = None
    attrs: dict[str, object] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        """Elapsed time in milliseconds, or None while still open."""
        if self.end_ns is None:
            return None
        return (self.end_ns - self.start_ns) / 1_000_000

    @property
    def is_open(self) -> bool:
        return self.end_ns is None


@dataclass(slots=True)
class Mark:
    """A single labeled instant within a turn."""

    name: str
    at_ns: int


class TurnTrace:
    """Timing record for one user-utterance to agent-response cycle."""

    def __init__(self, clock: Clock, turn_id: str | None = None) -> None:
        self._clock = clock
        self.turn_id = turn_id if turn_id is not None else uuid.uuid4().hex[:8]
        self.t0_ns = clock.now_ns()
        self.spans: list[Span] = []
        self.marks: list[Mark] = []

    @contextmanager
    def span(self, stage: Stage, name: str, **attrs: object) -> Iterator[Span]:
        """Open a synchronous span, closing it on exit or exception."""
        s = Span(stage=stage, name=name, start_ns=self._clock.now_ns(), attrs=dict(attrs))
        self.spans.append(s)
        try:
            yield s
        except BaseException as exc:
            s.attrs["error"] = repr(exc)
            raise
        finally:
            if s.end_ns is None:
                s.end_ns = self._clock.now_ns()

    @asynccontextmanager
    async def aspan(self, stage: Stage, name: str, **attrs: object) -> AsyncIterator[Span]:
        """Open an async span, closing it on exit, exception, or cancellation."""
        s = Span(stage=stage, name=name, start_ns=self._clock.now_ns(), attrs=dict(attrs))
        self.spans.append(s)
        try:
            yield s
        except BaseException as exc:
            s.attrs["error"] = repr(exc)
            raise
        finally:
            if s.end_ns is None:
                s.end_ns = self._clock.now_ns()

    def mark(self, name: str) -> None:
        """Record a labeled instant. Recording USER_SPEECH_END also sets t0."""
        at_ns = self._clock.now_ns()
        self.marks.append(Mark(name=name, at_ns=at_ns))
        if name == USER_SPEECH_END:
            self.t0_ns = at_ns

    def set_t0(self) -> None:
        """Pin the reference zero to now. Called at end-of-user-speech."""
        self.t0_ns = self._clock.now_ns()

    @property
    def ttfa_ms(self) -> float | None:
        """Time To First Audio: t0 to the first FIRST_AUDIO_OUT mark.

        None if that mark was never recorded.
        """
        for m in self.marks:
            if m.name == FIRST_AUDIO_OUT:
                return (m.at_ns - self.t0_ns) / 1_000_000
        return None

    @property
    def total_ms(self) -> float | None:
        """Wall time from t0 to the last recorded span end or mark.

        None if nothing has completed yet.
        """
        ends = [s.end_ns for s in self.spans if s.end_ns is not None]
        ends += [m.at_ns for m in self.marks]
        if not ends:
            return None
        return (max(ends) - self.t0_ns) / 1_000_000

    def critical_path(self) -> list[Span]:
        """Spans on the path from t0 to first audio.

        Walks backward from the FIRST_AUDIO_OUT mark (or, absent that mark,
        the latest span end). At each step, every span *active* at the
        current cursor instant -- its interval covers that instant, whether
        or not it has closed yet -- is on the path; the cursor then jumps to
        the earliest start among them, and the process repeats until it
        reaches t0.

        This deliberately includes spans that are still open at (or close
        after) the target instant: in the overlapped runner, TTS is still
        synthesizing later sentences well after FIRST_AUDIO_OUT, and that
        later time is still genuinely spent on the path to it. An earlier
        version of this method only ever selected spans that had *already
        closed* by the cursor, which silently excluded every concurrently
        running span from an overlapped trace -- exactly the traces this
        project exists to produce.

        If a genuine idle gap exists (nothing was active at some point on
        the way back to t0), the walk stops there rather than guessing at a
        causal link across it.
        """
        if not self.spans:
            return []

        audio_mark = next((m for m in self.marks if m.name == FIRST_AUDIO_OUT), None)
        if audio_mark is not None:
            target_ns = audio_mark.at_ns
        else:
            ends = [s.end_ns for s in self.spans if s.end_ns is not None]
            if not ends:
                return []
            target_ns = max(ends)

        def active_at(span: Span, instant_ns: int) -> bool:
            end_ns = span.end_ns if span.end_ns is not None else instant_ns
            return span.start_ns <= instant_ns <= end_ns

        selected: dict[int, Span] = {}
        cursor_ns = target_ns
        while cursor_ns > self.t0_ns:
            active = [s for s in self.spans if active_at(s, cursor_ns)]
            new = [s for s in active if id(s) not in selected]
            if not new:
                break
            for s in new:
                selected[id(s)] = s
            next_cursor_ns = min(s.start_ns for s in active)
            if next_cursor_ns >= cursor_ns:
                break
            cursor_ns = next_cursor_ns

        return sorted(selected.values(), key=lambda s: s.start_ns)

    def stage_total_ms(self, stage: Stage) -> float:
        """Wall-clock time covered by spans of this stage.

        Overlapping spans count once: this is the union of intervals, not
        the sum of durations. Open spans use the current clock time as a
        provisional end.
        """
        now_ns = self._clock.now_ns()
        intervals = sorted(
            (s.start_ns, s.end_ns if s.end_ns is not None else now_ns)
            for s in self.spans
            if s.stage == stage
        )
        if not intervals:
            return 0.0

        merged: list[list[int]] = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])

        total_ns = sum(end - start for start, end in merged)
        return total_ns / 1_000_000
