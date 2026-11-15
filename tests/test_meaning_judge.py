from __future__ import annotations

import pytest

from dhvani.eval.meaning_judge import (
    JudgeItem,
    agreement,
    build_messages,
    cohens_kappa,
    parse_verdict,
)


def test_parse_verdict_accepts_json_and_wrapped_json() -> None:
    assert parse_verdict('{"equivalent": true}') is True
    assert parse_verdict('Sure: {"equivalent": false} done') is False


@pytest.mark.parametrize("text", [None, "", "yes", '{"equivalent": "true"}', '{"other": 1}'])
def test_parse_verdict_rejects_anything_else(text: str | None) -> None:
    assert parse_verdict(text) is None


def test_messages_show_only_the_prereg_fields() -> None:
    item = JudgeItem("q?", "get_x", "city", "Chennai", '"Velachery"')
    system, user = build_messages(item)
    assert system["role"] == "system" and "equivalent" in system["content"]
    for part in ("q?", "get_x", "city", "Chennai", '"Velachery"'):
        assert part in user["content"]
    assert "whisper" not in user["content"].lower() and "pass" not in user["content"].lower()


def test_kappa_known_values() -> None:
    assert cohens_kappa([True, False, True, False], [True, False, True, False]) == 1.0
    assert cohens_kappa([True, True, False, False], [True, False, True, False]) == 0.0
    assert cohens_kappa([True, True], [True, True]) == 1.0


def test_agreement_counts_and_ci_contain_point_estimate() -> None:
    judge = [True] * 6 + [False] * 4
    owner = [True] * 5 + [False] * 5
    out = agreement(judge, owner, resamples=500)
    assert out["judge_yes_owner_no"] == 1 and out["judge_no_owner_yes"] == 0
    assert out["raw_agreement"] == 0.9
    lo, hi = out["kappa_ci95"]
    assert lo <= out["kappa"] <= hi
