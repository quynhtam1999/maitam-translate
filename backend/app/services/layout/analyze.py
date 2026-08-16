"""Phân tích bố cục trang PDF: chữ -> dòng -> khối (đơn vị dịch) + vùng dựng bản dịch.

Thứ tự làm việc (đúng nguyên lý "nhận diện cấu trúc trước, dịch sau"):

1. Bóc **dòng** chữ thật kèm kiểu chữ (cỡ, đậm, nghiêng, có chân, màu).
2. Khoanh **vùng**: bảng (tables.py), hình/ảnh, footnote, header–footer chạy trang, caption.
3. Chia **cột & thứ tự đọc** cho phần thân bài.
4. Gom dòng thành **khối trọn vẹn**: đoạn văn, tiêu đề, gạch đầu dòng, ô bảng, nhãn hình…
   Khối là đơn vị gửi đi dịch, **không bao giờ cắt giữa câu**.
5. Nối khối chảy tràn sang cột/trang kế thành MỘT khối nhiều vùng (bản dịch sẽ được rót
   tuần tự vào các vùng đó khi dựng lại).

Hai luật khác hẳn engine cũ:
- **Không bỏ chữ nào.** Engine cũ loại mọi block đè lên ảnh (đo được: 37 block của
  `01. tntc.pdf`, gồm nguyên trang mục lục và hộp KEY POINTS) — chúng vừa không được dịch
  vừa không bị xóa, nên bản dịch mới đè lên chữ gốc còn nguyên. Nay chữ nằm trên ảnh/nền màu
  vẫn là chữ: dịch bình thường, chỉ xóa đúng phần chữ chứ không đụng vào ảnh.
- **Không cắt bản dịch theo tỉ lệ.** Khối nào dịch xong thì dựng trọn vẹn trong vùng của
  chính nó.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore

from .model import (
    ALIGN_CENTER,
    ALIGN_JUSTIFY,
    ALIGN_LEFT,
    Area,
    Block,
    BlockKind,
    FLOWING_KINDS,
    Rect,
    Style,
    TextLine,
)
from .tables import TableRegion, build_cells, find_table_regions

_FLAG_SUPERSCRIPT = 1
_FLAG_ITALIC = 1 << 1
_FLAG_SERIF = 1 << 2
_FLAG_BOLD = 1 << 4

COLUMN_LEFT = 0
COLUMN_RIGHT = 1
COLUMN_SPAN = 2

#: Dòng rộng >= ngần này bề ngang vùng chữ thì coi là chạy ngang cả trang (tiêu đề mục,
#: bảng lớn) và cắt mạch đọc 2 cột.
_SPAN_WIDTH_RATIO = 0.72
#: Chữ đè lên ảnh quá ngần này thì coi là NHÃN nằm trong hình (dịch tại chỗ, không gộp).
_FIGURE_LABEL_OVERLAP = 0.55
_MIN_FIGURE_AREA = 4000.0
#: Khung kín nhỏ (hộp lưu đồ, ô sơ đồ) chứa vài dòng chữ -> cả hộp là MỘT nhãn.
#: Đo trên lưu đồ trang 839: hộp ~74×33pt, mỗi hộp 1-3 dòng. Ngưỡng cố ý chặt để KHÔNG bắt
#: nhầm khối văn xuôi được tô nền (hộp tô nền của đoạn nổi bật cao hơn nhiều và nhiều dòng).
_MAX_BOX_WIDTH_RATIO = 0.45
_MAX_BOX_HEIGHT_RATIO = 0.15
_MAX_BOX_LINES = 3

#: Header/footer chạy trang: nhận bằng CHỮ LẶP LẠI ở lề trên/dưới, không bằng vị trí.
_FURNITURE_MARGIN_RATIO = 0.12
_FURNITURE_MIN_PAGES = 3

#: Nét kẻ mảnh, ngắn, nằm nửa dưới trang = đường phân cách footnote.
_FOOTNOTE_RULE_MIN_RATIO = 0.10
_FOOTNOTE_RULE_MAX_RATIO = 0.50
_FOOTNOTE_TOP_RATIO = 0.55

#: Khe dọc tối đa (bội cỡ chữ) giữa hai dòng cùng một đoạn.
_LINE_GAP_RATIO = 0.85
#: Dòng cuối đoạn thường ngắn hơn mép phải cột ngần này.
_SHORT_LINE_SLACK = 2.5
#: Thụt đầu dòng đủ lớn thì chắc chắn là đoạn mới.
_INDENT_MIN = 5.0
#: Tiêu đề: cỡ chữ lớn hơn thân bài ngần này lần, hoặc in đậm và ngắn.
_HEADING_SIZE_RATIO = 1.12
_HEADING_MAX_LINES = 3

_CAPTION_RE = re.compile(
    r"^\s*(figure|fig\.?|table|box|chart|plate|bảng|hình)\s*\d+([.\-–—]\d+)?", re.IGNORECASE
)
_TABLE_TITLE_RE = re.compile(r"^\s*(table|box|bảng)\s*\d", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*([•▪◦‣∙·–—*]|\d{1,2}[.)]|[a-z][.)])\s+")
_HAS_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)

#: Đáy có thể nới tới, tính theo chiều cao trang (chừa lề dưới).
_PAGE_BOTTOM_RATIO = 0.97
#: Khoảng an toàn khi mượn chỗ trống bên dưới.
_BORROW_PADDING = 2.0


@dataclass
class _PageLayout:
    index: int
    rect: Rect
    lines: list[TextLine]
    tables: list[TableRegion]
    #: (bbox, chủ sở hữu) của mọi thứ chiếm chỗ trên trang — để tính chỗ trống còn lại.
    occupied: list[tuple[Rect, str | None]] = field(default_factory=list)
    column_bounds: dict[int, tuple[float, float]] = field(default_factory=dict)
    body_size: float = 10.0
    #: id -> khung kín nhỏ chứa chữ (hộp lưu đồ).
    boxes: dict[str, Rect] = field(default_factory=dict)


def analyze_document(doc) -> list[Block]:
    """Phân tích cả tài liệu -> danh sách khối theo thứ tự đọc, sẵn sàng đem đi dịch."""
    pages = [_analyze_page(doc[index], index) for index in range(doc.page_count)]
    _mark_furniture(pages)

    body: list[Block] = []
    others: list[Block] = []
    for page in pages:
        page_body, page_others = _build_page_blocks(page)
        body.extend(page_body)
        others.extend(page_others)
    # Chỉ nối trong DÒNG CHẢY thân bài: ô bảng, nhãn hình, header/footer nằm ngoài mạch đọc
    # nên không được phép chen vào giữa hai nửa của một câu.
    return _link_flowing_blocks(body) + others


# ----------------------------------------------------------------------------- bóc dòng


def _analyze_page(page, index: int) -> _PageLayout:
    page_rect = page.rect
    raw = page.get_text("dict")
    blocks = raw.get("blocks", [])

    lines: list[TextLine] = []
    occupied: list[tuple[Rect, str | None]] = []

    figure_rects: list[Rect] = []
    for block in blocks:
        rect = tuple(block.get("bbox", (0, 0, 0, 0)))
        if block.get("type") == 1:
            occupied.append((rect, "image"))
            if _area(rect) >= _MIN_FIGURE_AREA:
                figure_rects.append(rect)
            continue
        for line in block.get("lines", []):
            text_line = _make_line(line, index)
            if text_line is not None:
                lines.append(text_line)

    for drawing in page.get_drawings():
        rect = fitz.Rect(drawing.get("rect"))
        if not rect.is_empty and not rect.is_infinite and rect.get_area() >= 12:
            occupied.append(((rect.x0, rect.y0, rect.x1, rect.y1), "drawing"))

    layout = _PageLayout(index=index, rect=tuple(page_rect), lines=lines, tables=[])
    layout.tables = find_table_regions(page, index, lines)
    layout.boxes = _closed_boxes(page, layout)

    _classify_lines(layout, figure_rects, page)
    _assign_columns(layout)
    # Cỡ chữ thân bài phải đo SAU khi phân loại: nếu tính cả ô bảng và footnote (cỡ nhỏ hơn)
    # thì trang nào nhiều bảng sẽ có "cỡ thân bài" thấp giả tạo, và mọi đoạn văn bình thường
    # bị coi là tiêu đề.
    layout.body_size = _dominant_size(
        [
            line
            for line in lines
            if line.kind in (BlockKind.PARAGRAPH, BlockKind.LIST_ITEM, BlockKind.HEADING)
        ]
        or lines
    )

    for line_index, line in enumerate(lines):
        occupied.append((line.bbox, _line_owner(index, line_index)))
    layout.occupied = occupied
    return layout


def _make_line(line: dict, page_index: int) -> TextLine | None:
    spans = [span for span in line.get("spans", []) if span.get("text")]
    if not spans:
        return None
    text = "".join(span.get("text", "") for span in spans)
    text = _clean(text)
    if not _is_translatable(text):
        return None

    # Kiểu chữ lấy theo span CHIẾM NHIỀU CHỮ NHẤT, không lấy max: chỉ một ký hiệu tham chiếu
    # hay chỉ số trên cỡ khác là đủ làm hai mảnh của cùng một đoạn trông như khác kiểu chữ.
    body = max(spans, key=lambda s: len(s.get("text", "")))
    flags = body.get("flags", 0)
    font_name = body.get("font", "").lower()
    style = Style(
        size=round(float(body.get("size", 10.0)), 1),
        bold=bool(flags & _FLAG_BOLD) or "bold" in font_name or "black" in font_name,
        italic=bool(flags & _FLAG_ITALIC) or "italic" in font_name or "oblique" in font_name,
        serif=bool(flags & _FLAG_SERIF),
        color=int(body.get("color", 0)),
    )
    return TextLine(
        page_index=page_index,
        bbox=tuple(line.get("bbox", (0, 0, 0, 0))),
        text=text,
        style=style,
    )


def _clean(text: str) -> str:
    text = text.replace("­", "").replace("ﬁ", "fi").replace("ﬂ", "fl")
    return re.sub(r"[ \t]+", " ", text).strip()


def _is_translatable(text: str) -> bool:
    """Chỉ dịch chuỗi có chữ cái. Số trang, số hàng, ký hiệu… giữ nguyên bản gốc."""
    return bool(text) and bool(_HAS_LETTER_RE.search(text))


def _dominant_size(lines: list[TextLine]) -> float:
    weights: dict[float, int] = {}
    for line in lines:
        weights[line.style.size] = weights.get(line.style.size, 0) + len(line.text)
    return max(weights, key=weights.get) if weights else 10.0


# ------------------------------------------------------------------------ phân loại dòng


def _classify_lines(layout: _PageLayout, figure_rects: list[Rect], page) -> None:
    footnote_top = _footnote_rule_y(page, layout)

    for line in layout.lines:
        region = _table_of(line, layout.tables)
        if region is not None:
            line.kind = BlockKind.TABLE_CELL
            line.table_id = region.id
            continue

        box_id = _box_of(line, layout.boxes)
        if box_id is not None:
            line.kind = BlockKind.FIGURE_LABEL
            line.box_id = box_id
            continue

        if any(_overlap_ratio(line.bbox, rect) >= _FIGURE_LABEL_OVERLAP for rect in figure_rects):
            line.kind = BlockKind.FIGURE_LABEL
            continue

        if footnote_top is not None and line.bbox[1] >= footnote_top:
            line.kind = BlockKind.FOOTNOTE
            continue

        if _TABLE_TITLE_RE.match(line.text):
            line.kind = BlockKind.TABLE_TITLE
        elif _CAPTION_RE.match(line.text):
            line.kind = BlockKind.CAPTION


def _closed_boxes(page, layout: _PageLayout) -> dict[str, Rect]:
    """Các khung kín nhỏ có chữ bên trong (hộp lưu đồ) — mỗi hộp về sau là một nhãn trọn vẹn."""
    page_width = layout.rect[2] - layout.rect[0]
    page_height = layout.rect[3] - layout.rect[1]
    boxes: dict[str, Rect] = {}
    for index, drawing in enumerate(page.get_drawings()):
        rect = fitz.Rect(drawing.get("rect"))
        if drawing.get("type") not in ("f", "fs") or rect.is_infinite:
            continue
        if rect.width > page_width * _MAX_BOX_WIDTH_RATIO or rect.width < 12:
            continue
        if rect.height > page_height * _MAX_BOX_HEIGHT_RATIO or rect.height < 8:
            continue
        if rect.x0 < -2 or rect.y0 < -2 or rect.x1 > page_width + 2 or rect.y1 > page_height + 2:
            continue
        box = (rect.x0, rect.y0, rect.x1, rect.y1)
        inside = [line for line in layout.lines if _overlap_ratio(line.bbox, box) >= 0.75]
        if 1 <= len(inside) <= _MAX_BOX_LINES:
            boxes[f"p{layout.index}_box{index}"] = box
    return boxes


def _table_of(line: TextLine, regions: list[TableRegion]) -> TableRegion | None:
    for region in regions:
        if region.contains(line.bbox):
            return region
    return None


def _box_of(line: TextLine, boxes: dict[str, Rect]) -> str | None:
    for box_id, box in boxes.items():
        if _overlap_ratio(line.bbox, box) >= 0.75:
            return box_id
    return None


def _footnote_rule_y(page, layout: _PageLayout) -> float | None:
    """Cao độ đường kẻ phân cách footnote (nét ngang ngắn ở nửa dưới trang)."""
    page_height = layout.rect[3] - layout.rect[1]
    page_width = layout.rect[2] - layout.rect[0]
    best: float | None = None
    for drawing in page.get_drawings():
        rect = fitz.Rect(drawing.get("rect"))
        if rect.is_empty or rect.height > 2.5:
            continue
        ratio = rect.width / page_width if page_width else 0
        if not _FOOTNOTE_RULE_MIN_RATIO <= ratio <= _FOOTNOTE_RULE_MAX_RATIO:
            continue
        if rect.y0 < page_height * _FOOTNOTE_TOP_RATIO:
            continue
        best = rect.y1 if best is None else min(best, rect.y1)
    return best


def _mark_furniture(pages: list[_PageLayout]) -> None:
    """Header/footer chạy trang: chữ lặp lại (sau khi bỏ số trang) ở lề trên/dưới.

    Nhận bằng CHỮ chứ không bằng vị trí: đo trên sách 2 cột thật, băng y0≈58 lặp ở 10/15
    trang nhưng toàn là thân bài — đỉnh khung chữ đương nhiên lặp y0 ở mọi trang.
    """
    if len(pages) < _FURNITURE_MIN_PAGES:
        return

    seen: dict[str, set[int]] = {}
    for page in pages:
        for line in page.lines:
            if not _in_margin(line, page):
                continue
            key = _normalized(line.text)
            if key:
                seen.setdefault(key, set()).add(page.index)

    repeated = {key for key, indexes in seen.items() if len(indexes) >= _FURNITURE_MIN_PAGES}
    for page in pages:
        for line in page.lines:
            if _in_margin(line, page) and _normalized(line.text) in repeated:
                line.kind = BlockKind.PAGE_FURNITURE


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "", text)).strip().lower()


def _in_margin(line: TextLine, page: _PageLayout) -> bool:
    height = page.rect[3] - page.rect[1]
    return (
        line.bbox[1] < height * _FURNITURE_MARGIN_RATIO
        or line.bbox[3] > height * (1 - _FURNITURE_MARGIN_RATIO)
    )


# --------------------------------------------------------------------------- cột & thứ tự


def _assign_columns(layout: _PageLayout) -> None:
    body = [line for line in layout.lines if line.kind not in (BlockKind.TABLE_CELL,)]
    if not body:
        return

    x0 = min(line.bbox[0] for line in body)
    x1 = max(line.bbox[2] for line in body)
    width = max(x1 - x0, 1.0)
    middle = (x0 + x1) / 2

    for line in layout.lines:
        if line.width >= width * _SPAN_WIDTH_RATIO:
            line.column = COLUMN_SPAN
        else:
            # Phân cột theo TÂM dòng, không theo "có cắt qua tâm trang": đo trên sách thật,
            # cột trái chạy tới x=302 còn cột phải bắt đầu x=294 — hai cột đều lấn qua tâm.
            line.column = COLUMN_LEFT if (line.bbox[0] + line.bbox[2]) / 2 < middle else COLUMN_RIGHT

    by_column: dict[int, list[TextLine]] = {}
    for line in layout.lines:
        by_column.setdefault(line.column, []).append(line)

    bounds: dict[int, tuple[float, float]] = {}
    for column, column_lines in by_column.items():
        # Ô bảng và nhãn hình có hình học riêng, không phản ánh mép cột thân bài.
        flowing = [
            line
            for line in column_lines
            if line.kind not in (BlockKind.TABLE_CELL, BlockKind.FIGURE_LABEL)
        ]
        bounds[column] = _robust_bounds(flowing or column_lines)

    # Hai cột không được lấn nhau: chốt lại mép phải cột trái theo mép trái cột phải.
    if COLUMN_LEFT in bounds and COLUMN_RIGHT in bounds:
        left = bounds[COLUMN_LEFT]
        bounds[COLUMN_LEFT] = (left[0], min(left[1], bounds[COLUMN_RIGHT][0] - 4.0))
    layout.column_bounds = bounds


def _robust_bounds(lines: list[TextLine]) -> tuple[float, float]:
    """Mép trái/phải của cột, bỏ qua dòng cá biệt.

    Không dùng min/max thô: chỉ một caption hay nhãn hình lệch chuẩn là đủ kéo mép cột lấn
    sang cột bên cạnh (đo được: mép phải cột trái trang 831 bị kéo từ 289 ra 328, khiến tiêu
    đề bảng viết đè lên cột phải). Lấy các mốc x LẶP LẠI ở nhiều dòng mới là mép cột thật.
    """
    x0_values = [line.bbox[0] for line in lines]
    x1_values = [line.bbox[2] for line in lines]
    threshold = max(2, round(len(lines) * 0.15))
    return (
        _repeated_edge(x0_values, threshold, prefer_min=True),
        _repeated_edge(x1_values, threshold, prefer_min=False),
    )


def _repeated_edge(values: list[float], threshold: int, prefer_min: bool) -> float:
    clusters: list[list[float]] = []
    for value in sorted(values):
        if clusters and value - clusters[-1][0] <= 3.0:
            clusters[-1].append(value)
        else:
            clusters.append([value])

    common = [cluster for cluster in clusters if len(cluster) >= threshold]
    if not common:
        return min(values) if prefer_min else max(values)
    return min(c[0] for c in common) if prefer_min else max(c[-1] for c in common)


def _reading_order(lines: list[TextLine]) -> list[TextLine]:
    """Thứ tự đọc trang nhiều cột: khối chạy ngang cắt băng, trong băng đọc trái rồi phải."""
    ordered: list[TextLine] = []
    band: list[TextLine] = []
    for line in sorted(lines, key=lambda ln: (round(ln.bbox[1], 1), ln.bbox[0])):
        if line.column == COLUMN_SPAN:
            ordered.extend(_order_band(band))
            band = []
            ordered.append(line)
        else:
            band.append(line)
    ordered.extend(_order_band(band))
    return ordered


def _order_band(band: list[TextLine]) -> list[TextLine]:
    key = lambda ln: (round(ln.bbox[1], 1), ln.bbox[0])  # noqa: E731
    return sorted([ln for ln in band if ln.column == COLUMN_LEFT], key=key) + sorted(
        [ln for ln in band if ln.column == COLUMN_RIGHT], key=key
    )


# ------------------------------------------------------------------------------- gom khối


def _build_page_blocks(page: _PageLayout) -> tuple[list[Block], list[Block]]:
    """Trả về (khối thân bài theo thứ tự đọc, khối đứng riêng: ô bảng + nhãn hình)."""
    body_lines = [
        line
        for line in page.lines
        if line.kind not in (BlockKind.TABLE_CELL, BlockKind.FIGURE_LABEL)
    ]
    body = [_make_block(group, page) for group in _group_lines(_reading_order(body_lines), page)]

    others: list[Block] = []
    for region in page.tables:
        region_lines = [line for line in page.lines if line.table_id == region.id]
        for index, cell in enumerate(build_cells(region, region_lines)):
            others.append(_make_cell_block(region, index, cell, page))

    # Nhãn trong hình. Chữ trong cùng một hộp lưu đồ là MỘT nhãn (dịch trọn cụm, dựng lại
    # vừa trong hộp); nhãn rời trên nền hình thì mỗi dòng một khối, được nở ngang.
    boxed: dict[str, list[TextLine]] = {}
    for line in page.lines:
        if line.kind != BlockKind.FIGURE_LABEL:
            continue
        if line.box_id:
            boxed.setdefault(line.box_id, []).append(line)
        else:
            others.append(_widen_label(_make_block([line], page), line, page))

    for box_id, box_lines in boxed.items():
        others.append(_make_boxed_label(box_id, page.boxes[box_id], box_lines, page))

    return body, others


def _group_lines(lines: list[TextLine], page: _PageLayout) -> list[list[TextLine]]:
    """Gom dòng liền mạch thành đoạn; cắt đúng chỗ đoạn văn thật sự kết thúc."""
    groups: list[list[TextLine]] = []
    current: list[TextLine] = []

    for line in lines:
        if current and _breaks(current[-1], line, page):
            groups.append(current)
            current = []
        current.append(line)
    if current:
        groups.append(current)
    return groups


def _breaks(prev: TextLine, nxt: TextLine, page: _PageLayout) -> bool:
    if prev.kind != nxt.kind:
        return True
    if prev.kind in (BlockKind.PAGE_FURNITURE, BlockKind.FIGURE_LABEL):
        return True
    if prev.page_index != nxt.page_index or prev.column != nxt.column:
        return True
    if not _style_compatible(prev.style, nxt.style):
        return True
    if _BULLET_RE.match(nxt.text):
        return True

    gap = nxt.bbox[1] - prev.bbox[3]
    if gap > _LINE_GAP_RATIO * max(prev.style.size, 1.0):
        return True
    if gap < -prev.style.size:  # dòng chồng lên nhau: không phải mạch đọc bình thường
        return True

    if _ends_sentence(prev.text):
        # Đoạn mới khi có bằng chứng hình học: dòng trước ngắn (chưa chạm mép phải cột)
        # hoặc dòng sau thụt vào. Không có bằng chứng thì vẫn là cùng đoạn nhiều câu.
        _, column_right = page.column_bounds.get(prev.column, (prev.bbox[0], prev.bbox[2]))
        column_left, _ = page.column_bounds.get(nxt.column, (nxt.bbox[0], nxt.bbox[2]))
        if prev.bbox[2] < column_right - _SHORT_LINE_SLACK:
            return True
        if nxt.bbox[0] > column_left + _INDENT_MIN:
            return True
    return False


def _style_compatible(left: Style, right: Style) -> bool:
    """Hai dòng có cùng "mạch chữ" không?

    Chỉ so CỠ và MÀU, cố tình bỏ qua đậm/nghiêng: sách y khoa hay mở đầu đoạn bằng một cụm
    in đậm rồi chạy tiếp bằng chữ thường trong cùng một câu. Nếu coi đổi đậm là hết đoạn thì
    đoạn bị cắt ngay giữa từ ('…may be insti-' / 'tuted. There are many ways…') — đúng cái
    lỗi mà engine này sinh ra để chấm dứt.
    """
    return abs(left.size - right.size) <= 0.6 and left.color == right.color


def _dominant_style(lines: list[TextLine]) -> Style:
    """Kiểu chữ đại diện cho cả khối: kiểu của phần chữ CHIẾM NHIỀU NHẤT."""
    weights: dict[Style, int] = {}
    for line in lines:
        weights[line.style] = weights.get(line.style, 0) + len(line.text)
    return max(weights, key=weights.get)


def _ends_sentence(text: str) -> bool:
    trimmed = text.rstrip().rstrip("\"'”’)]}»›").rstrip()
    return bool(trimmed) and trimmed[-1] in ".!?"


def _make_block(lines: list[TextLine], page: _PageLayout) -> Block:
    first = lines[0]
    kind = _refine_kind(lines, page)
    column_left, column_right = page.column_bounds.get(
        first.column, (first.bbox[0], first.bbox[2])
    )
    x0 = min(line.bbox[0] for line in lines)
    x1 = max(column_right, max(line.bbox[2] for line in lines))
    if kind in (BlockKind.PARAGRAPH, BlockKind.LIST_ITEM, BlockKind.FOOTNOTE):
        x0 = min(x0, column_left)

    line_height = _line_height(lines)
    ink = (x0, min(l.bbox[1] for l in lines) - 1.0, x1, max(l.bbox[3] for l in lines) + 1.0)
    own = {line.bbox for line in lines}
    left_limit, right_limit = _horizontal_room(own, page)
    ink = (
        min(max(ink[0], left_limit), min(l.bbox[0] for l in lines)),
        ink[1],
        max(min(ink[2], right_limit), max(l.bbox[2] for l in lines)),
        ink[3],
    )
    free_bottom = _free_bottom(ink, lines, page)
    area = Area(
        page_index=first.page_index,
        rect=_flow_rect(
            ink,
            len(lines),
            lines[0].style.size,
            line_height,
            _free_top(ink, lines, page),
            free_bottom,
        ),
        max_bottom=free_bottom,
        page_height=page.rect[3] - page.rect[1],
    )
    return Block(
        id=_block_id(first.page_index, lines),
        kind=kind,
        text=_join_lines(lines),
        style=_dominant_style(lines),
        areas=[area],
        line_rects=[(line.page_index, line.bbox) for line in lines],
        align=_alignment(lines, kind, column_left, column_right),
        line_count=len(lines),
        line_height=_line_height(lines),
    )


def _flow_rect(
    ink: Rect,
    line_count: int,
    size: float,
    line_height: float,
    free_top: float,
    free_bottom: float,
) -> Rect:
    """Hộp chữ thật sự, không phải hộp mực.

    bbox của n dòng chỉ cao `(n-1)×pitch + chiều cao nét chữ`, hụt gần đúng một khoảng dẫn
    dòng (leading) so với `n×pitch`. Rót lại vào đúng hộp mực thì dòng cuối không bao giờ đủ
    chỗ, và khối phải co chữ oan — đo được 159/560 khối bị co dưới 0.85 chỉ vì thiếu vài pt.

    Nới đều lên trên và xuống dưới nửa khoảng leading (phần trắng vốn có giữa các dòng), luôn
    chặn ở chỗ trống thật nên không đụng dòng/ảnh/hàng bảng nào.
    """
    pitch = max(line_height, 1.0) * max(size, 1.0)
    ink_height = (ink[3] - ink[1]) / max(line_count, 1)
    half_lead = max(0.0, pitch - ink_height) / 2

    top = max(ink[1] - half_lead, free_top)
    bottom = min(max(ink[3] + half_lead, top + line_count * pitch), max(free_bottom, ink[3]))
    return (ink[0], top, ink[2], bottom)


def _make_cell_block(region: TableRegion, index: int, cell, page: _PageLayout) -> Block:
    lines = cell.lines
    line_height = _line_height(lines)
    ink = (cell.rect[0], cell.rect[1] - 1.0, cell.rect[2], cell.rect[3] + 1.0)
    free_bottom = _cell_bottom(ink, region, lines, page)
    rect = _flow_rect(
        ink,
        len(lines),
        lines[0].style.size,
        line_height,
        _free_top(ink, lines, page),
        free_bottom,
    )
    return Block(
        id=f"{region.id}_c{index}",
        kind=BlockKind.TABLE_CELL,
        text=_join_lines(lines),
        style=_dominant_style(lines),
        areas=[
            Area(
                page_index=region.page_index,
                rect=rect,
                # Ô bảng chỉ được nới tới ranh giới hàng kế tiếp, không bao giờ đè hàng dưới.
                max_bottom=free_bottom,
                page_height=page.rect[3] - page.rect[1],
            )
        ],
        line_rects=[(line.page_index, line.bbox) for line in lines],
        align=ALIGN_LEFT,
        line_count=len(lines),
        line_height=line_height,
    )


def _make_boxed_label(box_id: str, box: Rect, lines: list[TextLine], page: _PageLayout) -> Block:
    """Cả hộp lưu đồ là một khối: chữ được rót lại vừa trong hộp, canh giữa như bản gốc."""
    lines = sorted(lines, key=lambda ln: (ln.bbox[1], ln.bbox[0]))
    rect = (box[0] + 1.5, box[1] + 1.0, box[2] - 1.5, box[3] - 1.0)

    # Canh lề theo đúng bản gốc. Không mặc định canh giữa: trang mở chương có các mục lục
    # nằm trong khung nền rộng nhưng chữ canh TRÁI — canh giữa hết thì cả cột trôi sang phải
    # và đè lên cột bên cạnh (đo được trên trang 830).
    left_gap = min(line.bbox[0] for line in lines) - box[0]
    right_gap = box[2] - max(line.bbox[2] for line in lines)
    centered = abs(left_gap - right_gap) <= 4.0
    if not centered:
        rect = (min(line.bbox[0] for line in lines) - 1.0, rect[1], rect[2], rect[3])

    return Block(
        id=box_id,
        kind=BlockKind.FIGURE_LABEL,
        text=_join_lines(lines),
        style=_dominant_style(lines),
        areas=[
            Area(
                page_index=page.index,
                rect=rect,
                max_bottom=rect[3],
                page_height=page.rect[3] - page.rect[1],
            )
        ],
        line_rects=[(line.page_index, line.bbox) for line in lines],
        align=ALIGN_CENTER if centered else ALIGN_LEFT,
        line_count=len(lines),
        line_height=_line_height(lines),
    )


def _widen_label(block: Block, line: TextLine, page: _PageLayout) -> Block:
    """Cho nhãn trong hình nở ngang ra chỗ trống hai bên thay vì co chữ.

    Nhãn hình là chuỗi ngắn nằm trong hộp vừa khít bề ngang chữ gốc ('Cervical <1%'), không
    xuống dòng được — bản dịch dài hơn một chút là phải co tới 0.67 lần. Nhưng quanh nhãn
    thường là nền hình trống. Chỉ tránh các dòng CHỮ khác; ảnh và nét vẽ không tính là vật
    cản vì nhãn vốn nằm đè lên hình.
    """
    area = block.areas[0]
    x0, y0, x1, y1 = area.rect
    _left_limit, right_limit = _horizontal_room({line.bbox}, page)
    # Chỉ nở sang PHẢI và giữ nguyên mép trái: nhãn không được xê dịch. Nở đều hai bên rồi
    # canh giữa sẽ làm cả cột mục lục trang mở chương trôi khỏi vị trí gốc.
    widened = (x0, y0, max(min(x1 + (x1 - x0) * 0.6, right_limit), x1), y1)
    block.areas[0] = Area(
        page_index=area.page_index,
        rect=widened,
        max_bottom=area.max_bottom,
        page_height=area.page_height,
    )
    return block


def _horizontal_room(own: set, page: _PageLayout) -> tuple[float, float]:
    """Mép trái/phải mà một khối được phép chiếm, chặn bởi các dòng chữ khác cùng tầm cao.

    Áp cho MỌI khối, không riêng nhãn hình: đây là lưới an toàn không phụ thuộc việc chia cột
    có đúng hay không. Trang mở chương có **3 cột** mục lục, mô hình 2 cột chia sai, và nếu
    chỉ tin `column_bounds` thì cột này viết đè lên cột kia (đo được trên trang 830).

    Mốc so sánh là bề ngang CHỮ GỐC của khối, không phải hộp ứng viên: nếu so với hộp (vốn đã
    được nới rộng ra tới mép cột) thì khối bên cạnh nằm lọt trong hộp và bị bỏ qua, đúng lúc
    cần chặn nhất.
    """
    anchor_x0 = min(box[0] for box in own)
    anchor_x1 = max(box[2] for box in own)
    top = min(box[1] for box in own)
    bottom = max(box[3] for box in own)

    left = 0.0
    right = page.rect[2] - page.rect[0]
    for other, owner in page.occupied:
        if owner is None or not owner.startswith("line") or other in own:
            continue
        if other[3] <= top or other[1] >= bottom:  # không cùng tầm cao
            continue
        if other[2] <= anchor_x0:
            left = max(left, other[2] + 3.0)
        elif other[0] >= anchor_x1:
            right = min(right, other[0] - 3.0)
    return left, right


def _refine_kind(lines: list[TextLine], page: _PageLayout) -> BlockKind:
    kind = lines[0].kind
    if kind != BlockKind.PARAGRAPH:
        return kind
    if _BULLET_RE.match(lines[0].text):
        return BlockKind.LIST_ITEM
    style = lines[0].style
    looks_big = style.size >= page.body_size * _HEADING_SIZE_RATIO
    looks_bold = style.bold and len(lines) <= _HEADING_MAX_LINES
    if (looks_big or looks_bold) and len(lines) <= _HEADING_MAX_LINES:
        if not _ends_sentence(lines[-1].text) or looks_big:
            return BlockKind.HEADING
    return BlockKind.PARAGRAPH


def _join_lines(lines: list[TextLine]) -> str:
    text = lines[0].text
    for line in lines[1:]:
        # 'inher-' + 'ited' -> 'inherited' (gạch nối cuối dòng do dàn chữ, không phải dấu thật)
        if re.search(r"\w-$", text) and line.text[:1].islower():
            text = text[:-1] + line.text
        else:
            text = f"{text} {line.text}"
    return text


def _block_id(page_index: int, lines: list[TextLine]) -> str:
    first = lines[0]
    return f"p{page_index}_x{round(first.bbox[0])}_y{round(first.bbox[1])}_n{len(lines)}"


def _line_owner(page_index: int, line_index: int) -> str:
    return f"line:{page_index}:{line_index}"


def _line_height(lines: list[TextLine]) -> float:
    if len(lines) < 2:
        return 1.15
    pitch = (lines[-1].bbox[1] - lines[0].bbox[1]) / (len(lines) - 1)
    size = max(lines[0].style.size, 1.0)
    return min(max(pitch / size, 0.95), 2.0)


def _alignment(lines: list[TextLine], kind: BlockKind, left: float, right: float) -> int:
    if kind in (BlockKind.TABLE_CELL, BlockKind.FIGURE_LABEL):
        return ALIGN_LEFT

    if len(lines) >= 2:
        body = lines[:-1]
        flush_right = max(abs(right - line.bbox[2]) for line in body) <= _SHORT_LINE_SLACK
        flush_left = max(abs(line.bbox[0] - left) for line in lines[1:]) <= _SHORT_LINE_SLACK
        if flush_right and flush_left and kind in FLOWING_KINDS:
            return ALIGN_JUSTIFY

    centered = all(
        abs(((line.bbox[0] + line.bbox[2]) / 2) - (left + right) / 2) <= 3.0
        and line.bbox[0] - left > 8.0
        for line in lines
    )
    return ALIGN_CENTER if centered else ALIGN_LEFT


# --------------------------------------------------------------------------- chỗ trống


def _free_bottom(rect: Rect, lines: list[TextLine], page: _PageLayout) -> float:
    """Đáy mà vùng được phép nới xuống: chạm thứ gần nhất bên dưới trong cùng khoảng x."""
    own = {line.bbox for line in lines}
    limit = (page.rect[3] - page.rect[1]) * _PAGE_BOTTOM_RATIO
    for other, _owner in page.occupied:
        if other in own or other[1] < rect[3] - 1.0:
            continue
        if _horizontal_share(rect, other) < 0.15:
            continue
        limit = min(limit, other[1] - _BORROW_PADDING)
    return max(limit, rect[3])


def _free_top(rect: Rect, lines: list[TextLine], page: _PageLayout) -> float:
    """Trần mà vùng được phép nới lên (đối xứng với `_free_bottom`)."""
    own = {line.bbox for line in lines}
    limit = 0.0
    for other, _owner in page.occupied:
        if other in own or other[3] > rect[1] + 1.0:
            continue
        if _horizontal_share(rect, other) < 0.15:
            continue
        limit = max(limit, other[3] + _BORROW_PADDING)
    return min(limit, rect[1])


def _cell_bottom(rect: Rect, region: TableRegion, lines: list[TextLine], page: _PageLayout) -> float:
    limit = _free_bottom(rect, lines, page)
    below = [y for y in region.row_rules if y > rect[3] + 0.5]
    if below:
        limit = min(limit, min(below) - 1.0)
    return max(min(limit, region.rect[3]), rect[3])


def _horizontal_share(rect: Rect, other: Rect) -> float:
    """Mức chồng lấn ngang, tính theo bên HẸP hơn.

    Phải theo bên hẹp: mẩu chữ ngắn ('e120.' rộng 18pt) nằm ngay dưới một đoạn rộng 500pt
    chỉ chiếm 3% bề ngang đoạn — tính theo bên rộng thì nó không chặn, và đoạn ở trên sẽ
    mượn chỗ đè lên nó.
    """
    width = min(rect[2], other[2]) - max(rect[0], other[0])
    narrow = min(rect[2] - rect[0], other[2] - other[0])
    return width / narrow if narrow > 0 else 0.0


def _overlap_ratio(inner: Rect, outer: Rect) -> float:
    width = min(inner[2], outer[2]) - max(inner[0], outer[0])
    height = min(inner[3], outer[3]) - max(inner[1], outer[1])
    if width <= 0 or height <= 0:
        return 0.0
    area = _area(inner)
    return (width * height) / area if area > 0 else 0.0


def _area(rect: Rect) -> float:
    return max(rect[2] - rect[0], 0) * max(rect[3] - rect[1], 0)


# ------------------------------------------------------------ nối khối tràn cột/tràn trang


def _link_flowing_blocks(blocks: list[Block]) -> list[Block]:
    """Nối đoạn bị cắt ở biên cột/trang thành MỘT khối nhiều vùng.

    Đây là chỗ engine mới khác engine cũ về bản chất: khối nối vẫn là một đơn vị dịch trọn
    câu, nhưng khi dựng lại bản dịch được **rót tuần tự** vào từng vùng (đầy vùng 1 mới sang
    vùng 2) chứ không cắt theo tỉ lệ ký tự — nên không bao giờ có chuyện chữ của đoạn này
    rơi vào ô bảng hay caption của đoạn khác.

    Luật cố ý CHẶT: nối sai là trộn hai nội dung không liên quan, hại hơn cái nó sửa.
    """
    result: list[Block] = []
    #: Khối văn xuôi đang bỏ ngỏ giữa câu — có thể nằm cách khối nối tiếp vài khối "đứng
    #: ngoài mạch" (tiêu đề bảng, caption, header chạy trang). Đo trên `01. tntc.pdf`: đoạn
    #: cuối trang 830 nối sang cột phải trang 831, mà đầu trang 831 lại là tiêu đề bảng 32-1.
    pending: Block | None = None
    for block in blocks:
        if pending is not None and _continues(pending, block):
            pending.text = _join_text(pending.text, block.text)
            pending.areas.extend(block.areas)
            pending.line_rects.extend(block.line_rects)
            pending.line_count += block.line_count
            continue

        result.append(block)
        # Chỉ khối VĂN XUÔI mới cắt mạch. Tiêu đề mục, tiêu đề bảng, caption, header chạy
        # trang, nhãn hình đứng ngoài dòng chảy, nên câu bỏ ngỏ vẫn nối được xuyên qua chúng
        # (đo trên `01. tntc.pdf`: đoạn cuối trang 830 nối sang cột phải trang 831, mà đầu
        # trang 831 lại là tiêu đề của bảng 32-1).
        if block.kind in FLOWING_KINDS:
            pending = block
    return result


def _continues(prev: Block, nxt: Block) -> bool:
    if prev.kind not in FLOWING_KINDS or nxt.kind != prev.kind:
        return False
    if not _style_compatible(prev.style, nxt.style):
        return False
    if _ends_sentence(prev.text) or not nxt.text[:1].islower():
        return False
    prev_area = prev.areas[-1]
    next_area = nxt.areas[0]
    # Đoạn chỉ tràn sang cột/trang kế khi nó đã CHẠM ĐÁY cột. Đo trên sách 2 cột thật: ca
    # nối cột đúng có đáy y1=730/792 (92%), còn ca gộp nhầm (caption ở đỉnh cột trái, cạnh
    # thân bài cột phải) có y1=72/792 — ngưỡng 75% tách sạch hai ca này.
    if not _at_column_tail(prev_area):
        return False
    if next_area.page_index == prev_area.page_index:
        return next_area.rect[0] > prev_area.rect[2] - 1.0  # sang cột bên phải
    return next_area.page_index == prev_area.page_index + 1 and _at_column_head(next_area)


def _at_column_tail(area: Area) -> bool:
    return area.page_height > 0 and area.rect[3] >= area.page_height * 0.75


def _at_column_head(area: Area) -> bool:
    return area.page_height > 0 and area.rect[1] <= area.page_height * 0.25


def _join_text(left: str, right: str) -> str:
    if re.search(r"\w-$", left) and right[:1].islower():
        return left[:-1] + right
    return f"{left} {right}"
