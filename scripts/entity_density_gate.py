"""Phase 2 spec section 2A -- the entity-density gate.

F2's whole headline number is an Entity Error Rate computed over the
examples in Svarah and LAHAJA whose transcripts mention a lexicon entity.
Neither dataset was built around civic terminology, so there's no
guarantee the ~20-entry lexicon finds enough mentions to compute a
meaningful rate. This is a go/no-go gate, not a risk to note and move past:
an EER over eight mentions is not a result.

    uv run python scripts/entity_density_gate.py

Downloads manifests only (text columns), never audio -- see
`eval.datasets.load_svarah_ground_truth_texts` /
`load_lahaja_ground_truth_texts`. Needs a Hugging Face login that has
accepted both datasets' gated-access terms (verified directly: both
returned `GatedRepoError` unauthenticated) -- run `huggingface-cli login`
or set `HF_TOKEN` first.

Decision rule (spec section 2A):
- >=100 total mentions in a dataset: proceed as planned.
- 30-100: proceed, but report a confidence interval and expand the lexicon
  toward whatever terms the data actually contains.
- <30: stop and change corpus (widen the lexicon to place names/
  institutions/personal names, or switch to IndicVoices' use-case split).
"""

from __future__ import annotations

from collections import Counter

from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.eval.datasets import load_lahaja_ground_truth_texts, load_svarah_ground_truth_texts


def _count_mentions(texts: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        lowered = text.lower()
        for canonical, _script, variant in DEFAULT_LEXICON.all_variants():
            counts[canonical] += lowered.count(variant.lower())
    return counts


def _report(dataset_name: str, texts: list[str]) -> None:
    counts = _count_mentions(texts)
    total = sum(counts.values())
    print(f"\n{dataset_name}: {len(texts)} transcripts, {total} total lexicon mentions")
    for canonical, n in counts.most_common():
        if n:
            print(f"  {canonical:<30}{n:>6}")
    if total >= 100:
        decision = "PROCEED as planned (>=100 mentions)"
    elif total >= 30:
        decision = "PROCEED with a confidence interval + lexicon expansion (30-100 mentions)"
    else:
        decision = "STOP -- change corpus (<30 mentions)"
    print(f"  -> {decision}")


def main() -> None:
    print("Downloading Svarah ground-truth transcripts (text only, no audio)...")
    svarah_texts = load_svarah_ground_truth_texts()
    _report("Svarah", svarah_texts)

    print("\nDownloading LAHAJA ground-truth transcripts (text only, no audio)...")
    lahaja_texts = load_lahaja_ground_truth_texts()
    _report("LAHAJA", lahaja_texts)


if __name__ == "__main__":
    main()
