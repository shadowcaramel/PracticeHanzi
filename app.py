"""Chinese Calligraphy Training Sheet Generator — Streamlit UI."""

import streamlit as st

st.set_page_config(
    page_title="Chinese Calligraphy Sheets",
    page_icon="🖌️",
    layout="wide",
)

from utils.fonts import (
    FONT_REGISTRY,
    default_typeface_id_for_script,
    get_typeface,
    list_typeface_ids_for_script,
    render_typeface_preview_png,
    style_label,
    typeface_option_label,
)
from utils.pdf_generator import generate_pdf
from utils.presets import list_preset_names, load_preset, sample_hsk_words
from utils.pdf_naming import build_practice_hanzi_pdf_filename
from utils.segmentation import (
    character_sequence,
    extract_cjk,
    infer_layout_mode,
    phrase_segments,
)

SCRIPT_ORDER = list(FONT_REGISTRY.keys())

if "main_text" not in st.session_state:
    st.session_state.main_text = "永"

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container { max-width: 960px; padding-top: 2rem; }
    h1 { font-size: 1.8rem !important; }
    .stRadio > div { flex-direction: row; gap: 0.5rem; flex-wrap: wrap; }
    div[data-testid="stExpander"] { border: 1px solid #e0e0e0; border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Chinese Calligraphy Training Sheet Generator")
st.caption(
    "Generate printable A4 practice sheets with large-scale calligraphy characters, "
    "stroke order, pinyin, and translations."
)

# ---------------------------------------------------------------------------
# Sidebar — all controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Settings")

    # Word-bank / HSK buttons queue text updates here (must run before the text widget).
    if "_pending_main_text" in st.session_state:
        st.session_state.main_text = st.session_state.pop("_pending_main_text")
        if "_pending_pdf_name_source" in st.session_state:
            st.session_state["pdf_name_source"] = st.session_state.pop("_pending_pdf_name_source")
        if "_pending_pdf_loaded_snapshot" in st.session_state:
            st.session_state["pdf_loaded_snapshot"] = st.session_state.pop(
                "_pending_pdf_loaded_snapshot"
            )

    st.text_area(
        "Chinese text",
        height=260,
        key="main_text",
        help="Type or paste characters, words, or phrases. Multiple lines or spaces between "
        "segments switch to phrase-style sheets (one page per segment). A single continuous "
        "line without spaces uses one page per character.",
    )
    st.caption(
        "Layout is chosen automatically: **spaces or line breaks** between parts → one sheet per "
        "segment; **no spaces** in a line → one sheet per character."
    )

    with st.expander("Word banks"):
        _presets = list_preset_names()
        if _presets:
            _cat = st.selectbox("Preset category", _presets, index=0, key="preset_cat")
            if st.button("Load preset into text box", key="btn_preset_load"):
                loaded = " ".join(load_preset(_cat))
                st.session_state._pending_main_text = loaded
                st.session_state._pending_pdf_name_source = ("preset", _cat)
                st.session_state._pending_pdf_loaded_snapshot = loaded.strip()
                st.rerun()
        else:
            st.caption("No preset files found under data/presets/.")

        st.markdown("**HSK 3.0 (new) sample**")
        st.caption(
            "Vocabulary: MIT-licensed [complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary) "
            "(downloaded once into data/hsk/)."
        )
        _hsk_lvl = st.selectbox(
            "HSK level",
            [1, 2, 3, 4, 5, 6, 7],
            index=0,
            format_func=lambda n: f"Level {n}" + (" (levels 7–9 band)" if n == 7 else ""),
            key="hsk_lvl",
        )
        _hsk_n = st.number_input("Word count", min_value=5, max_value=400, value=24, step=1, key="hsk_n")
        _hsk_rand = st.checkbox("Random sample", value=True, key="hsk_rand")
        if st.button("Load HSK sample into text box", key="btn_hsk"):
            try:
                chunk = sample_hsk_words(int(_hsk_lvl), int(_hsk_n), randomize=_hsk_rand)
                joined = " ".join(chunk)
                st.session_state._pending_main_text = joined
                st.session_state._pending_pdf_name_source = ("hsk", int(_hsk_lvl))
                st.session_state._pending_pdf_loaded_snapshot = joined.strip()
                st.rerun()
            except Exception as e:
                st.error(str(e))

    st.subheader("Calligraphy style & typeface")
    all_styles = st.checkbox(
        "All five scripts (one PDF page per script)",
        value=False,
        help="Each practice unit is repeated for 楷 / 行 / 草 / 隶 / 篆 using the typefaces you pick below.",
    )

    selected_typeface_single: str | None = None
    typefaces_by_script: dict[str, str] | None = None

    if not all_styles:
        selected_script = st.radio(
            "Script",
            options=SCRIPT_ORDER,
            format_func=style_label,
            horizontal=True,
            key="script_pick",
        )
        _tfs = list_typeface_ids_for_script(selected_script)
        _def_tid = default_typeface_id_for_script(selected_script)
        _idx = _tfs.index(_def_tid) if _def_tid in _tfs else 0
        selected_typeface_single = st.selectbox(
            "Typeface (this script)",
            options=_tfs,
            index=_idx,
            format_func=typeface_option_label,
            key=f"typeface_sel_{selected_script}",
            help="Defaults match the original app fonts; pick another face in the same script if you like.",
        )
        try:
            st.image(
                render_typeface_preview_png(selected_typeface_single),
                caption="Preview sample: 汉语很难",
            )
        except Exception:
            st.caption("Preview will appear after the font file is downloaded.")
    else:
        selected_script = "kaishu"
        with st.expander("Typeface per script (defaults = original five fonts)", expanded=False):
            st.caption("Customize which font is used for each script bucket.")
            typefaces_by_script = {}
            for sk in SCRIPT_ORDER:
                opts = list_typeface_ids_for_script(sk)
                def_tid = default_typeface_id_for_script(sk)
                ix = opts.index(def_tid) if def_tid in opts else 0
                typefaces_by_script[sk] = st.selectbox(
                    style_label(sk),
                    options=opts,
                    index=ix,
                    format_func=typeface_option_label,
                    key=f"tf_ms_{sk}",
                )

    st.subheader("Content options")
    show_strokes = st.checkbox(
        "Show stroke order (楷书 / standard script only)",
        value=True,
        help="Uses hanzi-writer-data (Make Me a Hanzi). Diagrams are drawn only for 楷书 "
        "typefaces — not for 行/草/隶/篆.",
    )
    if not all_styles and selected_typeface_single:
        if show_strokes and get_typeface(selected_typeface_single)["script"] != "kaishu":
            st.caption(
                "Stroke diagrams are omitted for this typeface (not 楷书). Pick a 楷书 script + typeface, "
                "or use “All five scripts” to get diagrams on the 楷书 page only."
            )
    elif show_strokes and all_styles:
        st.caption("Stroke diagrams appear only on the 楷书 page for each unit (not on the other four).")
    show_pinyin = st.checkbox("Show pinyin", value=True)
    show_english = st.checkbox("Show English translation", value=True)
    show_russian = st.checkbox("Show Russian translation", value=True)
    show_radicals = st.checkbox(
        "Show radical (部首, BMP CJK)",
        value=False,
        help="Uses Unicode Unihan kRSUnicode (downloads Unihan.zip once into data/radicals/).",
    )
    show_decomposition = st.checkbox(
        "Show IDS & character structure (Make Me a Hanzi)",
        value=False,
        help="Ideographic Description Sequence (e.g. ⿰女马) plus etymology when present in "
        "Make Me a Hanzi dictionary.txt (downloads ~1 MB once into data/mmh/). "
        "Phonetic/semantic labels follow MMH; not every character is covered.",
    )
    compact_translations = st.checkbox(
        "Compact translations on phrase pages (single row when possible)",
        value=True,
        help="At display size ≥100 pt, places Pinyin / EN / RU in one row (three columns). "
        "Falls back to stacked lines if text is too long.",
    )
    show_mmh_gloss = st.checkbox(
        "Show MMH per-character gloss (phrase pages)",
        value=False,
        help="Short English gloss from Make Me a Hanzi per character (not a full sentence example). "
        "Uses the same dictionary.txt as IDS.",
    )

    st.subheader("Grid & sizing")
    grid_type = st.selectbox(
        "Grid type",
        options=["tian", "mi", "plain"],
        format_func=lambda g: {"tian": "田字格 (Tián)", "mi": "米字格 (Mǐ)", "plain": "Plain square"}[g],
        index=0,
    )
    practice_rows = st.slider("Practice rows", min_value=1, max_value=6, value=3)
    char_size = st.slider("Character display size (pt)", min_value=40, max_value=200, value=120, step=5)

text_input = st.session_state.get("main_text", "")
layout_mode = infer_layout_mode(text_input)

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
chars = character_sequence(text_input)
phrase_list = phrase_segments(text_input)
cjk_present = bool(extract_cjk(text_input))

if layout_mode == "phrase":
    if not cjk_present:
        st.info("Add at least one Chinese character (phrases are split on spaces and line breaks).")
        st.stop()
    content_units = len(phrase_list)
else:
    if not chars:
        st.info("Enter one or more characters in the sidebar to get started.")
        st.stop()
    content_units = len(chars)

# Show a preview of selected settings
col1, col2 = st.columns([1, 2])
with col1:
    if layout_mode == "phrase":
        st.markdown("**Phrases (pages):**")
        st.markdown("### " + (" · ".join(phrase_list) if phrase_list else "—"))
    else:
        st.markdown("**Characters:**")
        st.markdown(f"### {' '.join(chars)}")
with col2:
    if all_styles:
        st.markdown("**Typeface:** Custom per script (see sidebar) or defaults")
    elif selected_typeface_single:
        st.markdown(
            f"**Script:** {style_label(selected_script)}  \n**Typeface:** {get_typeface(selected_typeface_single)['label']}"
        )
    opts = []
    _stroke_ok = show_strokes and (
        all_styles
        or (
            selected_typeface_single is not None
            and get_typeface(selected_typeface_single)["script"] == "kaishu"
        )
    )
    if _stroke_ok:
        opts.append("Stroke order")
    if show_pinyin:
        opts.append("Pinyin")
    if show_english:
        opts.append("EN translation")
    if show_russian:
        opts.append("RU translation")
    if show_radicals:
        opts.append("Radicals")
    if show_decomposition:
        opts.append("IDS / structure")
    if layout_mode == "phrase" and compact_translations:
        opts.append("Compact translations")
    if layout_mode == "phrase" and show_mmh_gloss:
        opts.append("MMH gloss")
    st.markdown(f"**Showing:** {', '.join(opts) if opts else 'Character only'}")

    st.markdown(
        f"**Layout (auto):** {'One page per phrase segment' if layout_mode == 'phrase' else 'One page per character'}"
    )
    n_pages = content_units * (len(FONT_REGISTRY) if all_styles else 1)
    st.markdown(f"**Pages:** {n_pages}")

st.divider()

# Generate button
if st.button("Generate PDF", type="primary", use_container_width=True):
    with st.spinner("Downloading fonts & generating PDF…"):
        try:
            pdf_bytes = generate_pdf(
                text_input,
                typeface_id=None if all_styles else selected_typeface_single,
                typefaces_by_script=typefaces_by_script if all_styles else None,
                layout_mode=layout_mode,
                show_strokes=show_strokes,
                show_radicals=show_radicals,
                show_decomposition=show_decomposition,
                show_pinyin=show_pinyin,
                show_english=show_english,
                show_russian=show_russian,
                grid_type=grid_type,
                practice_rows=practice_rows,
                char_size_pt=char_size,
                all_styles=all_styles,
                compact_metadata=compact_translations,
                show_mmh_gloss=show_mmh_gloss,
            )
            st.session_state["pdf_bytes"] = pdf_bytes
            ti = text_input.strip()
            pdf_src = None
            if ti and ti == st.session_state.get("pdf_loaded_snapshot"):
                pdf_src = st.session_state.get("pdf_name_source")
            st.session_state["pdf_name"] = build_practice_hanzi_pdf_filename(
                text_input, source=pdf_src
            )
            st.success(f"PDF generated — {len(pdf_bytes) / 1024:.0f} KB, {n_pages} page(s)")
        except Exception as exc:
            st.error(f"Generation failed: {exc}")

# Download button (persists across reruns)
if "pdf_bytes" in st.session_state:
    st.download_button(
        label="Download PDF",
        data=st.session_state["pdf_bytes"],
        file_name=st.session_state.get("pdf_name", "PracticeHanzi.pdf"),
        mime="application/pdf",
        use_container_width=True,
    )
