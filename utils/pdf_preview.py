"""Generate a page-1 PNG thumbnail for the Streamlit UI.

Requires the ``pdf2image`` Python package and Poppler utilities (``pdftoppm``)
on ``PATH``. On Streamlit Community Cloud, declare ``pdf2image`` in
``requirements.txt`` and ``poppler-utils`` in ``packages.txt``.
"""

from __future__ import annotations

import shutil
from io import BytesIO


def _poppler_on_path() -> bool:
    return shutil.which("pdftoppm") is not None


def is_available() -> tuple[bool, str]:
    """Return ``(ok, reason)`` so callers can show a useful message."""
    try:
        import pdf2image  # noqa: F401
    except ImportError:
        return (
            False,
            "Missing Python package `pdf2image`. Install dependencies: "
            "`pip install -r requirements.txt`.",
        )
    if not _poppler_on_path():
        return (
            False,
            "Poppler is not on PATH (`pdftoppm` not found). "
            "**Streamlit Cloud:** add `poppler-utils` to `packages.txt` and redeploy. "
            "**Linux:** `sudo apt-get install -y poppler-utils`. "
            "**macOS:** `brew install poppler`. "
            "**Windows:** install [poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases) "
            "and add its `bin` folder to PATH.",
        )
    return True, ""


def render_first_page_png(pdf_bytes: bytes, dpi: int = 200, max_px: int = 2000) -> bytes | None:
    """Return a PNG of page 1 of *pdf_bytes*, or ``None`` on failure."""
    ok, _ = is_available()
    if not ok:
        return None
    try:
        from pdf2image import convert_from_bytes
        from PIL import Image
    except ImportError:
        return None
    try:
        images = convert_from_bytes(pdf_bytes, dpi=dpi, first_page=1, last_page=1)
        if not images:
            return None
        img = images[0]
        w, h = img.size
        longest = max(w, h)
        if longest > max_px:
            scale = max_px / longest
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        out = BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return None
