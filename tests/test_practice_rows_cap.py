"""Practice row slider cap derived from A4 layout at minimum character size."""

from utils.pdf_generator import (
    MIN_CHAR_DISPLAY_PT,
    PRACTICE_ROWS_SLIDER_MAX,
    max_practice_rows_for_char_size,
)


def test_slider_max_at_minimum_char_size_is_about_fifteen() -> None:
    assert PRACTICE_ROWS_SLIDER_MAX == max_practice_rows_for_char_size(MIN_CHAR_DISPLAY_PT)
    assert 14 <= PRACTICE_ROWS_SLIDER_MAX <= 16


def test_larger_char_size_allows_fewer_rows() -> None:
    small = max_practice_rows_for_char_size(20)
    large = max_practice_rows_for_char_size(200)
    assert large < small
