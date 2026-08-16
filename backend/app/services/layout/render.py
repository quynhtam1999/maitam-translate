"""Dựng lại PDF: xóa đúng chữ gốc, rồi RÓT bản dịch vào vùng của từng khối.

Ba nguyên tắc, đều là chỗ engine cũ làm sai:

1. **Xóa theo dòng, không xóa theo khối.** Redaction cũ phủ cả bbox khối nên ăn luôn nền
   màu và khung bảng. Nay chỉ xóa đúng hộp từng dòng chữ, và luôn giữ ảnh + nét vẽ
   (`PDF_REDACT_IMAGE_NONE` / `PDF_REDACT_LINE_ART_NONE`).
2. **Rót tuần tự, không cắt theo tỉ lệ.** Khối chảy tràn nhiều vùng thì đổ đầy vùng 1 rồi
   mới sang vùng 2 — chữ không bao giờ rơi sang ô/khối khác.
3. **Co chữ vừa phải rồi mượn chỗ trống.** Thứ tự thử: giữ nguyên cỡ chữ -> co dần tối đa
   15% -> nới xuống khoảng trắng trống ngay bên dưới (đã tính sẵn trong `Area.max_bottom`,
   không đụng dòng/ảnh/hàng bảng nào) -> cuối cùng mới co mạnh xuống sàn 5.5pt.
"""
from __future__ import annotations

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore

from . import fonts
from .model import Block, BORROWING_KINDS

#: Nới hộp xóa ra vài phần mười pt để không sót nét chân/đuôi chữ gốc.
_REDACT_PADDING = 0.7
#: Độ phân giải lấy mẫu màu nền khi phải vá (đủ để đọc màu, không tốn bộ nhớ).
_PATCH_SAMPLE_DPI = 96
#: Các mức co chữ được thử theo thứ tự (1.0 = giữ nguyên cỡ gốc).
_SCALE_STEPS = (1.0, 0.97, 0.94, 0.91, 0.88, 0.85)
_MIN_FONT_SIZE = 5.5
#: Giãn dòng tối thiểu khi phải nén cho vừa.
_MIN_LINE_HEIGHT = 0.95


def render_document(doc, blocks: list[Block], translations: dict[str, str]) -> None:
    """Xóa chữ gốc và chèn bản dịch cho toàn tài liệu (tại chỗ, trên `doc`)."""
    by_page: dict[int, dict[str, Block]] = {}
    for block in blocks:
        for area in block.areas:
            # Khối tràn trang xuất hiện ở nhiều trang; mỗi trang chỉ vẽ phần của mình.
            by_page.setdefault(area.page_index, {})[block.id] = block

    _redact(doc, blocks)

    for page_index, page_blocks in by_page.items():
        page = doc[page_index]
        for block in page_blocks.values():
            text = translations.get(block.id) or block.text
            if text.strip():
                _draw_block(page, page_index, block, text)


def _redact(doc, blocks: list[Block]) -> None:
    """Xóa chữ gốc theo từng dòng của các khối SẼ được viết đè lên.

    Hai cách xóa, chọn theo TỪNG TRANG dựa trên thử nghiệm thật chứ không đoán:

    - **Bôi đen (redaction)** — cách sạch nhất, gỡ hẳn chữ khỏi tầng text.
    - **Vá nền (patch)** — vẽ chữ nhật màu nền đè lên đúng hộp dòng chữ.

    Vì sao phải có cách thứ hai: `01. tntc.pdf` đặt chữ bằng toán tử dời chỗ TƯƠNG ĐỐI, nên
    xóa một dòng làm các dòng sau trong cùng khối chữ **trôi đi** (đo được: footnote trang 831
    nhảy từ y=660 lên y=497 đè lên hình; ghi chú bảng trang 832 nhảy 330 -> 251). Đây mới là
    thủ phạm thật của ca "chữ gốc còn nguyên, bản dịch đè chồng lên", không phải luật bỏ khối
    đè ảnh. `clean_contents(sanitize=True)` của MuPDF *không* cứu được: đo bằng ảnh render
    trước/sau, nó **tự nó làm trôi chữ** ở 62/1867 dòng của tài liệu này.

    Nên: thử bôi đen trên một BẢN SAO trước; trang nào sau khi bôi đen mà mọi dòng còn lại đều
    nguyên vị trí thì bôi đen thật, trang nào có dòng trôi thì chuyển sang vá nền.
    """
    per_page: dict[int, list] = {}
    for block in blocks:
        for page_index, rect in block.line_rects:
            per_page.setdefault(page_index, []).append(rect)

    unsafe = _pages_unsafe_for_redaction(doc, per_page)
    for page_index, rects in per_page.items():
        page = doc[page_index]
        if page_index in unsafe:
            _patch_over_text(page, rects)
        else:
            _apply_redactions(page, rects)


def _apply_redactions(page, rects) -> None:
    for rect in rects:
        page.add_redact_annot(_padded(rect), cross_out=False)
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_NONE,
        text=fitz.PDF_REDACT_TEXT_REMOVE,
    )


def _padded(rect):
    return fitz.Rect(rect) + (
        -_REDACT_PADDING,
        -_REDACT_PADDING,
        _REDACT_PADDING,
        _REDACT_PADDING,
    )


def _pages_unsafe_for_redaction(doc, per_page: dict[int, list]) -> set[int]:
    """Thử bôi đen trên bản sao; trang nào có chữ TRÔI CHỖ thì đánh dấu là không an toàn."""
    scratch = fitz.open()
    scratch.insert_pdf(doc)
    unsafe: set[int] = set()
    for page_index, rects in per_page.items():
        page = scratch[page_index]
        before = _line_positions(page)
        try:
            _apply_redactions(page, rects)
        except Exception:  # noqa: BLE001 - trang lỗi thì cứ vá nền cho chắc
            unsafe.add(page_index)
            continue
        # Chữ còn lại phải y nguyên chỗ cũ. Xuất hiện ở chỗ mới = đã bị trôi.
        if not _line_positions(page) <= before:
            unsafe.add(page_index)
    scratch.close()
    return unsafe


def _line_positions(page) -> set:
    positions = set()
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            if text.strip():
                positions.add((text, tuple(round(v) for v in line.get("bbox", ()))))
    return positions


def _patch_over_text(page, rects) -> None:
    """Vá màu nền lên từng dòng chữ gốc — không đụng vào luồng nội dung nên không làm trôi gì.

    Đánh đổi: chữ gốc vẫn còn trong tầng text (vô hình vì bị che), nên tìm kiếm/copy trên file
    kết quả sẽ thấy cả bản gốc lẫn bản dịch. Chấp nhận được, vì cách còn lại (bôi đen) làm
    **hỏng hình thức trang** trên tài liệu kiểu này.
    """
    pixmap = page.get_pixmap(dpi=_PATCH_SAMPLE_DPI)
    scale = _PATCH_SAMPLE_DPI / 72.0
    for rect in rects:
        box = _padded(rect)
        color = _background_color(pixmap, box, scale)
        if color is None:
            continue
        page.draw_rect(box, color=None, fill=color, width=0, overlay=True)


def _background_color(pixmap, box, scale):
    """Màu nền dưới hộp chữ = màu XUẤT HIỆN NHIỀU NHẤT trong chính hộp đó.

    Lấy mốt (mode) chứ không lấy trung vị, và lấy BÊN TRONG hộp chứ không lấy vành đai: nét
    chữ chỉ chiếm thiểu số điểm ảnh nên nền luôn thắng, kể cả chữ trắng trên nền sẫm. Lấy vành
    đai thì hỏng đúng ca chữ nằm trong ô màu vừa khít (nhãn 'Table 32-2' trên thẻ tím): vành
    đai rơi ra ngoài thẻ và trả về màu trắng của trang, vá trắng đè lên thẻ.
    """
    x0, y0 = max(int(box.x0 * scale), 0), max(int(box.y0 * scale), 0)
    x1 = min(int(box.x1 * scale), pixmap.width)
    y1 = min(int(box.y1 * scale), pixmap.height)
    if x1 <= x0 or y1 <= y0:
        return None

    counts: dict[tuple[int, int, int], int] = {}
    x_step = max(1, (x1 - x0) // 32)
    y_step = max(1, (y1 - y0) // 12)
    for x in range(x0, x1, x_step):
        for y in range(y0, y1, y_step):
            pixel = pixmap.pixel(x, y)[:3]
            # Gộp màu về lưới 8 mức/kênh để nhiễu khử răng cưa không xé nhỏ số đếm.
            key = (pixel[0] // 8, pixel[1] // 8, pixel[2] // 8)
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None

    red, green, blue = max(counts, key=counts.get)
    return ((red * 8 + 4) / 255.0, (green * 8 + 4) / 255.0, (blue * 8 + 4) / 255.0)


def _draw_block(page, page_index: int, block: Block, text: str) -> None:
    """Vẽ bản dịch của một khối lên đúng trang của nó (phần thuộc trang này)."""
    font = fonts.font_for_text(block.style, text)
    plan = _fit(block, text, font)
    if plan is None:
        return

    size, line_height, rects, chunks = plan
    color = _rgb(block.style.color)
    writer = fitz.TextWriter(page.rect)
    wrote = False
    for area, rect, chunk in zip(block.areas, rects, chunks, strict=True):
        if area.page_index != page_index or not chunk.strip():
            continue
        writer.fill_textbox(
            fitz.Rect(rect),
            chunk,
            font=font,
            fontsize=size,
            align=block.align,
            lineheight=line_height,
            warn=None,
        )
        wrote = True
    if wrote:
        writer.write_text(page, color=color)


def _fit(block: Block, text: str, font):
    """Chọn cỡ chữ + hộp cho khối, theo thứ tự ưu tiên: giữ cỡ > co nhẹ > mượn chỗ trống."""
    base = max(block.style.size, _MIN_FONT_SIZE)
    borrowable = block.kind in BORROWING_KINDS

    for borrow in (False, True) if borrowable else (False,):
        rects = [area.extended() if borrow else area.rect for area in block.areas]
        for scale in _SCALE_STEPS:
            size = round(base * scale, 1)
            if size < _MIN_FONT_SIZE:
                break
            chunks = _pour(text, rects, font, size, block)
            if chunks is not None:
                return size, _line_height(block, scale), rects, chunks

    # Vẫn không vừa: co xuống sàn và chấp nhận hộp lớn nhất có được.
    rects = [area.extended() if borrowable else area.rect for area in block.areas]
    size = base
    while size > _MIN_FONT_SIZE:
        size = round(max(size - 0.5, _MIN_FONT_SIZE), 1)
        chunks = _pour(text, rects, font, size, block)
        if chunks is not None:
            return size, _MIN_LINE_HEIGHT, rects, chunks

    chunks = _pour(text, rects, font, _MIN_FONT_SIZE, block, allow_overflow=True)
    return _MIN_FONT_SIZE, _MIN_LINE_HEIGHT, rects, chunks


def _pour(text, rects, font, size, block: Block, allow_overflow: bool = False):
    """Thử rót `text` lần lượt vào các hộp; trả về phần chữ cho từng hộp, None nếu không vừa.

    Chạy trên `TextWriter` nháp — chỉ đo, không vẽ gì lên trang thật.
    """
    words = text.split()
    chunks: list[str] = []
    line_height = _line_height(block, size / max(block.style.size, 1.0))
    cursor = 0

    for index, rect in enumerate(rects):
        remaining = " ".join(words[cursor:])
        if not remaining:
            chunks.append("")
            continue
        probe = fitz.TextWriter(fitz.Rect(0, 0, 10000, 10000))
        leftover = probe.fill_textbox(
            fitz.Rect(rect),
            remaining,
            font=font,
            fontsize=size,
            align=block.align,
            lineheight=line_height,
            warn=None,
        )
        # `fill_textbox` trả về các DÒNG không vẽ được; đếm theo TỪ (không theo ký tự) vì nó
        # đã chuẩn hóa khoảng trắng, so độ dài chuỗi sẽ lệch.
        left_words = sum(len(line.split()) for line, _ in leftover)
        taken = max(len(words) - cursor - left_words, 0)
        chunks.append(" ".join(words[cursor : cursor + taken]))
        cursor += taken
        if taken == 0 and index == len(rects) - 1:
            break
        if cursor >= len(words):
            chunks.extend([""] * (len(rects) - index - 1))
            break

    remaining = " ".join(words[cursor:])

    if remaining and not allow_overflow:
        return None
    if remaining:
        chunks[-1] = f"{chunks[-1]} {remaining}".strip()
    return chunks


def _line_height(block: Block, scale: float) -> float:
    """Giữ mật độ dòng như bản gốc; chỉ nén lại khi phải co chữ."""
    return max(_MIN_LINE_HEIGHT, block.line_height if scale >= 0.99 else block.line_height * 0.97)


def _rgb(color: int) -> tuple[float, float, float]:
    return (((color >> 16) & 0xFF) / 255.0, ((color >> 8) & 0xFF) / 255.0, (color & 0xFF) / 255.0)
