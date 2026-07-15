"""Giao diện trừu tượng cho nhà cung cấp dịch (multi-provider).

Mọi provider (Gemini, Gemma, Qwen...) đều hiện thực interface này, nên router/service
không bao giờ import trực tiếp một provider cụ thể — luôn qua registry.get_provider().
"""
from abc import ABC, abstractmethod
from typing import Callable
import json
import re

from pydantic import BaseModel

from ..models.glossary import GlossaryEntry

#: Callback báo tiến trình khi stream batch: nhận số đoạn đã dịch xong trong batch.
ProgressCallback = Callable[[int], None]


class RateLimits(BaseModel):
    rpm: int
    tpm: int
    rpd: int
    max_output_tokens: int = 0


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


class ProviderBatchError(RuntimeError):
    """Batch hỏng nhưng CÓ THỂ cứu được bằng cách chia đôi và dịch lại.

    Gồm: JSON cắt dở/không parse được, thiếu mảng translations, sai số lượng đoạn.
    Translator bắt lỗi này để chia nhỏ batch — KHÁC với ProviderQuotaError (phải
    dừng job) và các RuntimeError khác (lỗi cấu hình/API, chia nhỏ không giúp gì).
    """


class ProviderTruncatedError(ProviderBatchError):
    """Phản hồi về KHÔNG đầy đủ: stream đứt ngang, vượt maxOutputTokens, hoặc bị chặn.

    Tách riêng khỏi ProviderBatchError để phân biệt "dữ liệu về thiếu" với "dữ liệu về
    đủ nhưng sai cấu trúc" — hai ca này có nguyên nhân và cách xử lý khác hẳn nhau.
    """


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
        progress_cb: ProgressCallback | None = None,
    ) -> BatchTranslationResult:
        """Dịch nhiều đoạn trong MỘT request để giảm RPD.

        `progress_cb`: nếu truyền vào, provider stream phản hồi và gọi
        `progress_cb(so_doan_da_xong)` khi từng đoạn dịch xong — cho tiến trình
        real-time mà KHÔNG tăng số request.
        """
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
        # JSON mở ngoặc nhưng không đóng => phản hồi bị cắt giữa chừng. Thường là do
        # stream SSE đứt ngang (đo được: xảy ra rải rác, dữ liệu về một phần mà không
        # báo lỗi), ít khi do vượt maxOutputTokens — trường hợp đó finishReason đã bắt.
        if _looks_truncated(raw):
            raise ProviderTruncatedError(
                "Provider trả JSON bị cắt giữa chừng cho batch dịch "
                f"(nhận {len(raw)} ký tự cho {expected_count} đoạn) — "
                "phản hồi đứt giữa chừng, sẽ chia nhỏ batch và thử lại"
            )
        raise ProviderBatchError(
            f"Provider không trả JSON hợp lệ cho batch dịch (đầu phản hồi: {raw[:200]!r})"
        )

    items = data.get("translations") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ProviderBatchError("JSON batch dịch thiếu mảng translations")

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
        raise ProviderBatchError("JSON batch dịch có định dạng phần tử không hợp lệ")

    if len(texts) != expected_count:
        raise ProviderBatchError(
            f"Provider trả {len(texts)} bản dịch, nhưng batch cần {expected_count} đoạn"
        )
    return texts


def _load_json(text: str):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _looks_truncated(raw: str) -> bool:
    """Phản hồi có mở ngoặc JSON nhưng chưa đóng hết -> bị cắt giữa chừng."""
    if not raw:
        return False
    depth = 0
    in_string = False
    escaped = False
    for ch in raw:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
    return in_string or depth > 0


def count_streamed_json_items(buffer: str) -> int:
    """Đếm số object đã đóng hoàn chỉnh nằm trực tiếp trong một mảng JSON.

    Dùng cho phản hồi stream dạng {"translations":[{...},{...}]} hoặc [{...},...]:
    mỗi object là một đoạn dịch. Bỏ qua ký tự trong chuỗi (kể cả '{' '}' escape),
    nên con số phản ánh đúng số đoạn ĐÃ dịch xong tính đến thời điểm hiện tại.
    """
    count = 0
    stack: list[str] = []
    in_string = False
    escaped = False
    for ch in buffer:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
                if stack and stack[-1] == "[":  # object là phần tử của mảng -> 1 đoạn xong
                    count += 1
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
    return count
