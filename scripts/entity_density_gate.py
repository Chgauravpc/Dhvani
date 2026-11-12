"""Phase 2 spec section 2A entity-density gate, re-run under phase-3b 3B-1.

F2's headline number is an Entity Error Rate over the examples in Svarah
and LAHAJA whose transcripts mention a lexicon entity. Neither dataset was
built around civic terminology, so this is a go/no-go gate: an EER over
eight mentions is not a result.

    uv run python scripts/entity_density_gate.py [--out results/entity_density_gate.json]

Counts with the shared word-bounded definition in `dhvani.entity.mentions`
(the one the EER scorer and dataset filter also use), and reports the two
superseded counting methods beside it so the change is visible rather than
silently overwritten (phase-3b rule 0.2.6):

- `legacy_raw_occurrences` -- what this script reported before 3B-1:
  `text.lower().count(variant)` summed over every variant (substring, raw
  occurrences, a variant contained in a longer variant counted twice).
- `substring_pairs` -- unique (example, entity) pairs under the old
  substring test the scorer used.
- `word_boundary_pairs` -- unique (example, entity) pairs, word-bounded,
  longest variant wins. **The gate decides on this one.**

Every substring-only (example, entity) hit is written out with its
surrounding text, so each false hit can be checked by eye.

Downloads manifests only (text columns), never audio. Needs a Hugging Face
login that has accepted both datasets' gated-access terms (`HF_TOKEN` or
`huggingface-cli login`).

Decision rule (spec section 2A), applied per dataset:
- >=100 word-boundary pairs: proceed as planned.
- 30-100: proceed, but report a confidence interval and expand the lexicon
  toward whatever terms the data actually contains.
- <30: stop and change corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.entity.mentions import find_mentions, mentioned_entities, substring_mentioned_entities
from dhvani.eval.datasets import load_lahaja_ground_truth_texts, load_svarah_ground_truth_texts

_CONTEXT_CHARS = 30


def _decision(total: int) -> str:
    if total >= 100:
        return "PROCEED (>=100)"
    if total >= 30:
        return "PROCEED_WITH_CI_AND_LEXICON_EXPANSION (30-100)"
    return "STOP_CHANGE_CORPUS (<30)"


def _legacy_raw_occurrences(texts: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        lowered = text.lower()
        for canonical, _script, variant in DEFAULT_LEXICON.all_variants():
            counts[canonical] += lowered.count(variant.lower())
    return counts


def _substring_only_examples(index: int, text: str, entities: set[str]) -> list[dict[str, Any]]:
    """For each entity that only the substring rule found, the first place
    one of its variants occurs, with context -- the evidence a reader needs
    to judge the false hit."""
    lowered = text.lower()
    out = []
    for canonical in sorted(entities):
        entry = DEFAULT_LEXICON.find(canonical)
        assert entry is not None
        for variants in entry.variants.values():
            hit = next((v for v in variants if v.lower() in lowered), None)
            if hit is not None:
                pos = lowered.index(hit.lower())
                lo, hi = max(0, pos - _CONTEXT_CHARS), pos + len(hit) + _CONTEXT_CHARS
                out.append(
                    {"row": index, "entity": canonical, "variant": hit, "context": text[lo:hi]}
                )
                break
    return out


def analyse(name: str, texts: list[str]) -> dict[str, Any]:
    legacy = _legacy_raw_occurrences(texts)
    substring: Counter[str] = Counter()
    bounded: Counter[str] = Counter()
    variant_hits: Counter[str] = Counter()
    examples_with_mention = 0
    substring_only: list[dict[str, Any]] = []

    for i, text in enumerate(texts):
        sub = substring_mentioned_entities(text, DEFAULT_LEXICON)
        wb = mentioned_entities(text, DEFAULT_LEXICON)
        substring.update(sub)
        bounded.update(wb)
        for m in find_mentions(text, DEFAULT_LEXICON):
            variant_hits[f"{m.canonical} :: {m.variant}"] += 1
        if wb:
            examples_with_mention += 1
        substring_only.extend(_substring_only_examples(i, text, sub - wb))

    entities = sorted(
        {e.canonical for e in DEFAULT_LEXICON},
        key=lambda c: (-bounded[c], -substring[c], c),
    )
    per_entity = [
        {
            "entity": c,
            "legacy_raw_occurrences": legacy[c],
            "substring_pairs": substring[c],
            "word_boundary_pairs": bounded[c],
        }
        for c in entities
    ]
    total_wb = sum(bounded.values())
    digest = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()
    return {
        "dataset": name,
        "n_transcripts": len(texts),
        "transcripts_sha256": digest,
        "totals": {
            "legacy_raw_occurrences": sum(legacy.values()),
            "substring_pairs": sum(substring.values()),
            "word_boundary_pairs": total_wb,
        },
        "examples_with_word_boundary_mention": examples_with_mention,
        "decision": _decision(total_wb),
        "per_entity": per_entity,
        "word_boundary_variant_hits": dict(variant_hits.most_common()),
        "substring_only_hits": substring_only,
    }


def _print(result: dict[str, Any]) -> None:
    t = result["totals"]
    print(f"\n{result['dataset']}: {result['n_transcripts']} transcripts")
    print(f"  {'entity':<28}{'legacy':>8}{'substr':>8}{'word-b':>8}")
    for row in result["per_entity"]:
        if row["legacy_raw_occurrences"] or row["substring_pairs"]:
            print(
                f"  {row['entity']:<28}{row['legacy_raw_occurrences']:>8}"
                f"{row['substring_pairs']:>8}{row['word_boundary_pairs']:>8}"
            )
    print(
        f"  {'TOTAL':<28}{t['legacy_raw_occurrences']:>8}"
        f"{t['substring_pairs']:>8}{t['word_boundary_pairs']:>8}"
    )
    print(f"  -> {result['decision']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("results/entity_density_gate.json"))
    args = parser.parse_args()

    results = []
    for name, loader in (
        ("Svarah", load_svarah_ground_truth_texts),
        ("LAHAJA", load_lahaja_ground_truth_texts),
    ):
        print(f"Downloading {name} ground-truth transcripts (text only, no audio)...")
        result = analyse(name, loader())
        _print(result)
        results.append(result)

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {"item": "3B-1", "code_commit": commit, "datasets": results},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
