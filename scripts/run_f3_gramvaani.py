"""3B-21: transcribe the committed Gram Vaani sample (real telephone Hindi).

    uv run python scripts/run_f3_gramvaani.py --stt groq-whisper         # free
    SARVAM_API_KEY=... uv run python scripts/run_f3_gramvaani.py --stt sarvam   # about Rs 17.5

Protocol: `docs/runs/3b-21-preregistration.md`. The sample is `results/gramvaani_sample.json`;
audio is read from the extracted `GV_Dev_5h` folder, decoded to 16 kHz mono, and sent as WAV.
Hypotheses go to `results/transcripts/f3_gramvaani_<stt>.jsonl` (utterance id, model, text;
**no reference text**: those are Gram Vaani's and are re-read from the archive). Resumable;
stops at the first provider error (HTTP 402 = no credit left).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from run_f2_entity_eval import _make_stt

from dhvani.clock import RealClock
from dhvani.config import load_dotenv
from dhvani.eval.audio_io import decode_audio_file_to_chunks, iter_chunks
from dhvani.eval.transcript_log import stt_model_label
from dhvani.providers.base import ProviderError
from dhvani.providers.sarvam_stt import DEFAULT_MODEL as DEFAULT_SARVAM_MODEL
from dhvani.telemetry.span import TurnTrace

DATA_DIR = Path("D:/Desktop/Projects/Dhvani_data/gramvaani_dev/GV_Dev_5h")


def _done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        json.loads(line)["uttid"] for line in path.read_text(encoding="utf-8").splitlines() if line
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stt", choices=["sarvam", "groq-whisper"], required=True)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    load_dotenv()
    clock = RealClock()
    stt = _make_stt(args.stt, clock, "indicvoices-hindi")  # language forced to hi for Groq
    model = stt_model_label(args.stt, DEFAULT_SARVAM_MODEL)
    sample = json.loads(Path("results/gramvaani_sample.json").read_text(encoding="utf-8"))["items"]
    out_path = Path(f"results/transcripts/f3_gramvaani_{args.stt}.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = _done(out_path)
    sent = 0
    with out_path.open("a", encoding="utf-8") as out:
        for item in sample:
            uttid = item["uttid"]
            if uttid in done:
                continue
            chunks = decode_audio_file_to_chunks(args.data_dir / "Audio" / f"{uttid}.mp3", 16_000)
            text = ""
            try:
                async for transcript in stt.stream(iter_chunks(chunks), trace=TurnTrace(clock)):
                    if transcript.is_final:
                        text = transcript.text
            except ProviderError as exc:
                if "exceeds the maximum limit of 30 seconds" in str(exc):
                    # Deviation 1 (prereg section 8): the decoded clip is over the API's
                    # 30 s limit although its container duration was under 29.5 s. Logged
                    # as rejected (no text), skipped, and excluded from every arm's score.
                    text = ""
                    rejected = "audio_over_30s"
                else:
                    print(f"stopped after {sent} utterances: {exc}"[:300], flush=True)
                    return 3
            else:
                rejected = ""
            out.write(
                json.dumps(
                    {
                        "uttid": uttid,
                        "stt": stt.name,
                        "model": model,
                        "raw_text": None if rejected else text,
                        "rejected": rejected,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            out.flush()
            sent += 1
            if sent % 25 == 0:
                print(f"{sent} utterances", flush=True)
    print(f"done: {sent} utterances sent this invocation", flush=True)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    sys.exit(asyncio.run(main()))
