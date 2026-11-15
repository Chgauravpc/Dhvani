"""3B-17 (b): digit-string exact match and number-normalised WER, from the cached logs.

    uv run python scripts/score_digits.py     # -> results/f2_digits.json

Protocol: `docs/runs/3b-17-preregistration.md`. No API call. Reads the four F2
transcript logs.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from dhvani.eval.numbers import digit_strings, to_digit_tokens
from dhvani.eval.stats import mcnemar_exact_p, wilson_interval
from dhvani.eval.transcript_log import TranscriptRecord, read_transcripts
from dhvani.eval.wer import corpus_wer

ARMS = (
    ("svarah", "whisper"),
    ("svarah", "sarvam"),
    ("indicvoices-hindi", "whisper"),
    ("indicvoices-hindi", "sarvam"),
    ("svarah", "groq-whisper"),  # 3B-20
    ("indicvoices-hindi", "groq-whisper"),  # 3B-20 (broken baseline by pre-flight)
)
BROKEN = {("indicvoices-hindi", "whisper")}  # 66.5% WER > 40% (plan section 3, check 2)


def _unit_outcomes(rows: list[TranscriptRecord]) -> list[bool]:
    outcomes: list[bool] = []
    for r in rows:
        available = Counter(digit_strings(r.raw_text))
        for unit in digit_strings(r.ground_truth_text):
            if available[unit] > 0:
                available[unit] -= 1
                outcomes.append(True)
            else:
                outcomes.append(False)
    return outcomes


def _rate(outcomes: list[bool]) -> dict[str, Any]:
    n, k = len(outcomes), sum(outcomes)
    lo, hi = wilson_interval(k, n)
    return {"k": k, "n": n, "rate": k / n if n else 0.0, "ci95": [lo, hi]}


def _wer(rows: list[TranscriptRecord], *, numbers: bool) -> float:
    pairs = [
        (
            to_digit_tokens(r.ground_truth_text) if numbers else r.ground_truth_text,
            to_digit_tokens(r.raw_text) if numbers else r.raw_text,
        )
        for r in rows
    ]
    return corpus_wer(pairs).wer


def main() -> None:
    arms: dict[str, Any] = {}
    outcomes: dict[str, list[bool]] = {}
    for dataset, stt in ARMS:
        rows = list(
            {
                r.key(): r
                for r in read_transcripts(Path(f"results/transcripts/f2_{dataset}_{stt}.jsonl"))
            }.values()
        )
        test = [r for r in rows if r.split == "test"]
        name = f"{dataset}/{stt}"
        outcomes[name] = _unit_outcomes(rows)
        arms[name] = {
            "broken_baseline": (dataset, stt) in BROKEN,
            "rows": len(rows),
            "digit_string_exact_match_all_rows": _rate(outcomes[name]),
            "digit_string_exact_match_test_rows": _rate(_unit_outcomes(test)),
            "wer_all_rows": {
                "raw": _wer(rows, numbers=False),
                "number_normalised": _wer(rows, numbers=True),
            },
            "wer_test_rows": {
                "raw": _wer(test, numbers=False),
                "number_normalised": _wer(test, numbers=True),
            },
        }
        w = arms[name]["wer_all_rows"]
        w["formatting_inflation_pp"] = 100 * (w["raw"] - w["number_normalised"])
        wt = arms[name]["wer_test_rows"]
        wt["formatting_inflation_pp"] = 100 * (wt["raw"] - wt["number_normalised"])

    sv_w = outcomes["svarah/whisper"]
    sv_s = outcomes["svarah/sarvam"]
    only_w = sum(1 for a, b in zip(sv_w, sv_s, strict=True) if a and not b)
    only_s = sum(1 for a, b in zip(sv_w, sv_s, strict=True) if b and not a)
    out = {
        "item": "3B-17",
        "preregistration": "docs/runs/3b-17-preregistration.md",
        "note": (
            "Digit-string exact match (maximal runs of >= 4 digits, normalised by "
            "dhvani.eval.numbers) and WER before/after number normalisation, clean audio, "
            "cached transcripts. Hindi/Whisper `small` is a broken baseline (66.5% WER) and "
            "is not a comparison arm. Intervals are Wilson 95% and treat units as independent."
        ),
        "arms": arms,
        "paired_svarah_whisper_vs_saaras": {
            "units": len(sv_w),
            "only_whisper_right": only_w,
            "only_saaras_right": only_s,
            "mcnemar_p": mcnemar_exact_p(only_w, only_s),
        },
    }
    Path("results/f2_digits.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    for name, a in arms.items():
        m, t = a["digit_string_exact_match_all_rows"], a["wer_all_rows"]
        tag = "  [broken baseline]" if a["broken_baseline"] else ""
        print(
            f"{name:28s} digits {m['k']}/{m['n']} = {m['rate']:.1%} "
            f"[{m['ci95'][0]:.1%}, {m['ci95'][1]:.1%}]  WER {t['raw']:.1%} -> "
            f"{t['number_normalised']:.1%} ({t['formatting_inflation_pp']:+.1f} pp){tag}"
        )
    print("paired svarah:", out["paired_svarah_whisper_vs_saaras"])


if __name__ == "__main__":
    main()
