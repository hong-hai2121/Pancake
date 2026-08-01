"""Schema Pydantic cho API hội thoại (CONV-001…006)."""

from pydantic import BaseModel, Field


class AttachCustomerIn(BaseModel):
    """CONV-004 — gắn hội thoại vào khách."""

    customer_id: int = Field(gt=0)


class AssignIn(BaseModel):
    """CONV-005 — gán nhân viên phụ trách; user_id rỗng = bỏ gán."""

    user_id: int | None = Field(default=None, gt=0)


class SendMessageIn(BaseModel):
    """CONV-006 — gửi tin thật qua Pancake."""

    message: str = Field(min_length=1, max_length=5000)
