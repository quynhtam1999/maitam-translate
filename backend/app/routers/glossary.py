"""Endpoint xem & tải lên từ điển thuật ngữ (glossary.csv)."""
from fastapi import APIRouter, File, UploadFile

from ..core.config import get_settings
from ..models.glossary import GlossaryEntry, GlossaryUploadResponse
from ..services.glossary import load_glossary

router = APIRouter(prefix="/api/glossary", tags=["glossary"])


def _glossary_path():
    return get_settings().glossary_dir / "glossary.csv"


@router.get("", response_model=list[GlossaryEntry])
async def get_glossary():
    return load_glossary(_glossary_path())


@router.post("", response_model=GlossaryUploadResponse)
async def upload_glossary(file: UploadFile = File(...)):
    path = _glossary_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(await file.read())
    entries = load_glossary(path)
    return GlossaryUploadResponse(count_loaded=len(entries))
