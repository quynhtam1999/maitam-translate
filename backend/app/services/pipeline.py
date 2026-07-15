"""Điều phối dịch một file PDF giữ bố cục: mở -> bóc đoạn -> dịch (cache) -> overlay -> lưu.

Hàm này chạy trong tác vụ nền (job_runner). Cập nhật tiến trình vào job_store để frontend
poll được. Hết quota giữa chừng -> đặt job = paused_quota (KHÔNG failed), giữ cache đã ghi,
cho phép resume (đổi provider rồi dịch tiếp nhờ cache).

`input_key`/`output_key` là storage key (xem `services/storage.py`), không phải đường dẫn
đĩa trực tiếp — cho phép chạy trên object storage khi deploy.
"""
import asyncio
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.pool import StaticPool

from ..core import db as db_module, job_store
from ..models.job import JobProgress, JobStatus
from ..providers.base import ProviderQuotaError
from ..providers.registry import get_provider
from . import storage
from .cache import SegmentCache
from .glossary import load_glossary_bytes
from .pdf_overlay import collect_segments, overlay_translate
from .segment_merge import build_translation_units
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

    try:
        job_store.update_job(job_id, status=JobStatus.RUNNING, provider=provider_name)

        if fitz is None:
            raise RuntimeError("Chưa cài PyMuPDF (pip install pymupdf)")

        glossary_bytes = await asyncio.to_thread(
            storage.get_bytes, f"glossary/{user_id}/glossary.csv"
        )
        glossary = load_glossary_bytes(glossary_bytes) if glossary_bytes else []
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
        # tại đến khi khối này thoát, nên phải dựng file đầu ra xong trước đó.
        async with _async_local_copy(input_key) as tmp_in:
            # PyMuPDF là đồng bộ và có thể mất lâu với PDF nhiều bbox. Mở/đóng doc hoàn
            # toàn trong worker thread để poll status vẫn được phục vụ trên event loop.
            segments, page_count = await asyncio.to_thread(_extract_pdf, tmp_in)
            # Gộp các mảnh câu bị cắt ngang ở biên khối/cột/trang trước khi dịch; bản dịch
            # được cắt trả về đúng từng bbox trong translate_units.
            units = build_translation_units(segments)

            # Giai đoạn 2: dịch — cập nhật tiến độ theo từng batch (real-time).
            progress.phase = "translating"
            progress.segments_total = _count_unique_unit_texts(units)
            progress.pages_total = page_count
            job_store.update_job(job_id, progress=progress)

            def on_progress(done: int, total: int) -> None:
                progress.phase = "translating"
                progress.segments_total = total
                progress.segments_translated = done
                job_store.update_job(job_id, progress=progress)

            translations = await _translate_units_without_blocking(
                translator,
                units,
                target_lang,
                on_progress,
                api_key,
                force_retranslate,
            )

            # Giai đoạn 3: chèn bản dịch vào PDF và lưu file.
            progress.phase = "rendering"
            progress.segments_translated = progress.segments_total
            job_store.update_job(job_id, progress=progress)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_out_file:
                tmp_out_path = Path(tmp_out_file.name)
            try:
                await asyncio.to_thread(
                    _render_pdf, tmp_in, tmp_out_path, segments, translations
                )
                await asyncio.to_thread(storage.upload_file, output_key, tmp_out_path)
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


def _count_unique_unit_texts(units) -> int:
    return len({unit.text for unit in units if unit.text.strip()})


async def _translate_units_without_blocking(
    translator,
    units,
    target_lang: str,
    on_progress,
    api_key: str | None,
    force_retranslate: bool,
):
    """Chạy provider + cache DB ngoài event loop; giữ in-memory SQLite cùng thread."""
    args = (translator, units, target_lang, on_progress, api_key, force_retranslate)
    if isinstance(db_module.get_engine().pool, StaticPool):
        return await translator.translate_units(
            units,
            target_lang=target_lang,
            on_progress=on_progress,
            api_key=api_key,
            force_retranslate=force_retranslate,
        )
    return await asyncio.to_thread(_run_translate_units, *args)


def _run_translate_units(
    translator,
    units,
    target_lang: str,
    on_progress,
    api_key: str | None,
    force_retranslate: bool,
):
    return asyncio.run(
        translator.translate_units(
            units,
            target_lang=target_lang,
            on_progress=on_progress,
            api_key=api_key,
            force_retranslate=force_retranslate,
        )
    )


@asynccontextmanager
async def _async_local_copy(key: str):
    """Lấy/giải phóng file tạm storage trong worker để S3 không chặn event loop."""
    manager = storage.local_copy(key)
    local_path = await asyncio.to_thread(manager.__enter__)
    try:
        yield local_path
    except BaseException:
        exc_type, exc, traceback = sys.exc_info()
        suppressed = await asyncio.to_thread(manager.__exit__, exc_type, exc, traceback)
        if not suppressed:
            raise
    else:
        await asyncio.to_thread(manager.__exit__, None, None, None)


def _extract_pdf(input_path: Path):
    """Bóc segment trong worker; không truyền đối tượng fitz.Document qua thread."""
    doc = fitz.open(str(input_path))
    try:
        return collect_segments(doc), doc.page_count
    finally:
        doc.close()


def _render_pdf(
    input_path: Path,
    output_path: Path,
    segments,
    translations: dict[str, str],
) -> None:
    """Mở lại PDF và dựng kết quả hoàn toàn trong worker thread."""
    doc = fitz.open(str(input_path))
    try:
        overlay_translate(doc, segments, translations)
        doc.save(str(output_path))
    finally:
        doc.close()
