"""PDF translation job endpoints."""
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from ..core import auth_store, job_store
from ..core.auth import CurrentUser
from ..models.job import (
    JobCreateResponse,
    JobProgress,
    JobResumeRequest,
    JobStatus,
    JobStatusResponse,
)
from ..providers.quota_tracker import quota_tracker
from ..providers.qwen import resolve_qwen_base_url, validate_qwen_base_url
from ..providers.registry import get_provider
from ..services import storage
from ..services.job_runner import run_pdf_job

router = APIRouter(prefix="/api/pdf", tags=["pdf"])


def _provider_credentials(user_id: str, provider: str) -> tuple[str | None, dict[str, str]]:
    api_key = auth_store.get_provider_api_key(user_id, provider)
    provider_options = auth_store.get_provider_options(user_id, provider)
    if provider == "qwen":
        try:
            validate_qwen_base_url(resolve_qwen_base_url(provider_options))
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Chưa lưu API key ModelScope cho Qwen trong tài khoản.",
            )
        return api_key, provider_options

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Chưa lưu API key cho provider này trong tài khoản.",
        )
    return api_key, provider_options


def _quota_for(provider_name: str | None, user_id: str):
    if not provider_name:
        return None
    try:
        limits = get_provider(provider_name).get_limits()
    except KeyError:
        return None
    return quota_tracker.snapshot(
        provider_name, limits.rpm, limits.tpm, limits.rpd, scope=user_id
    )


def _to_status_response(job: dict) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=job["job_id"],
        status=JobStatus(job["status"]),
        progress=JobProgress(**job["progress"]),
        provider_used=job.get("provider"),
        target_lang=job.get("target_lang", "vi"),
        quota=_quota_for(job.get("provider"), job["user_id"]),
        error=job.get("error"),
    )


def _content_disposition(filename: str) -> str:
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "document.pdf"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.post("/jobs", response_model=JobCreateResponse, status_code=202)
async def create_pdf_job(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
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

    api_key, provider_options = _provider_credentials(current_user["id"], provider)
    job_id = job_store.create_job(
        current_user["id"],
        input_path="",
        output_path="",
        original_name=file.filename or "document.pdf",
        provider=provider,
        target_lang=target_lang,
    )

    input_key = f"uploads/{current_user['id']}/{job_id}.pdf"
    output_key = f"outputs/{current_user['id']}/{job_id}_vi.pdf"
    storage.put_bytes(input_key, await file.read())

    job_store.set_job_paths(job_id, current_user["id"], input_key, output_key)

    background_tasks.add_task(
        run_pdf_job,
        job_id,
        current_user["id"],
        input_key,
        output_key,
        provider,
        target_lang,
        force_retranslate,
        api_key,
        provider_options,
    )
    return JobCreateResponse(job_id=job_id, status=JobStatus.QUEUED)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_pdf_job(job_id: str, current_user: CurrentUser):
    job = job_store.get_job(job_id, current_user["id"])
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy job")
    return _to_status_response(job)


@router.post("/jobs/{job_id}/resume", response_model=JobCreateResponse, status_code=202)
async def resume_pdf_job(
    job_id: str,
    body: JobResumeRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
):
    job = job_store.get_job(job_id, current_user["id"])
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy job")

    provider = body.provider or job.get("provider")
    try:
        get_provider(provider)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Provider không hợp lệ: {provider}")

    api_key, provider_options = _provider_credentials(current_user["id"], provider)
    job_store.update_job(job_id, status=JobStatus.QUEUED, provider=provider, error=None)
    background_tasks.add_task(
        run_pdf_job,
        job_id,
        current_user["id"],
        job["input_path"],
        job["output_path"],
        provider,
        job.get("target_lang", "vi"),
        False,
        api_key,
        provider_options,
    )
    return JobCreateResponse(job_id=job_id, status=JobStatus.QUEUED)


@router.get("/jobs/{job_id}/download")
async def download_pdf_job(job_id: str, current_user: CurrentUser):
    job = job_store.get_job(job_id, current_user["id"])
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy job")
    if job["status"] != JobStatus.DONE.value:
        raise HTTPException(status_code=409, detail="Job chưa hoàn tất")

    data = storage.get_bytes(job["output_path"])
    if data is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy file kết quả")

    base = Path(job.get("original_name") or "document.pdf").stem
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(f"{base}_vi.pdf")},
    )
