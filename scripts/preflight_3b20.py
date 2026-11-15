"""3B-20 pre-flight (plan R2): exercise Groq `whisper-large-v3` before the real run.

    uv run python scripts/preflight_3b20.py     # -> results/preflight_3b-20.json

Checks (plan section 3): the rows are the 3B-4 rows (same ids as the committed
Saaras logs), audio seconds measured from the rows against Groq's free-tier
limits, the model string and audio format accepted by the live endpoint, the
limit headers observed, and baseline sanity on 20 rows per dataset (WER under
40% and the expected script). Costs nothing; sends 40 clips to Groq.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import groq
from run_f2_entity_eval import _load

from dhvani.clock import RealClock
from dhvani.config import load_dotenv
from dhvani.eval.datasets import TranscriptExample
from dhvani.eval.entity_error_rate import _transcribe
from dhvani.eval.transcript_log import read_transcripts
from dhvani.eval.wer import corpus_wer
from dhvani.providers.groq_stt import DEFAULT_MODEL, GroqSTT, _encode_wav

LANGUAGE = {"svarah": "en", "indicvoices-hindi": "hi"}
N_SANITY = 20


def _seconds(example: TranscriptExample) -> float:
    return sum(len(c.pcm) / 2 / c.sample_rate for c in example.audio_chunks)


def _dominant_script(text: str) -> str:
    counts: Counter[str] = Counter()
    for ch in text:
        if unicodedata.category(ch).startswith("L"):
            counts[unicodedata.name(ch, "UNKNOWN").split()[0]] += 1
    return counts.most_common(1)[0][0].lower() if counts else "none"


async def main() -> None:
    load_dotenv()
    keys = [k.strip() for k in os.environ.get("GROQ_API_KEYS", "").split(",") if k.strip()]
    api_key = keys[0] if keys else os.environ["GROQ_API_KEY"]
    out: dict[str, Any] = {"item": "3B-20", "model_requested": DEFAULT_MODEL, "datasets": {}}
    for dataset, language in LANGUAGE.items():
        args = argparse.Namespace(dataset=dataset, n_clean_sample=150, min_entity_rows=300, seed=0)
        dev, test, _ = _load(args)
        examples = [
            *dev.entity_bearing,
            *dev.clean_sample,
            *test.entity_bearing,
            *test.clean_sample,
        ]
        logged = {
            r.example_id
            for r in read_transcripts(Path(f"results/transcripts/f2_{dataset}_sarvam.jsonl"))
        }
        ids = {e.example_id for e in examples}
        seconds = sum(_seconds(e) for e in examples)
        stt = GroqSTT(RealClock(), language=language, api_key=api_key)
        sample = examples[:N_SANITY]
        pairs: list[tuple[str, str]] = []
        for e in sample:
            pairs.append((e.ground_truth_text, await _transcribe(e, stt, RealClock())))
        wer = corpus_wer(pairs).wer
        scripts = Counter(_dominant_script(hyp) for _, hyp in pairs)
        raw = await groq.AsyncGroq(api_key=api_key).audio.transcriptions.with_raw_response.create(
            file=("audio.wav", _encode_wav(sample[0].audio_chunks[0].pcm, 16000)),
            model=DEFAULT_MODEL,
            language=language,
            response_format="json",
            temperature=0.0,
        )
        headers = {
            k: v
            for k, v in raw.headers.items()
            if k.lower().startswith(("x-ratelimit", "retry-after", "x-groq", "x-request"))
        }
        out["datasets"][dataset] = {
            "rows": len(examples),
            "rows_match_committed_saaras_log": ids == logged,
            "audio_seconds_total": seconds,
            "audio_seconds_longest_clip": max(_seconds(e) for e in examples),
            "sanity_rows": len(sample),
            "sanity_wer": wer,
            "sanity_wer_under_40pct": wer < 0.4,
            "sanity_output_scripts": dict(scripts),
            "response_headers_seen": headers,
        }
        print(dataset, json.dumps(out["datasets"][dataset], indent=1), flush=True)
    Path("results/preflight_3b-20.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    asyncio.run(main())
