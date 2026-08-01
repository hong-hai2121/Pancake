"""Schema vào/ra B10 — cơ hội mua lại, tính ngày hết, khách ngủ, chiến dịch."""

from datetime import date

from pydantic import BaseModel, Field


class RepurchaseCreateIn(BaseModel):
    customer_id: int = Field(gt=0)
    current_treatment_id: int | None = Field(None, gt=0)
    next_template_id: int | None = Field(None, gt=0)
    owner_id: int | None = Field(None, gt=0)
    expected_close_date: date | None = None
    expected_value: float | None = Field(None, ge=0)
    readiness: str | None = None   # bộ repurchase_readiness (ref_codes)


class RepurchaseUpdateIn(BaseModel):
    current_treatment_id: int | None = Field(None, gt=0)
    next_template_id: int | None = Field(None, gt=0)
    owner_id: int | None = Field(None, gt=0)
    expected_close_date: date | None = None
    expected_value: float | None = Field(None, ge=0)
    readiness: str | None = None


class MoveStageIn(BaseModel):
    stage: str                     # contacted | negotiating | won | lost | postponed
    reason: str = ""               # bắt buộc khi lost (nếu chưa có lý do sẵn)


class LostReasonIn(BaseModel):
    ma_ly_do: str = ""             # mã trong lead_reasons (9 lý do BRD)
    note: str = ""


class CalcEndDateIn(BaseModel):
    """FR-120 — mọi trường đều tùy chọn: thiếu thì lấy từ liệu trình/care plan."""
    start_date: date | None = None
    so_ngay: float | None = Field(None, gt=0)
    so_luong: float | None = Field(None, gt=0)
    so_ngay_moi_don_vi: float | None = Field(None, gt=0)
    adherence_level: str | None = None
    tam_dung_ngay: int = Field(0, ge=0)
    con_hang_cu_ngay: int = Field(0, ge=0)


class AssignCampaignIn(BaseModel):
    customer_ids: list[int]
    campaign_id: int | None = Field(None, gt=0)
    ten_moi: str = ""              # đặt tên là tạo chiến dịch mới
    assigned_to: int | None = Field(None, gt=0)
    tao_viec: bool = True
