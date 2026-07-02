"""Schemas for account login and the authenticated user."""
from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
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


class UserResponse(BaseModel):
    id: str
    username: str
    created_at: float


class AuthResponse(BaseModel):
    user: UserResponse
