"""Per-user glossary endpoints."""
from fastapi import APIRouter, File, UploadFile

from ..core.auth import CurrentUser
from ..core.config import get_settings
from ..models.glossary import GlossaryEntry, GlossaryUploadResponse
from ..services.glossary import load_glossary

router = APIRouter(prefix="/api/glossary", tags=["glossary"])


def _glossary_path(user_id: str):
    return get_settings().glossary_dir / user_id / "glossary.csv"


@router.get("", response_model=list[GlossaryEntry])
async def get_glossary(current_user: CurrentUser):
    return load_glossary(_glossary_path(current_user["id"]))


@router.post("", response_model=GlossaryUploadResponse)
async def upload_glossary(current_user: CurrentUser, file: UploadFile = File(...)):
    path = _glossary_path(current_user["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(await file.read())
    entries = load_glossary(path)
    return GlossaryUploadResponse(count_loaded=len(entries))
