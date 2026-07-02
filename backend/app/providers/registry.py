"""Provider registry."""
from ..models.provider import ProviderInfo
from .base import BaseProvider
from .gemini import GeminiProvider
from .qwen import QwenProvider

_PROVIDERS: dict[str, BaseProvider] = {
    "qwen": QwenProvider(),
    "gemini": GeminiProvider(model="gemini-3.1-flash-lite", display_name="Gemini 3.1 Flash Lite"),
    "gemma": GeminiProvider(model="gemma-4-31b", display_name="Gemma 4 31B", name="gemma"),
}

_FREE_TIER_NOTE = {
    "qwen": "Miễn phí: 2.000 lượt gọi/ngày (chung mọi model), tối đa 500 lượt/model/ngày; reset 00:00 giờ Bắc Kinh (UTC+8).",
    "gemini": "Miễn phí trọn đời (giới hạn RPD/ngày)",
    "gemma": "Miễn phí trọn đời (giới hạn RPD/ngày)",
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
                requires_key=True,
                key_configured=provider.is_configured(),
                free_tier_note=_FREE_TIER_NOTE.get(name, ""),
            )
        )
    return infos
