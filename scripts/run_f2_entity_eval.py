"""F2 -- run the entity-error-rate eval against real Svarah or LAHAJA data.

    uv run python scripts/run_f2_entity_eval.py --dataset svarah --split dev --threshold 0.82
    uv run python scripts/run_f2_entity_eval.py --dataset lahaja --split test --threshold 0.82

Needs Hugging Face access to the chosen dataset (both are gated) -- see
`scripts/entity_density_gate.py`'s docstring for how to set that up, and
run that gate first (phase-2 spec section 2A: it's a go/no-go check, not
optional). Downloads faster-whisper's model on first run; set
`DHVANI_WHISPER_MODEL` (default `small`) the same way `dhvani.live` does.

Tune the threshold on `--split dev`, then report the number a single
`--split test` run at the chosen threshold produces -- re-running test to
pick a better-looking threshold turns the result into a fit (spec section
6.7).
"""

from __future__ import annotations

import argparse
import asyncio
import os

from dhvani.clock import RealClock
from dhvani.config import load_dotenv
from dhvani.entity.corrector import EntityCorrector
from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.eval.datasets import load_lahaja, load_svarah
from dhvani.eval.entity_error_rate import compute_entity_error_rate
from dhvani.providers.whisper_stt import WhisperSTT

_LOADERS = {"svarah": load_svarah, "lahaja": load_lahaja}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(_LOADERS), required=True)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--threshold", type=float, default=0.82)
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    load_dotenv()

    print(f"loading {args.dataset} (this needs Hugging Face access to the dataset)...")
    examples = _LOADERS[args.dataset]()
    print(f"loaded {len(examples)} examples")

    clock = RealClock()
    whisper_model_size = os.environ.get("DHVANI_WHISPER_MODEL", "small")
    stt = WhisperSTT(whisper_model_size, clock)
    corrector = EntityCorrector(DEFAULT_LEXICON, threshold=args.threshold)

    report = await compute_entity_error_rate(
        examples, DEFAULT_LEXICON, stt, corrector, clock, split=args.split
    )

    print()
    print(f"split={report.split} threshold={report.threshold}")
    print(f"n_entity_mentions={report.n_entity_mentions}")
    print(f"eer_before={report.eer_before:.1%}  eer_after={report.eer_after:.1%}")
    print(
        f"n_clean_examples={report.n_clean_examples}  corruption_rate={report.corruption_rate:.1%}"
    )


if __name__ == "__main__":
    asyncio.run(main())
