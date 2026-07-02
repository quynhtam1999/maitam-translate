"""Endpoint Cài đặt: đọc/ghi cấu hình (API key, base URL, quota) và dọn cache."""
import sqlite3

from fastapi import APIRouter

from ..core import job_store
from ..core.config import get_settings
from ..models.settings import (
    CacheStats,
    ClearResult,
    SettingsResponse,
    SettingsUpdateRequest,
)
from ..services.app_settings import _count_files, apply_updates, mask_key
from ..services.cache import SegmentCache

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _count_segments() -> int:
    db = get_settings().cache_dir / "segments.db"
    if not db.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute("SELECT COUNT(*) FROM segment_cache").fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def _count_jobs() -> int:
    db = get_settings().cache_dir / "jobs.db"
    if not db.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def _cache_stats() -> CacheStats:
    s = get_settings()
    return CacheStats(
        segments=_count_segments(),
        jobs=_count_jobs(),
        upload_files=_count_files(s.uploads_dir),
        output_files=_count_files(s.outputs_dir),
    )


@router.get("", response_model=SettingsResponse)
async def read_settings():
    s = get_settings()
    return SettingsResponse(
        gemini_api_key_set=bool(s.gemini_api_key),
        gemini_api_key_masked=mask_key(s.gemini_api_key),
        qwen_api_key_set=bool(s.qwen_api_key),
        qwen_api_key_masked=mask_key(s.qwen_api_key),
        qwen_base_url=s.qwen_base_url,
        default_target_lang=s.default_target_lang,
        gemini_rpm_limit=s.gemini_rpm_limit,
        gemini_tpm_limit=s.gemini_tpm_limit,
        gemini_rpd_limit=s.gemini_rpd_limit,
        qwen_rpm_limit=s.qwen_rpm_limit,
        qwen_tpm_limit=s.qwen_tpm_limit,
        qwen_rpd_limit=s.qwen_rpd_limit,
        cache=_cache_stats(),
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(req: SettingsUpdateRequest):
    # Chỉ áp dụng các trường được gửi lên (exclude_unset) -> None nghĩa là "giữ nguyên".
    apply_updates(req.model_dump(exclude_unset=True))
    return await read_settings()


@router.post("/cache/clear", response_model=ClearResult)
async def clear_translation_cache():
    """Xóa toàn bộ bộ nhớ đệm bản dịch (segments.db)."""
    cache = SegmentCache(get_settings().cache_dir / "segments.db")
    removed = cache.clear()
    return ClearResult(cleared=removed, message=f"Đã xóa {removed} đoạn dịch khỏi cache.")


@router.post("/jobs/clear", response_model=ClearResult)
async def clear_jobs():
    """Xóa lịch sử job + file PDF gốc/đã dịch trong uploads/ và outputs/."""
    s = get_settings()
    removed_jobs = 0
    try:
        cur = job_store._db().execute("DELETE FROM jobs")  # noqa: SLF001
        job_store._db().commit()  # noqa: SLF001
        removed_jobs = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    except (sqlite3.Error, RuntimeError):
        pass

    removed_files = 0
    for directory in (s.uploads_dir, s.outputs_dir):
        if directory.exists():
            for p in directory.iterdir():
                if p.is_file():
                    try:
                        p.unlink()
                        removed_files += 1
                    except OSError:
                        pass

    return ClearResult(
        cleared=removed_jobs,
        message=f"Đã xóa {removed_jobs} job và {removed_files} file kết quả.",
    )
