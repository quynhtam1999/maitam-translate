"""Account endpoints: register, login, logout, and current user."""
from fastapi import APIRouter, HTTPException, Request, Response, status

from ..core import auth_store
from ..core.auth import CurrentUser, clear_session_cookie, get_session_token, set_session_cookie
from ..core.config import get_settings
from ..models.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(req: RegisterRequest, response: Response):
    try:
        user = auth_store.create_user(req.username, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _login_response(response, user["id"])
    return AuthResponse(user=UserResponse(**user))


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, response: Response):
    user = auth_store.verify_user(req.username, req.password)
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


def _login_response(response: Response, user_id: str) -> None:
    ttl = int(get_settings().auth_session_days * 24 * 60 * 60)
    token, _expires_at = auth_store.create_session(user_id, ttl)
    set_session_cookie(response, token, ttl)
