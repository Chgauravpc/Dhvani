"""3B-18 pre-flight (plan R2): rows, audio minutes, cost, and one live Saaras probe.

    uv run python scripts/preflight_3b18.py     # -> results/preflight_3b-18.json

Spends one clip of Sarvam credit (a probe through the `pstn` leg) to answer: does
the key have credit, is an 8 kHz WAV accepted, which model string comes back, and
does the response or its headers say anything about the balance. The SDK has no
balance call, so the dashboard balance is read by the owner (plan section 4).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import wave
from pathlib import Path
from typing import Any

import httpx
from run_f2_entity_eval import _load
from sarvamai import AsyncSarvamAI

from dhvani.config import load_dotenv
from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.entity.mentions import mentioned_entities
from dhvani.eval.datasets import TranscriptExample
from dhvani.eval.pstn import to_pstn
from dhvani.providers.sarvam_stt import DEFAULT_MODEL

DATASETS = ("svarah", "indicvoices-hindi")
PLAN_RATE_RS_PER_HOUR = 30.0  # the rate behind the plan's "about 33 credits"


def _seconds(example: TranscriptExample) -> float:
    return sum(len(c.pcm) / 2 / c.sample_rate for c in example.audio_chunks)


def _wav(pcm: bytes, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buffer.getvalue()


async def main() -> None:
    load_dotenv()
    out: dict[str, Any] = {"item": "3B-18", "model_requested": DEFAULT_MODEL, "datasets": {}}
    probe_row: TranscriptExample | None = None
    total_seconds = 0.0
    for dataset in DATASETS:
        args = argparse.Namespace(dataset=dataset, n_clean_sample=150, min_entity_rows=300, seed=0)
        _dev, test, _ = _load(args)
        rows = [
            e
            for e in test.entity_bearing
            if mentioned_entities(e.ground_truth_text, DEFAULT_LEXICON)
        ]
        seconds = sum(_seconds(e) for e in rows)
        total_seconds += seconds
        if probe_row is None:
            probe_row = min(rows, key=_seconds)
        out["datasets"][dataset] = {
            "test_entity_rows": len(rows),
            "audio_seconds": seconds,
            "longest_clip_seconds": max(_seconds(e) for e in rows),
        }
    out["total_test_entity_rows"] = sum(d["test_entity_rows"] for d in out["datasets"].values())
    out["total_audio_minutes"] = total_seconds / 60
    out["estimated_cost_rs_at_plan_rate"] = total_seconds / 3600 * PLAN_RATE_RS_PER_HOUR

    assert probe_row is not None
    chunk = to_pstn(probe_row.audio_chunks)[0]
    client = AsyncSarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"], timeout=60.0)
    result: dict[str, Any] = {"probe_seconds": len(chunk.pcm) / 2 / chunk.sample_rate}
    try:
        raw = await client.speech_to_text.with_raw_response.transcribe(
            file=("audio.wav", _wav(chunk.pcm, chunk.sample_rate), "audio/wav"),
            model=DEFAULT_MODEL,
            mode="transcribe",
        )
        data = raw.data
        result |= {
            "accepted_8khz_wav": True,
            "status": getattr(raw, "status_code", None),
            "response_fields": sorted(
                k for k in (data.dict() if hasattr(data, "dict") else vars(data))
            ),
            "language_code": getattr(data, "language_code", None),
            "transcript_chars": len(getattr(data, "transcript", "") or ""),
            "headers_seen": {
                k: v
                for k, v in raw.headers.items()
                if any(t in k.lower() for t in ("credit", "balance", "limit", "usage", "model"))
            },
        }
    except httpx.HTTPError as exc:
        result |= {"accepted_8khz_wav": False, "error": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:  # the SDK's ApiError carries the status (e.g. 402: no credit)
        result |= {
            "accepted_8khz_wav": False,
            "status": getattr(exc, "status_code", None),
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
        }
    out["live_probe"] = result
    Path("results/preflight_3b-18.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in out.items() if k != "model_requested"}, indent=1))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    asyncio.run(main())
