from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class UserRegisterRequest(BaseModel):
    email: str
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("Invalid email address.")
        return normalized

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Username cannot be empty.")
        return normalized


class UserLoginRequest(BaseModel):
    identifier: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Identifier cannot be empty.")
        return normalized


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
