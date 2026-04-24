import io
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import requests

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BASE_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = BASE_DIR / "fonts"

# Legacy registry (script bucket → file). Kept for tests and script defaults.
FONT_REGISTRY = {
    "kaishu": {
        "name": "MaShanZheng",
        "label": "楷书 Kǎishū (Standard)",
        "filename": "MaShanZheng-Regular.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/mashanzheng/MaShanZheng-Regular.ttf",
    },
    "xingshu": {
        "name": "ZhiMangXing",
        "label": "行书 Xíngshū (Semi-cursive)",
        "filename": "ZhiMangXing-Regular.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/zhimangxing/ZhiMangXing-Regular.ttf",
    },
    "caoshu": {
        "name": "LiuJianMaoCao",
        "label": "草书 Cǎoshū (Cursive)",
        "filename": "LiuJianMaoCao-Regular.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/liujianmaocao/LiuJianMaoCao-Regular.ttf",
    },
    "lishu": {
        "name": "ZCOOLQingKeHuangYou",
        "label": "隶书 Lìshū (Clerical)",
        "filename": "ZCOOLQingKeHuangYou-Regular.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/zcoolqingkehuangyou/ZCOOLQingKeHuangYou-Regular.ttf",
    },
    "zhuanshu": {
        "name": "JFZSKSealScript",
        "label": "篆书 Zhuànshū (Seal)",
        "filename": "JFZSKSealScript_V3.ttf",
        "url": "https://github.com/jeffi369/JFZSKSealScript/releases/download/V3.0/JFZSKSealScript_V3.ttf",
    },
}

# Named typefaces: pick by font name / preview. ``script`` drives stroke-order visibility (hanzi-writer = 楷书 only).
TYPEFACES: list[dict] = [
    {
        "id": "kaishu_mashanzheng",
        "reportlab_name": "MaShanZheng",
        "label": "Ma Shan Zheng 马善政",
        "note": "Kaishu, high contrast strokes",
        "filename": "MaShanZheng-Regular.ttf",
        "url": FONT_REGISTRY["kaishu"]["url"],
        "script": "kaishu",
        "default_for_script": True,
    },
    {
        "id": "kaishu_zcoolxiaowei",
        "reportlab_name": "ZCOOLXiaoWei",
        "label": "ZCOOL XiaoWei 站酷小薇体",
        "note": "Kaishu, lighter weight",
        "filename": "ZCOOLXiaoWei-Regular.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/zcoolxiaowei/ZCOOLXiaoWei-Regular.ttf",
        "script": "kaishu",
        "default_for_script": False,
    },
    {
        "id": "kaishu_longcang",
        "reportlab_name": "LongCang",
        "label": "Long Cang 龙藏体",
        "note": "Kaishu with handwritten rhythm",
        "filename": "LongCang-Regular.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/longcang/LongCang-Regular.ttf",
        "script": "kaishu",
        "default_for_script": False,
    },
    {
        "id": "kaishu_zcoolkuaile",
        "reportlab_name": "ZCOOLKuaiLe",
        "label": "ZCOOL KuaiLe 站酷快乐体",
        "note": "Rounded display kaishu",
        "filename": "ZCOOLKuaiLe-Regular.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/zcoolkuaile/ZCOOLKuaiLe-Regular.ttf",
        "script": "kaishu",
        "default_for_script": False,
    },
    {
        "id": "xingshu_zhimangxing",
        "reportlab_name": "ZhiMangXing",
        "label": "Zhi Mang Xing",
        "note": "Running hand, semi-cursive",
        "filename": "ZhiMangXing-Regular.ttf",
        "url": FONT_REGISTRY["xingshu"]["url"],
        "script": "xingshu",
        "default_for_script": True,
    },
    {
        "id": "xingshu_iansui",
        "reportlab_name": "Iansui",
        "label": "Iansui 芫荽",
        "note": "Traditional Chinese pen handwriting (OFL, Google Fonts)",
        "filename": "Iansui-Regular.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/iansui/Iansui-Regular.ttf",
        "script": "xingshu",
        "default_for_script": False,
    },
    {
        "id": "caoshu_liujianmaocao",
        "reportlab_name": "LiuJianMaoCao",
        "label": "Liu Jian Mao Cao",
        "note": "Cursive script",
        "filename": "LiuJianMaoCao-Regular.ttf",
        "url": FONT_REGISTRY["caoshu"]["url"],
        "script": "caoshu",
        "default_for_script": True,
    },
    {
        "id": "caoshu_lxgwmarkergothic",
        "reportlab_name": "LXGWMarkerGothic",
        "label": "LXGW Marker Gothic",
        "note": "Marker-pen handwritten display (霞鹜 LXGW series, OFL on Google Fonts)",
        "filename": "LXGWMarkerGothic-Regular.ttf",
        "url": (
            "https://raw.githubusercontent.com/google/fonts/main/ofl/"
            "lxgwmarkergothic/LXGWMarkerGothic-Regular.ttf"
        ),
        "script": "caoshu",
        "default_for_script": False,
    },
    {
        "id": "lishu_zcoolqingke",
        "reportlab_name": "ZCOOLQingKeHuangYou",
        "label": "ZCOOL QingKe HuangYou 站酷庆科黄油体",
        "note": "Clerical / lishu display",
        "filename": "ZCOOLQingKeHuangYou-Regular.ttf",
        "url": FONT_REGISTRY["lishu"]["url"],
        "script": "lishu",
        "default_for_script": True,
    },
    {
        "id": "lishu_huninn",
        "reportlab_name": "Huninn",
        "label": "Huninn 粉圓",
        "note": "Rounded Traditional Chinese display (justfont / Google Fonts OFL)",
        "filename": "Huninn-Regular.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/huninn/Huninn-Regular.ttf",
        "script": "lishu",
        "default_for_script": False,
    },
    {
        "id": "zhuanshu_jfz_seal",
        "reportlab_name": "JFZSKSealScript",
        "label": "JFZSK Seal Script",
        "note": "Seal script (OFL release)",
        "filename": "JFZSKSealScript_V3.ttf",
        "url": FONT_REGISTRY["zhuanshu"]["url"],
        "script": "zhuanshu",
        "default_for_script": True,
    },
]

_registered: set[str] = set()
_register_lock = threading.Lock()
_TYPEFACE_BY_ID = {t["id"]: t for t in TYPEFACES}

# Full Unicode UI font (Latin with tone marks, Cyrillic, CJK for style labels).
_LABEL_FONT_NAME = "NotoSansSC"
_LABEL_FONT_FILE = "NotoSansSC[wght].ttf"
_LABEL_FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/"
    "NotoSansSC%5Bwght%5D.ttf"
)

SCRIPT_ORDER = list(FONT_REGISTRY.keys())


# Valid opening bytes of TTF / OTF / TrueType Collection files.
_TTF_MAGIC = (b"\x00\x01\x00\x00", b"OTTO", b"ttcf", b"true", b"typ1")


def _is_valid_font_file(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except Exception:
        return False
    return any(head.startswith(m) for m in _TTF_MAGIC)


def _download_font(url: str, dest: Path, timeout: int = 60) -> None:
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    if not _is_valid_font_file(dest):
        try:
            dest.unlink()
        except Exception:
            pass
        raise RuntimeError(
            f"Downloaded file is not a valid TTF/OTF: {url}"
        )


def get_typeface(typeface_id: str) -> dict:
    if typeface_id not in _TYPEFACE_BY_ID:
        raise KeyError(f"Unknown typeface id: {typeface_id}")
    return _TYPEFACE_BY_ID[typeface_id]


def list_typeface_ids() -> list[str]:
    return [t["id"] for t in TYPEFACES]


def list_typeface_ids_for_script(script: str) -> list[str]:
    """Typefaces that belong to a calligraphy script bucket (楷书 / 行书 / …)."""
    return [t["id"] for t in TYPEFACES if t["script"] == script]


def typeface_option_label(typeface_id: str) -> str:
    t = get_typeface(typeface_id)
    script_names = {
        "kaishu": "楷书",
        "xingshu": "行书",
        "caoshu": "草书",
        "lishu": "隶书",
        "zhuanshu": "篆书",
    }
    g = script_names.get(t["script"], t["script"])
    note = t.get("note") or ""
    suffix = f" — {note}" if note else ""
    return f"{g} · {t['label']}{suffix}"


def default_typeface_id_for_script(script: str) -> str:
    for t in TYPEFACES:
        if t["script"] == script and t.get("default_for_script"):
            return t["id"]
    for t in TYPEFACES:
        if t["script"] == script:
            return t["id"]
    raise KeyError(f"No typeface for script {script}")


def default_typeface_id() -> str:
    return default_typeface_id_for_script("kaishu")


def ensure_typeface(typeface_id: str) -> str:
    """Download (if needed) and register the typeface. Returns the reportlab font name."""
    info = get_typeface(typeface_id)
    font_name = info["reportlab_name"]
    if font_name in _registered:
        return font_name

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    path = FONTS_DIR / info["filename"]

    if not path.exists() or not _is_valid_font_file(path):
        _download_font(info["url"], path)

    with _register_lock:
        if font_name not in _registered:
            pdfmetrics.registerFont(TTFont(font_name, str(path)))
            _registered.add(font_name)
    return font_name


def ensure_all_typefaces_parallel(ids: Iterable[str], max_workers: int = 5) -> dict[str, str]:
    """Parallel download + sequential register (pdfmetrics is not thread-safe).

    Safe to call with already-registered ids; they just return immediately.
    Use this for cold-start all-styles runs where five different TTFs would
    otherwise be downloaded one at a time.
    """
    ids = list(ids)
    to_download: list[tuple[str, Path, str]] = []
    for tid in ids:
        info = get_typeface(tid)
        path = FONTS_DIR / info["filename"]
        if not path.exists() or not _is_valid_font_file(path):
            to_download.append((info["url"], path, tid))

    if to_download:
        FONTS_DIR.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="font-dl") as pool:
            futs = [pool.submit(_download_font, url, dest) for url, dest, _ in to_download]
            for f in as_completed(futs):
                try:
                    f.result()
                except Exception:
                    pass

    out: dict[str, str] = {}
    for tid in ids:
        out[tid] = ensure_typeface(tid)
    return out


def typeface_font_path(typeface_id: str) -> Path:
    """Path to the TTF after ensure_typeface has run."""
    info = get_typeface(typeface_id)
    return FONTS_DIR / info["filename"]


def ensure_font(style_key: str) -> str:
    """Legacy: resolve script bucket via bundled default typeface."""
    tid = default_typeface_id_for_script(style_key)
    return ensure_typeface(tid)


def ensure_all_fonts() -> dict[str, str]:
    """Ensure every script’s default typeface is available."""
    return {key: ensure_typeface(default_typeface_id_for_script(key)) for key in FONT_REGISTRY}


def get_font_path(style_key: str) -> Path:
    tid = default_typeface_id_for_script(style_key)
    return typeface_font_path(tid)


def style_keys() -> list[str]:
    return list(FONT_REGISTRY.keys())


def style_label(key: str) -> str:
    return FONT_REGISTRY[key]["label"]


def ensure_label_font() -> str:
    """Download (if needed) and register Noto Sans SC for UI text (pinyin, EN, RU, labels)."""
    if _LABEL_FONT_NAME in _registered:
        return _LABEL_FONT_NAME

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    path = FONTS_DIR / _LABEL_FONT_FILE

    if not path.exists():
        _download_font(_LABEL_FONT_URL, path, timeout=120)

    pdfmetrics.registerFont(TTFont(_LABEL_FONT_NAME, str(path)))
    _registered.add(_LABEL_FONT_NAME)
    return _LABEL_FONT_NAME


_SEAL_SAFE_SAMPLE = "永字八法"


def _font_covers_all(font, text: str) -> bool:
    """True if every glyph in *text* is rendered by *font* (no tofu)."""
    for ch in text:
        try:
            if font.getlength(ch) <= 0:
                return False
            mask = font.getmask(ch)
            if mask is None or mask.getbbox() is None:
                return False
        except Exception:
            return False
    return True


def render_typeface_preview_png(
    typeface_id: str,
    sample: str = "汉语很难",
    height_px: int = 120,
    pad: int = 12,
    scale: int = 2,
    *,
    bg: tuple[int, int, int] | None = (250, 250, 250),
    fg: tuple[int, int, int] = (20, 20, 20),
) -> bytes:
    """Raster preview for Streamlit.

    The canvas is sized from the actual text bbox (short samples are no
    longer floating in a huge image, long samples never clip). The text is
    centered on both axes. For typefaces whose font file does not cover the
    sample glyphs (common with seal-script fonts that omit simplifieds like
    ``汉`` / ``难``), we fall back to a known-good seal sample or — failing
    that — to the kaishu UI font so the preview never shows tofu squares.

    Rendering is performed at *scale*x resolution internally and downscaled
    with LANCZOS so the PNG looks crisp on high-DPI displays.
    """
    from PIL import Image, ImageDraw, ImageFont

    ensure_typeface(typeface_id)
    path = typeface_font_path(typeface_id)

    scale = max(1, int(scale))
    work_h = height_px * scale
    work_pad = pad * scale
    font_size = int(work_h * 0.72)

    try:
        font = ImageFont.truetype(str(path), size=font_size)
    except OSError:
        font = ImageFont.load_default()

    # Glyph-coverage fallback chain: requested sample -> seal-safe sample ->
    # kaishu label font with the original sample.
    text = sample
    if not _font_covers_all(font, text):
        if _font_covers_all(font, _SEAL_SAFE_SAMPLE):
            text = _SEAL_SAFE_SAMPLE
        else:
            try:
                label_path = FONTS_DIR / _LABEL_FONT_FILE
                if not label_path.exists():
                    ensure_label_font()
                font = ImageFont.truetype(str(label_path), size=font_size)
            except OSError:
                pass

    probe = Image.new("RGB", (4, 4))
    pdraw = ImageDraw.Draw(probe)
    bbox = pdraw.textbbox((0, 0), text, font=font)
    tw = max(1, bbox[2] - bbox[0])
    th = max(1, bbox[3] - bbox[1])

    img_w = tw + 2 * work_pad
    img_h = max(work_h, th) + 2 * work_pad

    if bg is None:
        img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        fill = (fg[0], fg[1], fg[2], 255)
    else:
        img = Image.new("RGB", (img_w, img_h), bg)
        fill = fg
    draw = ImageDraw.Draw(img)

    x = (img_w - tw) // 2 - bbox[0]
    y = (img_h - th) // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=fill)

    if scale > 1:
        img = img.resize((img_w // scale, img_h // scale), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
