"""Lưu trạng thái job dịch PDF (SQLAlchemy Core; SQLite local / Postgres prod, bền qua
restart -> hỗ trợ resume).

Bảng được tạo qua `db.init()`. Dùng một khóa tiến trình chung; đủ cho scaffold
(mỗi job xử lý nền tuần tự qua BackgroundTasks).
"""
import json
import threading
import time
import uuid

import sqlalchemy as sa

from . import db as db_module
from .db import jobs
from ..models.job import JobProgress, JobStatus

_lock = threading.Lock()
_UNSET = object()


def create_job(
    user_id: str,
    input_path: str,
    output_path: str,
    original_name: str,
    provider: str,
    target_lang: str = "vi",
) -> str:
    job_id = uuid.uuid4().hex
    now = time.time()
    with _lock, db_module.get_engine().begin() as conn:
        conn.execute(
            jobs.insert(),
            {
                "job_id": job_id,
                "user_id": user_id,
                "status": JobStatus.QUEUED.value,
                "input_path": input_path,
                "output_path": output_path,
                "original_name": original_name,
                "provider": provider,
                "target_lang": target_lang,
                "progress": json.dumps(JobProgress().model_dump()),
                "created_at": now,
                "updated_at": now,
            },
        )
    return job_id


def get_job(job_id: str, user_id: str | None = None) -> dict | None:
    with _lock, db_module.get_engine().connect() as conn:
        stmt = jobs.select().where(jobs.c.job_id == job_id)
        if user_id is not None:
            stmt = stmt.where(jobs.c.user_id == user_id)
        row = conn.execute(stmt).mappings().first()
    if row is None:
        return None
    d = dict(row)
    d["progress"] = json.loads(d.get("progress") or "{}")
    return d


def update_job(
    job_id: str,
    *,
    status: JobStatus | None = None,
    progress: JobProgress | None = None,
    provider: str | None = None,
    error: str | None | object = _UNSET,
) -> None:
    sets: dict = {"updated_at": time.time()}
    if status is not None:
        sets["status"] = status.value
    if progress is not None:
        sets["progress"] = json.dumps(progress.model_dump())
    if provider is not None:
        sets["provider"] = provider
    if error is not _UNSET:
        sets["error"] = error

    with _lock, db_module.get_engine().begin() as conn:
        conn.execute(jobs.update().where(jobs.c.job_id == job_id).values(**sets))


def set_job_paths(job_id: str, user_id: str, input_path: str, output_path: str) -> None:
    with _lock, db_module.get_engine().begin() as conn:
        conn.execute(
            jobs.update()
            .where(jobs.c.job_id == job_id, jobs.c.user_id == user_id)
            .values(input_path=input_path, output_path=output_path, updated_at=time.time())
        )


def count_jobs(user_id: str) -> int:
    with _lock, db_module.get_engine().connect() as conn:
        result = conn.execute(
            sa.select(sa.func.count()).select_from(jobs).where(jobs.c.user_id == user_id)
        )
        return int(result.scalar() or 0)


def delete_jobs_for_user(user_id: str) -> list[dict]:
    with _lock, db_module.get_engine().begin() as conn:
        rows = conn.execute(
            sa.select(jobs.c.job_id, jobs.c.input_path, jobs.c.output_path).where(
                jobs.c.user_id == user_id
            )
        ).mappings().all()
        conn.execute(jobs.delete().where(jobs.c.user_id == user_id))
    return [dict(row) for row in rows]
