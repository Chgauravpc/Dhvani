"""Manifest loaders for VoiceAgentBench (F1), Svarah, and LAHAJA (F2).

Uses `huggingface_hub` directly, not the heavier `datasets` library (phase-2
spec section 4) -- confirmed to actually work this way for VoiceAgentBench,
which is plain per-language/category JSON files plus separately-hosted
audio files (`hf_hub_download` on exact paths, no network beyond that).

Svarah and LAHAJA are different in two verified ways the spec did not
anticipate:

1. **Both are gated**, not just LAHAJA. A real `hf_hub_download` attempt
   against `ai4bharat/Svarah` returned `GatedRepoError` -- secondary sources
   describing it as open access were wrong. `load_svarah`/`load_lahaja`
   need an authenticated `huggingface_hub` login that has accepted each
   dataset's terms; `load_voiceagentbench_subset` does not (verified: an
   unauthenticated download succeeds).
2. **Both ship as Hugging Face parquet with embedded audio**, not the raw
   `.wav` + JSON-manifest layout the spec's citation of Svarah's own README
   manifest format described -- that format is what the *original* Svarah
   release uses; the Hugging Face mirror re-packages it as parquet. Reading
   parquet still doesn't need the `datasets` library, just `pyarrow`
   (already a dependency for exactly this).

**Unverified pending your Hugging Face access** (flagged, not guessed past):
the exact column names inside Svarah's and LAHAJA's parquet files. Both
loaders below assume the standard Hugging Face `Audio()` feature shape (a
struct column named `audio` with an embedded `bytes` field) and a text
column from a short candidate list, and raise a clear, specific error
naming the real columns found if none of the candidates match -- so a first
real run either works or fails in an obviously fixable way, rather than
silently reading the wrong field.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download, list_repo_files

from dhvani.eval.audio_io import decode_audio_bytes_to_chunks
from dhvani.types import AudioChunk

_VOICEAGENTBENCH_REPO = "krutrim-ai-labs/VoiceAgentBench"
_SVARAH_REPO = "ai4bharat/Svarah"
_LAHAJA_REPO = "ai4bharat/lahaja"

_SINGLE_TOOL_CATEGORY = "single_tool"
"""The only VoiceAgentBench category `load_voiceagentbench_subset` reads --
see phase-2 open question 1: `parallel_tool`/`seqdep_tool` carry ordered
lists of expected calls and `multi_turn` needs chat-history plumbing, which
`judge_tool_call`'s single-call design does not handle."""

_TEXT_COLUMN_CANDIDATES = ("text", "transcript", "sentence", "normalized_text")
_AUDIO_COLUMN_CANDIDATES = ("audio", "audio_filepath")


@dataclass(frozen=True, slots=True)
class ExpectedToolCall:
    """One tool call VoiceAgentBench considers correct for an example.

    `arguments` maps each parameter name to every value VoiceAgentBench
    accepts as correct for it -- always strings, since the raw JSON mixes
    numbers and strings across languages and examples.
    """

    name: str
    arguments: Mapping[str, Sequence[str]]


def _parse_expected_tool_call(raw: Sequence[Mapping[str, object]]) -> ExpectedToolCall:
    """The real VoiceAgentBench shape, checked directly against downloaded
    examples (not the flat `{"name": ..., "arguments": ...}` phase-2 spec
    section 6.6 sketched): a list containing exactly one
    `{function_name: {param: [acceptable value variants]}}` dict. Confirmed
    on real `single_tool` examples in both English and Hindi; that category
    restriction (see `_SINGLE_TOOL_CATEGORY`) is what keeps this a safe
    assumption -- a `parallel_tool` example's list has more than one entry.
    """
    if len(raw) != 1:
        raise ValueError(f"expected exactly one tool call in a single_tool example, got {len(raw)}")
    ((name, params),) = raw[0].items()
    assert isinstance(params, Mapping)
    arguments = {str(param): tuple(str(v) for v in variants) for param, variants in params.items()}
    return ExpectedToolCall(name=str(name), arguments=arguments)


@dataclass(frozen=True, slots=True)
class VoiceAgentBenchExample:
    id: str
    language: str
    query: str
    audio_path: Path
    functions: Sequence[Mapping[str, object]]
    expected_tool_call: ExpectedToolCall


def load_voiceagentbench_subset(
    languages: Sequence[str],
    n_per_language: int,
    cache_dir: Path | None = None,
) -> list[VoiceAgentBenchExample]:
    """Loads up to `n_per_language` `single_tool` examples per language,
    downloading each example's audio alongside its manifest entry."""
    cache_dir_str = str(cache_dir) if cache_dir is not None else None
    examples: list[VoiceAgentBenchExample] = []
    for language in languages:
        manifest_path = hf_hub_download(
            _VOICEAGENTBENCH_REPO,
            f"data/{_SINGLE_TOOL_CATEGORY}_data/{language}/{_SINGLE_TOOL_CATEGORY}_{language}.json",
            repo_type="dataset",
            cache_dir=cache_dir_str,
        )
        raw_examples = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        for raw in raw_examples[:n_per_language]:
            audio_path = Path(
                hf_hub_download(
                    _VOICEAGENTBENCH_REPO,
                    raw["path"],
                    repo_type="dataset",
                    cache_dir=cache_dir_str,
                )
            )
            examples.append(
                VoiceAgentBenchExample(
                    id=raw["id"],
                    language=language,
                    query=raw["query"],
                    audio_path=audio_path,
                    functions=raw["functions"],
                    expected_tool_call=_parse_expected_tool_call(raw["expected_tool_call"]),
                )
            )
    return examples


@dataclass(frozen=True, slots=True)
class TranscriptExample:
    audio_chunks: Sequence[AudioChunk]
    ground_truth_text: str


def _pick_column(available: Sequence[str], candidates: Sequence[str], purpose: str) -> str:
    for candidate in candidates:
        if candidate in available:
            return candidate
    raise ValueError(
        f"none of {candidates!r} found as a {purpose} column; "
        f"real columns are {sorted(available)!r} -- update _TEXT_COLUMN_CANDIDATES "
        f"or _AUDIO_COLUMN_CANDIDATES in eval/datasets.py once you can see them"
    )


def _repo_parquet_files(repo_id: str) -> list[str]:
    all_files = list_repo_files(repo_id, repo_type="dataset")
    return sorted(f for f in all_files if f.endswith(".parquet"))


def _load_hf_audio_parquet_transcripts(repo_id: str, cache_dir: Path | None) -> list[str]:
    """Text-only pass: reads just the text column of every parquet shard,
    never materializing embedded audio bytes. This is deliberately the only
    thing the phase-2 section 2A entity-density gate needs -- "download the
    manifests only (no audio yet)."
    """
    cache_dir_str = str(cache_dir) if cache_dir is not None else None
    texts: list[str] = []
    for shard in _repo_parquet_files(repo_id):
        shard_path = hf_hub_download(repo_id, shard, repo_type="dataset", cache_dir=cache_dir_str)
        schema_names = pq.read_schema(shard_path).names
        text_column = _pick_column(schema_names, _TEXT_COLUMN_CANDIDATES, "text")
        table = pq.read_table(shard_path, columns=[text_column])
        texts.extend(str(v) for v in table[text_column].to_pylist())
    return texts


def _load_hf_audio_parquet_examples(
    repo_id: str, cache_dir: Path | None
) -> list[TranscriptExample]:
    cache_dir_str = str(cache_dir) if cache_dir is not None else None
    examples: list[TranscriptExample] = []
    for shard in _repo_parquet_files(repo_id):
        shard_path = hf_hub_download(repo_id, shard, repo_type="dataset", cache_dir=cache_dir_str)
        schema_names = pq.read_schema(shard_path).names
        text_column = _pick_column(schema_names, _TEXT_COLUMN_CANDIDATES, "text")
        audio_column = _pick_column(schema_names, _AUDIO_COLUMN_CANDIDATES, "audio")
        table = pq.read_table(shard_path, columns=[text_column, audio_column])
        for row in table.to_pylist():
            audio_value = row[audio_column]
            audio_bytes = audio_value["bytes"] if isinstance(audio_value, dict) else audio_value
            chunks = decode_audio_bytes_to_chunks(audio_bytes)
            examples.append(
                TranscriptExample(audio_chunks=chunks, ground_truth_text=str(row[text_column]))
            )
    return examples


def load_svarah_ground_truth_texts(cache_dir: Path | None = None) -> list[str]:
    """Ground-truth transcripts only, no audio -- for the entity-density
    gate (phase-2 spec section 2A)."""
    return _load_hf_audio_parquet_transcripts(_SVARAH_REPO, cache_dir)


def load_lahaja_ground_truth_texts(cache_dir: Path | None = None) -> list[str]:
    """Ground-truth transcripts only, no audio -- for the entity-density
    gate (phase-2 spec section 2A)."""
    return _load_hf_audio_parquet_transcripts(_LAHAJA_REPO, cache_dir)


def load_svarah(cache_dir: Path | None = None) -> list[TranscriptExample]:
    return _load_hf_audio_parquet_examples(_SVARAH_REPO, cache_dir)


def load_lahaja(cache_dir: Path | None = None) -> list[TranscriptExample]:
    return _load_hf_audio_parquet_examples(_LAHAJA_REPO, cache_dir)
