"""Runtime .env updates for global provider settings.

Per-user API keys are intentionally not written here. They are stored encrypted
in auth_store and scoped to the authenticated account.
"""
from ..core.config import BACKEND_ROOT, get_settings

ENV_PATH = BACKEND_ROOT / ".env"

_FIELD_TO_ENV = {
    "gemini_rpm_limit": "GEMINI_RPM_LIMIT",
    "gemini_tpm_limit": "GEMINI_TPM_LIMIT",
    "gemini_rpd_limit": "GEMINI_RPD_LIMIT",
    "gemini_max_tokens_per_request": "GEMINI_MAX_TOKENS_PER_REQUEST",
    "gemma_rpm_limit": "GEMMA_RPM_LIMIT",
    "gemma_tpm_limit": "GEMMA_TPM_LIMIT",
    "gemma_rpd_limit": "GEMMA_RPD_LIMIT",
    "gemma_max_tokens_per_request": "GEMMA_MAX_TOKENS_PER_REQUEST",
    "qwen_rpm_limit": "QWEN_RPM_LIMIT",
    "qwen_tpm_limit": "QWEN_TPM_LIMIT",
    "qwen_rpd_limit": "QWEN_RPD_LIMIT",
    "qwen_max_tokens_per_request": "QWEN_MAX_TOKENS_PER_REQUEST",
}


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return "****" + key[-4:]


def _write_env(updates: dict[str, str]) -> None:
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

    if remaining:
        if out and out[-1].strip() != "":
            out.append("")
        for name, value in remaining.items():
            out.append(f"{name}={value}")

    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def apply_updates(fields: dict[str, object]) -> None:
    env_updates: dict[str, str] = {}
    for field, value in fields.items():
        env_name = _FIELD_TO_ENV.get(field)
        if env_name is None or value is None:
            continue
        env_updates[env_name] = str(value)

    if env_updates:
        _write_env(env_updates)
        get_settings.cache_clear()
