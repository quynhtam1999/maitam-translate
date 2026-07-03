"""Per-user glossary endpoints."""
from fastapi import APIRouter, File, UploadFile

from ..core.auth import CurrentUser
from ..models.glossary import GlossaryEntry, GlossaryUploadResponse
from ..services import storage
from ..services.glossary import load_glossary_bytes

router = APIRouter(prefix="/api/glossary", tags=["glossary"])


def _glossary_key(user_id: str) -> str:
    return f"glossary/{user_id}/glossary.csv"


@router.get("", response_model=list[GlossaryEntry])
async def get_glossary(current_user: CurrentUser):
    data = storage.get_bytes(_glossary_key(current_user["id"]))
    return load_glossary_bytes(data) if data else []


@router.post("", response_model=GlossaryUploadResponse)
async def upload_glossary(current_user: CurrentUser, file: UploadFile = File(...)):
    data = await file.read()
    storage.put_bytes(_glossary_key(current_user["id"]), data)
    entries = load_glossary_bytes(data)
    return GlossaryUploadResponse(count_loaded=len(entries))
