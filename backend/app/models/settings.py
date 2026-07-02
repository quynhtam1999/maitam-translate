"""Schemas for user settings, provider keys, and cleanup actions."""
from pydantic import BaseModel, Field


class CacheStats(BaseModel):
    segments: int = 0
    jobs: int = 0
    upload_files: int = 0
    output_files: int = 0


class SettingsResponse(BaseModel):
    is_admin: bool = False
    gemini_api_key_set: bool = False
    gemini_api_key_masked: str = ""
    qwen_api_key_set: bool = False
    qwen_api_key_masked: str = ""
    qwen_base_url: str = ""
    qwen_model: str = ""

    gemini_rpm_limit: int = 0
    gemini_tpm_limit: int = 0
    gemini_rpd_limit: int = 0
    gemini_max_tokens_per_request: int = 0
    gemma_rpm_limit: int = 0
    gemma_tpm_limit: int = 0
    gemma_rpd_limit: int = 0
    gemma_max_tokens_per_request: int = 0
    qwen_rpm_limit: int = 0
    qwen_tpm_limit: int = 0
    qwen_rpd_limit: int = 0
    qwen_max_tokens_per_request: int = 0

    cache: CacheStats = Field(default_factory=CacheStats)


class SettingsUpdateRequest(BaseModel):
    # None means keep the current value. Empty string clears that user's key.
    gemini_api_key: str | None = None
    qwen_api_key: str | None = None
    qwen_base_url: str | None = None
    qwen_model: str | None = None

    gemini_rpm_limit: int | None = None
    gemini_tpm_limit: int | None = None
    gemini_rpd_limit: int | None = None
    gemini_max_tokens_per_request: int | None = None
    gemma_rpm_limit: int | None = None
    gemma_tpm_limit: int | None = None
    gemma_rpd_limit: int | None = None
    gemma_max_tokens_per_request: int | None = None
    qwen_rpm_limit: int | None = None
    qwen_tpm_limit: int | None = None
    qwen_rpd_limit: int | None = None
    qwen_max_tokens_per_request: int | None = None


class ClearResult(BaseModel):
    cleared: int = 0
    message: str = ""
