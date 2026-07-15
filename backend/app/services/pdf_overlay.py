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

# Khối rộng >= 72% bề ngang trang thì coi là chạy ngang cả trang (tiêu đề, hình, bảng lớn)
# và cắt mạch đọc 2 cột. Đo trên sách y khoa 2 cột (594pt): cột đơn ~266pt, khối ngang ~524pt
# — khoảng cách rất rộng nên ngưỡng này không nhạy cảm.
_SPAN_WIDTH_RATIO = 0.72
COLUMN_LEFT = 0
COLUMN_RIGHT = 1
COLUMN_SPAN = 2

# Header/footer chạy trang nhận diện bằng CHỮ LẶP LẠI, không bằng ngưỡng lề và cũng không
# bằng vị trí lặp lại. Đo trên sách thật: header nằm y0=33.0 còn thân bài bắt đầu y0≈57 —
# cách nhau 8pt nên ngưỡng lề cố định nuốt nhầm thân bài; mà chỉ xét "cùng y0 trên nhiều
# trang" cũng sai nốt, vì đỉnh thân bài đương nhiên lặp lại y0 ở mọi trang (đo được: băng
# y0≈58 trúng 10/15 trang toàn là thân bài). Thứ chỉ header mới có là CHỮ lặp lại sau khi bỏ
# số trang ('… Textbook of Assisted Reproductive Techniques'), nên băng nào chứa chữ lặp thì
# cả băng đó là header/footer.
_FURNITURE_Y_TOLERANCE = 2.0
_FURNITURE_MARGIN_RATIO = 0.15
_FURNITURE_MIN_PAGES = 3
# Không có thân bài nào chạy xuống 5% cuối trang (đo được: đáy thân bài y1=743, footer
# y1=773 trên trang cao 792) — nên footer chỉ có ở vài trang (mở chương) vẫn bắt được.
_FOOTER_MARGIN_RATIO = 0.95


@dataclass
class TextSegment:
    """Một khối chữ theo vị trí trên trang."""
    page_index: int
    bbox: tuple[float, float, float, float]
    text: str
    font_size: float
    color: int = 0
    is_bold: bool = False
    #: Cỡ chữ của phần THÂN khối (nhiều chữ nhất), khác `font_size` vốn lấy max để làm cận
    #: trên cho Fitter. Chỉ một span lớn lọt vào (ký hiệu tham chiếu, chỉ số trên) là đủ kéo
    #: `font_size` lên và làm hai mảnh của cùng một đoạn trông như khác kiểu chữ.
    dominant_font_size: float = 0.0
    block_id: str = ""  # id ổn định để chèn lại + ánh xạ cache
    page_height: float = 0.0
    column: int = COLUMN_SPAN
    #: False = dòng bảng: đứng độc lập theo ô/hàng nên không gộp được với khối kề, và còn
    #: CẮT mạch đọc (một dòng bảng chen giữa hai đoạn văn nghĩa là chúng không liền nhau).
    mergeable: bool = True
    #: True = header/footer chạy trang: không gộp, nhưng mạch đọc NHẢY QUA nó — nhờ vậy đoạn
    #: cuối trang trước nối được với đầu trang sau. Cả hai cờ chỉ ảnh hưởng việc gộp ở
    #: services/segment_merge.py; khối vẫn được dịch và chèn lại bình thường.
    is_furniture: bool = False

    def __post_init__(self):
        if self.dominant_font_size <= 0:
            self.dominant_font_size = self.font_size


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
                            page.rect.height,
                            # Dòng bảng đứng độc lập theo ô/hàng — gộp với dòng kề sẽ trộn
                            # nội dung giữa các ô.
                            mergeable=False,
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
                    page.rect.height,
                )
            )

        segments.extend(_order_page_segments(page_segments, page.rect.width))

    _mark_page_furniture(segments, doc.page_count)
    return segments


def _segment_from_lines(
    page_index: int,
    rect: "fitz.Rect",
    lines: list[dict],
    text: str,
    block_id: str,
    page_height: float,
    mergeable: bool = True,
) -> TextSegment:
    sizes: list[float] = []
    color_weights: dict[int, int] = {}
    size_weights: dict[float, int] = {}
    bold_votes = 0
    span_count = 0

    for line in lines:
        for span in line.get("spans", []):
            span_text = span.get("text", "")
            if not span_text:
                continue
            size = span.get("size", 0.0)
            sizes.append(size)
            size_weights[round(size, 1)] = size_weights.get(round(size, 1), 0) + len(span_text)
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
        dominant_font_size=(
            max(size_weights, key=size_weights.get) if size_weights else 10.0
        ),
        color=max(color_weights, key=color_weights.get) if color_weights else 0,
        is_bold=span_count > 0 and bold_votes * 2 >= span_count,
        block_id=block_id,
        page_height=page_height,
        mergeable=mergeable,
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


def _order_page_segments(page_segments: list[TextSegment], page_width: float) -> list[TextSegment]:
    """Sắp các khối theo đúng thứ tự đọc của trang 2 cột, và gắn `column` cho từng khối.

    Chia trang thành các *băng* ngăn bởi khối chạy ngang cả trang (tiêu đề mục, hình, bảng
    lớn): trong mỗi băng đọc hết cột trái rồi tới cột phải; gặp khối chạy ngang thì chốt băng
    hiện tại, xuất khối đó, rồi mở băng mới.

    Thứ tự đọc KHÔNG ảnh hưởng bố cục file ra (bản dịch luôn được chèn lại đúng bbox theo
    block_id) — nó quyết định việc gộp mảnh câu ở `services/segment_merge.py` nhận đúng đoạn
    liền trước hay không.
    """
    for seg in page_segments:
        seg.column = _classify_column(seg, page_width)

    ordered: list[TextSegment] = []
    band: list[TextSegment] = []
    for seg in sorted(page_segments, key=_position_key):
        if seg.column == COLUMN_SPAN:
            ordered.extend(_order_band(band))
            band = []
            ordered.append(seg)
        else:
            band.append(seg)
    ordered.extend(_order_band(band))
    return ordered


def _order_band(band: list[TextSegment]) -> list[TextSegment]:
    left = sorted((s for s in band if s.column == COLUMN_LEFT), key=_position_key)
    right = sorted((s for s in band if s.column == COLUMN_RIGHT), key=_position_key)
    return left + right


def _position_key(seg: TextSegment):
    return (seg.bbox[1], seg.bbox[0])


def _classify_column(seg: TextSegment, page_width: float) -> int:
    x0, _, x1, _ = seg.bbox
    if x1 - x0 >= page_width * _SPAN_WIDTH_RATIO:
        return COLUMN_SPAN
    # Phân cột theo TÂM khối, không theo việc có cắt qua tâm trang hay không: đo trên sách
    # thật, cột trái chạy tới x=302 còn cột phải bắt đầu x=294, tức hai cột đều lấn qua tâm
    # trang (297) vài pt.
    return COLUMN_LEFT if (x0 + x1) / 2 < page_width / 2 else COLUMN_RIGHT


def _mark_page_furniture(segments: list[TextSegment], page_count: int) -> None:
    """Đánh dấu header/footer chạy trang, để việc gộp mảnh câu nhảy qua chúng.

    Cần cờ này vì header đứng ngay TRƯỚC khối thân bài đầu trang trong thứ tự đọc, còn footer
    thì chen vào giữa đáy cột trái và đỉnh cột phải (nó nằm trong cột trái, dưới cùng) — cả
    hai đều cắt đứt mạch nối của một câu chảy tràn sang cột/trang kế.
    """
    for seg in segments:
        if seg.page_height > 0 and seg.bbox[3] > seg.page_height * _FOOTER_MARGIN_RATIO:
            seg.is_furniture = True

    if page_count < _FURNITURE_MIN_PAGES:
        return

    pages_per_text: dict[tuple[int, str], set[int]] = {}
    for seg in segments:
        if not _in_page_margin(seg):
            continue
        key = (_furniture_band(seg), _normalized_furniture_text(seg.text))
        pages_per_text.setdefault(key, set()).add(seg.page_index)

    furniture_bands = {
        band for (band, _), pages in pages_per_text.items() if len(pages) >= _FURNITURE_MIN_PAGES
    }
    for seg in segments:
        if _in_page_margin(seg) and _furniture_band(seg) in furniture_bands:
            seg.is_furniture = True


def _normalized_furniture_text(text: str) -> str:
    """Bỏ số trang để header hai trang đối diện quy về cùng một chuỗi."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", "", text)).strip().lower()


def _in_page_margin(seg: TextSegment) -> bool:
    if seg.page_height <= 0:
        return False
    return (
        seg.bbox[1] < seg.page_height * _FURNITURE_MARGIN_RATIO
        or seg.bbox[3] > seg.page_height * (1 - _FURNITURE_MARGIN_RATIO)
    )


def _furniture_band(seg: TextSegment) -> int:
    return round(seg.bbox[1] / _FURNITURE_Y_TOLERANCE)


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
