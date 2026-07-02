"""Schema cho dịch văn bản dán tay (tab "Dịch văn bản")."""
from pydantic import BaseModel, Field

from .provider import QuotaSnapshot


class TextTranslateRequest(BaseModel):
    text: str = Field(..., min_length=1)
    target_lang: str = "vi"
    provider: str


class TextTranslateResponse(BaseModel):
    translated_text: str
    provider_used: str
    quota: QuotaSnapshot | None = None
