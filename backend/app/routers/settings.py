"""Settings endpoints for the authenticated account."""
from fastapi import APIRouter

from ..core import auth_store, job_store
from ..core.auth import CurrentUser
from ..core.config import get_settings
from ..models.settings import (
    CacheStats,
    ClearResult,
    SettingsResponse,
    SettingsUpdateRequest,
)
from ..services import storage
from ..services.app_settings import apply_updates
from ..services.cache import SegmentCache
from ..services.user_data import purge_jobs_and_files

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _cache_stats(user_id: str) -> CacheStats:
    return CacheStats(
        segments=SegmentCache(user_id=user_id).count(),
        jobs=job_store.count_jobs(user_id),
        upload_files=storage.count_prefix(f"uploads/{user_id}/"),
        output_files=storage.count_prefix(f"outputs/{user_id}/"),
    )


_QUOTA_FIELDS = {
    "gemini_rpm_limit",
    "gemini_tpm_limit",
    "gemini_rpd_limit",
    "gemini_max_tokens_per_request",
    "gemma_rpm_limit",
    "gemma_tpm_limit",
    "gemma_rpd_limit",
    "gemma_max_tokens_per_request",
    "qwen_rpm_limit",
    "qwen_tpm_limit",
    "qwen_rpd_limit",
    "qwen_max_tokens_per_request",
}


@router.get("", response_model=SettingsResponse)
async def read_settings(current_user: CurrentUser):
    s = get_settings()
    key_status = auth_store.get_api_key_status(current_user["id"])
    user_qwen_base_url = auth_store.get_qwen_base_url(current_user["id"])
    user_qwen_model = auth_store.get_qwen_model(current_user["id"])
    return SettingsResponse(
        is_admin=bool(current_user["is_admin"]),
        gemini_api_key_set=bool(key_status["gemini"]["set"]),
        gemini_api_key_masked=str(key_status["gemini"]["masked"]),
        qwen_api_key_set=bool(key_status["qwen"]["set"]),
        qwen_api_key_masked=str(key_status["qwen"]["masked"]),
        qwen_base_url=user_qwen_base_url or s.qwen_base_url,
        qwen_model=user_qwen_model or s.qwen_model,
        gemini_rpm_limit=s.gemini_rpm_limit,
        gemini_tpm_limit=s.gemini_tpm_limit,
        gemini_rpd_limit=s.gemini_rpd_limit,
        gemini_max_tokens_per_request=s.gemini_max_tokens_per_request,
        gemma_rpm_limit=s.gemma_rpm_limit,
        gemma_tpm_limit=s.gemma_tpm_limit,
        gemma_rpd_limit=s.gemma_rpd_limit,
        gemma_max_tokens_per_request=s.gemma_max_tokens_per_request,
        qwen_rpm_limit=s.qwen_rpm_limit,
        qwen_tpm_limit=s.qwen_tpm_limit,
        qwen_rpd_limit=s.qwen_rpd_limit,
        qwen_max_tokens_per_request=s.qwen_max_tokens_per_request,
        cache=_cache_stats(current_user["id"]),
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(req: SettingsUpdateRequest, current_user: CurrentUser):
    fields = req.model_dump(exclude_unset=True)

    key_updates = {}
    if "gemini_api_key" in fields:
        key_updates["gemini_key"] = fields.pop("gemini_api_key")
    if "qwen_api_key" in fields:
        key_updates["qwen_key"] = fields.pop("qwen_api_key")
    if "qwen_base_url" in fields:
        key_updates["qwen_base_url"] = fields.pop("qwen_base_url")
    if "qwen_model" in fields:
        key_updates["qwen_model"] = fields.pop("qwen_model")
    if key_updates:
        auth_store.update_api_keys(current_user["id"], **key_updates)

    if not current_user["is_admin"]:
        # Quota giới hạn API là cấu hình chung — chỉ admin được sửa.
        # Bỏ qua thay vì lỗi để không phá luồng lưu API key của user thường.
        for field in _QUOTA_FIELDS:
            fields.pop(field, None)

    apply_updates(fields)
    return await read_settings(current_user)


@router.post("/cache/clear", response_model=ClearResult)
async def clear_translation_cache(current_user: CurrentUser):
    cache = SegmentCache(user_id=current_user["id"])
    removed = cache.clear()
    return ClearResult(cleared=removed, message=f"Đã xóa {removed} đoạn dịch khỏi cache.")


@router.post("/jobs/clear", response_model=ClearResult)
async def clear_jobs(current_user: CurrentUser):
    job_count, removed_files = purge_jobs_and_files(current_user["id"])
    return ClearResult(
        cleared=job_count,
        message=f"Đã xóa {job_count} job và {removed_files} file kết quả.",
    )
