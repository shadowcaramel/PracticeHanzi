# Chinese Calligraphy Training Sheet Generator

A small **Streamlit** web application that builds **printable A4 PDF** practice sheets for Chinese calligraphy. You can enter single characters, words, or short phrases. **Layout** is inferred automatically (spaces or line breaks → phrase-style sheets; one continuous line without spaces → one sheet per character). Pick a **script** (楷书 / 行书 / …) and a **named typeface** within it, with a **Pillow preview**. **Word banks** replace the text box with a preset or **HSK 3.0** sample (HSK uses **random** sampling by default). Each sheet shows **script name then typeface** in the PDF header, optional **stroke order** (caption: “Stroke order”), optional **部首** radical line (Unicode Unihan), **pinyin**, **EN/RU**, and **practice grids** that **tile** across the row (phrase mode repeats the phrase; character mode ghosts every cell on the first row).

---

## Features

- **Page layout (automatic)** — More than one whitespace-separated CJK segment, or multiple lines → **phrase** sheets (one row per segment). A single run without spaces → **character** sheets (one page per character).  
- **Typefaces** — Pick **script** then **typeface** (several OFL options per bucket where available; some extra faces are JP-influenced Google Fonts—check previews). Pillow preview sample: `汉语很难`. Stroke diagrams only for **楷书** script (hanzi-writer-data).  
- **All five scripts** — One PDF page per script (楷·行·草·隶·篆); optional per-script typeface overrides in the sidebar.  
- **Word banks** — Presets under `data/presets/`; **Load** replaces the entire text box (no append).  
- **HSK 3.0 (new) sample** — **Load** replaces the text box; **random sample is on by default**; data from [complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary) (MIT), cached under `data/hsk/`.  
- **Radicals (optional)** — Checkbox adds a **部首** line using Unicode **Unihan kRSUnicode** (first use downloads `Unihan.zip` from unicode.org into `data/radicals/`, then builds a small JSON cache).  
- **Stroke order** from [hanzi-writer-data](https://github.com/chanind/hanzi-writer-data) / [Make Me a Hanzi](https://github.com/skishore/makemeahanzi): progressive **楷书** steps; stroke JSON is **prefetched in parallel** before drawing. PDF caption is **“Stroke order”**; full attribution remains in upstream projects.  
- **Speed** — EN/RU translations run **in parallel** when both are enabled; only requested languages are fetched; stroke JSON is prefetched for all characters in the job.  
- **Pinyin** via [pypinyin](https://github.com/mozillazg/python-pinyin).  
- **Translations** via [deep-translator](https://github.com/nidhaloff/deep-translator) (Google Translate backend; requires internet).  
- **Grids**: 田字格 (field), 米字格 (rice), or plain square; adjustable practice rows and main character size (slider **40–200 pt**, step **5**).  
- **Phrase layout** — Practice cell size is **shrunk** if needed so at least one practice row fits below strokes / IDS / translations; requested row count may be reduced if the page is full. **Phrase mode** tiles practice columns in **whole-phrase** widths (e.g. 2 columns for a 2-character phrase when 3 would show only 1.5 repeats).  
- **Compact translations (phrase pages)** — Optional single-row **Pinyin | EN | RU** (three columns) when display size is **≥100 pt**; falls back to stacked lines if text is too long.  
- **MMH gloss (phrase pages, optional)** — One line of short **per-character** English glosses from Make Me a Hanzi `dictionary.txt` (not sample sentences).

---

## Requirements

- **Python 3.10+**  
- **Internet** on first run (font downloads, stroke JSON, translations).  
- **Disk**: cached data under `fonts/`, `stroke_cache/`, `data/hsk/`, `data/radicals/` (Unihan when you use radicals), and `data/mmh/` (Make Me a Hanzi `dictionary.txt` when you use IDS or MMH gloss), including a ~17 MB **Noto Sans SC** UI font on first PDF generation.

---

## Installation

From the project root (the folder that contains `app.py`), create a **virtual environment**, activate it, then install dependencies.

**venv** (recommended; works everywhere Python is installed):

```bash
python -m venv .venv
```

Activate it:

- **Windows (cmd/PowerShell):** `.venv\Scripts\activate`
- **macOS / Linux:** `source .venv/bin/activate`

Then:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

**Conda** (optional): create and use any env name you like, for example:

```bash
conda create -n calligraphy-sheets python=3.12 -y
conda activate calligraphy-sheets
python -m pip install -r requirements.txt
```

---

## How to launch

With the same environment **activated**:

```bash
streamlit run app.py
```

Then open the URL shown in the terminal (by default **http://localhost:8501**).

### How to stop the app

In the **same terminal** where Streamlit is running, press **Ctrl+C** (Windows/Linux) or **Ctrl+Break** on some keyboards. Wait until the process exits and the shell prompt returns. If the terminal is closed without stopping Streamlit, the process may keep running in the background until ended from Task Manager or another shell.

**Typical workflow**

1. Enter **Chinese text** (multi-line area); layout follows spacing rules above.  
2. Optionally **Word banks** → load a preset or HSK sample (replaces the text box).  
3. Pick **script + typeface** (or **all five scripts** with optional per-script faces).  
4. Toggle stroke order, radicals, pinyin, English, Russian, IDS/structure, **compact translations** and **MMH gloss** (phrases).  
5. Set **grid**, **practice rows**, **character size**.  
6. **Generate PDF**, then **Download PDF**.

---

## Technical description

### Stack

| Layer | Technology |
|--------|------------|
| UI | [Streamlit](https://streamlit.io/) |
| PDF | [ReportLab](https://www.reportlab.com/) (`Canvas`, A4 portrait) |
| SVG in PDF | [svglib](https://github.com/deeplook/svglib) (`svg2rlg` + `renderPDF`) |
| Fonts | Calligraphy: TrueType (`.ttf`). **PDF labels / pinyin / EN / RU**: **Noto Sans SC** (variable TTF, ~17 MB, downloaded once to `fonts/`) so tone marks and Cyrillic embed correctly; ReportLab `pdfmetrics` / `TTFont` |
| Pinyin | [pypinyin](https://pypi.org/project/pypinyin/) |
| Translation | [deep-translator](https://pypi.org/project/deep-translator/) → Google Translate |
| HTTP | [requests](https://pypi.org/project/requests/) (fonts, stroke JSON) |

### Project layout

```
app.py                 # Streamlit entry point and UI
requirements.txt       # Python dependencies
README.md              # This file
data/
  presets/             # Small bundled JSON word lists for “Word banks”
  hsk/                 # Cached HSK inclusive lists (created when you use HSK; optional)
  radicals/            # Unihan.zip + kRS BMP cache (optional; first radical use)
  mmh/                 # Make Me a Hanzi dictionary.txt (optional; IDS / MMH gloss)
utils/
  fonts.py             # Typeface registry, download, ReportLab registration, PIL previews
  segmentation.py      # Phrase vs character splitting for PDF layout
  presets.py           # Preset loader + optional HSK download/sample
  radicals.py          # Unihan kRSUnicode → Kangxi radical caption (BMP)
  stroke_order.py      # hanzi-writer-data fetch/cache, SVG generation, svglib bridge
  pinyin_utils.py      # Tone-marked pinyin helpers
  translation.py       # EN/RU translation with LRU cache + parallel fetch
  pdf_generator.py     # Character and phrase page layout, stroke blocks, grids
  decomposition.py   # MMH dictionary: IDS, etymology lines, phrase gloss
fonts/                 # Downloaded TTFs (created automatically)
stroke_cache/          # Per-character stroke JSON cache (created automatically)
```

### Data flow

1. **Fonts** — On demand, `utils/fonts.py` downloads each TTF if missing, then registers a unique ReportLab font name per **typeface**. Seal script is fetched from a GitHub **release** asset; Google Fonts families use **google/fonts** raw paths.  
2. **Stroke order** — For each CJK character, `utils/stroke_order.py` requests JSON from jsDelivr (`hanzi-writer-data`), caches it under `stroke_cache/`, builds small SVGs. Path **y** coordinates are converted from Hanzi Writer character space (**y up**, top at 900) to SVG space (**y down**) with `svg_y = 900 - y` (see `Positioner.ts` in [hanzi-writer](https://github.com/chanind/hanzi-writer)). `utils/pdf_generator.py` draws the block **only** when the active **script** is **楷书** (`kaishu`).  
3. **PDF** — **Character mode** walks each character; **phrase mode** walks whitespace-separated CJK phrases. PDF **header**: script label (e.g. 楷书…) then **typeface** name. **Practice**: cells are sized to fit the remaining vertical space (may be smaller than the header character row); character mode ghosts **every** cell on the first practice row; phrase mode **tiles** the phrase in columns that are a **multiple of the phrase length** when possible. **Stroke** block title is **“Stroke order”**. **Radicals** (optional): `utils/radicals.py` reads cached **kRSUnicode** for BMP hanzi and prints Kangxi presentation + stroke remainder. **Phrase metadata**: optional compact **Pinyin / EN / RU** row and optional **MMH gloss** from `utils/decomposition.py`.  
4. **Translations** — Phrase- or character-level; `functools.lru_cache` on each language; **parallel** requests when both EN and RU are enabled; skipped languages are not requested.  
5. **HSK lists** — `utils/presets.py` downloads inclusive new-level JSON from [complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary) (MIT) into `data/hsk/`.  
6. **Prefetch** — Before drawing pages, unique CJK in the job are used to warm the stroke JSON cache (`prefetch_stroke_json`).

### PDF layout (conceptual)

- Top: **script** line, then **typeface** line.  
- **Character mode**: main box + optional pinyin / radical / EN / RU; stroke strip; practice grid with full-width tiled ghosts on row 1.  
- **Phrase mode**: centered phrase row; phrase pinyin / EN / RU (compact or stacked); optional MMH gloss; per-character stroke blocks; practice rows tile the phrase in whole-phrase column groups with rescaled cells if vertical space is tight.

### Limitations and notes

- **Seal script font** covers a finite set of characters; missing glyphs fall back to the standard (楷书) font for display.  
- **Stroke data** follows simplified-oriented hanzi-writer coverage; rare characters may have no JSON (stroke block is skipped). There is **no** comparable open, per-character stroke-SVG corpus for seal / clerical / semi-cursive / grass script in the same form factor, so those styles **do not** show stroke diagrams.  
- **Translation** depends on a third-party web service; failures return empty strings for that language.  
- **Windows console**: if you run scripts that print Chinese text in `cmd.exe`, set UTF-8 (e.g. `chcp 65001` or `PYTHONIOENCODING=utf-8`) to avoid encoding errors; Streamlit in the browser is unaffected.

### Dependencies (`requirements.txt`)

```
streamlit
reportlab
svglib
pypinyin
deep-translator
requests
Pillow
```

---

## Licenses (third-party fonts)

The bundled/downloaded fonts are used under their respective licenses (typically **SIL OFL 1.1** for the Google Fonts families and the seal script project). Keep the font files for personal or commercial use according to each font’s license text shipped with or linked from the upstream repositories.

### HSK vocabulary data (optional)

If you use **HSK word samples**, JSON is fetched from [drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary), which is published under the **MIT License**. Attribution: Yanis Zafirópulos (Dr.Kameleon), 2026. Cached files live under `data/hsk/` on your machine.

### Unihan / radicals (optional)

Radical captions use the Unicode **Unihan** database (`kRSUnicode` in `Unihan_IRGSources.txt` inside [Unihan.zip](https://www.unicode.org/Public/zipped/16.0.0/Unihan.zip)). Follow the [Unicode Terms of Use](https://www.unicode.org/copyright.html). Cached files: `data/radicals/Unihan.zip` and `data/radicals/krs_bmp_cache.json`.

---

## Repository maintenance

- Safe to delete `fonts/`, `stroke_cache/`, `data/hsk/`, `data/radicals/`, and `data/mmh/` to force re-download (slower next run).  
- The project `.gitignore` excludes downloaded caches, virtual envs, and **Cursor** plan files under `.cursor/plans/` so the repo stays lean; adjust if you want to track any of those paths.
