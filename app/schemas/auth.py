"""Pydantic cho 6 API auth (A2). Tên trường tiếng Anh theo đúng PDF API."""

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=120, description="username hoặc email")
    password: str = Field(min_length=1, max_length=200)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=200)


class LogoutIn(BaseModel):
    refresh_token: str = ""   # cho phép rỗng: access còn sống nhưng refresh đã mất


class ChangePasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class ForgotPasswordIn(BaseModel):
    username: str = Field(min_length=1, max_length=120)
