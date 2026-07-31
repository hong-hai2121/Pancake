"""Pydantic vào/ra nhóm khách hàng (B1 — CUSTOMER-001…012, IDENTITY-001/002)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

AssignmentType = Literal["sale", "cskh", "chuyen_mon"]


class CustomerCreateIn(BaseModel):
    """FR-020 — tên + (SĐT hoặc định danh MXH) + nguồn bắt buộc; luật ở service."""
    full_name: str
    primary_phone: str | None = None
    gender: Literal["male", "female", "other"] | None = None
    province: str | None = None
    source: str
    owner_id: int | None = None
    assignment_type: AssignmentType = "sale"
    # định danh MXH đi kèm (thay cho SĐT được)
    platform: str | None = None
    external_customer_id: str | None = None
    psid: str | None = None
    page_id: int | None = None
    force: bool = False        # true = đã xem cảnh báo trùng, vẫn tạo mới


class CustomerUpdateIn(BaseModel):
    full_name: str | None = None
    primary_phone: str | None = None
    gender: Literal["male", "female", "other"] | None = None
    birth_date: date | None = None
    province: str | None = None
    source: str | None = None
    status: str | None = None
    customer_code: str | None = None


class MergeIn(BaseModel):
    """CUSTOMER-007 — đúng khuôn ví dụ trong tài liệu API."""
    primary_customer_id: int
    duplicate_customer_ids: list[int]


class TagIn(BaseModel):
    tag_id: int | None = None
    name: str | None = None
    type: str | None = None


class CustomerAssignIn(BaseModel):
    user_id: int
    assignment_type: AssignmentType = "sale"
    reason: str | None = None


class IdentityIn(BaseModel):
    platform: str | None = None
    external_customer_id: str | None = None
    psid: str | None = None
    page_id: int | None = None


class DeleteIn(BaseModel):
    reason: str | None = None
