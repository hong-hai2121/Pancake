"""Pydantic cho API sản phẩm & liệu trình (B6 — FR-060…062)."""

from datetime import date

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ sản phẩm
class ProductCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    product_code: str | None = Field(default=None, max_length=60)
    product_type: str | None = Field(default=None, max_length=60)
    price: float | None = Field(default=None, ge=0)
    package: str | None = Field(default=None, max_length=200)
    units_per_package: int | None = Field(default=None, gt=0)
    usage_text: str | None = Field(default=None, max_length=4000)
    approved_claims: list[str] | None = None
    prohibited_claims: list[str] | None = None


class ProductUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    product_code: str | None = Field(default=None, max_length=60)
    product_type: str | None = Field(default=None, max_length=60)
    price: float | None = Field(default=None, ge=0)
    package: str | None = Field(default=None, max_length=200)
    units_per_package: int | None = Field(default=None, gt=0)


class ProductVersionIn(BaseModel):
    price: float | None = Field(default=None, ge=0)
    usage_text: str | None = Field(default=None, max_length=4000)
    approved_claims: list[str] | None = None
    prohibited_claims: list[str] | None = None


class ProductApproveIn(BaseModel):
    approve: bool = True


class ProductStatusIn(BaseModel):
    status: str = Field(pattern="^(active|inactive|discontinued)$")


# ------------------------------------------------------------------ mẫu liệu trình
class TemplateCreateIn(BaseModel):
    template_code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    problem_group: str | None = Field(default=None, max_length=60)
    level: str | None = Field(default=None, pattern="^(mild|moderate|severe)$")
    base_price: float | None = Field(default=None, ge=0)
    duration_days: int | None = Field(default=None, gt=0)
    status: str | None = Field(default=None, pattern="^(draft|active|archived)$")


class TemplateUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    problem_group: str | None = Field(default=None, max_length=60)
    level: str | None = Field(default=None, pattern="^(mild|moderate|severe)$")
    base_price: float | None = Field(default=None, ge=0)
    duration_days: int | None = Field(default=None, gt=0)
    status: str | None = Field(default=None, pattern="^(draft|active|archived)$")


class TemplateItemIn(BaseModel):
    product_id: int
    quantity: float = Field(gt=0)
    dose_text: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class TemplateItemUpdateIn(BaseModel):
    quantity: float | None = Field(default=None, gt=0)
    dose_text: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None


class RuleIn(BaseModel):
    rule_type: str = Field(pattern="^(exclusion|suitable|warning)$")
    condition: dict = Field(description='vd {"type":"screening","code":"thai_ky"}')
    action: dict = Field(description='vd {"message":"Không dùng cho thai kỳ"}')
    priority: int = 0


# ------------------------------------------------------------------ đề xuất + liệu trình
class EligibilityIn(BaseModel):
    customer_id: int


class RecommendIn(BaseModel):
    template_id: int | None = Field(
        default=None, description="trống = chỉ chạy engine xem danh sách; "
        "có = lưu phiên bản đề xuất cho mẫu đã chọn")
    note: str | None = Field(default=None, max_length=1000)


class RecommendationApproveIn(BaseModel):
    approve: bool = True
    note: str | None = Field(default=None, max_length=1000)


class CustomerTreatmentIn(BaseModel):
    template_id: int | None = None
    recommendation_id: int | None = None
    order_id: int | None = None
    start_date: date | None = None


class TreatmentAdjustIn(BaseModel):
    start_date: date | None = None
    expected_end_date: date | None = None
    status: str | None = Field(default=None,
                               pattern="^(planned|active|paused|completed|stopped)$")
    reason: str = Field(default="", max_length=500)
