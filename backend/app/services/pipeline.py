"""Điều phối dịch một file PDF giữ bố cục: mở -> bóc đoạn -> dịch (cache) -> overlay -> lưu.

Hàm này chạy trong tác vụ nền (job_runner). Cập nhật tiến trình vào job_store để frontend
poll được. Hết quota giữa chừng -> đặt job = paused_quota (KHÔNG failed), giữ cache đã ghi,
cho phép resume (đổi provider rồi dịch tiếp nhờ cache).
"""
from pathlib import Path

from ..core import job_store
from ..core.config import get_settings
from ..models.job import JobProgress, JobStatus
from ..providers.base import ProviderQuotaError
from ..providers.registry import get_provider
from .cache import SegmentCache
from .glossary import load_glossary
from .pdf_overlay import collect_segments, overlay_translate
from .translator import Translator

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore


async def translate_pdf(
    job_id: str,
    user_id: str,
    input_path: Path,
    output_path: Path,
    provider_name: str,
    target_lang: str = "vi",
    force_retranslate: bool = False,
    api_key: str | None = None,
    provider_options: dict | None = None,
) -> None:
    settings = get_settings()
    cache = SegmentCache(settings.cache_dir / "segments.db", user_id=user_id)
    glossary = load_glossary(settings.glossary_dir / user_id / "glossary.csv")

    try:
        job_store.update_job(job_id, status=JobStatus.RUNNING, provider=provider_name)

        if fitz is None:
            raise RuntimeError("Chưa cài PyMuPDF (pip install pymupdf)")

        provider = get_provider(provider_name)
        translator = Translator(
            provider,
            cache,
            glossary,
            quota_scope=user_id,
            provider_options=provider_options,
        )

        # Giai đoạn 1: bóc tách cấu trúc PDF (báo ngay để frontend hiện "đang dựng cấu trúc").
        progress = JobProgress(phase="extracting")
        job_store.update_job(job_id, progress=progress)

        doc = fitz.open(str(input_path))
        segments = collect_segments(doc)  # TODO: đã stub

        # Giai đoạn 2: dịch — cập nhật tiến độ theo từng batch (real-time).
        progress.phase = "translating"
        progress.segments_total = _count_unique_segment_texts(segments)
        progress.pages_total = doc.page_count
        job_store.update_job(job_id, progress=progress)

        def on_progress(done: int, total: int) -> None:
            progress.phase = "translating"
            progress.segments_total = total
            progress.segments_translated = done
            job_store.update_job(job_id, progress=progress)

        translations = await translator.translate_segments(
            segments,
            target_lang=target_lang,
            on_progress=on_progress,
            api_key=api_key,
            force_retranslate=force_retranslate,
        )

        # Giai đoạn 3: chèn bản dịch vào PDF và lưu file.
        progress.phase = "rendering"
        progress.segments_translated = progress.segments_total
        job_store.update_job(job_id, progress=progress)

        overlay_translate(doc, segments, translations)  # TODO: đã stub
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))
        doc.close()

        progress.phase = "done"
        progress.segments_translated = progress.segments_total
        job_store.update_job(job_id, status=JobStatus.DONE, progress=progress)

    except ProviderQuotaError as e:
        # Hết quota — cho phép dịch tiếp sau (A4). Phần đã dịch đã nằm trong cache.
        job_store.update_job(job_id, status=JobStatus.PAUSED_QUOTA, error=str(e))
    except Exception as e:  # noqa: BLE001
        job_store.update_job(job_id, status=JobStatus.FAILED, error=str(e))


def _count_unique_segment_texts(segments) -> int:
    return len({seg.text for seg in segments if seg.text.strip()})
