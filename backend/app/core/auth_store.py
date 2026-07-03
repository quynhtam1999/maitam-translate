"""Accounts, sessions, and encrypted per-user API keys (SQLAlchemy Core).

Chạy trên SQLite (dev) hoặc Postgres/Neon (deploy) qua engine dùng chung ở `core/db.py`.
Passwords are stored as PBKDF2-HMAC-SHA256 hashes. Session cookies contain only
random tokens; the database stores token hashes. Provider API keys are encrypted
at rest with AES-GCM (authenticated) using a server-side secret, then masked in
every response. Legacy "v1" (HMAC keystream) payloads still decrypt for backward
compatibility; new writes always use AES-GCM ("v2").
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import db as db_module
from .db import sessions, upsert, user_api_keys, users

PBKDF2_ITERATIONS = 210_000
SESSION_TOKEN_BYTES = 32
KEY_NONCE_BYTES = 16       # legacy v1 keystream nonce
GCM_NONCE_BYTES = 12       # AES-GCM nonce
AUTH_COOKIE_NAME = "mtt_session"

# Chống dò mật khẩu: khoá tạm theo tên đăng nhập sau nhiều lần sai liên tiếp.
LOGIN_MAX_ATTEMPTS = 8
LOGIN_LOCKOUT_SECONDS = 300

_lock = threading.Lock()
_secret: bytes | None = None

# username_norm -> {"count": int, "until": float}. Đủ nhẹ cho công cụ nội bộ.
_login_attempts: dict[str, dict[str, float]] = {}
_attempts_lock = threading.Lock()


def init_secret(secret_path: Path, configured_secret: str = "") -> None:
    """Khởi tạo khóa mã hóa AES-GCM. Bảng DB đã được tạo qua `db.init()`."""
    global _secret
    _secret = _load_or_create_secret(secret_path, configured_secret)


def create_user(username: str, password: str, is_admin: bool = False) -> dict[str, Any]:
    username = username.strip()
    norm = _normalize_username(username)
    if len(password) < 8:
        raise ValueError("Mat khau can toi thieu 8 ky tu")

    now = time.time()
    user_id = uuid.uuid4().hex
    try:
        with _lock, db_module.get_engine().begin() as conn:
            conn.execute(
                users.insert(),
                {
                    "id": user_id,
                    "username": username,
                    "username_norm": norm,
                    "password_hash": _hash_password(password),
                    "is_admin": int(is_admin),
                    "created_at": now,
                },
            )
    except sa.exc.IntegrityError as exc:
        raise ValueError("Ten dang nhap da ton tai") from exc
    return {"id": user_id, "username": username, "is_admin": is_admin, "created_at": now}


def ensure_admin(username: str, password: str) -> None:
    """Bootstrap the first admin account from env vars, idempotently.

    If no admin exists yet: creates the account (or promotes it if the
    username already exists). Never overwrites an existing password.
    """
    username = username.strip()
    if not username or not password:
        return
    if count_admins() > 0:
        return
    row = _get_user_by_norm(_normalize_username(username))
    if row is None:
        create_user(username, password, is_admin=True)
        return
    with _lock, db_module.get_engine().begin() as conn:
        conn.execute(users.update().where(users.c.id == row["id"]).values(is_admin=1))


def count_admins() -> int:
    with _lock, db_module.get_engine().connect() as conn:
        result = conn.execute(
            sa.select(sa.func.count()).select_from(users).where(users.c.is_admin == 1)
        )
        return int(result.scalar() or 0)


def list_users() -> list[dict[str, Any]]:
    with _lock, db_module.get_engine().connect() as conn:
        rows = conn.execute(users.select().order_by(users.c.created_at.asc())).mappings().all()
    return [_row_to_user(row) for row in rows]


def delete_user(user_id: str) -> bool:
    with _lock, db_module.get_engine().begin() as conn:
        result = conn.execute(users.delete().where(users.c.id == user_id))
    return result.rowcount > 0


def set_password(user_id: str, new_password: str) -> None:
    if len(new_password) < 8:
        raise ValueError("Mat khau can toi thieu 8 ky tu")
    with _lock, db_module.get_engine().begin() as conn:
        conn.execute(
            users.update().where(users.c.id == user_id).values(password_hash=_hash_password(new_password))
        )


def delete_sessions_for_user(user_id: str, keep_token: str | None = None) -> None:
    keep_hash = _hash_token(keep_token) if keep_token else None
    with _lock, db_module.get_engine().begin() as conn:
        if keep_hash:
            conn.execute(
                sessions.delete().where(
                    sessions.c.user_id == user_id, sessions.c.token_hash != keep_hash
                )
            )
        else:
            conn.execute(sessions.delete().where(sessions.c.user_id == user_id))


def verify_user(username: str, password: str) -> dict[str, Any] | None:
    norm = _normalize_username(username)
    if _is_locked_out(norm):
        raise PermissionError("Tài khoản tạm khóa do đăng nhập sai nhiều lần. Thử lại sau.")
    row = _get_user_by_norm(norm)
    if row is None or not _verify_password(password, row["password_hash"]):
        _record_failed_login(norm)
        return None
    _clear_failed_login(norm)
    return _row_to_user(row)


def _is_locked_out(norm: str) -> bool:
    with _attempts_lock:
        entry = _login_attempts.get(norm)
        if not entry:
            return False
        if entry["count"] < LOGIN_MAX_ATTEMPTS:
            return False
        if time.time() >= entry["until"]:
            del _login_attempts[norm]
            return False
        return True


def _record_failed_login(norm: str) -> None:
    with _attempts_lock:
        entry = _login_attempts.setdefault(norm, {"count": 0, "until": 0.0})
        entry["count"] += 1
        if entry["count"] >= LOGIN_MAX_ATTEMPTS:
            entry["until"] = time.time() + LOGIN_LOCKOUT_SECONDS


def _clear_failed_login(norm: str) -> None:
    with _attempts_lock:
        _login_attempts.pop(norm, None)


def get_user(user_id: str) -> dict[str, Any] | None:
    with _lock, db_module.get_engine().connect() as conn:
        row = conn.execute(users.select().where(users.c.id == user_id)).mappings().first()
    return _row_to_user(row) if row else None


def create_session(user_id: str, ttl_seconds: int) -> tuple[str, float]:
    token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    now = time.time()
    expires_at = now + ttl_seconds
    with _lock, db_module.get_engine().begin() as conn:
        conn.execute(
            sessions.insert(),
            {
                "token_hash": _hash_token(token),
                "user_id": user_id,
                "created_at": now,
                "expires_at": expires_at,
            },
        )
    return token, expires_at


def get_user_by_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    token_hash = _hash_token(token)
    now = time.time()
    with _lock, db_module.get_engine().begin() as conn:
        conn.execute(sessions.delete().where(sessions.c.expires_at <= now))
        row = conn.execute(
            sa.select(users)
            .select_from(sessions.join(users, users.c.id == sessions.c.user_id))
            .where(sessions.c.token_hash == token_hash, sessions.c.expires_at > now)
        ).mappings().first()
    return _row_to_user(row) if row else None


def renew_session_if_stale(token: str | None, ttl_seconds: int, min_remaining_seconds: int) -> bool:
    """Kéo dài expires_at = now + ttl nếu phiên còn hạn nhưng sắp hết (rolling session).

    Trả về True nếu có gia hạn (để lớp trên set lại cookie).
    """
    if not token:
        return False
    now = time.time()
    new_expires = now + ttl_seconds
    with _lock, db_module.get_engine().begin() as conn:
        result = conn.execute(
            sessions.update()
            .where(
                sessions.c.token_hash == _hash_token(token),
                sessions.c.expires_at > now,
                sessions.c.expires_at < now + min_remaining_seconds,
            )
            .values(expires_at=new_expires)
        )
    return result.rowcount > 0


def delete_session(token: str | None) -> None:
    if not token:
        return
    with _lock, db_module.get_engine().begin() as conn:
        conn.execute(sessions.delete().where(sessions.c.token_hash == _hash_token(token)))


def update_api_keys(
    user_id: str,
    *,
    gemini_key: str | None = None,
    qwen_key: str | None = None,
    qwen_base_url: str | None = None,
    qwen_model: str | None = None,
) -> None:
    now = time.time()
    sets: dict[str, Any] = {"updated_at": now}
    if gemini_key is not None:
        sets["gemini_key_enc"] = _seal(gemini_key.strip()) if gemini_key.strip() else None
    if qwen_key is not None:
        sets["qwen_key_enc"] = _seal(qwen_key.strip()) if qwen_key.strip() else None
    if qwen_base_url is not None:
        sets["qwen_base_url"] = qwen_base_url.strip() or None
    if qwen_model is not None:
        sets["qwen_model"] = qwen_model.strip() or None
    if len(sets) == 1:
        return

    with _lock, db_module.get_engine().begin() as conn:
        stmt = upsert(user_api_keys).values(user_id=user_id, updated_at=now)
        stmt = stmt.on_conflict_do_nothing(index_elements=["user_id"])
        conn.execute(stmt)
        conn.execute(user_api_keys.update().where(user_api_keys.c.user_id == user_id).values(**sets))


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
    options: dict[str, str] = {}
    base_url = get_qwen_base_url(user_id)
    if base_url:
        options["qwen_base_url"] = base_url
    model = get_qwen_model(user_id)
    if model:
        options["qwen_model"] = model
    return options


def get_qwen_base_url(user_id: str) -> str:
    with _lock, db_module.get_engine().connect() as conn:
        row = conn.execute(
            sa.select(user_api_keys.c.qwen_base_url).where(user_api_keys.c.user_id == user_id)
        ).first()
    return str(row[0] or "") if row else ""


def get_qwen_model(user_id: str) -> str:
    with _lock, db_module.get_engine().connect() as conn:
        row = conn.execute(
            sa.select(user_api_keys.c.qwen_model).where(user_api_keys.c.user_id == user_id)
        ).first()
    return str(row[0] or "") if row else ""


def get_api_keys(user_id: str) -> dict[str, str]:
    with _lock, db_module.get_engine().connect() as conn:
        row = conn.execute(
            sa.select(user_api_keys.c.gemini_key_enc, user_api_keys.c.qwen_key_enc).where(
                user_api_keys.c.user_id == user_id
            )
        ).mappings().first()
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


def _get_user_by_norm(norm: str) -> Any:
    with _lock, db_module.get_engine().connect() as conn:
        return conn.execute(users.select().where(users.c.username_norm == norm)).mappings().first()


def _row_to_user(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "is_admin": bool(row["is_admin"]),
        "created_at": row["created_at"],
    }


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
    """Encrypt with AES-GCM ("v2"). New writes always use this format."""
    data = plain_text.encode("utf-8")
    nonce = secrets.token_bytes(GCM_NONCE_BYTES)
    aesgcm = AESGCM(_derive_key(b"mtt-key-encryption-v2")[:32])
    cipher = aesgcm.encrypt(nonce, data, None)
    payload = b"v2" + nonce + cipher
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _open(sealed: str) -> str:
    raw = base64.urlsafe_b64decode(sealed.encode("ascii"))
    if len(raw) < 2:
        raise ValueError("Invalid encrypted key payload")
    version, body = raw[:2], raw[2:]
    if version == b"v2":
        nonce, cipher = body[:GCM_NONCE_BYTES], body[GCM_NONCE_BYTES:]
        aesgcm = AESGCM(_derive_key(b"mtt-key-encryption-v2")[:32])
        return aesgcm.decrypt(nonce, cipher, None).decode("utf-8")
    if version == b"v1":
        return _open_v1(raw)
    raise ValueError("Unknown encrypted key payload version")


def _open_v1(raw: bytes) -> str:
    """Legacy HMAC-keystream format, kept read-only for previously saved keys."""
    if len(raw) < 2 + KEY_NONCE_BYTES + 32:
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
    except (ValueError, UnicodeDecodeError, InvalidTag):
        return ""


def _xor_stream(data: bytes, key: bytes, nonce: bytes) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < len(data):
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(a ^ b for a, b in zip(data, out))
