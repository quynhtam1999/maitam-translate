"""Schemas for account login, admin user management, and the authenticated user."""
from pydantic import BaseModel, Field, field_validator


def _clean_username(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError("Ten dang nhap khong duoc de trong")
    return cleaned


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        return " ".join(value.strip().split())


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=256)
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        return _clean_username(value)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)


class UserResponse(BaseModel):
    id: str
    username: str
    is_admin: bool = False
    created_at: float


class AuthResponse(BaseModel):
    user: UserResponse
