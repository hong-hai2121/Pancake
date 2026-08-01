"""Schema Pydantic cho API đơn hàng B7 (ORDER-001…011).

Pattern trạng thái dựng từ danh sách 11 trạng thái chuẩn trong
services/order_service.py — thêm/bớt trạng thái chỉ sửa MỘT chỗ đó.
"""

from pydantic import BaseModel, Field

from app.services.order_service import ORDER_STATUSES

_STATUS_PATTERN = f"^({'|'.join(ORDER_STATUSES)})$"
_TYPE_PATTERN = "^(new|repurchase|upsell|exchange)$"


class OrderItemIn(BaseModel):
    product_id: int
    quantity: float = Field(gt=0)
    # Bỏ trống = chốt theo giá sản phẩm HIỆN TẠI (service tự tra) — sau đó giá
    # sản phẩm đổi cũng không ảnh hưởng dòng này nữa.
    unit_price: float | None = Field(default=None, ge=0)
    treatment_template_id: int | None = None


class OrderCreateIn(BaseModel):
    customer_id: int
    items: list[OrderItemIn] = Field(min_length=1)
    status: str = Field(default="draft", pattern=_STATUS_PATTERN)
    # Bỏ trống = tự phân loại đơn đầu/mua lại (FR-082)
    order_type: str | None = Field(default=None, pattern=_TYPE_PATTERN)
    sale_owner_id: int | None = None
    cskh_owner_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)
    external_order_id: str | None = Field(default=None, max_length=100)


class OrderUpdateIn(BaseModel):
    sale_owner_id: int | None = None
    cskh_owner_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)
    order_type: str | None = Field(default=None, pattern=_TYPE_PATTERN)


class StatusChangeIn(BaseModel):
    to_status: str = Field(pattern=_STATUS_PATTERN)
    reason: str | None = Field(default=None, max_length=500)


class MappingUpdateIn(BaseModel):
    crm_status: str = Field(pattern=_STATUS_PATTERN)
    note: str | None = Field(default=None, max_length=500)


class SyncPosIn(BaseModel):
    """Kéo tay đơn POS (ORDER-011): mặc định đơn ĐỔI trong 24h qua, tối đa 5 trang."""

    tu_gio_truoc: float = Field(default=24, gt=0, le=24 * 90)
    so_trang: int = Field(default=5, ge=1, le=50)
