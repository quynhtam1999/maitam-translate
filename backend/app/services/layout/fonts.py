"""Chọn font tiếng Việt theo đúng kiểu chữ gốc (serif/sans × đậm × nghiêng).

Base14 của PDF (Helvetica/Times) KHÔNG có dấu tiếng Việt, nên phải nhúng font. Bộ Noto
(Sans + Serif, 4 kiểu mỗi bộ) phủ đủ dấu tiếng Việt; DejaVuSans giữ lại làm phương án dự
phòng nếu thiếu file.
"""
from __future__ import annotations

import functools
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # cho phép import module khi chưa cài PyMuPDF
    fitz = None  # type: ignore

_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
_FALLBACK = "DejaVuSans.ttf"

# (serif, bold, italic) -> tên file
#
# Nhánh serif dùng **Tinos** chứ không dùng Noto Serif: Tinos khớp *metric* với Times New
# Roman, mà tài liệu y khoa thật hầu hết đặt bằng Times (đo trên `01. tntc.pdf`: 84/95 nghìn
# ký tự là TimesLTStd). Noto Serif rộng hơn Times rất nhiều — đo được một dòng bảng 9pt dài
# 226pt ở bản gốc thành **364pt** khi đổi sang Noto Serif, tức phải co chữ ~35% chỉ vì đổi
# font, chứ không phải vì tiếng Việt dài hơn.
_FILES: dict[tuple[bool, bool, bool], str] = {
    (True, False, False): "Tinos-Regular.ttf",
    (True, True, False): "Tinos-Bold.ttf",
    (True, False, True): "Tinos-Italic.ttf",
    (True, True, True): "Tinos-BoldItalic.ttf",
    (False, False, False): "NotoSans-Regular.ttf",
    (False, True, False): "NotoSans-Bold.ttf",
    (False, False, True): "NotoSans-Italic.ttf",
    (False, True, True): "NotoSans-BoldItalic.ttf",
}


@functools.lru_cache(maxsize=None)
def get_font(serif: bool, bold: bool, italic: bool):
    """Trả về `fitz.Font` tương ứng (cache theo kiểu chữ — mở font là thao tác đắt)."""
    path = _FONT_DIR / _FILES[(serif, bold, italic)]
    if not path.exists():
        path = _FONT_DIR / _FALLBACK
    return fitz.Font(fontfile=str(path))


def font_for(style) -> "fitz.Font":
    return get_font(style.serif, style.bold, style.italic)


def font_for_text(style, text: str) -> "fitz.Font":
    """Font hợp kiểu chữ VÀ có đủ glyph cho đoạn chữ này.

    Cần thiết vì tài liệu y khoa đầy ký hiệu ngoài bảng chữ cái: `β-hCG`, `≥`, `≤`, `𝛍g`, mũi
    tên trong lưu đồ. Đo trên bộ font đang dùng: Noto Sans **thiếu `≥ ≤ → ←`**, còn Tinos có
    đủ (chỉ thiếu `𝛍` mà không font nào ở đây có). Thiếu glyph là chữ ra ô vuông rỗng, nên
    chuyển tạm sang font phủ đủ còn hơn.
    """
    primary = font_for(style)
    missing = {ch for ch in set(text) if not primary.has_glyph(ord(ch))}
    if not missing:
        return primary

    for candidate in (
        get_font(True, style.bold, style.italic),  # nhánh serif (Tinos) phủ rộng nhất
        _fallback_font(),
    ):
        if all(candidate.has_glyph(ord(ch)) for ch in missing):
            return candidate
    return primary


@functools.lru_cache(maxsize=1)
def _fallback_font():
    return fitz.Font(fontfile=str(_FONT_DIR / _FALLBACK))
