"""Combines F1's `AblationReport` and F2's `EerReport` into the milestone
framing from `ROADMAP.md` Phase 2: "the agent loses X% of task success to
transcription alone, and `dhvani-entity` recovers Y% of it."
"""

from __future__ import annotations

from dhvani.eval.entity_error_rate import EerReport
from dhvani.eval.task_success import AblationReport


def render_milestone_report(ablation: AblationReport, eer: EerReport | None) -> str:
    """Renders a short markdown summary for the README.

    `eer` is optional: F1 can be reported alone (e.g. before F2's real
    dataset access lands) while still being honest about what's missing.
    """
    lines = ["## Phase 2 milestone", ""]
    lines.append(
        "**Caveat carried on every number below:** VoiceAgentBench's audio is "
        "synthesized (TTS over text queries), so the ASR penalty measured here "
        "is a lower bound on the real-world penalty, not an estimate of it."
    )
    lines.append("")

    lines.append("### F1 -- task success lost to transcription")
    lines.append("")
    lines.append("| language | n | ground truth | real ASR | loss to ASR |")
    lines.append("|---|---|---|---|---|")
    for language, result in ablation.per_language.items():
        loss = result.success_rate_ground_truth - result.success_rate_real_asr
        lines.append(
            f"| {language} | {result.n} | {result.success_rate_ground_truth:.1%} "
            f"| {result.success_rate_real_asr:.1%} | {loss:.1%} |"
        )
    lines.append("")

    if eer is None:
        lines.append("### F2 -- not yet run (waiting on Hugging Face access to Svarah/LAHAJA)")
        return "\n".join(lines)

    lines.append(f"### F2 -- entity recovery (`{eer.split}` split, threshold={eer.threshold})")
    lines.append("")
    lines.append(
        f"- {eer.n_entity_mentions} lexicon entity mentions found across the evaluated set"
    )
    lines.append(f"- Entity Error Rate before correction: {eer.eer_before:.1%}")
    lines.append(f"- Entity Error Rate after correction: {eer.eer_after:.1%}")
    lines.append(
        f"- Corruption rate on {eer.n_clean_examples} entity-free examples: "
        f"{eer.corruption_rate:.1%}"
    )
    lines.append("")

    eer_recovery = eer.eer_before - eer.eer_after
    for language, result in ablation.per_language.items():
        gap = result.success_rate_ground_truth - result.success_rate_real_asr
        if gap <= 0 or result.success_rate_corrected_asr is None:
            continue
        recovered_share = (result.success_rate_corrected_asr - result.success_rate_real_asr) / gap
        lines.append(
            f"- {language}: `dhvani-entity` recovers {recovered_share:.1%} of the task-success "
            f"gap lost to ASR"
        )
    if eer_recovery:
        lines.append(f"- Entity-level recovery: {eer_recovery:.1%} of the pre-correction EER")

    return "\n".join(lines)
