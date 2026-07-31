"""Pydantic vào/ra cho nhóm lead & pipeline (B3 — LEAD-001…011, PIPELINE-001…004)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Temperature = Literal["nong", "am", "lanh"]
Priority = Literal["low", "normal", "high", "urgent"]


class LeadCreateIn(BaseModel):
    customer_id: int
    pipeline_id: int | None = None      # rỗng = pipeline "Bán mới"
    source: str | None = None
    temperature: Temperature | None = None
    priority: Priority = "normal"
    owner_id: int | None = None         # rỗng + auto_assign = chia vòng tròn
    auto_assign: bool = True


class LeadUpdateIn(BaseModel):
    """LEAD-004 — chỉ trường phụ; giai đoạn/người giữ đi đường riêng có luật."""
    source: str | None = None
    temperature: Temperature | None = None
    priority: Priority | None = None
    next_action_at: datetime | None = None


class MoveStageIn(BaseModel):
    """LEAD-005 — đúng khuôn ví dụ trong tài liệu API."""
    stage_id: int
    reason: str | None = None
    note: str | None = None
    next_action_at: datetime | None = None
    lost_reason_id: int | None = None   # tiện tay khi chuyển sang giai đoạn thua


class AssignIn(BaseModel):
    user_id: int
    reason: str | None = None           # bắt buộc khi lead ĐANG có người giữ (FR-031)


class LostReasonIn(BaseModel):
    lost_reason_id: int
    note: str | None = None
    evidence_type: Literal["message", "call", "note"] | None = None
    evidence_id: int | None = None


class CloseIn(BaseModel):
    """LEAD-011 — stage_code phải là giai đoạn kết thúc của pipeline."""
    stage_code: str = Field(examples=["da_chot", "tu_choi"])
    reason: str | None = None
    note: str | None = None
    lost_reason_id: int | None = None


class PipelineCreateIn(BaseModel):
    name: str
    type: Literal["new_sale", "upsell", "reactivation"] | None = None


class StageIn(BaseModel):
    code: str
    name: str
    sort_order: int = 0
    is_closed: bool = False


class StagesUpdateIn(BaseModel):
    stages: list[StageIn]
