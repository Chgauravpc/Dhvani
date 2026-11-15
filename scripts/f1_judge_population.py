"""The 3B-19 judged population, shared by the runner and the analysis.

Every `value_mismatch` parameter under the list-aware judge, across all three
conditions of the 3B-5 log, de-duplicated on (language, example, parameter,
normalised returned value) -- preregistration section 8, deviation 1.
No API call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from huggingface_hub import hf_hub_download

from dhvani.eval.datasets import _parse_expected_tool_call
from dhvani.eval.judge_audit import array_params, mismatching_params
from dhvani.eval.meaning_judge import JudgeItem
from dhvani.eval.noise_floor import RunLog
from dhvani.eval.task_success import _normalize
from dhvani.types import ToolCall

REPO = "krutrim-ai-labs/VoiceAgentBench"
RUNS = Path("results/f1_runs/runs.jsonl")
LANGUAGES = ("english", "hindi")

Key = tuple[str, str, str, str]


def item_key(key: Key) -> str:
    return "|".join(key)


def build_population() -> dict[Key, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for lang in LANGUAGES:
        path = hf_hub_download(
            REPO, f"data/single_tool_data/{lang}/single_tool_{lang}.json", repo_type="dataset"
        )
        manifests[lang] = {str(r["id"]): r for r in json.loads(Path(path).read_text("utf-8"))}
    population: dict[Key, dict[str, Any]] = {}
    for r in RunLog(RUNS).records():
        if r.tool_call is None or r.outcome == "incomplete":
            continue
        raw = manifests[r.language][r.example_id]
        expected = _parse_expected_tool_call(raw["expected_tool_call"])
        arrays = array_params(raw["functions"], expected.name)
        call = ToolCall(
            id="", name=str(r.tool_call["name"]), arguments=dict(r.tool_call["arguments"])
        )
        if call.name != expected.name or any(p not in call.arguments for p in expected.arguments):
            continue
        for param in mismatching_params(call, expected, arrays, list_aware=True):
            value = call.arguments[param]
            key: Key = (
                r.language,
                r.example_id,
                param,
                _normalize(json.dumps(value, ensure_ascii=False)),
            )
            population.setdefault(
                key,
                {
                    "language": r.language,
                    "example_id": r.example_id,
                    "parameter": param,
                    "item": JudgeItem(
                        query=str(raw["query"]),
                        function=expected.name,
                        parameter=param,
                        accepted_values=" | ".join(expected.arguments[param]),
                        returned_value=json.dumps(value, ensure_ascii=False),
                    ),
                },
            )
    return population
