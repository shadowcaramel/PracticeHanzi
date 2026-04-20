"""Fetch stroke order data from hanzi-writer-data and render SVG sequences."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "stroke_cache"

CDN_URL = "https://cdn.jsdelivr.net/npm/hanzi-writer-data@2.0/{char}.json"

VIEWBOX = 1024
# Hanzi Writer / Make Me a Hanzi character space: y increases upward, y in [-124, 900].
# See chanind/hanzi-writer Positioner.ts CHARACTER_BOUNDS.
CHAR_Y_TOP = 900.0

STROKE_COLOR = "#333333"
STROKE_LIGHT = "#cccccc"
HIGHLIGHT_COLOR = "#d32f2f"


def _is_cjk(char: str) -> bool:
    cp = ord(char)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x20000 <= cp <= 0x2A6DF
        or 0xF900 <= cp <= 0xFAFF
    )


def fetch_stroke_data(char: str) -> dict | None:
    """Return stroke JSON for a single character, or None if unavailable.

    The on-disk cache is lazily upgraded with a ``svg_strokes`` list of
    pre-transformed path strings; callers that only need the transformed
    paths can read them without re-running the parser.
    """
    if not _is_cjk(char):
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{ord(char):05X}.json"

    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            try:
                cache_file.unlink()
            except Exception:
                pass

    url = CDN_URL.format(char=char)
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
    except Exception:
        return None


def _get_transformed_paths(char: str) -> list[str] | None:
    """Return the transformed SVG path list for *char*, caching on disk."""
    data = fetch_stroke_data(char)
    if not data or "strokes" not in data:
        return None
    svg_strokes = data.get("svg_strokes")
    if isinstance(svg_strokes, list) and svg_strokes and all(isinstance(s, str) for s in svg_strokes):
        return svg_strokes
    transformed = [_transform_path(p) for p in data["strokes"]]
    data["svg_strokes"] = transformed
    try:
        cache_file = CACHE_DIR / f"{ord(char):05X}.json"
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return transformed


def prefetch_stroke_json(chars: set[str], *, max_workers: int = 6) -> None:
    """Ensure stroke JSON is cached for all CJK characters in *chars* (parallel network)."""
    todo = [ch for ch in chars if _is_cjk(ch)]
    if not todo:
        return

    def _one(ch: str) -> None:
        fetch_stroke_data(ch)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_one, ch) for ch in todo]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass


def _char_space_y_to_svg_y(y: float) -> float:
    """Map Make Me a Hanzi y (upward) to SVG user y (downward) inside viewBox height 1024."""
    return CHAR_Y_TOP - y


@lru_cache(maxsize=4096)
def _transform_path(d: str) -> str:
    """Convert path coordinates from hanzi-writer character space to SVG coordinates.

    Paths use space-separated numbers (not comma-separated). Y is flipped with
    svg_y = CHAR_Y_TOP - y per Hanzi Writer / Make Me a Hanzi bounds.
    """
    out: list[str] = []
    i = 0
    n = len(d)

    def _skip_sep() -> None:
        nonlocal i
        while i < n and d[i] in " \t\n,":
            i += 1

    def _read_float() -> float:
        nonlocal i
        _skip_sep()
        start = i
        if i < n and d[i] in "+-":
            i += 1
        while i < n and d[i] in "0123456789.":
            i += 1
        return float(d[start:i])

    while True:
        _skip_sep()
        if i >= n:
            break
        cmd = d[i].upper()
        if cmd == "Z":
            out.append("Z")
            i += 1
            continue
        if cmd not in "MLCQ":
            out.append(d[i])
            i += 1
            continue
        i += 1
        out.append(cmd)

        if cmd in "ML":
            x = _read_float()
            y = _char_space_y_to_svg_y(_read_float())
            out.append(f" {x:g} {y:g}")
        elif cmd == "Q":
            x1 = _read_float()
            y1 = _char_space_y_to_svg_y(_read_float())
            x = _read_float()
            y = _char_space_y_to_svg_y(_read_float())
            out.append(f" {x1:g} {y1:g} {x:g} {y:g}")
        elif cmd == "C":
            x1 = _read_float()
            y1 = _char_space_y_to_svg_y(_read_float())
            x2 = _read_float()
            y2 = _char_space_y_to_svg_y(_read_float())
            x = _read_float()
            y = _char_space_y_to_svg_y(_read_float())
            out.append(f" {x1:g} {y1:g} {x2:g} {y2:g} {x:g} {y:g}")
        else:
            # Unknown command: copy rest conservatively
            rest_start = i
            while i < n and d[i].upper() not in "MLCQZ":
                i += 1
            out.append(d[rest_start:i])

    return "".join(out)


def render_stroke_step_svg(
    strokes: list[str],
    up_to: int,
    size: int = 80,
    *,
    step_label: int | None = None,
    transformed: bool = False,
) -> str:
    """Render an SVG showing strokes[0..up_to-1] in dark, stroke[up_to-1]
    highlighted in red, and remaining strokes in light gray.

    When ``step_label`` is given, its integer value is drawn at the top-left
    corner of the SVG — useful for printable order diagrams. ``transformed``
    skips ``_transform_path`` (caller already handled it).
    """
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{size}" height="{size}" '
        f'viewBox="0 0 {VIEWBOX} {VIEWBOX}">'
    ]

    for i, raw_d in enumerate(strokes):
        d = raw_d if transformed else _transform_path(raw_d)
        if i < up_to - 1:
            color = STROKE_COLOR
        elif i == up_to - 1:
            color = HIGHLIGHT_COLOR
        else:
            color = STROKE_LIGHT
        parts.append(f'<path d="{d}" fill="{color}" />')

    if step_label is not None:
        parts.append(
            f'<text x="40" y="160" font-family="sans-serif" '
            f'font-size="180" font-weight="bold" '
            f'fill="{HIGHLIGHT_COLOR}" opacity="0.85">{step_label}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def render_stroke_sequence(
    char: str,
    cell_size: int = 80,
    *,
    number_steps: bool = False,
) -> list[str] | None:
    """Return a list of SVG strings showing progressive stroke buildup,
    or None if data is unavailable. Pass ``number_steps=True`` to stamp a
    1-based step label in the top-left of each cell.
    """
    paths = _get_transformed_paths(char)
    if not paths:
        return None

    n = len(paths)
    return [
        render_stroke_step_svg(
            paths,
            step,
            size=cell_size,
            step_label=step if number_steps else None,
            transformed=True,
        )
        for step in range(1, n + 1)
    ]


def render_full_char_svg(char: str, size: int = 80) -> str | None:
    """Render the completed character from stroke data as a single SVG."""
    data = fetch_stroke_data(char)
    if not data or "strokes" not in data:
        return None

    strokes = data["strokes"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{size}" height="{size}" '
        f'viewBox="0 0 {VIEWBOX} {VIEWBOX}">'
    ]
    for raw_d in strokes:
        d = _transform_path(raw_d)
        parts.append(f'<path d="{d}" fill="{STROKE_COLOR}" />')
    parts.append("</svg>")
    return "\n".join(parts)


_DRAWING_CACHE: dict[str, object] = {}


def svg_to_drawing(svg_string: str):
    """Convert an SVG string to a reportlab Drawing using svglib.

    Parsing SVGs is the slowest single step in stroke-heavy pages. Drawings
    returned here are memoized by SHA-1 of the SVG source; ``renderPDF.draw``
    accepts the same Drawing object on any Canvas, so cached results stay
    valid across pages and jobs.
    """
    key = hashlib.sha1(svg_string.encode("utf-8")).hexdigest()
    cached = _DRAWING_CACHE.get(key)
    if cached is not None:
        return cached
    from svglib.svglib import svg2rlg
    bio = BytesIO(svg_string.encode("utf-8"))
    drawing = svg2rlg(bio)
    if drawing is not None:
        # Cap cache growth; simple LFU-style prune when it gets large.
        if len(_DRAWING_CACHE) > 4000:
            for k in list(_DRAWING_CACHE.keys())[:500]:
                _DRAWING_CACHE.pop(k, None)
        _DRAWING_CACHE[key] = drawing
    return drawing
