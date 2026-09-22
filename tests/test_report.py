from __future__ import annotations

from dhvani.eval.entity_error_rate import EerReport
from dhvani.eval.report import render_milestone_report
from dhvani.eval.task_success import AblationReport, LanguageResult


def _ablation(gt: float, real: float, corrected: float | None = None) -> AblationReport:
    return AblationReport(
        per_language={
            "hindi": LanguageResult(
                n=40,
                success_rate_ground_truth=gt,
                success_rate_real_asr=real,
                success_rate_corrected_asr=corrected,
            )
        }
    )


def test_report_without_eer_notes_it_is_missing() -> None:
    report = render_milestone_report(_ablation(0.8, 0.6), eer=None)
    assert "not yet run" in report
    assert "F1" in report


def test_report_includes_f1_numbers() -> None:
    report = render_milestone_report(_ablation(0.8, 0.6), eer=None)
    assert "80.0%" in report
    assert "60.0%" in report


def test_report_includes_eer_numbers_when_given() -> None:
    eer = EerReport(
        split="test",
        threshold=0.82,
        n_entity_mentions=120,
        eer_before=0.4,
        eer_after=0.1,
        n_clean_examples=50,
        corruption_rate=0.02,
    )
    report = render_milestone_report(_ablation(0.8, 0.6), eer=eer)
    assert "120" in report
    assert "40.0%" in report
    assert "10.0%" in report
    assert "2.0%" in report


def test_report_computes_recovered_share_when_corrected_rate_given() -> None:
    eer = EerReport(
        split="test",
        threshold=0.82,
        n_entity_mentions=100,
        eer_before=0.4,
        eer_after=0.1,
        n_clean_examples=50,
        corruption_rate=0.0,
    )
    # ground_truth=0.8, real=0.6 (gap=0.2), corrected=0.7 -> recovers half the gap
    report = render_milestone_report(_ablation(0.8, 0.6, corrected=0.7), eer=eer)
    assert "50.0%" in report


def test_report_skips_recovery_line_when_no_gap() -> None:
    eer = EerReport(
        split="test",
        threshold=0.82,
        n_entity_mentions=10,
        eer_before=0.0,
        eer_after=0.0,
        n_clean_examples=5,
        corruption_rate=0.0,
    )
    report = render_milestone_report(_ablation(0.5, 0.5, corrected=0.5), eer=eer)
    assert "recovers" not in report
