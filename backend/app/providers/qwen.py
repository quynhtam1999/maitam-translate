"""Provider Qwen qua ModelScope (endpoint OpenAI-compatible)."""
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
        api_key: str | None = None,
    ) -> TranslationResult:
        settings = get_settings()
        key = api_key or settings.qwen_api_key
        if not key:
            raise RuntimeError("Chưa có API key cho Qwen — nhập trong ⚙ Cài đặt")

        system_prompt = build_system_prompt(target_lang, glossary_hints)
        url = f"{settings.qwen_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=body)

        if resp.status_code == 429:
            raise ProviderQuotaError(f"Qwen/ModelScope hết quota / vượt giới hạn tốc độ: {resp.text}")
        if resp.status_code >= 400:
            data = _safe_json(resp)
            message = (data.get("error") or {}).get("message", resp.text) if data else resp.text
            raise RuntimeError(f"Qwen API lỗi ({resp.status_code}): {message}")

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Qwen không trả về kết quả")

        translated = (choices[0].get("message") or {}).get("content", "").strip()
        usage = data.get("usage", {})
        return TranslationResult(
            text=translated,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    async def translate_batch(
        self,
        texts: list[str],
        target_lang: str = "vi",
        glossary_hints: list[GlossaryEntry] | None = None,
        api_key: str | None = None,
    ) -> BatchTranslationResult:
        if not texts:
            return BatchTranslationResult(texts=[])

        settings = get_settings()
        key = api_key or settings.qwen_api_key
        if not key:
            raise RuntimeError("Chưa có API key cho Qwen — nhập trong ⚙ Cài đặt")

        system_prompt = build_batch_system_prompt(target_lang, glossary_hints)
        payload = [{"id": idx, "text": text} for idx, text in enumerate(texts)]
        url = f"{settings.qwen_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0.1,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=body)

        if resp.status_code == 429:
            raise ProviderQuotaError(f"Qwen/ModelScope hết quota / vượt giới hạn tốc độ: {resp.text}")
        if resp.status_code >= 400:
            data = _safe_json(resp)
            message = (data.get("error") or {}).get("message", resp.text) if data else resp.text
            raise RuntimeError(f"Qwen API lỗi ({resp.status_code}): {message}")

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Qwen không trả về kết quả")

        raw = (choices[0].get("message") or {}).get("content", "").strip()
        usage = data.get("usage", {})
        return BatchTranslationResult(
            texts=parse_batch_translations(raw, len(texts)),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )


def _safe_json(resp: httpx.Response) -> dict | None:
    try:
        return resp.json()
    except ValueError:
        return None
