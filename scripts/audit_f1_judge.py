"""3B-19 steps (a), (a2) and the blind labelling sheet for (c).

Protocol: `docs/runs/3b-19-preregistration.md`. Makes **no API call**; reads the
committed 3B-5 run log and the cached VoiceAgentBench manifests.

    uv run python scripts/audit_f1_judge.py

Writes `results/f1_judge_audit.json` (classification, list-aware re-score, the
registered judge reproduced as a sanity check, prediction check),
`results/f1_judge_population.json` (the mismatch population for (c)/(b)) and
`results/f1_judge_labels_blank.csv` (the owner's sheet: no verdicts, no
outcomes, no ASR condition). Step (b), the meaning judge, is NOT run here.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from huggingface_hub import hf_hub_download

from dhvani.eval.datasets import ExpectedToolCall, _parse_expected_tool_call
from dhvani.eval.judge_audit import (
    VALUE_MISMATCH,
    array_params,
    classify_failure,
    judge_list_aware,
    mismatching_params,
)
from dhvani.eval.noise_floor import RunLog, RunRecord, analyze
from dhvani.eval.task_success import _normalize, judge_tool_call
from dhvani.types import ToolCall

REPO = "krutrim-ai-labs/VoiceAgentBench"
LANGUAGES = ("english", "hindi")
RUNS = Path("results/f1_runs/runs.jsonl")
SAMPLE_PER_LANGUAGE = 25


def _manifest(language: str) -> dict[str, dict[str, Any]]:
    path = hf_hub_download(
        REPO, f"data/single_tool_data/{language}/single_tool_{language}.json", repo_type="dataset"
    )
    return {str(r["id"]): r for r in json.loads(Path(path).read_text(encoding="utf-8"))}


def _tool_call(record: RunRecord) -> ToolCall | None:
    if record.tool_call is None:
        return None
    return ToolCall(
        id="", name=str(record.tool_call["name"]), arguments=dict(record.tool_call["arguments"])
    )


def main() -> None:
    manifests = {lang: _manifest(lang) for lang in LANGUAGES}
    expected: dict[tuple[str, str], ExpectedToolCall] = {}
    arrays: dict[tuple[str, str], frozenset[str]] = {}
    for lang, by_id in manifests.items():
        for ex_id, raw in by_id.items():
            exp = _parse_expected_tool_call(raw["expected_tool_call"])
            expected[(lang, ex_id)] = exp
            arrays[(lang, ex_id)] = array_params(raw["functions"], exp.name)

    records = RunLog(RUNS).records()
    assert len(records) == 2475, f"expected 2,475 cells, found {len(records)}"

    # sanity: the registered judge, re-applied to the logged tool calls, must
    # reproduce every logged outcome (cells without a call are failures).
    disagreements = 0
    for r in records:
        if r.outcome == "incomplete":
            raise SystemExit("incomplete cell in the log")
        call = _tool_call(r)
        redo = judge_tool_call(call, expected[(r.language, r.example_id)]) if call else False
        if redo != (r.outcome == "pass"):
            disagreements += 1

    # (a) classify every gt failure
    gt_fail = [r for r in records if r.condition == "gt" and r.outcome == "fail"]
    by_cell: Counter[tuple[str, int, str]] = Counter()
    flags: Counter[tuple[str, str]] = Counter()
    for r in gt_fail:
        key = (r.language, r.example_id)
        fc = classify_failure(_tool_call(r), r.error_class, expected[key], arrays[key])
        by_cell[(r.language, r.run, fc.category)] += 1
        if fc.category == VALUE_MISMATCH:
            for name, on in (
                ("list_valued", fc.list_valued),
                ("devanagari", fc.devanagari),
                ("other", fc.other),
            ):
                if on:
                    flags[(r.language, name)] += 1
    classification = {
        lang: {
            "gt_cells": sum(1 for r in records if r.condition == "gt" and r.language == lang),
            "gt_failures": sum(1 for r in gt_fail if r.language == lang),
            "by_category": dict(
                Counter(c for (lg, _, c), n in by_cell.items() for _ in range(n) if lg == lang)
            ),
            "by_run": {
                str(run): {c: n for (lg, rn, c), n in by_cell.items() if lg == lang and rn == run}
                for run in (1, 2, 3)
            },
            "value_mismatch_flags": {f: n for (lg, f), n in flags.items() if lg == lang},
        }
        for lang in LANGUAGES
    }

    # (a2) list-aware re-score of every cell
    rescored: list[RunRecord] = []
    for r in records:
        call = _tool_call(r)
        ok = (
            judge_list_aware(
                call, expected[(r.language, r.example_id)], arrays[(r.language, r.example_id)]
            )
            if call
            else False
        )
        rescored.append(dataclasses.replace(r, outcome="pass" if ok else "fail"))
    registered = analyze(records)
    list_aware = analyze(rescored)
    reference = json.loads(Path("results/f1_noise_floor.json").read_text(encoding="utf-8"))

    def rate(rs: list[RunRecord], lang: str, cond: str) -> float:
        cells = [x for x in rs if x.language == lang and x.condition == cond]
        return 100 * sum(1 for x in cells if x.outcome == "pass") / len(cells)

    tasks_with_array = {
        lang: {
            "any_array_param_in_expected_call": sum(
                1
                for (lg, _), exp in expected.items()
                if lg == lang and arrays[(lg, _)] & set(exp.arguments)
            ),
            "array_param_with_two_or_more_expected_elements": sum(
                1
                for (lg, i), exp in expected.items()
                if lg == lang
                and any(len(exp.arguments[p]) >= 2 for p in arrays[(lg, i)] & set(exp.arguments))
            ),
            "of": len(manifests[lang]),
        }
        for lang in LANGUAGES
    }
    hindi_gt_deva = sum(
        1
        for r in gt_fail
        if r.language == "hindi"
        and classify_failure(
            _tool_call(r),
            r.error_class,
            expected[("hindi", r.example_id)],
            arrays[("hindi", r.example_id)],
        ).devanagari
    )

    # (c) population: unique gt value_mismatch under the list-aware judge
    population: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for r in records:
        if r.condition != "gt" or r.outcome == "incomplete":
            continue
        call = _tool_call(r)
        key = (r.language, r.example_id)
        if call is None or call.name != expected[key].name:
            continue
        if any(p not in call.arguments for p in expected[key].arguments):
            continue
        for param in mismatching_params(call, expected[key], arrays[key], list_aware=True):
            value = call.arguments[param]
            pop_key = (
                r.language,
                r.example_id,
                param,
                _normalize(json.dumps(value, ensure_ascii=False)),
            )
            population.setdefault(
                pop_key,
                {
                    "language": r.language,
                    "example_id": r.example_id,
                    "query": str(manifests[r.language][r.example_id]["query"]),
                    "function": expected[key].name,
                    "parameter": param,
                    "accepted_values": " | ".join(expected[key].arguments[param]),
                    "returned_value": json.dumps(value, ensure_ascii=False),
                },
            )
    ordered = sorted(population)
    rng = random.Random(0)
    sample: list[tuple[str, str, str, str]] = []
    shortfall: dict[str, int] = {}
    for lang in LANGUAGES:
        pool = [k for k in ordered if k[0] == lang]
        take = min(SAMPLE_PER_LANGUAGE, len(pool))
        shortfall[lang] = SAMPLE_PER_LANGUAGE - take
        sample.extend(rng.sample(pool, take))
    rng.shuffle(sample)  # the owner should not see all of one language, in key order

    Path("results").mkdir(exist_ok=True)
    Path("results/f1_judge_population.json").write_text(
        json.dumps(
            {"n": len(ordered), "items": [population[k] for k in ordered]},
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with open("results/f1_judge_labels_blank.csv", "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "item",
                "language",
                "user_query",
                "function",
                "parameter",
                "accepted_values",
                "returned_value",
                "label (equivalent / not_equivalent)",
                "note",
            ]
        )
        for n, k in enumerate(sample, start=1):
            p = population[k]
            writer.writerow(
                [
                    n,
                    p["language"],
                    p["query"],
                    p["function"],
                    p["parameter"],
                    p["accepted_values"],
                    p["returned_value"],
                    "",
                    "",
                ]
            )

    out = {
        "item": "3B-19 (a), (a2)",
        "preregistration": "docs/runs/3b-19-preregistration.md",
        "source_log": str(RUNS),
        "sanity": {
            "registered_judge_reproduces_logged_outcomes": disagreements == 0,
            "disagreements": disagreements,
            "analysis_equals_results_f1_noise_floor_json": registered == reference,
        },
        "classification_gt_failures": classification,
        "tasks_with_array_param": tasks_with_array,
        "hindi_gt_failures_with_devanagari_value": hindi_gt_deva,
        "gt_pass_rate_pct": {
            lang: {
                "registered": rate(records, lang, "gt"),
                "list_aware": rate(rescored, lang, "gt"),
            }
            for lang in LANGUAGES
        },
        "analysis_registered_exact_match": registered,
        "analysis_list_aware": list_aware,
        "labelling_sheet": {
            "population_size": len(ordered),
            "by_language": dict(Counter(k[0] for k in ordered)),
            "sampled": len(sample),
            "shortfall_vs_25_per_language": shortfall,
            "file": "results/f1_judge_labels_blank.csv",
        },
    }
    Path("results/f1_judge_audit.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: out[k]
                for k in (
                    "sanity",
                    "classification_gt_failures",
                    "tasks_with_array_param",
                    "hindi_gt_failures_with_devanagari_value",
                    "gt_pass_rate_pct",
                    "labelling_sheet",
                )
            },
            indent=1,
            ensure_ascii=False,
        )
    )
    for name, res in (("registered", registered), ("list-aware", list_aware)):
        print(f"\n[{name}]")
        for lang, la in res["languages"].items():
            print(f"  {lang}: noise floor {la['noise_floor_pp']:.1f} pp")
            for cond, arm in la["arms"].items():
                lo, hi = arm["loss_ci_pp"]
                a, b = arm["majority_gt_pass_real_fail"], arm["majority_gt_fail_real_pass"]
                print(
                    f"    {cond}: loss {arm['mean_loss_pp']:.1f} pp [{lo:.1f}, {hi:.1f}] "
                    f"McNemar {a}/{b} p={arm['mcnemar_p']:.3g} -> {arm['verdict']}"
                )


if __name__ == "__main__":
    main()
