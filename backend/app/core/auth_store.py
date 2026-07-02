"""SQLite-backed accounts, sessions, and encrypted per-user API keys.

Passwords are stored as PBKDF2-HMAC-SHA256 hashes. Session cookies contain only
random tokens; the database stores token hashes. Provider API keys are encrypted
at rest with a server-side secret, then masked in every response.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

PBKDF2_ITERATIONS = 210_000
SESSION_TOKEN_BYTES = 32
KEY_NONCE_BYTES = 16
AUTH_COOKIE_NAME = "mtt_session"

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_secret: bytes | None = None


def init(db_path: Path, secret_path: Path, configured_secret: str = "") -> None:
    global _conn, _secret
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _secret = _load_or_create_secret(secret_path, configured_secret)
    _conn = sqlite3.connect(str(db_path), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    with _lock:
        _db().execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                username      TEXT NOT NULL,
                username_norm TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at    REAL NOT NULL
            )
            """
        )
        _db().execute(
            """
            CREATE TABLE IF NOT EXISTS user_api_keys (
                user_id         TEXT PRIMARY KEY,
                gemini_key_enc  TEXT,
                qwen_key_enc    TEXT,
                qwen_base_url   TEXT,
                updated_at      REAL NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        _db().execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        _db().execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
        columns = {
            row[1] for row in _db().execute("PRAGMA table_info(user_api_keys)").fetchall()
        }
        if "qwen_base_url" not in columns:
            _db().execute("ALTER TABLE user_api_keys ADD COLUMN qwen_base_url TEXT")
        _db().commit()


def _db() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("auth_store has not been initialized")
    return _conn


def create_user(username: str, password: str) -> dict[str, Any]:
    username = username.strip()
    norm = _normalize_username(username)
    if len(password) < 8:
        raise ValueError("Mat khau can toi thieu 8 ky tu")

    now = time.time()
    user_id = uuid.uuid4().hex
    try:
        with _lock:
            _db().execute(
                """INSERT INTO users (id, username, username_norm, password_hash, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, username, norm, _hash_password(password), now),
            )
            _db().commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Ten dang nhap da ton tai") from exc
    return {"id": user_id, "username": username, "created_at": now}


def verify_user(username: str, password: str) -> dict[str, Any] | None:
    row = _get_user_by_norm(_normalize_username(username))
    if row is None:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    return _row_to_user(row)


def get_user(user_id: str) -> dict[str, Any] | None:
    with _lock:
        row = _db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def create_session(user_id: str, ttl_seconds: int) -> tuple[str, float]:
    token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    now = time.time()
    expires_at = now + ttl_seconds
    with _lock:
        _db().execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_hash_token(token), user_id, now, expires_at),
        )
        _db().commit()
    return token, expires_at


def get_user_by_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    token_hash = _hash_token(token)
    now = time.time()
    with _lock:
        _db().execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        row = _db().execute(
            """SELECT users.* FROM sessions
               JOIN users ON users.id = sessions.user_id
               WHERE sessions.token_hash = ? AND sessions.expires_at > ?""",
            (token_hash, now),
        ).fetchone()
        _db().commit()
    return _row_to_user(row) if row else None


def delete_session(token: str | None) -> None:
    if not token:
        return
    with _lock:
        _db().execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
        _db().commit()


def update_api_keys(
    user_id: str,
    *,
    gemini_key: str | None = None,
    qwen_key: str | None = None,
    qwen_base_url: str | None = None,
) -> None:
    now = time.time()
    sets: list[str] = ["updated_at = ?"]
    params: list[Any] = [now]
    if gemini_key is not None:
        sets.append("gemini_key_enc = ?")
        params.append(_seal(gemini_key.strip()) if gemini_key.strip() else None)
    if qwen_key is not None:
        sets.append("qwen_key_enc = ?")
        params.append(_seal(qwen_key.strip()) if qwen_key.strip() else None)
    if qwen_base_url is not None:
        sets.append("qwen_base_url = ?")
        params.append(qwen_base_url.strip() or None)
    if len(sets) == 1:
        return

    with _lock:
        _db().execute(
            """INSERT INTO user_api_keys (user_id, updated_at)
               VALUES (?, ?)
               ON CONFLICT(user_id) DO NOTHING""",
            (user_id, now),
        )
        params.append(user_id)
        _db().execute(f"UPDATE user_api_keys SET {', '.join(sets)} WHERE user_id = ?", params)
        _db().commit()


def get_provider_api_key(user_id: str, provider_name: str) -> str | None:
    keys = get_api_keys(user_id)
    if provider_name in ("gemini", "gemma"):
        return keys.get("gemini") or None
    if provider_name == "qwen":
        return keys.get("qwen") or None
    return None


def get_provider_options(user_id: str, provider_name: str) -> dict[str, str]:
    if provider_name != "qwen":
        return {}
    base_url = get_qwen_base_url(user_id)
    return {"qwen_base_url": base_url} if base_url else {}


def get_qwen_base_url(user_id: str) -> str:
    with _lock:
        row = _db().execute(
            "SELECT qwen_base_url FROM user_api_keys WHERE user_id = ?", (user_id,)
        ).fetchone()
    return str(row["qwen_base_url"] or "") if row else ""


def get_api_keys(user_id: str) -> dict[str, str]:
    with _lock:
        row = _db().execute(
            "SELECT gemini_key_enc, qwen_key_enc FROM user_api_keys WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return {"gemini": "", "qwen": ""}
    return {
        "gemini": _safe_open(row["gemini_key_enc"]) if row["gemini_key_enc"] else "",
        "qwen": _safe_open(row["qwen_key_enc"]) if row["qwen_key_enc"] else "",
    }


def get_api_key_status(user_id: str) -> dict[str, dict[str, str | bool]]:
    keys = get_api_keys(user_id)
    return {
        "gemini": {"set": bool(keys["gemini"]), "masked": mask_key(keys["gemini"])},
        "qwen": {"set": bool(keys["qwen"]), "masked": mask_key(keys["qwen"])},
    }


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return "****" + key[-4:]


def _get_user_by_norm(norm: str) -> sqlite3.Row | None:
    with _lock:
        return _db().execute("SELECT * FROM users WHERE username_norm = ?", (norm,)).fetchone()


def _row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}


def _normalize_username(username: str) -> str:
    return " ".join(username.strip().split()).casefold()


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PBKDF2_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def _verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_b64, digest_b64 = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_or_create_secret(secret_path: Path, configured_secret: str) -> bytes:
    configured_secret = configured_secret.strip()
    if configured_secret:
        return hashlib.sha256(configured_secret.encode("utf-8")).digest()

    secret_path.parent.mkdir(parents=True, exist_ok=True)
    if secret_path.exists():
        raw = secret_path.read_text(encoding="ascii").strip()
        return base64.urlsafe_b64decode(raw.encode("ascii"))

    secret = secrets.token_bytes(32)
    secret_path.write_text(base64.urlsafe_b64encode(secret).decode("ascii"), encoding="ascii")
    return secret


def _secret_bytes() -> bytes:
    if _secret is None:
        raise RuntimeError("auth encryption secret has not been initialized")
    return _secret


def _derive_key(label: bytes) -> bytes:
    return hmac.new(_secret_bytes(), label, hashlib.sha256).digest()


def _seal(plain_text: str) -> str:
    data = plain_text.encode("utf-8")
    nonce = secrets.token_bytes(KEY_NONCE_BYTES)
    cipher = _xor_stream(data, _derive_key(b"mtt-key-encryption-v1"), nonce)
    payload = b"v1" + nonce + cipher
    mac = hmac.new(_derive_key(b"mtt-key-auth-v1"), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + mac).decode("ascii")


def _open(sealed: str) -> str:
    raw = base64.urlsafe_b64decode(sealed.encode("ascii"))
    if len(raw) < 2 + KEY_NONCE_BYTES + 32 or raw[:2] != b"v1":
        raise ValueError("Invalid encrypted key payload")
    payload, mac = raw[:-32], raw[-32:]
    expected = hmac.new(_derive_key(b"mtt-key-auth-v1"), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Encrypted key authentication failed")
    nonce = payload[2 : 2 + KEY_NONCE_BYTES]
    cipher = payload[2 + KEY_NONCE_BYTES :]
    return _xor_stream(cipher, _derive_key(b"mtt-key-encryption-v1"), nonce).decode("utf-8")


def _safe_open(sealed: str) -> str:
    try:
        return _open(sealed)
    except (ValueError, UnicodeDecodeError):
        return ""


def _xor_stream(data: bytes, key: bytes, nonce: bytes) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < len(data):
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(a ^ b for a, b in zip(data, out))
