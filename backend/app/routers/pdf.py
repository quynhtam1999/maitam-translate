"""Endpoint dịch PDF theo mẫu job: tạo -> poll -> (resume) -> tải kết quả."""
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..core import job_store
from ..core.config import get_settings
from ..models.job import (
    JobCreateResponse,
    JobProgress,
    JobResumeRequest,
    JobStatus,
    JobStatusResponse,
)
from ..providers.quota_tracker import quota_tracker
from ..providers.registry import get_provider
from ..services.job_runner import run_pdf_job

router = APIRouter(prefix="/api/pdf", tags=["pdf"])


def _quota_for(provider_name: str | None):
    if not provider_name:
        return None
    try:
        limits = get_provider(provider_name).get_limits()
    except KeyError:
        return None
    return quota_tracker.snapshot(provider_name, limits.rpm, limits.tpm, limits.rpd)


def _to_status_response(job: dict) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=job["job_id"],
        status=JobStatus(job["status"]),
        progress=JobProgress(**job["progress"]),
        provider_used=job.get("provider"),
        target_lang=job.get("target_lang", "vi"),
        quota=_quota_for(job.get("provider")),
        error=job.get("error"),
    )


@router.post("/jobs", response_model=JobCreateResponse, status_code=202)
async def create_pdf_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    provider: str = Form(...),
    target_lang: str = Form("vi"),
    force_retranslate: bool = Form(False),
):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file PDF")
    try:
        get_provider(provider)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Provider không hợp lệ: {provider}")

    settings = get_settings()
    # tên file tạm sẽ đặt theo job_id sau khi tạo bản ghi
    job_id = job_store.create_job(
        input_path="", output_path="", original_name=file.filename or "document.pdf",
        provider=provider, target_lang=target_lang,
    )
    input_path = settings.uploads_dir / f"{job_id}.pdf"
    output_path = settings.outputs_dir / f"{job_id}_vi.pdf"
    input_path.write_bytes(await file.read())
    job_store.update_job(job_id, provider=provider)
    # cập nhật đường dẫn thật
    job_store._db().execute(  # noqa: SLF001 — cập nhật đường dẫn nội bộ
        "UPDATE jobs SET input_path = ?, output_path = ? WHERE job_id = ?",
        (str(input_path), str(output_path), job_id),
    )
    job_store._db().commit()  # noqa: SLF001

    background_tasks.add_task(
        run_pdf_job, job_id, str(input_path), str(output_path), provider, target_lang, force_retranslate
    )
    return JobCreateResponse(job_id=job_id, status=JobStatus.QUEUED)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_pdf_job(job_id: str):
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy job")
    return _to_status_response(job)


@router.post("/jobs/{job_id}/resume", response_model=JobCreateResponse, status_code=202)
async def resume_pdf_job(job_id: str, body: JobResumeRequest, background_tasks: BackgroundTasks):
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy job")

    provider = body.provider or job.get("provider")
    try:
        get_provider(provider)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Provider không hợp lệ: {provider}")

    job_store.update_job(job_id, status=JobStatus.QUEUED, provider=provider, error=None)
    background_tasks.add_task(
        run_pdf_job, job_id, job["input_path"], job["output_path"],
        provider, job.get("target_lang", "vi"), False,
    )
    return JobCreateResponse(job_id=job_id, status=JobStatus.QUEUED)


@router.get("/jobs/{job_id}/download")
async def download_pdf_job(job_id: str):
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy job")
    if job["status"] != JobStatus.DONE.value:
        raise HTTPException(status_code=409, detail="Job chưa hoàn tất")

    output_path = Path(job["output_path"])
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy file kết quả")

    base = Path(job.get("original_name") or "document.pdf").stem
    return FileResponse(
        str(output_path), media_type="application/pdf", filename=f"{base}_vi.pdf"
    )
