"""Giao diện trừu tượng cho nhà cung cấp dịch (multi-provider).

Mọi provider (Gemini, Gemma, Qwen...) đều hiện thực interface này, nên router/service
không bao giờ import trực tiếp một provider cụ thể — luôn qua registry.get_provider().
"""
from abc import ABC, abstractmethod

from pydantic import BaseModel

from ..models.glossary import GlossaryEntry


class RateLimits(BaseModel):
    rpm: int
    tpm: int
    rpd: int


class TranslationResult(BaseModel):
    text: str
    # Số token THẬT lấy từ phản hồi API — cần cho việc đếm quota cục bộ (A6b).
    input_tokens: int = 0
    output_tokens: int = 0


class ProviderQuotaError(Exception):
    """Ném ra khi provider báo hết quota / vượt RPM — pipeline sẽ đặt job = paused_quota."""


class BaseProvider(ABC):
    #: định danh nội bộ, vd "gemini" | "gemma" | "qwen"
    name: str = ""
    #: tên hiển thị cho người dùng
    display_name: str = ""

    @abstractmethod
    async def translate(
        self,
        text: str,
        target_lang: str = "vi",
        glossary_hints: list[GlossaryEntry] | None = None,
    ) -> TranslationResult:
        """Dịch một đoạn văn bản.

        TODO: gọi HTTP thật (httpx) tới Gemini/Qwen. Phải trả về số token thật
        từ phản hồi để QuotaTracker đếm quota cục bộ (A6b). Khi provider báo hết
        quota/vượt RPM thì raise ProviderQuotaError.
        """
        raise NotImplementedError

    @abstractmethod
    def get_limits(self) -> RateLimits:
        """Trả về giới hạn RPM/TPM/RPD (đọc từ cấu hình)."""
        raise NotImplementedError

    def is_configured(self) -> bool:
        """Provider đã có API key để dùng chưa."""
        return True
