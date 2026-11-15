"""3B-17 pre-flight (plan R2): is there enough to measure? No API call, no ASR output used.

    uv run python scripts/preflight_3b17.py     # -> results/preflight_3b-17.json

Check 1 (density) only: counts the digit strings of at least four digits in the
**reference** text of the cached F2 transcript logs, after `dhvani.eval.numbers`
normalisation. Checks 3-5 do not apply (no cost, no model, no API). Check 2
(baseline sanity) is read from the committed 3B-14 re-score, not re-run.
"""

from __future__ import annotations

import json
from pathlib import Path

from dhvani.eval.numbers import digit_strings
from dhvani.eval.transcript_log import read_transcripts

CORPORA = ("svarah", "indicvoices-hindi")


def main() -> None:
    rescore = json.loads(Path("results/f2_rescore.json").read_text(encoding="utf-8"))
    out: dict[str, object] = {
        "item": "3B-17",
        "checks": {
            "1_density": "reference digit strings (>= 4 digits) after number normalisation",
            "2_baseline_sanity": "taken from results/f2_rescore.json (3B-14), not re-run",
            "3_cost": "none: no API call",
            "4_machine_fit": "none: string processing only",
            "5_api_reality": "none: no API call",
        },
        "corpora": {},
    }
    for dataset in CORPORA:
        rows = {
            r.key(): r
            for r in read_transcripts(Path(f"results/transcripts/f2_{dataset}_sarvam.jsonl"))
        }
        units = [digit_strings(r.ground_truth_text) for r in rows.values()]
        n_units = sum(len(u) for u in units)
        by_split: dict[str, int] = {}
        for r, u in zip(rows.values(), units, strict=True):
            by_split[r.split] = by_split.get(r.split, 0) + len(u)
        lengths = sorted({len(d) for u in units for d in u})
        out["corpora"][dataset] = {  # type: ignore[index]
            "rows": len(rows),
            "rows_with_a_digit_string": sum(1 for u in units if u),
            "digit_strings": n_units,
            "digit_strings_by_split": by_split,
            "digit_string_lengths_seen": lengths,
            "density_check": (
                "pass (>= 100)"
                if n_units >= 100
                else "report intervals (30-100)"
                if n_units >= 30
                else "fail (< 30)"
            ),
            "wer_all_rows_raw": {
                stt: rescore["arms"][f"{dataset}/{stt}"]["wer"]["all_rows"]["wer"]
                for stt in ("whisper", "sarvam")
            },
        }
    Path("results/preflight_3b-17.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(out["corpora"], indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
