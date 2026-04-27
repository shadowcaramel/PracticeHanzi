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
from utils.pdf_options import PdfJobOptions
from utils.pdf_preview import is_available as preview_is_available, render_first_page_png
from utils.presets import (
    list_preset_ids_sorted_by_label,
    load_preset,
    preset_label,
    sample_hsk_words,
)
from utils.pdf_naming import build_practice_hanzi_pdf_filename
from utils.segmentation import (
    character_sequence,
    extract_cjk,
    infer_layout_mode,
    phrase_segments,
)
from utils.session import (
    K_MAIN_TEXT,
    apply_pending_text,
    get_pdf_name_source_for_text,
    queue_text_and_source,
)

SCRIPT_ORDER = list(FONT_REGISTRY.keys())


@st.cache_data(show_spinner=False)
def _cached_preview(typeface_id: str, sample: str, height_px: int, theme_base: str) -> bytes:
    """Cached rasteriser; bg / fg chosen so the preview stays readable on
    both light and dark Streamlit themes (a fully transparent background
    breaks on dark themes because our fallback text is near-black)."""
    if theme_base == "dark":
        bg = (38, 39, 48)        # matches Streamlit's dark surface
        fg = (235, 235, 235)
    else:
        bg = (250, 250, 250)
        fg = (20, 20, 20)
    return render_typeface_preview_png(
        typeface_id, sample=sample, height_px=height_px, bg=bg, fg=fg
    )


def _current_theme_base() -> str:
    try:
        return (st.get_option("theme.base") or "light").lower()
    except Exception:
        return "light"


@st.cache_data(show_spinner=False)
def _cached_thumbnail(pdf_bytes: bytes) -> bytes | None:
    return render_first_page_png(pdf_bytes)


if K_MAIN_TEXT not in st.session_state:
    st.session_state[K_MAIN_TEXT] = "永"


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container { max-width: 980px; padding-top: 1.5rem; }
    h1 { font-size: 1.8rem !important; }
    .stRadio > div { flex-direction: row; gap: 0.5rem; flex-wrap: wrap; }
    div[data-testid="stExpander"] { border: 1px solid #e0e0e0; border-radius: 8px; }
    .chip-btn button { font-size: 0.9rem; padding: 0.25rem 0.9rem; }
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
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Settings")

    apply_pending_text()

    with st.expander("Content", expanded=True):
        st.text_area(
            "Chinese text",
            height=220,
            key=K_MAIN_TEXT,
            help="Type or paste characters, words, or phrases. Multiple lines or spaces between "
            "segments switch to phrase-style sheets (one page per segment). A single continuous "
            "line without spaces uses one page per character.",
        )
        st.caption(
            "Layout is chosen automatically: **spaces or line breaks** between parts → one sheet per "
            "segment; **no spaces** in a line → one sheet per character."
        )

        with st.expander("Word banks"):
            _presets = list_preset_ids_sorted_by_label()
            if _presets:
                _cat = st.selectbox(
                    "Preset category",
                    _presets,
                    index=0,
                    format_func=preset_label,
                    key="preset_cat",
                )
                if st.button("Load preset into text box", key="btn_preset_load"):
                    loaded = " ".join(load_preset(_cat))
                    queue_text_and_source(loaded, ("preset", _cat))
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
                    queue_text_and_source(joined, ("hsk", int(_hsk_lvl)))
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    with st.expander("Style", expanded=True):
        all_styles = st.checkbox(
            "All five scripts (one PDF page per script)",
            value=False,
            help="Each practice unit is repeated for 楷 / 行 / 草 / 隶 / 篆 using the typefaces you pick below.",
        )

        selected_typeface_single = None
        typefaces_by_script = None

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
            )
            try:
                _is_seal = get_typeface(selected_typeface_single)["script"] == "zhuanshu"
                _preview_sample = "永字八法" if _is_seal else "汉语很难"
                _preview_height = 140 if _is_seal else 120
                st.image(
                    _cached_preview(
                        selected_typeface_single,
                        _preview_sample,
                        _preview_height,
                        _current_theme_base(),
                    ),
                    caption=f"Preview sample: {_preview_sample}",
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

    with st.expander("Layout", expanded=False):
        grid_type = st.selectbox(
            "Grid type",
            options=["tian", "mi", "hui", "plain"],
            format_func=lambda g: {
                "tian": "田字格 (Tián)",
                "mi": "米字格 (Mǐ)",
                "hui": "回字格 (Huí)",
                "plain": "Plain square",
            }[g],
            index=0,
        )
        practice_rows = st.slider("Practice rows", min_value=1, max_value=6, value=3)
        char_size = st.slider(
            "Character display size (pt)", min_value=40, max_value=200, value=40, step=5
        )
        ghost_opacity = st.slider(
            "Ghost opacity (first row)", min_value=0.0, max_value=0.4, value=0.20, step=0.02,
            help="Tracing guide opacity on the top practice row; subsequent rows fade out.",
        )
        cover_page = st.checkbox(
            "Add cover page",
            value=False,
            help="Prepends a summary page listing every character/phrase included.",
        )
        ascii_filename = st.checkbox(
            "ASCII filename (broader compatibility)",
            value=False,
            help="Replace Chinese characters with a tone-less pinyin slug in the download filename.",
        )

    with st.expander("Extras", expanded=False):
        show_strokes = st.checkbox(
            "Show stroke order (楷书 / standard script only)",
            value=True,
            help="Uses hanzi-writer-data (Make Me a Hanzi). Diagrams are drawn only for 楷书 typefaces.",
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
            "Make Me a Hanzi dictionary.txt (downloads ~1 MB once into data/mmh/).",
        )
        compact_translations = st.checkbox(
            "Compact translations on phrase pages (single row when possible)",
            value=True,
            help="At display size ≥100 pt, places Pinyin / EN / RU in one row (three columns).",
        )
        show_mmh_gloss = st.checkbox(
            "Show MMH per-character gloss (phrase pages)",
            value=False,
            help="Short English gloss from Make Me a Hanzi per character.",
        )


text_input = st.session_state.get(K_MAIN_TEXT, "")

# ---------------------------------------------------------------------------
# Empty-state chips
# ---------------------------------------------------------------------------
if not text_input.strip():
    st.info("Enter text in the sidebar — or try one of these starter examples:")
    cc = st.columns(3)
    with cc[0]:
        if st.button("Try «你好»", key="ex_nihao", width="stretch"):
            queue_text_and_source("你好", None)
            st.rerun()
    with cc[1]:
        if st.button("Try HSK Level 1", key="ex_hsk1", width="stretch"):
            try:
                words = sample_hsk_words(1, 24, randomize=True)
                queue_text_and_source(" ".join(words), ("hsk", 1))
                st.rerun()
            except Exception as e:
                st.error(str(e))
    with cc[2]:
        if st.button("Try «画龙点睛»", key="ex_idiom", width="stretch"):
            queue_text_and_source("画龙点睛", None)
            st.rerun()
    st.stop()


layout_mode = infer_layout_mode(text_input)

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
    if cover_page:
        opts.append("Cover page")
    st.markdown(f"**Showing:** {', '.join(opts) if opts else 'Character only'}")

    st.markdown(
        f"**Layout (auto):** {'One page per phrase segment' if layout_mode == 'phrase' else 'One page per character'}"
    )
    n_pages = content_units * (len(FONT_REGISTRY) if all_styles else 1) + (1 if cover_page else 0)
    st.markdown(f"**Pages:** {n_pages}")

st.divider()

# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------
if st.button("Generate PDF", type="primary", width="stretch"):
    status = st.status("Preparing…", expanded=False)
    pbar = st.progress(0.0)

    def _progress(frac: float, msg: str) -> None:
        try:
            pbar.progress(min(1.0, max(0.0, frac)))
            status.update(label=msg)
        except Exception:
            pass

    try:
        opts = PdfJobOptions.from_kwargs(
            text=text_input,
            typeface_id=None if all_styles else selected_typeface_single,
            style_key=selected_script if not all_styles else "kaishu",
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
            ghost_opacity=ghost_opacity,
            cover_page=cover_page,
        )
        layout_warnings: list[str] = []
        pdf_bytes = generate_pdf(
            options=opts, progress=_progress, warnings_out=layout_warnings
        )
        st.session_state["pdf_bytes"] = pdf_bytes
        st.session_state["pdf_layout_warnings"] = sorted(set(layout_warnings))
        pdf_src = get_pdf_name_source_for_text(text_input)
        st.session_state["pdf_name"] = build_practice_hanzi_pdf_filename(
            text_input, source=pdf_src, ascii_only=ascii_filename
        )
        status.update(label=f"PDF generated — {len(pdf_bytes) / 1024:.0f} KB, {n_pages} page(s)", state="complete")
        pbar.empty()
    except Exception as exc:
        status.update(label=f"Generation failed: {exc}", state="error")
        st.error(f"Generation failed: {exc}")

if "pdf_bytes" in st.session_state:
    st.download_button(
        label="Download PDF",
        data=st.session_state["pdf_bytes"],
        file_name=st.session_state.get("pdf_name", "PracticeHanzi.pdf"),
        mime="application/pdf",
        width="stretch",
    )

    _layout_warnings = st.session_state.get("pdf_layout_warnings") or []
    if _layout_warnings:
        st.warning(
            "Layout squeezed — some pages fit fewer practice rows than requested:\n\n"
            + "\n".join(f"• {w}" for w in _layout_warnings[:12])
            + ("\n\n…and more." if len(_layout_warnings) > 12 else "")
        )

    # Optional thumbnail preview (requires pdf2image + poppler).
    ok, why = preview_is_available()
    if ok:
        try:
            png = _cached_thumbnail(st.session_state["pdf_bytes"])
            if png:
                st.image(png, caption="Page 1 preview", width="stretch")
        except Exception:
            pass
    else:
        st.caption(why)
