"""Cache đoạn dịch theo hash NỘI DUNG (THAMKHAO A3).

Khóa cache = sha256(chuẩn_hóa(text) + '|' + target_lang), KHÔNG gồm model — nên đổi
model giữa chừng vẫn trúng cache. Ghi ngay sau mỗi đoạn/lô -> mất điện/hết quota không
mất phần đã dịch. Cache không tự xóa (dịch lại cùng file khỏi tốn quota).
"""
import hashlib
import sqlite3
import threading
import time
from pathlib import Path


def segment_hash(text: str, target_lang: str) -> str:
    normalized = " ".join(text.split()).strip()
    key = f"{normalized}|{target_lang}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class SegmentCache:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS segment_cache (
                hash            TEXT PRIMARY KEY,
                source_text     TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                target_lang     TEXT NOT NULL,
                provider_used   TEXT,
                created_at      REAL NOT NULL,
                updated_at      REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, text: str, target_lang: str) -> str | None:
        h = segment_hash(text, target_lang)
        with self._lock:
            row = self._conn.execute(
                "SELECT translated_text FROM segment_cache WHERE hash = ?", (h,)
            ).fetchone()
        return row[0] if row else None

    def set(self, text: str, target_lang: str, translated: str, provider_used: str | None = None) -> None:
        h = segment_hash(text, target_lang)
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO segment_cache
                   (hash, source_text, translated_text, target_lang, provider_used, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(hash) DO UPDATE SET
                     translated_text = excluded.translated_text,
                     provider_used   = excluded.provider_used,
                     updated_at      = excluded.updated_at""",
                (h, text, translated, target_lang, provider_used, now, now),
            )
            self._conn.commit()

    def clear(self) -> int:
        """Xóa toàn bộ cache (⚙ Cài đặt → Xóa bộ nhớ đệm dịch)."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM segment_cache")
            self._conn.commit()
            return cur.rowcount
