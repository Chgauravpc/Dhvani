from __future__ import annotations

import pytest

from dhvani.safety.prompt_guard import strip_markdown_for_speech


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("plain sentence, nothing to do.", "plain sentence, nothing to do."),
        ("# Heading\nBody text.", "Heading\nBody text."),
        ("### Small heading", "Small heading"),
        ("- one\n- two\n- three", "one\ntwo\nthree"),
        ("1. first\n2. second", "first\nsecond"),
        ("Hello **world**, this is *fun*.", "Hello world, this is fun."),
        ("Use ***very*** bold italics.", "Use very bold italics."),
        ("Run `pip install piper-tts` first.", "Run pip install piper-tts first."),
        ("See [the docs](https://example.com) for more.", "See the docs for more."),
        ("Para one.\n\n\nPara two.", "Para one.\nPara two."),
    ],
)
def test_strip_markdown_for_speech(text: str, expected: str) -> None:
    assert strip_markdown_for_speech(text) == expected


def test_strip_markdown_collapses_runs_of_spaces() -> None:
    assert strip_markdown_for_speech("a    b") == "a b"
