"""3B-5 -- F1 noise floor: k independent LLM runs per condition per example.

Protocol (preregistered, committed before this script existed):
`docs/specs/phase-3b.md` section 10. Read it before changing anything here.

    # 1. transcribe every example once per ASR (resumable, text cached by 3B-3)
    uv run python scripts/run_f1_noise_floor.py --phase asr
    # 2. LLM runs, interleaved run -> example -> condition (resumable; capped per
    #    invocation because Groq's free tier allows 1,000 requests/day)
    uv run python scripts/run_f1_noise_floor.py --phase llm
    # 3. does re-transcribing give identical text? (30 examples, Whisper)
    uv run python scripts/run_f1_noise_floor.py --phase determinism
    # 4. analysis from the committed run log
    uv run python scripts/analyze_f1_noise_floor.py

Exit code 3 means "daily quota exhausted, run again later" -- progress is
saved and nothing was mis-scored. Infrastructure errors (429, 5xx, timeouts)
are never scored as task failures (section 10.4).

Needs `GROQ_API_KEY`; `SARVAM_API_KEY` for the sarvam arm.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

from dhvani.clock import Clock, RealClock
from dhvani.config import load_dotenv
from dhvani.eval.audio_io import decode_audio_file_to_chunks, iter_chunks
from dhvani.eval.datasets import VoiceAgentBenchExample, load_voiceagentbench_subset
from dhvani.eval.noise_floor import (
    GT,
    FatalProviderError,
    QuotaExhausted,
    RunLog,
    RunRecord,
    call_llm_with_retries,
    now_utc,
)
from dhvani.eval.transcript_log import TranscriptLog, run_label, stt_model_label
from dhvani.providers.base import STTProvider
from dhvani.providers.groq_llm import DEFAULT_MODEL as GROQ_MODEL
from dhvani.providers.groq_llm import GroqLLM
from dhvani.providers.sarvam_stt import DEFAULT_MODEL as DEFAULT_SARVAM_MODEL
from dhvani.providers.sarvam_stt import SarvamSTT
from dhvani.providers.whisper_stt import WhisperSTT
from dhvani.telemetry.span import TurnTrace

DATASET = "voiceagentbench"
CONDITION = "real"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["asr", "llm", "determinism"], required=True)
    parser.add_argument("--arms", default="whisper,sarvam")
    parser.add_argument("--languages", default="english,hindi")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument(
        "--max-llm-calls",
        type=int,
        default=900,
        help="cap on LLM calls this invocation (Groq free tier: 1,000 requests/day)",
    )
    parser.add_argument(
        "--min-interval",
        type=float,
        default=8.0,
        help="seconds between LLM calls (Groq free tier: 8,000 tokens/minute)",
    )
    parser.add_argument("--runs", type=Path, default=Path("results/f1_runs/runs.jsonl"))
    return parser.parse_args()


def _make_stt(arm: str, clock: Clock) -> STTProvider:
    if arm == "sarvam":
        return SarvamSTT(DEFAULT_SARVAM_MODEL, clock)
    return WhisperSTT(os.environ.get("DHVANI_WHISPER_MODEL", "small"), clock)


def _stt_name(arm: str) -> str:
    return "sarvam" if arm == "sarvam" else "faster-whisper"


def _transcript_log(arm: str) -> TranscriptLog:
    return TranscriptLog(
        Path(f"results/transcripts/f1_noise_floor_{arm}.jsonl"),
        stt=_stt_name(arm),
        model=stt_model_label(arm, DEFAULT_SARVAM_MODEL),
        run=run_label("f1-noise-floor", DATASET),
    )


def _eid(example: VoiceAgentBenchExample) -> str:
    """Ids repeat across languages (133 of them do) -- always qualify."""
    return f"{example.language}:{example.id}"


async def _transcribe(example: VoiceAgentBenchExample, stt: STTProvider, clock: Clock) -> str:
    chunks = decode_audio_file_to_chunks(example.audio_path)
    heard = ""
    async for transcript in stt.stream(iter_chunks(chunks), trace=TurnTrace(clock)):
        if transcript.is_final:
            heard = transcript.text
    return heard


async def _phase_asr(args: argparse.Namespace, examples: list[VoiceAgentBenchExample]) -> None:
    clock = RealClock()
    for arm in [a.strip() for a in args.arms.split(",") if a.strip()]:
        log = _transcript_log(arm)
        todo = [e for e in examples if log.lookup(DATASET, _eid(e), CONDITION) is None]
        print(f"[{arm}] {len(examples) - len(todo)} cached, {len(todo)} to transcribe", flush=True)
        if not todo:
            log.close()
            continue
        stt = _make_stt(arm, clock)
        try:
            for n, example in enumerate(todo, start=1):
                text = await _transcribe(example, stt, clock)
                log.record(
                    dataset=DATASET,
                    example_id=_eid(example),
                    ground_truth_text=example.query,
                    raw_text=text,
                    split=example.language,
                    condition=CONDITION,
                )
                if n % 20 == 0:
                    print(f"[{arm}] {n}/{len(todo)}", flush=True)
        finally:
            log.close()


async def _phase_llm(args: argparse.Namespace, examples: list[VoiceAgentBenchExample]) -> int:
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    conditions = [GT, *arms]
    logs = {arm: _transcript_log(arm) for arm in arms}
    runs = RunLog(args.runs)
    clock = RealClock()
    # `GROQ_API_KEYS` (comma-separated) spreads calls across keys, each with its
    # own throttle, moving on when one hits its daily quota. Quotas are per
    # Groq account, so this only helps with keys from separate accounts. Keys
    # are never logged or written anywhere.
    keys = [k.strip() for k in os.environ.get("GROQ_API_KEYS", "").split(",") if k.strip()]
    if not keys:
        keys = [os.environ["GROQ_API_KEY"]]
    llms = [GroqLLM(clock, api_key=k) for k in keys]
    alive = list(range(len(llms)))
    last_call = [0.0] * len(llms)
    turn = 0
    print(f"using {len(llms)} Groq key(s)", flush=True)
    by_language: dict[str, int] = {}
    indices: dict[str, int] = {}
    for example in examples:
        indices[_eid(example)] = by_language.get(example.language, 0)
        by_language[example.language] = indices[_eid(example)] + 1

    calls = 0
    try:
        for run in range(1, args.k + 1):
            for example in examples:
                for condition in conditions:
                    if runs.done(example.language, example.id, condition, run):
                        continue
                    if condition == GT:
                        text: str | None = example.query
                    else:
                        text = logs[condition].lookup(DATASET, _eid(example), CONDITION)
                    if text is None:
                        continue  # transcript missing: stays an incomplete cell
                    base = dict(
                        example_id=example.id,
                        language=example.language,
                        index=indices[_eid(example)],
                        condition=condition,
                        run=run,
                        model=GROQ_MODEL,
                        ts=now_utc(),
                    )
                    if not text.strip():
                        # An ASR that produced nothing cannot fill a tool call; this
                        # is the same outcome the Phase 2 harness reached, without
                        # spending a request on it.
                        runs.append(
                            RunRecord(
                                **base, outcome="fail", tool_call=None, error_class="empty_text"
                            )
                        )
                        continue
                    if calls >= args.max_llm_calls:
                        print(f"call cap reached ({calls}); run again later", flush=True)
                        return 0
                    while True:
                        if not alive:
                            raise QuotaExhausted("every Groq key has hit its daily quota")
                        key_index = alive[turn % len(alive)]
                        turn += 1
                        wait = args.min_interval - (time.monotonic() - last_call[key_index])
                        if wait > 0:
                            await asyncio.sleep(wait)
                        last_call[key_index] = time.monotonic()
                        try:
                            attempt = await call_llm_with_retries(
                                llms[key_index], example, text, clock
                            )
                            break
                        except QuotaExhausted:
                            alive.remove(key_index)
                            print(f"key #{key_index + 1} quota exhausted", flush=True)
                    calls += 1
                    call = (
                        None
                        if attempt.tool_call is None
                        else {
                            "name": attempt.tool_call.name,
                            "arguments": dict(attempt.tool_call.arguments),
                        }
                    )
                    runs.append(
                        RunRecord(
                            **base,
                            outcome=attempt.outcome,
                            tool_call=call,
                            error_class=attempt.error_class,
                        )
                    )
                    if calls % 25 == 0:
                        print(f"{calls} calls this invocation (run {run})", flush=True)
    except QuotaExhausted as exc:
        print(f"quota exhausted after {calls} calls: {exc}", flush=True)
        return 3
    finally:
        runs.close()
        for log in logs.values():
            log.close()
    print(f"all scheduled cells done ({calls} calls this invocation)", flush=True)
    return 0


async def _phase_determinism(examples: list[VoiceAgentBenchExample]) -> None:
    clock = RealClock()
    log = _transcript_log("whisper")
    rng = random.Random(0)
    sample = rng.sample(examples, 30)
    stt = _make_stt("whisper", clock)
    rows = []
    for example in sample:
        first = log.lookup(DATASET, _eid(example), CONDITION)
        if first is None:
            raise SystemExit(f"{_eid(example)} not transcribed yet -- run --phase asr first")
        second = await _transcribe(example, stt, clock)
        rows.append({"example_id": _eid(example), "identical": first == second})
    log.close()
    identical = sum(r["identical"] for r in rows)
    out = {
        "item": "3B-5",
        "check": "whisper small/int8 re-transcription, 30 examples, seed 0",
        "n": len(rows),
        "n_identical": identical,
        "fraction_identical": identical / len(rows),
        "rows": rows,
    }
    path = Path("results/f1_whisper_determinism.json")
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"{identical}/{len(rows)} byte-identical -> {path}")


async def main() -> int:
    args = _parse_args()
    load_dotenv()
    languages = [x.strip() for x in args.languages.split(",") if x.strip()]
    examples = load_voiceagentbench_subset(languages, n_per_language=10_000)
    print(f"loaded {len(examples)} examples: {languages}", flush=True)
    if args.phase == "asr":
        await _phase_asr(args, examples)
        return 0
    if args.phase == "determinism":
        await _phase_determinism(examples)
        return 0
    if not os.environ.get("GROQ_API_KEY"):
        raise SystemExit("GROQ_API_KEY is not set")
    try:
        return await _phase_llm(args, examples)
    except FatalProviderError as exc:
        print(f"FATAL (not scored): {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
