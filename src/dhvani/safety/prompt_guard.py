"""Strip markdown formatting an LLM might emit before it reaches TTS.

A voice channel cannot render bold text, bullet points, or headers -- it can
only speak literal characters. This is a pure text transform; no LLM call is
involved. Structure (headers, list markers) is dropped, and emphasis/link
markup is unwrapped down to its text content.
"""

from __future__ import annotations

import re

_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HEADER_RE = re.compile(r"^[ \t]*#{1,6}[ \t]*", re.MULTILINE)
_BULLET_RE = re.compile(r"^[ \t]*[-*+][ \t]+", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^[ \t]*\d+[.)][ \t]+", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(\*{1,3}|_{1,3})(\S(?:.*?\S)?)\1")
_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_BLANK_LINES_RE = re.compile(r"\n{2,}")
_RUN_OF_SPACES_RE = re.compile(r"[ \t]{2,}")


def strip_markdown_for_speech(text: str) -> str:
    """Remove markdown that would otherwise be spoken literally.

    Headers and list markers are dropped (their line's remaining text is
    kept). Emphasis and inline-code markers are removed but their content is
    kept. Links are replaced by their link text. Excess whitespace left
    behind by the above is then collapsed.
    """
    result = _LINK_RE.sub(r"\1", text)
    result = _HEADER_RE.sub("", result)
    result = _BULLET_RE.sub("", result)
    result = _NUMBERED_RE.sub("", result)
    # Applied twice: strips "***bold italic***" down to "*italic*" on the
    # first pass, then the remaining single markers on the second.
    result = _EMPHASIS_RE.sub(r"\2", result)
    result = _EMPHASIS_RE.sub(r"\2", result)
    result = _INLINE_CODE_RE.sub(r"\1", result)
    result = _RUN_OF_SPACES_RE.sub(" ", result)
    result = _BLANK_LINES_RE.sub("\n", result)
    return result.strip()
