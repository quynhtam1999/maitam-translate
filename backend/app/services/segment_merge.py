"""Gộp các mảnh câu bị PDF cắt ngang thành ĐƠN VỊ DỊCH, rồi phân bổ bản dịch về từng bbox.

Vì sao cần: `collect_segments` bóc chữ theo vị trí trên trang (để chèn bản dịch lại đúng chỗ),
nên một câu bị cắt ở biên khối/cột/trang thành nhiều mảnh, và mỗi mảnh thành một đơn vị dịch
riêng. Đo trên sách y khoa 2 cột thật (372 khối, 253 khối văn xuôi): **51% kết thúc giữa câu,
24% bắt đầu giữa câu**. Mảnh mà model thật sự nhận được trông như:

    'ited bone marrow failure. In a child with a history of bone'

(bắt đầu bằng đuôi của "inherited"). Không model nào dịch chuẩn được mảnh như vậy — đây là
trần chất lượng chung, KHÔNG phải lỗi provider.

Cách làm: gộp mảnh liền mạch trong thứ tự đọc thành một đơn vị dịch, dịch trọn câu, rồi cắt
bản dịch trả về từng bbox theo tỉ lệ độ dài nguồn.

**Vì sao cắt theo tỉ lệ là đúng, dù trật tự từ Việt/Anh khác nhau:** người đọc đọc các bbox
THEO THỨ TỰ ĐỌC, nên chỗ cắt không cần khớp ngữ nghĩa với mảnh gốc — chỉ cần ghép các phần
lại đúng thứ tự thì ra nguyên văn bản dịch, và mỗi phần vừa bbox của nó. Cắt luôn rơi vào
ranh giới từ.

Luật gộp cố ý CHẶT: sai một lần gộp là trộn nội dung hai khối không liên quan, hại hơn cái nó
sửa. Không chắc thì không gộp — mảnh giữ nguyên như trước, không tệ đi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .pdf_overlay import COLUMN_LEFT, COLUMN_RIGHT, TextSegment

#: Trần số mảnh/đơn vị — chỉ là lưới an toàn chặn thiệt hại nếu một chuỗi bị gộp nhầm dây
#: chuyền, KHÔNG phải để giới hạn độ dài đoạn. Chuỗi tự dừng ở dấu chấm hết câu nên độ dài
#: thật do văn bản quyết định: đo trên 2 tài liệu (1176 khối) chuỗi dài nhất chỉ **12 mảnh /
#: 702 ký tự**, nên trần này gần như không bao giờ chạm tới. Đừng hạ xuống mức chạm được:
#: trần 6 từng cắt ngang một đoạn 12 dòng thành 6+6, đúng cái mà module này sinh ra để sửa.
_MAX_PARTS_PER_UNIT = 40
#: Ký tự kết câu: mảnh kết thúc bằng chúng thì coi như câu đã trọn -> không gộp tiếp.
_SENTENCE_END_CHARS = ".!?:;"
#: Dấu đóng bám sau dấu kết câu ('... [3].”' ) — bỏ ra trước khi soi ký tự cuối.
_TRAILING_CLOSERS = "\"'”’)]}»›"
#: Khe dọc tối đa (theo bội cỡ chữ) giữa hai khối cùng cột còn coi là liền mạch. ~1.6 lần cỡ
#: chữ đủ cho một khoảng dòng bình thường nhưng chặn được khe ngắt mục.
_SAME_COLUMN_GAP_RATIO = 1.6
#: Đoạn chỉ tràn sang cột/trang kế khi nó đã chạm đáy cột. Đo trên sách thật: ca nối cột
#: ĐÚNG có đáy y1=730/792 (92%), còn ca gộp NHẦM (caption bảng ở đỉnh cột trái, cạnh thân
#: bài cột phải) có y1=72/792 — ngưỡng 75% tách sạch hai ca này.
_COLUMN_TAIL_RATIO = 0.75
#: Đối xứng: mảnh nối tiếp phải nằm ở đỉnh cột/trang mới.
_COLUMN_HEAD_RATIO = 0.25
#: Dung sai so khớp kiểu chữ giữa hai mảnh của cùng một đoạn (pt).
_FONT_SIZE_TOLERANCE = 0.75


@dataclass
class TranslationUnit:
    """Một đơn vị dịch: chữ đã gộp + các mảnh gốc tạo nên nó (theo thứ tự đọc)."""

    text: str
    parts: list[TextSegment] = field(default_factory=list)


def build_translation_units(segments: list[TextSegment]) -> list[TranslationUnit]:
    """Gộp các mảnh liền mạch trong `segments` (đã ở thứ tự đọc) thành đơn vị dịch."""
    groups: list[list[TextSegment]] = []
    open_group: list[TextSegment] | None = None

    for seg in segments:
        if seg.is_furniture:
            # Header/footer chạy trang: đứng riêng một đơn vị, nhưng KHÔNG cắt mạch — nhờ vậy
            # đoạn cuối trang trước vẫn nối được với đầu trang sau xuyên qua header.
            groups.append([seg])
            continue

        if not seg.mergeable:
            # Dòng bảng chen giữa hai đoạn văn nghĩa là chúng KHÔNG liền mạch -> cắt.
            groups.append([seg])
            open_group = None
            continue

        if (
            open_group is not None
            and len(open_group) < _MAX_PARTS_PER_UNIT
            and _can_merge(open_group[-1], seg)
        ):
            open_group.append(seg)
            continue

        open_group = [seg]
        groups.append(open_group)

    return [TranslationUnit(text=_merged_text(group), parts=group) for group in groups]


def distribute_translation(unit: TranslationUnit, translated: str) -> dict[str, str]:
    """Cắt bản dịch của một đơn vị trả về từng bbox -> ánh xạ block_id -> chữ."""
    if len(unit.parts) == 1:
        return {unit.parts[0].block_id: translated}

    weights = [max(len(part.text), 1) for part in unit.parts]
    chunks = _split_proportional(translated, weights)
    return {part.block_id: chunk for part, chunk in zip(unit.parts, chunks, strict=True)}


def _merged_text(parts: list[TextSegment]) -> str:
    text = parts[0].text
    for seg in parts[1:]:
        text = _join_fragments(text, seg.text)
    return text


def _join_fragments(left: str, right: str) -> str:
    # 'inher-' + 'ited' -> 'inherited'. Cùng cách xử lý mà _clean_block_text đã dùng cho chữ
    # bị gạch nối cuối dòng TRONG một khối; ở đây là gạch nối rơi đúng biên khối.
    if re.search(r"\w-$", left) and right[:1].islower():
        return left[:-1] + right
    return f"{left} {right}"


def _can_merge(prev: TextSegment, nxt: TextSegment) -> bool:
    if not (prev.mergeable and nxt.mergeable):
        return False
    if prev.is_furniture or nxt.is_furniture:
        return False
    if not _ends_mid_sentence(prev.text):
        return False
    if not _starts_mid_sentence(nxt.text):
        return False
    if not _style_matches(prev, nxt):
        return False
    return _flows_into(prev, nxt)


def _ends_mid_sentence(text: str) -> bool:
    trimmed = text.rstrip().rstrip(_TRAILING_CLOSERS).rstrip()
    return bool(trimmed) and trimmed[-1] not in _SENTENCE_END_CHARS


def _starts_mid_sentence(text: str) -> bool:
    trimmed = text.lstrip()
    # Chỉ nhận chữ cái thường mở đầu. Mảnh mở đầu bằng số/ngoặc/ký hiệu ('<2 SD for age)a')
    # hầu hết là ô bảng, gộp vào là trộn nội dung.
    return bool(trimmed) and trimmed[0].islower()


def _style_matches(prev: TextSegment, nxt: TextSegment) -> bool:
    # So cỡ chữ THÂN khối, không so `font_size` (= max): đo trên sách thật có ca nối cột
    # hoàn hảo ('…This group is at' -> 'increased risk of exaggerated ovarian response…')
    # bị chặn oan chỉ vì khối trước lẫn một span 10pt giữa nền chữ 9pt.
    return (
        abs(prev.dominant_font_size - nxt.dominant_font_size) <= _FONT_SIZE_TOLERANCE
        and prev.is_bold == nxt.is_bold
        and prev.color == nxt.color
    )


def _flows_into(prev: TextSegment, nxt: TextSegment) -> bool:
    """Mảnh sau có thật sự là chỗ đoạn văn chảy tiếp không (theo hình học trang)?"""
    if prev.page_index == nxt.page_index:
        if prev.column == nxt.column:
            gap = nxt.bbox[1] - prev.bbox[3]
            # Cho phép chồng nhẹ (khối kề nhau đôi khi lệch âm vài pt), chặn khe ngắt mục.
            return -prev.font_size <= gap <= _SAME_COLUMN_GAP_RATIO * prev.font_size
        if prev.column == COLUMN_LEFT and nxt.column == COLUMN_RIGHT:
            # Không đòi `nxt` phải ở đỉnh cột: thứ tự đọc đã bảo đảm nxt là khối trên cùng
            # của cột phải, mà đỉnh cột phải hay bị bảng/hình chiếm (đo được: cột phải p3 mãi
            # y=485 mới có chữ) — đòi thêm là chặn oan đúng dòng chảy thật.
            return _at_column_tail(prev)
        return False

    if nxt.page_index == prev.page_index + 1:
        return _at_column_tail(prev) and _at_column_head(nxt)

    return False


def _at_column_tail(seg: TextSegment) -> bool:
    return seg.page_height > 0 and seg.bbox[3] >= seg.page_height * _COLUMN_TAIL_RATIO


def _at_column_head(seg: TextSegment) -> bool:
    return seg.page_height > 0 and seg.bbox[1] <= seg.page_height * _COLUMN_HEAD_RATIO


def _split_proportional(text: str, weights: list[int]) -> list[str]:
    """Cắt `text` thành len(weights) phần tại ranh giới từ, theo tỉ lệ `weights`."""
    words = text.split()
    parts_count = len(weights)
    if parts_count <= 1:
        return [text]
    if len(words) < parts_count:
        # Ít từ hơn số bbox — không có cách cắt nào cho mỗi bbox một từ. Hiếm tới mức chỉ
        # xảy ra khi provider trả về gần như rỗng; dồn hết vào mảnh đầu để không mất chữ.
        return [text] + [""] * (parts_count - 1)

    # bounds[k] = độ dài của " ".join(words[:k + 1]) -> vị trí ký tự của mỗi ranh giới từ.
    bounds: list[int] = []
    acc = 0
    for word in words:
        acc += len(word) + (1 if bounds else 0)
        bounds.append(acc)

    total_weight = sum(weights)
    total_len = bounds[-1]
    cuts: list[int] = []
    prev_cut = 0
    cumulative_weight = 0
    for index, weight in enumerate(weights[:-1]):
        cumulative_weight += weight
        target = total_len * cumulative_weight / total_weight
        remaining_parts = parts_count - index - 1
        # Chừa >= 1 từ cho mỗi phần còn lại, và >= 1 từ cho phần vừa cắt.
        lo = prev_cut + 1
        hi = len(words) - remaining_parts
        cut = min(range(lo, hi + 1), key=lambda k: abs(bounds[k - 1] - target))
        cuts.append(cut)
        prev_cut = cut

    chunks: list[str] = []
    start = 0
    for cut in cuts:
        chunks.append(" ".join(words[start:cut]))
        start = cut
    chunks.append(" ".join(words[start:]))
    return chunks
