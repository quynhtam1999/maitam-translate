"""Bóc & dịch đè chữ trên PDF bằng PyMuPDF — GIỮ NGUYÊN bố cục (THAMKHAO B2).

Luồng: PDF gốc làm nền -> collect_segments() bóc khối chữ theo vị trí -> (dịch ở
translator) -> overlay_translate() xóa chữ gốc + chèn bản dịch đúng bbox, tự co cỡ chữ.

Các hàm dưới đây là STUB có chữ ký ổn định; phần thân port trực tiếp từ bản desktop.
"""
from __future__ import annotations

from dataclasses import dataclass

try:
    import fitz  # PyMuPDF
except ImportError:  # cho phép import module khi chưa cài PyMuPDF (giai đoạn scaffold)
    fitz = None  # type: ignore


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
    """Duyệt từng trang qua page.get_text('dict'), lấy khối chữ kèm bbox/size/màu/đậm.

    TODO: port logic duyệt block/line/span từ bản desktop pdf_overlay.collect_segments.
    """
    raise NotImplementedError("collect_segments chưa được triển khai (port từ bản desktop)")


class Fitter:
    """Co cỡ chữ để bản dịch tiếng Việt (thường DÀI hơn) vừa vào bbox gốc."""

    def __init__(self, min_font_size: float = 5.0):
        self.min_font_size = min_font_size

    def fit(self, page, bbox: tuple[float, float, float, float], text: str, base_font_size: float) -> float:
        """Trả về cỡ chữ lớn nhất mà insert_textbox không tràn bbox.

        TODO: vòng lặp giảm dần / tìm nhị phân cỡ chữ, thử page.insert_textbox(..., dry) đến khi vừa.
        """
        raise NotImplementedError("Fitter.fit chưa được triển khai")


def overlay_translate(doc, segments: list[TextSegment], translations: dict[str, str]):
    """Với mỗi segment: xóa chữ gốc (giữ ảnh + đường kẻ) rồi chèn bản dịch đúng bbox.

    Các bước (THAMKHAO B2 mục 4):
      page.add_redact_annot(bbox, cross_out=False)
      page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                            text=fitz.PDF_REDACT_TEXT_REMOVE)
      page.insert_textbox(bbox, translations[seg.block_id], fontsize=Fitter().fit(...))

    TODO: port đầy đủ; trả về `doc` đã chỉnh để pipeline lưu ra file.
    """
    raise NotImplementedError("overlay_translate chưa được triển khai (port từ bản desktop)")
