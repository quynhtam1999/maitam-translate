"""Provider registry."""
from ..models.provider import ProviderInfo
from .base import BaseProvider
from .gemini import GeminiProvider
from .qwen import QwenProvider

_PROVIDERS: dict[str, BaseProvider] = {
    "qwen": QwenProvider(),
    "gemini": GeminiProvider(model="gemini-3.1-flash-lite", display_name="Gemini 3.1 Flash Lite"),
    "gemma": GeminiProvider(model="gemma-4-31b-it", display_name="Gemma 4 31B", name="gemma"),
}

_FREE_TIER_NOTE = {
    "qwen": (
        "Cần Qwen Base URL của endpoint OpenAI-compatible tự triển khai "
        "(vLLM/SGLang); API key có thể để trống/EMPTY."
    ),
    "gemini": "Miễn phí trọn đời (giới hạn RPD/ngày)",
    "gemma": "Gemma 4 31B - miễn phí trọn đời (giới hạn RPD/ngày)",
}


def get_provider(name: str) -> BaseProvider:
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise KeyError(f"Provider không tồn tại: {name!r}")
    return provider


def list_providers() -> list[ProviderInfo]:
    infos: list[ProviderInfo] = []
    for name, provider in _PROVIDERS.items():
        infos.append(
            ProviderInfo(
                name=name,
                display_name=provider.display_name,
                requires_key=name != "qwen",
                key_configured=provider.is_configured(),
                free_tier_note=_FREE_TIER_NOTE.get(name, ""),
            )
        )
    return infos
