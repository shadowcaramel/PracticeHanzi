---
name: PDF headers practice fonts
overview: Update PDF headers to show script style then typeface; expand the OFL typeface catalog; fix practice grids (tile phrase and fill character rows); shorten stroke captions; simplify word banks and HSK defaults; outline a phased radical feature; speed up generation where safe.
todos:
  - id: header-two-line
    content: Pass script_label + typeface_label from generate_pdf; draw both in _draw_character_page and _draw_phrase_page
    status: completed
  - id: stroke-caption
    content: Replace long stroke-order caption with 'Stroke order' in both page draw functions
    status: completed
  - id: practice-tile
    content: "Character: ghost full first row; Phrase: cells_per_row from usable_w + tile phrase_chars[col % n]"
    status: completed
  - id: typefaces-expand
    content: Add vetted OFL typefaces per script (focus xingshu/caoshu/lishu/zhuanshu) in fonts.py
    status: completed
  - id: wordbanks-hsk-ui
    content: "app.py: preset load replaces only; HSK random default True; HSK load replaces text"
    status: completed
  - id: speed-translate-prefetch
    content: Parallel EN/RU in get_translations; prefetch stroke JSON for unique chars before draw loop
    status: completed
  - id: radicals-phase1
    content: utils/radicals.py + small data/cache; optional PDF line + Streamlit toggle
    status: completed
  - id: readme
    content: README updates for headers, practice, word banks, HSK, radicals data, speed notes
    status: completed
isProject: false
---

# PDF polish, typefaces, practice grid, radicals research, speed

## 1. PDF header: script first, then typeface

**Current:** [`utils/pdf_generator.py`](g:/Мой диск/Китайский язык/Training sheets generator/utils/pdf_generator.py) sets `style_label = get_typeface(tid)["label"]` (typeface name only) and passes it into `_draw_character_page` / `_draw_phrase_page` as a single header line.

**Change:**

- In `generate_pdf`, derive two strings per page:
  - `script_label` = [`FONT_REGISTRY[script_key]["label"]`](g:/Мой диск/Китайский язык/Training sheets generator/utils/fonts.py) (e.g. `楷书 Kǎishū (Standard)`).
  - `typeface_label` = `get_typeface(tid)["label"]` (e.g. `Ma Shan Zheng 马善政`).
- Extend `_draw_character_page` / `_draw_phrase_page` signatures to accept both (or a small struct); draw **two lines** at the top (script line first, slightly larger or same size; typeface second in muted gray), or one line with explicit separator if vertical space is tight.

## 2. Stroke order caption

Replace the long string in both `_draw_character_page` and `_draw_phrase_page` with exactly **`Stroke order`** (keep per-character `你:` labels as today). Attribution can move to README only if you still want legal clarity.

## 3. Practice rows: fill width (character + phrase)

**Character mode** ([`_draw_character_page`](g:/Мой диск/Китайский язык/Training sheets generator/utils/pdf_generator.py) ~474–496): `cells_per_row = int(usable_w // cell_size)` already allows many cells, but **`ghost_count = min(2, cells_per_row)`** only ghosts the first two cells. **Fix:** on the first practice row, ghost **every** cell (or up to `cells_per_row`) with the same target character so the row is fully usable for tracing.

**Phrase mode** ([`_draw_phrase_page`](g:/Мой диск/Китайский язык/Training sheets generator/utils/pdf_generator.py) ~338–361): today `cells_per_row = n` (phrase length), so **北京** yields only **2** squares per row. **Fix:** compute how many cells fit the row: `cells_per_row = max(1, int((usable_w + gap) // (cell_size + gap)))` using the same `cell_size` / `gap` as the main phrase row, then **tile** the phrase left-to-right: character at column `col` is `phrase_chars[col % n]`. Center the full practice row using `row_width = cells_per_row * cell_size + (cells_per_row - 1) * gap`. First row: draw ghosts for the tiled pattern; later rows: empty grids (same as now).

**Tall phrases / low vertical space:** if practice rows still clip (`row_y < MARGIN`), optionally shrink practice `cell_size` slightly (floor) so at least one row fits, or cap stroke block height—only if needed after testing with long phrase + strokes.

## 4. More typefaces (especially 行/草/隶/篆)

**Current:** [`TYPEFACES`](g:/Мой диск/Китайский язык/Training sheets generator/utils/fonts.py) has multiple 楷书 entries but **one** face each for `xingshu`, `caoshu`, `lishu`, `zhuanshu`.

**Approach:**

- Curate **additional SIL-OFL** entries from the official [`google/fonts` `ofl/`](https://github.com/google/fonts/tree/main/ofl) tree (raw `githubusercontent` TTF URLs), verifying **OFL.txt** per family. Good-faith script buckets (appearance-based, not “pen type”):
  - **行书:** e.g. semi-cursive / brush-script Simplified-Chinese faces (candidates to validate: families similar to Zhi Mang Xing / handwritten linkage; avoid Latin-only fonts).
  - **草书 / 隶书:** add at least one extra distinct face per bucket where GF offers a second Simplified-compatible display font (e.g. additional **ZCOOL** / handwritten releases clerical-ish or brush-ish—each must be checked for coverage and license).
  - **篆书:** OFL seal-style options are scarce; keep JFZSK as default, add **one** more only if a clear OFL + stable raw URL exists (otherwise document limitation in README).

- Add helper already present pattern: `list_typeface_ids_for_script` continues to filter by `script` key on each dict.

## 5. Word banks and HSK UI ([`app.py`](g:/Мой диск/Китайский язык/Training sheets generator/app.py))

- **Presets:** remove “Insert words” / two-column flow; single control **“Load preset”** that sets `_pending_main_text` to `" ".join(load_preset(cat))` (always replace).
- **HSK:** set **Random sample** checkbox default to **`True`** (`value=True`). Rename button to **“Load HSK sample”** (or similar) and set `_pending_main_text` to **only** the HSK chunk (replace, do not concatenate with existing text), matching “always replace” for word banks.

## 6. Radicals + description (research + phased implementation)

**Data sources (machine-readable):**

- **Unicode Unihan** [`kRSUnicode`](https://www.unicode.org/reports/tr38/) (radical index + stroke count) via Unicode’s [Unihan](https://github.com/unicode-org/unihan-database) / UCD downloads.
- **Radical glyph + English gloss:** small bundled table for the **214 Kangxi** radicals (index → character → short English name); optional Chinese name column.

**Feasible v1 in-app:**

- New module e.g. [`utils/radicals.py`](g:/Мой диск/Китайский язык/Training sheets generator/utils/radicals.py): `radical_info(char: str) -> dict | None` resolving primary Han character to `{radical_char, radical_index, strokes_after_radical, name_en, name_zh?}`.
- Ship a **minimal** JSON/CSV in `data/` (Kangxi table + optional subset of Unihan kRSUnicode for BMP) **or** lazy-download Unihan zip on first use into `data/unihan/` (similar to HSK cache) to avoid huge repo blobs—product choice in implementation.
- **PDF:** optional checkbox “Show radical (部首)” on character pages (and optionally under each char subsection on phrase stroke blocks): one line like `部首: 宀 (roof)` using Noto Sans SC.

**Out of scope for first pass unless time:** traditional vs simplified alternate radicals, every Extension-B rare character.

## 7. Speed up PDF generation

**Hot spots today:** per-page `get_translations` ([`utils/translation.py`](g:/Мой диск/Китайский язык/Training sheets generator/utils/translation.py)) runs EN then RU sequentially; stroke JSON fetch on cache miss ([`utils/stroke_order.py`](g:/Мой диск/Китайский язык/Training sheets generator/utils/stroke_order.py)); SVG→ReportLab per step.

**Concrete optimizations (low risk):**

- **Translations:** in `get_translations`, run `translate_to_english` and `translate_to_russian` in parallel (`concurrent.futures.ThreadPoolExecutor`, max 2 workers) when both toggles on; keep `lru_cache` on the underlying functions.
- **Prefetch:** before the page loop in `generate_pdf`, collect the set of CJK characters appearing in `items` (and phrase chars); call a new `prefetch_stroke_json(chars: set[str])` that issues bounded parallel `requests` (or sequential with short timeout) only for missing cache files—reduces wait inside the tight draw loop.
- **Optional:** warm `ensure_typeface` for all typeface IDs used in the job once at start (single- and all-styles paths).

**Do not** parallelize ReportLab canvas drawing across threads (not thread-safe); keep drawing single-threaded.

## 8. Docs

Update [`README.md`](g:/Мой диск/Китайский язык/Training sheets generator/README.md) briefly: header format, practice tiling behavior, stroke caption, word-bank replace-only, HSK random default, radical feature + data license (Unicode terms of use for Unihan if bundled/downloaded).

## Files to touch (expected)

| Area | Files |
|------|--------|
| Header + stroke caption + practice | [`utils/pdf_generator.py`](g:/Мой диск/Китайский язык/Training sheets generator/utils/pdf_generator.py) |
| Typeface list | [`utils/fonts.py`](g:/Мой диск/Китайский язык/Training sheets generator/utils/fonts.py) |
| Word banks / HSK UI | [`app.py`](g:/Мой диск/Китайский язык/Training sheets generator/app.py) |
| Stroke prefetch | [`utils/stroke_order.py`](g:/Мой диск/Китайский язык/Training sheets generator/utils/stroke_order.py), [`utils/pdf_generator.py`](g:/Мой диск/Китайский язык/Training sheets generator/utils/pdf_generator.py) |
| Parallel translate | [`utils/translation.py`](g:/Мой диск/Китайский язык/Training sheets generator/utils/translation.py) |
| Radicals (new) | `utils/radicals.py`, `data/radicals*.json` or cache dir, optional UI + PDF hooks |
| Docs | [`README.md`](g:/Мой диск/Китайский язык/Training sheets generator/README.md) |

**Note on attached PDFs:** binary PDFs are not ideal to diff in the IDE; the layout fixes above follow directly from the current code paths (`ghost_count` and `cells_per_row = n` in phrase practice).
