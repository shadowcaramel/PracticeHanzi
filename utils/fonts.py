import io
import requests
from pathlib import Path

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
        "id": "xingshu_kleeone",
        "reportlab_name": "KleeOne",
        "label": "Klee One",
        "note": "Semi-cursive / school-hand style (JP; good Latin + some CJK)",
        "filename": "KleeOne-Regular.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/kleeone/KleeOne-Regular.ttf",
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
        "id": "caoshu_zenkurenaido",
        "reportlab_name": "ZenKurenaido",
        "label": "Zen Kurenaido",
        "note": "Brushy informal script (JP; display use)",
        "filename": "ZenKurenaido-Regular.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/zenkurenaido/ZenKurenaido-Regular.ttf",
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
        "id": "lishu_yuseimagic",
        "reportlab_name": "YuseiMagic",
        "label": "Yusei Magic",
        "note": "Soft brush display (JP; clerical-ish weight)",
        "filename": "YuseiMagic-Regular.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/yuseimagic/YuseiMagic-Regular.ttf",
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
_TYPEFACE_BY_ID = {t["id"]: t for t in TYPEFACES}

# Full Unicode UI font (Latin with tone marks, Cyrillic, CJK for style labels).
_LABEL_FONT_NAME = "NotoSansSC"
_LABEL_FONT_FILE = "NotoSansSC[wght].ttf"
_LABEL_FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/"
    "NotoSansSC%5Bwght%5D.ttf"
)

SCRIPT_ORDER = list(FONT_REGISTRY.keys())


def _download_font(url: str, dest: Path, timeout: int = 60) -> None:
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)


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

    if not path.exists():
        _download_font(info["url"], path)

    pdfmetrics.registerFont(TTFont(font_name, str(path)))
    _registered.add(font_name)
    return font_name


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


def render_typeface_preview_png(
    typeface_id: str,
    sample: str = "汉语很难",
    height_px: int = 56,
) -> bytes:
    """Raster preview for Streamlit (Pillow)."""
    from PIL import Image, ImageDraw, ImageFont

    ensure_typeface(typeface_id)
    path = typeface_font_path(typeface_id)
    pad = 8
    img = Image.new("RGB", (420, height_px + pad * 2), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(str(path), size=int(height_px * 0.72))
    except OSError:
        font = ImageFont.load_default()

    text = sample
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = pad
    y = pad + (height_px - th) // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=(20, 20, 20))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
