"""F1 -- run the ASR-ablation harness against real VoiceAgentBench examples.

    uv run python scripts/run_f1_ablation.py [--languages english,hindi] [--n-per-language 40]

Needs `GROQ_API_KEY` (via `.env` or the environment, same as `dhvani.live`).
Downloads faster-whisper's model on first run; set `DHVANI_WHISPER_MODEL`
(default `small`) the same way `dhvani.live` does.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from dhvani.clock import RealClock
from dhvani.config import load_dotenv
from dhvani.eval.datasets import load_voiceagentbench_subset
from dhvani.eval.task_success import run_ablation
from dhvani.providers.groq_llm import GroqLLM
from dhvani.providers.whisper_stt import WhisperSTT


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", default="english,hindi")
    parser.add_argument("--n-per-language", type=int, default=40)
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    load_dotenv()
    if not os.environ.get("GROQ_API_KEY"):
        raise SystemExit("GROQ_API_KEY is not set -- see README.md's live-demo setup.")

    languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    print(f"loading {args.n_per_language} single_tool examples per language: {languages}...")
    examples = load_voiceagentbench_subset(languages, n_per_language=args.n_per_language)
    print(f"loaded {len(examples)} examples total")

    clock = RealClock()
    whisper_model_size = os.environ.get("DHVANI_WHISPER_MODEL", "small")
    llm = GroqLLM(clock)

    report = await run_ablation(
        examples,
        make_real_stt=lambda: WhisperSTT(whisper_model_size, clock),
        llm=llm,
        clock=clock,
    )

    print()
    print("Note: VoiceAgentBench audio is synthesized (TTS over text queries),")
    print("so this measures a LOWER BOUND on the real-world ASR penalty, not an")
    print("estimate of it -- see docs/specs/phase-2.md section 2.")
    print()
    header = f"{'language':<10}{'n':>5}{'ground_truth':>15}{'real_asr':>12}{'loss':>10}"
    print(header)
    print("-" * len(header))
    for language, result in report.per_language.items():
        loss = result.success_rate_ground_truth - result.success_rate_real_asr
        print(
            f"{language:<10}{result.n:>5}{result.success_rate_ground_truth:>15.1%}"
            f"{result.success_rate_real_asr:>12.1%}{loss:>10.1%}"
        )


if __name__ == "__main__":
    asyncio.run(main())
