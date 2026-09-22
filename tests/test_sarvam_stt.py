"""Unit tests for `SarvamSTT` against a mocked Sarvam client -- no network.
Real round trip is `test_sarvam_stt_integration.py`, opt-in and skipped
without `SARVAM_API_KEY` (phase-2b spec section 7)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import pytest
from sarvamai.core import ApiError

from dhvani.clock import FakeClock
from dhvani.providers.base import ProviderError
from dhvani.providers.sarvam_stt import DEFAULT_MODEL, SarvamSTT
from dhvani.telemetry.span import FINAL_TRANSCRIPT, TurnTrace
from dhvani.types import AudioChunk, Stage


@dataclass
class _FakeTranscribeResponse:
    transcript: str
    language_code: str | None = None


class _FakeSpeechToText:
    """Stands in for `AsyncSpeechToTextClient`. Records every call's kwargs
    so tests can assert on what `SarvamSTT` actually sent."""

    def __init__(self, response: _FakeTranscribeResponse | BaseException) -> None:
        self._response = response
        self.calls: list[Mapping[str, Any]] = []

    async def transcribe(self, **kwargs: Any) -> _FakeTranscribeResponse:
        self.calls.append(kwargs)
        if isinstance(self._response, BaseException):
            raise self._response
        return self._response


def _make_stt(
    response: _FakeTranscribeResponse | BaseException,
) -> tuple[SarvamSTT, _FakeSpeechToText]:
    clock = FakeClock()
    stt = SarvamSTT(DEFAULT_MODEL, clock, api_key="test-key")
    fake = _FakeSpeechToText(response)
    # `speech_to_text` is a read-only cached property on the real client;
    # patch the bound method on the resolved sub-client instance instead.
    stt._client.speech_to_text.transcribe = fake.transcribe
    return stt, fake


async def _two_chunks() -> AsyncIterator[AudioChunk]:
    yield AudioChunk(pcm=b"\x01\x00" * 160, sample_rate=16000, seq=0)
    yield AudioChunk(pcm=b"\x02\x00" * 160, sample_rate=16000, seq=1, is_last=True)


def test_sarvam_stt_requires_api_key() -> None:
    clock = FakeClock()
    with pytest.raises(ProviderError, match="SARVAM_API_KEY"):
        SarvamSTT(DEFAULT_MODEL, clock, api_key=None)


@pytest.mark.asyncio
async def test_sarvam_stt_buffers_all_chunks_before_one_call() -> None:
    stt, fake = _make_stt(_FakeTranscribeResponse(transcript="hello world"))
    trace = TurnTrace(FakeClock(), turn_id="t1")

    transcripts = [t async for t in stt.stream(_two_chunks(), trace=trace)]

    assert len(fake.calls) == 1
    assert len(transcripts) == 1


@pytest.mark.asyncio
async def test_sarvam_stt_emits_one_final_transcript() -> None:
    stt, _fake = _make_stt(_FakeTranscribeResponse(transcript="hello world"))
    trace = TurnTrace(FakeClock(), turn_id="t1")

    (transcript,) = [t async for t in stt.stream(_two_chunks(), trace=trace)]

    assert transcript.is_final is True
    assert transcript.text == "hello world"


@pytest.mark.asyncio
async def test_sarvam_stt_maps_response_fields() -> None:
    stt, _fake = _make_stt(_FakeTranscribeResponse(transcript="मेरा फोन", language_code="hi-IN"))
    trace = TurnTrace(FakeClock(), turn_id="t1")

    (transcript,) = [t async for t in stt.stream(_two_chunks(), trace=trace)]

    assert transcript.text == "मेरा फोन"
    assert transcript.language == "hi-IN"


@pytest.mark.asyncio
async def test_sarvam_stt_uses_transcribe_mode_never_translate() -> None:
    """The one fact phase-2b spec section A.1 exists to nail down."""
    stt, fake = _make_stt(_FakeTranscribeResponse(transcript="hello"))
    trace = TurnTrace(FakeClock(), turn_id="t1")

    async for _ in stt.stream(_two_chunks(), trace=trace):
        pass

    assert fake.calls[0]["mode"] == "transcribe"


@pytest.mark.asyncio
async def test_sarvam_stt_sends_wav_file_and_model() -> None:
    stt, fake = _make_stt(_FakeTranscribeResponse(transcript="hello"))
    trace = TurnTrace(FakeClock(), turn_id="t1")

    async for _ in stt.stream(_two_chunks(), trace=trace):
        pass

    filename, wav_bytes, content_type = fake.calls[0]["file"]
    assert filename == "audio.wav"
    assert wav_bytes[:4] == b"RIFF"
    assert content_type == "audio/wav"
    assert fake.calls[0]["model"] == DEFAULT_MODEL


@pytest.mark.asyncio
async def test_sarvam_stt_opens_stt_span_and_marks_final_transcript() -> None:
    stt, _fake = _make_stt(_FakeTranscribeResponse(transcript="hello"))
    trace = TurnTrace(FakeClock(), turn_id="t1")

    async for _ in stt.stream(_two_chunks(), trace=trace):
        pass

    assert len(trace.spans) == 1
    assert trace.spans[0].stage == Stage.STT
    assert trace.spans[0].name == "sarvam"
    assert not trace.spans[0].is_open
    assert any(m.name == FINAL_TRANSCRIPT for m in trace.marks)


@pytest.mark.asyncio
async def test_sarvam_stt_empty_audio_yields_empty_final_without_a_call() -> None:
    stt, fake = _make_stt(_FakeTranscribeResponse(transcript="should not be used"))
    trace = TurnTrace(FakeClock(), turn_id="t1")

    async def no_chunks() -> AsyncIterator[AudioChunk]:
        return
        yield  # pragma: no cover -- makes this an async generator

    (transcript,) = [t async for t in stt.stream(no_chunks(), trace=trace)]

    assert transcript.text == ""
    assert transcript.is_final is True
    assert fake.calls == []


@pytest.mark.asyncio
async def test_sarvam_stt_raises_provider_error_on_api_failure() -> None:
    api_error = ApiError(status_code=500, headers={}, body="boom")
    stt, _fake = _make_stt(api_error)
    trace = TurnTrace(FakeClock(), turn_id="t1")

    with pytest.raises(ProviderError):
        async for _ in stt.stream(_two_chunks(), trace=trace):
            pass

    assert not trace.spans[0].is_open


@pytest.mark.asyncio
async def test_sarvam_stt_reraises_cancelled_error_with_span_closed() -> None:
    stt, _fake = _make_stt(asyncio.CancelledError())
    trace = TurnTrace(FakeClock(), turn_id="t1")

    with pytest.raises(asyncio.CancelledError):
        async for _ in stt.stream(_two_chunks(), trace=trace):
            pass

    assert not trace.spans[0].is_open
