"""Per-user translation cache keyed by normalized text and target language.

SQLAlchemy Core trên engine dùng chung (`core/db.py`); chạy được cả SQLite (dev)
và Postgres/Neon (deploy).
"""
import hashlib
import threading
import time

import sqlalchemy as sa

from ..core import db as db_module
from ..core.db import segment_cache, upsert


def segment_hash(text: str, target_lang: str, user_id: str = "global") -> str:
    normalized = " ".join(text.split()).strip()
    key = f"{user_id}|{normalized}|{target_lang}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class SegmentCache:
    def __init__(self, user_id: str = "global"):
        self.user_id = user_id or "global"
        self._lock = threading.Lock()

    def get(self, text: str, target_lang: str) -> str | None:
        h = segment_hash(text, target_lang, self.user_id)
        with self._lock, db_module.get_engine().connect() as conn:
            row = conn.execute(
                sa.select(segment_cache.c.translated_text).where(
                    segment_cache.c.hash == h, segment_cache.c.user_id == self.user_id
                )
            ).first()
        return row[0] if row else None

    def set(
        self,
        text: str,
        target_lang: str,
        translated: str,
        provider_used: str | None = None,
    ) -> None:
        h = segment_hash(text, target_lang, self.user_id)
        now = time.time()
        with self._lock, db_module.get_engine().begin() as conn:
            stmt = upsert(segment_cache).values(
                hash=h,
                user_id=self.user_id,
                source_text=text,
                translated_text=translated,
                target_lang=target_lang,
                provider_used=provider_used,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["hash"],
                set_={
                    "user_id": self.user_id,
                    "translated_text": translated,
                    "provider_used": provider_used,
                    "updated_at": now,
                },
            )
            conn.execute(stmt)

    def clear(self) -> int:
        with self._lock, db_module.get_engine().begin() as conn:
            result = conn.execute(segment_cache.delete().where(segment_cache.c.user_id == self.user_id))
            return result.rowcount

    def count(self) -> int:
        with self._lock, db_module.get_engine().connect() as conn:
            result = conn.execute(
                sa.select(sa.func.count())
                .select_from(segment_cache)
                .where(segment_cache.c.user_id == self.user_id)
            )
        return int(result.scalar() or 0)
