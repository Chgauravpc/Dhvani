"""3B-21 scoring: WER on real telephone Hindi vs the same ASR's clean read-Hindi WER.

    uv run python scripts/score_gramvaani.py     # -> results/f3_gramvaani.json

Protocol: `docs/runs/3b-21-preregistration.md` sections 4 and 6. References are re-read
from the extracted `GV_Dev_5h` archive (not committed). Per ASR with a hypothesis log:
corpus WER raw and number-normalised with a 95% bootstrap interval over utterances
(10,000 resamples, seed 0), the same ASR's clean IndicVoices WER (`results/f2_digits.json`,
all rows), the gap, and the preregistered outcome row. No API call.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from preflight_3b21 import DEFAULT_DIR, read_references

from dhvani.eval.numbers import to_digit_tokens
from dhvani.eval.wer import corpus_wer

ASRS = {"sarvam": "indicvoices-hindi/sarvam", "groq-whisper": "indicvoices-hindi/groq-whisper"}


def _per_utterance(pairs: list[tuple[str, str]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for ref, hyp in pairs:
        r = corpus_wer([(ref, hyp)])
        out.append((r.substitutions + r.deletions + r.insertions, r.reference_words))
    return out


def _wer_ci(per: list[tuple[int, int]], resamples: int = 10_000) -> dict[str, Any]:
    rng = random.Random(0)
    n = len(per)
    values = []
    for _ in range(resamples):
        sample = [per[rng.randrange(n)] for _ in range(n)]
        words = sum(w for _, w in sample)
        values.append(sum(e for e, _ in sample) / words if words else 0.0)
    values.sort()
    errors, words = sum(e for e, _ in per), sum(w for _, w in per)
    return {
        "wer": errors / words,
        "ci95": [values[int(0.025 * resamples)], values[int(0.975 * resamples) - 1]],
        "reference_words": words,
        "utterances": n,
    }


def _outcome(gap_pp: float) -> str:
    if gap_pp >= 10:
        return "far above the clean rows"
    if gap_pp <= 5:
        return "close to the clean rows"
    return "moderately above the clean rows"


def main() -> None:
    refs = read_references(DEFAULT_DIR)
    sample = json.loads(Path("results/gramvaani_sample.json").read_text("utf-8"))["items"]
    clean = json.loads(Path("results/f2_digits.json").read_text("utf-8"))["arms"]
    channel = json.loads(Path("results/f3_channel_sarvam.json").read_text("utf-8"))
    codec_pp = 100 * (
        channel["datasets"]["indicvoices-hindi"]["wer"]["pstn_number_normalised"]
        - channel["datasets"]["indicvoices-hindi"]["wer"]["clean_number_normalised"]
    )
    out: dict[str, Any] = {
        "item": "3B-21",
        "preregistration": "docs/runs/3b-21-preregistration.md",
        "note": (
            "Real telephone Hindi (Gram Vaani, OpenSLR 118 dev), 221 utterances, not paired "
            "with the clean rows; dialect, spontaneity and channel are confounded. Bootstrap "
            "over utterances."
        ),
        "codec_share_pp_3b18_saaras_hindi_normalised": codec_pp,
        "arms": {},
    }
    for stt, arm in ASRS.items():
        path = Path(f"results/transcripts/f3_gramvaani_{stt}.jsonl")
        if not path.exists():
            continue
        hyps = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                hyps[rec["uttid"]] = rec["raw_text"]
        items = [i["uttid"] for i in sample if i["uttid"] in hyps]
        raw = [(refs[u], hyps[u]) for u in items]
        norm = [(to_digit_tokens(r), to_digit_tokens(h)) for r, h in raw]
        w_raw, w_norm = _wer_ci(_per_utterance(raw)), _wer_ci(_per_utterance(norm))
        clean_w = clean[arm]["wer_all_rows"]
        gap = 100 * (w_norm["wer"] - clean_w["number_normalised"])
        out["arms"][stt] = {
            "complete": len(items) == len(sample),
            "telephone_raw": w_raw,
            "telephone_number_normalised": w_norm,
            "clean_rows_raw_wer": clean_w["raw"],
            "clean_rows_number_normalised_wer": clean_w["number_normalised"],
            "gap_normalised_pp": gap,
            "outcome_row": _outcome(gap),
            "broken_baseline_on_clean_rows": stt == "groq-whisper",
        }
        print(
            f"{stt:13s} {len(items)}/{len(sample)} utterances  WER raw {w_raw['wer']:.1%} "
            f"normalised {w_norm['wer']:.1%} [{w_norm['ci95'][0]:.1%}, {w_norm['ci95'][1]:.1%}]  "
            f"clean-rows normalised {clean_w['number_normalised']:.1%}  gap {gap:+.1f} pp "
            f"-> {_outcome(gap)}"
        )
    Path("results/f3_gramvaani.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"codec share (3B-18, Saaras Hindi, normalised): {codec_pp:+.1f} pp")


if __name__ == "__main__":
    main()
