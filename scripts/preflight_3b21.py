"""3B-21 pre-flight (plan R2): real telephone Hindi, Gram Vaani (OpenSLR 118).

    uv run python scripts/preflight_3b21.py [DATA_DIR]
    # -> results/preflight_3b-21.json, results/gramvaani_sample.json

DATA_DIR is the extracted `GV_Dev_5h` folder (default
`D:/Desktop/Projects/Dhvani_data/gramvaani_dev/GV_Dev_5h`; download
https://www.openslr.org/resources/118/GV_Dev_5h.tar.gz into its own folder first).
Free, no API call. Eligible utterance: reference non-empty and free of `<...>` tags
(`<inaudible>`), audio duration 1.0 to 29.5 s. The sample is a seed-0 shuffle taken in
order until the next utterance would pass 35 minutes. Only ids, durations and rates
are committed (the transcripts are Gram Vaani's, licensed for academic use).
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import av

from dhvani.eval.numbers import digit_strings

DEFAULT_DIR = Path("D:/Desktop/Projects/Dhvani_data/gramvaani_dev/GV_Dev_5h")
MAX_SECONDS = 35 * 60
MIN_CLIP_S, MAX_CLIP_S = 1.0, 29.5
SEED = 0


def read_references(data_dir: Path) -> dict[str, str]:
    refs: dict[str, str] = {}
    for line in (data_dir / "text").read_text(encoding="utf-8").splitlines():
        uttid, _, text = line.partition(" ")
        if uttid:
            refs[uttid] = text.strip()
    return refs


def probe(path: Path) -> tuple[float, int]:
    container = av.open(str(path))
    try:
        stream = container.streams.audio[0]
        return float(container.duration or 0) / 1_000_000, int(stream.rate)
    finally:
        container.close()


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    refs = read_references(data_dir)
    eligible: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for uttid in sorted(refs):
        path = data_dir / "Audio" / f"{uttid}.mp3"
        if not path.exists():
            skipped["no_audio"] += 1
            continue
        if not refs[uttid] or "<" in refs[uttid]:
            skipped["empty_or_tagged_reference"] += 1
            continue
        seconds, rate = probe(path)
        if not MIN_CLIP_S <= seconds <= MAX_CLIP_S:
            skipped["duration_out_of_range"] += 1
            continue
        eligible.append({"uttid": uttid, "seconds": round(seconds, 3), "sample_rate_hz": rate})
    rng = random.Random(SEED)
    shuffled = list(eligible)
    rng.shuffle(shuffled)
    sample: list[dict[str, Any]] = []
    total = 0.0
    for item in shuffled:
        if total + item["seconds"] > MAX_SECONDS:
            break
        sample.append(item)
        total += item["seconds"]
    units = sum(len(digit_strings(refs[i["uttid"]])) for i in sample)
    rows_with_units = sum(1 for i in sample if digit_strings(refs[i["uttid"]]))
    report = {
        "item": "3B-21",
        "source": (
            "OpenSLR 118, GV_Dev_5h.tar.gz "
            "(labelled dev split of the Gram Vaani Hindi ASR challenge)"
        ),
        "licence": "free for academic purposes; commercial use needs permission (openslr.org/118)",
        "utterances_in_dev": len(refs),
        "skipped": dict(skipped),
        "eligible": len(eligible),
        "eligible_sample_rates_hz": dict(Counter(e["sample_rate_hz"] for e in eligible)),
        "sample": {
            "seed": SEED,
            "utterances": len(sample),
            "minutes": total / 60,
            "sample_rates_hz": dict(Counter(i["sample_rate_hz"] for i in sample)),
            "reference_words": sum(len(refs[i["uttid"]].split()) for i in sample),
            "rows_with_a_digit_string": rows_with_units,
            "digit_strings": units,
        },
        "checks": {
            "downloadable": True,
            "fits_on_D": True,
            "at_least_100_utterances": len(sample) >= 100,
            "references_usable": "Devanagari text; spelled numbers; <...> tags excluded",
        },
    }
    Path("results/preflight_3b-21.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    Path("results/gramvaani_sample.json").write_text(
        json.dumps({"seed": SEED, "max_seconds": MAX_SECONDS, "items": sample}, indent=1),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
