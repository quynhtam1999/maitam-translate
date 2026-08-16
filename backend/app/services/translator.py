"""Dịch danh sách đoạn: khử trùng lặp, ưu tiên cache, chỉ gọi API phần thiếu.

Ghi cache NGAY sau mỗi đoạn dịch xong -> đây là điều làm cho 'resume' khả thi (A3):
hết quota/tắt máy giữa chừng thì phần đã dịch vẫn còn trong cache.
"""
import asyncio
import math
from dataclasses import dataclass

from ..models.glossary import GlossaryEntry
from .cache import SegmentCache
from .glossary import apply_glossary_post, apply_glossary_pre
from .layout import Block
from ..providers.base import BaseProvider, ProviderBatchError, ProviderQuotaError
from ..providers.quota_tracker import quota_tracker

# Trần số đoạn/batch. KHÔNG phải vì trần token (batch cả tài liệu vẫn thừa chỗ token) —
# mà vì stream SSE càng dài càng dễ đứt ngang: đo trên tài liệu 738 đoạn (2026-07-15),
#   không trần -> 738 đoạn/1 request: đứt ở 702/738, chia đôi 2 lần, TỔNG 5 request/294s
#   trần 200   -> 4 request/124s, không lần nào phải chia đôi
# Tức trần 200 vừa ÍT request hơn (tốt cho RPD) vừa nhanh gấp đôi. Tiến trình real-time
# vẫn đến từ STREAM phản hồi, không phải từ việc chia nhỏ batch.
_MAX_BATCH_ITEMS = 200
_INPUT_BATCH_HEADROOM = 0.8
_OUTPUT_BATCH_HEADROOM = 0.9
_SINGLE_PROMPT_TOKEN_OVERHEAD = 256
_BATCH_PROMPT_TOKEN_OVERHEAD = 512
_JSON_ITEM_TOKEN_OVERHEAD = 16
_OUTPUT_ITEM_TOKEN_OVERHEAD = 16
#: Đo trên tài liệu y khoa Anh->Việt: token đầu ra / token nguồn thật sự là 1.07-1.25
#: (batch 100 đoạn: 7520 token ra / 4739 token nguồn). 1.3 là mức có đệm nhẹ.
_OUTPUT_EXPANSION_FACTOR = 1.3


@dataclass(frozen=True)
class _PendingTranslation:
    original: str
    prepared: str
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class Translator:
    def __init__(
        self,
        provider: BaseProvider,
        cache: SegmentCache,
        glossary: list[GlossaryEntry] | None = None,
        quota_scope: str | None = None,
        provider_options: dict | None = None,
    ):
        self.provider = provider
        self.cache = cache
        self.glossary = glossary or []
        self.quota_scope = quota_scope
        self.provider_options = provider_options or {}

    async def translate_one(
        self,
        text: str,
        target_lang: str = "vi",
        api_key: str | None = None,
        force_retranslate: bool = False,
    ) -> str:
        """Dịch một đoạn (dùng cho tab văn bản dán tay và cho từng segment)."""
        if not force_retranslate:
            cached = self.cache.get(text, target_lang)
            if cached is not None:
                return cached

        prepared = apply_glossary_pre(text, self.glossary)
        estimated_tokens = _estimate_total_tokens(prepared)
        await self._wait_for_quota_window(estimated_tokens)
        result = await self.provider.translate(
            prepared,
            target_lang,
            self.glossary,
            api_key=api_key,
            provider_options=self.provider_options,
        )
        # Ghi lại token thật để đếm quota cục bộ (A6b).
        input_tokens = result.input_tokens
        output_tokens = result.output_tokens
        if input_tokens + output_tokens <= 0:
            input_tokens = estimated_tokens
        quota_tracker.record(
            self.provider.name, input_tokens, output_tokens, scope=self.quota_scope
        )

        final = apply_glossary_post(result.text, self.glossary)
        self.cache.set(text, target_lang, final, provider_used=self.provider.name)
        return final

    async def translate_units(
        self,
        units: list[Block],
        target_lang: str = "vi",
        on_progress=None,
        api_key: str | None = None,
        force_retranslate: bool = False,
    ) -> dict[str, str]:
        """Trả về ánh xạ block_id -> bản dịch.

        Đơn vị dịch là một KHỐI trọn vẹn do engine bố cục dựng ra (đoạn văn, tiêu đề, ô bảng,
        caption, nhãn hình) — không bao giờ là mảnh câu, nên bản dịch cũng không phải cắt lại.
        Cache đánh theo nội dung khối.

        Khử trùng lặp theo nội dung (nhiều khối cùng chữ chỉ dịch 1 lần), ưu tiên cache,
        gọi provider cho phần thiếu, ghi cache ngay. `on_progress(done, total)` gọi sau mỗi đoạn.
        """
        # gom các đoạn text duy nhất
        unique_texts: dict[str, None] = {}
        for unit in units:
            if unit.text.strip():
                unique_texts.setdefault(unit.text, None)

        text_to_translation: dict[str, str] = {}
        pending: list[_PendingTranslation] = []
        total = len(unique_texts)
        done = 0
        for text in unique_texts:
            if not force_retranslate:
                cached = self.cache.get(text, target_lang)
                if cached is not None:
                    text_to_translation[text] = cached
                    done += 1
                    if on_progress:
                        on_progress(done, total)
                    continue

            prepared = apply_glossary_pre(text, self.glossary)
            pending.append(
                _PendingTranslation(
                    original=text,
                    prepared=prepared,
                    input_tokens=_estimate_batch_input_tokens(prepared),
                    output_tokens=_estimate_output_tokens(prepared),
                )
            )

        for batch in self._make_batches(pending):
            translations = await self._translate_batch_with_split(
                batch, target_lang, api_key, on_progress, done, total
            )
            for item, translated in zip(batch, translations, strict=True):
                final = apply_glossary_post(translated, self.glossary)
                self.cache.set(item.original, target_lang, final, provider_used=self.provider.name)
                text_to_translation[item.original] = final
                done += 1
            if on_progress:
                on_progress(done, total)

        # Thiếu bản dịch (khối rỗng) -> giữ nguyên chữ gốc.
        return {unit.id: text_to_translation.get(unit.text, unit.text) for unit in units}

    async def _translate_batch_with_split(
        self,
        batch: list[_PendingTranslation],
        target_lang: str,
        api_key: str | None,
        on_progress,
        base_done: int,
        total: int,
    ) -> list[str]:
        """Dịch một batch; nếu phản hồi hỏng thì CHIA ĐÔI và dịch lại từng nửa.

        Phản hồi batch thỉnh thoảng hỏng vì lý do NGOÀI tầm kiểm soát của ta: đo thực
        tế thấy stream SSE của Google đôi khi đứt giữa chừng (~10-15%), trả về một
        phần dữ liệu mà KHÔNG báo lỗi và finishReason vẫn là STOP. Model cũng có thể
        trả thiếu/thừa số đoạn. Chia đôi cho phép job tự cứu (chỉ tốn thêm request khi
        thật sự hỏng) thay vì mất trắng cả tài liệu.

        Xuống còn 1 đoạn mà vẫn lỗi thì đoạn đó có vấn đề thật -> ném lỗi ra ngoài.
        """
        estimated_tokens = _estimate_batch_total_tokens(batch)
        await self._wait_for_quota_window(estimated_tokens)

        # Tiến trình real-time: provider stream phản hồi và gọi progress_cb với
        # số đoạn đã dịch xong TRONG batch này (không tốn thêm request/RPD).
        progress_cb = _make_batch_progress_cb(on_progress, base_done, len(batch), total)
        try:
            result = await self.provider.translate_batch(
                [item.prepared for item in batch],
                target_lang,
                self.glossary,
                api_key=api_key,
                provider_options=self.provider_options,
                progress_cb=progress_cb,
            )
        except ProviderBatchError:
            # Request hỏng vẫn TỐN quota thật -> phải ghi nhận, nếu không RPM/RPD bị
            # đếm thiếu và ta sẽ gọi vượt giới hạn thật của provider.
            quota_tracker.record(
                self.provider.name, estimated_tokens, 0, scope=self.quota_scope
            )
            if len(batch) == 1:
                raise
            mid = len(batch) // 2
            left = await self._translate_batch_with_split(
                batch[:mid], target_lang, api_key, on_progress, base_done, total
            )
            right = await self._translate_batch_with_split(
                batch[mid:], target_lang, api_key, on_progress, base_done + mid, total
            )
            return left + right

        input_tokens = result.input_tokens
        output_tokens = result.output_tokens
        if input_tokens + output_tokens <= 0:
            input_tokens = estimated_tokens
        quota_tracker.record(
            self.provider.name, input_tokens, output_tokens, scope=self.quota_scope
        )
        return result.texts

    def _make_batches(self, pending: list[_PendingTranslation]) -> list[list[_PendingTranslation]]:
        limits = self.provider.get_limits()
        input_budget = _batch_input_token_budget(limits.tpm)
        output_budget = _batch_output_token_budget(limits.max_output_tokens)
        batches: list[list[_PendingTranslation]] = []
        current: list[_PendingTranslation] = []
        current_input_tokens = _BATCH_PROMPT_TOKEN_OVERHEAD
        current_output_tokens = 0

        for item in pending:
            should_flush = (
                current
                and (
                    len(current) >= _MAX_BATCH_ITEMS
                    or _exceeds_budget(current_input_tokens, item.input_tokens, input_budget)
                    or _exceeds_budget(current_output_tokens, item.output_tokens, output_budget)
                )
            )
            if should_flush:
                batches.append(current)
                current = []
                current_input_tokens = _BATCH_PROMPT_TOKEN_OVERHEAD
                current_output_tokens = 0

            current.append(item)
            current_input_tokens += item.input_tokens
            current_output_tokens += item.output_tokens

        if current:
            batches.append(current)
        return batches

    async def _wait_for_quota_window(self, estimated_tokens: int) -> None:
        limits = self.provider.get_limits()

        while True:
            wait_seconds = quota_tracker.wait_seconds_until_ready(
                self.provider.name,
                limits.rpm,
                limits.tpm,
                limits.rpd,
                estimated_tokens=estimated_tokens,
                scope=self.quota_scope,
            )
            if wait_seconds is None:
                snapshot = quota_tracker.snapshot(
                    self.provider.name,
                    limits.rpm,
                    limits.tpm,
                    limits.rpd,
                    scope=self.quota_scope,
                )
                raise ProviderQuotaError(
                    "Đã hết giới hạn ngày (RPD) của model "
                    f"{self.provider.display_name} ({snapshot.rpd_used}/{snapshot.rpd_limit} yêu cầu). "
                    "Phần mềm đã ngưng dịch; vui lòng chờ ngày reset hoặc đổi model/API key để dịch tiếp."
                )
            if wait_seconds <= 0:
                return
            await asyncio.sleep(wait_seconds)


def _make_batch_progress_cb(on_progress, base_done: int, batch_len: int, total: int):
    """Bọc callback stream: nhận số đoạn xong trong batch -> báo tiến trình toàn cục.

    Chỉ báo khi số đếm tăng và không vượt quá kích thước batch (số đếm từ JSON
    đang stream chỉ là ước lượng; con số chính xác được chốt lại sau khi batch xong).
    """
    if on_progress is None:
        return None

    last_reported = 0

    def cb(items_done_in_batch: int) -> None:
        nonlocal last_reported
        capped = max(0, min(items_done_in_batch, batch_len))
        if capped <= last_reported:
            return
        last_reported = capped
        on_progress(min(base_done + capped, total), total)

    return cb


def _estimate_total_tokens(text: str) -> int:
    """Rough local estimate for TPM gating before the provider returns real usage."""
    return _estimate_input_tokens(text) + _estimate_output_tokens(text)


def _estimate_batch_total_tokens(batch: list[_PendingTranslation]) -> int:
    return _BATCH_PROMPT_TOKEN_OVERHEAD + sum(item.total_tokens for item in batch)


def _estimate_input_tokens(text: str) -> int:
    return math.ceil(_estimate_source_tokens(text) + _SINGLE_PROMPT_TOKEN_OVERHEAD)


def _estimate_batch_input_tokens(text: str) -> int:
    return math.ceil(_estimate_source_tokens(text) + _JSON_ITEM_TOKEN_OVERHEAD)


def _estimate_output_tokens(text: str) -> int:
    return math.ceil(_estimate_source_tokens(text) * _OUTPUT_EXPANSION_FACTOR + _OUTPUT_ITEM_TOKEN_OVERHEAD)


def _estimate_source_tokens(text: str) -> float:
    return max(len(text) / 4, len(text.split()) * 1.3, 1)


def _batch_input_token_budget(tpm_limit: int) -> int | None:
    if tpm_limit <= 0:
        return None
    return max(1, math.floor(tpm_limit * _INPUT_BATCH_HEADROOM))


def _batch_output_token_budget(max_output_tokens: int) -> int | None:
    if max_output_tokens <= 0:
        return None
    return max(1, math.floor(max_output_tokens * _OUTPUT_BATCH_HEADROOM))


def _exceeds_budget(current_tokens: int, item_tokens: int, budget: int | None) -> bool:
    return budget is not None and current_tokens + item_tokens > budget
