"""Entrypoint chạy nền cho một job dịch PDF.

Pipeline tự đưa các bước đồng bộ nặng sang worker thread để không chặn web server.
TODO: khi cần chạy song song / bền hơn, chuyển sang hàng đợi thật (arq / Celery / RQ).
"""
from .pipeline import translate_pdf


async def run_pdf_job(
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
    await translate_pdf(
        job_id=job_id,
        user_id=user_id,
        input_key=input_key,
        output_key=output_key,
        provider_name=provider_name,
        target_lang=target_lang,
        force_retranslate=force_retranslate,
        api_key=api_key,
        provider_options=provider_options,
    )
