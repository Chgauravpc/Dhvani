"""3B-19 steps (b) agreement and (d) the three-judge re-score. No API call.

    uv run python scripts/analyze_f1_meaning_judge.py

Reads results/f1_meaning_judge/verdicts.jsonl and the owner's labels, writes
results/f1_meaning_judge.json:

- agreement: Cohen's kappa and raw agreement between the judge and the owner's 50
  labels, bootstrap 95% intervals (threshold kappa >= 0.6);
- if every judged item is scored, the whole 3B-5 log re-scored under judge (3)
  (list-aware exact match, then the meaning judge on each remaining value
  mismatch) with the section 10.6 machinery, beside judges (1) and (2).
"""

from __future__ import annotations

import csv
import dataclasses
import json
from pathlib import Path
from typing import Any

from f1_judge_population import Key, build_population, item_key
from run_f1_meaning_judge import OWNER, VERDICTS, labelled_keys

from dhvani.eval.judge_audit import array_params, mismatching_params
from dhvani.eval.meaning_judge import agreement
from dhvani.eval.noise_floor import RunLog, RunRecord, analyze
from dhvani.eval.task_success import _normalize
from dhvani.types import ToolCall

OUT = Path("results/f1_meaning_judge.json")
LABEL = "label (equivalent / not_equivalent)"


def _verdicts() -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for line in VERDICTS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            latest[rec["key"]] = rec
    return latest


def main() -> None:
    from huggingface_hub import hf_hub_download

    from dhvani.eval.datasets import _parse_expected_tool_call

    population = build_population()
    verdicts = _verdicts()
    out: dict[str, Any] = {
        "item": "3B-19 (b), (d)",
        "preregistration": "docs/runs/3b-19-preregistration.md",
        "judge_model": next(iter(verdicts.values()))["model"],
        "population": {
            "unique_items": len(population),
            "judged": sum(1 for v in verdicts.values() if v["status"] == "scored"),
            "unparsed": sum(1 for v in verdicts.values() if v["status"] == "unparsed"),
            "incomplete": sum(1 for v in verdicts.values() if v["status"] == "incomplete"),
        },
    }

    # ---- agreement on the owner's 50 labels
    keys = labelled_keys(population)
    with OWNER.open(encoding="utf-8-sig", newline="") as fh:
        owner_rows = list(csv.DictReader(fh))
    judge_votes: list[bool] = []
    owner_votes: list[bool] = []
    for key, row in zip(keys, owner_rows, strict=True):
        v = verdicts.get(item_key(key))
        if v is None or v["status"] != "scored":
            continue
        judge_votes.append(bool(v["equivalent"]))
        owner_votes.append(row[LABEL] == "equivalent")
    out["agreement"] = agreement(judge_votes, owner_votes) | {
        "labelled_items": len(keys),
        "unscored_labelled_items": len(keys) - len(judge_votes),
        "threshold_kappa": 0.6,
        "meets_threshold": agreement(judge_votes, owner_votes, resamples=1)["kappa"] >= 0.6,
    }
    by_lang: dict[str, dict[str, int]] = {}
    for key, j, o in zip(keys, judge_votes, owner_votes, strict=False):
        d = by_lang.setdefault(key[0], {"n": 0, "agree": 0})
        d["n"] += 1
        d["agree"] += j == o
    out["agreement"]["by_language"] = by_lang
    out["agreement"]["disagreements"] = [
        {
            "item": i + 1,
            "language": keys[i][0],
            "query": population[keys[i]]["item"].query,
            "accepted": population[keys[i]]["item"].accepted_values,
            "returned": population[keys[i]]["item"].returned_value,
            "owner": "equivalent" if o else "not_equivalent",
            "judge": "equivalent" if j else "not_equivalent",
            "owner_note": owner_rows[i]["note"],
        }
        for i, (j, o) in enumerate(zip(judge_votes, owner_votes, strict=False))
        if j != o
    ]

    # ---- (d) three-judge re-score, only once every item is scored
    complete = (
        out["population"]["judged"] == len(population)
        and out["population"]["unparsed"] == 0
        and out["population"]["incomplete"] == 0
    )
    out["rescore_complete"] = complete
    if complete:
        manifests: dict[str, dict[str, Any]] = {}
        for lang in ("english", "hindi"):
            path = hf_hub_download(
                "krutrim-ai-labs/VoiceAgentBench",
                f"data/single_tool_data/{lang}/single_tool_{lang}.json",
                repo_type="dataset",
            )
            manifests[lang] = {str(r["id"]): r for r in json.loads(Path(path).read_text("utf-8"))}
        records = RunLog(Path("results/f1_runs/runs.jsonl")).records()

        def passes_meaning(r: RunRecord) -> bool:
            if r.tool_call is None:
                return False
            raw = manifests[r.language][r.example_id]
            exp = _parse_expected_tool_call(raw["expected_tool_call"])
            arrays = array_params(raw["functions"], exp.name)
            call = ToolCall(
                id="", name=str(r.tool_call["name"]), arguments=dict(r.tool_call["arguments"])
            )
            if call.name != exp.name or any(p not in call.arguments for p in exp.arguments):
                return False
            for param in mismatching_params(call, exp, arrays, list_aware=True):
                key: Key = (
                    r.language,
                    r.example_id,
                    param,
                    _normalize(json.dumps(call.arguments[param], ensure_ascii=False)),
                )
                if not verdicts[item_key(key)]["equivalent"]:
                    return False
            return True

        rescored = [
            dataclasses.replace(r, outcome="pass" if passes_meaning(r) else "fail") for r in records
        ]

        def gt_rate(rs: list[RunRecord], lang: str) -> float:
            cells = [x for x in rs if x.language == lang and x.condition == "gt"]
            return 100 * sum(1 for x in cells if x.outcome == "pass") / len(cells)

        audit = json.loads(Path("results/f1_judge_audit.json").read_text(encoding="utf-8"))
        out["gt_pass_rate_pct"] = {
            lang: {
                "registered": audit["gt_pass_rate_pct"][lang]["registered"],
                "list_aware": audit["gt_pass_rate_pct"][lang]["list_aware"],
                "list_aware_plus_meaning": gt_rate(rescored, lang),
            }
            for lang in ("english", "hindi")
        }
        out["analysis_list_aware_plus_meaning"] = analyze(rescored)
        out["analysis_list_aware"] = audit["analysis_list_aware"]
        out["analysis_registered_exact_match"] = audit["analysis_registered_exact_match"]

    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    a = out["agreement"]
    print(
        f"agreement n={a['n']}  kappa={a['kappa']:.3f} "
        f"[{a['kappa_ci95'][0]:.3f}, {a['kappa_ci95'][1]:.3f}]  "
        f"raw={a['raw_agreement']:.1%}  meets 0.6: {a['meets_threshold']}"
    )
    print(
        f"judge yes/owner no {a['judge_yes_owner_no']}, "
        f"judge no/owner yes {a['judge_no_owner_yes']}"
    )
    print(f"population: {out['population']}  rescore_complete: {complete}")


if __name__ == "__main__":
    main()
