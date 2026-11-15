"""3B-18 / 3B-20: transcribe the 290 test entity rows through the `pstn` phone leg.

    SARVAM_API_KEY=... uv run python scripts/run_f3_channel.py --stt sarvam
    uv run python scripts/run_f3_channel.py --stt groq-whisper     # free; 3B-20's pstn half

Protocol: `docs/runs/3b-18-preregistration.md`. Rows: the test-split entity rows of
both corpora (the ids of the committed 3B-4 logs). Each row is transcribed once
through `dhvani.eval.pstn.to_pstn`; transcripts go to
`results/transcripts/f3_<dataset>_<stt>_pstn.jsonl` with `condition="pstn"`. Resumable
(a logged row is never re-sent). Stops at the first provider error (HTTP 402 means
no credit left) and never scores a failed call.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from run_f2_entity_eval import _load, _make_stt

from dhvani.clock import RealClock
from dhvani.config import load_dotenv
from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.entity.mentions import mentioned_entities
from dhvani.eval.audio_io import iter_chunks
from dhvani.eval.pstn import to_pstn
from dhvani.eval.transcript_log import TranscriptLog, run_label, stt_model_label
from dhvani.providers.base import ProviderError
from dhvani.providers.sarvam_stt import DEFAULT_MODEL as DEFAULT_SARVAM_MODEL
from dhvani.telemetry.span import TurnTrace

DATASETS = ("svarah", "indicvoices-hindi")
CONDITION = "pstn"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stt", choices=["sarvam", "groq-whisper"], required=True)
    parser.add_argument("--max-rows", type=int, default=290)
    args = parser.parse_args()
    load_dotenv()
    clock = RealClock()
    sent = 0
    for dataset in DATASETS:
        loaded = argparse.Namespace(
            dataset=dataset, n_clean_sample=150, min_entity_rows=300, seed=0
        )
        _dev, test, _ = _load(loaded)
        rows = [
            e
            for e in test.entity_bearing
            if mentioned_entities(e.ground_truth_text, DEFAULT_LEXICON)
        ]
        stt = _make_stt(args.stt, clock, dataset)
        log = TranscriptLog(
            Path(f"results/transcripts/f3_{dataset}_{args.stt}_pstn.jsonl"),
            stt=stt.name,
            model=stt_model_label(args.stt, DEFAULT_SARVAM_MODEL),
            run=run_label("f3", dataset),
        )
        print(f"{dataset}: {len(rows)} rows", flush=True)
        try:
            for example in rows:
                if log.lookup(example.dataset, example.example_id, CONDITION) is not None:
                    continue
                if sent >= args.max_rows:
                    print("row cap reached", flush=True)
                    return 0
                trace = TurnTrace(clock)
                text = ""
                async for transcript in stt.stream(
                    iter_chunks(to_pstn(example.audio_chunks)), trace=trace
                ):
                    if transcript.is_final:
                        text = transcript.text
                log.record(
                    dataset=example.dataset,
                    example_id=example.example_id,
                    ground_truth_text=example.ground_truth_text,
                    raw_text=text,
                    split="test",
                    condition=CONDITION,
                )
                sent += 1
                if sent % 25 == 0:
                    print(f"{sent} rows sent", flush=True)
        except ProviderError as exc:
            print(f"stopped after {sent} rows: {exc}"[:300], flush=True)
            return 3
        finally:
            log.close()
    print(f"done: {sent} rows sent this invocation", flush=True)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    sys.exit(asyncio.run(main()))
