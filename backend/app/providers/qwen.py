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
        return RateLimits(
            rpm=s.qwen_rpm_limit,
            tpm=s.qwen_tpm_limit,
            rpd=s.qwen_rpd_limit,
            max_output_tokens=s.qwen_max_tokens_per_request,
        )

    async def translate(
        self,
        text: str,
        target_lang: str = "vi",
        glossary_hints: list[GlossaryEntry] | None = None,
        api_key: str | None = None,
        provider_options: dict | None = None,
    ) -> TranslationResult:
        settings = get_settings()
        key = api_key or settings.qwen_api_key
        if not key:
            raise RuntimeError("Chưa có API key cho Qwen — nhập trong ⚙ Cài đặt")

        system_prompt = build_system_prompt(target_lang, glossary_hints)
        base_url = (provider_options or {}).get("qwen_base_url") or settings.qwen_base_url
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
        }
        max_output_tokens = self.get_limits().max_output_tokens
        if max_output_tokens > 0:
            body["max_tokens"] = max_output_tokens

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=body)

        if resp.status_code == 429:
            raise ProviderQuotaError(
                f"Qwen/ModelScope hết quota / vượt giới hạn tốc độ: {resp.text}"
            )
        if resp.status_code >= 400:
            data = _safe_json(resp)
            message = _error_message(data) if data else resp.text
            raise RuntimeError(f"Qwen API lỗi ({resp.status_code}): {message}")

        data = resp.json()
        provider_error = _provider_error_message(data)
        if provider_error:
            raise RuntimeError(f"Qwen API lỗi: {provider_error}")

        translated = _extract_response_text(data)
        if not translated:
            raise RuntimeError(f"Qwen không trả về kết quả hợp lệ (keys={_top_level_keys(data)})")

        usage = _extract_usage(data)
        return TranslationResult(
            text=translated,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
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

        settings = get_settings()
        key = api_key or settings.qwen_api_key
        if not key:
            raise RuntimeError("Chưa có API key cho Qwen — nhập trong ⚙ Cài đặt")

        system_prompt = build_batch_system_prompt(target_lang, glossary_hints)
        payload = [{"id": idx, "text": text} for idx, text in enumerate(texts)]
        base_url = (provider_options or {}).get("qwen_base_url") or settings.qwen_base_url
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0.1,
        }
        max_output_tokens = self.get_limits().max_output_tokens
        if max_output_tokens > 0:
            body["max_tokens"] = max_output_tokens

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=body)

        if resp.status_code == 429:
            raise ProviderQuotaError(
                f"Qwen/ModelScope hết quota / vượt giới hạn tốc độ: {resp.text}"
            )
        if resp.status_code >= 400:
            data = _safe_json(resp)
            message = _error_message(data) if data else resp.text
            raise RuntimeError(f"Qwen API lỗi ({resp.status_code}): {message}")

        data = resp.json()
        provider_error = _provider_error_message(data)
        if provider_error:
            raise RuntimeError(f"Qwen API lỗi: {provider_error}")

        raw = _extract_response_text(data)
        if not raw:
            raise RuntimeError(
                f"Qwen không trả về kết quả hợp lệ (keys={_top_level_keys(data)})"
            )

        usage = _extract_usage(data)
        return BatchTranslationResult(
            texts=parse_batch_translations(raw, len(texts)),
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
        )


def _error_message(data: dict) -> str:
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error.get("msg") or error)
    if isinstance(error, str):
        return error
    return str(data.get("message") or data.get("msg") or data)


def _provider_error_message(data: dict) -> str:
    error = data.get("error")
    if error:
        return _error_message(data)

    code = data.get("code")
    if code in (None, 0, "0", 200, "200", "success", "Success", "OK", "ok"):
        return ""
    return str(data.get("message") or data.get("msg") or code)


def _extract_response_text(data: dict) -> str:
    for choice in _iter_choices(data):
        text = _text_from_choice(choice)
        if text:
            return text

    for container in _iter_containers(data):
        for key in ("output_text", "generated_text", "text", "content", "response", "answer"):
            text = _text_from_value(container.get(key))
            if text:
                return text

    return ""


def _iter_choices(data: dict):
    for container in _iter_containers(data):
        choices = container.get("choices")
        if isinstance(choices, list):
            yield from choices


def _iter_containers(data: dict):
    yield data
    for key in ("data", "output", "result"):
        value = data.get(key)
        if isinstance(value, dict):
            yield value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield item


def _text_from_choice(choice: object) -> str:
    if not isinstance(choice, dict):
        return ""
    for key in ("message", "delta"):
        text = _text_from_value(choice.get(key))
        if text:
            return text
    for key in ("text", "content", "output_text", "generated_text"):
        text = _text_from_value(choice.get(key))
        if text:
            return text
    return ""


def _text_from_value(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "".join(_text_from_value(item) for item in value).strip()
    if not isinstance(value, dict):
        return ""

    for key in ("content", "text", "output_text", "generated_text", "response", "answer"):
        text = _text_from_value(value.get(key))
        if text:
            return text
    return _text_from_value(value.get("parts"))


def _extract_usage(data: dict) -> dict[str, int]:
    usage = {}
    for container in _iter_containers(data):
        candidate = container.get("usage")
        if isinstance(candidate, dict):
            usage = candidate
            break

    return {
        "input_tokens": _int_from_keys(
            usage, ("prompt_tokens", "input_tokens", "promptTokens", "inputTokens")
        ),
        "output_tokens": _int_from_keys(
            usage, ("completion_tokens", "output_tokens", "completionTokens", "outputTokens")
        ),
    }


def _int_from_keys(data: dict, keys: tuple[str, ...]) -> int:
    for key in keys:
        value = data.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def _top_level_keys(data: object) -> list[str]:
    if not isinstance(data, dict):
        return []
    return sorted(str(key) for key in data.keys())


def _safe_json(resp: httpx.Response) -> dict | None:
    try:
        return resp.json()
    except ValueError:
        return None
