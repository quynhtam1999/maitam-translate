"""Entrypoint chạy nền cho một job dịch PDF.

Bản scaffold dùng FastAPI BackgroundTasks (đủ cho 1 tiến trình, xử lý tuần tự).
TODO: khi cần chạy song song / bền hơn, chuyển sang hàng đợi thật (arq / Celery / RQ).
"""
from pathlib import Path

from .pipeline import translate_pdf


async def run_pdf_job(
    job_id: str,
    input_path: str,
    output_path: str,
    provider_name: str,
    target_lang: str = "vi",
    force_retranslate: bool = False,
) -> None:
    await translate_pdf(
        job_id=job_id,
        input_path=Path(input_path),
        output_path=Path(output_path),
        provider_name=provider_name,
        target_lang=target_lang,
        force_retranslate=force_retranslate,
    )
