"""API Tích hợp Pancake & nguồn quảng cáo — BRD mục 4 (INTEGRATION-001…010).

Route là lớp mỏng: luật + audit nằm ở services/integration_service.py.

Quyền: `integration.manage` cho mọi thao tác quản trị tích hợp (Chủ DN + Admin
đã có sẵn qua ma trận A5). Riêng link mở hội thoại Pancake của một khách dùng
`customer.view` — Sale/CSKH phải bấm được từ hồ sơ 360°.

Lưu ý luật mục 4: TẤT CẢ endpoint ở đây đọc từ `crm.*`, KHÔNG gọi Pancake —
trừ đúng một cái: POST /integrations/{id}/kiem-tra (người chủ động bấm).
"""

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_permission
from app.core.errors import ApiError
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.db.repositories import attribution_repo, customer_repo, integration_repo
from app.integrations.pancake.links import link_hoi_thoai
from app.schemas.integration import PageAccountIn, PageSyncIn, RetryIn, StaffMapIn
from app.services import integration_service

router = APIRouter(prefix="/api/v1", tags=["integrations"])

_quan_tri = Depends(require_permission("integration.manage"))
_xem_khach = Depends(require_permission("customer.view"))


# ------------------------------------------------------------------ kết nối
@router.get("/integrations")
async def list_integrations(_user: dict = _quan_tri):
    """INTEGRATION-001 — danh sách kết nối Pancake (tab Kết nối, màn Tích hợp)."""
    return ok({"items": integration_service.danh_sach_ket_noi()})


@router.get("/integrations/tinh-trang")
async def tinh_trang(so_gio: int = Query(24, ge=1, le=24 * 30), _user: dict = _quan_tri):
    """INTEGRATION-002 — "Tình trạng đồng bộ": công tắc, số lượt, lỗi, cảnh báo token."""
    return ok(integration_service.tinh_trang(so_gio))


@router.post("/integrations/{account_id}/kiem-tra")
async def kiem_tra(account_id: int, user: dict = _quan_tri):
    """INTEGRATION-003 — gọi thật 1 lần để biết token còn sống (nút bấm tay)."""
    return ok(await integration_service.kiem_tra_ket_noi(account_id, actor=user))


# ------------------------------------------------------------------ page
@router.get("/integrations/pages")
async def list_pages(account_id: int | None = None, _user: dict = _quan_tri):
    """INTEGRATION-004 — page đã nối + cờ đồng bộ + số hội thoại đã về."""
    return ok({"items": integration_service.danh_sach_page(account_id)})


@router.put("/integrations/pages/{page_id}/dong-bo")
async def set_page_sync(page_id: int, body: PageSyncIn, user: dict = _quan_tri):
    """INTEGRATION-005 — bật/tắt đồng bộ CRM cho 1 page."""
    return ok(
        integration_service.bat_tat_page(page_id, body.sync_enabled, actor=user),
        "Đã bật đồng bộ" if body.sync_enabled else "Đã tắt đồng bộ",
    )


@router.put("/integrations/pages/{page_id}/ket-noi")
async def set_page_account(page_id: int, body: PageAccountIn, user: dict = _quan_tri):
    """INTEGRATION-006 — ánh xạ page về tài khoản Pancake nào."""
    return ok(
        integration_service.gan_page_vao_ket_noi(page_id, body.account_id, actor=user),
        "Đã gán page vào kết nối",
    )


# ------------------------------------------------------------------ nhân viên
@router.get("/integrations/nhan-vien")
async def list_staff(
    provider: str = Query("", pattern="^(pancake_pages|pancake_pos)?$"),
    _user: dict = _quan_tri,
):
    """INTEGRATION-007 — ánh xạ nhân viên Pancake ↔ nhân viên CRM."""
    return ok({"items": integration_service.danh_sach_nhan_vien(provider)})


@router.put("/integrations/nhan-vien")
async def map_staff(body: StaffMapIn, user: dict = _quan_tri):
    """INTEGRATION-008 — gán 1 nhân viên Pancake vào tài khoản CRM."""
    return ok(
        integration_service.gan_nhan_vien(
            body.provider, body.external_staff_id, body.user_id, actor=user),
        "Đã lưu ánh xạ nhân viên",
    )


# ------------------------------------------------------------------ nhật ký & lỗi
@router.get("/integrations/nhat-ky")
async def list_logs(
    provider: str = Query("", pattern="^(pancake_pages|pancake_pos)?$"),
    entity: str = Query("", pattern="^(conversation|order|customer|tag|page)?$"),
    status: str = Query("", pattern="^(running|success|partial|failed)?$"),
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _quan_tri,
):
    """INTEGRATION-009 — nhật ký đồng bộ (mỗi lượt chạy 1 dòng)."""
    rows, total = integration_service.danh_sach_log(
        provider=provider, entity=entity, status=status,
        limit=pt.limit, offset=pt.offset)
    return ok(bao_trang(rows, total, pt))


@router.get("/integrations/loi")
async def list_errors(
    provider: str = Query("", pattern="^(pancake_pages|pancake_pos)?$"),
    entity: str = Query("", pattern="^(conversation|order|customer|tag|page)?$"),
    status: str = Query("pending", pattern="^(pending|resolved|given_up)?$"),
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _quan_tri,
):
    """INTEGRATION-010 — danh sách lỗi đồng bộ (hàng đợi retry)."""
    rows, total = integration_service.danh_sach_loi(
        provider=provider, entity=entity, status=status,
        limit=pt.limit, offset=pt.offset)
    return ok(bao_trang(rows, total, pt))


@router.post("/integrations/loi/{error_id}/thu-lai")
async def retry_one(error_id: int, user: dict = _quan_tri):
    """Đặt lại lịch cho 1 dòng lỗi -> worker retry nhặt ngay lượt kế."""
    return ok(integration_service.thu_lai_ngay(error_id, actor=user), "Đã xếp thử lại")


@router.post("/integrations/loi/chay-ngay")
async def retry_now(body: RetryIn, _user: dict = _quan_tri):
    """Chạy hàng đợi lỗi NGAY (không chờ worker) — dùng sau khi vừa sửa ánh xạ."""
    return ok(integration_service.chay_hang_doi(body.limit), "Đã chạy hàng đợi")


# ------------------------------------------------------------------ quy nguồn
@router.get("/integrations/quy-nguon")
async def top_nguon(limit: int = Query(20, ge=1, le=100), _user: dict = _quan_tri):
    """Attribution Marketing: top quảng cáo theo số khách chạm cuối + doanh thu."""
    return ok({"items": attribution_repo.thong_ke_nguon(limit)})


@router.get("/customers/{customer_id}/quy-nguon")
async def quy_nguon_khach(customer_id: int, _user: dict = _xem_khach):
    """Chạm đầu/cuối của 1 khách — tab Nguồn Ads của hồ sơ 360° (màn 8)."""
    if not customer_repo.get_customer(customer_id):
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    return ok({"items": attribution_repo.cham_cua_khach(customer_id)})


# ------------------------------------------------------------------ link Pancake
@router.get("/customers/{customer_id}/pancake-links")
async def pancake_links(customer_id: int, _user: dict = _xem_khach):
    """"Nút mở đúng hội thoại Pancake từ hồ sơ CRM" — chỉ ghép chuỗi, không gọi API."""
    if not customer_repo.get_customer(customer_id):
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    ra = []
    for hoi_thoai in integration_repo.hoi_thoai_cua_khach(customer_id):
        ra.append({
            **hoi_thoai,
            "link": link_hoi_thoai(hoi_thoai["external_page_id"],
                                   hoi_thoai["external_conversation_id"]),
        })
    return ok({"items": ra})
