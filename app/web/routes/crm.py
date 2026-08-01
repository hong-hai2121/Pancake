"""Route bộ màn CRM tạm (khung) — /crm/*.

Chỉ đọc, chưa có thao tác ghi nên chưa gắn quyền riêng (middleware đã bắt đăng
nhập). Khi lát cắt nào làm thật thì thêm kiểm quyền màn đó (vd customer.view
cho /crm/khach-hang) cùng lúc với form thao tác.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.deps import co_quyen
from app.core.errors import ApiError
from app.db.repositories import crm_screens_repo as repo
from app.services import ads_service
from app.web.views import ads as views_ads
from app.web.views import crm as views
from app.web.views.admin import render_403

router = APIRouter(prefix="/crm", tags=["web-crm"])


@router.get("/tong-quan", response_class=HTMLResponse)
async def tong_quan() -> HTMLResponse:
    """Màn 4 (khung) — dashboard toàn công ty."""
    tieu_cuc: int | None = None
    try:  # số hội thoại tiêu cực lấy từ kho watcher — DB bot tắt thì bỏ qua ô này
        from app.db.repositories import inbox_store

        tieu_cuc = inbox_store.stats().get("negative", 0)
    except Exception:  # noqa: BLE001
        pass
    return HTMLResponse(views.render_tong_quan(repo.dashboard(), tieu_cuc))


@router.get("/khach-hang", response_class=HTMLResponse)
async def khach_hang(q: str = "") -> HTMLResponse:
    """Màn 8 (khung) — danh sách khách CRM (khác /khach-hang của bot Pancake)."""
    rows, total = repo.list_customers(q=q)
    return HTMLResponse(views.render_khach_hang(rows, total, q))


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline(st: int = 0) -> HTMLResponse:
    """Màn 11 (khung) — Kanban 13 giai đoạn. `?st=<stage_id>` tô sáng + cuộn
    tới cột đó (đường vào từ khối Sale ở menu trái)."""
    return HTMLResponse(views.render_pipeline(repo.pipeline_board(), st=st))


@router.get("/cong-viec", response_class=HTMLResponse)
async def cong_viec(request: Request, pham_vi: str = "minh") -> HTMLResponse:
    """Màn 12 + 26 — việc quá hạn / hôm nay / sắp tới (B4 đổ dữ liệu thật).

    Mặc định chỉ việc CỦA NGƯỜI ĐANG ĐĂNG NHẬP (BRD: màn 'việc hôm nay' là
    của từng người); `?pham_vi=tatca` xem cả đội — trưởng nhóm/giám sát dùng.
    """
    user = getattr(request.state, "user", None) or {}
    cua_ai = None if pham_vi == "tatca" else int(user.get("sub", 0)) or None
    return HTMLResponse(views.render_cong_viec(
        repo.tasks_groups(assigned_to=cua_ai), pham_vi=pham_vi,
    ))


@router.get("/don-hang", response_class=HTMLResponse)
async def don_hang() -> HTMLResponse:
    """Màn 21 (khung) — danh sách đơn + đếm theo trạng thái."""
    return HTMLResponse(views.render_don_hang(repo.orders_summary()))


@router.get("/cham-soc", response_class=HTMLResponse)
async def cham_soc() -> HTMLResponse:
    """Màn 26-27 (khung) — pipeline CSKH C01-C09 + mốc chăm chờ làm."""
    return HTMLResponse(views.render_cham_soc(repo.care_board()))


@router.get("/mua-lai", response_class=HTMLResponse)
async def mua_lai() -> HTMLResponse:
    """Màn 39-40 (khung) — cơ hội mua lại."""
    return HTMLResponse(views.render_mua_lai(repo.repurchase_summary()))


@router.get("/san-pham", response_class=HTMLResponse)
async def san_pham() -> HTMLResponse:
    """Màn 42 + 44 (khung) — danh mục sản phẩm & mẫu liệu trình."""
    return HTMLResponse(views.render_san_pham(repo.products_treatments()))


# ------------------------------------------------------------ nguồn quảng cáo
@router.get("/quang-cao", response_class=HTMLResponse)
async def quang_cao(
    request: Request, cap: str = "ad", tu: str = "", den: str = "",
) -> HTMLResponse:
    """Màn 7 + 53-55 — hiệu quả quảng cáo theo chiến dịch / nhóm / quảng cáo.

    Quyền `ads.view` (Marketing + Chủ DN + Admin): màn này bày chi phí và doanh
    thu, không phải ai đăng nhập cũng được xem.
    """
    if not co_quyen(getattr(request.state, "user", None), "ads.view"):
        return HTMLResponse(
            render_403("Màn Nguồn quảng cáo cần quyền ads.view",
                       heading="Nguồn quảng cáo"),
            status_code=403,
        )
    if cap not in ("campaign", "ad_set", "ad"):
        cap = "ad"
    if not (tu or den):
        tu, den = ads_service.ky_mac_dinh(30)
    return HTMLResponse(views_ads.render_quang_cao(
        cap, ads_service.bao_cao(cap, tu, den), ads_service.tong_quan(tu, den),
        tu=tu, den=den,
    ))


@router.get("/quang-cao/{external_ad_id}", response_class=HTMLResponse)
async def quang_cao_chi_tiet(
    request: Request, external_ad_id: str, window: int = 30,
) -> HTMLResponse:
    """Màn 56 — phiếu sức khỏe 1 quảng cáo (phễu · lý do chưa chốt · khách)."""
    if not co_quyen(getattr(request.state, "user", None), "ads.view"):
        return HTMLResponse(
            render_403("Màn Nguồn quảng cáo cần quyền ads.view",
                       heading="Nguồn quảng cáo"),
            status_code=403,
        )
    try:
        data = ads_service.chi_tiet_ad(external_ad_id, window)
    except ApiError as err:
        return HTMLResponse(
            render_403(err.message, heading="Nguồn quảng cáo"), status_code=404)
    return HTMLResponse(views_ads.render_chi_tiet_ad(data, window=window))
