"""3B-14 -- re-score the four committed F2 transcript logs, no API call.

    uv run python scripts/rescore_f2_transcripts.py

Turns the Nov 14 review's throwaway numbers (phase-3b section 11.1, B1-B4)
into a committed results file, `results/f2_rescore.json`, per arm
(Svarah / IndicVoices Hindi x Whisper small / Saaras):

- corpus WER (existing `eval.wer`, unchanged -- see B6: digit formatting
  inflates Hindi WER until 3B-17) overall, on test, on entity and clean rows;
- the script each output is written in (dominant letter script per row);
- recognition / canonical rates per entity (test split);
- an **exact-lookup baseline**: replace word-bounded curated variants by their
  canonical form (`dhvani.entity.exact`), no phonetic matching;
- the fuzzy corrector at the dev-chosen threshold, and **exact then fuzzy**;
- what the fuzzy layer adds over exact lookup, and the false-rewrite list on
  the clean test rows.

Self-check: the fuzzy corrector's test report here must equal the committed
`results/f2_eer_*.json` test block; `sanity.reproduces_committed_results`
says whether it does.
"""

from __future__ import annotations

import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from dhvani.entity.corrector import EntityCorrector
from dhvani.entity.exact import canonicalise_exact
from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.entity.mentions import contains_variant, mentioned_entities
from dhvani.eval.entity_error_rate import TranscribedExample, score_transcripts
from dhvani.eval.transcript_log import TranscriptRecord, read_transcripts
from dhvani.eval.wer import corpus_wer

ARMS = (
    ("svarah", "whisper"),
    ("svarah", "sarvam"),
    ("indicvoices-hindi", "whisper"),
    ("indicvoices-hindi", "sarvam"),
)
REPORT_KEYS = (
    "n_entity_mentions",
    "recognition_eer_before",
    "recognition_eer_after",
    "canonical_miss_before",
    "canonical_miss_after",
    "n_clean_examples",
    "corruption_rate",
    "recognition_fixed",
    "recognition_broken",
    "canonical_fixed",
    "canonical_broken",
    "n_corrupted",
)


class _Exact:
    """Adapter so `score_transcripts` can score exact lookup."""

    threshold = 0.0

    def correct(self, text: str) -> Any:
        return canonicalise_exact(text, DEFAULT_LEXICON)


class _Layered:
    """Exact lookup first, then the fuzzy windows over its output."""

    def __init__(self, fuzzy: EntityCorrector) -> None:
        self._fuzzy = fuzzy
        self.threshold = fuzzy.threshold

    def correct(self, text: str) -> Any:
        return self._fuzzy.correct(canonicalise_exact(text, DEFAULT_LEXICON).text)


def dominant_script(text: str) -> str:
    counts: Counter[str] = Counter()
    for ch in text:
        if unicodedata.category(ch).startswith("L"):
            counts[unicodedata.name(ch, "UNKNOWN").split()[0]] += 1
    return counts.most_common(1)[0][0].lower() if counts else "none"


def _wer(rows: list[TranscriptRecord]) -> dict[str, Any]:
    result = corpus_wer([(r.ground_truth_text, r.raw_text) for r in rows])
    return {"wer": result.wer, "reference_words": result.reference_words, "n_rows": len(rows)}


def _report(report: Any, *, has_threshold: bool) -> dict[str, Any]:
    out = {key: getattr(report, key) for key in REPORT_KEYS}
    out["threshold"] = report.threshold if has_threshold else None
    return out


def rescore_arm(dataset: str, stt: str) -> dict[str, Any]:
    log_path = Path(f"results/transcripts/f2_{dataset}_{stt}.jsonl")
    committed = json.loads(Path(f"results/f2_eer_{dataset}_{stt}.json").read_text(encoding="utf-8"))
    latest = {r.key(): r for r in read_transcripts(log_path)}
    rows = list(latest.values())
    test = [r for r in rows if r.split == "test"]
    threshold = float(committed["chosen_threshold"])
    fuzzy = EntityCorrector(DEFAULT_LEXICON, threshold=threshold)

    def transcribed(rs: list[TranscriptRecord]) -> list[TranscribedExample]:
        return [TranscribedExample(r.ground_truth_text, r.raw_text) for r in rs]

    fuzzy_report = score_transcripts(transcribed(test), DEFAULT_LEXICON, fuzzy, "test")  # type: ignore[arg-type]
    exact_report = score_transcripts(transcribed(test), DEFAULT_LEXICON, _Exact(), "test")  # type: ignore[arg-type]
    layered_report = score_transcripts(
        transcribed(test),
        DEFAULT_LEXICON,
        _Layered(fuzzy),  # type: ignore[arg-type]
        "test",
    )
    reproduces = all(
        abs(getattr(fuzzy_report, k) - committed["test"][k]) < 1e-12
        for k in REPORT_KEYS
        if k in committed["test"]
    )

    entity_rows = [r for r in test if mentioned_entities(r.ground_truth_text, DEFAULT_LEXICON)]
    clean_rows = [r for r in test if not mentioned_entities(r.ground_truth_text, DEFAULT_LEXICON)]

    per_entity: dict[str, dict[str, int]] = {}
    fuzzy_adds = fuzzy_breaks = 0
    for r in entity_rows:
        exact_text = canonicalise_exact(r.raw_text, DEFAULT_LEXICON).text
        layered_text = fuzzy.correct(exact_text).text
        recognised = mentioned_entities(r.raw_text, DEFAULT_LEXICON)
        for canonical in mentioned_entities(r.ground_truth_text, DEFAULT_LEXICON):
            row = per_entity.setdefault(
                canonical,
                {"mentions": 0, "recognised_raw": 0, "canonical_raw": 0, "canonical_exact": 0},
            )
            row["mentions"] += 1
            row["recognised_raw"] += canonical in recognised
            row["canonical_raw"] += contains_variant(r.raw_text, canonical)
            after_exact = contains_variant(exact_text, canonical)
            row["canonical_exact"] += after_exact
            after_layered = contains_variant(layered_text, canonical)
            fuzzy_adds += after_layered and not after_exact
            fuzzy_breaks += after_exact and not after_layered

    false_fuzzy: list[dict[str, Any]] = []
    false_exact: list[dict[str, Any]] = []
    for r in clean_rows:
        fuzzy_result = fuzzy.correct(r.raw_text)
        if fuzzy_result.text != r.raw_text:
            false_fuzzy.append(
                {
                    "example_id": r.example_id,
                    "rewrites": [
                        {"from": c.original, "to": c.corrected} for c in fuzzy_result.corrections
                    ],
                }
            )
        exact_result = canonicalise_exact(r.raw_text, DEFAULT_LEXICON)
        if exact_result.text != r.raw_text:
            false_exact.append(
                {
                    "example_id": r.example_id,
                    "rewrites": [
                        {"from": w.original, "to": w.canonical} for w in exact_result.rewrites
                    ],
                }
            )

    return {
        "dataset": dataset,
        "stt": stt,
        "model": rows[0].model,
        "transcript_log": str(log_path),
        "n_rows": len(rows),
        "n_rows_by_split": dict(Counter(r.split for r in rows)),
        "wer": {
            "all_rows": _wer(rows),
            "test_rows": _wer(test),
            "test_entity_rows": _wer(entity_rows),
            "test_clean_rows": _wer(clean_rows),
        },
        "output_script_rows": {
            "all_rows": dict(Counter(dominant_script(r.raw_text) for r in rows)),
            "test_rows": dict(Counter(dominant_script(r.raw_text) for r in test)),
        },
        "empty_outputs": sum(1 for r in rows if not r.raw_text.strip()),
        "sanity": {"reproduces_committed_results": reproduces, "chosen_threshold": threshold},
        "test": {
            "raw_vs_fuzzy_as_committed": _report(fuzzy_report, has_threshold=True),
            "exact_lookup": _report(exact_report, has_threshold=False),
            "exact_then_fuzzy": _report(layered_report, has_threshold=True),
            "fuzzy_layer_over_exact": {
                "mentions_made_canonical_by_fuzzy_beyond_exact": fuzzy_adds,
                "mentions_broken_by_fuzzy_after_exact": fuzzy_breaks,
            },
        },
        "per_entity_test": dict(sorted(per_entity.items())),
        "false_rewrites_test_clean_rows": {
            "n_clean_rows": len(clean_rows),
            "fuzzy_at_chosen_threshold": {"n": len(false_fuzzy), "rows": false_fuzzy},
            "exact_lookup": {"n": len(false_exact), "rows": false_exact},
        },
    }


def main() -> None:
    arms = {f"{d}/{s}": rescore_arm(d, s) for d, s in ARMS}
    out = {
        "item": "3B-14",
        "note": (
            "Re-score of the committed F2 transcript logs; no API call. WER uses eval.wer "
            "unchanged (digit formatting inflates Hindi WER, phase-3b 11.1 B6, until 3B-17)."
        ),
        "arms": arms,
    }
    Path("results/f2_rescore.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    for name, arm in arms.items():
        t = arm["test"]
        w = arm["wer"]
        print(
            f"\n== {name}  rows {arm['n_rows']}  reproduces committed: "
            f"{arm['sanity']['reproduces_committed_results']}"
        )
        print(
            f"   WER all {w['all_rows']['wer']:.1%}  test {w['test_rows']['wer']:.1%}  "
            f"scripts(all) {arm['output_script_rows']['all_rows']}  empty {arm['empty_outputs']}"
        )
        for label in ("raw_vs_fuzzy_as_committed", "exact_lookup", "exact_then_fuzzy"):
            r = t[label]
            recog = f"{r['recognition_eer_before']:.1%}->{r['recognition_eer_after']:.1%}"
            canon = f"{r['canonical_miss_before']:.1%}->{r['canonical_miss_after']:.1%}"
            print(
                f"   {label:26s} n={r['n_entity_mentions']}  recog {recog}  canon {canon}  "
                f"corrupt {r['corruption_rate']:.1%} ({r['n_corrupted']}/{r['n_clean_examples']})"
            )
        print(f"   fuzzy over exact: {t['fuzzy_layer_over_exact']}")
    print("\nwrote results/f2_rescore.json")


if __name__ == "__main__":
    main()
