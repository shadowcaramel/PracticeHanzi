"""Default download filenames for generated PDFs (PracticeHanzi + optional source + short CJK slug)."""

from __future__ import annotations

import re

from utils.segmentation import extract_cjk

_DEFAULT_BASE = "PracticeHanzi"
_MAX_SLUG_CJK = 3


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


def build_practice_hanzi_pdf_filename(
    text: str,
    *,
    source: tuple[str, str | int] | None = None,
) -> str:
    """Return e.g. ``PracticeHanzi_你好.pdf``, ``PracticeHanzi_preset_animals_你好.pdf``, ``PracticeHanzi_HSK3_L2_你好.pdf``."""
    slug = _cjk_slug(text)
    parts: list[str] = [_DEFAULT_BASE]

    if source:
        kind, val = source
        if kind == "preset":
            parts.append("preset")
            parts.append(_safe_token(str(val)))
        elif kind == "hsk":
            parts.append(f"HSK3_L{int(val)}")

    stem = "_".join(parts) + "_" + slug
    if len(stem) > 160:
        stem = stem[:160]
    return stem + ".pdf"
