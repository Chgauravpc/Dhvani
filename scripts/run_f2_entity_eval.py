"""F2 -- the real entity-error-rate eval (phase-3b 3B-4 protocol).

    uv run python scripts/run_f2_entity_eval.py --dataset svarah --stt whisper
    uv run python scripts/run_f2_entity_eval.py --dataset indicvoices-hindi --stt sarvam

The protocol is preregistered in `docs/specs/phase-3b.md` (3B-4) and must
not change between that commit and the runs it governs.

Datasets (both gated on Hugging Face -- `HF_TOKEN` in `.env`):

- `svarah`: every entity-bearing row (word-bounded, lexicon v2) plus
  `--n-clean-sample` entity-free rows; dev/test split 30/70 at random by row
  (`--seed`), the Phase 2 protocol.
- `indicvoices-hindi`: cluster sample by shard
  (`eval.datasets.select_indicvoices_eval_rows`): shards drawn in seeded
  order until >= `--min-entity-rows` entity rows, all of them used, plus
  `--n-clean-sample` entity-free rows from the same shards. Dev/test split
  by **speaker** (a speaker is dev iff sha256(speaker_id) mod 100 < 30), so
  no voice the threshold was tuned on is reported on. Replaces LAHAJA,
  whose gate failed (3B-1). LAHAJA is not run.

`--stt whisper` uses faster-whisper `DHVANI_WHISPER_MODEL` (default `small`,
int8, the Phase 2 setting); `--stt sarvam` uses Saaras (`SARVAM_API_KEY`).
Only the inner ASR changes between arms.

Scoring (3B-2): recognition EER and canonical miss rate, before and after
correction, each with a 95% Wilson CI and an exact two-sided McNemar test
on the paired per-mention outcomes, always beside `corruption_rate` on the
clean arm. The correction threshold is chosen on dev by minimising
`canonical_miss_after + corruption_rate` (ties -> higher threshold), then
test is scored once at that threshold. Every transcript goes to the 3B-3
log; results go to `--out` (default `results/f2_eer_<dataset>_<stt>.json`).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dhvani.clock import Clock, RealClock
from dhvani.config import load_dotenv
from dhvani.entity.corrector import EntityCorrector
from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.eval.datasets import (
    FilteredExamples,
    TranscriptExample,
    load_indicvoices_examples,
    load_indicvoices_text_rows,
    load_svarah_filtered,
    select_indicvoices_eval_rows,
)
from dhvani.eval.entity_error_rate import (
    EerReport,
    TranscribedExample,
    score_transcripts,
    transcribe_examples,
)
from dhvani.eval.stats import mcnemar_exact_p, wilson_interval
from dhvani.eval.transcript_log import (
    TranscriptLog,
    default_log_path,
    run_label,
    stt_model_label,
)
from dhvani.providers.base import STTProvider
from dhvani.providers.sarvam_stt import DEFAULT_MODEL as DEFAULT_SARVAM_MODEL
from dhvani.providers.sarvam_stt import SarvamSTT
from dhvani.providers.whisper_stt import WhisperSTT

_DATASETS = ("svarah", "indicvoices-hindi")
_THRESHOLD_GRID = (0.70, 0.75, 0.80, 0.82, 0.85, 0.90, 0.95)
_DEV_FRACTION = 0.3


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=_DATASETS, required=True)
    parser.add_argument("--stt", choices=["whisper", "sarvam"], default="whisper")
    parser.add_argument("--n-clean-sample", type=int, default=150)
    parser.add_argument("--min-entity-rows", type=int, default=300)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--transcripts", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def _make_stt(stt_choice: str, clock: Clock) -> STTProvider:
    if stt_choice == "sarvam":
        return SarvamSTT(DEFAULT_SARVAM_MODEL, clock)
    whisper_model_size = os.environ.get("DHVANI_WHISPER_MODEL", "small")
    return WhisperSTT(
        whisper_model_size,
        clock,
        cpu_threads=int(os.environ.get("DHVANI_WHISPER_CPU_THREADS", "0")),
    )


def _split_by_row(
    filtered: FilteredExamples, seed: int
) -> tuple[FilteredExamples, FilteredExamples]:
    rng = random.Random(seed)
    entity = list(filtered.entity_bearing)
    clean = list(filtered.clean_sample)
    rng.shuffle(entity)
    rng.shuffle(clean)
    entity_split = round(len(entity) * _DEV_FRACTION)
    clean_split = round(len(clean) * _DEV_FRACTION)
    dev = FilteredExamples(entity_bearing=entity[:entity_split], clean_sample=clean[:clean_split])
    test = FilteredExamples(entity_bearing=entity[entity_split:], clean_sample=clean[clean_split:])
    return dev, test


def is_dev_speaker(speaker_id: str) -> bool:
    """Deterministic, seed-free speaker assignment: ~30% of speakers to dev."""
    digest = hashlib.sha256(speaker_id.encode("utf-8")).hexdigest()
    return int(digest, 16) % 100 < round(_DEV_FRACTION * 100)


def _split_by_speaker(
    filtered: FilteredExamples,
) -> tuple[FilteredExamples, FilteredExamples]:
    def part(examples: list[TranscriptExample], dev: bool) -> list[TranscriptExample]:
        return [e for e in examples if is_dev_speaker(e.speaker_id) == dev]

    dev = FilteredExamples(
        entity_bearing=part(filtered.entity_bearing, True),
        clean_sample=part(filtered.clean_sample, True),
    )
    test = FilteredExamples(
        entity_bearing=part(filtered.entity_bearing, False),
        clean_sample=part(filtered.clean_sample, False),
    )
    return dev, test


def _load(args: argparse.Namespace) -> tuple[FilteredExamples, FilteredExamples, dict[str, Any]]:
    if args.dataset == "svarah":
        filtered = load_svarah_filtered(DEFAULT_LEXICON, n_clean_sample=args.n_clean_sample)
        dev, test = _split_by_row(filtered, seed=args.seed)
        return dev, test, {"split_unit": "row", "sampling": "all entity rows"}

    selection = select_indicvoices_eval_rows(
        load_indicvoices_text_rows("hindi"),
        DEFAULT_LEXICON,
        min_entity_rows=args.min_entity_rows,
        n_clean=args.n_clean_sample,
        seed=args.seed,
    )
    print(f"drew {len(selection.shards)} shards: {selection.shards}")
    entity = load_indicvoices_examples(selection.entity_rows)
    clean = load_indicvoices_examples(selection.clean_rows)
    dev, test = _split_by_speaker(FilteredExamples(entity_bearing=entity, clean_sample=clean))
    speakers = {e.speaker_id for e in entity + clean}
    dev_speakers = {s for s in speakers if is_dev_speaker(s)}
    meta = {
        "split_unit": "speaker",
        "sampling": "cluster sample by shard",
        "shards": selection.shards,
        "n_speakers": len(speakers),
        "n_dev_speakers": len(dev_speakers),
    }
    return dev, test, meta


def _summarise(report: EerReport) -> dict[str, Any]:
    n = report.n_entity_mentions

    def rate(value: float, denom: int) -> dict[str, Any]:
        lo, hi = wilson_interval(round(value * denom), denom)
        return {"rate": value, "ci95": [lo, hi]}

    return {
        **asdict(report),
        "recognition_eer_before_ci": rate(report.recognition_eer_before, n)["ci95"],
        "recognition_eer_after_ci": rate(report.recognition_eer_after, n)["ci95"],
        "canonical_miss_before_ci": rate(report.canonical_miss_before, n)["ci95"],
        "canonical_miss_after_ci": rate(report.canonical_miss_after, n)["ci95"],
        "corruption_rate_ci": rate(report.corruption_rate, report.n_clean_examples)["ci95"],
        "recognition_mcnemar_p": mcnemar_exact_p(
            report.recognition_fixed, report.recognition_broken
        ),
        "canonical_mcnemar_p": mcnemar_exact_p(report.canonical_fixed, report.canonical_broken),
    }


def _print_report(label: str, report: EerReport) -> None:
    s = _summarise(report)
    print(
        f"{label}: thr={report.threshold} n={report.n_entity_mentions} | "
        f"recog {report.recognition_eer_before:.1%} -> {report.recognition_eer_after:.1%} "
        f"(+{report.recognition_fixed}/-{report.recognition_broken}, "
        f"p={s['recognition_mcnemar_p']:.3g}) | "
        f"canon {report.canonical_miss_before:.1%} -> {report.canonical_miss_after:.1%} "
        f"(+{report.canonical_fixed}/-{report.canonical_broken}, "
        f"p={s['canonical_mcnemar_p']:.3g}) | "
        f"corrupt {report.corruption_rate:.1%} of {report.n_clean_examples}"
    )


def _sweep_dev(dev_transcribed: list[TranscribedExample]) -> tuple[float, list[EerReport]]:
    print("\nsweeping threshold on dev...")
    best_threshold = _THRESHOLD_GRID[0]
    best_cost = float("inf")
    reports: list[EerReport] = []
    for threshold in _THRESHOLD_GRID:
        corrector = EntityCorrector(DEFAULT_LEXICON, threshold=threshold)
        report = score_transcripts(dev_transcribed, DEFAULT_LEXICON, corrector, split="dev")
        reports.append(report)
        _print_report("  dev", report)
        cost = report.canonical_miss_after + report.corruption_rate
        if cost <= best_cost:  # <= : ties prefer the later (higher) threshold
            best_cost = cost
            best_threshold = threshold
    print(f"chosen threshold: {best_threshold} (min canonical_miss_after + corruption_rate)")
    return best_threshold, reports


async def main() -> None:
    args = _parse_args()
    load_dotenv()

    dev, test, sampling = _load(args)
    print(
        f"dev: {len(dev.entity_bearing)} entity-bearing, {len(dev.clean_sample)} clean | "
        f"test: {len(test.entity_bearing)} entity-bearing, {len(test.clean_sample)} clean"
    )

    clock = RealClock()
    stt = _make_stt(args.stt, clock)
    model = stt_model_label(args.stt, DEFAULT_SARVAM_MODEL)
    log = TranscriptLog(
        args.transcripts or default_log_path("f2", args.dataset, args.stt),
        stt=stt.name,
        model=model,
        run=run_label("f2", args.dataset),
    )
    print(f"transcript log: {log.path}")

    print("\ntranscribing dev split (once)...")
    dev_transcribed = await transcribe_examples(
        list(dev.entity_bearing) + list(dev.clean_sample), stt, clock, log=log, split="dev"
    )
    chosen_threshold, dev_reports = _sweep_dev(dev_transcribed)

    print("\ntranscribing test split (once)...")
    test_transcribed = await transcribe_examples(
        list(test.entity_bearing) + list(test.clean_sample), stt, clock, log=log, split="test"
    )
    log.close()
    test_report = score_transcripts(
        test_transcribed,
        DEFAULT_LEXICON,
        EntityCorrector(DEFAULT_LEXICON, threshold=chosen_threshold),
        split="test",
    )

    print(f"\n--- final (test split, single run at the dev-chosen threshold) [stt={stt.name}] ---")
    _print_report("test", test_report)

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    out = args.out or Path(f"results/f2_eer_{args.dataset}_{args.stt}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "item": "3B-4",
        "code_commit": commit,
        "dataset": args.dataset,
        "stt": stt.name,
        "model": model,
        "seed": args.seed,
        "sampling": sampling,
        "n_dev": {"entity": len(dev.entity_bearing), "clean": len(dev.clean_sample)},
        "n_test": {"entity": len(test.entity_bearing), "clean": len(test.clean_sample)},
        "transcript_log": str(log.path).replace("\\", "/"),
        "threshold_objective": "min dev canonical_miss_after + corruption_rate; ties -> higher",
        "dev_sweep": [_summarise(r) for r in dev_reports],
        "chosen_threshold": chosen_threshold,
        "test": _summarise(test_report),
    }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
