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
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download, list_repo_files

from dhvani.entity.lexicon import DomainLexicon
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


@dataclass(frozen=True, slots=True)
class FilteredExamples:
    """Result of `load_*_filtered`: the entity-bearing rows (all of them --
    the phase-2 spec section 2A gate already sized these in the hundreds,
    not the thousands) plus a bounded random sample of entity-free rows for
    the `corruption_rate` arm. Deliberately not "the whole dataset with
    audio decoded" -- Svarah and LAHAJA are each ~6,000+ rows, and decoding
    and transcribing all of them would turn a few-minute eval into a
    multi-hour one for no additional signal `compute_entity_error_rate`
    actually uses."""

    entity_bearing: list[TranscriptExample]
    clean_sample: list[TranscriptExample]


def _has_lexicon_mention(text: str, lexicon: DomainLexicon) -> bool:
    lowered = text.lower()
    return any(variant.lower() in lowered for _, _, variant in lexicon.all_variants())


_STREAM_BATCH_ROWS = 64


def _load_hf_audio_parquet_filtered(
    repo_id: str,
    lexicon: DomainLexicon,
    cache_dir: Path | None,
    n_clean_sample: int,
    seed: int,
) -> FilteredExamples:
    """Like `_load_hf_audio_parquet_examples`, but only decodes audio for
    rows that either mention a lexicon entity or land in a per-shard random
    sample of entity-free rows.

    Streams each shard in small batches via `ParquetFile.iter_batches`
    rather than `read_table` -- a real run against Svarah/LAHAJA (each
    ~6,000+ rows) was killed for memory pressure with the `read_table`
    version, which materializes every row's embedded audio bytes into a
    single in-memory table before any filtering happens. Streaming keeps at
    most `_STREAM_BATCH_ROWS` rows' audio in memory at once, and a batch
    with nothing wanted in it is dropped without ever touching its audio
    column.
    """
    cache_dir_str = str(cache_dir) if cache_dir is not None else None
    rng = random.Random(seed)
    entity_examples: list[TranscriptExample] = []
    clean_examples: list[TranscriptExample] = []

    shards = _repo_parquet_files(repo_id)
    per_shard_clean_quota = max(1, -(-n_clean_sample // len(shards))) if shards else 0

    for shard in shards:
        shard_path = hf_hub_download(repo_id, shard, repo_type="dataset", cache_dir=cache_dir_str)
        parquet_file = pq.ParquetFile(shard_path)
        schema_names = parquet_file.schema_arrow.names
        text_column = _pick_column(schema_names, _TEXT_COLUMN_CANDIDATES, "text")
        audio_column = _pick_column(schema_names, _AUDIO_COLUMN_CANDIDATES, "audio")

        # Pass 1: text only, to decide which row indices are wanted.
        texts: list[str] = []
        for batch in parquet_file.iter_batches(
            columns=[text_column], batch_size=_STREAM_BATCH_ROWS
        ):
            texts.extend(str(v) for v in batch.column(text_column).to_pylist())

        entity_row_indices = {
            i for i, text in enumerate(texts) if _has_lexicon_mention(text, lexicon)
        }
        clean_row_indices = [i for i in range(len(texts)) if i not in entity_row_indices]
        sampled_clean_indices = set(
            rng.sample(clean_row_indices, min(per_shard_clean_quota, len(clean_row_indices)))
        )
        wanted_indices = entity_row_indices | sampled_clean_indices
        if not wanted_indices:
            continue

        # Pass 2: text + audio, streamed in batches; only decode audio for
        # rows in `wanted_indices`, and only for the batch that has them.
        row_offset = 0
        for batch in parquet_file.iter_batches(
            columns=[text_column, audio_column], batch_size=_STREAM_BATCH_ROWS
        ):
            batch_len = batch.num_rows
            local_indices = [
                i - row_offset for i in wanted_indices if row_offset <= i < row_offset + batch_len
            ]
            if local_indices:
                for row in batch.take(local_indices).to_pylist():
                    text = str(row[text_column])
                    audio_value = row[audio_column]
                    audio_bytes = (
                        audio_value["bytes"] if isinstance(audio_value, dict) else audio_value
                    )
                    chunks = decode_audio_bytes_to_chunks(audio_bytes)
                    example = TranscriptExample(audio_chunks=chunks, ground_truth_text=text)
                    if _has_lexicon_mention(text, lexicon):
                        entity_examples.append(example)
                    else:
                        clean_examples.append(example)
            row_offset += batch_len

    return FilteredExamples(entity_bearing=entity_examples, clean_sample=clean_examples)


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


def load_svarah_filtered(
    lexicon: DomainLexicon,
    n_clean_sample: int = 150,
    seed: int = 0,
    cache_dir: Path | None = None,
) -> FilteredExamples:
    """Every entity-bearing Svarah row plus a bounded random sample of
    entity-free rows, with audio decoded only for those -- see
    `FilteredExamples`. What `compute_entity_error_rate` actually needs;
    `load_svarah` decodes all 6,656 rows and is not what a real eval run
    should use."""
    return _load_hf_audio_parquet_filtered(_SVARAH_REPO, lexicon, cache_dir, n_clean_sample, seed)


def load_lahaja_filtered(
    lexicon: DomainLexicon,
    n_clean_sample: int = 150,
    seed: int = 0,
    cache_dir: Path | None = None,
) -> FilteredExamples:
    """Same as `load_svarah_filtered`, for LAHAJA."""
    return _load_hf_audio_parquet_filtered(_LAHAJA_REPO, lexicon, cache_dir, n_clean_sample, seed)
