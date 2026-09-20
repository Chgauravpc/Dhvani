"""Post-ASR entity correction: slide a word-window over a transcript,
phonetic-key-match each window against the lexicon, and replace windows
that score above `threshold` with the canonical form (phase-2 spec section
6.3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from dhvani.entity.lexicon import LATIN, DomainLexicon
from dhvani.entity.phonetic import phonetic_key

_WORD_RE = re.compile(r"\S+")


@dataclass(frozen=True, slots=True)
class Correction:
    span: tuple[int, int]
    original: str
    corrected: str
    canonical_entity: str


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    text: str
    corrections: list[Correction]


class EntityCorrector:
    """Corrects lexicon entity mentions in a transcript.

    `threshold` (0..1, a rapidfuzz `fuzz.ratio` fraction) is the single knob
    trading recovery against corruption -- 0.82 is a starting guess with
    nothing behind it (phase-2 spec section 6.3). Tune it on a dev split
    and report the sweep alongside the chosen value; don't just pick one
    and move on.

    **Known corruption source, observed directly, not just theorized**: for
    each window start position this tries the *widest* window that clears
    `threshold`, not the best-scoring one, so a window that runs one word
    too wide can still pass if the extra word is short relative to the
    match ("my adhar card" scores 0.87 against the lexicon's own "aadhar
    card" variant and swallows "my" into the correction). This is exactly
    what `corruption_rate` (phase-2 spec section 6.7) exists to measure --
    it is not fixed here by hand-tuning the algorithm, because the
    threshold sweep this class is built for is the honest way to trade it
    off, not a guess.
    """

    def __init__(self, lexicon: DomainLexicon, threshold: float = 0.82) -> None:
        self._threshold = threshold
        self._keys: tuple[tuple[str, str], ...] = tuple(
            (canonical, phonetic_key(variant, script))
            for canonical, script, variant in lexicon.all_variants()
        )
        self._max_window_words = max(
            (len(variant.split()) for _, _, variant in lexicon.all_variants()),
            default=1,
        )

    def _best_match(self, candidate_key: str) -> tuple[str, float] | None:
        if not candidate_key:
            return None
        best_canonical: str | None = None
        best_score = 0.0
        for canonical, key in self._keys:
            score = fuzz.ratio(candidate_key, key) / 100.0
            if score > best_score:
                best_score = score
                best_canonical = canonical
        if best_canonical is None:
            return None
        return best_canonical, best_score

    def correct(self, text: str, script: str = LATIN) -> CorrectionResult:
        """Slides a word-window (longest lexicon phrase down to one word)
        over `text`, replacing the first (greedy, non-overlapping,
        longest-first) window at or above `threshold` with its canonical
        form. `script` says how to interpret `text` for phonetic-key
        generation -- `LATIN` for a romanized/English-heavy ASR transcript,
        the usual case for `CorrectedSTT`.
        """
        words = list(_WORD_RE.finditer(text))
        corrections: list[Correction] = []
        out_parts: list[str] = []
        last_end = 0

        i = 0
        n = len(words)
        while i < n:
            matched = False
            max_width = min(self._max_window_words, n - i)
            for width in range(max_width, 0, -1):
                start_char = words[i].start()
                end_char = words[i + width - 1].end()
                candidate = text[start_char:end_char]
                key = phonetic_key(candidate, script)
                match = self._best_match(key)
                if match is not None and match[1] >= self._threshold:
                    canonical, _score = match
                    out_parts.append(text[last_end:start_char])
                    out_parts.append(canonical)
                    corrections.append(
                        Correction(
                            span=(start_char, end_char),
                            original=candidate,
                            corrected=canonical,
                            canonical_entity=canonical,
                        )
                    )
                    last_end = end_char
                    i += width
                    matched = True
                    break
            if not matched:
                i += 1

        out_parts.append(text[last_end:])
        return CorrectionResult(text="".join(out_parts), corrections=corrections)
