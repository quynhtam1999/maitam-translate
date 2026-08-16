"""Mô hình bố cục trang: dòng chữ -> khối (đơn vị dịch) -> vùng để rót bản dịch.

Nguyên lý (thay cho engine cũ): nhận diện CẤU TRÚC trước (bảng / hình / chữ), rồi mới dịch,
và **đơn vị dịch luôn là một khối trọn vẹn** — không bao giờ cắt giữa câu, không bao giờ
"cắt bản dịch theo tỉ lệ ký tự" rải sang các bbox khác (đó chính là thứ đã phá nát bảng và
đẩy footnote đè lên hình ở engine cũ).

Một khối có thể có NHIỀU `Area` khi đoạn văn chảy tràn sang cột/trang kế. Bản dịch được
**rót tuần tự** vào các vùng đó (đầy vùng 1 thì tràn sang vùng 2), chứ không chia theo tỉ lệ.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

Rect = tuple[float, float, float, float]


class BlockKind(str, Enum):
    """Loại khối — quyết định cách gộp, cách canh lề và có được mượn chỗ trống hay không."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST_ITEM = "list_item"
    CAPTION = "caption"
    TABLE_TITLE = "table_title"
    TABLE_CELL = "table_cell"
    FOOTNOTE = "footnote"
    FIGURE_LABEL = "figure_label"
    PAGE_FURNITURE = "page_furniture"


#: Khối được phép nối tiếp sang cột/trang kế (văn xuôi mới chảy tràn; ô bảng, nhãn hình,
#: caption thì không bao giờ).
FLOWING_KINDS = frozenset({BlockKind.PARAGRAPH, BlockKind.LIST_ITEM, BlockKind.FOOTNOTE})

#: Khối được phép mượn khoảng trắng ngay bên dưới khi bản dịch dài hơn bản gốc.
BORROWING_KINDS = frozenset(
    {
        BlockKind.PARAGRAPH,
        BlockKind.LIST_ITEM,
        BlockKind.CAPTION,
        BlockKind.HEADING,
        BlockKind.TABLE_TITLE,
        BlockKind.TABLE_CELL,
        BlockKind.FOOTNOTE,
    }
)

ALIGN_LEFT = 0
ALIGN_CENTER = 1
ALIGN_RIGHT = 2
ALIGN_JUSTIFY = 3


@dataclass(frozen=True)
class Style:
    """Kiểu chữ của một dòng/khối — dùng để chọn font Việt tương ứng và để chặn gộp nhầm."""

    size: float
    bold: bool = False
    italic: bool = False
    serif: bool = True
    color: int = 0

    def matches(self, other: "Style", size_tolerance: float = 0.6) -> bool:
        return (
            abs(self.size - other.size) <= size_tolerance
            and self.bold == other.bold
            and self.italic == other.italic
            and self.serif == other.serif
            and self.color == other.color
        )


@dataclass
class TextLine:
    """Một dòng chữ thật trên trang (đơn vị nhỏ nhất mà PDF cho biết vị trí chính xác)."""

    page_index: int
    bbox: Rect
    text: str
    style: Style
    kind: BlockKind = BlockKind.PARAGRAPH
    column: int = 0
    #: id vùng bảng chứa dòng này (None nếu không nằm trong bảng).
    table_id: str | None = None
    #: id khung kín (hộp lưu đồ, ô chú thích) chứa dòng này — cả hộp là MỘT nhãn.
    box_id: str | None = None

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]


@dataclass
class Area:
    """Một vùng chữ nhật để rót bản dịch vào.

    `max_bottom` là đáy mà vùng được phép nới xuống khi bản dịch tiếng Việt dài hơn — tính
    bằng chỗ trống thật bên dưới trong cùng cột (không đụng dòng/ảnh/nét vẽ nào khác).
    """

    page_index: int
    rect: Rect
    max_bottom: float
    page_height: float = 0.0

    def extended(self) -> Rect:
        x0, y0, x1, y1 = self.rect
        return (x0, y0, x1, max(y1, self.max_bottom))


@dataclass
class Block:
    """Một ĐƠN VỊ DỊCH trọn vẹn + nơi để dựng lại bản dịch."""

    id: str
    kind: BlockKind
    text: str
    style: Style
    areas: list[Area]
    #: bbox từng dòng gốc, theo trang — dùng để xóa chữ gốc đúng chỗ (không xóa cả khối,
    #: nhờ vậy nền màu/khung bảng/ảnh giữ nguyên).
    line_rects: list[tuple[int, Rect]] = field(default_factory=list)
    align: int = ALIGN_LEFT
    line_count: int = 1
    #: Giãn dòng gốc (pitch / cỡ chữ) — giữ lại để bản dịch có mật độ dòng như bản gốc.
    line_height: float = 1.15

    @property
    def page_index(self) -> int:
        return self.areas[0].page_index if self.areas else 0
