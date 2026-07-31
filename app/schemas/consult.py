"""Pydantic cho API hồ sơ tư vấn + sàng lọc an toàn (B5 — FR-050…053).

Chỉ kiểm hình dạng dữ liệu; luật nghiệp vụ (red flag, chặn đề xuất, câu hỏi
bắt buộc...) nằm ở services/consult_service.py.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

_FREQUENCY = "^(rare|sometimes|often|daily|constant)$"
_MEAL = "^(truoc_an|sau_an|khi_doi|khong_lien_quan)$"


class SessionCreateIn(BaseModel):
    customer_id: int
    lead_id: int | None = None
    channel: str | None = Field(default=None, pattern="^(chat|call|zalo|direct)$")


class AnswerIn(BaseModel):
    question_code: str = Field(min_length=1, max_length=60)
    answer_text: str | None = Field(default=None, max_length=2000)
    answer_value: float | None = None


class AnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1)


class SymptomSaveIn(BaseModel):
    symptom_id: int
    severity: int | None = Field(default=None, ge=0, le=10)
    frequency: str | None = Field(default=None, pattern=_FREQUENCY)
    started_at: datetime | None = None
    is_primary: bool = False
    occurs_when: str | None = Field(default=None, max_length=200)
    meal_relation: str | None = Field(default=None, pattern=_MEAL)
    note: str | None = Field(default=None, max_length=1000)


class SymptomUpdateIn(BaseModel):
    severity: int | None = Field(default=None, ge=0, le=10)
    frequency: str | None = Field(default=None, pattern=_FREQUENCY)
    started_at: datetime | None = None
    is_primary: bool | None = None
    occurs_when: str | None = Field(default=None, max_length=200)
    meal_relation: str | None = Field(default=None, pattern=_MEAL)
    note: str | None = Field(default=None, max_length=1000)


class ExaminationIn(BaseModel):
    exam_type: str = Field(pattern="^(noi_soi|hp|sieu_am|xet_nghiem|khac)$")
    exam_date: date | None = None
    facility: str | None = Field(default=None, max_length=200)
    conclusion: str | None = Field(default=None, max_length=2000)
    file_url: str | None = Field(default=None, max_length=500)


class MedicationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dosage: str | None = Field(default=None, max_length=200)
    duration: str | None = Field(default=None, max_length=200)
    is_active: bool = True
    effect: str | None = Field(default=None, max_length=500)
    reaction: str | None = Field(default=None, max_length=500,
                                 description="có nội dung = FR-052 tự mở ca chuyên môn")


class PreviousTreatmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    duration: str | None = Field(default=None, max_length=200)
    result: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=1000)


class ScreeningIn(BaseModel):
    screening_type: str = Field(min_length=1, max_length=40)
    value: str | None = Field(default=None, max_length=500)


class EscalationIn(BaseModel):
    reason: str = Field(default="", max_length=1000)


class ResolveIn(BaseModel):
    resolution: str = Field(default="", max_length=2000)
    go_canh_bao: bool = Field(
        default=False,
        description="True = kết luận an toàn: gỡ phiếu sàng lọc + tính lại cờ",
    )
