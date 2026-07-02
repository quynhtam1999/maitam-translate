"""Account endpoints: login, logout, current user, change password, and
admin-only user management (create/list/delete/reset password).

There is no public self-registration — only an admin can create accounts.
"""
from fastapi import APIRouter, HTTPException, Request, Response, status

from ..core import auth_store
from ..core.auth import (
    AdminUser,
    CurrentUser,
    clear_session_cookie,
    get_session_token,
    set_session_cookie,
)
from ..core.config import get_settings
from ..models.auth import (
    AuthResponse,
    ChangePasswordRequest,
    CreateUserRequest,
    LoginRequest,
    ResetPasswordRequest,
    UserResponse,
)
from ..services.user_data import purge_user_data

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, response: Response):
    try:
        user = auth_store.verify_user(req.username, req.password)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không đúng.",
        )
    _login_response(response, user["id"])
    return AuthResponse(user=UserResponse(**user))


@router.post("/logout")
async def logout(request: Request, response: Response):
    auth_store.delete_session(get_session_token(request))
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser):
    return UserResponse(**current_user)


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, request: Request, current_user: CurrentUser):
    try:
        verified = auth_store.verify_user(current_user["username"], req.current_password)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    if verified is None:
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng.")

    auth_store.set_password(current_user["id"], req.new_password)
    current_token = get_session_token(request)
    auth_store.delete_sessions_for_user(current_user["id"], keep_token=current_token)
    return {"ok": True}


# --- Admin: user management ---


@router.get("/users", response_model=list[UserResponse])
async def list_users(admin: AdminUser):
    return [UserResponse(**u) for u in auth_store.list_users()]


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(req: CreateUserRequest, admin: AdminUser):
    try:
        user = auth_store.create_user(req.username, req.password, is_admin=req.is_admin)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return UserResponse(**user)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: AdminUser):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Không thể tự xóa tài khoản của chính mình.")
    target = auth_store.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    if target["is_admin"] and auth_store.count_admins() <= 1:
        raise HTTPException(status_code=400, detail="Không thể xóa quản trị viên cuối cùng.")

    auth_store.delete_user(user_id)
    purge_user_data(user_id)
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: str, req: ResetPasswordRequest, admin: AdminUser):
    target = auth_store.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    auth_store.set_password(user_id, req.new_password)
    auth_store.delete_sessions_for_user(user_id)
    return {"ok": True}


def _login_response(response: Response, user_id: str) -> None:
    ttl = int(get_settings().auth_session_days * 24 * 60 * 60)
    token, _expires_at = auth_store.create_session(user_id, ttl)
    set_session_cookie(response, token, ttl)
