"""Generate printable A4 PDF calligraphy training sheets using reportlab."""

from __future__ import annotations

import hashlib
import json
import math
import pickle
from datetime import date
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import Color, HexColor, black, white
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.graphics import renderPDF

from utils.fonts import (
    FONT_REGISTRY,
    default_typeface_id_for_script,
    ensure_all_typefaces_parallel,
    ensure_label_font,
    ensure_typeface,
    get_typeface,
)
from utils.stroke_order import prefetch_stroke_json, render_stroke_sequence, svg_to_drawing
from utils.pinyin_utils import get_pinyin, get_pinyin_per_char
from utils.translation import (
    get_translations,
    prefetch_translations,
    save_translation_cache_now,
)
from utils.radicals import radical_caption
from utils.decomposition import (
    decomposition_lines,
    ensure_decomposition_data,
    ids_compact,
    phrase_mmh_gloss,
)
from utils.segmentation import character_sequence, phrase_segments, is_cjk
from utils.pdf_options import PdfJobOptions
from utils import palette as P

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_CACHE_DIR = BASE_DIR / "data" / "pdf_cache"
PDF_CACHE_MAX_BYTES = 200 * 1024 * 1024
# Bump when font/layout changes should invalidate cached PDFs.
FONTS_VERSION = "v2"

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm

GRID_LIGHT = P.GRID_EDGE
GRID_MID = P.GRID_CROSS
GHOST_ALPHA = 0.20


ProgressFn = Callable[[float, str], None]


# ---------------------------------------------------------------------------
# Grid styles
# ---------------------------------------------------------------------------
def _draw_tian_grid(c: Canvas, x: float, y: float, size: float) -> None:
    """田字格 (field-character grid)."""
    c.setStrokeColor(GRID_LIGHT)
    c.setLineWidth(0.8)
    c.rect(x, y, size, size, stroke=1, fill=0)
    c.setStrokeColor(GRID_MID)
    c.setLineWidth(0.35)
    c.setDash([1, 3])
    half = size / 2
    c.line(x + half, y, x + half, y + size)
    c.line(x, y + half, x + size, y + half)
    c.setDash()


def _draw_mi_grid(c: Canvas, x: float, y: float, size: float) -> None:
    """米字格 (rice-character grid)."""
    c.setStrokeColor(GRID_LIGHT)
    c.setLineWidth(0.8)
    c.rect(x, y, size, size, stroke=1, fill=0)
    c.setStrokeColor(GRID_MID)
    c.setLineWidth(0.35)
    c.setDash([1, 3])
    half = size / 2
    c.line(x + half, y, x + half, y + size)
    c.line(x, y + half, x + size, y + half)
    c.line(x, y, x + size, y + size)
    c.line(x, y + size, x + size, y)
    c.setDash()


def _draw_hui_grid(c: Canvas, x: float, y: float, size: float) -> None:
    """回字格: outer square + concentric inner square at 1/6 inset."""
    c.setStrokeColor(GRID_LIGHT)
    c.setLineWidth(0.8)
    c.rect(x, y, size, size, stroke=1, fill=0)
    inset = size / 6.0
    c.setStrokeColor(GRID_MID)
    c.setLineWidth(0.5)
    c.rect(x + inset, y + inset, size - 2 * inset, size - 2 * inset, stroke=1, fill=0)


def _draw_plain_grid(c: Canvas, x: float, y: float, size: float) -> None:
    c.setStrokeColor(GRID_LIGHT)
    c.setLineWidth(0.8)
    c.rect(x, y, size, size, stroke=1, fill=0)


GRID_FUNCS = {
    "tian": _draw_tian_grid,
    "mi": _draw_mi_grid,
    "hui": _draw_hui_grid,
    "plain": _draw_plain_grid,
}


# Practice grid: vertical budget.
PRACTICE_HEADER_BEFORE_GRID = 5 * mm + 5 * mm
ROW_GAP_PRACTICE = 2 * mm
PRACTICE_CELL_MIN = 16.0
BOTTOM_SAFE_PT = 24.0            # leave room for the footer stripe on cover pages
TRAINING_BOTTOM_SAFE_PT = 6.0    # training pages have no footer — just breathing room
TRAINING_TOP_RECLAIM_PT = 8.0    # pull content up into the space the header rule used
COMPACT_METADATA_CHAR_PT = 100


# ---------------------------------------------------------------------------
# Small text helpers
# ---------------------------------------------------------------------------
def _truncate_to_width_canvas(
    c: Canvas, font_name: str, font_size: float, text: str, max_w: float
) -> str:
    if c.stringWidth(text, font_name, font_size) <= max_w:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        t = text[:mid] + ell
        if c.stringWidth(t, font_name, font_size) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ell if lo > 0 else ell


@lru_cache(maxsize=8192)
def _char_fits_font(font_name: str, char: str) -> bool:
    """Cached: does *font_name* have a glyph for *char*?"""
    try:
        font = pdfmetrics.getFont(font_name)
        if hasattr(font, "face") and hasattr(font.face, "charWidths"):
            return ord(char) in font.face.charWidths
        w = font.stringWidth(char, 10)
        return w > 0
    except Exception:
        return True


def _practice_cell_and_rows(
    stroke_low: float,
    practice_rows: int,
    char_box_cap: float,
    bottom_safe: float = TRAINING_BOTTOM_SAFE_PT,
) -> tuple[float, int, int]:
    """Return ``(cell_size, rows_drawn, rows_requested)``.

    Policy: keep practice cells at the nominal size (= top-character box) so
    they visually echo the model glyph; when vertical space is tight, **drop
    rows** instead of shrinking cells. Callers can compare the last two
    numbers and surface a UI warning when the layout couldn't honor the
    requested row count.

    Only as a last resort — when a single nominal row cannot fit — do we
    scale the cell down to fit exactly one row.
    """
    avail = stroke_low - PRACTICE_HEADER_BEFORE_GRID - MARGIN - bottom_safe
    want = max(1, practice_rows)
    nominal = max(PRACTICE_CELL_MIN, char_box_cap)

    if avail <= 0:
        return max(12.0, PRACTICE_CELL_MIN), 0, want

    rows_at_nominal = int((avail + ROW_GAP_PRACTICE) // (nominal + ROW_GAP_PRACTICE))
    if rows_at_nominal >= want:
        return nominal, want, want
    if rows_at_nominal >= 1:
        return nominal, rows_at_nominal, want

    cell = max(PRACTICE_CELL_MIN, min(nominal, avail))
    return cell, 1, want


def _phrase_cells_per_row(usable_w: float, gap: float, practice_cell: float, n: int) -> int:
    if practice_cell + gap <= 0:
        return max(1, n)
    max_cells = max(1, int((usable_w + gap) // (practice_cell + gap)))
    full_mult = (max_cells // n) * n
    if full_mult >= n:
        return full_mult
    return max_cells


def _collect_job_cjk_chars(items: list[tuple[str, str]]) -> set[str]:
    out: set[str] = set()
    for kind, payload in items:
        if kind == "char" and is_cjk(payload):
            out.add(payload)
        elif kind == "phrase":
            for ch in payload:
                if is_cjk(ch):
                    out.add(ch)
    return out


# ---------------------------------------------------------------------------
# Page chrome (header rule, footer stripe, script badge, page N / M)
# ---------------------------------------------------------------------------
def _draw_page_chrome(
    c: Canvas,
    *,
    label_font: str,
    script_key: str,
    page_num: int,
    page_total: int,
    page_pinyin: str | None = None,
    draw_ribbon: bool = False,
) -> None:
    """Header rule + optional pinyin, script badge top-right, footer stripe + page numbers."""
    top_y = PAGE_H - MARGIN + 2
    c.setStrokeColor(P.INK_SOFT)
    c.setLineWidth(0.6)
    c.line(MARGIN, top_y + 14, PAGE_W - MARGIN, top_y + 14)

    if page_pinyin:
        c.setFont(label_font, 10)
        c.setFillColor(P.INK_MUTED)
        c.drawRightString(PAGE_W - MARGIN, top_y + 18, page_pinyin)

    badge_color = P.SCRIPT_COLORS.get(script_key, P.ACCENT)
    badge = P.SCRIPT_SHORT.get(script_key, "?")
    bw, bh = 18, 18
    bx = PAGE_W - MARGIN - bw
    by = PAGE_H - MARGIN + 16
    c.setFillColor(badge_color)
    c.roundRect(bx, by, bw, bh, 3, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont(label_font, 11)
    c.drawCentredString(bx + bw / 2, by + bh / 2 - 4, badge)

    if draw_ribbon:
        c.setFillColor(badge_color)
        c.rect(0, MARGIN, 4, PAGE_H - 2 * MARGIN, stroke=0, fill=1)

    # Footer
    foot_y = MARGIN - 8
    c.setStrokeColor(P.GRID_EDGE)
    c.setLineWidth(0.3)
    c.line(MARGIN, foot_y + 10, PAGE_W - MARGIN, foot_y + 10)
    c.setFont(label_font, 7)
    c.setFillColor(P.INK_MUTED)
    today = date.today().isoformat()
    c.drawString(MARGIN, foot_y, f"PracticeHanzi · {today}")
    c.drawRightString(PAGE_W - MARGIN, foot_y, f"{page_num} / {page_total}")


def _draw_script_typeface_header(
    c: Canvas,
    *,
    label_font: str,
    script_label: str,
    typeface_label: str,
    cursor_y: float,
) -> float:
    c.setFont(label_font, 14)
    c.setFillColor(P.INK_SOFT)
    c.drawString(MARGIN, cursor_y - 14, script_label)
    c.setFont(label_font, 11)
    c.setFillColor(P.INK_MUTED)
    c.drawString(MARGIN, cursor_y - 30, typeface_label)
    return cursor_y - 38


def _draw_ghost_char(
    c: Canvas, char: str, font_name: str, x: float, y: float, size: float, alpha: float = GHOST_ALPHA
) -> None:
    """Draw a faint tracing guide character centered in a grid cell."""
    if alpha <= 0.001:
        return
    c.saveState()
    c.setFillColor(Color(0, 0, 0, alpha=alpha))
    font_size = size * 0.85
    c.setFont(font_name, font_size)
    tw = c.stringWidth(char, font_name, font_size)
    tx = x + (size - tw) / 2
    ty = y + (size - font_size) / 2 + font_size * 0.1
    c.drawString(tx, ty, char)
    c.restoreState()


# ---------------------------------------------------------------------------
# Metadata block (phrase pages)
# ---------------------------------------------------------------------------
def _draw_phrase_metadata_block(
    c: Canvas,
    *,
    label_font: str,
    phrase: str,
    usable_w: float,
    margin_x: float,
    info_y: float,
    inner_fs: float,
    show_pinyin: bool,
    show_english: bool,
    show_russian: bool,
    char_size_pt: int,
    compact: bool,
    show_mmh_gloss: bool,
) -> float:
    info_line_h = max(14.0, inner_fs * 0.2)
    translations = get_translations(
        phrase, need_en=show_english, need_ru=show_russian
    )
    py = get_pinyin(phrase) if show_pinyin else ""
    en = translations.get("en") or ""
    ru = translations.get("ru") or ""
    mmh_line = phrase_mmh_gloss(phrase) if show_mmh_gloss else None

    drew_compact = False
    if (
        compact
        and char_size_pt >= COMPACT_METADATA_CHAR_PT
        and (show_pinyin and py or show_english and en or show_russian and ru)
    ):
        pieces: list[tuple[str, HexColor]] = []
        if show_pinyin and py:
            pieces.append((f"Pinyin: {py}", P.PINYIN))
        if show_english and en:
            pieces.append((f"EN: {en}", P.EN))
        if show_russian and ru:
            pieces.append((f"RU: {ru}", P.RU))
        if pieces:
            col_w = usable_w / len(pieces)
            fs = max(7.5, min(9.0, inner_fs * 0.11))
            c.setFont(label_font, fs)
            bad = False
            x = margin_x
            for full, color in pieces:
                t = _truncate_to_width_canvas(c, label_font, fs, full, col_w - 2)
                if len(full) > 24 and len(t) < len(full) * 0.4:
                    bad = True
                    break
                c.setFillColor(color)
                c.drawString(x, info_y - 12, t)
                x += col_w
            if not bad:
                drew_compact = True
                info_y -= info_line_h + 2

    if not drew_compact:
        if show_pinyin and py:
            c.setFont(label_font, max(10.0, inner_fs * 0.12))
            c.setFillColor(P.PINYIN)
            c.drawString(margin_x, info_y - 12, f"Pinyin: {py}")
            info_y -= info_line_h + 4
        fs = max(9.0, inner_fs * 0.1)
        c.setFont(label_font, fs)
        if show_english and en:
            c.setFillColor(P.EN)
            c.drawString(margin_x, info_y - 12, f"EN: {en}")
            info_y -= info_line_h
        if show_russian and ru:
            c.setFillColor(P.RU)
            c.drawString(margin_x, info_y - 12, f"RU: {ru}")
            info_y -= info_line_h

    if mmh_line:
        mfs = max(8.0, inner_fs * 0.09)
        c.setFont(label_font, mfs)
        c.setFillColor(P.IDS)
        mt = _truncate_to_width_canvas(c, label_font, mfs, mmh_line, usable_w - 2)
        c.drawString(margin_x, info_y - 12, mt)
        info_y -= info_line_h

    return info_y


# ---------------------------------------------------------------------------
# Whole-PDF cache (hashed on a PdfJobOptions)
# ---------------------------------------------------------------------------
def _pdf_cache_key(options: PdfJobOptions) -> str:
    blob = pickle.dumps((FONTS_VERSION, options), protocol=4)
    return hashlib.sha1(blob).hexdigest()


def _pdf_cache_get(key: str) -> bytes | None:
    p = PDF_CACHE_DIR / f"{key}.pdf"
    if p.is_file():
        try:
            data = p.read_bytes()
            p.touch()
            return data
        except Exception:
            return None
    return None


def _pdf_cache_get_warnings(key: str) -> list[str]:
    p = PDF_CACHE_DIR / f"{key}.warnings.json"
    if not p.is_file():
        return []
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [str(x) for x in payload]
    except Exception:
        pass
    return []


def _pdf_cache_put(key: str, data: bytes, warnings: list[str] | None = None) -> None:
    try:
        PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (PDF_CACHE_DIR / f"{key}.pdf").write_bytes(data)
        side = PDF_CACHE_DIR / f"{key}.warnings.json"
        if warnings:
            side.write_text(json.dumps(list(warnings), ensure_ascii=False), encoding="utf-8")
        elif side.exists():
            try:
                side.unlink()
            except Exception:
                pass
        _pdf_cache_evict()
    except Exception:
        pass


def _pdf_cache_evict() -> None:
    """LRU-by-mtime cap so the cache directory never grows past 200 MB."""
    try:
        entries = sorted(
            PDF_CACHE_DIR.glob("*.pdf"),
            key=lambda p: p.stat().st_mtime,
        )
        total = sum(p.stat().st_size for p in entries)
        while total > PDF_CACHE_MAX_BYTES and entries:
            victim = entries.pop(0)
            try:
                total -= victim.stat().st_size
                victim.unlink()
            except Exception:
                break
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Cover page (Phase 5a)
# ---------------------------------------------------------------------------
def _cover_included_layout(
    payloads: list[str],
    avail_w: float,
    avail_h: float,
) -> tuple[int, int, float, float, float]:
    """Choose ``(cols, rows, cell_w, cell_h, char_size)`` for the cover's
    "Included" grid.

    Goals (in order):
      1. Pick a cell size large enough to make the showcase visually clear.
      2. For **few** items scale up so the grid fills roughly a quarter of
         the vertical budget (capped so single glyphs don't look cartoonish).
      3. For **many** items use most of the vertical budget but keep glyphs
         readable; excess items are truncated by the caller.
      4. Prefer rectangular grids whose aspect is close to the available box.
    """
    n = max(1, len(payloads))
    max_chars = max((len(p) for p in payloads), default=1)

    # Target fraction of available vertical space based on how many items
    # we need to showcase. A handful of items get airy display; a packed HSK
    # sample fills the page. These ratios hit the "~25–35% for a few,
    # ~75–90% for many" brief.
    if n <= 4:
        target_frac = 0.28
    elif n <= 9:
        target_frac = 0.34
    elif n <= 20:
        target_frac = 0.48
    elif n <= 60:
        target_frac = 0.68
    elif n <= 120:
        target_frac = 0.82
    else:
        target_frac = 0.92

    target_h = max(40.0, avail_h * target_frac)
    gap = 6.0

    CAP = 120.0  # don't make single glyphs cartoonish
    MIN = 14.0
    ideal_aspect = (avail_w / target_h) if target_h > 0 else 1.0

    best: tuple[float, int, int, float] | None = None
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        char_w = (avail_w - (cols - 1) * gap) / (cols * max_chars)
        char_h = (target_h - (rows - 1) * gap) / rows
        if char_w <= 0 or char_h <= 0:
            continue
        char_size = min(char_w, char_h, CAP)
        if char_size < MIN:
            # Don't reject outright — caller may truncate — but penalize heavily.
            penalty = 5.0
            char_size = MIN
        else:
            penalty = 0.0

        grid_w = cols * char_size * max_chars + (cols - 1) * gap
        grid_h = rows * char_size + (rows - 1) * gap
        aspect = grid_w / max(1.0, grid_h)
        aspect_penalty = abs(math.log(aspect) - math.log(ideal_aspect))
        waste = cols * rows - n
        score = -char_size + 0.35 * aspect_penalty + 0.015 * waste + penalty
        if best is None or score < best[0]:
            best = (score, cols, rows, char_size)

    assert best is not None
    _, cols, rows, char_size = best
    cell_w = char_size * max_chars
    cell_h = char_size
    return cols, rows, cell_w, cell_h, char_size


def _draw_cover_page(
    c: Canvas,
    *,
    label_font: str,
    items: list[tuple[str, str]],
    options: PdfJobOptions,
    page_total: int,
) -> None:
    # Masthead ----------------------------------------------------------------
    c.setFillColor(P.ACCENT)
    c.rect(0, PAGE_H - 80, PAGE_W, 80, stroke=0, fill=1)

    c.setFillColor(white)
    c.setFont(label_font, 24)
    c.drawString(MARGIN, PAGE_H - 50, "PracticeHanzi")
    c.setFont(label_font, 11)
    c.drawString(MARGIN, PAGE_H - 68, "Chinese calligraphy training sheets")

    # Meta block --------------------------------------------------------------
    y = PAGE_H - 120
    c.setFillColor(P.INK)
    c.setFont(label_font, 14)
    c.drawString(MARGIN, y, f"Generated {date.today().isoformat()}")
    y -= 20

    c.setFont(label_font, 11)
    c.setFillColor(P.INK_SOFT)
    c.drawString(MARGIN, y, f"Total pages: {page_total}")
    y -= 14
    c.drawString(MARGIN, y, f"Content units: {len(items)} ({options.layout_mode} mode)")
    y -= 14
    if options.all_styles:
        c.drawString(MARGIN, y, "Scripts: 楷 · 行 · 草 · 隶 · 篆")
    else:
        try:
            tid = options.typeface_id or default_typeface_id_for_script(options.style_key)
            c.drawString(MARGIN, y, f"Typeface: {get_typeface(tid)['label']}")
        except Exception:
            pass
    y -= 22

    # Pick a calligraphy typeface for the item glyphs.
    try:
        preview_font = ensure_typeface(
            options.typeface_id or default_typeface_id_for_script("kaishu")
        )
    except Exception:
        preview_font = label_font

    payloads = [p for _, p in items if p]

    # "Included" header -------------------------------------------------------
    c.setFillColor(P.INK)
    c.setFont(label_font, 10)
    c.drawString(MARGIN, y, f"Included ({len(payloads)}):")
    y -= 10

    if not payloads:
        return

    # Available box for the showcase grid. Leave ~50 pt at the bottom so
    # the footer stripe from the page chrome doesn't collide.
    avail_top = y
    avail_bottom = MARGIN + 50
    avail_w = PAGE_W - 2 * MARGIN
    avail_h = max(80.0, avail_top - avail_bottom)

    cols, rows, cell_w, cell_h, char_size = _cover_included_layout(
        payloads, avail_w=avail_w, avail_h=avail_h
    )
    gap = 6.0

    # Truncate if even with the chosen cell size we can't fit every item.
    max_rows = max(1, int((avail_h + gap) // (cell_h + gap)))
    if rows > max_rows:
        shown_cap = max_rows * cols
        shown = payloads[:shown_cap]
        overflow = len(payloads) - shown_cap
        rows = max_rows
    else:
        shown = payloads
        overflow = 0

    # Center the grid horizontally.
    grid_w = cols * cell_w + (cols - 1) * gap
    grid_left = MARGIN + (avail_w - grid_w) / 2
    grid_top = avail_top - 6  # small padding below "Included:" label

    # Draw subtle tile backgrounds so the rectangle reads as a composed grid.
    tile_fill = P.PAPER_WARM if hasattr(P, "PAPER_WARM") else None
    c.setStrokeColor(P.GRID_EDGE)
    c.setLineWidth(0.4)

    # Font-size probe: shrink per-tile if a phrase is wider than its cell.
    def _fit_size_for_text(text: str, base: float) -> float:
        if not text:
            return base
        size = base
        while size > 8.0 and c.stringWidth(text, preview_font, size) > cell_w - 4:
            size -= 1.0
        return size

    for i, p in enumerate(shown):
        r = i // cols
        col = i % cols
        x = grid_left + col * (cell_w + gap)
        y_tile_top = grid_top - r * (cell_h + gap)
        y_tile_bot = y_tile_top - cell_h

        if tile_fill is not None:
            c.setFillColor(tile_fill)
            c.roundRect(x, y_tile_bot, cell_w, cell_h, 3, stroke=1, fill=1)

        fs = _fit_size_for_text(p, char_size)
        tw = c.stringWidth(p, preview_font, fs)
        tx = x + (cell_w - tw) / 2
        ty = y_tile_bot + (cell_h - fs) / 2 + fs * 0.18
        c.setFont(preview_font, fs)
        c.setFillColor(P.INK)
        c.drawString(tx, ty, p)

    if overflow > 0:
        note_y = grid_top - rows * (cell_h + gap) + gap - 4
        if note_y > avail_bottom:
            c.setFont(label_font, 9)
            c.setFillColor(P.INK_MUTED)
            c.drawCentredString(
                PAGE_W / 2, note_y, f"… and {overflow} more on the following pages"
            )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def _options_from_legacy_kwargs(text: str, kw: dict) -> PdfJobOptions:
    return PdfJobOptions.from_kwargs(text=text, **kw)


def generate_pdf(
    text: str | None = None,
    *,
    options: PdfJobOptions | None = None,
    progress: ProgressFn | None = None,
    use_cache: bool = True,
    warnings_out: list[str] | None = None,
    **legacy_kwargs,
) -> bytes:
    """Generate a complete PDF and return it as bytes.

    Modern call sites should build a :class:`PdfJobOptions` and pass
    ``options=...``. The legacy keyword form (``generate_pdf(text,
    show_strokes=True, ...)``) is still accepted and converted internally;
    this keeps existing tests / snippets working.
    """
    if options is None:
        if text is None:
            raise TypeError("generate_pdf() requires `text` or `options=`")
        options = _options_from_legacy_kwargs(text, legacy_kwargs)
    elif text is not None and text != options.text:
        # Caller passed text= alongside options; prefer explicit text.
        options = PdfJobOptions.from_kwargs(
            text=text,
            **{
                f.name: getattr(options, f.name)
                for f in options.__dataclass_fields__.values()
                if f.name != "text"
            },
        )

    def _progress(p: float, msg: str) -> None:
        if progress:
            try:
                progress(max(0.0, min(1.0, p)), msg)
            except Exception:
                pass

    if use_cache:
        key = _pdf_cache_key(options)
        hit = _pdf_cache_get(key)
        if hit is not None:
            if warnings_out is not None:
                warnings_out.extend(_pdf_cache_get_warnings(key))
            _progress(1.0, "Loaded cached PDF")
            return hit
    else:
        key = None

    _progress(0.02, "Preparing fonts")
    ensure_label_font()

    if options.all_styles:
        tmap = options.typefaces_by_script_dict() or {}
        style_jobs: list[tuple[str, str]] = [
            (sk, tmap.get(sk, default_typeface_id_for_script(sk))) for sk in FONT_REGISTRY.keys()
        ]
        ensure_all_typefaces_parallel([tid for _, tid in style_jobs])
    else:
        tid = options.typeface_id or default_typeface_id_for_script(options.style_key)
        sk = get_typeface(tid)["script"]
        style_jobs = [(sk, tid)]
        ensure_typeface(tid)

    kaishu_fallback_id = default_typeface_id_for_script("kaishu")
    kaishu_fallback_font = ensure_typeface(kaishu_fallback_id)

    # Build item list once.
    if options.layout_mode == "phrase":
        phrases = phrase_segments(options.text)
        if not phrases:
            phrases = [""]
        items: list[tuple[str, str]] = [("phrase", p) for p in phrases if p]
        if not items:
            items = [("phrase", "")]
    else:
        chars = character_sequence(options.text)
        items = [("char", ch) for ch in chars]

    job_cjk = _collect_job_cjk_chars(items)

    # Prefetch passes.
    _progress(0.15, "Translating")
    texts_for_translation: list[str] = []
    if options.layout_mode == "phrase":
        texts_for_translation.extend(p for _, p in items)
    else:
        texts_for_translation.extend(p for _, p in items)
    prefetch_translations(
        texts_for_translation,
        need_en=options.show_english,
        need_ru=options.show_russian,
    )

    _progress(0.30, "Fetching stroke data")
    if options.show_strokes:
        prefetch_stroke_json(job_cjk)
    if options.show_decomposition or options.show_mmh_gloss:
        ensure_decomposition_data()

    # Canvas setup with compression + metadata.
    buf = BytesIO()
    c = Canvas(buf, pagesize=A4, pageCompression=1, invariant=1)
    c.setTitle(f"PracticeHanzi — {options.text[:30]}" if options.text else "PracticeHanzi")
    c.setAuthor("PracticeHanzi")
    c.setCreator("PracticeHanzi")
    c.setSubject(f"{options.layout_mode} practice")

    page_total = len(style_jobs) * len(items) + (1 if options.cover_page else 0)
    page_num = 0

    if options.cover_page:
        page_num += 1
        label_font = ensure_label_font()
        try:
            _draw_cover_page(
                c,
                label_font=label_font,
                items=items,
                options=options,
                page_total=page_total,
            )
        except Exception:
            pass
        _draw_page_chrome(
            c,
            label_font=label_font,
            script_key="kaishu",
            page_num=page_num,
            page_total=page_total,
            draw_ribbon=options.all_styles,
        )
        c.showPage()

    draw_base = 0.30
    draw_span = 0.65

    for script_key, tid in style_jobs:
        font_name = ensure_typeface(tid)
        fallback_font = font_name if script_key == "kaishu" else kaishu_fallback_font
        script_label = FONT_REGISTRY[script_key]["label"]
        typeface_label = get_typeface(tid)["label"]

        for kind, payload in items:
            page_num += 1
            if page_total > 0:
                _progress(
                    draw_base + draw_span * (page_num / page_total),
                    f"Drawing page {page_num} / {page_total}",
                )
            try:
                if kind == "char":
                    _draw_character_page(
                        c,
                        char=payload,
                        font_name=font_name,
                        fallback_font=fallback_font,
                        script_label=script_label,
                        typeface_label=typeface_label,
                        script_key=script_key,
                        options=options,
                        warnings_out=warnings_out,
                    )
                else:
                    if not payload.strip():
                        continue
                    _draw_phrase_page(
                        c,
                        phrase=payload,
                        font_name=font_name,
                        fallback_font=fallback_font,
                        script_label=script_label,
                        typeface_label=typeface_label,
                        script_key=script_key,
                        options=options,
                        warnings_out=warnings_out,
                    )
            except Exception as exc:
                _draw_error_page(c, payload=payload, err=str(exc), label_font=ensure_label_font())
            # Training pages intentionally omit page chrome (no header/footer) to
            # maximise the vertical budget available for the practice grid and to
            # keep the sheets visually uncluttered.
            c.showPage()

    _progress(0.98, "Finalizing")
    c.save()
    data = buf.getvalue()

    save_translation_cache_now()
    if key is not None:
        _pdf_cache_put(key, data, warnings_out)

    _progress(1.0, "Done")
    return data


def _draw_error_page(c: Canvas, *, payload: str, err: str, label_font: str) -> None:
    c.setFont(label_font, 12)
    c.setFillColor(HexColor("#C62828"))
    c.drawString(MARGIN, PAGE_H - MARGIN - 20, f"Could not render “{payload}”")
    c.setFont(label_font, 9)
    c.setFillColor(P.INK_MUTED)
    c.drawString(MARGIN, PAGE_H - MARGIN - 36, err[:200])


# ---------------------------------------------------------------------------
# Phrase page
# ---------------------------------------------------------------------------
def _draw_phrase_page(
    c: Canvas,
    *,
    phrase: str,
    font_name: str,
    fallback_font: str,
    script_label: str,
    typeface_label: str,
    script_key: str,
    options: PdfJobOptions,
    warnings_out: list[str] | None = None,
) -> None:
    show_strokes = options.show_strokes
    show_radicals = options.show_radicals
    show_decomposition = options.show_decomposition
    show_pinyin = options.show_pinyin
    show_english = options.show_english
    show_russian = options.show_russian
    grid_type = options.grid_type
    practice_rows = options.practice_rows
    char_size_pt = options.char_size_pt
    compact_metadata = options.compact_metadata
    show_mmh_gloss = options.show_mmh_gloss

    usable_w = PAGE_W - 2 * MARGIN
    label_font = ensure_label_font()
    cursor_y = PAGE_H - MARGIN + TRAINING_TOP_RECLAIM_PT

    phrase_chars = [ch for ch in phrase if is_cjk(ch)]
    if not phrase_chars:
        return

    n = len(phrase_chars)
    gap = max(1.0 * mm, char_size_pt * 0.02)
    total_w_budget = usable_w - (n - 1) * gap
    char_box_size = total_w_budget / n
    char_box_size = min(char_box_size, char_size_pt * 1.35)
    char_box_size = max(char_box_size, min(usable_w / n, 36.0))

    inner_fs = char_box_size / 1.15

    cursor_y = _draw_script_typeface_header(
        c,
        label_font=label_font,
        script_label=script_label,
        typeface_label=typeface_label,
        cursor_y=cursor_y,
    )

    row_width = n * char_box_size + (n - 1) * gap
    start_x = MARGIN + (usable_w - row_width) / 2
    char_box_y = cursor_y - char_box_size

    # Per-character pinyin above the row.
    if show_pinyin:
        py_pairs = get_pinyin_per_char(phrase)
        py_map = {ch: py for ch, py in py_pairs if py}
        pfs = max(8.0, min(11.0, inner_fs * 0.12))
        c.setFont(label_font, pfs)
        c.setFillColor(P.PINYIN)
        for i, ch in enumerate(phrase_chars):
            py = py_map.get(ch, "")
            if not py:
                continue
            cx = start_x + i * (char_box_size + gap)
            tw = c.stringWidth(py, label_font, pfs)
            if tw <= char_box_size - 2:
                tx = cx + (char_box_size - tw) / 2
                c.drawString(tx, char_box_y + char_box_size + 2, py)

    for i, ch in enumerate(phrase_chars):
        active_font = font_name if _char_fits_font(font_name, ch) else fallback_font
        c.setFillColor(black)
        c.setFont(active_font, inner_fs)
        tw = c.stringWidth(ch, active_font, inner_fs)
        cx = start_x + i * (char_box_size + gap)
        c.setStrokeColor(GRID_LIGHT)
        c.setLineWidth(1)
        c.rect(cx, char_box_y, char_box_size, char_box_size, stroke=1, fill=0)
        tx = cx + (char_box_size - tw) / 2
        ty = char_box_y + (char_box_size - inner_fs) / 2 + inner_fs * 0.1
        c.drawString(tx, ty, ch)

    show_stroke_block = show_strokes and script_key == "kaishu"
    if show_decomposition and not show_stroke_block:
        fy = max(6.0, min(8.5, char_box_size * 0.18))
        c.setFont(label_font, fy)
        c.setFillColor(P.IDS)
        for i, ch in enumerate(phrase_chars):
            cid = ids_compact(ch)
            if not cid:
                continue
            cx = start_x + i * (char_box_size + gap)
            tw = c.stringWidth(cid, label_font, fy)
            tx = cx + max(0, (char_box_size - tw) / 2)
            c.drawString(tx, char_box_y - 10, cid)

    info_y = char_box_y - 10
    info_y = _draw_phrase_metadata_block(
        c,
        label_font=label_font,
        phrase=phrase,
        usable_w=usable_w,
        margin_x=MARGIN,
        info_y=info_y,
        inner_fs=inner_fs,
        show_pinyin=show_pinyin,
        show_english=show_english,
        show_russian=show_russian,
        char_size_pt=char_size_pt,
        compact=compact_metadata,
        show_mmh_gloss=show_mmh_gloss,
    )

    column_low = min(char_box_y, info_y - 18)

    stroke_low = column_low
    if show_stroke_block:
        stroke_cell = max(14.0, min(22.0, char_box_size * 0.22))
        stroke_gap = max(2.0, stroke_cell * 0.08)
        max_per_row = max(1, int((usable_w + stroke_gap) // (stroke_cell + stroke_gap)))

        c.setFont(label_font, 9.0)
        c.setFillColor(P.STROKE_CAPTION)
        head_bl = column_low - 8
        c.drawString(MARGIN, head_bl, "Stroke order")
        stroke_low = head_bl - 14

        # Duplicates (e.g. 爸爸) only need their stroke order / radical / IDS once.
        _seen: set[str] = set()
        unique_chars: list[str] = []
        for ch in phrase_chars:
            if ch not in _seen:
                _seen.add(ch)
                unique_chars.append(ch)

        for ch in unique_chars:
            sub_head = stroke_low - 6
            c.setFont(label_font, 9.0)
            c.setFillColor(P.STROKE_CAPTION)
            c.drawString(MARGIN, sub_head, f"{ch}:")
            y_meta = sub_head - 11
            if show_radicals:
                cap = radical_caption(ch)
                if cap:
                    c.setFont(label_font, 8.0)
                    c.setFillColor(P.RADICAL)
                    c.drawString(MARGIN, y_meta, cap)
                    c.setFillColor(P.STROKE_CAPTION)
                    y_meta -= 12
            if show_decomposition:
                dlines = decomposition_lines(ch)
                if dlines:
                    c.setFont(label_font, 8.0)
                    c.setFillColor(P.IDS)
                    for dline in dlines:
                        c.drawString(MARGIN, y_meta, dline)
                        y_meta -= 11
            label_baseline = y_meta - 3

            stroke_svgs = render_stroke_sequence(
                ch, cell_size=int(stroke_cell), number_steps=True
            )
            if not stroke_svgs:
                stroke_low = label_baseline - 12
                continue

            n_st = len(stroke_svgs)
            n_rows = int(math.ceil(n_st / max_per_row))
            row_h = stroke_cell + stroke_gap
            row0_bottom = label_baseline - 8 - stroke_cell

            for si, svg_str in enumerate(stroke_svgs):
                row = si // max_per_row
                col = si % max_per_row
                sx = MARGIN + col * (stroke_cell + stroke_gap)
                y_draw = row0_bottom - row * row_h
                try:
                    drawing = svg_to_drawing(svg_str)
                    if drawing:
                        renderPDF.draw(drawing, c, sx, y_draw)
                except Exception:
                    pass

            block_bottom = row0_bottom - (n_rows - 1) * row_h - 6
            stroke_low = block_bottom

    # Practice grid.
    cursor_y = stroke_low - 5 * mm
    c.setFont(label_font, 11)
    c.setFillColor(P.STROKE_CAPTION)
    c.drawString(MARGIN, cursor_y, "Practice:")
    cursor_y -= 5 * mm

    grid_draw = GRID_FUNCS.get(grid_type, _draw_tian_grid)
    cell_size, eff_rows, req_rows = _practice_cell_and_rows(
        stroke_low, practice_rows, char_box_size
    )
    cells_per_row = _phrase_cells_per_row(usable_w, gap, cell_size, n)
    pr_row_w = cells_per_row * cell_size + (cells_per_row - 1) * gap
    start_practice_x = MARGIN + (usable_w - pr_row_w) / 2
    if warnings_out is not None and eff_rows < req_rows:
        warnings_out.append(
            f"«{phrase}»: fit {eff_rows} of {req_rows} practice rows — lower "
            f"character size or reduce practice rows to use all of them."
        )

    base_alpha = options.ghost_opacity
    for row in range(eff_rows):
        row_y = cursor_y - cell_size
        if row_y < MARGIN:
            break
        # Fade ghosts across rows: row0 full, row1 ~60%, row2 ~20%, row3+ none.
        row_alpha = max(0.0, base_alpha * (1.0 - row * 0.45))
        for col in range(cells_per_row):
            cx = start_practice_x + col * (cell_size + gap)
            grid_draw(c, cx, row_y, cell_size)
            if row_alpha > 0:
                ch = phrase_chars[col % n]
                active_font = font_name if _char_fits_font(font_name, ch) else fallback_font
                _draw_ghost_char(c, ch, active_font, cx, row_y, cell_size, alpha=row_alpha)
        cursor_y = row_y - ROW_GAP_PRACTICE


# ---------------------------------------------------------------------------
# Character page
# ---------------------------------------------------------------------------
def _draw_character_page(
    c: Canvas,
    *,
    char: str,
    font_name: str,
    fallback_font: str,
    script_label: str,
    typeface_label: str,
    script_key: str,
    options: PdfJobOptions,
    warnings_out: list[str] | None = None,
) -> None:
    show_strokes = options.show_strokes
    show_radicals = options.show_radicals
    show_decomposition = options.show_decomposition
    show_pinyin = options.show_pinyin
    show_english = options.show_english
    show_russian = options.show_russian
    grid_type = options.grid_type
    practice_rows = options.practice_rows
    char_size_pt = options.char_size_pt

    usable_w = PAGE_W - 2 * MARGIN
    label_font = ensure_label_font()
    cursor_y = PAGE_H - MARGIN + TRAINING_TOP_RECLAIM_PT

    cursor_y = _draw_script_typeface_header(
        c,
        label_font=label_font,
        script_label=script_label,
        typeface_label=typeface_label,
        cursor_y=cursor_y,
    )

    active_font = font_name if _char_fits_font(font_name, char) else fallback_font
    c.setFillColor(black)
    c.setFont(active_font, char_size_pt)
    tw = c.stringWidth(char, active_font, char_size_pt)
    char_box_size = char_size_pt * 1.15

    char_box_x = MARGIN
    char_box_y = cursor_y - char_box_size
    c.setStrokeColor(GRID_LIGHT)
    c.setLineWidth(1)
    c.rect(char_box_x, char_box_y, char_box_size, char_box_size, stroke=1, fill=0)

    tx = char_box_x + (char_box_size - tw) / 2
    ty = char_box_y + (char_box_size - char_size_pt) / 2 + char_size_pt * 0.1
    c.drawString(tx, ty, char)

    if show_decomposition:
        cid = ids_compact(char)
        if cid:
            fy = max(8.0, min(10.0, char_box_size * 0.09))
            c.setFont(label_font, fy)
            c.setFillColor(P.IDS)
            ids_tw = c.stringWidth(cid, label_font, fy)
            ids_tx = char_box_x + (char_box_size - ids_tw) / 2
            c.drawString(ids_tx, char_box_y - 10, cid)

    info_x = char_box_x + char_box_size + 5 * mm
    info_y = cursor_y
    info_line_h = max(16.0, char_size_pt * 0.14)

    if show_pinyin:
        py = get_pinyin(char)
        c.setFont(label_font, max(11.0, char_size_pt * 0.11))
        c.setFillColor(P.PINYIN)
        c.drawString(info_x, info_y - 12, f"Pinyin: {py}")
        info_y -= info_line_h + 4

    if show_radicals:
        rc = radical_caption(char)
        if rc:
            c.setFont(label_font, max(9.0, char_size_pt * 0.09))
            c.setFillColor(P.RADICAL)
            c.drawString(info_x, info_y - 12, rc)
            info_y -= info_line_h

    if show_decomposition:
        dlines = decomposition_lines(char)
        if dlines:
            dfs = max(8.5, char_size_pt * 0.085)
            c.setFont(label_font, dfs)
            c.setFillColor(P.IDS)
            step = max(12.0, char_size_pt * 0.095)
            for dline in dlines:
                c.drawString(info_x, info_y - 12, dline)
                info_y -= step

    if show_english or show_russian:
        translations = get_translations(char, need_en=show_english, need_ru=show_russian)
        fs = max(10.0, char_size_pt * 0.095)
        c.setFont(label_font, fs)
        if show_english and translations["en"]:
            c.setFillColor(P.EN)
            c.drawString(info_x, info_y - 12, f"EN: {translations['en']}")
            info_y -= info_line_h
        if show_russian and translations["ru"]:
            c.setFillColor(P.RU)
            c.drawString(info_x, info_y - 12, f"RU: {translations['ru']}")
            info_y -= info_line_h

    column_low = min(char_box_y, info_y - 18)

    stroke_low = column_low
    show_stroke_block = show_strokes and script_key == "kaishu"
    if show_stroke_block:
        stroke_cell = max(28.0, min(char_box_size * 0.36, usable_w * 0.10))
        stroke_gap = max(3.0, stroke_cell * 0.08)
        max_per_row = max(1, int((usable_w + stroke_gap) // (stroke_cell + stroke_gap)))

        stroke_svgs = render_stroke_sequence(
            char, cell_size=int(stroke_cell), number_steps=True
        )
        if stroke_svgs:
            label_baseline = column_low - 10
            c.setFont(label_font, 9.5)
            c.setFillColor(P.STROKE_CAPTION)
            c.drawString(MARGIN, label_baseline, "Stroke order")

            n = len(stroke_svgs)
            n_rows = int(math.ceil(n / max_per_row))
            row_h = stroke_cell + stroke_gap

            row0_bottom = label_baseline - 18 - stroke_cell
            for i, svg_str in enumerate(stroke_svgs):
                row = i // max_per_row
                col = i % max_per_row
                sx = MARGIN + col * (stroke_cell + stroke_gap)
                y_draw = row0_bottom - row * row_h
                try:
                    drawing = svg_to_drawing(svg_str)
                    if drawing:
                        renderPDF.draw(drawing, c, sx, y_draw)
                except Exception:
                    pass

            stroke_low = row0_bottom - (n_rows - 1) * row_h - 6

    cursor_y = stroke_low - 5 * mm
    c.setFont(label_font, 11)
    c.setFillColor(P.STROKE_CAPTION)
    c.drawString(MARGIN, cursor_y, "Practice:")
    cursor_y -= 5 * mm

    grid_draw = GRID_FUNCS.get(grid_type, _draw_tian_grid)
    cell_size, eff_rows, req_rows = _practice_cell_and_rows(
        stroke_low, practice_rows, char_box_size
    )
    cells_per_row = max(1, int(usable_w // cell_size))
    if warnings_out is not None and eff_rows < req_rows:
        warnings_out.append(
            f"«{char}»: fit {eff_rows} of {req_rows} practice rows — lower "
            f"character size or reduce practice rows to use all of them."
        )

    base_alpha = options.ghost_opacity
    for row in range(eff_rows):
        row_y = cursor_y - cell_size
        if row_y < MARGIN:
            break
        row_alpha = max(0.0, base_alpha * (1.0 - row * 0.45))
        for col in range(cells_per_row):
            cx = MARGIN + col * cell_size
            grid_draw(c, cx, row_y, cell_size)
            if row_alpha > 0:
                _draw_ghost_char(c, char, active_font, cx, row_y, cell_size, alpha=row_alpha)
        cursor_y = row_y - ROW_GAP_PRACTICE
