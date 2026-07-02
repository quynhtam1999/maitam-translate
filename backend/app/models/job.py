"""Schema cho job dịch PDF (mẫu submit → poll → download)."""
from enum import Enum

from pydantic import BaseModel

from .provider import QuotaSnapshot


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED_QUOTA = "paused_quota"  # hết quota giữa chừng — chờ đổi provider để dịch tiếp (A4)
    DONE = "done"
    FAILED = "failed"


class JobProgress(BaseModel):
    segments_total: int = 0
    segments_translated: int = 0
    current_page: int = 0
    pages_total: int = 0


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: JobProgress
    provider_used: str | None = None
    target_lang: str = "vi"
    quota: QuotaSnapshot | None = None
    error: str | None = None


class JobResumeRequest(BaseModel):
    provider: str | None = None  # tùy chọn đổi provider khi dịch tiếp
