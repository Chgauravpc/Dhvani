"""Phase 3 -- run the real degradation sweep: WER and STT latency as a
function of channel impairment, against a bounded Svarah/LAHAJA sample.

    uv run python scripts/run_degradation_sweep.py --dataset svarah
    uv run python scripts/run_degradation_sweep.py --dataset svarah --stt sarvam
    uv run python scripts/run_degradation_sweep.py --dataset lahaja --n-examples 20

Needs Hugging Face access to the chosen dataset, same as
`scripts/run_f2_entity_eval.py` and `scripts/run_model_sweep.py`. Samples
via `eval.datasets.load_*_filtered` (the same streaming loader those two
scripts use), never the plain `load_svarah`/`load_lahaja`, for the same
memory-pressure reason phase-2 spec section 14 fixed. `--stt sarvam` needs
`SARVAM_API_KEY` -- see phase-2b spec section A.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random

from dhvani.audio.channel import default_sweep
from dhvani.clock import Clock, RealClock
from dhvani.config import load_dotenv
from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.eval.datasets import TranscriptExample, load_lahaja_filtered, load_svarah_filtered
from dhvani.eval.degradation import render_table, run_degradation_sweep
from dhvani.providers.base import STTProvider
from dhvani.providers.sarvam_stt import DEFAULT_MODEL as DEFAULT_SARVAM_MODEL
from dhvani.providers.sarvam_stt import SarvamSTT
from dhvani.providers.whisper_stt import WhisperSTT

_LOADERS = {"svarah": load_svarah_filtered, "lahaja": load_lahaja_filtered}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(_LOADERS), required=True)
    parser.add_argument("--stt", choices=["whisper", "sarvam"], default="whisper")
    parser.add_argument("--n-examples", type=int, default=30)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def _make_stt(stt_choice: str, clock: Clock) -> STTProvider:
    """Same choice `scripts/run_f2_entity_eval.py` makes -- only the inner
    ASR differs, nothing about the sweep's flow."""
    if stt_choice == "sarvam":
        return SarvamSTT(DEFAULT_SARVAM_MODEL, clock)
    whisper_model_size = os.environ.get("DHVANI_WHISPER_MODEL", "small")
    return WhisperSTT(whisper_model_size, clock)


def _bounded_sample(
    examples: list[TranscriptExample], n: int, seed: int
) -> list[TranscriptExample]:
    rng = random.Random(seed)
    if len(examples) <= n:
        return examples
    return rng.sample(examples, n)


async def main() -> None:
    args = _parse_args()
    load_dotenv()

    print(f"loading {args.dataset} (streamed, bounded pool)...")
    filtered = _LOADERS[args.dataset](DEFAULT_LEXICON, n_clean_sample=args.n_examples)
    pool = list(filtered.entity_bearing) + list(filtered.clean_sample)
    examples = _bounded_sample(pool, args.n_examples, args.seed)
    print(f"pooled {len(pool)} rows, sweeping a bounded sample of {len(examples)}")

    clock = RealClock()
    stt = _make_stt(args.stt, clock)
    configs = default_sweep()

    print(f"running degradation sweep [stt={stt.name}] over {len(configs)} channel configs...")
    points = await run_degradation_sweep(examples, configs, stt, clock)

    print()
    print(render_table(points))


if __name__ == "__main__":
    asyncio.run(main())
