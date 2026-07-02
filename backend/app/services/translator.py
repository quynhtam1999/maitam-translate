"""Dịch danh sách đoạn: khử trùng lặp, ưu tiên cache, chỉ gọi API phần thiếu.

Ghi cache NGAY sau mỗi đoạn dịch xong -> đây là điều làm cho 'resume' khả thi (A3):
hết quota/tắt máy giữa chừng thì phần đã dịch vẫn còn trong cache.
"""
from ..models.glossary import GlossaryEntry
from .cache import SegmentCache
from .glossary import apply_glossary_post, apply_glossary_pre
from .pdf_overlay import TextSegment
from ..providers.base import BaseProvider
from ..providers.quota_tracker import quota_tracker


class Translator:
    def __init__(
        self,
        provider: BaseProvider,
        cache: SegmentCache,
        glossary: list[GlossaryEntry] | None = None,
    ):
        self.provider = provider
        self.cache = cache
        self.glossary = glossary or []

    async def translate_one(self, text: str, target_lang: str = "vi") -> str:
        """Dịch một đoạn (dùng cho tab văn bản dán tay và cho từng segment)."""
        cached = self.cache.get(text, target_lang)
        if cached is not None:
            return cached

        prepared = apply_glossary_pre(text, self.glossary)
        result = await self.provider.translate(prepared, target_lang, self.glossary)
        # Ghi lại token thật để đếm quota cục bộ (A6b).
        quota_tracker.record(self.provider.name, result.input_tokens, result.output_tokens)

        final = apply_glossary_post(result.text, self.glossary)
        self.cache.set(text, target_lang, final, provider_used=self.provider.name)
        return final

    async def translate_segments(
        self,
        segments: list[TextSegment],
        target_lang: str = "vi",
        on_progress=None,
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
        total = len(unique_texts)
        done = 0
        for text in unique_texts:
            text_to_translation[text] = await self.translate_one(text, target_lang)
            done += 1
            if on_progress:
                on_progress(done, total)

        return {seg.block_id: text_to_translation.get(seg.text, seg.text) for seg in segments}
