"""API mua lại & khách ngủ — REPURCHASE-001…010 (B10, FR-120…123).

Route là lớp mỏng: luật (9 trạng thái suy từ ngày, công thức ngày hết,
chuyển stage, chiến dịch tái kích hoạt) ở services/repurchase_service.py.

Quyền: đọc = `customer.view`; ghi = `customer.edit` (CSKH giữ pipeline này).

⚠️ Router này phải include TRƯỚC customers router — /customers/sleeping là
đường literal, đứng sau /customers/{customer_id} sẽ bị route số nuốt mất.
"""

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import require_permission
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.schemas.repurchase import (
    AssignCampaignIn,
    CalcEndDateIn,
    LostReasonIn,
    MoveStageIn,
    RepurchaseCreateIn,
    RepurchaseUpdateIn,
)
from app.services import repurchase_service

router = APIRouter(prefix="/api/v1", tags=["repurchase"])

_xem = Depends(require_permission("customer.view"))
_sua = Depends(require_permission("customer.edit"))


# ------------------------------------------------- đường literal khai TRƯỚC {id}
@router.get("/repurchase-opportunities/due-soon")
async def due_soon(
    request: Request, days: int = Query(7, ge=1, le=90),
    pham_vi: str = "minh", _user: dict = _xem,
):
    """REPURCHASE-008 — khách sắp hết liệu trình (cửa sổ mặc định 7 ngày)."""
    user = getattr(request.state, "user", None) or {}
    owner = None if pham_vi == "tatca" else int(user.get("sub", 0)) or None
    return ok(repurchase_service.sap_den_han(days, owner))


@router.get("/repurchase-opportunities/overdue")
async def overdue(request: Request, pham_vi: str = "minh", _user: dict = _xem):
    """REPURCHASE-009 — cơ hội mở đã trượt ngày dự kiến."""
    user = getattr(request.state, "user", None) or {}
    owner = None if pham_vi == "tatca" else int(user.get("sub", 0)) or None
    return ok(repurchase_service.qua_han(owner))


@router.get("/repurchase-opportunities")
async def list_opps(
    stage: str = "", nhan: str = "",
    owner_id: int | None = Query(None, gt=0),
    customer_id: int | None = Query(None, gt=0),
    dang_mo: bool | None = None,
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _xem,
):
    """REPURCHASE-001 — mỗi dòng kèm nhãn FR-122 (display_state/label);
    `?nhan=` lọc theo nhãn suy ra (sap_den_han, qua_han, khach_ngu…)."""
    rows, total = repurchase_service.danh_sach(
        stage=stage, nhan=nhan, owner_id=owner_id, customer_id=customer_id,
        dang_mo=dang_mo, limit=pt.limit, offset=pt.offset)
    return ok(bao_trang(rows, total, pt))


@router.post("/repurchase-opportunities", status_code=201)
async def create_opp(body: RepurchaseCreateIn, user: dict = _sua):
    """REPURCHASE-003 — FR-121 (đường tự động là phiếu ngày 20 của B9)."""
    return ok(repurchase_service.tao(body.model_dump(), actor=user),
              "Đã tạo cơ hội mua lại")


@router.get("/repurchase-opportunities/{opportunity_id}")
async def get_opp(opportunity_id: int, _user: dict = _xem):
    """REPURCHASE-002."""
    return ok(repurchase_service.chi_tiet(opportunity_id))


@router.put("/repurchase-opportunities/{opportunity_id}")
async def update_opp(
    opportunity_id: int, body: RepurchaseUpdateIn, user: dict = _sua,
):
    """REPURCHASE-004 — cơ hội đã đóng thì khoá."""
    return ok(repurchase_service.cap_nhat(
        opportunity_id, body.model_dump(exclude_none=True), actor=user),
        "Đã cập nhật cơ hội")


@router.post("/repurchase-opportunities/{opportunity_id}/move-stage")
async def move_stage(opportunity_id: int, body: MoveStageIn, user: dict = _sua):
    """REPURCHASE-005 — 'lost' bắt buộc lý do."""
    return ok(repurchase_service.chuyen_stage(
        opportunity_id, body.stage, reason=body.reason, actor=user),
        "Đã chuyển trạng thái")


@router.post("/repurchase-opportunities/{opportunity_id}/lost-reason")
async def lost_reason(opportunity_id: int, body: LostReasonIn, user: dict = _sua):
    """REPURCHASE-006 — mã chuẩn 9 lý do BRD (lead_reasons) + diễn giải."""
    return ok(repurchase_service.ghi_ly_do(
        opportunity_id, ma_ly_do=body.ma_ly_do, note=body.note, actor=user),
        "Đã ghi lý do chưa mua")


@router.post("/customer-treatments/{customer_treatment_id}/calculate-end-date")
async def calc_end_date(
    customer_treatment_id: int, body: CalcEndDateIn, user: dict = _sua,
):
    """REPURCHASE-007 — FR-120: trả breakdown từng khoản, lưu vào liệu trình
    + đồng bộ sang cơ hội đang mở."""
    return ok(repurchase_service.tinh_ngay_het(
        customer_treatment_id, body.model_dump(exclude_none=True), actor=user),
        "Đã tính ngày dự kiến hết")


@router.get("/customers/sleeping")
async def sleeping(
    tu_ngay: int = Query(30, ge=1),
    gia_tri_tu: float | None = Query(None, ge=0),
    _user: dict = _xem,
):
    """REPURCHASE-010 — FR-123: khách từng mua im ắng ≥ tu_ngay ngày, chia rổ
    30/60/90/180; lọc thêm theo tổng giá trị mua."""
    return ok(repurchase_service.khach_ngu(tu_ngay, gia_tri_tu))


# ----------------------------------------------- chiến dịch tái kích hoạt (FR-123)
@router.post("/reactivation-campaigns/assign")
async def assign_campaign(body: AssignCampaignIn, user: dict = _sua):
    """FR-123 'gán chiến dịch + tạo nhiệm vụ' — chọn chiến dịch có sẵn hoặc
    đặt tên tạo mới; mỗi khách 1 việc `mua_lai` cho người được giao."""
    return ok(repurchase_service.gan_chien_dich(
        campaign_id=body.campaign_id, ten_moi=body.ten_moi,
        customer_ids=body.customer_ids, assigned_to=body.assigned_to,
        tao_viec=body.tao_viec, actor=user), "Đã gán chiến dịch")


@router.get("/reactivation-campaigns")
async def list_campaigns(_user: dict = _xem):
    """FR-123 'đo doanh thu tái kích hoạt' — số khách · chuyển đổi · doanh thu
    (đơn giao TC tạo SAU khi khách vào chiến dịch)."""
    return ok(repurchase_service.bao_cao_chien_dich())
