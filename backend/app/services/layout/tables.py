"""Nhận diện vùng BẢNG và chia thành Ô — để mỗi ô là một đơn vị dịch độc lập.

Vì sao phải làm riêng: engine cũ đoán bảng bằng heuristic "một block PyMuPDF có >= 4 dòng
xếp thành cột". Đo trên `01. tntc.pdf`: **0 bảng nào được nhận diện**, vì sách này cho mỗi
hàng bảng thành một block riêng. Hậu quả là hàng bảng bị coi là văn xuôi, bị gộp vào đoạn
văn bên cạnh, rồi bản dịch bị rải sang các ô khác -> bảng trắng trơn.

Cách mới dựa trên thứ mà bảng THẬT SỰ để lại trong file, đo trên chính tài liệu này:
- **Nền tô của bảng**: hình chữ nhật được tô nằm gọn trong trang, đủ rộng/cao và chứa >= 2
  dòng chữ (bảng 32-1 = fill `[47, 93, 287, 290]`).
- **Nét kẻ ngang lặp lại**: >= 3 nét ngang cùng khoảng x, cách đều nhau theo chiều dọc.
- **`page.find_tables(strategy="lines_strict")`** cho bảng có khung kẻ thật (trang 3 của
  tài liệu này). Chiến lược `"text"` bị loại vì đo được nó coi NGUYÊN TRANG là một bảng
  59×10 ô — vô dụng và nguy hiểm.

Chia ô: gom theo CỘT (cụm x0) trước, rồi trong mỗi cột gom dòng liền nhau thành ô, cắt ở
nét kẻ ngang hoặc khi khe dọc quá lớn. Nhờ vậy ô nhiều dòng vẫn là MỘT đơn vị dịch trọn
câu, còn hai ô khác nhau thì không bao giờ dính vào nhau.
"""
from __future__ import annotations

from dataclasses import dataclass, field

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore

from .model import Rect, TextLine

#: Nền tô phải chiếm ít nhất ngần này bề ngang vùng chữ mới coi là nền bảng.
_MIN_FILL_WIDTH_RATIO = 0.22
_MIN_FILL_HEIGHT = 22.0
#: Hình tô tràn ra ngoài mép trang là trang trí (măng-sét, góc trang), không phải bảng.
_PAGE_BLEED_TOLERANCE = 2.0
#: Nét được coi là "ngang" khi mỏng hơn ngần này.
_RULE_THICKNESS = 2.5
_MIN_RULE_WIDTH_RATIO = 0.18
_MIN_RULES_FOR_TABLE = 3
#: Hai cụm x0 cách nhau hơn ngần này (pt) là hai cột bảng khác nhau.
_COLUMN_GAP = 18.0
#: Khe dọc tối đa (bội cỡ chữ) giữa hai dòng cùng một ô.
_CELL_LINE_GAP_RATIO = 1.8


@dataclass
class TableRegion:
    """Một vùng bảng trên trang, kèm các đường kẻ ngang bên trong (ranh giới hàng)."""

    id: str
    page_index: int
    rect: Rect
    row_rules: list[float] = field(default_factory=list)

    def contains(self, bbox: Rect, ratio: float = 0.6) -> bool:
        return _overlap_ratio(bbox, self.rect) >= ratio


@dataclass
class TableCell:
    """Một ô bảng: các dòng của ô + khung để dựng bản dịch (không tràn sang ô khác)."""

    region_id: str
    rect: Rect
    lines: list[TextLine]


def find_table_regions(page, page_index: int, lines: list[TextLine]) -> list[TableRegion]:
    """Tìm các vùng bảng trên một trang bằng 3 tín hiệu độc lập rồi hợp nhất."""
    page_rect = page.rect
    text_width = max(page_rect.width, 1.0)

    candidates: list[Rect] = []
    fills, rules = _drawing_features(page, page_rect)

    for rect in fills:
        if rect[2] - rect[0] < text_width * _MIN_FILL_WIDTH_RATIO:
            continue
        if rect[3] - rect[1] < _MIN_FILL_HEIGHT:
            continue
        if _count_lines_inside(rect, lines) >= 2:
            candidates.append(rect)

    candidates.extend(_rule_clusters(rules, text_width, lines))
    candidates.extend(_ruled_tables(page))

    merged = _merge_rects(candidates)
    regions: list[TableRegion] = []
    for index, rect in enumerate(merged):
        if _count_lines_inside(rect, lines) < 2:
            continue
        regions.append(
            TableRegion(
                id=f"p{page_index}_t{index}",
                page_index=page_index,
                rect=rect,
                row_rules=_inner_row_rules(rect, rules),
            )
        )
    return regions


def _inner_row_rules(rect: Rect, rules: list[Rect]) -> list[float]:
    """Cao độ các nét kẻ ngang nằm trong vùng bảng — chính là ranh giới giữa các hàng."""
    inner: list[float] = []
    for rule in rules:
        middle = (rule[1] + rule[3]) / 2
        if rect[1] - 1 <= middle <= rect[3] + 1 and _horizontal_overlap(rect, rule) >= 0.5:
            inner.append(middle)
    return sorted(inner)


def build_cells(region: TableRegion, lines: list[TextLine]) -> list[TableCell]:
    """Chia các dòng trong vùng bảng thành ô: gom cột trước, rồi gom dòng trong cột."""
    if not lines:
        return []

    columns = _group_columns(lines)
    cells: list[TableCell] = []
    for col_index, (col_x0, col_x1, col_lines) in enumerate(columns):
        col_lines.sort(key=lambda ln: ln.bbox[1])
        current: list[TextLine] = []
        for line in col_lines:
            if current and _cell_breaks(current[-1], line, region):
                cells.append(_make_cell(region, col_x0, col_x1, current))
                current = []
            current.append(line)
        if current:
            cells.append(_make_cell(region, col_x0, col_x1, current))

    cells.sort(key=lambda c: (round(c.rect[1], 1), c.rect[0]))
    return cells


def _make_cell(region: TableRegion, col_x0: float, col_x1: float, lines: list[TextLine]) -> TableCell:
    top = min(ln.bbox[1] for ln in lines)
    bottom = max(ln.bbox[3] for ln in lines)
    # Ô rộng bằng cả cột (không chỉ bề ngang chữ hiện có) để bản dịch dài hơn vẫn có chỗ,
    # nhưng không bao giờ lấn sang cột kế bên.
    return TableCell(region_id=region.id, rect=(col_x0, top, col_x1, bottom), lines=list(lines))


def _cell_breaks(prev: TextLine, nxt: TextLine, region: TableRegion) -> bool:
    """Hai dòng cùng cột có thuộc hai ô khác nhau không?"""
    gap = nxt.bbox[1] - prev.bbox[3]
    if gap > _CELL_LINE_GAP_RATIO * max(prev.style.size, 1.0):
        return True
    if not prev.style.matches(nxt.style):
        return True
    # Có nét kẻ ngang chen giữa -> chắc chắn sang hàng mới.
    return any(prev.bbox[3] <= y <= nxt.bbox[1] for y in region.row_rules)


def _group_columns(lines: list[TextLine]) -> list[tuple[float, float, list[TextLine]]]:
    """Gom dòng thành cột theo cụm x0; trả về (x0 cột, x1 cột, các dòng)."""
    ordered = sorted(lines, key=lambda ln: ln.bbox[0])
    groups: list[list[TextLine]] = []
    for line in ordered:
        if groups and line.bbox[0] - groups[-1][-1].bbox[0] <= _COLUMN_GAP:
            groups[-1].append(line)
        else:
            groups.append([line])

    columns: list[tuple[float, float, list[TextLine]]] = []
    for index, group in enumerate(groups):
        x0 = min(ln.bbox[0] for ln in group)
        x1 = max(ln.bbox[2] for ln in group)
        # Cột được phép rộng tới sát cột kế bên (chừa 4pt) để chữ tiếng Việt có chỗ.
        if index + 1 < len(groups):
            next_x0 = min(ln.bbox[0] for ln in groups[index + 1])
            x1 = max(x1, next_x0 - 4.0)
        columns.append((x0, x1, group))
    return columns


def _drawing_features(page, page_rect) -> tuple[list[Rect], list[Rect]]:
    """Tách nét vẽ của trang thành (hình tô, nét kẻ ngang), bỏ trang trí tràn mép trang."""
    fills: list[Rect] = []
    rules: list[Rect] = []
    for drawing in page.get_drawings():
        rect = fitz.Rect(drawing.get("rect"))
        # KHÔNG loại `rect.is_empty`: nét kẻ ngang có chiều cao 0 nên PyMuPDF coi là "empty",
        # mà đó chính là ranh giới hàng cần tìm (bỏ nhầm là bảng gộp hết thành một ô).
        if rect.is_infinite or (rect.width <= 0 and rect.height <= 0):
            continue
        if _bleeds_off_page(rect, page_rect):
            continue
        box = (rect.x0, rect.y0, rect.x1, rect.y1)
        if drawing.get("fill") is not None and drawing.get("type") in ("f", "fs"):
            if rect.height <= _RULE_THICKNESS:
                rules.append(box)
            else:
                fills.append(box)
        elif rect.height <= _RULE_THICKNESS and rect.width > _RULE_THICKNESS:
            rules.append(box)
    return fills, rules


def _bleeds_off_page(rect, page_rect) -> bool:
    return (
        rect.x0 < page_rect.x0 - _PAGE_BLEED_TOLERANCE
        or rect.y0 < page_rect.y0 - _PAGE_BLEED_TOLERANCE
        or rect.x1 > page_rect.x1 + _PAGE_BLEED_TOLERANCE
        or rect.y1 > page_rect.y1 + _PAGE_BLEED_TOLERANCE
    )


def _rule_clusters(rules: list[Rect], text_width: float, lines: list[TextLine]) -> list[Rect]:
    """Nhóm >= 3 nét kẻ ngang cùng khoảng x thành một vùng bảng ứng viên."""
    wide = [r for r in rules if r[2] - r[0] >= text_width * _MIN_RULE_WIDTH_RATIO]
    wide.sort(key=lambda r: (round(r[0] / 8), r[1]))

    clusters: list[list[Rect]] = []
    for rule in wide:
        for cluster in clusters:
            ref = cluster[0]
            if abs(ref[0] - rule[0]) <= 8 and abs(ref[2] - rule[2]) <= 8:
                cluster.append(rule)
                break
        else:
            clusters.append([rule])

    regions: list[Rect] = []
    for cluster in clusters:
        if len(cluster) < _MIN_RULES_FOR_TABLE:
            continue
        x0 = min(r[0] for r in cluster)
        x1 = max(r[2] for r in cluster)
        y0 = min(r[1] for r in cluster)
        y1 = max(r[3] for r in cluster)
        if _count_lines_inside((x0, y0, x1, y1), lines) >= 2:
            regions.append((x0, y0, x1, y1))
    return regions


def _ruled_tables(page) -> list[Rect]:
    """Bảng có khung kẻ thật — để PyMuPDF tự tìm (chỉ dùng chiến lược `lines_strict`)."""
    try:
        finder = page.find_tables(strategy="lines_strict")
    except Exception:  # noqa: BLE001 - find_tables có thể ném lỗi trên trang lạ
        return []
    return [tuple(table.bbox) for table in finder.tables]


def _merge_rects(rects: list[Rect]) -> list[Rect]:
    """Hợp nhất các ứng viên chồng lấn thành một vùng bảng duy nhất."""
    merged: list[Rect] = []
    for rect in sorted(rects, key=lambda r: (r[1], r[0])):
        for index, existing in enumerate(merged):
            if _overlap_ratio(rect, existing) > 0.15 or _overlap_ratio(existing, rect) > 0.15:
                merged[index] = (
                    min(existing[0], rect[0]),
                    min(existing[1], rect[1]),
                    max(existing[2], rect[2]),
                    max(existing[3], rect[3]),
                )
                break
        else:
            merged.append(rect)
    return merged


def _count_lines_inside(rect: Rect, lines: list[TextLine]) -> int:
    return sum(1 for line in lines if _overlap_ratio(line.bbox, rect) >= 0.6)


def _overlap_ratio(inner: Rect, outer: Rect) -> float:
    """Tỉ lệ diện tích `inner` nằm trong `outer`."""
    width = min(inner[2], outer[2]) - max(inner[0], outer[0])
    height = min(inner[3], outer[3]) - max(inner[1], outer[1])
    if width <= 0 or height <= 0:
        return 0.0
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return (width * height) / area if area > 0 else 0.0


def _horizontal_overlap(outer: Rect, rule: Rect) -> float:
    width = min(rule[2], outer[2]) - max(rule[0], outer[0])
    rule_width = rule[2] - rule[0]
    return width / rule_width if rule_width > 0 else 0.0
