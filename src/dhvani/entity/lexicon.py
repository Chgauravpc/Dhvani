"""Starter civic/government/finance entity lexicon for `dhvani-entity` (F2).

~20 entries (phase-2 spec open question 2's default), across Devanagari,
Latin, and Tamil (spec section 2's script scope) -- matching ROADMAP.md's
own named examples (Aadhaar, PAN, "Pradhan Mantri Awas Yojana", ...).

Devanagari and Latin variants are hand-curated from working knowledge of
Hindi. Tamil variants are machine-generated at import time via
`indic_transliteration`, from an ITRANS seed whose Devanagari round-trip
was checked against the hand-curated Devanagari form before being trusted
(script `verify_transliteration.py`, run once during development -- not
part of this module). That check only proves the seed encodes the intended
*Hindi* word; it says nothing about whether the resulting Tamil is how a
Tamil speaker would actually write or say the term, which nobody has
checked. Two categories of entry carry no Tamil variant at all rather than
risk a fabricated one:

- **Acronyms** (PAN, EPFO, UPI, IFSC, GST, ESIC, PF) and **English-loanword
  phrases** (voter ID, Kisan Credit Card, DigiLocker, Passport Seva) --
  transliterating a Latin acronym or an English loanword phonetically
  through Sanskrit-oriented ITRANS rules is guesswork, not a Hindi compound
  word the scheme was designed for.
- **Sukanya Samriddhi Yojana** -- consonantal ऋ (vocalic r, in "samRRiddhi")
  has no clean single-character Tamil equivalent; the raw transliteration
  output contains a stray apostrophe artifact, a visible sign something is
  actually wrong rather than merely unverified.

Get a Tamil speaker to check the eight Tamil variants that do exist here
before trusting them for anything beyond the phase-2 entity-density gate
(spec section 2A), which only needs approximate phonetic proximity, not
correctness.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

from indic_transliteration import sanscript

DEVANAGARI = "devanagari"
LATIN = "latin"
TAMIL = "tamil"


@dataclass(frozen=True, slots=True)
class LexiconEntry:
    """One entity and every spelling it's known to appear as, by script."""

    canonical: str
    variants: Mapping[str, Sequence[str]]


def _tamil(itrans_seed: str) -> str:
    """Transliterate a verified ITRANS seed to Tamil. See the module
    docstring: verification only covers the Devanagari round-trip, not
    Tamil correctness."""
    result: str = sanscript.transliterate(itrans_seed, sanscript.ITRANS, sanscript.TAMIL)
    return result


_ENTRIES: tuple[LexiconEntry, ...] = (
    LexiconEntry(
        canonical="Aadhaar",
        variants={
            DEVANAGARI: ("आधार", "आधार कार्ड"),
            LATIN: ("aadhaar", "aadhar", "adhaar", "aadhar card", "aadhaar card"),
            TAMIL: (_tamil("aadhaara"),),
        },
    ),
    LexiconEntry(
        canonical="PAN card",
        variants={
            DEVANAGARI: ("पैन", "पैन कार्ड"),
            LATIN: ("pan", "pan card"),
        },
    ),
    LexiconEntry(
        canonical="EPFO",
        variants={
            DEVANAGARI: ("ईपीएफओ",),
            LATIN: ("epfo",),
        },
    ),
    LexiconEntry(
        canonical="Ayushman Bharat",
        variants={
            DEVANAGARI: ("आयुष्मान भारत",),
            LATIN: ("ayushman bharat", "ayushman"),
            TAMIL: (_tamil("AyuShmAna bhArata"),),
        },
    ),
    LexiconEntry(
        canonical="Pradhan Mantri Awas Yojana",
        variants={
            DEVANAGARI: ("प्रधानमंत्री आवास योजना",),
            LATIN: ("pradhan mantri awas yojana", "pmay"),
            TAMIL: (_tamil("pradhAnamaMtrI AvAsa yojanA"),),
        },
    ),
    LexiconEntry(
        canonical="UPI",
        variants={
            DEVANAGARI: ("यूपीआई",),
            LATIN: ("upi",),
        },
    ),
    LexiconEntry(
        canonical="IFSC code",
        variants={
            DEVANAGARI: ("आईएफएससी", "आईएफएससी कोड"),
            LATIN: ("ifsc", "ifsc code"),
        },
    ),
    LexiconEntry(
        canonical="Ration card",
        variants={
            DEVANAGARI: ("राशन कार्ड",),
            LATIN: ("ration card",),
            TAMIL: (_tamil("rAshana kArDa"),),
        },
    ),
    LexiconEntry(
        canonical="Voter ID",
        variants={
            DEVANAGARI: ("वोटर आईडी", "मतदाता पहचान पत्र"),
            LATIN: ("voter id", "epic"),
        },
    ),
    LexiconEntry(
        canonical="GST",
        variants={
            DEVANAGARI: ("जीएसटी",),
            LATIN: ("gst",),
        },
    ),
    LexiconEntry(
        canonical="Kisan Credit Card",
        variants={
            DEVANAGARI: ("किसान क्रेडिट कार्ड",),
            LATIN: ("kisan credit card", "kcc"),
        },
    ),
    LexiconEntry(
        canonical="Jan Dhan Yojana",
        variants={
            DEVANAGARI: ("जन धन योजना",),
            LATIN: ("jan dhan yojana",),
            TAMIL: (_tamil("jana dhana yojanA"),),
        },
    ),
    LexiconEntry(
        canonical="Mudra Yojana",
        variants={
            DEVANAGARI: ("मुद्रा योजना",),
            LATIN: ("mudra yojana",),
            TAMIL: (_tamil("mudrA yojanA"),),
        },
    ),
    LexiconEntry(
        canonical="Sukanya Samriddhi Yojana",
        variants={
            DEVANAGARI: ("सुकन्या समृद्धि योजना",),
            LATIN: ("sukanya samriddhi yojana",),
        },
    ),
    LexiconEntry(
        canonical="Ujjwala Yojana",
        variants={
            DEVANAGARI: ("उज्ज्वला योजना",),
            LATIN: ("ujjwala yojana",),
            TAMIL: (_tamil("ujjvalA yojanA"),),
        },
    ),
    LexiconEntry(
        canonical="ESIC",
        variants={
            DEVANAGARI: ("ईएसआईसी",),
            LATIN: ("esic",),
        },
    ),
    LexiconEntry(
        canonical="Passport Seva",
        variants={
            DEVANAGARI: ("पासपोर्ट सेवा",),
            LATIN: ("passport seva",),
        },
    ),
    LexiconEntry(
        canonical="DigiLocker",
        variants={
            DEVANAGARI: ("डिजिलॉकर",),
            LATIN: ("digilocker", "digi locker"),
        },
    ),
    LexiconEntry(
        canonical="CoWIN",
        variants={
            DEVANAGARI: ("कोविन",),
            LATIN: ("cowin", "co-win"),
            TAMIL: (_tamil("kovina"),),
        },
    ),
    LexiconEntry(
        canonical="Provident Fund",
        variants={
            DEVANAGARI: ("पीएफ", "प्रोविडेंट फंड"),
            LATIN: ("pf", "provident fund"),
        },
    ),
)


class DomainLexicon:
    """A fixed set of `LexiconEntry` objects, searchable by canonical name."""

    def __init__(self, entries: Sequence[LexiconEntry]) -> None:
        self._entries = tuple(entries)
        self._by_canonical = {entry.canonical: entry for entry in self._entries}

    def __iter__(self) -> Iterator[LexiconEntry]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def all_variants(self) -> Iterator[tuple[str, str, str]]:
        """Yields (canonical, script, variant) for every entry."""
        for entry in self._entries:
            for script, variants in entry.variants.items():
                for variant in variants:
                    yield entry.canonical, script, variant

    def find(self, canonical: str) -> LexiconEntry | None:
        return self._by_canonical.get(canonical)


DEFAULT_LEXICON = DomainLexicon(_ENTRIES)
