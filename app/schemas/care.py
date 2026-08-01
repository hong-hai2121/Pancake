"""Schema vào/ra cho B9 — kế hoạch chăm, mốc, đánh giá, chuỗi không phản hồi.

Riêng PHIẾU CHĂM (CARE-STEP-001…011) nhận dict tự do: trường bắt buộc của
từng bước nằm trong ref_codes (BRD bảng 18) và được care_service kiểm —
khai Pydantic cứng ở đây là sai chỗ (thêm trường phải sửa code).
"""

from datetime import date, datetime

from pydantic import BaseModel, Field


class CarePlanCreateIn(BaseModel):
    customer_id: int = Field(gt=0)
    customer_treatment_id: int | None = Field(None, gt=0)
    owner_id: int | None = Field(None, gt=0)


class StepCompleteIn(BaseModel):
    result_code: str = ""          # RS01-RS12 (ref_codes care_result)
    note: str = ""


class StepRescheduleIn(BaseModel):
    planned_at: datetime
    reason: str


class StepSkipIn(BaseModel):
    reason: str


class AssessmentItemIn(BaseModel):
    symptom_id: int = Field(gt=0)
    current_score: float = Field(ge=0, le=10)
    before_score: float | None = Field(None, ge=0, le=10)


class AssessmentsIn(BaseModel):
    items: list[AssessmentItemIn]


class NoResponseOpenIn(BaseModel):
    care_plan_step_id: int | None = Field(None, gt=0)


class NoResponseAttemptIn(BaseModel):
    channel: str                   # message | call — thứ tự chuẩn FR-110
    result: str = ""               # bộ contact_result
    note: str = ""


class NoResponseCloseIn(BaseModel):
    outcome: str                   # responded | lost_contact | do_not_contact
    reason: str = ""


class DoNotContactIn(BaseModel):
    reason: str


class StartUsageIn(BaseModel):
    """CARE-STEP-003 (giữ đúng mẫu JSON trong danh sách API) — các phiếu khác
    dùng dict tự do, riêng phiếu này đặc tả in rõ 3 trường nên khai để làm mẫu."""
    actual_start_date: date | None = None
    started: bool
    delay_reason: str | None = None
