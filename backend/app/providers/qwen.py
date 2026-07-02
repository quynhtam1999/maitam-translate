"""Provider Qwen qua ModelScope (endpoint OpenAI-compatible). Hiện là STUB."""
from ..core.config import get_settings
from ..models.glossary import GlossaryEntry
from .base import BaseProvider, ProviderQuotaError, RateLimits, TranslationResult


class QwenProvider(BaseProvider):
    name = "qwen"
    display_name = "Qwen3 235B (ModelScope)"

    def __init__(self, model: str = "Qwen/Qwen3-235B-A22B-Instruct-2507"):
        self.model = model

    def is_configured(self) -> bool:
        return bool(get_settings().qwen_api_key)

    def get_limits(self) -> RateLimits:
        s = get_settings()
        return RateLimits(rpm=s.qwen_rpm_limit, tpm=s.qwen_tpm_limit, rpd=s.qwen_rpd_limit)

    async def translate(
        self,
        text: str,
        target_lang: str = "vi",
        glossary_hints: list[GlossaryEntry] | None = None,
    ) -> TranslationResult:
        # TODO: gọi endpoint OpenAI-compatible của ModelScope qua httpx:
        #   POST {QWEN_BASE_URL}/chat/completions với header Authorization: Bearer <QWEN_API_KEY>.
        #   - messages: system (yêu cầu dịch sang target_lang + glossary) + user (text).
        #   - Đọc response.usage.prompt_tokens / completion_tokens làm token thật.
        #   - Nếu HTTP 429 / báo hết quota -> raise ProviderQuotaError.
        raise NotImplementedError(
            "QwenProvider.translate chưa được triển khai — xem TODO trong qwen.py"
        )
