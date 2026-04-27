"""Frozen options dataclass for generate_pdf.

Having a single hashable object for the whole job makes it trivial to:
  * key caches (per-option PDF cache, translation prefetch set, Streamlit thumbnail).
  * log / compare two runs.
  * pass a single value to helpers instead of 15 kwargs.

``typefaces_by_script`` is stored as a frozen tuple of pairs so the dataclass
itself can be hashed. Convert from a ``dict`` via :meth:`PdfJobOptions.from_kwargs`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields


@dataclass(frozen=True, slots=True)
class PdfJobOptions:
    text: str = ""
    layout_mode: str = "character"

    typeface_id: str | None = None
    style_key: str = "kaishu"
    typefaces_by_script: tuple[tuple[str, str], ...] | None = None
    all_styles: bool = False

    show_strokes: bool = True
    show_radicals: bool = False
    show_decomposition: bool = False
    show_pinyin: bool = True
    show_english: bool = True
    show_russian: bool = True

    grid_type: str = "tian"
    practice_rows: int = 3
    char_size_pt: int = 40

    compact_metadata: bool = True
    show_mmh_gloss: bool = False

    ghost_opacity: float = 0.20
    cover_page: bool = False

    # Reserved for backward-compatible future options.
    extras: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @classmethod
    def from_kwargs(cls, text: str, **kw) -> "PdfJobOptions":
        """Build options from legacy generate_pdf(**kwargs) call sites."""
        tbs = kw.pop("typefaces_by_script", None)
        if isinstance(tbs, dict):
            tbs = tuple(sorted(tbs.items()))
        kw["typefaces_by_script"] = tbs

        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in kw.items() if k in known}
        return cls(text=text, **filtered)

    def typefaces_by_script_dict(self) -> dict[str, str] | None:
        if not self.typefaces_by_script:
            return None
        return dict(self.typefaces_by_script)
