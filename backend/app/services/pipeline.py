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
    input_path: Path,
    output_path: Path,
    provider_name: str,
    target_lang: str = "vi",
    force_retranslate: bool = False,
) -> None:
    settings = get_settings()
    cache = SegmentCache(settings.cache_dir / "segments.db")
    glossary = load_glossary(settings.glossary_dir / "glossary.csv")

    try:
        job_store.update_job(job_id, status=JobStatus.RUNNING, provider=provider_name)

        if fitz is None:
            raise RuntimeError("Chưa cài PyMuPDF (pip install pymupdf)")

        provider = get_provider(provider_name)
        translator = Translator(provider, cache, glossary)

        doc = fitz.open(str(input_path))
        segments = collect_segments(doc)  # TODO: đã stub

        progress = JobProgress(segments_total=len(segments), pages_total=doc.page_count)
        job_store.update_job(job_id, progress=progress)

        def on_progress(done: int, total: int) -> None:
            progress.segments_translated = done
            job_store.update_job(job_id, progress=progress)

        translations = await translator.translate_segments(
            segments, target_lang=target_lang, on_progress=on_progress
        )

        overlay_translate(doc, segments, translations)  # TODO: đã stub
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))
        doc.close()

        job_store.update_job(job_id, status=JobStatus.DONE, progress=progress)

    except ProviderQuotaError as e:
        # Hết quota — cho phép dịch tiếp sau (A4). Phần đã dịch đã nằm trong cache.
        job_store.update_job(job_id, status=JobStatus.PAUSED_QUOTA, error=str(e))
    except Exception as e:  # noqa: BLE001
        job_store.update_job(job_id, status=JobStatus.FAILED, error=str(e))
