"""Bóc & dịch đè chữ trên PDF bằng PyMuPDF — GIỮ NGUYÊN bố cục (THAMKHAO B2).

Luồng: PDF gốc làm nền -> collect_segments() bóc khối chữ theo vị trí -> (dịch ở
translator) -> overlay_translate() xóa chữ gốc + chèn bản dịch đúng bbox, tự co cỡ chữ.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # cho phép import module khi chưa cài PyMuPDF (giai đoạn scaffold)
    fitz = None  # type: ignore

# Font nhúng hỗ trợ đủ dấu tiếng Việt (Base14/Helvetica của PyMuPDF KHÔNG có dấu tiếng Việt).
_FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "DejaVuSans.ttf"
_FONT_ALIAS = "dejavu-vi"

# Bit cờ "in đậm" trong span["flags"] của PyMuPDF (xem docs TextPage flags).
_FLAG_BOLD = 1 << 4


@dataclass
class TextSegment:
    """Một khối chữ theo vị trí trên trang."""
    page_index: int
    bbox: tuple[float, float, float, float]
    text: str
    font_size: float
    color: int = 0
    is_bold: bool = False
    block_id: str = ""  # id ổn định để chèn lại + ánh xạ cache


def collect_segments(doc) -> list[TextSegment]:
    """Duyệt từng trang qua page.get_text('dict'), lấy khối chữ kèm bbox/size/màu/đậm."""
    segments: list[TextSegment] = []
    for page_index in range(doc.page_count):
        page = doc[page_index]
        page_dict = page.get_text("dict")
        for block_index, block in enumerate(page_dict.get("blocks", [])):
            if block.get("type") != 0:  # 0 = text block, 1 = image block
                continue

            lines = block.get("lines", [])
            texts: list[str] = []
            sizes: list[float] = []
            colors: list[int] = []
            bold_votes = 0
            span_count = 0

            for line in lines:
                line_text_parts = []
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    if not span_text:
                        continue
                    line_text_parts.append(span_text)
                    sizes.append(span.get("size", 0.0))
                    colors.append(span.get("color", 0))
                    span_count += 1
                    if span.get("flags", 0) & _FLAG_BOLD or "bold" in span.get("font", "").lower():
                        bold_votes += 1
                if line_text_parts:
                    texts.append("".join(line_text_parts))

            text = "\n".join(texts).strip()
            if not text:
                continue

            font_size = max(sizes) if sizes else 10.0
            color = colors[0] if colors else 0
            is_bold = span_count > 0 and bold_votes * 2 >= span_count

            segments.append(
                TextSegment(
                    page_index=page_index,
                    bbox=tuple(block.get("bbox", (0, 0, 0, 0))),
                    text=text,
                    font_size=font_size,
                    color=color,
                    is_bold=is_bold,
                    block_id=f"p{page_index}_b{block_index}",
                )
            )

    return segments


class Fitter:
    """Co cỡ chữ để bản dịch tiếng Việt (thường DÀI hơn) vừa vào bbox gốc."""

    def __init__(self, min_font_size: float = 5.0):
        self.min_font_size = min_font_size
        # Tài liệu dùng chung một document nháp để đo (dry-run), không đụng vào page thật.
        self._scratch_doc = fitz.open() if fitz is not None else None
        self._scratch_page = self._scratch_doc.new_page() if self._scratch_doc is not None else None
        if self._scratch_page is not None:
            self._scratch_page.insert_font(fontname=_FONT_ALIAS, fontfile=str(_FONT_PATH))

    def fit(self, page, bbox: tuple[float, float, float, float], text: str, base_font_size: float) -> float:
        """Trả về cỡ chữ lớn nhất mà insert_textbox không tràn bbox (dò nhị phân trên trang nháp)."""
        rect = fitz.Rect(bbox)
        if rect.is_empty or not text.strip():
            return max(base_font_size, self.min_font_size)

        page.insert_font(fontname=_FONT_ALIAS, fontfile=str(_FONT_PATH))

        lo, hi = self.min_font_size, max(base_font_size, self.min_font_size)
        best = self.min_font_size
        if self._fits(rect, text, self.min_font_size):
            best = self.min_font_size
        else:
            return self.min_font_size  # không vừa cả ở cỡ tối thiểu, đành chấp nhận tràn nhẹ

        # dò nhị phân giữa [lo, hi] tìm cỡ lớn nhất còn vừa (bước 0.5pt)
        while hi - lo > 0.5:
            mid = (lo + hi) / 2
            if self._fits(rect, text, mid):
                best = mid
                lo = mid
            else:
                hi = mid
        return round(best, 1)

    def _fits(self, rect: "fitz.Rect", text: str, font_size: float) -> bool:
        leftover = self._scratch_page.insert_textbox(
            rect, text, fontsize=font_size, fontname=_FONT_ALIAS
        )
        return leftover >= 0


def overlay_translate(doc, segments: list[TextSegment], translations: dict[str, str]):
    """Với mỗi segment: xóa chữ gốc (giữ ảnh + đường kẻ) rồi chèn bản dịch đúng bbox."""
    fitter = Fitter()

    by_page: dict[int, list[TextSegment]] = {}
    for seg in segments:
        by_page.setdefault(seg.page_index, []).append(seg)

    for page_index, page_segments in by_page.items():
        page = doc[page_index]

        for seg in page_segments:
            rect = fitz.Rect(seg.bbox)
            page.add_redact_annot(rect, cross_out=False)

        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            text=fitz.PDF_REDACT_TEXT_REMOVE,
        )

        for seg in page_segments:
            translated = translations.get(seg.block_id, seg.text)
            if not translated.strip():
                continue
            rect = fitz.Rect(seg.bbox)
            font_size = fitter.fit(page, seg.bbox, translated, seg.font_size)
            color = _int_to_rgb(seg.color)
            page.insert_textbox(
                rect,
                translated,
                fontsize=font_size,
                fontname=_FONT_ALIAS,
                color=color,
            )

    return doc


def _int_to_rgb(color: int) -> tuple[float, float, float]:
    """PyMuPDF trả màu chữ dạng số nguyên sRGB — tách thành (r, g, b) 0..1 cho insert_textbox."""
    r = ((color >> 16) & 0xFF) / 255.0
    g = ((color >> 8) & 0xFF) / 255.0
    b = (color & 0xFF) / 255.0
    return (r, g, b)
