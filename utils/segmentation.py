"""Split user text into CJK phrases (whitespace-separated) or character sequences."""

from __future__ import annotations

import re
from typing import Literal

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def is_cjk(char: str) -> bool:
    return len(char) == 1 and bool(_CJK_RE.match(char))


def extract_cjk(text: str) -> str:
    return "".join(_CJK_RE.findall(text))


def phrase_segments(text: str) -> list[str]:
    """Whitespace-separated segments; each segment keeps only CJK characters.

    If there are no whitespace chunks with CJK but the text contains CJK, treat the
    whole string as one phrase (e.g. '你好' with no spaces).
    """
    text = text.strip()
    if not text:
        return []

    parts: list[str] = []
    for raw in text.split():
        s = extract_cjk(raw)
        if s:
            parts.append(s)

    if not parts:
        whole = extract_cjk(text)
        if whole:
            parts.append(whole)

    return parts


def character_sequence(text: str) -> list[str]:
    """Every non-whitespace character (same as legacy app behaviour)."""
    return [ch for ch in text if ch.strip()]


def infer_layout_mode(text: str) -> Literal["character", "phrase"]:
    """Choose PDF layout without a manual toggle.

    * **phrase** — Multiple CJK chunks separated by whitespace (spaces or newlines), e.g.
      ``你好 谢谢`` or one phrase per line in a multi-line box.
    * **character** — A single contiguous run per “token” (no whitespace between parts), e.g.
      ``你好`` → one token → one character per page for stroke practice.
    """
    if not text or not text.strip():
        return "character"
    segs = phrase_segments(text)
    if len(segs) > 1:
        return "phrase"
    return "character"
