"""Pydantic cho API quản lý nhân viên / vai trò / nhóm (A5)."""

from pydantic import BaseModel, EmailStr, Field


class UserCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str | None = Field(default=None, min_length=8, max_length=200,
                                 description="bỏ trống = hệ thống tự sinh")
    phone: str | None = Field(default=None, max_length=20)
    role_id: int | None = None
    team_id: int | None = None


class UserUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=60,
                                 pattern=r"^[a-zA-Z0-9_.-]+$")
    phone: str | None = Field(default=None, max_length=20)
    role_id: int | None = None
    team_id: int | None = None


class UserStatusIn(BaseModel):
    status: str = Field(pattern="^(active|inactive|suspended)$")
    reason: str = ""


class TransferIn(BaseModel):
    """USER-006 — đúng shape trong PDF API."""

    new_owner_id: int
    transfer_open_tasks: bool = True
    transfer_leads: bool = True
    transfer_care_plans: bool = True


class RoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)


class RolePermissionsIn(BaseModel):
    permissions: list[str] = Field(description="danh sách mã quyền, THAY toàn bộ")


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    department: str | None = Field(
        default=None, pattern="^(sale|cskh|marketing|chuyen_mon|admin)$"
    )
    manager_id: int | None = None


class TeamMembersIn(BaseModel):
    user_ids: list[int] = Field(min_length=1)
