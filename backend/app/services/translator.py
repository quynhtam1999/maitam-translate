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
from .pdf_overlay import TextSegment
from ..providers.base import BaseProvider, ProviderQuotaError
from ..providers.quota_tracker import quota_tracker

_MAX_BATCH_ITEMS = 2000
_INPUT_BATCH_HEADROOM = 0.8
_OUTPUT_BATCH_HEADROOM = 0.9
_SINGLE_PROMPT_TOKEN_OVERHEAD = 256
_BATCH_PROMPT_TOKEN_OVERHEAD = 512
_JSON_ITEM_TOKEN_OVERHEAD = 16
_OUTPUT_ITEM_TOKEN_OVERHEAD = 16
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

    async def translate_one(self, text: str, target_lang: str = "vi", api_key: str | None = None) -> str:
        """Dịch một đoạn (dùng cho tab văn bản dán tay và cho từng segment)."""
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

    async def translate_segments(
        self,
        segments: list[TextSegment],
        target_lang: str = "vi",
        on_progress=None,
        api_key: str | None = None,
    ) -> dict[str, str]:
        """Trả về ánh xạ block_id -> bản dịch.

        Khử trùng lặp theo nội dung (nhiều block cùng chữ chỉ dịch 1 lần), ưu tiên cache,
        gọi provider cho phần thiếu, ghi cache ngay. `on_progress(done, total)` gọi sau mỗi đoạn.
        """
        # gom các đoạn text duy nhất
        unique_texts: dict[str, None] = {}
        for seg in segments:
            if seg.text.strip():
                unique_texts.setdefault(seg.text, None)

        text_to_translation: dict[str, str] = {}
        pending: list[_PendingTranslation] = []
        total = len(unique_texts)
        done = 0
        for text in unique_texts:
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
            originals = [item.original for item in batch]
            prepared_texts = [item.prepared for item in batch]
            estimated_tokens = _estimate_batch_total_tokens(batch)

            await self._wait_for_quota_window(estimated_tokens)
            result = await self.provider.translate_batch(
                prepared_texts,
                target_lang,
                self.glossary,
                api_key=api_key,
                provider_options=self.provider_options,
            )

            input_tokens = result.input_tokens
            output_tokens = result.output_tokens
            if input_tokens + output_tokens <= 0:
                input_tokens = estimated_tokens
            quota_tracker.record(
                self.provider.name, input_tokens, output_tokens, scope=self.quota_scope
            )

            for original, translated in zip(originals, result.texts, strict=True):
                final = apply_glossary_post(translated, self.glossary)
                self.cache.set(original, target_lang, final, provider_used=self.provider.name)
                text_to_translation[original] = final
                done += 1
                if on_progress:
                    on_progress(done, total)

        return {seg.block_id: text_to_translation.get(seg.text, seg.text) for seg in segments}

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
