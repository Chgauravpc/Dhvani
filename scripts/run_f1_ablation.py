"""F1 -- run the ASR-ablation harness against real VoiceAgentBench examples.

    uv run python scripts/run_f1_ablation.py [--languages english,hindi] [--n-per-language 40]
    uv run python scripts/run_f1_ablation.py --with-corrected-stt   # ties F1 and F2 together
    uv run python scripts/run_f1_ablation.py --stt sarvam           # phase-2b: Indic ASR baseline

Needs `GROQ_API_KEY` (via `.env` or the environment, same as `dhvani.live`).
`--stt whisper` (default) downloads faster-whisper's model on first run; set
`DHVANI_WHISPER_MODEL` (default `small`) the same way `dhvani.live` does.
`--stt sarvam` needs `SARVAM_API_KEY` -- see phase-2b spec section A. Per
that spec, only the inner ASR changes; nothing else about this script does.

`--with-corrected-stt` adds a third condition, `CorrectedSTT` wrapping
`WhisperSTT`, so this measures whether `dhvani-entity` changes any real
VoiceAgentBench tool-call outcome -- not just whether it improves Entity
Error Rate in isolation (`scripts/run_f2_entity_eval.py`, which is what
that flag was missing before). Set expectations honestly first:
VoiceAgentBench's `single_tool` category is restaurants/recipes/local-
search queries, not the civic/government/finance domain `DEFAULT_LEXICON`
covers, so most examples are expected to show no lexicon mention at all --
a near-zero delta here would say "these two corpora don't overlap much,"
not "dhvani-entity doesn't work" (see the real Svarah/LAHAJA EER numbers,
`docs/specs/phase-2.md` sections 14-15, for that). Uses
`EntityCorrector`'s default threshold (0.82) -- no VoiceAgentBench-
specific dev/test tuning exists, unlike Svarah/LAHAJA's own sweeps, so
this isn't presented as a tuned number.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from dhvani.clock import Clock, RealClock
from dhvani.config import load_dotenv
from dhvani.entity.corrector import EntityCorrector
from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.eval.datasets import load_voiceagentbench_subset
from dhvani.eval.task_success import run_ablation
from dhvani.providers.base import STTProvider
from dhvani.providers.corrected_stt import CorrectedSTT
from dhvani.providers.groq_llm import GroqLLM
from dhvani.providers.sarvam_stt import DEFAULT_MODEL as DEFAULT_SARVAM_MODEL
from dhvani.providers.sarvam_stt import SarvamSTT
from dhvani.providers.whisper_stt import WhisperSTT


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", default="english,hindi")
    parser.add_argument("--n-per-language", type=int, default=40)
    parser.add_argument("--with-corrected-stt", action="store_true")
    parser.add_argument("--stt", choices=["whisper", "sarvam"], default="whisper")
    return parser.parse_args()


def _make_stt(stt_choice: str, clock: Clock) -> STTProvider:
    """The one thing phase-2b spec section A changes about this script --
    same ablation logic, only the inner ASR differs."""
    if stt_choice == "sarvam":
        return SarvamSTT(DEFAULT_SARVAM_MODEL, clock)
    whisper_model_size = os.environ.get("DHVANI_WHISPER_MODEL", "small")
    return WhisperSTT(whisper_model_size, clock)


async def main() -> None:
    args = _parse_args()
    load_dotenv()
    if not os.environ.get("GROQ_API_KEY"):
        raise SystemExit("GROQ_API_KEY is not set -- see README.md's live-demo setup.")

    languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    print(f"loading {args.n_per_language} single_tool examples per language: {languages}...")
    examples = load_voiceagentbench_subset(languages, n_per_language=args.n_per_language)
    print(f"loaded {len(examples)} examples total")

    if args.with_corrected_stt:
        n_mentioning = sum(
            1
            for e in examples
            if any(v.lower() in e.query.lower() for _, _, v in DEFAULT_LEXICON.all_variants())
        )
        print(
            f"{n_mentioning}/{len(examples)} example queries mention a lexicon entity at all "
            "-- expect most of the delta (if any) to come from just these."
        )

    clock = RealClock()
    llm = GroqLLM(clock)

    make_corrected_stt = None
    if args.with_corrected_stt:

        def make_corrected_stt() -> CorrectedSTT:
            return CorrectedSTT(_make_stt(args.stt, clock), EntityCorrector(DEFAULT_LEXICON))

    report = await run_ablation(
        examples,
        make_real_stt=lambda: _make_stt(args.stt, clock),
        llm=llm,
        clock=clock,
        make_corrected_stt=make_corrected_stt,
    )

    print()
    print("Note: VoiceAgentBench audio is synthesized (TTS over text queries),")
    print("so this measures a LOWER BOUND on the real-world ASR penalty, not an")
    print("estimate of it -- see docs/specs/phase-2.md section 2.")
    print()
    print(f"stt={args.stt}")
    header = f"{'language':<10}{'n':>5}{'ground_truth':>15}{'real_asr':>12}{'loss':>10}"
    if args.with_corrected_stt:
        header += f"{'corrected_asr':>16}{'recovered':>12}"
    print(header)
    print("-" * len(header))
    for language, result in report.per_language.items():
        loss = result.success_rate_ground_truth - result.success_rate_real_asr
        row = (
            f"{language:<10}{result.n:>5}{result.success_rate_ground_truth:>15.1%}"
            f"{result.success_rate_real_asr:>12.1%}{loss:>10.1%}"
        )
        if args.with_corrected_stt and result.success_rate_corrected_asr is not None:
            recovered = result.success_rate_corrected_asr - result.success_rate_real_asr
            row += f"{result.success_rate_corrected_asr:>16.1%}{recovered:>12.1%}"
        print(row)


if __name__ == "__main__":
    asyncio.run(main())
