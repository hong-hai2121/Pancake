"""API bàn giao Sale→CSKH — HANDOVER-001…006 (B8, FR-090/091).

Route là lớp mỏng: luật (tự động khi giao thành công, 8 trường bắt buộc,
trả lại Sale) nằm ở services/handover_service.py.

Quyền: đọc = `customer.view`; tạo/sửa phiếu/nhận/trả/gán = `customer.edit`
(Sale bổ sung phiếu, CSKH nhận — cả hai vai đều có customer.edit).
"""

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_permission
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.schemas.handover import (
    HandoverAssignIn,
    HandoverCreateIn,
    HandoverReturnIn,
    HandoverUpdateIn,
)
from app.services import handover_service

router = APIRouter(prefix="/api/v1", tags=["handovers"])

_xem = Depends(require_permission("customer.view"))
_sua = Depends(require_permission("customer.edit"))


@router.get("/handovers/pending")
async def list_pending(
    cskh_user_id: int | None = Query(None, gt=0),
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _xem,
):
    """HANDOVER-001 — phiếu CHỜ xử lý (pending + assigned + returned), màn 24."""
    rows, total = handover_service.danh_sach(
        status="cho", cskh_user_id=cskh_user_id,
        limit=pt.limit, offset=pt.offset)
    return ok(bao_trang(rows, total, pt))


@router.get("/handovers")
async def list_handovers(
    status: str = "",
    cskh_user_id: int | None = Query(None, gt=0),
    customer_id: int | None = Query(None, gt=0),
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _xem,
):
    """Danh sách đầy đủ (lọc status/CSKH/khách) — nền cho màn 24 + báo cáo."""
    rows, total = handover_service.danh_sach(
        status=status, cskh_user_id=cskh_user_id, customer_id=customer_id,
        limit=pt.limit, offset=pt.offset)
    return ok(bao_trang(rows, total, pt))


@router.post("/handovers", status_code=201)
async def create_handover(body: HandoverCreateIn, user: dict = _sua):
    """HANDOVER-002 — tạo phiếu tay từ đơn đã giao (đơn đã có phiếu thì trả
    phiếu cũ, không tạo trùng)."""
    return ok(handover_service.tao_tu_don(body.order_id, actor=user),
              "Đã tạo phiếu bàn giao")


@router.get("/handovers/{handover_id}")
async def get_handover(handover_id: int, _user: dict = _xem):
    """HANDOVER-003 — chi tiết phiếu (màn 25), kèm danh sách trường thiếu."""
    return ok(handover_service.chi_tiet(handover_id))


@router.put("/handovers/{handover_id}")
async def update_handover(
    handover_id: int, body: HandoverUpdateIn, user: dict = _sua,
):
    """FR-091 — Sale bổ sung / CSKH ghi thêm nội dung phiếu; đủ 8 trường thì
    phiếu 'returned' tự quay lại 'assigned'."""
    return ok(
        handover_service.cap_nhat_phieu(
            handover_id, body.model_dump(exclude_none=True), actor=user),
        "Đã cập nhật phiếu",
    )


@router.post("/handovers/{handover_id}/accept")
async def accept(handover_id: int, user: dict = _sua):
    """HANDOVER-004 — CSKH nhận bàn giao (hồ sơ phải ĐỦ); khách chính thức
    thuộc CSKH này."""
    return ok(handover_service.nhan(handover_id, actor=user), "Đã nhận bàn giao")


@router.post("/handovers/{handover_id}/return")
async def return_handover(
    handover_id: int, body: HandoverReturnIn, user: dict = _sua,
):
    """HANDOVER-005 — trả lại Sale bổ sung, kèm việc cho Sale."""
    return ok(handover_service.tra_lai(handover_id, body.reason, actor=user),
              "Đã trả lại Sale")


@router.post("/handovers/{handover_id}/assign")
async def assign(handover_id: int, body: HandoverAssignIn, user: dict = _sua):
    """HANDOVER-006 — gán/đổi CSKH cho phiếu."""
    return ok(handover_service.gan_cskh(handover_id, body.user_id, actor=user),
              "Đã gán CSKH")
