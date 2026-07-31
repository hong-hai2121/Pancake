"""Route khu Quản trị (A5): /quan-tri/... — cần quyền `user.manage`
(riêng nhật ký: `audit.view`). Gọi chung services với API nên luật + audit
chỉ có một chỗ; lỗi nghiệp vụ (ApiError) hiện thành dải đỏ trên trang.
"""

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import co_quyen
from app.core.errors import ApiError
from app.db.repositories import audit_repo, org_repo, user_repo
from app.services import org_service, user_service
from app.web.views.admin import (
    render_403,
    render_audit,
    render_roles,
    render_user_detail,
    render_users,
)

router = APIRouter(prefix="/quan-tri", tags=["web-admin"])


def _user(request: Request) -> dict:
    return getattr(request.state, "user", None) or {}


def _chan(request: Request, quyen: str = "user.manage") -> HTMLResponse | None:
    if not co_quyen(_user(request), quyen):
        return HTMLResponse(render_403(), status_code=403)
    return None


def _ip_ua(request: Request) -> dict:
    return {
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:300],
    }


def _back(path: str, ok: str = "", error: str = "") -> RedirectResponse:
    tham_so = f"?ok={quote(ok)}" if ok else (f"?error={quote(error)}" if error else "")
    return RedirectResponse(path + tham_so, status_code=303)


async def _form(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: str(v).strip() for k, v in form.items()}


def _to_int(v: str) -> int | None:
    return int(v) if v.strip().isdigit() else None


# ------------------------------------------------------------ nhân viên
@router.get("/nhan-vien", response_class=HTMLResponse)
async def users_page(request: Request, q: str = "", ok: str = "", error: str = ""):
    if chan := _chan(request):
        return chan
    users, _total = user_repo.list_users(q=q, limit=100)
    return HTMLResponse(render_users(
        users, org_repo.list_roles(), org_repo.list_teams(), q=q, ok=ok, error=error,
    ))


@router.post("/nhan-vien")
async def create_user(request: Request):
    if chan := _chan(request):
        return chan
    f = await _form(request)
    try:
        data = user_service.create_user(
            {
                "name": f.get("name", ""), "email": f.get("email", ""),
                "username": f.get("username", ""),
                "password": f.get("password") or None,
                "role_id": _to_int(f.get("role_id", "")),
                "team_id": _to_int(f.get("team_id", "")),
            },
            actor=_user(request), **_ip_ua(request),
        )
    except ApiError as err:
        return _back("/quan-tri/nhan-vien", error=err.message)
    return _back(
        "/quan-tri/nhan-vien",
        ok=f"Đã tạo {data['username']} — mật khẩu (hiện MỘT lần): {data['initial_password']}",
    )


@router.get("/nhan-vien/{user_id}", response_class=HTMLResponse)
async def user_detail(request: Request, user_id: int, ok: str = "", error: str = ""):
    if chan := _chan(request):
        return chan
    u = user_repo.get_user(user_id)
    if not u:
        return _back("/quan-tri/nhan-vien", error="Không tìm thấy nhân viên")
    others = [
        x for x in user_repo.list_users(status="active", limit=100)[0]
        if x["id"] != user_id
    ]
    return HTMLResponse(render_user_detail(
        u, org_repo.list_roles(), org_repo.list_teams(), others,
        user_repo.list_sessions(user_id), ok=ok, error=error,
    ))


@router.post("/nhan-vien/{user_id}/sua")
async def edit_user(request: Request, user_id: int):
    if chan := _chan(request):
        return chan
    f = await _form(request)
    try:
        user_service.update_user(
            user_id,
            {
                "name": f.get("name") or None, "email": f.get("email") or None,
                "username": f.get("username") or None,
                "phone": f.get("phone") or None,
                "role_id": _to_int(f.get("role_id", "")),
                "team_id": _to_int(f.get("team_id", "")),
            },
            actor=_user(request), **_ip_ua(request),
        )
    except ApiError as err:
        return _back(f"/quan-tri/nhan-vien/{user_id}", error=err.message)
    return _back(f"/quan-tri/nhan-vien/{user_id}", ok="Đã lưu thay đổi")


@router.post("/nhan-vien/{user_id}/trang-thai")
async def user_status(request: Request, user_id: int):
    if chan := _chan(request):
        return chan
    f = await _form(request)
    try:
        u = user_service.set_status(
            user_id, f.get("status", ""), actor=_user(request), **_ip_ua(request)
        )
    except ApiError as err:
        chi_tiet = "; ".join(f"{k} {v}" for k, v in err.errors.items())
        return _back("/quan-tri/nhan-vien",
                     error=err.message + (f" ({chi_tiet})" if chi_tiet else ""))
    return _back("/quan-tri/nhan-vien", ok=f"{u['username']}: {u['status']}")


@router.post("/nhan-vien/{user_id}/reset-mat-khau")
async def user_reset_password(request: Request, user_id: int):
    if chan := _chan(request):
        return chan
    try:
        data = user_service.reset_password(
            user_id, actor=_user(request), **_ip_ua(request)
        )
    except ApiError as err:
        return _back("/quan-tri/nhan-vien", error=err.message)
    return _back(
        "/quan-tri/nhan-vien",
        ok=f"Mật khẩu mới (hiện MỘT lần): {data['new_password']}",
    )


@router.post("/nhan-vien/{user_id}/chuyen-khach")
async def user_transfer(request: Request, user_id: int):
    if chan := _chan(request):
        return chan
    f = await _form(request)
    nguoi_nhan = _to_int(f.get("new_owner_id", ""))
    if not nguoi_nhan:
        return _back(f"/quan-tri/nhan-vien/{user_id}", error="Chưa chọn người nhận")
    try:
        kq = user_service.transfer_customers(
            user_id, {"new_owner_id": nguoi_nhan},
            actor=_user(request), **_ip_ua(request),
        )
    except ApiError as err:
        return _back(f"/quan-tri/nhan-vien/{user_id}", error=err.message)
    so = ", ".join(f"{k}: {v}" for k, v in kq.items() if isinstance(v, int))
    return _back(f"/quan-tri/nhan-vien/{user_id}",
                 ok=f"Đã chuyển sang {kq['to']} ({so or 'không có gì để chuyển'})")


# ------------------------------------------------------------ vai trò & quyền
@router.get("/phan-quyen", response_class=HTMLResponse)
async def roles_page(request: Request, ok: str = "", error: str = ""):
    if chan := _chan(request):
        return chan
    users, _ = user_repo.list_users(status="active", limit=100)
    return HTMLResponse(render_roles(
        org_repo.list_roles(), org_repo.list_permissions(),
        org_repo.list_teams(), users, ok=ok, error=error,
    ))


@router.post("/phan-quyen/{role_id:int}")
async def save_role_perms(request: Request, role_id: int):
    if chan := _chan(request):
        return chan
    form = await request.form()
    perms = [str(v) for v in form.getlist("perm")]
    try:
        org_service.set_role_permissions(
            role_id, perms, actor=_user(request), **_ip_ua(request)
        )
    except ApiError as err:
        return _back("/quan-tri/phan-quyen", error=err.message)
    return _back("/quan-tri/phan-quyen", ok=f"Đã lưu {len(perms)} quyền cho vai trò")


@router.post("/phan-quyen/vai-tro")
async def create_role(request: Request):
    if chan := _chan(request):
        return chan
    f = await _form(request)
    try:
        role = org_service.create_role(
            f.get("name", ""), f.get("description") or None,
            actor=_user(request), **_ip_ua(request),
        )
    except ApiError as err:
        return _back("/quan-tri/phan-quyen", error=err.message)
    return _back("/quan-tri/phan-quyen", ok=f"Đã tạo vai trò {role['name']}")


@router.post("/phan-quyen/nhom")
async def create_team(request: Request):
    if chan := _chan(request):
        return chan
    f = await _form(request)
    try:
        team = org_service.create_team(
            f.get("name", ""), f.get("department") or None,
            _to_int(f.get("manager_id", "")),
            actor=_user(request), **_ip_ua(request),
        )
    except ApiError as err:
        return _back("/quan-tri/phan-quyen", error=err.message)
    return _back("/quan-tri/phan-quyen", ok=f"Đã tạo nhóm {team['name']}")


# ------------------------------------------------------------ nhật ký
@router.get("/nhat-ky", response_class=HTMLResponse)
async def audit_page(
    request: Request, action: str = "", page: int = 1, ok: str = "", error: str = ""
):
    if chan := _chan(request, "audit.view"):
        return chan
    page = max(page, 1)
    rows, total = audit_repo.list_logs(action=action, limit=30, offset=(page - 1) * 30)
    return HTMLResponse(render_audit(
        rows, total, action=action, page=page, ok=ok, error=error,
    ))
