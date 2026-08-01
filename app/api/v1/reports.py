"""API báo cáo — REPORT-001…011 (B11, FR-170…173).

Quyền theo NỘI DUNG: doanh thu/đơn = `revenue.view` · marketing = `ads.view`
· còn lại `customer.view`; drill-down & export kiểm quyền RIÊNG của từng
metric trong service (sổ METRICS); export thêm `data.export` (FR-181).
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.core.deps import get_current_user, require_permission
from app.core.response import ok
from app.services import report_service

router = APIRouter(prefix="/api/v1", tags=["reports"])

_xem = Depends(require_permission("customer.view"))
_doanh_thu = Depends(require_permission("revenue.view"))
_ads = Depends(require_permission("ads.view"))


@router.get("/reports/dashboard")
async def dashboard(tu: str = "", den: str = "", user: dict = _xem):
    """REPORT-001 — màn 4; ô doanh thu/chi phí tự ẩn theo quyền người gọi."""
    return ok(report_service.dashboard(tu, den, user=user))


@router.get("/reports/sales")
async def sales(tu: str = "", den: str = "", _user: dict = _doanh_thu):
    """REPORT-002 — FR-170, mỗi Sale một dòng + tỷ lệ phễu."""
    return ok(report_service.bao_cao_sale(tu, den))


@router.get("/reports/customer-care")
async def customer_care(tu: str = "", den: str = "", _user: dict = _xem):
    """REPORT-003 — FR-171, mỗi CSKH một dòng."""
    return ok(report_service.bao_cao_cskh(tu, den))


@router.get("/reports/marketing")
async def marketing(tu: str = "", den: str = "", _user: dict = _ads):
    """REPORT-004 — FR-172: chi phí · ROAS · LTV · lý do chưa chốt."""
    return ok(report_service.bao_cao_marketing(tu, den))


@router.get("/reports/orders")
async def orders(tu: str = "", den: str = "", _user: dict = _doanh_thu):
    """REPORT-005."""
    return ok(report_service.bao_cao_don_hang(tu, den))


@router.get("/reports/revenue")
async def revenue(tu: str = "", den: str = "", _user: dict = _doanh_thu):
    """REPORT-006 — chuỗi ngày, tách bán mới / mua lại."""
    return ok(report_service.bao_cao_doanh_thu(tu, den))


@router.get("/reports/repurchase")
async def repurchase(tu: str = "", den: str = "", _user: dict = _xem):
    """REPORT-007 — cơ hội + chiến dịch tái kích hoạt."""
    return ok(report_service.bao_cao_mua_lai(tu, den))


@router.get("/reports/call-quality")
async def call_quality(_user: dict = _xem):
    """REPORT-008 — giữ đúng đặc tả; dữ liệu chờ tổng đài C-MVP3."""
    return ok(report_service.bao_cao_cuoc_goi())


@router.get("/reports/tasks")
async def tasks(tu: str = "", den: str = "", _user: dict = _xem):
    """REPORT-009 — việc theo loại: tạo/xong/đúng hạn/quá hạn."""
    return ok(report_service.bao_cao_cong_viec(tu, den))


@router.get("/reports/drill-down")
async def drill_down(
    request: Request,
    metric: str,
    tu: str = "", den: str = "",
    user_id: int | None = Query(None, gt=0),
    limit: int = Query(200, ge=1, le=1000),
):
    """REPORT-010 — FR-173: danh sách chi tiết CÙNG điều kiện với số tổng.
    Quyền kiểm THEO METRIC (doanh thu đòi revenue.view, ads đòi ads.view…)."""
    user = get_current_user(request)
    return ok(report_service.drill_down(metric, tu, den, user_id,
                                        user=user, limit=limit))


class ExportIn(BaseModel):
    metric: str
    tu: str = ""
    den: str = ""
    user_id: int | None = Field(None, gt=0)


@router.post("/reports/export")
async def export(request: Request, body: ExportIn):
    """REPORT-011 — CSV BOM UTF-8 chấm phẩy (Excel VN mở thẳng); đòi
    `data.export` + quyền metric; mỗi lần xuất ghi audit (FR-181)."""
    user = get_current_user(request)
    noi_dung, ten_file = report_service.xuat_csv(
        body.metric, body.tu, body.den, body.user_id, user=user)
    return PlainTextResponse(
        noi_dung, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{ten_file}"'})
