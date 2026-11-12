"""Committed log of every raw STT transcript an eval produces (phase-3b 3B-3).

Why it exists: fixing the scorer in 3B-1/3B-2 meant every headline number
had to be re-transcribed -- hours of local Whisper and paid Sarvam credits
-- because only the scores were kept, never the text they were computed
from. From 3B-3 on, every eval run appends one JSON line per transcription
to a file under `results/transcripts/`, and any later rescoring reads the
text from there instead of running ASR again.

One line = one (dataset, example_id, stt, model, condition) transcription:

    {"dataset": "ai4bharat/Svarah", "example_id": "data/test-00000-of-00003.parquet#17",
     "split": "test", "stt": "faster-whisper", "model": "small/int8",
     "condition": "clean", "ground_truth_text": "...", "raw_text": "...",
     "run": "f2-svarah-2026-11-13T10:02:11"}

- `condition` separates transcriptions of the same audio under different
  inputs: `clean` for the dataset audio as-is, a channel-config label for
  the degradation sweep, `real`/`corrected` for the F1 ablation arms.
- Append-only and flushed per line, so a run killed half way (this host's
  memory guard has done it several times) keeps everything it finished.
- `lookup` returns a previously logged transcript for the same key, which
  lets an F2 rerun skip ASR entirely. Latency-measuring runs (model and
  degradation sweeps) only `record`, never `lookup` -- a cached transcript
  has no timing.

Ground-truth text is stored next to the transcript so a rescoring needs
nothing but this file. Svarah, LAHAJA and IndicVoices are all CC-BY-4.0;
committing their transcripts with attribution is within that licence.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO


@dataclass(frozen=True, slots=True)
class TranscriptRecord:
    dataset: str
    example_id: str
    split: str
    stt: str
    model: str
    condition: str
    ground_truth_text: str
    raw_text: str
    run: str

    def key(self) -> tuple[str, str, str, str, str]:
        return (self.dataset, self.example_id, self.stt, self.model, self.condition)


class TranscriptLog:
    """Append-only JSONL transcript log for one eval run.

    `stt`, `model` and `run` are fixed per log; open a second log on the
    same path (`for_model`) when one run sweeps several models.
    """

    def __init__(self, path: Path, *, stt: str, model: str, run: str) -> None:
        self.path = path
        self.stt = stt
        self.model = model
        self.run = run
        self._known: dict[tuple[str, str, str, str, str], TranscriptRecord] = {}
        if path.exists():
            for record in read_transcripts(path):
                self._known[record.key()] = record
        self._handle: TextIO | None = None

    def for_model(self, *, stt: str, model: str) -> TranscriptLog:
        """A log on the same file for a different (stt, model) -- the model
        sweep's per-grid-cell logs. Call `close` on each."""
        return TranscriptLog(self.path, stt=stt, model=model, run=self.run)

    def lookup(self, dataset: str, example_id: str, condition: str = "clean") -> str | None:
        record = self._known.get((dataset, example_id, self.stt, self.model, condition))
        return record.raw_text if record is not None else None

    def record(
        self,
        *,
        dataset: str,
        example_id: str,
        ground_truth_text: str,
        raw_text: str,
        split: str = "",
        condition: str = "clean",
    ) -> None:
        if not example_id:
            raise ValueError(
                "transcript logged without an example_id -- every example must be "
                "re-findable for rescoring (3B-3)"
            )
        entry = TranscriptRecord(
            dataset=dataset,
            example_id=example_id,
            split=split,
            stt=self.stt,
            model=self.model,
            condition=condition,
            ground_truth_text=ground_truth_text,
            raw_text=raw_text,
            run=self.run,
        )
        if self._handle is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a", encoding="utf-8")
        self._handle.write(json.dumps(_as_dict(entry), ensure_ascii=False) + "\n")
        self._handle.flush()
        self._known[entry.key()] = entry

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def _as_dict(record: TranscriptRecord) -> dict[str, str]:
    return {
        "dataset": record.dataset,
        "example_id": record.example_id,
        "split": record.split,
        "stt": record.stt,
        "model": record.model,
        "condition": record.condition,
        "ground_truth_text": record.ground_truth_text,
        "raw_text": record.raw_text,
        "run": record.run,
    }


def stt_model_label(stt_choice: str, sarvam_model: str) -> str:
    """The `model` field the eval scripts log for their `--stt` choice:
    the Sarvam model id, or `<size>/<compute_type>` for Whisper (size from
    `DHVANI_WHISPER_MODEL`, compute type `WhisperSTT`'s default `int8`)."""
    if stt_choice == "sarvam":
        return sarvam_model
    return f"{os.environ.get('DHVANI_WHISPER_MODEL', 'small')}/int8"


def run_label(script: str, dataset: str) -> str:
    """`<script>-<dataset>-<UTC timestamp>`: which run produced a line."""
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{script}-{dataset}-{stamp}"


def default_log_path(script: str, dataset: str, stt_choice: str) -> Path:
    return Path("results/transcripts") / f"{script}_{dataset}_{stt_choice}.jsonl"


def read_transcripts(path: Path) -> list[TranscriptRecord]:
    """Every record in a transcript log, in file order. A later line for
    the same key supersedes an earlier one in `TranscriptLog`'s lookup."""
    with path.open(encoding="utf-8") as f:
        return [TranscriptRecord(**json.loads(line)) for line in f if line.strip()]
