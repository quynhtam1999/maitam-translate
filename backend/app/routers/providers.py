"""Endpoint liệt kê provider và xem quota còn lại."""
from fastapi import APIRouter, HTTPException

from ..models.provider import ProviderInfo, QuotaSnapshot
from ..providers.quota_tracker import quota_tracker
from ..providers.registry import get_provider, list_providers

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("", response_model=list[ProviderInfo])
async def get_providers():
    return list_providers()


@router.get("/{name}/quota", response_model=QuotaSnapshot)
async def get_quota(name: str):
    try:
        limits = get_provider(name).get_limits()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider không tồn tại: {name}")
    return quota_tracker.snapshot(name, limits.rpm, limits.tpm, limits.rpd)
