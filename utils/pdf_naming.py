"""Default download filenames for generated PDFs (PracticeHanzi + optional source + short CJK slug)."""

from __future__ import annotations

import re

from utils.segmentation import extract_cjk

_DEFAULT_BASE = "PracticeHanzi"
_MAX_SLUG_CJK = 3
_MAX_STEM_LEN = 160


def _safe_token(s: str, max_len: int = 40) -> str:
    """ASCII-ish token for preset id (Windows-safe)."""
    t = re.sub(r"[^\w\-]+", "_", s, flags=re.ASCII)
    t = t.strip("_") or "preset"
    return t[:max_len]


def _cjk_slug(text: str) -> str:
    """Use up to *_MAX_SLUG_CJK* Han characters for the file stem; longer inputs are truncated."""
    cjk = extract_cjk(text)
    if not cjk:
        return "sheet"
    if len(cjk) > _MAX_SLUG_CJK:
        return cjk[:_MAX_SLUG_CJK]
    return cjk


def _pinyin_slug(text: str) -> str:
    """Tone-less pinyin slug for ASCII-only filenames."""
    try:
        from pypinyin import pinyin, Style
    except Exception:
        return "sheet"
    cjk = extract_cjk(text)
    if not cjk:
        return "sheet"
    if len(cjk) > _MAX_SLUG_CJK:
        cjk = cjk[:_MAX_SLUG_CJK]
    syls = pinyin(cjk, style=Style.NORMAL, errors="ignore")
    joined = "".join(s[0] for s in syls if s and s[0]).lower()
    return _safe_token(joined) if joined else "sheet"


def build_practice_hanzi_pdf_filename(
    text: str,
    *,
    source: tuple[str, str | int] | None = None,
    ascii_only: bool = False,
) -> str:
    """Return e.g. ``PracticeHanzi_你好.pdf`` or (ASCII) ``PracticeHanzi_nihao.pdf``."""
    slug = _pinyin_slug(text) if ascii_only else _cjk_slug(text)
    parts: list[str] = [_DEFAULT_BASE]

    if source:
        kind, val = source
        if kind == "preset":
            parts.append("preset")
            parts.append(_safe_token(str(val)))
        elif kind == "hsk":
            parts.append(f"HSK3_L{int(val)}")

    stem = "_".join(parts) + "_" + slug
    if len(stem) > _MAX_STEM_LEN:
        stem = stem[:_MAX_STEM_LEN]
    return stem + ".pdf"
