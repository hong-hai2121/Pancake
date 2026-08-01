"""Schema Pydantic cho API bàn giao Sale→CSKH (HANDOVER-001…006)."""

from datetime import date

from pydantic import BaseModel, Field


class HandoverCreateIn(BaseModel):
    """HANDOVER-002 — tạo phiếu tay từ một đơn đã giao thành công."""

    order_id: int = Field(gt=0)


class HandoverUpdateIn(BaseModel):
    """Sửa nội dung phiếu (màn 25) — trường nào gửi lên thì sửa trường đó."""

    customer_condition: str | None = None
    main_symptoms: str | None = None
    treatment_summary: str | None = None
    dose_text: str | None = None
    current_medications: str | None = None
    comorbidities: str | None = None
    notes: str | None = None
    concerns: str | None = None
    sale_discussed: str | None = None
    promises_made: str | None = None
    cskh_watch_points: str | None = None
    expected_start_date: date | None = None


class HandoverReturnIn(BaseModel):
    """HANDOVER-005 — trả lại Sale, bắt buộc lý do."""

    reason: str = Field(min_length=3, max_length=1000)


class HandoverAssignIn(BaseModel):
    """HANDOVER-006 — gán CSKH phụ trách phiếu."""

    user_id: int = Field(gt=0)
