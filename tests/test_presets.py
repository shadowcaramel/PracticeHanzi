"""Bundled preset JSON files."""

from utils.presets import load_preset, preset_label


def test_strokes_loads():
    words = load_preset("strokes")
    assert len(words) == 8
    assert words == ["一", "丨", "丿", "丶", "乛", "乙", "亅", "乚"]


def test_strokes_label():
    assert "笔画" in preset_label("strokes")
