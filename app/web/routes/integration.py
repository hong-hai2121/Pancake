"""Route khu Tích hợp (BRD mục 4): /quan-tri/tich-hop/... — quyền `integration.manage`.

Lớp mỏng như routes/admin.py: gọi chung service với API (`integration_service`)
nên luật + audit chỉ có MỘT chỗ; lỗi nghiệp vụ (ApiError) hiện thành dải đỏ.
"""

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import co_quyen
from app.core.errors import ApiError
from app.db.repositories import integration_repo, order_repo, user_repo
from app.services import integration_service, order_service
from app.web.views.admin import render_403
from app.web.views.integration import (
    render_anh_xa,
    render_ket_noi,
    render_loi,
    render_nhat_ky,
)

router = APIRouter(prefix="/quan-tri/tich-hop", tags=["web-integration"])

_MOI_TRANG = 30


def _user(request: Request) -> dict:
    return getattr(request.state, "user", None) or {}


def _chan(request: Request) -> HTMLResponse | None:
    if not co_quyen(_user(request), "integration.manage"):
        return HTMLResponse(
            render_403("Khu Tích hợp cần quyền integration.manage",
                       heading="Tích hợp Pancake"),
            status_code=403,
        )
    return None


def _back(path: str, ok: str = "", error: str = "") -> RedirectResponse:
    tham_so = f"?ok={quote(ok)}" if ok else (f"?error={quote(error)}" if error else "")
    return RedirectResponse(path + tham_so, status_code=303)


async def _form(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: str(v).strip() for k, v in form.items()}


def _to_int(v: str) -> int | None:
    return int(v) if str(v).strip().isdigit() else None


# ------------------------------------------------------------ tab Kết nối
@router.get("", response_class=HTMLResponse)
async def trang_ket_noi(request: Request, ok: str = "", error: str = ""):
    if (chan := _chan(request)):
        return chan
    return HTMLResponse(render_ket_noi(
        integration_service.tinh_trang(),
        integration_service.danh_sach_page(),
        ok=ok, error=error,
    ))


@router.post("/{account_id}/kiem-tra")
async def kiem_tra(request: Request, account_id: int):
    if (chan := _chan(request)):
        return chan
    try:
        kq = await integration_service.kiem_tra_ket_noi(account_id, actor=_user(request))
    except ApiError as err:
        return _back("/quan-tri/tich-hop", error=err.message)
    if kq.get("ok"):
        return _back("/quan-tri/tich-hop", ok=kq.get("message") or "Kết nối tốt")
    return _back("/quan-tri/tich-hop", error=kq.get("message") or "Kết nối hỏng")


@router.post("/page/{page_id}/dong-bo")
async def bat_tat_page(request: Request, page_id: int):
    if (chan := _chan(request)):
        return chan
    form = await _form(request)
    bat = form.get("bat") == "1"
    try:
        integration_service.bat_tat_page(page_id, bat, actor=_user(request))
    except ApiError as err:
        return _back("/quan-tri/tich-hop", error=err.message)
    return _back("/quan-tri/tich-hop",
                 ok="Đã bật đồng bộ page" if bat else "Đã tắt đồng bộ page")


# ------------------------------------------------------------ tab Nhật ký
@router.get("/nhat-ky", response_class=HTMLResponse)
async def trang_nhat_ky(
    request: Request, provider: str = "", page: int = 1, ok: str = "", error: str = ""
):
    if (chan := _chan(request)):
        return chan
    page = max(page, 1)
    rows, total = integration_service.danh_sach_log(
        provider=provider, limit=_MOI_TRANG, offset=(page - 1) * _MOI_TRANG)
    return HTMLResponse(render_nhat_ky(
        rows, total, provider=provider, page=page, per_page=_MOI_TRANG,
        ok=ok, error=error))


# ------------------------------------------------------------ tab Lỗi
@router.get("/loi", response_class=HTMLResponse)
async def trang_loi(
    request: Request, status: str = "pending", page: int = 1,
    ok: str = "", error: str = "",
):
    if (chan := _chan(request)):
        return chan
    page = max(page, 1)
    rows, total = integration_service.danh_sach_loi(
        status=status, limit=_MOI_TRANG, offset=(page - 1) * _MOI_TRANG)
    return HTMLResponse(render_loi(
        rows, total, status=status, page=page, per_page=_MOI_TRANG,
        ok=ok, error=error))


@router.post("/loi/{error_id}/thu-lai")
async def thu_lai(request: Request, error_id: int):
    if (chan := _chan(request)):
        return chan
    try:
        integration_service.thu_lai_ngay(error_id, actor=_user(request))
    except ApiError as err:
        return _back("/quan-tri/tich-hop/loi", error=err.message)
    return _back("/quan-tri/tich-hop/loi", ok="Đã xếp thử lại — worker chạy lượt kế")


@router.post("/loi/chay-ngay")
async def chay_ngay(request: Request):
    if (chan := _chan(request)):
        return chan
    kq = integration_service.chay_hang_doi()
    return _back(
        "/quan-tri/tich-hop/loi",
        ok=f"Đã thử {kq['da_thu']} dòng · xong {kq['xong']} · còn lỗi {kq['con_loi']}",
    )


# ------------------------------------------------------------ tab Ánh xạ
@router.get("/anh-xa", response_class=HTMLResponse)
async def trang_anh_xa(request: Request, ok: str = "", error: str = ""):
    if (chan := _chan(request)):
        return chan
    users, _ = user_repo.list_users(status="active", limit=100)
    return HTMLResponse(render_anh_xa(
        integration_service.danh_sach_page(),
        integration_repo.list_accounts(),
        integration_service.danh_sach_nhan_vien(),
        users,
        order_repo.list_mappings(),
        order_service.ORDER_STATUSES,
        ok=ok, error=error,
    ))


@router.post("/page/{page_id}/ket-noi")
async def gan_page(request: Request, page_id: int):
    if (chan := _chan(request)):
        return chan
    form = await _form(request)
    try:
        integration_service.gan_page_vao_ket_noi(
            page_id, _to_int(form.get("account_id", "")), actor=_user(request))
    except ApiError as err:
        return _back("/quan-tri/tich-hop/anh-xa", error=err.message)
    return _back("/quan-tri/tich-hop/anh-xa", ok="Đã gán page vào kết nối")


@router.post("/nhan-vien/dong-bo")
async def dong_bo_nhan_vien(request: Request, nguon: str = "pos"):
    """Kéo DANH SÁCH nhân viên từ Pancake về bảng ánh xạ (bấm tay).

    `nguon=pos` (POS, có email/SĐT/phòng ban) hoặc `nguon=pages` (pages.fm, chỉ
    có tên nhưng phủ được người POS không biết). Đặt TRƯỚC `POST /nhan-vien`
    cho khỏi bị nuốt đường dẫn con."""
    if (chan := _chan(request)):
        return chan
    la_pages = nguon == "pages"
    try:
        kq = await (integration_service.dong_bo_nhan_vien_pages(actor=_user(request))
                    if la_pages
                    else integration_service.dong_bo_nhan_vien_pos(actor=_user(request)))
    except ApiError as err:
        return _back("/quan-tri/tich-hop/anh-xa", error=err.message)
    them = f" · {kq['page_loi']} page gọi hỏng" if kq.get("page_loi") else ""
    return _back("/quan-tri/tich-hop/anh-xa",
                 ok=f"Lấy {kq['tong']} nhân viên từ "
                    f"{'Pancake (chat)' if la_pages else 'POS'} — "
                    f"{kq['tao_moi']} mới, {kq['cap_nhat']} cập nhật{them}")


@router.post("/nhan-vien")
async def gan_nhan_vien(request: Request):
    if (chan := _chan(request)):
        return chan
    form = await _form(request)
    try:
        row = integration_service.gan_nhan_vien(
            form.get("provider", ""), form.get("external_staff_id", ""),
            _to_int(form.get("user_id", "")), actor=_user(request))
    except ApiError as err:
        return _back("/quan-tri/tich-hop/anh-xa", error=err.message)
    # Nói rõ khi ánh xạ lan sang nguồn kia, kẻo Admin tưởng máy tự đổi bậy.
    lan = int(row.get("lan_toa") or 0)
    return _back("/quan-tri/tich-hop/anh-xa",
                 ok="Đã lưu ánh xạ nhân viên"
                    + (f" — áp cho cả {lan + 1} nguồn (cùng ID Pancake)" if lan else ""))


@router.post("/trang-thai-don/{pancake_status}")
async def sua_anh_xa_don(request: Request, pancake_status: int):
    """Màn 23 — ánh xạ mã trạng thái POS; dùng chung service với ORDER-010."""
    if (chan := _chan(request)):
        return chan
    form = await _form(request)
    try:
        order_service.update_mapping(
            pancake_status, {"crm_status": form.get("crm_status", "")},
            actor=_user(request))
    except ApiError as err:
        return _back("/quan-tri/tich-hop/anh-xa", error=err.message)
    return _back("/quan-tri/tich-hop/anh-xa",
                 ok=f"Đã sửa ánh xạ mã POS {pancake_status}")
