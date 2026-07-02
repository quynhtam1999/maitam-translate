"""FastAPI auth dependencies and secure session cookie helpers."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status

from . import auth_store
from .config import get_settings


def get_session_token(request: Request) -> str | None:
    token = request.cookies.get(auth_store.AUTH_COOKIE_NAME)
    if token:
        return token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def get_current_user(request: Request, response: Response) -> dict:
    token = get_session_token(request)
    user = auth_store.get_user_by_session(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vui lòng đăng nhập để sử dụng ứng dụng.",
        )
    ttl = int(get_settings().auth_session_days * 24 * 60 * 60)
    # Rolling session: gia hạn khi còn dưới nửa thời hạn, để user còn hoạt động
    # (mở app ít nhất mỗi năm) không bao giờ bị buộc đăng nhập lại.
    if auth_store.renew_session_if_stale(token, ttl, ttl // 2):
        set_session_cookie(response, token, ttl)
    return user


CurrentUser = Annotated[dict, Depends(get_current_user)]


def get_current_admin(current_user: CurrentUser) -> dict:
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ quản trị viên mới có quyền thực hiện thao tác này.",
        )
    return current_user


AdminUser = Annotated[dict, Depends(get_current_admin)]


def set_session_cookie(response: Response, token: str, ttl_seconds: int) -> None:
    settings = get_settings()
    response.set_cookie(
        auth_store.AUTH_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=max(0, int(ttl_seconds)),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(auth_store.AUTH_COOKIE_NAME, path="/", samesite="lax")
