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

    gemini_rpm_limit: int = 0
    gemini_tpm_limit: int = 0
    gemini_rpd_limit: int = 0
    gemma_rpm_limit: int = 0
    gemma_tpm_limit: int = 0
    gemma_rpd_limit: int = 0
    qwen_rpm_limit: int = 0
    qwen_tpm_limit: int = 0
    qwen_rpd_limit: int = 0

    cache: CacheStats = CacheStats()


class SettingsUpdateRequest(BaseModel):
    """Cập nhật cấu hình. Trường None = giữ nguyên.

    KHÔNG có gemini_api_key/qwen_api_key ở đây: site public, mỗi người dùng tự
    nhập key riêng và key chỉ lưu ở trình duyệt của họ (localStorage), gửi kèm
    mỗi request qua header X-Gemini-Key / X-Qwen-Key — không lưu trên server để
    tránh một người ghi đè/xem key của người khác.
    """
    qwen_base_url: str | None = None

    gemini_rpm_limit: int | None = None
    gemini_tpm_limit: int | None = None
    gemini_rpd_limit: int | None = None
    gemma_rpm_limit: int | None = None
    gemma_tpm_limit: int | None = None
    gemma_rpd_limit: int | None = None
    qwen_rpm_limit: int | None = None
    qwen_tpm_limit: int | None = None
    qwen_rpd_limit: int | None = None


class ClearResult(BaseModel):
    cleared: int = 0
    message: str = ""
