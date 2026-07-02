"""Schema cho từ điển thuật ngữ (glossary)."""
from typing import Literal

from pydantic import BaseModel


class GlossaryEntry(BaseModel):
    source: str
    target: str
    # translate: ép bản dịch ưu tiên | keep: giữ nguyên không dịch (vd tên thuốc)
    mode: Literal["translate", "keep"] = "translate"


class GlossaryUploadResponse(BaseModel):
    count_loaded: int
