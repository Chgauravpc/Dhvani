"""3B-15 -- the three-way F2 table: raw / exact lookup / exact + fuzzy, per arm.

    uv run python scripts/f2_three_way_table.py

Reads the committed F2 transcript logs (no API call) and scores the **test**
split of each of the four 3B-4 arms with the *shipped* `EntityCorrector`
modes -- `mode="exact"` (the default) and `mode="fuzzy"` (exact, then the
fuzzy windows at the arm's dev-chosen threshold, from the committed
`results/f2_eer_*.json`). Per column: recognition error, canonical miss,
corruption on clean rows, each with a 95% Wilson interval; and the two paired
comparisons that decide what each layer is worth -- exact lookup over raw, and
the **fuzzy layer over exact lookup** (fixed / broken mentions, exact McNemar).

Writes `results/f2_three_way.json`. Self-check: the rates must equal the
3B-14 re-score (`results/f2_rescore.json`); `sanity.matches_f2_rescore` says so.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dhvani.entity.corrector import EntityCorrector
from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.entity.mentions import contains_variant, mentioned_entities
from dhvani.eval.stats import mcnemar_exact_p, wilson_interval
from dhvani.eval.transcript_log import TranscriptRecord, read_transcripts

ARMS = (
    ("svarah", "whisper"),
    ("svarah", "sarvam"),
    ("indicvoices-hindi", "whisper"),
    ("indicvoices-hindi", "sarvam"),
)
COLUMNS = ("raw", "exact", "exact_plus_fuzzy")


def _rate(k: int, n: int) -> dict[str, Any]:
    lo, hi = wilson_interval(k, n)
    return {"k": k, "n": n, "rate": k / n if n else 0.0, "ci95": [lo, hi]}


def _paired(before: list[bool], after: list[bool]) -> dict[str, Any]:
    fixed = sum(1 for b, a in zip(before, after, strict=True) if a and not b)
    broken = sum(1 for b, a in zip(before, after, strict=True) if b and not a)
    return {"fixed": fixed, "broken": broken, "mcnemar_p": mcnemar_exact_p(fixed, broken)}


def score_arm(dataset: str, stt: str) -> dict[str, Any]:
    committed = json.loads(Path(f"results/f2_eer_{dataset}_{stt}.json").read_text(encoding="utf-8"))
    threshold = float(committed["chosen_threshold"])
    correctors = {
        "exact": EntityCorrector(DEFAULT_LEXICON, mode="exact"),
        "exact_plus_fuzzy": EntityCorrector(DEFAULT_LEXICON, threshold=threshold, mode="fuzzy"),
    }
    latest = {
        r.key(): r for r in read_transcripts(Path(f"results/transcripts/f2_{dataset}_{stt}.jsonl"))
    }
    test = [r for r in latest.values() if r.split == "test"]

    recognised: dict[str, list[bool]] = {c: [] for c in COLUMNS}
    canonical: dict[str, list[bool]] = {c: [] for c in COLUMNS}
    corrupted: dict[str, list[bool]] = {c: [] for c in ("exact", "exact_plus_fuzzy")}

    def texts(r: TranscriptRecord) -> dict[str, str]:
        return {"raw": r.raw_text} | {c: k.correct(r.raw_text).text for c, k in correctors.items()}

    for r in test:
        mentioned = mentioned_entities(r.ground_truth_text, DEFAULT_LEXICON)
        out = texts(r)
        if mentioned:
            seen = {c: mentioned_entities(out[c], DEFAULT_LEXICON) for c in COLUMNS}
            for entity in sorted(mentioned):
                for c in COLUMNS:
                    recognised[c].append(entity in seen[c])
                    canonical[c].append(contains_variant(out[c], entity))
        else:
            for c in corrupted:
                corrupted[c].append(out[c] != r.raw_text)

    n = len(recognised["raw"])
    n_clean = len(corrupted["exact"])
    columns = {
        c: {
            "recognition_error": _rate(n - sum(recognised[c]), n),
            "canonical_miss": _rate(n - sum(canonical[c]), n),
            "corruption_on_clean_rows": _rate(sum(corrupted[c]), n_clean)
            if c in corrupted
            else None,
        }
        for c in COLUMNS
    }
    return {
        "dataset": dataset,
        "stt": stt,
        "fuzzy_threshold": threshold,
        "n_test_mentions": n,
        "n_test_clean_rows": n_clean,
        "columns": columns,
        "paired": {
            "exact_over_raw": {
                "recognition": _paired(recognised["raw"], recognised["exact"]),
                "canonical": _paired(canonical["raw"], canonical["exact"]),
            },
            "fuzzy_layer_over_exact": {
                "recognition": _paired(recognised["exact"], recognised["exact_plus_fuzzy"]),
                "canonical": _paired(canonical["exact"], canonical["exact_plus_fuzzy"]),
                "extra_corrupted_clean_rows": sum(corrupted["exact_plus_fuzzy"])
                - sum(corrupted["exact"]),
            },
        },
    }


def main() -> None:
    arms = {f"{d}/{s}": score_arm(d, s) for d, s in ARMS}
    rescore = json.loads(Path("results/f2_rescore.json").read_text(encoding="utf-8"))
    matches = True
    for name, arm in arms.items():
        ref = rescore["arms"][name]["test"]
        for col, key in (("exact", "exact_lookup"), ("exact_plus_fuzzy", "exact_then_fuzzy")):
            c = arm["columns"][col]
            matches &= (
                abs(c["recognition_error"]["rate"] - ref[key]["recognition_eer_after"]) < 1e-12
            )
            matches &= abs(c["canonical_miss"]["rate"] - ref[key]["canonical_miss_after"]) < 1e-12
            matches &= (
                abs(c["corruption_on_clean_rows"]["rate"] - ref[key]["corruption_rate"]) < 1e-12
            )
    out = {
        "item": "3B-15",
        "note": (
            "Test split of the four 3B-4 arms, scored with the shipped EntityCorrector modes. "
            "Fuzzy threshold per arm is the committed dev-chosen one (results/f2_eer_*.json); "
            "the exact column has no parameter. Intervals are Wilson 95% and, like the McNemar "
            "tests, treat mentions as independent, which the clustered samples do not satisfy."
        ),
        "sanity": {"matches_f2_rescore": bool(matches)},
        "arms": arms,
    }
    Path("results/f2_three_way.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    def cell(x: dict[str, Any] | None) -> str:
        if x is None:
            return "     -     "
        lo, hi = x["ci95"]
        return f"{x['rate']:6.1%} [{lo:4.1%},{hi:5.1%}]"

    print(f"sanity.matches_f2_rescore = {matches}")
    for name, arm in arms.items():
        head = f"{arm['n_test_mentions']} mentions, {arm['n_test_clean_rows']} clean rows"
        print(f"\n== {name}  n={head}, fuzzy threshold {arm['fuzzy_threshold']}")
        titles = ("recognition error", "canonical miss", "corruption (clean)")
        print(f"   {'':17s}{titles[0]:>24s}{titles[1]:>26s}{titles[2]:>26s}")
        for col in COLUMNS:
            c = arm["columns"][col]
            print(
                f"   {col:17s}{cell(c['recognition_error']):>24s}{cell(c['canonical_miss']):>26s}"
                f"{cell(c['corruption_on_clean_rows']):>26s}"
            )
        p = arm["paired"]
        for label, key in (
            ("exact over raw", "exact_over_raw"),
            ("fuzzy over exact", "fuzzy_layer_over_exact"),
        ):
            r, k = p[key]["recognition"], p[key]["canonical"]
            print(
                f"   {label:17s} recognition +{r['fixed']}/-{r['broken']} (p={r['mcnemar_p']:.3g})"
                f"   canonical +{k['fixed']}/-{k['broken']} (p={k['mcnemar_p']:.3g})"
            )
        print(
            f"   fuzzy layer corrupts {p['fuzzy_layer_over_exact']['extra_corrupted_clean_rows']} "
            f"more clean rows than exact lookup"
        )
    print("\nwrote results/f2_three_way.json")


if __name__ == "__main__":
    main()
