"""Provider list and per-user quota snapshots."""
from fastapi import APIRouter, HTTPException

from ..core import auth_store
from ..core.auth import CurrentUser
from ..models.provider import ProviderInfo, QuotaSnapshot
from ..providers.quota_tracker import quota_tracker
from ..providers.registry import get_provider, list_providers

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("", response_model=list[ProviderInfo])
async def get_providers(current_user: CurrentUser):
    key_status = auth_store.get_api_key_status(current_user["id"])
    infos = list_providers()
    for info in infos:
        if info.name in ("gemini", "gemma"):
            info.key_configured = bool(key_status["gemini"]["set"])
        elif info.name == "qwen":
            info.key_configured = bool(key_status["qwen"]["set"])
    return infos


@router.get("/{name}/quota", response_model=QuotaSnapshot)
async def get_quota(name: str, current_user: CurrentUser):
    try:
        limits = get_provider(name).get_limits()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider không tồn tại: {name}")
    return quota_tracker.snapshot(
        name, limits.rpm, limits.tpm, limits.rpd, scope=current_user["id"]
    )
