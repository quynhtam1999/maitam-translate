"""Điều phối dịch một file PDF giữ bố cục: mở -> bóc đoạn -> dịch (cache) -> overlay -> lưu.

Hàm này chạy trong tác vụ nền (job_runner). Cập nhật tiến trình vào job_store để frontend
poll được. Hết quota giữa chừng -> đặt job = paused_quota (KHÔNG failed), giữ cache đã ghi,
cho phép resume (đổi provider rồi dịch tiếp nhờ cache).

`input_key`/`output_key` là storage key (xem `services/storage.py`), không phải đường dẫn
đĩa trực tiếp — cho phép chạy trên object storage khi deploy.
"""
import tempfile
from pathlib import Path

from ..core import job_store
from ..models.job import JobProgress, JobStatus
from ..providers.base import ProviderQuotaError
from ..providers.registry import get_provider
from . import storage
from .cache import SegmentCache
from .glossary import load_glossary_bytes
from .pdf_overlay import collect_segments, overlay_translate
from .translator import Translator

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore


async def translate_pdf(
    job_id: str,
    user_id: str,
    input_key: str,
    output_key: str,
    provider_name: str,
    target_lang: str = "vi",
    force_retranslate: bool = False,
    api_key: str | None = None,
    provider_options: dict | None = None,
) -> None:
    cache = SegmentCache(user_id=user_id)
    glossary_bytes = storage.get_bytes(f"glossary/{user_id}/glossary.csv")
    glossary = load_glossary_bytes(glossary_bytes) if glossary_bytes else []

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

        # Toàn bộ vòng đời `doc` nằm trong `local_copy` — với S3Storage, file tạm chỉ tồn
        # tại đến khi khối này thoát, nên phải mở/dịch/lưu xong (doc.close()) trước đó.
        with storage.local_copy(input_key) as tmp_in:
            doc = fitz.open(str(tmp_in))
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
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_out_file:
                tmp_out_path = Path(tmp_out_file.name)
            doc.save(str(tmp_out_path))
            doc.close()

        try:
            storage.upload_file(output_key, tmp_out_path)
        finally:
            tmp_out_path.unlink(missing_ok=True)

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
