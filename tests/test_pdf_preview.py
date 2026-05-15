"""PDF thumbnail dependency checks."""

from unittest.mock import patch

from utils import pdf_preview as pv


def test_is_available_requires_poppler_on_path() -> None:
    import builtins
    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name == "pdf2image":
            return object()
        return real_import(name, *args, **kwargs)

    with (
        patch.object(builtins, "__import__", side_effect=_import),
        patch.object(pv, "_poppler_on_path", return_value=False),
    ):
        ok, reason = pv.is_available()
    assert not ok
    assert "poppler" in reason.lower()


def test_is_available_ok_when_pdf2image_and_poppler() -> None:
    with patch.object(pv, "_poppler_on_path", return_value=True):
        ok, reason = pv.is_available()
    # Skip if pdf2image not installed in this environment.
    if reason.startswith("Missing Python package"):
        return
    assert ok
    assert reason == ""
