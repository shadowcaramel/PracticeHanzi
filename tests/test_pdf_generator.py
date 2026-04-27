"""Practice-grid tracing (ghost) behaviour."""

import pytest

from utils.pdf_generator import _practice_row_ghost_alpha


def test_single_practice_row_has_no_ghost() -> None:
    """Large header / one fitted row: entire practice strip must stay blank."""
    base = 0.25
    assert _practice_row_ghost_alpha(0, 1, base) == 0.0


def test_last_row_never_ghosted() -> None:
    base = 0.2
    for eff in range(2, 8):
        assert _practice_row_ghost_alpha(eff - 1, eff, base) == 0.0


def test_upper_rows_keep_downward_fade() -> None:
    base = 0.2
    assert _practice_row_ghost_alpha(0, 4, base) == pytest.approx(base)
    assert _practice_row_ghost_alpha(1, 4, base) == pytest.approx(base * 0.55)
    assert _practice_row_ghost_alpha(2, 4, base) == pytest.approx(base * 0.10)
    assert _practice_row_ghost_alpha(3, 4, base) == 0.0


def test_invalid_eff_rows() -> None:
    assert _practice_row_ghost_alpha(0, 0, 0.2) == 0.0
