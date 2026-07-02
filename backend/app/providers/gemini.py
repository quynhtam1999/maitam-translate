"""Provider Google AI Studio (Gemini / Gemma). Hiện là STUB."""
from ..core.config import get_settings
from ..models.glossary import GlossaryEntry
from .base import BaseProvider, ProviderQuotaError, RateLimits, TranslationResult


class GeminiProvider(BaseProvider):
    name = "gemini"
    display_name = "Gemini 3.1 Flash Lite"

    def __init__(self, model: str = "gemini-3.1-flash-lite", display_name: str | None = None):
        self.model = model
        if display_name:
            self.display_name = display_name

    def is_configured(self) -> bool:
        return bool(get_settings().gemini_api_key)

    def get_limits(self) -> RateLimits:
        s = get_settings()
        return RateLimits(rpm=s.gemini_rpm_limit, tpm=s.gemini_tpm_limit, rpd=s.gemini_rpd_limit)

    async def translate(
        self,
        text: str,
        target_lang: str = "vi",
        glossary_hints: list[GlossaryEntry] | None = None,
    ) -> TranslationResult:
        # TODO: gọi Google AI Studio (generativelanguage API) qua httpx.
        #   - Dựng prompt dịch sang target_lang, chèn glossary_hints (translate/keep).
        #   - Đọc usageMetadata.promptTokenCount / candidatesTokenCount làm token thật.
        #   - Nếu HTTP 429 / báo hết quota -> raise ProviderQuotaError.
        raise NotImplementedError(
            "GeminiProvider.translate chưa được triển khai — xem TODO trong gemini.py"
        )
