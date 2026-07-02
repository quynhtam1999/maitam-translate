"""Schema liên quan tới nhà cung cấp (provider) và quota."""
from pydantic import BaseModel


class ProviderInfo(BaseModel):
    name: str                 # "gemini" | "gemma" | "qwen"
    display_name: str
    requires_key: bool
    key_configured: bool
    free_tier_note: str = ""


class QuotaSnapshot(BaseModel):
    """Ảnh chụp quota cục bộ (A6b) — đếm từ số token thật trả về sau mỗi lần gọi."""
    provider: str
    rpm_used: int = 0
    rpm_limit: int = 0
    tpm_used: int = 0
    tpm_limit: int = 0
    rpd_used: int = 0
    rpd_limit: int = 0
    resets_at: str | None = None  # ISO time, mốc reset RPD (theo lệch UTC của provider)
