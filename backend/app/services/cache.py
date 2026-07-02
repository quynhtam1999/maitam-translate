"""Per-user translation cache keyed by normalized text and target language."""
import hashlib
import sqlite3
import threading
import time
from pathlib import Path


def segment_hash(text: str, target_lang: str, user_id: str = "global") -> str:
    normalized = " ".join(text.split()).strip()
    key = f"{user_id}|{normalized}|{target_lang}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class SegmentCache:
    def __init__(self, db_path: Path, user_id: str = "global"):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_id = user_id or "global"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS segment_cache (
                hash            TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL DEFAULT 'global',
                source_text     TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                target_lang     TEXT NOT NULL,
                provider_used   TEXT,
                created_at      REAL NOT NULL,
                updated_at      REAL NOT NULL
            )
            """
        )
        columns = {
            row[1] for row in self._conn.execute("PRAGMA table_info(segment_cache)").fetchall()
        }
        if "user_id" not in columns:
            self._conn.execute(
                "ALTER TABLE segment_cache ADD COLUMN user_id TEXT NOT NULL DEFAULT 'global'"
            )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_segment_cache_user_id ON segment_cache(user_id)"
        )
        self._conn.commit()

    def get(self, text: str, target_lang: str) -> str | None:
        h = segment_hash(text, target_lang, self.user_id)
        with self._lock:
            row = self._conn.execute(
                "SELECT translated_text FROM segment_cache WHERE hash = ? AND user_id = ?",
                (h, self.user_id),
            ).fetchone()
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
        with self._lock:
            self._conn.execute(
                """INSERT INTO segment_cache
                   (hash, user_id, source_text, translated_text, target_lang, provider_used, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(hash) DO UPDATE SET
                     user_id         = excluded.user_id,
                     translated_text = excluded.translated_text,
                     provider_used   = excluded.provider_used,
                     updated_at      = excluded.updated_at""",
                (h, self.user_id, text, translated, target_lang, provider_used, now, now),
            )
            self._conn.commit()

    def clear(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM segment_cache WHERE user_id = ?", (self.user_id,)
            )
            self._conn.commit()
            return cur.rowcount

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM segment_cache WHERE user_id = ?", (self.user_id,)
            ).fetchone()
        return int(row[0]) if row else 0
