"""Dựng prompt dịch dùng chung cho mọi provider (Gemini/Qwen)."""
from ..models.glossary import GlossaryEntry

_LANG_NAMES = {
    "vi": "tiếng Việt",
    "en": "tiếng Anh",
}


def build_system_prompt(target_lang: str, glossary_hints: list[GlossaryEntry] | None) -> str:
    lang_name = _LANG_NAMES.get(target_lang, target_lang)
    lines = [
        f"Bạn là biên dịch viên y khoa chuyên nghiệp. Dịch đoạn văn bản người dùng gửi sang {lang_name}.",
        "Giữ nguyên ý nghĩa chuyên môn, dùng thuật ngữ y khoa chuẩn xác.",
        "Chỉ trả về đúng bản dịch, KHÔNG thêm giải thích, KHÔNG thêm ghi chú, KHÔNG lặp lại văn bản gốc.",
    ]

    translate_terms = [g for g in (glossary_hints or []) if g.mode == "translate" and g.target]
    keep_terms = [g for g in (glossary_hints or []) if g.mode == "keep"]

    if translate_terms:
        pairs = "; ".join(f"{g.source} -> {g.target}" for g in translate_terms)
        lines.append(f"Bắt buộc dịch đúng các thuật ngữ sau: {pairs}.")
    if keep_terms:
        terms = "; ".join(g.source for g in keep_terms)
        lines.append(f"Giữ nguyên không dịch (tên thuốc/riêng): {terms}.")

    return "\n".join(lines)


def build_batch_system_prompt(target_lang: str, glossary_hints: list[GlossaryEntry] | None) -> str:
    lang_name = _LANG_NAMES.get(target_lang, target_lang)
    lines = [
        f"Bạn là biên dịch viên y khoa chuyên nghiệp. Dịch từng mục trong JSON người dùng gửi sang {lang_name}.",
        "Giữ nguyên ý nghĩa chuyên môn, dùng thuật ngữ y khoa chuẩn xác.",
        "Người dùng sẽ gửi một JSON array gồm các object {\"id\": number, \"text\": string}.",
        "Trả về DUY NHẤT JSON hợp lệ dạng {\"translations\":[{\"id\": number, \"text\": string}]} theo đúng id đầu vào.",
        "Không thêm markdown, không giải thích, không bỏ sót mục, không gộp các mục với nhau.",
    ]

    translate_terms = [g for g in (glossary_hints or []) if g.mode == "translate" and g.target]
    keep_terms = [g for g in (glossary_hints or []) if g.mode == "keep"]

    if translate_terms:
        pairs = "; ".join(f"{g.source} -> {g.target}" for g in translate_terms)
        lines.append(f"Bắt buộc dịch đúng các thuật ngữ sau: {pairs}.")
    if keep_terms:
        terms = "; ".join(g.source for g in keep_terms)
        lines.append(f"Giữ nguyên không dịch (tên thuốc/riêng): {terms}.")

    return "\n".join(lines)
