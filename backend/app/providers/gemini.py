"""Provider Google AI Studio (Gemini / Gemma) — gọi generativelanguage API qua httpx."""
import json

import httpx

from ..core.config import get_settings
from ..models.glossary import GlossaryEntry
from .base import (
    BaseProvider,
    BatchTranslationResult,
    ProviderQuotaError,
    RateLimits,
    TranslationResult,
    parse_batch_translations,
)
from .prompt import build_batch_system_prompt, build_system_prompt

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(BaseProvider):
    name = "gemini"
    display_name = "Gemini 3.1 Flash Lite"

    def __init__(
        self,
        model: str = "gemini-3.1-flash-lite",
        display_name: str | None = None,
        name: str = "gemini",
    ):
        self.model = model
        self.name = name
        if display_name:
            self.display_name = display_name

    def is_configured(self) -> bool:
        return bool(get_settings().gemini_api_key)

    def get_limits(self) -> RateLimits:
        s = get_settings()
        if self.name == "gemma":
            return RateLimits(
                rpm=s.gemma_rpm_limit,
                tpm=s.gemma_tpm_limit,
                rpd=s.gemma_rpd_limit,
                max_output_tokens=s.gemma_max_tokens_per_request,
            )
        return RateLimits(
            rpm=s.gemini_rpm_limit,
            tpm=s.gemini_tpm_limit,
            rpd=s.gemini_rpd_limit,
            max_output_tokens=s.gemini_max_tokens_per_request,
        )

    async def translate(
        self,
        text: str,
        target_lang: str = "vi",
        glossary_hints: list[GlossaryEntry] | None = None,
        api_key: str | None = None,
        provider_options: dict | None = None,
    ) -> TranslationResult:
        api_key = api_key or get_settings().gemini_api_key
        if not api_key:
            raise RuntimeError("Chưa có API key cho Gemini/Gemma — nhập trong ⚙ Cài đặt")

        system_prompt = build_system_prompt(target_lang, glossary_hints)
        url = f"{_API_BASE}/{self.model}:generateContent"
        body = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {"temperature": 0.2},
        }
        max_output_tokens = self.get_limits().max_output_tokens
        if max_output_tokens > 0:
            body["generationConfig"]["maxOutputTokens"] = max_output_tokens

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, params={"key": api_key}, json=body)

        if resp.status_code == 429:
            raise ProviderQuotaError(f"Gemini hết quota / vượt giới hạn tốc độ: {resp.text}")
        if resp.status_code >= 400:
            data = _safe_json(resp)
            message = (data.get("error") or {}).get("message", resp.text) if data else resp.text
            status = (data.get("error") or {}).get("status", "") if data else ""
            if status in ("RESOURCE_EXHAUSTED",):
                raise ProviderQuotaError(f"Gemini hết quota: {message}")
            raise RuntimeError(f"Gemini API lỗi ({resp.status_code}): {message}")

        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            block_reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise RuntimeError(f"Gemini không trả về kết quả (blockReason={block_reason})")

        parts = candidates[0].get("content", {}).get("parts", [])
        translated = "".join(p.get("text", "") for p in parts).strip()

        usage = data.get("usageMetadata", {})
        return TranslationResult(
            text=translated,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
        )

    async def translate_batch(
        self,
        texts: list[str],
        target_lang: str = "vi",
        glossary_hints: list[GlossaryEntry] | None = None,
        api_key: str | None = None,
        provider_options: dict | None = None,
    ) -> BatchTranslationResult:
        if not texts:
            return BatchTranslationResult(texts=[])

        api_key = api_key or get_settings().gemini_api_key
        if not api_key:
            raise RuntimeError("Chưa có API key cho Gemini/Gemma — nhập trong ⚙ Cài đặt")

        system_prompt = build_batch_system_prompt(target_lang, glossary_hints)
        payload = [{"id": idx, "text": text} for idx, text in enumerate(texts)]
        url = f"{_API_BASE}/{self.model}:generateContent"
        body = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": json.dumps(payload, ensure_ascii=False)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
        }
        max_output_tokens = self.get_limits().max_output_tokens
        if max_output_tokens > 0:
            body["generationConfig"]["maxOutputTokens"] = max_output_tokens

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, params={"key": api_key}, json=body)

        if resp.status_code == 429:
            raise ProviderQuotaError(f"Gemini hết quota / vượt giới hạn tốc độ: {resp.text}")
        if resp.status_code >= 400:
            data = _safe_json(resp)
            message = (data.get("error") or {}).get("message", resp.text) if data else resp.text
            status = (data.get("error") or {}).get("status", "") if data else ""
            if status in ("RESOURCE_EXHAUSTED",):
                raise ProviderQuotaError(f"Gemini hết quota: {message}")
            raise RuntimeError(f"Gemini API lỗi ({resp.status_code}): {message}")

        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            block_reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise RuntimeError(f"Gemini không trả về kết quả (blockReason={block_reason})")

        parts = candidates[0].get("content", {}).get("parts", [])
        raw = "".join(p.get("text", "") for p in parts).strip()
        usage = data.get("usageMetadata", {})
        return BatchTranslationResult(
            texts=parse_batch_translations(raw, len(texts)),
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
        )


def _safe_json(resp: httpx.Response) -> dict | None:
    try:
        return resp.json()
    except ValueError:
        return None
