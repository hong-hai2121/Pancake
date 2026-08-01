"""API đơn hàng B7 — ORDER-001…011 (màn 21-23).

Route là lớp mỏng: luật nằm ở services/order_service.py; đồng bộ POS nằm ở
app/integrations/pancake_pos/. Quyền: order.view (xem) / order.edit (tạo, sửa,
chuyển trạng thái) / user.manage (sửa ánh xạ + kéo đồng bộ tay — việc quản trị).
"""

import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.deps import require_permission
from app.core.errors import ApiError
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.db.repositories import order_repo
from app.schemas.order import (
    MappingUpdateIn,
    OrderCreateIn,
    OrderUpdateIn,
    StatusChangeIn,
    SyncPosIn,
)
from app.services import order_service

router = APIRouter(prefix="/api/v1", tags=["orders"])

_xem = Depends(require_permission("order.view"))
_sua = Depends(require_permission("order.edit"))
_quan_tri = Depends(require_permission("user.manage"))


def _den_bao_gom(den: str) -> str:
    """Ngày 'đến' là NGÀY BAO GỒM: cộng 1 ngày vì repo lọc created_at < den."""
    try:
        return (datetime.fromisoformat(den) + timedelta(days=1)).isoformat()
    except ValueError as err:
        raise ApiError("VALIDATION_ERROR", "Ngày không hợp lệ (ISO: 2026-08-01)",
                       errors={"den": den}) from err


# ------------------------------------------------------------------ danh sách
@router.get("/orders/tong-quan")
async def tong_quan(_user: dict = _xem):
    """ORDER-008 — đếm đơn theo trạng thái + theo loại đầu/mua lại (màn 21)."""
    return ok(order_repo.dem_theo_trang_thai())


@router.get("/orders")
async def list_orders(
    status: str = "",
    order_type: str = "",
    customer_id: int | None = None,
    source: str = Query("", pattern="^(crm|pancake_pos)?$"),
    q: str = "",
    tu: str = "",
    den: str = "",
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _xem,
):
    """ORDER-001 — danh sách đơn, lọc trạng thái/loại/nguồn/khách/thời gian."""
    rows, total = order_repo.list_orders(
        status=status, order_type=order_type, customer_id=customer_id,
        source=source, q=q, tu=tu, den=_den_bao_gom(den) if den else "",
        limit=pt.limit, offset=pt.offset,
    )
    return ok(bao_trang(rows, total, pt))


@router.get("/customers/{customer_id}/orders")
async def orders_of_customer(
    customer_id: int, pt: PhanTrang = Depends(phan_trang), _user: dict = _xem
):
    """ORDER-007 — đơn của 1 khách (tab Đơn hàng hồ sơ 360°, màn 8)."""
    rows, total = order_repo.list_orders(
        customer_id=customer_id, limit=pt.limit, offset=pt.offset
    )
    return ok(bao_trang(rows, total, pt))


# ------------------------------------------------------------------ chi tiết
@router.get("/orders/{order_id}")
async def get_order(order_id: int, _user: dict = _xem):
    """ORDER-002 — đơn + dòng hàng + toàn bộ lịch sử trạng thái."""
    return ok(order_service.get_detail(order_id))


@router.get("/orders/{order_id}/history")
async def order_history(order_id: int, _user: dict = _xem):
    """ORDER-006 — riêng lịch sử trạng thái (không bao giờ bị xoá — FR-080)."""
    order_service.get_detail(order_id)   # 404 nếu đơn không tồn tại
    return ok({"items": order_repo.list_history(order_id)})


# ------------------------------------------------------------------ ghi
@router.post("/orders", status_code=201)
async def create_order(body: OrderCreateIn, user: dict = _sua):
    """ORDER-003 — tạo đơn tay trong CRM (đơn POS về qua đồng bộ, không tạo ở đây)."""
    return ok(order_service.create_order(body.model_dump(), actor=user), "Đã tạo đơn")


@router.put("/orders/{order_id}")
async def update_order(order_id: int, body: OrderUpdateIn, user: dict = _sua):
    """ORDER-004 — sửa owner/ghi chú/loại đơn (trạng thái đi endpoint riêng)."""
    return ok(
        order_service.update_order(
            order_id, body.model_dump(exclude_none=True), actor=user
        ),
        "Đã cập nhật đơn",
    )


@router.post("/orders/{order_id}/status")
async def change_status(order_id: int, body: StatusChangeIn, user: dict = _sua):
    """ORDER-005 — chuyển trạng thái theo luật; sai luật -> INVALID_STAGE_TRANSITION."""
    return ok(
        order_service.change_status(
            order_id, body.to_status, actor=user, reason=body.reason
        ),
        "Đã chuyển trạng thái",
    )


# ------------------------------------------------------------------ ánh xạ POS
@router.get("/order-status-mappings")
async def list_mappings(_user: dict = _xem):
    """ORDER-009 — bảng ánh xạ mã POS -> trạng thái CRM (màn 23)."""
    return ok({"items": order_service.list_mappings()})


@router.put("/order-status-mappings/{pancake_status}")
async def update_mapping(pancake_status: int, body: MappingUpdateIn, user: dict = _quan_tri):
    """ORDER-010 — admin sửa ánh xạ; lượt đồng bộ sau dùng bản mới ngay."""
    return ok(
        order_service.update_mapping(pancake_status, body.model_dump(), actor=user),
        "Đã sửa ánh xạ",
    )


# ------------------------------------------------------------------ đồng bộ tay
@router.post("/orders/sync-pos")
async def sync_pos(body: SyncPosIn, user: dict = _quan_tri):
    """ORDER-011 — kéo tay đơn POS đổi gần đây (worker poll bù chạy nền sẵn).

    Dành cho quản trị: vừa sửa ánh xạ xong muốn thấy kết quả ngay, hoặc worker
    đang tắt. Backfill lịch sử dài: scripts/backfill_don_pos.py.
    """
    if not (settings.pancake_pos_api_key and settings.pancake_pos_shop_id):
        raise ApiError("VALIDATION_ERROR",
                       "Chưa cấu hình PANCAKE_POS_API_KEY / PANCAKE_POS_SHOP_ID trong .env")
    from app.integrations.pancake_pos import client, pos_sync
    from app.integrations.pancake_pos.client import PancakePosError

    since = int(time.time() - body.tu_gio_truoc * 3600)
    dons: list[dict] = []
    try:
        for trang in range(1, body.so_trang + 1):
            data = await client.list_orders(
                page_number=trang, page_size=100,
                since=since, update_status="updated_at",
            )
            mot_trang = [d for d in data.get("data") or [] if isinstance(d, dict)]
            dons.extend(mot_trang)
            if trang >= int(data.get("total_pages") or 1) or not mot_trang:
                break
    except PancakePosError as err:
        raise ApiError("INTEGRATION_ERROR", f"Pancake POS lỗi: {err}") from err

    import asyncio

    ket_qua = await asyncio.to_thread(pos_sync.sync_batch, dons)
    return ok({"so_don_keo_ve": len(dons), **ket_qua}, "Đã đồng bộ")
