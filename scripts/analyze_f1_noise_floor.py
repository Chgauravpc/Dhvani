"""3B-5 analysis: A/A noise floor, ASR loss with paired-bootstrap CI,
majority-vote McNemar, and the section 10.6 verdict -- all from the committed
run log. Protocol: `docs/specs/phase-3b.md` section 10.

    uv run python scripts/analyze_f1_noise_floor.py [--runs results/f1_runs/runs.jsonl]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dhvani.eval.noise_floor import RunLog, analyze


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("results/f1_runs/runs.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("results/f1_noise_floor.json"))
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()

    log = RunLog(args.runs)
    result = analyze(log.records(), k=args.k)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"k={result['k']}  incomplete cells: {result['incomplete_cells'] or 'none'}")
    for language, lang in result["languages"].items():
        per_run = {r: round(v, 1) for r, v in lang["gt_rate_per_run_pct"].items()}
        print(
            f"\n{language}: GT complete n={lang['n_gt_complete']}  "
            f"noise floor = {lang['noise_floor_pp']:.1f} pp  (GT rate per run: {per_run})"
        )
        for cond, arm in lang["arms"].items():
            if arm.get("n", 0) == 0:
                print(f"  {cond}: no complete data")
                continue
            lo, hi = arm["loss_ci_pp"]
            print(
                f"  {cond}: loss {arm['mean_loss_pp']:.1f} pp  CI [{lo:.1f}, {hi:.1f}]  "
                f"McNemar {arm['majority_gt_pass_real_fail']}/{arm['majority_gt_fail_real_pass']} "
                f"p={arm['mcnemar_p']:.3g}  -> {arm['verdict']}"
            )
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
