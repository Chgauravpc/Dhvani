"""3B-9 pre-flight (plan R2): exercise Sarvam's realtime streaming endpoint once.

    SARVAM_API_KEY=... uv run python scripts/preflight_3b9.py    # -> results/preflight_3b-9.json

Streams one short telephone clip (8 kHz mu-law, real time) and records the resolved session
config and every event with its time, so the realtime provider is built on observed behaviour,
not documentation. Costs about one clip of credit (under Rs 0.1). Also sizes the 50-utterance
set (audio minutes and cost at the plan's Rs 30/hour) and records the machine fit.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from run_latency import DATA_DIR, MAX_CLIP_S

from dhvani.eval.audio_io import decode_audio_file_to_chunks
from dhvani.eval.pstn import to_pstn

PLAN_RATE_RS_PER_HOUR = 30.0


async def probe(pcm8: bytes) -> dict[str, Any]:
    import base64

    from sarvamai import AsyncSarvamAI
    from sarvamai.types.realtime_audio_input import RealtimeAudioInput

    from dhvani.audio import mulaw

    ulaw = mulaw.encode(pcm8)
    client = AsyncSarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"])
    events: list[dict[str, Any]] = []
    config: Any = None
    t0 = time.monotonic()
    async with client.speech_to_text_realtime_streaming.connect(
        language_code="hi-IN",
        encoding="mulaw",
        sample_rate="8000",
        endpointing="vad",
        silence_duration_ms="500",
    ) as sock:

        async def send() -> None:
            step = 160  # 20 ms of 8 kHz mu-law
            n = 0
            while n * step < len(ulaw) + 8000 * 3:
                seg = ulaw[n * step : (n + 1) * step] or b"\xff" * step  # 0xff: mu-law silence
                await sock.send_realtime_audio_input(
                    RealtimeAudioInput(audio=base64.b64encode(seg).decode("ascii"))
                )
                n += 1
                await asyncio.sleep(max(0.0, t0 + n * 0.02 - time.monotonic()))

        task = asyncio.create_task(send())
        try:
            async with asyncio.timeout(30):
                async for message in sock:
                    name = str(getattr(message, "event", type(message).__name__))
                    events.append({"event": name, "t_s": round(time.monotonic() - t0, 3)})
                    if name == "session.begin":
                        config = getattr(message, "config", None)
                    if name == "transcript.final":
                        break
        finally:
            task.cancel()
    names = [e["event"] for e in events]
    return {
        "clip_seconds": len(pcm8) / 2 / 8000,
        "resolved_config": config.dict() if config is not None else None,
        "event_sequence_compact": [n for i, n in enumerate(names) if i == 0 or n != names[i - 1]],
        "events": events[:6] + events[-6:],
        "speech_end_after_clip_end_s": next(
            (e["t_s"] - len(pcm8) / 2 / 8000 for e in events if e["event"] == "vad.speech_end"),
            None,
        ),
        "got_transcript_final": "transcript.final" in names,
    }


def main() -> None:
    sample = json.loads(Path("results/gramvaani_sample.json").read_text("utf-8"))["items"]
    picked = [i for i in sample if i["seconds"] <= MAX_CLIP_S][:51]
    seconds = sum(i["seconds"] for i in picked[1:])
    first = decode_audio_file_to_chunks(DATA_DIR / f"{picked[0]['uttid']}.mp3", 16_000)
    short = next(i for i in sample if i["seconds"] <= 4)
    chunks = decode_audio_file_to_chunks(DATA_DIR / f"{short['uttid']}.mp3", 16_000)
    del first
    out = {
        "item": "3B-9",
        "utterances": len(picked) - 1,
        "plus_warmup": 1,
        "audio_minutes_50": seconds / 60,
        "estimated_cost_rs_at_plan_rate": seconds / 3600 * PLAN_RATE_RS_PER_HOUR,
        "machine_fit": "Whisper tiny/int8 + Piper + Silero on CPU, one process; no large model",
        "live_probe": asyncio.run(probe(to_pstn(chunks)[0].pcm)),
    }
    Path("results/preflight_3b-9.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main()
