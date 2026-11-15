"""3B-18 / 3B-20 scoring: clean vs `pstn`, paired by unit. No API call.

    uv run python scripts/score_channel.py --stt sarvam        # -> results/f3_channel_sarvam.json
    uv run python scripts/score_channel.py --stt groq-whisper  # -> f3_channel_groq-whisper.json

Protocol: `docs/runs/3b-18-preregistration.md` section 3. Per corpus, over the 290
test-split entity rows: digit-string exact match (3B-17 rule), entity recognition
error, and WER raw / number-normalised, clean vs `pstn`. "Degrades" means an
absolute drop of at least 5 points AND exact McNemar p < 0.05 against clean.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.entity.mentions import mentioned_entities
from dhvani.eval.numbers import digit_strings, to_digit_tokens
from dhvani.eval.stats import mcnemar_exact_p, wilson_interval
from dhvani.eval.transcript_log import TranscriptRecord, read_transcripts
from dhvani.eval.wer import corpus_wer

DATASETS = ("svarah", "indicvoices-hindi")
MIN_DROP_PP = 5.0
ALPHA = 0.05


def _rate(outcomes: list[bool]) -> dict[str, Any]:
    n, k = len(outcomes), sum(outcomes)
    lo, hi = wilson_interval(k, n)
    return {"k": k, "n": n, "rate": k / n if n else 0.0, "ci95": [lo, hi]}


def _digit_outcomes(refs: list[TranscriptRecord], hyps: dict[str, str]) -> list[bool]:
    out: list[bool] = []
    for r in refs:
        available = Counter(digit_strings(hyps[r.example_id]))
        for unit in digit_strings(r.ground_truth_text):
            if available[unit] > 0:
                available[unit] -= 1
                out.append(True)
            else:
                out.append(False)
    return out


def _entity_outcomes(refs: list[TranscriptRecord], hyps: dict[str, str]) -> list[bool]:
    out: list[bool] = []
    for r in refs:
        seen = mentioned_entities(hyps[r.example_id], DEFAULT_LEXICON)
        out.extend(
            entity in seen
            for entity in sorted(mentioned_entities(r.ground_truth_text, DEFAULT_LEXICON))
        )
    return out


def _compare(clean: list[bool], pstn: list[bool], *, higher_is_better: bool) -> dict[str, Any]:
    """Paired clean vs pstn. `drop_pp` is how much worse pstn is, in points."""
    a, b = (clean, pstn) if higher_is_better else ([not x for x in clean], [not x for x in pstn])
    worse = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    better = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    drop = 100 * (sum(a) - sum(b)) / len(a)
    p = mcnemar_exact_p(worse, better)
    return {
        "clean": _rate(clean),
        "pstn": _rate(pstn),
        "worse_under_pstn": worse,
        "better_under_pstn": better,
        "drop_pp": drop,
        "mcnemar_p": p,
        "degrades": bool(drop >= MIN_DROP_PP and p < ALPHA),
    }


def _wer(refs: list[TranscriptRecord], hyps: dict[str, str], *, numbers: bool) -> float:
    fn = to_digit_tokens if numbers else (lambda t: t)
    return corpus_wer([(fn(r.ground_truth_text), fn(hyps[r.example_id])) for r in refs]).wer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stt", choices=["sarvam", "groq-whisper"], required=True)
    args = parser.parse_args()
    out: dict[str, Any] = {
        "item": "3B-18" if args.stt == "sarvam" else "3B-20 (pstn half)",
        "preregistration": "docs/runs/3b-18-preregistration.md",
        "stt": args.stt,
        "note": (
            "Test-split entity rows, clean (3B-4 transcripts) vs simulated 8 kHz mu-law `pstn`, "
            "paired by unit. Degrades = drop >= 5 points and exact McNemar p < 0.05. Intervals "
            "and tests treat units as independent; samples are clustered, so they are optimistic."
        ),
        "datasets": {},
    }
    for dataset in DATASETS:
        pstn_records = {
            r.example_id: r
            for r in read_transcripts(
                Path(f"results/transcripts/f3_{dataset}_{args.stt}_pstn.jsonl")
            )
        }
        clean_all = {
            r.example_id: r
            for r in read_transcripts(Path(f"results/transcripts/f2_{dataset}_{args.stt}.jsonl"))
        }
        refs = [clean_all[i] for i in pstn_records]
        clean = {r.example_id: r.raw_text for r in refs}
        pstn = {i: r.raw_text for i, r in pstn_records.items()}
        out["datasets"][dataset] = {
            "rows": len(refs),
            "digit_string_exact_match": _compare(
                _digit_outcomes(refs, clean), _digit_outcomes(refs, pstn), higher_is_better=True
            ),
            "entity_recognition_rate": _compare(
                _entity_outcomes(refs, clean), _entity_outcomes(refs, pstn), higher_is_better=True
            ),
            "wer": {
                "clean_raw": _wer(refs, clean, numbers=False),
                "pstn_raw": _wer(refs, pstn, numbers=False),
                "clean_number_normalised": _wer(refs, clean, numbers=True),
                "pstn_number_normalised": _wer(refs, pstn, numbers=True),
            },
        }
    Path(f"results/f3_channel_{args.stt}.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    for dataset, d in out["datasets"].items():
        for name in ("digit_string_exact_match", "entity_recognition_rate"):
            c = d[name]
            print(
                f"{dataset:18s} {name:26s} clean {c['clean']['rate']:.1%} -> pstn "
                f"{c['pstn']['rate']:.1%} (drop {c['drop_pp']:+.1f} pp, worse/better "
                f"{c['worse_under_pstn']}/{c['better_under_pstn']}, p={c['mcnemar_p']:.3g}) "
                f"degrades={c['degrades']}"
            )
        w = d["wer"]
        print(
            f"{dataset:18s} WER raw {w['clean_raw']:.1%}->{w['pstn_raw']:.1%}  "
            f"normalised {w['clean_number_normalised']:.1%}->{w['pstn_number_normalised']:.1%}"
        )


if __name__ == "__main__":
    main()
