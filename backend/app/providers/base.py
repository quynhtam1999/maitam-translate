"""Giao diện trừu tượng cho nhà cung cấp dịch (multi-provider).

Mọi provider (Gemini, Gemma, Qwen...) đều hiện thực interface này, nên router/service
không bao giờ import trực tiếp một provider cụ thể — luôn qua registry.get_provider().
"""
from abc import ABC, abstractmethod
import json
import re

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


class BatchTranslationResult(BaseModel):
    texts: list[str]
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
        api_key: str | None = None,
        provider_options: dict | None = None,
    ) -> TranslationResult:
        """Dịch một đoạn văn bản.

        `api_key`: nếu người dùng tự nhập key riêng ở trình duyệt (site public,
        mỗi người dùng key của họ), key này được ưu tiên hơn key cấu hình server.
        """
        raise NotImplementedError

    @abstractmethod
    async def translate_batch(
        self,
        texts: list[str],
        target_lang: str = "vi",
        glossary_hints: list[GlossaryEntry] | None = None,
        api_key: str | None = None,
        provider_options: dict | None = None,
    ) -> BatchTranslationResult:
        """Dịch nhiều đoạn trong một request để giảm RPD."""
        raise NotImplementedError

    @abstractmethod
    def get_limits(self) -> RateLimits:
        """Trả về giới hạn RPM/TPM/RPD (đọc từ cấu hình)."""
        raise NotImplementedError

    def is_configured(self) -> bool:
        """Provider đã có API key để dùng chưa."""
        return True


def parse_batch_translations(raw_text: str, expected_count: int) -> list[str]:
    """Parse strict JSON batch output, accepting common markdown-fence wrappers."""
    raw = raw_text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw).strip()

    data = _load_json(raw)
    if data is None:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            data = _load_json(raw[start : end + 1])
    if data is None:
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            data = _load_json(raw[start : end + 1])
    if data is None:
        raise RuntimeError("Provider không trả JSON hợp lệ cho batch dịch")

    items = data.get("translations") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise RuntimeError("JSON batch dịch thiếu mảng translations")

    if all(isinstance(item, str) for item in items):
        texts = [item.strip() for item in items]
    elif all(isinstance(item, dict) for item in items):
        indexed: list[tuple[int, str]] = []
        for idx, item in enumerate(items):
            item_id = item.get("id", idx)
            text = item.get("text", item.get("translation", ""))
            indexed.append((int(item_id), str(text).strip()))
        texts = [text for _, text in sorted(indexed, key=lambda pair: pair[0])]
    else:
        raise RuntimeError("JSON batch dịch có định dạng phần tử không hợp lệ")

    if len(texts) != expected_count:
        raise RuntimeError(
            f"Provider trả {len(texts)} bản dịch, nhưng batch cần {expected_count} đoạn"
        )
    return texts


def _load_json(text: str):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None
