"""Từ điển thuật ngữ (THAMKHAO A7): CSV 3 cột source,target,mode.

- mode=translate: ép bản dịch ưu tiên (vd 'preterm labor,chuyển dạ sinh non,translate').
- mode=keep: giữ nguyên không dịch (vd tên thuốc 'oxytocin,,keep').
"""
import csv
import io
from pathlib import Path

from ..models.glossary import GlossaryEntry


def load_glossary(path: Path) -> list[GlossaryEntry]:
    """Đọc glossary.csv trên đĩa. Trả list rỗng nếu file chưa tồn tại."""
    if not path.exists():
        return []
    return load_glossary_bytes(path.read_bytes())


def load_glossary_bytes(data: bytes) -> list[GlossaryEntry]:
    """Đọc glossary từ bytes CSV (dùng khi lấy dữ liệu qua object storage)."""
    text = data.decode("utf-8-sig")
    entries: list[GlossaryEntry] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        source = (row.get("source") or "").strip()
        if not source:
            continue
        mode = (row.get("mode") or "translate").strip().lower()
        if mode not in ("translate", "keep"):
            mode = "translate"
        entries.append(
            GlossaryEntry(source=source, target=(row.get("target") or "").strip(), mode=mode)  # type: ignore[arg-type]
        )
    return entries


def apply_glossary_pre(text: str, glossary: list[GlossaryEntry]) -> str:
    """Xử lý trước khi gửi LLM.

    TODO: với mode=keep, bảo vệ thuật ngữ (vd thay bằng placeholder) để không bị dịch.
    Hiện trả nguyên văn.
    """
    return text


def apply_glossary_post(translated_text: str, glossary: list[GlossaryEntry]) -> str:
    """Xử lý sau khi LLM trả kết quả.

    TODO: với mode=translate, đảm bảo/ép đúng thuật ngữ đích xuất hiện; khôi phục placeholder keep.
    Hiện trả nguyên văn.
    """
    return translated_text
