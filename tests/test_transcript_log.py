"""Phase-3b item 3B-3: every eval transcription is logged and reusable."""

from __future__ import annotations

import io
import wave
from array import array
from collections.abc import AsyncIterator
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from dhvani.audio.channel import ChannelConfig
from dhvani.clock import FakeClock
from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.eval import datasets
from dhvani.eval.datasets import ExpectedToolCall, TranscriptExample, VoiceAgentBenchExample
from dhvani.eval.degradation import run_degradation_sweep
from dhvani.eval.entity_error_rate import transcribe_examples
from dhvani.eval.task_success import run_ablation
from dhvani.eval.transcript_log import TranscriptLog, read_transcripts
from dhvani.providers.mock import MockLLM, MockSTT, MockTiming
from dhvani.telemetry.span import FINAL_TRANSCRIPT, TurnTrace
from dhvani.types import AudioChunk, Stage, ToolCall, Transcript

_TIMING = MockTiming(ttfb_ms=1.0, per_unit_ms=1.0)


class _CountingSTT:
    """Drains its audio, returns a fixed transcript, and counts calls --
    so a test can prove a logged example was *not* re-transcribed."""

    name = "counting-stt"

    def __init__(self, final: str, clock: FakeClock) -> None:
        self.final = final
        self.calls = 0
        self._clock = clock

    async def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]:
        self.calls += 1
        async with trace.aspan(Stage.STT, self.name):
            async for _chunk in audio:
                pass
            await self._clock.sleep(0.01)
            trace.mark(FINAL_TRANSCRIPT)
            yield Transcript(text=self.final, is_final=True)


def _example(example_id: str, text: str) -> TranscriptExample:
    pcm = array("h", [int(4000 * ((-1) ** i)) for i in range(160)]).tobytes()
    chunks = [AudioChunk(pcm=pcm, sample_rate=16000, seq=i, is_last=(i == 2)) for i in range(3)]
    return TranscriptExample(
        audio_chunks=chunks, ground_truth_text=text, dataset="test/ds", example_id=example_id
    )


def _log(path: Path, model: str = "m1") -> TranscriptLog:
    return TranscriptLog(path, stt="counting-stt", model=model, run="test-run")


def test_record_then_lookup_and_survive_reopen(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    log = _log(path)
    log.record(dataset="d", example_id="a#1", ground_truth_text="gt", raw_text="heard")
    log.close()

    reopened = _log(path)  # a fresh process after a killed run
    assert reopened.lookup("d", "a#1") == "heard"
    assert reopened.lookup("d", "a#2") is None
    assert reopened.lookup("d", "a#1", condition="other") is None
    assert _log(path, model="m2").lookup("d", "a#1") is None  # model is part of the key

    (record,) = read_transcripts(path)
    assert record.ground_truth_text == "gt"
    assert record.stt == "counting-stt"
    assert record.run == "test-run"


def test_line_is_on_disk_before_close(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    log = _log(path)
    log.record(dataset="d", example_id="a#1", ground_truth_text="gt", raw_text="x")
    assert len(read_transcripts(path)) == 1  # flushed per line, not at close
    log.close()


def test_missing_example_id_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="example_id"):
        _log(tmp_path / "t.jsonl").record(
            dataset="d", example_id="", ground_truth_text="gt", raw_text="x"
        )


@pytest.mark.asyncio
async def test_transcribe_examples_reuses_logged_text_instead_of_rerunning_stt(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    path = tmp_path / "f2.jsonl"
    examples = [_example("s#0", "my aadhaar card"), _example("s#1", "nothing here")]

    first_stt = _CountingSTT("first pass", clock)
    log = _log(path)
    first = await transcribe_examples(examples, first_stt, clock, log=log, split="test")
    log.close()
    assert first_stt.calls == 2

    second_stt = _CountingSTT("second pass", clock)
    log = _log(path)
    second = await transcribe_examples(examples, second_stt, clock, log=log, split="test")
    log.close()

    assert second_stt.calls == 0
    assert [t.raw_text for t in second] == ["first pass", "first pass"]
    assert [t.raw_text for t in first] == [t.raw_text for t in second]
    assert {r.split for r in read_transcripts(path)} == {"test"}
    assert len(read_transcripts(path)) == 2  # reuse appends nothing


@pytest.mark.asyncio
async def test_degradation_sweep_logs_one_line_per_example_per_config(tmp_path: Path) -> None:
    clock = FakeClock()
    path = tmp_path / "deg.jsonl"
    configs = [
        ChannelConfig(narrowband_hz=16000, mulaw=False),
        ChannelConfig(narrowband_hz=8000, mulaw=True),
    ]
    a, b = (c.label for c in configs)
    assert a != b
    log = _log(path)
    await run_degradation_sweep(
        [_example("s#0", "a"), _example("s#1", "b")],
        configs,
        _CountingSTT("x", clock),
        clock,
        log=log,
    )
    log.close()

    records = read_transcripts(path)
    assert len(records) == 4
    assert {(r.example_id, r.condition) for r in records} == {
        ("s#0", a),
        ("s#1", a),
        ("s#0", b),
        ("s#1", b),
    }


@pytest.mark.asyncio
async def test_f1_ablation_logs_real_and_corrected_transcripts(tmp_path: Path) -> None:
    wav_path = tmp_path / "silence.wav"
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)
    clock = FakeClock()
    llm = MockLLM(
        response="",
        timing=_TIMING,
        clock=clock,
        tool_calls=(ToolCall(id="1", name="book", arguments={"time": "7pm"}),),
    )
    example = VoiceAgentBenchExample(
        id="vab-7",
        language="hindi",
        query="book at 7pm",
        audio_path=wav_path,
        functions=[{"name": "book", "parameters": {"type": "dict", "properties": {}}}],
        expected_tool_call=ExpectedToolCall(name="book", arguments={"time": ("7pm",)}),
    )
    path = tmp_path / "f1.jsonl"
    log = _log(path)
    await run_ablation(
        [example],
        make_real_stt=lambda: MockSTT(partials=[], final="real", timing=_TIMING, clock=clock),
        llm=llm,
        clock=clock,
        make_corrected_stt=lambda: MockSTT(
            partials=[], final="corrected", timing=_TIMING, clock=clock
        ),
        log=log,
    )
    log.close()

    records = {r.condition: r for r in read_transcripts(path)}
    assert set(records) == {"real", "corrected"}
    assert records["real"].raw_text == "real"
    assert records["corrected"].raw_text == "corrected"
    assert records["real"].example_id == "vab-7"
    assert records["real"].ground_truth_text == "book at 7pm"
    assert records["real"].split == "hindi"


def _wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 800)
    return buf.getvalue()


def test_filtered_loader_assigns_shard_and_row_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ids must point at the original row even though the filtered loader
    decodes only some rows, in batches -- otherwise a logged transcript
    can't be matched back to its audio."""
    texts = [f"filler row {i}" for i in range(150)]
    texts[3] = "my aadhaar card"
    texts[130] = "link upi please"  # lands in the third streamed batch (size 64)
    audio = [{"bytes": _wav_bytes(), "path": None}] * len(texts)
    shard = tmp_path / "test-00000-of-00001.parquet"
    pq.write_table(pa.table({"text": texts, "audio": audio}), shard)

    monkeypatch.setattr(
        datasets, "_repo_parquet_files", lambda repo: ["data/test-00000-of-00001.parquet"]
    )
    monkeypatch.setattr(datasets, "hf_hub_download", lambda *a, **k: str(shard))

    loaded = datasets._load_hf_audio_parquet_filtered(
        "org/repo", DEFAULT_LEXICON, None, n_clean_sample=5, seed=0
    )

    by_id = {e.example_id: e for e in loaded.entity_bearing}
    assert set(by_id) == {
        "data/test-00000-of-00001.parquet#3",
        "data/test-00000-of-00001.parquet#130",
    }
    assert by_id["data/test-00000-of-00001.parquet#130"].ground_truth_text == "link upi please"
    assert len(loaded.clean_sample) == 5
    for example in loaded.entity_bearing + loaded.clean_sample:
        assert example.dataset == "org/repo"
        row = int(example.example_id.rsplit("#", 1)[1])
        assert example.ground_truth_text == texts[row]
