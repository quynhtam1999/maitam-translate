"""Provider Google AI Studio (Gemini / Gemma) — gọi generativelanguage API qua httpx."""
import asyncio
import json

import httpx

from ..core.config import get_settings
from ..models.glossary import GlossaryEntry
from .base import (
    BaseProvider,
    BatchTranslationResult,
    ProgressCallback,
    ProviderQuotaError,
    RateLimits,
    TranslationResult,
    count_streamed_json_items,
    parse_batch_translations,
)
from .prompt import build_batch_system_prompt, build_system_prompt

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_RETRY_DELAYS_SECONDS = (1.0, 3.0, 8.0)
_TRANSIENT_STATUS_CODES = {500, 502, 503, 504}


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
        return True

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
        if not api_key:
            raise RuntimeError("Chưa có API key cho Gemini/Gemma 4 31B — nhập trong ⚙ Cài đặt")

        system_prompt = build_system_prompt(target_lang, glossary_hints)
        url = f"{_API_BASE}/{self.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {"temperature": 0.2},
        }
        max_output_tokens = self.get_limits().max_output_tokens
        if max_output_tokens > 0:
            body["generationConfig"]["maxOutputTokens"] = max_output_tokens

        resp = await _post_generate_content(url, api_key, body, timeout=60.0)
        _raise_for_error(resp, self.display_name)

        data = resp.json()
        translated = _extract_candidate_text(data, self.display_name)

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
        progress_cb: ProgressCallback | None = None,
    ) -> BatchTranslationResult:
        if not texts:
            return BatchTranslationResult(texts=[])

        if not api_key:
            raise RuntimeError("Chưa có API key cho Gemini/Gemma 4 31B — nhập trong ⚙ Cài đặt")

        system_prompt = build_batch_system_prompt(target_lang, glossary_hints)
        payload = [{"id": idx, "text": text} for idx, text in enumerate(texts)]
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": json.dumps(payload, ensure_ascii=False)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        max_output_tokens = self.get_limits().max_output_tokens
        if max_output_tokens > 0:
            body["generationConfig"]["maxOutputTokens"] = max_output_tokens

        # Cùng MỘT request; chỉ khác là stream để đếm số đoạn xong -> tiến trình real-time.
        if progress_cb is not None:
            raw, usage = await self._stream_batch(api_key, body, progress_cb)
        else:
            resp = await _post_generate_content(
                f"{_API_BASE}/{self.model}:generateContent", api_key, body, timeout=120.0
            )
            _raise_for_error(resp, self.display_name)
            data = resp.json()
            raw = _extract_candidate_text(data, self.display_name)
            usage = data.get("usageMetadata", {})

        return BatchTranslationResult(
            texts=parse_batch_translations(raw, len(texts)),
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
        )

    async def _stream_batch(
        self, api_key: str, body: dict, progress_cb: ProgressCallback
    ) -> tuple[str, dict]:
        """Gọi streamGenerateContent (SSE), gộp text và báo tiến trình theo số đoạn xong.

        Nếu stream trả về rỗng bất thường -> lùi về generateContent thường (1 request).
        """
        url = f"{_API_BASE}/{self.model}:streamGenerateContent"
        raw, usage, resp = await _stream_generate_content(
            url, api_key, body, timeout=180.0, progress_cb=progress_cb
        )
        _raise_for_error(resp, self.display_name)
        if not raw:
            resp = await _post_generate_content(
                f"{_API_BASE}/{self.model}:generateContent", api_key, body, timeout=120.0
            )
            _raise_for_error(resp, self.display_name)
            data = resp.json()
            raw = _extract_candidate_text(data, self.display_name)
            usage = data.get("usageMetadata", {})
        return raw, usage


async def _stream_generate_content(
    url: str,
    api_key: str,
    body: dict,
    timeout: float,
    progress_cb: ProgressCallback,
) -> tuple[str, dict, httpx.Response]:
    """Stream SSE từ streamGenerateContent.

    Trả về (text_đầy_đủ, usageMetadata, response). Gọi progress_cb theo số object
    JSON đã đóng. Retry khi lỗi tạm thời/đứt kết nối lúc THIẾT LẬP stream (chưa nhận
    dữ liệu) — không tăng request trong trường hợp thành công.
    """
    params = {"key": api_key, "alt": "sse"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(len(_RETRY_DELAYS_SECONDS) + 1):
            pieces: list[str] = []
            usage: dict = {}
            try:
                async with client.stream("POST", url, params=params, json=body) as resp:
                    if resp.status_code >= 400:
                        await resp.aread()
                        if (
                            resp.status_code in _TRANSIENT_STATUS_CODES
                            and attempt < len(_RETRY_DELAYS_SECONDS)
                        ):
                            await asyncio.sleep(_retry_delay_seconds(resp, attempt))
                            continue
                        return "", {}, resp

                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(data_str)
                        except ValueError:
                            continue
                        piece = _chunk_text(chunk)
                        if piece:
                            pieces.append(piece)
                            progress_cb(count_streamed_json_items("".join(pieces)))
                        meta = chunk.get("usageMetadata")
                        if isinstance(meta, dict):
                            usage = meta
                    return "".join(pieces), usage, resp
            except httpx.TransportError as exc:
                if attempt >= len(_RETRY_DELAYS_SECONDS):
                    raise RuntimeError(
                        f"Không kết nối được Google AI Studio API sau {attempt + 1} lần thử: {exc}"
                    ) from exc
                await asyncio.sleep(_RETRY_DELAYS_SECONDS[attempt])

    raise RuntimeError("Không nhận được phản hồi từ Google AI Studio API")


def _chunk_text(chunk: dict) -> str:
    candidates = chunk.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))


async def _post_generate_content(
    url: str, api_key: str, body: dict, timeout: float
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(len(_RETRY_DELAYS_SECONDS) + 1):
            try:
                resp = await client.post(url, params={"key": api_key}, json=body)
            except httpx.TransportError as exc:
                if attempt >= len(_RETRY_DELAYS_SECONDS):
                    raise RuntimeError(
                        f"Không kết nối được Google AI Studio API sau {attempt + 1} lần thử: {exc}"
                    ) from exc
                await asyncio.sleep(_RETRY_DELAYS_SECONDS[attempt])
                continue

            if (
                resp.status_code not in _TRANSIENT_STATUS_CODES
                or attempt >= len(_RETRY_DELAYS_SECONDS)
            ):
                return resp

            await asyncio.sleep(_retry_delay_seconds(resp, attempt))

    raise RuntimeError("Không nhận được phản hồi từ Google AI Studio API")


def _retry_delay_seconds(resp: httpx.Response, attempt: int) -> float:
    retry_after = resp.headers.get("retry-after")
    if retry_after:
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            pass
    return _RETRY_DELAYS_SECONDS[attempt]


def _raise_for_error(resp: httpx.Response, provider_label: str) -> None:
    if resp.status_code == 429:
        raise ProviderQuotaError(
            f"{provider_label} hết quota / vượt giới hạn tốc độ: {resp.text}"
        )
    if resp.status_code < 400:
        return

    data = _safe_json(resp)
    error = data.get("error") if isinstance(data, dict) else None
    message = error.get("message", resp.text) if isinstance(error, dict) else resp.text
    status = error.get("status", "") if isinstance(error, dict) else ""
    if status == "RESOURCE_EXHAUSTED":
        raise ProviderQuotaError(f"{provider_label} hết quota: {message}")
    if resp.status_code in _TRANSIENT_STATUS_CODES:
        raise RuntimeError(
            f"{provider_label} API tạm quá tải ({resp.status_code}) sau "
            f"{len(_RETRY_DELAYS_SECONDS) + 1} lần thử: {message}"
        )
    raise RuntimeError(f"{provider_label} API lỗi ({resp.status_code}): {message}")


def _extract_candidate_text(data: dict, provider_label: str) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        block_reason = (data.get("promptFeedback") or {}).get("blockReason")
        raise RuntimeError(
            f"{provider_label} không trả về kết quả (blockReason={block_reason})"
        )

    candidate = candidates[0]
    parts = candidate.get("content", {}).get("parts", [])
    text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()
    if not text:
        finish_reason = candidate.get("finishReason")
        raise RuntimeError(
            f"{provider_label} không trả về nội dung dịch (finishReason={finish_reason})"
        )
    return text


def _safe_json(resp: httpx.Response) -> dict | None:
    try:
        return resp.json()
    except ValueError:
        return None
