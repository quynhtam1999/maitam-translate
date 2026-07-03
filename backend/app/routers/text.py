"""Text translation endpoint."""
from fastapi import APIRouter, HTTPException

from ..core import auth_store
from ..core.auth import CurrentUser
from ..models.translate import TextTranslateRequest, TextTranslateResponse
from ..providers.base import ProviderQuotaError
from ..providers.quota_tracker import quota_tracker
from ..providers.qwen import resolve_qwen_base_url, validate_qwen_base_url
from ..providers.registry import get_provider
from ..services import storage
from ..services.cache import SegmentCache
from ..services.glossary import load_glossary_bytes
from ..services.translator import Translator

router = APIRouter(prefix="/api/text", tags=["text"])


@router.post("/translate", response_model=TextTranslateResponse)
async def translate_text(req: TextTranslateRequest, current_user: CurrentUser):
    try:
        provider = get_provider(req.provider)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Provider không hợp lệ: {req.provider}")

    provider_options = auth_store.get_provider_options(current_user["id"], req.provider)
    api_key = auth_store.get_provider_api_key(current_user["id"], req.provider)
    if req.provider == "qwen":
        try:
            validate_qwen_base_url(resolve_qwen_base_url(provider_options))
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Chưa lưu API key ModelScope cho Qwen trong tài khoản.",
            )
    elif not api_key:
        raise HTTPException(
            status_code=400,
            detail="Chưa lưu API key cho provider này trong tài khoản.",
        )
    cache = SegmentCache(user_id=current_user["id"])
    glossary_bytes = storage.get_bytes(f"glossary/{current_user['id']}/glossary.csv")
    glossary = load_glossary_bytes(glossary_bytes) if glossary_bytes else []
    translator = Translator(
        provider,
        cache,
        glossary,
        quota_scope=current_user["id"],
        provider_options=provider_options,
    )

    try:
        translated = await translator.translate_one(req.text, req.target_lang, api_key=api_key)
    except ProviderQuotaError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    limits = provider.get_limits()
    quota = quota_tracker.snapshot(
        provider.name, limits.rpm, limits.tpm, limits.rpd, scope=current_user["id"]
    )
    return TextTranslateResponse(
        translated_text=translated, provider_used=provider.name, quota=quota
    )
