"""FastAPI app: Mai Tam Translate — dịch tài liệu PDF y khoa giữ nguyên bố cục."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core import auth_store, job_store
from .core.config import get_settings
from .routers import auth, glossary, pdf, providers, settings as settings_router, text


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    job_store.init(settings.cache_dir / "jobs.db")
    auth_store.init(
        settings.cache_dir / "auth.db",
        settings.cache_dir / "auth_secret.key",
        settings.auth_secret_key,
    )
    auth_store.ensure_admin(settings.admin_username, settings.admin_password)
    yield


app = FastAPI(title="Mai Tam Translate API", version="0.1.0", lifespan=lifespan)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


app.include_router(pdf.router)
app.include_router(text.router)
app.include_router(providers.router)
app.include_router(glossary.router)
app.include_router(settings_router.router)
app.include_router(auth.router)
