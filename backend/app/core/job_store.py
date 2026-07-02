"""Lưu trạng thái job dịch PDF trong SQLite (bền qua restart -> hỗ trợ resume).

Dùng sqlite3 chuẩn với một khóa tiến trình; đủ cho scaffold (mỗi job xử lý nền tuần tự).
TODO: nếu nâng lên nhiều worker/queue thật, cân nhắc WAL mode + kết nối theo luồng.
"""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from ..models.job import JobProgress, JobStatus

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_UNSET = object()


def init(db_path: Path) -> None:
    global _conn
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(db_path), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id        TEXT PRIMARY KEY,
            user_id       TEXT,
            status        TEXT NOT NULL,
            input_path    TEXT NOT NULL,
            output_path   TEXT NOT NULL,
            original_name TEXT,
            provider      TEXT,
            target_lang   TEXT NOT NULL DEFAULT 'vi',
            progress      TEXT NOT NULL DEFAULT '{}',
            error         TEXT,
            created_at    REAL NOT NULL,
            updated_at    REAL NOT NULL
        )
        """
    )
    columns = {row[1] for row in _conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "user_id" not in columns:
        _conn.execute("ALTER TABLE jobs ADD COLUMN user_id TEXT")
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id)")
    _conn.commit()


def _db() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("job_store chưa được init()")
    return _conn


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
    with _lock:
        _db().execute(
            """INSERT INTO jobs
               (job_id, user_id, status, input_path, output_path, original_name, provider,
                target_lang, progress, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                user_id,
                JobStatus.QUEUED.value,
                input_path,
                output_path,
                original_name,
                provider,
                target_lang,
                json.dumps(JobProgress().model_dump()),
                now,
                now,
            ),
        )
        _db().commit()
    return job_id


def get_job(job_id: str, user_id: str | None = None) -> dict | None:
    with _lock:
        if user_id is None:
            row = _db().execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        else:
            row = _db().execute(
                "SELECT * FROM jobs WHERE job_id = ? AND user_id = ?", (job_id, user_id)
            ).fetchone()
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
    sets, params = [], []
    if status is not None:
        sets.append("status = ?")
        params.append(status.value)
    if progress is not None:
        sets.append("progress = ?")
        params.append(json.dumps(progress.model_dump()))
    if provider is not None:
        sets.append("provider = ?")
        params.append(provider)
    if error is not _UNSET:
        sets.append("error = ?")
        params.append(error)
    sets.append("updated_at = ?")
    params.append(time.time())
    params.append(job_id)

    with _lock:
        _db().execute(f"UPDATE jobs SET {', '.join(sets)} WHERE job_id = ?", params)
        _db().commit()


def set_job_paths(job_id: str, user_id: str, input_path: str, output_path: str) -> None:
    with _lock:
        _db().execute(
            """UPDATE jobs
               SET input_path = ?, output_path = ?, updated_at = ?
               WHERE job_id = ? AND user_id = ?""",
            (input_path, output_path, time.time(), job_id, user_id),
        )
        _db().commit()


def count_jobs(user_id: str) -> int:
    with _lock:
        row = _db().execute("SELECT COUNT(*) FROM jobs WHERE user_id = ?", (user_id,)).fetchone()
    return int(row[0]) if row else 0


def delete_jobs_for_user(user_id: str) -> list[dict]:
    with _lock:
        rows = _db().execute(
            "SELECT job_id, input_path, output_path FROM jobs WHERE user_id = ?", (user_id,)
        ).fetchall()
        _db().execute("DELETE FROM jobs WHERE user_id = ?", (user_id,))
        _db().commit()
    return [dict(row) for row in rows]
