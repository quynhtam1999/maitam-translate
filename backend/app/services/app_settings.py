"""Đọc/ghi cấu hình runtime vào file .env và làm mới cache get_settings().

Cho phép người dùng nhập API key / base URL / giới hạn quota ngay trong giao diện
(⚙ Cài đặt) mà không phải sửa .env tay rồi khởi động lại. Ghi giữ nguyên comment,
chỉ thay giá trị của khóa tương ứng (hoặc thêm mới ở cuối nếu chưa có).
"""
from pathlib import Path

from ..core.config import BACKEND_ROOT, get_settings

ENV_PATH = BACKEND_ROOT / ".env"

# Ánh xạ tên trường (snake_case) -> tên biến môi trường trong .env.
_FIELD_TO_ENV = {
    "gemini_api_key": "GEMINI_API_KEY",
    "qwen_api_key": "QWEN_API_KEY",
    "qwen_base_url": "QWEN_BASE_URL",
    "default_target_lang": "DEFAULT_TARGET_LANG",
    "gemini_rpm_limit": "GEMINI_RPM_LIMIT",
    "gemini_tpm_limit": "GEMINI_TPM_LIMIT",
    "gemini_rpd_limit": "GEMINI_RPD_LIMIT",
    "qwen_rpm_limit": "QWEN_RPM_LIMIT",
    "qwen_tpm_limit": "QWEN_TPM_LIMIT",
    "qwen_rpd_limit": "QWEN_RPD_LIMIT",
}


def mask_key(key: str) -> str:
    """Che API key khi trả về giao diện: chỉ lộ 4 ký tự cuối."""
    if not key:
        return ""
    if len(key) <= 4:
        return "••••"
    return "••••" + key[-4:]


def _write_env(updates: dict[str, str]) -> None:
    """Cập nhật các KEY=VALUE trong .env, giữ nguyên comment & thứ tự dòng."""
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name = stripped.split("=", 1)[0].strip()
            if name in remaining:
                out.append(f"{name}={remaining.pop(name)}")
                continue
        out.append(line)

    # Khóa chưa từng có trong file -> thêm ở cuối.
    if remaining:
        if out and out[-1].strip() != "":
            out.append("")
        for name, value in remaining.items():
            out.append(f"{name}={value}")

    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def apply_updates(fields: dict[str, object]) -> None:
    """Nhận dict {field_name: value} (chỉ các trường được đặt), ghi vào .env.

    Sau khi ghi, xóa lru_cache của get_settings() để lần đọc kế tiếp lấy giá trị mới.
    """
    env_updates: dict[str, str] = {}
    for field, value in fields.items():
        env_name = _FIELD_TO_ENV.get(field)
        if env_name is None or value is None:
            continue
        env_updates[env_name] = str(value)

    if env_updates:
        _write_env(env_updates)
        get_settings.cache_clear()


def _count_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(1 for p in directory.iterdir() if p.is_file())
