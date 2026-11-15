"""3B-9 scoring: p50 / p90 per stage, per arm, from the committed per-utterance rows.

    uv run python scripts/score_latency.py     # -> results/latency_3b9.json

Protocol: `docs/runs/3b-9-preregistration.md` section 3. Reports every completed turn (as
preregistered) and, because a clamped instant means the endpoint fired before the last speech
of the clip (the speaker paused longer than the 500 ms silence rule), the same numbers over the
turns with no clamped instant. No API call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dhvani.eval.latency import summarise

ARMS = ("sarvam-realtime", "whisper-tiny")


def main() -> None:
    out: dict[str, Any] = {
        "item": "3B-9",
        "preregistration": "docs/runs/3b-9-preregistration.md",
        "note": (
            "End of speech (last Silero-voiced window of the clip) to first TTS audio byte; "
            "8 kHz mu-law telephone audio at real time; 50 utterances plus an excluded warm-up; "
            "Groq LLM and local Piper behind both STT arms. 'clamped' turns are ones whose "
            "endpoint fired before the clip's last speech (a premature endpoint)."
        ),
        "arms": {},
    }
    for arm in ARMS:
        rows = [
            json.loads(line)
            for line in Path(f"results/latency/3b9_{arm}.jsonl").read_text("utf-8").splitlines()
            if line.strip()
        ]
        measured = [r for r in rows if not r["warmup"]]
        completed = [r for r in measured if not r.get("error")]
        clean = [r for r in completed if not r["clamped"]]
        out["arms"][arm] = {
            "turns": len(measured),
            "all_completed_as_preregistered": summarise(measured),
            "turns_with_premature_endpoint": len(completed) - len(clean),
            "excluding_premature_endpoints": summarise(clean),
            "failures": [r["error"] for r in measured if r.get("error")],
        }
    Path("results/latency_3b9.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    for arm, a in out["arms"].items():
        for label, key in (
            ("all completed", "all_completed_as_preregistered"),
            ("no premature endpoint", "excluding_premature_endpoints"),
        ):
            s = a[key]
            cells = "  ".join(
                f"{k[:-3]} {s[k]['p50']:.0f}/{s[k]['p90']:.0f}"
                for k in ("endpoint_ms", "stt_ms", "llm_ms", "tts_ms", "total_ms")
                if k in s
            )
            print(f"{arm:16s} {label:22s} n={s['n_completed']:2d}  p50/p90 ms: {cells}")
        print(
            f"{'':16s} premature endpoints: {a['turns_with_premature_endpoint']}, "
            f"failures: {len(a['failures'])}"
        )


if __name__ == "__main__":
    main()
