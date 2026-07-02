"""Cấu hình ứng dụng, đọc từ biến môi trường / file .env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Thư mục gốc của backend/ (chứa file .env, thư mục storage)
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Providers
    gemini_api_key: str = ""
    qwen_api_key: str = ""
    qwen_base_url: str = ""

    # App
    backend_cors_origins: str = "http://localhost:5173"
    storage_dir: str = "./storage"
    auth_session_days: int = 365
    auth_cookie_secure: bool = False
    # "lax" cho cùng site (dev localhost). Deploy tách domain (frontend Vercel +
    # backend riêng) là cross-site -> phải đặt "none" để trình duyệt gửi kèm cookie.
    auth_cookie_samesite: str = "lax"
    auth_secret_key: str = ""
    admin_username: str = ""
    admin_password: str = ""

    # Quota limits plus per-request output-token ceilings.
    gemini_rpm_limit: int = 15
    gemini_tpm_limit: int = 250_000
    gemini_rpd_limit: int = 1500
    gemini_max_tokens_per_request: int = 65_536
    gemma_rpm_limit: int = 30
    gemma_tpm_limit: int = 15_000
    gemma_rpd_limit: int = 14_400
    gemma_max_tokens_per_request: int = 8_192
    qwen_rpm_limit: int = 60
    qwen_tpm_limit: int = 100_000
    # Local limiter for the configured OpenAI-compatible Qwen endpoint.
    qwen_rpd_limit: int = 500
    qwen_max_tokens_per_request: int = 16_384

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def storage_path(self) -> Path:
        p = self.storage_dir
        path = Path(p) if Path(p).is_absolute() else BACKEND_ROOT / p
        return path.resolve()

    @property
    def uploads_dir(self) -> Path:
        return self.storage_path / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.storage_path / "outputs"

    @property
    def cache_dir(self) -> Path:
        return self.storage_path / "cache"

    @property
    def glossary_dir(self) -> Path:
        return self.storage_path / "glossary"

    def ensure_dirs(self) -> None:
        for d in (self.uploads_dir, self.outputs_dir, self.cache_dir, self.glossary_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
