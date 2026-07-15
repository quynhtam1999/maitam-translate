"""Engine + schema dùng chung cho auth_store/job_store/cache.

Một bộ Table SQLAlchemy Core chạy được trên cả hai dialect:
- SQLite (dev cục bộ, zero-setup): file `storage/cache/app.db`.
- Postgres/Neon (deploy): qua `DATABASE_URL`, tự phục hồi kết nối sau khi
  Neon autosuspend nhờ `pool_pre_ping`.
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    Engine,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", String, primary_key=True),
    Column("username", String, nullable=False),
    Column("username_norm", String, nullable=False, unique=True),
    Column("password_hash", String, nullable=False),
    Column("is_admin", Integer, nullable=False, server_default="0"),
    Column("created_at", Float, nullable=False),
)

user_api_keys = Table(
    "user_api_keys",
    metadata,
    Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("gemini_key_enc", Text),
    Column("qwen_key_enc", Text),
    Column("qwen_base_url", Text),
    Column("qwen_model", Text),
    Column("updated_at", Float, nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("token_hash", String, primary_key=True),
    Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", Float, nullable=False),
    Column("expires_at", Float, nullable=False),
    Index("idx_sessions_user_id", "user_id"),
)

jobs = Table(
    "jobs",
    metadata,
    Column("job_id", String, primary_key=True),
    Column("user_id", String),
    Column("status", String, nullable=False),
    Column("input_path", Text, nullable=False),
    Column("output_path", Text, nullable=False),
    Column("original_name", Text),
    Column("provider", String),
    Column("target_lang", String, nullable=False, server_default="vi"),
    Column("progress", Text, nullable=False, server_default="{}"),
    Column("error", Text),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
    Index("idx_jobs_user_id", "user_id"),
)

segment_cache = Table(
    "segment_cache",
    metadata,
    Column("hash", String, primary_key=True),
    Column("user_id", String, nullable=False, server_default="global"),
    Column("source_text", Text, nullable=False),
    Column("translated_text", Text, nullable=False),
    Column("target_lang", String, nullable=False),
    Column("provider_used", String),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
    Index("idx_segment_cache_user_id", "user_id"),
)

_engine: Engine | None = None


def init(url: str) -> Engine:
    """Tạo engine (SQLite hoặc Postgres) và đảm bảo schema tồn tại."""
    global _engine
    is_sqlite = url.startswith("sqlite")
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    connect_args: dict = {}
    if is_sqlite:
        connect_args["check_same_thread"] = False
        # StaticPool chỉ an toàn/cần thiết cho SQLite in-memory. Với file SQLite,
        # một connection dùng chung giữa web thread và worker dịch có thể làm hai
        # transaction giẫm lên nhau; để SQLAlchemy dùng QueuePool mặc định.
        database = make_url(url).database
        if not database or database == ":memory:":
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, connect_args=connect_args, **kwargs)
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            dbapi_connection.execute("PRAGMA foreign_keys = ON")

    metadata.create_all(engine)
    _engine = engine
    return engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("db chưa được init()")
    return _engine


def upsert(table: Table):
    """Trả về Insert dialect phù hợp (Postgres/SQLite) hỗ trợ ON CONFLICT."""
    dialect = get_engine().dialect.name
    if dialect == "postgresql":
        return postgresql.insert(table)
    return sqlite.insert(table)
