"""Continuous multi-turn conversation orchestration.

Wires an `Endpointer` (decides utterance boundaries), an `OverlappedRunner`
(runs one turn), and an audio sink (plays the response back) into a session
that keeps going for as long as the input audio stream lasts. Transport-
agnostic: `run()` takes any `AsyncIterator[AudioChunk]` and `audio_sink` is
any callable, so this is identical whether the audio comes from a WebRTC
track or a test double.

Known limitation: a second barge-in arriving before the first one's turn has
finished cancelling will discard the first barge-in utterance's
already-buffered audio rather than queue both. Rare in practice (it requires
interrupting an already-interrupted turn within the same cancellation
window); not handled here rather than adding unverified complexity for it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Protocol

from dhvani.pipeline.overlapped import BargeInError, OverlappedRunner
from dhvani.telemetry.session import SessionTrace
from dhvani.types import AudioChunk
from dhvani.vad.endpointer import EndpointEvent

logger = logging.getLogger(__name__)

_Queue = asyncio.Queue["AudioChunk | None"]


class EndpointerLike(Protocol):
    """What `ConversationSession` needs from an endpointer.

    Matches `Endpointer.feed`'s shape structurally rather than requiring
    that concrete class, so tests can drive turn-taking with a scripted
    double without needing a real (or fake) VAD scorer underneath.
    """

    def feed(self, chunk: AudioChunk) -> list[EndpointEvent]: ...


class ConversationSession:
    """Runs one continuous conversation: audio in, turns out."""

    def __init__(
        self,
        runner: OverlappedRunner,
        endpointer: EndpointerLike,
        audio_sink: Callable[[AudioChunk], None],
    ) -> None:
        self._runner = runner
        self._endpointer = endpointer
        self._audio_sink = audio_sink
        self.session_trace = SessionTrace()

        self._recording_queue: _Queue | None = None
        self._next_queue: _Queue | None = None
        self._turn_task: asyncio.Task[None] | None = None
        self._barge_in: asyncio.Event | None = None
        # The queue object the currently-running turn is consuming, or None
        # if no turn is running. Identity (not a plain boolean) matters: a
        # SPEECH_ENDED that closes the *active* turn's own queue must not
        # schedule a new turn -- the running turn already owns that queue
        # and will finish on its own once it reads the closing sentinel.
        # Only a SPEECH_ENDED for a *different* (newer, barge-in) queue
        # should ever be deferred to `_next_queue`. A plain "is a turn
        # active" boolean can't make that distinction, and a freshly created
        # asyncio.Task hasn't run any code until the caller yields control,
        # so `task.done()` can't either -- both would misfire when a single
        # utterance's SPEECH_STARTED and SPEECH_ENDED are processed back to
        # back with no intervening await.
        self._active_turn_queue: _Queue | None = None

    async def run(self, audio: AsyncIterator[AudioChunk]) -> None:
        """Consume the live audio stream for the lifetime of the session."""
        async for chunk in audio:
            for event in self._endpointer.feed(chunk):
                if event is EndpointEvent.SPEECH_STARTED:
                    self._on_speech_started()
                elif event is EndpointEvent.SPEECH_ENDED:
                    self._on_speech_ended()
            if self._recording_queue is not None:
                self._recording_queue.put_nowait(chunk)

        if self._recording_queue is not None:
            self._recording_queue.put_nowait(None)
        # A cancelled turn's `finally` can chain a brand-new turn task (see
        # `_run_turn`), so keep awaiting until nothing is left running rather
        # than awaiting once -- a single await could return while a chained
        # turn is still in flight.
        while self._turn_task is not None:
            await self._turn_task

    def _on_speech_started(self) -> None:
        self._recording_queue = asyncio.Queue()
        if self._active_turn_queue is not None:
            assert self._barge_in is not None
            self._barge_in.set()
        else:
            self._start_turn(self._recording_queue)

    def _on_speech_ended(self) -> None:
        if self._recording_queue is None:
            return
        self._recording_queue.put_nowait(None)
        finished_queue = self._recording_queue
        self._recording_queue = None

        if finished_queue is self._active_turn_queue:
            # This just closes the running turn's own input; that turn owns
            # this queue already and will finish on its own once it reads
            # the sentinel -- no new turn to schedule.
            return
        if self._active_turn_queue is None:
            self._start_turn(finished_queue)
        else:
            # A barge-in is already in flight for a previous turn; this
            # utterance is fully captured, so start it the moment that
            # turn finishes cancelling (see _run_turn's finally).
            self._next_queue = finished_queue

    def _start_turn(self, queue: _Queue) -> None:
        self._active_turn_queue = queue
        self._barge_in = asyncio.Event()
        self._turn_task = asyncio.create_task(self._run_turn(queue, self._barge_in))

    async def _run_turn(self, queue: _Queue, barge_in: asyncio.Event) -> None:
        try:
            result = await self._runner.run_turn(self._utterance_stream(queue), barge_in=barge_in)
            self.session_trace.add(result.trace)
            logger.info(
                "turn %s: heard %r, ttfa=%sms",
                result.trace.turn_id,
                result.transcript,
                result.trace.ttfa_ms,
            )
            for chunk in result.audio:
                self._audio_sink(chunk)
        except BargeInError as exc:
            self.session_trace.add(exc.trace)
            logger.info("turn %s: interrupted by barge-in", exc.trace.turn_id)
        finally:
            self._active_turn_queue = None
            self._turn_task = None
            self._barge_in = None
            if self._next_queue is not None:
                next_queue = self._next_queue
                self._next_queue = None
                self._start_turn(next_queue)
            # Else, if `self._recording_queue` is not None, the interrupting
            # utterance is still being spoken -- `_on_speech_ended` will
            # start its turn itself once it closes (no turn is running now).

    @staticmethod
    async def _utterance_stream(queue: _Queue) -> AsyncIterator[AudioChunk]:
        while True:
            item = await queue.get()
            if item is None:
                return
            yield item
