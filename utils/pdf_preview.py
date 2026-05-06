"""Generate a page-1 PNG thumbnail for the Streamlit UI.

Rendering a full PDF and converting it to an image requires poppler +
``pdf2image``. Both are heavy deps, so this module is best-effort: it
returns ``None`` (and a one-line reason) when either isn't available, and
callers should hide the preview in that case instead of erroring.
"""

from __future__ import annotations

from io import BytesIO


def is_available() -> tuple[bool, str]:
    """Return ``(ok, reason)`` so callers can show a useful caption."""
    try:
        import pdf2image  # noqa: F401
    except Exception:
        return False, "Install `pdf2image` + poppler for a live preview."
    return True, ""


def render_first_page_png(pdf_bytes: bytes, dpi: int = 200, max_px: int = 2000) -> bytes | None:
    """Return a PNG of page 1 of *pdf_bytes*, or ``None`` on failure."""
    try:
        from pdf2image import convert_from_bytes
        from PIL import Image
    except Exception:
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
