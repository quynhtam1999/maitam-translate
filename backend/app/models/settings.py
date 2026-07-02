"""Schema cho phần Cài đặt (đọc/ghi cấu hình runtime + dọn cache)."""
from pydantic import BaseModel


class CacheStats(BaseModel):
    segments: int = 0          # số đoạn đã cache trong segments.db
    jobs: int = 0              # số job trong jobs.db
    upload_files: int = 0      # số file PDF gốc còn trong uploads/
    output_files: int = 0      # số file PDF đã dịch còn trong outputs/


class SettingsResponse(BaseModel):
    """Trạng thái cấu hình hiện tại. API key luôn được che (masked)."""
    gemini_api_key_set: bool = False
    gemini_api_key_masked: str = ""
    qwen_api_key_set: bool = False
    qwen_api_key_masked: str = ""
    qwen_base_url: str = ""
    default_target_lang: str = "vi"

    gemini_rpm_limit: int = 0
    gemini_tpm_limit: int = 0
    gemini_rpd_limit: int = 0
    qwen_rpm_limit: int = 0
    qwen_tpm_limit: int = 0
    qwen_rpd_limit: int = 0

    cache: CacheStats = CacheStats()


class SettingsUpdateRequest(BaseModel):
    """Cập nhật cấu hình. Trường None = giữ nguyên; với key: "" = xóa key."""
    gemini_api_key: str | None = None
    qwen_api_key: str | None = None
    qwen_base_url: str | None = None
    default_target_lang: str | None = None

    gemini_rpm_limit: int | None = None
    gemini_tpm_limit: int | None = None
    gemini_rpd_limit: int | None = None
    qwen_rpm_limit: int | None = None
    qwen_tpm_limit: int | None = None
    qwen_rpd_limit: int | None = None


class ClearResult(BaseModel):
    cleared: int = 0
    message: str = ""
