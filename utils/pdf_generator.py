"""Generate printable A4 PDF calligraphy training sheets using reportlab."""

from io import BytesIO
import math

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import Color, HexColor, black
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.graphics import renderPDF

from utils.fonts import (
    FONT_REGISTRY,
    default_typeface_id_for_script,
    ensure_label_font,
    ensure_typeface,
    get_typeface,
)
from utils.stroke_order import prefetch_stroke_json, render_stroke_sequence, svg_to_drawing
from utils.pinyin_utils import get_pinyin
from utils.translation import get_translations
from utils.radicals import radical_caption
from utils.decomposition import (
    decomposition_lines,
    ensure_decomposition_data,
    ids_compact,
    phrase_mmh_gloss,
)
from utils.segmentation import character_sequence, phrase_segments, is_cjk

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm

GRID_LIGHT = HexColor("#BBBBBB")
GRID_MID = HexColor("#DDDDDD")
GHOST_ALPHA = 0.15


def _draw_tian_grid(c: Canvas, x: float, y: float, size: float) -> None:
    """Draw a 田字格 (field-character grid) cell at (x, y) bottom-left."""
    c.setStrokeColor(GRID_LIGHT)
    c.setLineWidth(0.7)
    c.rect(x, y, size, size, stroke=1, fill=0)
    c.setStrokeColor(GRID_MID)
    c.setLineWidth(0.4)
    c.setDash(3, 3)
    half = size / 2
    c.line(x + half, y, x + half, y + size)
    c.line(x, y + half, x + size, y + half)
    c.setDash()


def _draw_mi_grid(c: Canvas, x: float, y: float, size: float) -> None:
    """Draw a 米字格 (rice-character grid) cell at (x, y) bottom-left."""
    c.setStrokeColor(GRID_LIGHT)
    c.setLineWidth(0.7)
    c.rect(x, y, size, size, stroke=1, fill=0)
    c.setStrokeColor(GRID_MID)
    c.setLineWidth(0.4)
    c.setDash(3, 3)
    half = size / 2
    c.line(x + half, y, x + half, y + size)
    c.line(x, y + half, x + size, y + half)
    c.line(x, y, x + size, y + size)
    c.line(x, y + size, x + size, y)
    c.setDash()


def _draw_plain_grid(c: Canvas, x: float, y: float, size: float) -> None:
    c.setStrokeColor(GRID_LIGHT)
    c.setLineWidth(0.7)
    c.rect(x, y, size, size, stroke=1, fill=0)


GRID_FUNCS = {
    "tian": _draw_tian_grid,
    "mi": _draw_mi_grid,
    "plain": _draw_plain_grid,
}

# Practice grid: vertical budget (matches stroke_low → "Practice:" → first row spacing).
PRACTICE_HEADER_BEFORE_GRID = 5 * mm + 5 * mm
ROW_GAP_PRACTICE = 2 * mm
PRACTICE_CELL_MIN = 16.0
BOTTOM_SAFE_PT = 10.0
# Use compact 3-column Pinyin/EN/RU when display size is at or above this (phrase mode).
COMPACT_METADATA_CHAR_PT = 100


def _truncate_to_width_canvas(
    c: Canvas, font_name: str, font_size: float, text: str, max_w: float
) -> str:
    """Truncate *text* with ellipsis so it fits *max_w* in the current font metrics."""
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


def _practice_cell_and_rows(
    stroke_low: float, practice_rows: int, char_box_cap: float
) -> tuple[float, int]:
    """Shrink practice cell and optionally row count so the grid fits above the bottom margin."""
    ref = stroke_low - PRACTICE_HEADER_BEFORE_GRID
    avail = ref - MARGIN - BOTTOM_SAFE_PT
    want = max(1, practice_rows)
    if avail <= 0:
        return max(12.0, min(char_box_cap, PRACTICE_CELL_MIN)), 1
    for r in range(want, 0, -1):
        inner = avail - (r - 1) * ROW_GAP_PRACTICE
        if inner <= 0:
            continue
        cell_fit = inner / r
        cell = min(char_box_cap, cell_fit)
        cell = max(PRACTICE_CELL_MIN, cell)
        total = r * cell + (r - 1) * ROW_GAP_PRACTICE
        if total <= avail:
            return cell, r
    cell = max(PRACTICE_CELL_MIN, min(char_box_cap, avail))
    return cell, 1


def _phrase_cells_per_row(usable_w: float, gap: float, practice_cell: float, n: int) -> int:
    """Prefer whole-phrase widths: columns are a multiple of *n* when possible."""
    if practice_cell + gap <= 0:
        return max(1, n)
    max_cells = max(1, int((usable_w + gap) // (practice_cell + gap)))
    full_mult = (max_cells // n) * n
    if full_mult >= n:
        return full_mult
    return max_cells


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
    """Draw pinyin / EN / RU / optional MMH gloss; return updated info_y (lower on page)."""
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
            pieces.append((f"Pinyin: {py}", HexColor("#1565C0")))
        if show_english and en:
            pieces.append((f"EN: {en}", HexColor("#2E7D32")))
        if show_russian and ru:
            pieces.append((f"RU: {ru}", HexColor("#6A1B9A")))
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
            c.setFillColor(HexColor("#1565C0"))
            c.drawString(margin_x, info_y - 12, f"Pinyin: {py}")
            info_y -= info_line_h + 4
        fs = max(9.0, inner_fs * 0.1)
        c.setFont(label_font, fs)
        if show_english and en:
            c.setFillColor(HexColor("#2E7D32"))
            c.drawString(margin_x, info_y - 12, f"EN: {en}")
            info_y -= info_line_h
        if show_russian and ru:
            c.setFillColor(HexColor("#6A1B9A"))
            c.drawString(margin_x, info_y - 12, f"RU: {ru}")
            info_y -= info_line_h

    if mmh_line:
        mfs = max(8.0, inner_fs * 0.09)
        c.setFont(label_font, mfs)
        c.setFillColor(HexColor("#5D4037"))
        mt = _truncate_to_width_canvas(c, label_font, mfs, mmh_line, usable_w - 2)
        c.drawString(margin_x, info_y - 12, mt)
        info_y -= info_line_h

    return info_y


def _char_fits_font(font_name: str, char: str) -> bool:
    """Check if the given font contains a glyph for *char*."""
    try:
        font = pdfmetrics.getFont(font_name)
        if hasattr(font, "face") and hasattr(font.face, "charWidths"):
            return ord(char) in font.face.charWidths
        w = font.stringWidth(char, 10)
        return w > 0
    except Exception:
        return True


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


def _draw_script_typeface_header(
    c: Canvas,
    *,
    label_font: str,
    script_label: str,
    typeface_label: str,
    cursor_y: float,
) -> float:
    """Draw script line then typeface line; return updated cursor_y (baseline of last line)."""
    c.setFont(label_font, 14)
    c.setFillColor(HexColor("#37474F"))
    c.drawString(MARGIN, cursor_y - 14, script_label)
    c.setFont(label_font, 11)
    c.setFillColor(HexColor("#546E7A"))
    c.drawString(MARGIN, cursor_y - 30, typeface_label)
    return cursor_y - 38


def _draw_ghost_char(
    c: Canvas, char: str, font_name: str, x: float, y: float, size: float
) -> None:
    """Draw a faint tracing guide character centered in a grid cell."""
    c.saveState()
    c.setFillColor(Color(0, 0, 0, alpha=GHOST_ALPHA))
    font_size = size * 0.85
    c.setFont(font_name, font_size)
    tw = c.stringWidth(char, font_name, font_size)
    tx = x + (size - tw) / 2
    ty = y + (size - font_size) / 2 + font_size * 0.1
    c.drawString(tx, ty, char)
    c.restoreState()


def generate_pdf(
    text: str,
    *,
    typeface_id: str | None = None,
    style_key: str = "kaishu",
    typefaces_by_script: dict[str, str] | None = None,
    layout_mode: str = "character",
    show_strokes: bool = True,
    show_radicals: bool = False,
    show_decomposition: bool = False,
    show_pinyin: bool = True,
    show_english: bool = True,
    show_russian: bool = True,
    grid_type: str = "tian",
    practice_rows: int = 3,
    char_size_pt: int = 120,
    all_styles: bool = False,
    compact_metadata: bool = True,
    show_mmh_gloss: bool = False,
) -> bytes:
    """Generate a complete PDF and return it as bytes.

    layout_mode: ``character`` — one page per non-whitespace character (legacy).
    ``phrase`` — one page per whitespace-separated CJK phrase (see ``phrase_segments``).

    Pick a font with ``typeface_id`` (see ``TYPEFACES`` in ``utils.fonts``), or leave it
    ``None`` and pass ``style_key`` to use each script’s default typeface.

    When ``all_styles`` is True, optional ``typefaces_by_script`` maps each script key to a
    typeface id (defaults apply for missing keys).

    ``compact_metadata`` (phrase pages): when True and ``char_size_pt`` ≥ 100, try one-row
    Pinyin / EN / RU; otherwise stacked lines. ``show_mmh_gloss``: optional per-character
    MMH English gloss line on phrase pages.
    """

    ensure_label_font()

    buf = BytesIO()
    c = Canvas(buf, pagesize=A4)

    kaishu_fallback_id = default_typeface_id_for_script("kaishu")
    kaishu_fallback_font = ensure_typeface(kaishu_fallback_id)

    if all_styles:
        tmap = typefaces_by_script or {}
        style_jobs: list[tuple[str, str]] = [
            (sk, tmap.get(sk, default_typeface_id_for_script(sk))) for sk in FONT_REGISTRY.keys()
        ]
    else:
        tid = typeface_id or default_typeface_id_for_script(style_key)
        sk = get_typeface(tid)["script"]
        style_jobs = [(sk, tid)]

    if layout_mode == "phrase":
        phrases = phrase_segments(text)
        if not phrases:
            phrases = [""]
        items: list[tuple[str, str]] = [("phrase", p) for p in phrases if p]
        if not items:
            items = [("phrase", "")]
    else:
        chars = character_sequence(text)
        items = [("char", ch) for ch in chars]

    job_cjk = _collect_job_cjk_chars(items)
    if show_strokes:
        prefetch_stroke_json(job_cjk)
    if show_decomposition or show_mmh_gloss:
        ensure_decomposition_data()
    for _, tid in style_jobs:
        ensure_typeface(tid)

    for script_key, tid in style_jobs:
        font_name = ensure_typeface(tid)
        fallback_font = font_name if script_key == "kaishu" else kaishu_fallback_font
        script_label = FONT_REGISTRY[script_key]["label"]
        typeface_label = get_typeface(tid)["label"]

        for kind, payload in items:
            if kind == "char":
                _draw_character_page(
                    c,
                    char=payload,
                    font_name=font_name,
                    fallback_font=fallback_font,
                    script_label=script_label,
                    typeface_label=typeface_label,
                    style_key=script_key,
                    show_strokes=show_strokes,
                    show_radicals=show_radicals,
                    show_decomposition=show_decomposition,
                    show_pinyin=show_pinyin,
                    show_english=show_english,
                    show_russian=show_russian,
                    grid_type=grid_type,
                    practice_rows=practice_rows,
                    char_size_pt=char_size_pt,
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
                    style_key=script_key,
                    show_strokes=show_strokes,
                    show_radicals=show_radicals,
                    show_decomposition=show_decomposition,
                    show_pinyin=show_pinyin,
                    show_english=show_english,
                    show_russian=show_russian,
                    grid_type=grid_type,
                    practice_rows=practice_rows,
                    char_size_pt=char_size_pt,
                    compact_metadata=compact_metadata,
                    show_mmh_gloss=show_mmh_gloss,
                )
            c.showPage()

    c.save()
    return buf.getvalue()


def _draw_phrase_page(
    c: Canvas,
    *,
    phrase: str,
    font_name: str,
    fallback_font: str,
    script_label: str,
    typeface_label: str,
    style_key: str,
    show_strokes: bool,
    show_radicals: bool,
    show_decomposition: bool,
    show_pinyin: bool,
    show_english: bool,
    show_russian: bool,
    grid_type: str,
    practice_rows: int,
    char_size_pt: int,
    compact_metadata: bool,
    show_mmh_gloss: bool,
) -> None:
    """One row of character cells for *phrase*, compact stroke blocks, phrase-wide practice rows."""
    usable_w = PAGE_W - 2 * MARGIN
    label_font = ensure_label_font()
    cursor_y = PAGE_H - MARGIN

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

    show_stroke_block = show_strokes and style_key == "kaishu"
    if show_decomposition and not show_stroke_block:
        fy = max(6.0, min(8.0, char_box_size * 0.18))
        c.setFont(label_font, fy)
        c.setFillColor(HexColor("#6D4C41"))
        for i, ch in enumerate(phrase_chars):
            cid = ids_compact(ch)
            if not cid:
                continue
            cx = start_x + i * (char_box_size + gap)
            tw = c.stringWidth(cid, label_font, fy)
            tx = cx + max(0, (char_box_size - tw) / 2)
            c.drawString(tx, char_box_y - 8, cid)

    # --- Metadata: full phrase below the row (compact 3-col or stacked) ---
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

    # --- Compact stroke order: 楷书 only ---
    stroke_low = column_low
    if show_stroke_block:
        stroke_cell = max(14.0, min(22.0, char_box_size * 0.22))
        stroke_gap = max(2.0, stroke_cell * 0.08)
        max_per_row = max(1, int((usable_w + stroke_gap) // (stroke_cell + stroke_gap)))

        c.setFont(label_font, 9.0)
        c.setFillColor(HexColor("#555555"))
        head_bl = column_low - 8
        c.drawString(MARGIN, head_bl, "Stroke order")
        stroke_low = head_bl - 14

        for ch in phrase_chars:
            sub_head = stroke_low - 6
            c.setFont(label_font, 9.0)
            c.setFillColor(HexColor("#555555"))
            c.drawString(MARGIN, sub_head, f"{ch}:")
            y_meta = sub_head - 11
            if show_radicals:
                cap = radical_caption(ch)
                if cap:
                    c.setFont(label_font, 8.0)
                    c.setFillColor(HexColor("#666666"))
                    c.drawString(MARGIN, y_meta, cap)
                    c.setFillColor(HexColor("#555555"))
                    y_meta -= 12
            if show_decomposition:
                dlines = decomposition_lines(ch)
                if dlines:
                    c.setFont(label_font, 8.0)
                    c.setFillColor(HexColor("#6D4C41"))
                    for dline in dlines:
                        c.drawString(MARGIN, y_meta, dline)
                        y_meta -= 11
            label_baseline = y_meta - 3

            stroke_svgs = render_stroke_sequence(ch, cell_size=int(stroke_cell))
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

    # --- Practice: tile phrase across usable width; ghosts on first row ---
    cursor_y = stroke_low - 5 * mm

    c.setFont(label_font, 11)
    c.setFillColor(HexColor("#555555"))
    c.drawString(MARGIN, cursor_y, "Practice:")
    cursor_y -= 5 * mm

    grid_draw = GRID_FUNCS.get(grid_type, _draw_tian_grid)
    cell_size, eff_rows = _practice_cell_and_rows(
        stroke_low, practice_rows, char_box_size
    )
    cells_per_row = _phrase_cells_per_row(usable_w, gap, cell_size, n)
    pr_row_w = cells_per_row * cell_size + (cells_per_row - 1) * gap
    start_practice_x = MARGIN + (usable_w - pr_row_w) / 2

    for row in range(eff_rows):
        row_y = cursor_y - cell_size
        if row_y < MARGIN:
            break
        for col in range(cells_per_row):
            cx = start_practice_x + col * (cell_size + gap)
            grid_draw(c, cx, row_y, cell_size)
            if row == 0:
                ch = phrase_chars[col % n]
                active_font = font_name if _char_fits_font(font_name, ch) else fallback_font
                _draw_ghost_char(c, ch, active_font, cx, row_y, cell_size)
        cursor_y = row_y - ROW_GAP_PRACTICE


def _draw_character_page(
    c: Canvas,
    *,
    char: str,
    font_name: str,
    fallback_font: str,
    script_label: str,
    typeface_label: str,
    style_key: str,
    show_strokes: bool,
    show_radicals: bool,
    show_decomposition: bool,
    show_pinyin: bool,
    show_english: bool,
    show_russian: bool,
    grid_type: str,
    practice_rows: int,
    char_size_pt: int,
) -> None:
    usable_w = PAGE_W - 2 * MARGIN
    label_font = ensure_label_font()
    cursor_y = PAGE_H - MARGIN

    cursor_y = _draw_script_typeface_header(
        c,
        label_font=label_font,
        script_label=script_label,
        typeface_label=typeface_label,
        cursor_y=cursor_y,
    )

    # --- Main character display ---
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

    # --- Right column: pinyin + translations (same scale as main = readable) ---
    info_x = char_box_x + char_box_size + 5 * mm
    info_y = cursor_y
    info_line_h = max(16.0, char_size_pt * 0.14)

    if show_pinyin:
        py = get_pinyin(char)
        c.setFont(label_font, max(11.0, char_size_pt * 0.11))
        c.setFillColor(HexColor("#1565C0"))
        c.drawString(info_x, info_y - 12, f"Pinyin: {py}")
        info_y -= info_line_h + 4

    if show_radicals:
        rc = radical_caption(char)
        if rc:
            c.setFont(label_font, max(9.0, char_size_pt * 0.09))
            c.setFillColor(HexColor("#455A64"))
            c.drawString(info_x, info_y - 12, rc)
            info_y -= info_line_h

    if show_decomposition:
        dlines = decomposition_lines(char)
        if dlines:
            dfs = max(8.5, char_size_pt * 0.085)
            c.setFont(label_font, dfs)
            c.setFillColor(HexColor("#6D4C41"))
            step = max(12.0, char_size_pt * 0.095)
            for dline in dlines:
                c.drawString(info_x, info_y - 12, dline)
                info_y -= step

    if show_english or show_russian:
        translations = get_translations(char, need_en=show_english, need_ru=show_russian)
        fs = max(10.0, char_size_pt * 0.095)
        c.setFont(label_font, fs)
        if show_english and translations["en"]:
            c.setFillColor(HexColor("#2E7D32"))
            c.drawString(info_x, info_y - 12, f"EN: {translations['en']}")
            info_y -= info_line_h
        if show_russian and translations["ru"]:
            c.setFillColor(HexColor("#6A1B9A"))
            c.drawString(info_x, info_y - 12, f"RU: {translations['ru']}")
            info_y -= info_line_h

    # Lowest y touched by the top row (character box vs. right-column text)
    column_low = min(char_box_y, info_y - 18)

    # --- Stroke order: only for 楷书 (kaishu); open data is MMH / hanzi-writer regular script ---
    stroke_low = column_low
    show_stroke_block = show_strokes and style_key == "kaishu"
    if show_stroke_block:
        # Smaller than main box; paths are Make Me a Hanzi / hanzi-writer regular script.
        stroke_cell = max(28.0, min(char_box_size * 0.36, usable_w * 0.10))
        stroke_gap = max(3.0, stroke_cell * 0.08)
        max_per_row = max(1, int((usable_w + stroke_gap) // (stroke_cell + stroke_gap)))

        stroke_svgs = render_stroke_sequence(char, cell_size=int(stroke_cell))
        if stroke_svgs:
            label_baseline = column_low - 10
            c.setFont(label_font, 9.5)
            c.setFillColor(HexColor("#555555"))
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

    # --- Practice grid: cell size matches main character box ---
    cursor_y = stroke_low - 5 * mm

    c.setFont(label_font, 11)
    c.setFillColor(HexColor("#555555"))
    c.drawString(MARGIN, cursor_y, "Practice:")
    cursor_y -= 5 * mm

    grid_draw = GRID_FUNCS.get(grid_type, _draw_tian_grid)
    cell_size, eff_rows = _practice_cell_and_rows(
        stroke_low, practice_rows, char_box_size
    )
    cells_per_row = max(1, int(usable_w // cell_size))
    ghost_count = cells_per_row

    for row in range(eff_rows):
        row_y = cursor_y - cell_size
        if row_y < MARGIN:
            break
        for col in range(cells_per_row):
            cx = MARGIN + col * cell_size
            grid_draw(c, cx, row_y, cell_size)
            if row == 0 and col < ghost_count:
                _draw_ghost_char(c, char, active_font, cx, row_y, cell_size)
        cursor_y = row_y - ROW_GAP_PRACTICE
