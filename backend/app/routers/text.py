"""Endpoint dịch văn bản dán tay (tab 'Dịch văn bản')."""
from fastapi import APIRouter, HTTPException

from ..core.config import get_settings
from ..models.translate import TextTranslateRequest, TextTranslateResponse
from ..providers.base import ProviderQuotaError
from ..providers.quota_tracker import quota_tracker
from ..providers.registry import get_provider
from ..services.cache import SegmentCache
from ..services.glossary import load_glossary
from ..services.translator import Translator

router = APIRouter(prefix="/api/text", tags=["text"])


@router.post("/translate", response_model=TextTranslateResponse)
async def translate_text(req: TextTranslateRequest):
    settings = get_settings()
    try:
        provider = get_provider(req.provider)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Provider không hợp lệ: {req.provider}")

    cache = SegmentCache(settings.cache_dir / "segments.db")
    glossary = load_glossary(settings.glossary_dir / "glossary.csv")
    translator = Translator(provider, cache, glossary)

    try:
        translated = await translator.translate_one(req.text, req.target_lang)
    except ProviderQuotaError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))

    limits = provider.get_limits()
    quota = quota_tracker.snapshot(provider.name, limits.rpm, limits.tpm, limits.rpd)
    return TextTranslateResponse(
        translated_text=translated, provider_used=provider.name, quota=quota
    )
