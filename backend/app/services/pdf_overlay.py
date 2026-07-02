"""Bóc & dịch đè chữ trên PDF bằng PyMuPDF — GIỮ NGUYÊN bố cục (THAMKHAO B2).

Luồng: PDF gốc làm nền -> collect_segments() bóc khối chữ theo vị trí -> (dịch ở
translator) -> overlay_translate() xóa chữ gốc + chèn bản dịch đúng bbox, tự co cỡ chữ.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

try:
    import fitz  # PyMuPDF
except ImportError:  # cho phép import module khi chưa cài PyMuPDF (giai đoạn scaffold)
    fitz = None  # type: ignore

# Font nhúng hỗ trợ đủ dấu tiếng Việt (Base14/Helvetica của PyMuPDF KHÔNG có dấu tiếng Việt).
_FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "DejaVuSans.ttf"
_FONT_ALIAS = "dejavu-vi"

# Bit cờ "in đậm" trong span["flags"] của PyMuPDF (xem docs TextPage flags).
_FLAG_BOLD = 1 << 4
_IMAGE_SKIP_OVERLAP_RATIO = 0.5
_TABLE_ROW_TOLERANCE = 2.0


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
    """Duyệt từng trang, lấy chữ thật theo bbox; không OCR/dịch nội dung nằm trong ảnh."""
    segments: list[TextSegment] = []
    for page_index in range(doc.page_count):
        page = doc[page_index]
        page_dict = page.get_text("dict")
        blocks = page_dict.get("blocks", [])
        image_rects = [
            fitz.Rect(block.get("bbox", (0, 0, 0, 0)))
            for block in blocks
            if block.get("type") == 1
        ]
        page_segments: list[TextSegment] = []

        for block_index, block in enumerate(blocks):
            if block.get("type") != 0:  # 0 = text block, 1 = image block
                continue

            lines = block.get("lines", [])
            block_rect = fitz.Rect(block.get("bbox", (0, 0, 0, 0)))
            if _overlaps_image(block_rect, image_rects):
                continue

            if _looks_like_table_block(lines):
                for line_index, line in enumerate(lines):
                    text = _clean_inline_text(_line_text(line))
                    if not _should_translate_text(text):
                        continue
                    line_rect = fitz.Rect(line.get("bbox", (0, 0, 0, 0)))
                    if _overlaps_image(line_rect, image_rects):
                        continue
                    page_segments.append(
                        _segment_from_lines(
                            page_index,
                            line_rect,
                            [line],
                            text,
                            f"p{page_index}_b{block_index}_l{line_index}",
                        )
                    )
                continue

            texts: list[str] = []
            for line in lines:
                line_text = _line_text(line)
                if line_text:
                    texts.append(line_text)

            text = _clean_block_text("\n".join(texts))
            if not _should_translate_text(text):
                continue

            page_segments.append(
                _segment_from_lines(
                    page_index,
                    block_rect,
                    lines,
                    text,
                    f"p{page_index}_b{block_index}",
                )
            )

        page_segments.sort(
            key=lambda seg: _reading_order_key(seg, page.rect.width, page.rect.height)
        )
        segments.extend(page_segments)

    return segments


def _segment_from_lines(
    page_index: int,
    rect: "fitz.Rect",
    lines: list[dict],
    text: str,
    block_id: str,
) -> TextSegment:
    sizes: list[float] = []
    color_weights: dict[int, int] = {}
    bold_votes = 0
    span_count = 0

    for line in lines:
        for span in line.get("spans", []):
            span_text = span.get("text", "")
            if not span_text:
                continue
            sizes.append(span.get("size", 0.0))
            color = span.get("color", 0)
            color_weights[color] = color_weights.get(color, 0) + len(span_text)
            span_count += 1
            if span.get("flags", 0) & _FLAG_BOLD or "bold" in span.get("font", "").lower():
                bold_votes += 1

    return TextSegment(
        page_index=page_index,
        bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
        text=text,
        font_size=max(sizes) if sizes else 10.0,
        color=max(color_weights, key=color_weights.get) if color_weights else 0,
        is_bold=span_count > 0 and bold_votes * 2 >= span_count,
        block_id=block_id,
    )


def _line_text(line: dict) -> str:
    return "".join(span.get("text", "") for span in line.get("spans", []))


def _clean_inline_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    return re.sub(r"[ \t]+", " ", text).strip()


def _clean_block_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return _clean_inline_text(text)


def _should_translate_text(text: str) -> bool:
    if not text:
        return False
    if re.fullmatch(r"\d+\s*/\s*DOI:.*", text, flags=re.IGNORECASE):
        return False
    return bool(re.search(r"[^\W\d_]", text))


def _looks_like_table_block(lines: list[dict]) -> bool:
    if len(lines) < 4:
        return False

    rows: list[list["fitz.Rect"]] = []
    for line in lines:
        rect = fitz.Rect(line.get("bbox", (0, 0, 0, 0)))
        if rect.is_empty:
            continue
        for row in rows:
            if abs(row[0].y0 - rect.y0) <= _TABLE_ROW_TOLERANCE:
                row.append(rect)
                break
        else:
            rows.append([rect])

    multi_cell_rows = sum(
        1
        for row in rows
        if len(row) >= 2 and (max(rect.x0 for rect in row) - min(rect.x0 for rect in row)) > 24
    )
    distinct_x = len({round(rect.x0 / 12) for row in rows for rect in row})
    return multi_cell_rows >= 2 or (multi_cell_rows >= 1 and distinct_x >= 3)


def _overlaps_image(rect: "fitz.Rect", image_rects: list["fitz.Rect"]) -> bool:
    if rect.is_empty:
        return False
    rect_area = rect.get_area()
    if rect_area <= 0:
        return False
    for image_rect in image_rects:
        overlap = rect & image_rect
        if not overlap.is_empty and overlap.get_area() / rect_area >= _IMAGE_SKIP_OVERLAP_RATIO:
            return True
    return False


def _reading_order_key(seg: TextSegment, page_width: float, page_height: float):
    x0, y0, x1, _ = seg.bbox
    width = x1 - x0
    center_x = (x0 + x1) / 2
    is_full_width = width >= page_width * 0.72
    if y0 < page_height * 0.22:
        column = -1
    elif y0 > page_height * 0.92:
        column = 3
    elif is_full_width:
        column = 2
    else:
        column = 0 if center_x < page_width / 2 else 1
    return (column, y0, x0)


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
