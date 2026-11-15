"""Render the README's result tables from committed results files (3B-16).

    uv run python scripts/render_readme_tables.py            # print the tables
    uv run python scripts/render_readme_tables.py --check README.md

Every number in the README's tables comes from here, and `--check` fails if the
README does not contain the generated text verbatim -- so a table cannot drift
from the results file it claims to read. Sources:

- `results/f2_three_way.json` (3B-15): the F2 table.
- `results/f1_meaning_judge.json` (3B-19): the F1 ground-truth ceiling under the three
  judges, the noise floor, and the per-arm ASR loss table.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ARM_LABELS = {
    "svarah/whisper": "Svarah (English), local Whisper `small`",
    "svarah/sarvam": "Svarah (English), Saaras",
    "indicvoices-hindi/whisper": "IndicVoices (Hindi), local Whisper `small`",
    "indicvoices-hindi/sarvam": "IndicVoices (Hindi), Saaras",
}
COLUMN_LABELS = {
    "raw": "raw ASR output",
    "exact": "+ exact lookup (default)",
    "exact_plus_fuzzy": "+ exact + fuzzy",
}


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def f2_table() -> str:
    data: dict[str, Any] = json.loads(Path("results/f2_three_way.json").read_text("utf-8"))
    lines = [
        "| Arm (test mentions / clean rows) | Corrector | Recognition error | "
        "Canonical-form miss | Clean rows corrupted |",
        "|---|---|---|---|---|",
    ]
    for key, label in ARM_LABELS.items():
        arm = data["arms"][key]
        first = True
        for col, col_label in COLUMN_LABELS.items():
            c = arm["columns"][col]
            corrupt = c["corruption_on_clean_rows"]
            corrupt_text = "-" if corrupt is None else f"{corrupt['k']} / {corrupt['n']}"
            name = (
                f"{label} ({arm['n_test_mentions']} / {arm['n_test_clean_rows']})" if first else ""
            )
            lines.append(
                f"| {name} | {col_label} | {_pct(c['recognition_error']['rate'])} | "
                f"{_pct(c['canonical_miss']['rate'])} | {corrupt_text} |"
            )
            first = False
    return "\n".join(lines)


def f1_table() -> str:
    judged: dict[str, Any] = json.loads(Path("results/f1_meaning_judge.json").read_text("utf-8"))
    floor = judged["analysis_list_aware_plus_meaning"]["languages"]
    lines = [
        "| | Ground-truth text passes: exact-match judge as run | List-argument bug fixed | "
        "Plus meaning-level judge | Run-to-run noise floor (final judge) |",
        "|---|---|---|---|---|",
    ]
    for lang, name in (("english", "English (141 tasks)"), ("hindi", "Hindi (134 tasks)")):
        rates = judged["gt_pass_rate_pct"][lang]
        lines.append(
            f"| {name} | {rates['registered']:.1f}% | {rates['list_aware']:.1f}% | "
            f"{rates['list_aware_plus_meaning']:.1f}% | {floor[lang]['noise_floor_pp']:.1f} pp |"
        )
    return "\n".join(lines)


def f1_loss_table() -> str:
    judged: dict[str, Any] = json.loads(Path("results/f1_meaning_judge.json").read_text("utf-8"))
    final = judged["analysis_list_aware_plus_meaning"]["languages"]
    lines = [
        "| Language / ASR | Task success lost vs ground-truth text | 95% interval | "
        "Tasks only ground truth passes / only the ASR passes | McNemar p | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    arms = {"whisper": "local Whisper `small`", "sarvam": "Saaras"}
    for lang, name in (("english", "English"), ("hindi", "Hindi")):
        for arm, arm_name in arms.items():
            a = final[lang]["arms"][arm]
            lo, hi = a["loss_ci_pp"]
            lines.append(
                f"| {name} / {arm_name} | {a['mean_loss_pp']:.1f} pp | {lo:.1f} to {hi:.1f} | "
                f"{a['majority_gt_pass_real_fail']} / {a['majority_gt_fail_real_pass']} | "
                f"{a['mcnemar_p']:.2g} | {a['verdict']} |"
            )
    return "\n".join(lines)


def blocks() -> dict[str, str]:
    return {"F2 table": f2_table(), "F1 table": f1_table(), "F1 loss table": f1_loss_table()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", type=Path, default=None, help="README to verify")
    args = parser.parse_args()
    rendered = blocks()
    if args.check is None:
        for name, text in rendered.items():
            print(f"<!-- {name} -->\n{text}\n")
        return
    readme = args.check.read_text(encoding="utf-8")
    missing = [name for name, text in rendered.items() if text not in readme]
    if missing:
        print(f"README does not contain the generated text of: {', '.join(missing)}")
        sys.exit(1)
    print(f"{args.check}: all {len(rendered)} generated tables present verbatim")


if __name__ == "__main__":
    main()
