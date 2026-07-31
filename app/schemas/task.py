"""Pydantic cho API công việc (B4 — TASK-001…009).

Luật nghiệp vụ (loại việc chuẩn, owner+hạn bắt buộc, kết quả khi đóng...)
nằm ở services/task_service.py — ở đây chỉ kiểm hình dạng dữ liệu.
"""

from datetime import datetime

from pydantic import BaseModel, Field

_PRIORITY = "^(low|normal|high|urgent)$"
_RELATED = "^(lead|order|care_plan_step|customer_treatment|repurchase_opportunity)$"


class TaskCreateIn(BaseModel):
    task_type: str = Field(min_length=1, max_length=40)
    assigned_to: int
    due_at: datetime
    title: str | None = Field(default=None, max_length=200)
    priority: str = Field(default="normal", pattern=_PRIORITY)
    customer_id: int | None = None
    related_type: str | None = Field(default=None, pattern=_RELATED)
    related_id: int | None = None


class TaskUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    task_type: str | None = Field(default=None, max_length=40)
    priority: str | None = Field(default=None, pattern=_PRIORITY)
    customer_id: int | None = None
    related_type: str | None = Field(default=None, pattern=_RELATED)
    related_id: int | None = None
    status: str | None = Field(default=None, pattern="^(in_progress|cancelled|done)$",
                               description="done bị service chặn — đóng qua /complete")
    reason: str | None = Field(default=None, max_length=300,
                               description="bắt buộc khi status=cancelled")


class TaskCompleteIn(BaseModel):
    result: str = Field(default="", max_length=2000,
                        description="mục 19 BRD: rỗng là bị chặn")


class TaskRescheduleIn(BaseModel):
    due_at: datetime
    reason: str = Field(default="", max_length=300)


class TaskReassignIn(BaseModel):
    user_id: int
    reason: str = Field(default="", max_length=300)
