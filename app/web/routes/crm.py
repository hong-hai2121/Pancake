"""Route bộ màn CRM tạm (khung) — /crm/*.

Chỉ đọc, chưa có thao tác ghi nên chưa gắn quyền riêng (middleware đã bắt đăng
nhập). Khi lát cắt nào làm thật thì thêm kiểm quyền màn đó (vd customer.view
cho /crm/khach-hang) cùng lúc với form thao tác.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.db.repositories import crm_screens_repo as repo
from app.web.views import crm as views

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
async def pipeline() -> HTMLResponse:
    """Màn 11 (khung) — Kanban 13 giai đoạn."""
    return HTMLResponse(views.render_pipeline(repo.pipeline_board()))


@router.get("/cong-viec", response_class=HTMLResponse)
async def cong_viec() -> HTMLResponse:
    """Màn 12 + 26 (khung) — việc quá hạn / hôm nay / sắp tới."""
    return HTMLResponse(views.render_cong_viec(repo.tasks_groups()))


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
