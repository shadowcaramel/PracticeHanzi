"""Typed helpers for Streamlit session state.

The main UI used free-form ``st.session_state._pending_*`` keys from multiple
callbacks. Collecting them behind tiny functions keeps the call sites
readable and the keys in one place — which matters because Streamlit's
widget keys *and* our pending keys share the same dict.
"""

from __future__ import annotations

from typing import Any, Optional

import streamlit as st

# Keys in one place so the whole app agrees on spelling.
K_MAIN_TEXT = "main_text"
K_PENDING_TEXT = "_pending_main_text"
K_PDF_NAME_SOURCE = "pdf_name_source"
K_PDF_LOADED_SNAPSHOT = "pdf_loaded_snapshot"
K_PENDING_NAME_SOURCE = "_pending_pdf_name_source"
K_PENDING_LOADED_SNAPSHOT = "_pending_pdf_loaded_snapshot"


def queue_text_and_source(text: str, source: tuple[str, Any] | None = None) -> None:
    """Schedule a sidebar text-box update + PDF-name source (applied on next rerun).

    Streamlit will re-render the sidebar top-down; these pending keys are
    applied by :func:`apply_pending_text` before the text widget is drawn.
    """
    st.session_state[K_PENDING_TEXT] = text
    if source is not None:
        st.session_state[K_PENDING_NAME_SOURCE] = source
        st.session_state[K_PENDING_LOADED_SNAPSHOT] = text.strip()


def apply_pending_text() -> None:
    """Flush queued sidebar text updates into the active widget state."""
    if K_PENDING_TEXT in st.session_state:
        st.session_state[K_MAIN_TEXT] = st.session_state.pop(K_PENDING_TEXT)
        if K_PENDING_NAME_SOURCE in st.session_state:
            st.session_state[K_PDF_NAME_SOURCE] = st.session_state.pop(K_PENDING_NAME_SOURCE)
        if K_PENDING_LOADED_SNAPSHOT in st.session_state:
            st.session_state[K_PDF_LOADED_SNAPSHOT] = st.session_state.pop(
                K_PENDING_LOADED_SNAPSHOT
            )


def get_pdf_name_source_for_text(current_text: str) -> Optional[tuple[str, Any]]:
    """Return the stored name source only if *current_text* still matches the snapshot."""
    ti = current_text.strip()
    if ti and ti == st.session_state.get(K_PDF_LOADED_SNAPSHOT):
        src = st.session_state.get(K_PDF_NAME_SOURCE)
        if isinstance(src, tuple) and len(src) == 2:
            return src
    return None
