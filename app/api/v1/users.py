"""USER-001…006 + đặt lại mật khẩu (A5). Tất cả đòi quyền `user.manage`."""

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import require_permission
from app.core.errors import ApiError
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.db.repositories import user_repo
from app.schemas.user import TransferIn, UserCreateIn, UserStatusIn, UserUpdateIn
from app.services import user_service

router = APIRouter(prefix="/api/v1/users", tags=["users"])

_can_quyen = Depends(require_permission("user.manage"))


def _ip_ua(request: Request) -> dict:
    return {
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:300],
    }


@router.get("")
async def list_users(
    q: str = "",
    role_id: int | None = Query(None),
    team_id: int | None = Query(None),
    status: str = Query("", pattern="^(active|inactive|suspended)?$"),
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _can_quyen,
):
    """USER-001 — lọc theo vai trò/nhóm/trạng thái/từ khoá."""
    rows, total = user_repo.list_users(
        q=q, role_id=role_id, team_id=team_id, status=status,
        limit=pt.limit, offset=pt.offset,
    )
    return ok(bao_trang(rows, total, pt))


@router.get("/{user_id}")
async def get_user(user_id: int, _user: dict = _can_quyen):
    """USER-002 — kèm 10 phiên đăng nhập gần nhất (màn 66)."""
    user = user_repo.get_user(user_id)
    if not user:
        raise ApiError("NOT_FOUND", "Không tìm thấy nhân viên")
    return ok({**user, "sessions": user_repo.list_sessions(user_id)})


@router.post("", status_code=201)
async def create_user(body: UserCreateIn, request: Request, user: dict = _can_quyen):
    """USER-003 — `initial_password` chỉ trả MỘT lần, đưa tay cho nhân viên."""
    data = user_service.create_user(
        body.model_dump(), actor=user, **_ip_ua(request)
    )
    return ok(data, "Đã tạo tài khoản")


@router.put("/{user_id}")
async def update_user(
    user_id: int, body: UserUpdateIn, request: Request, user: dict = _can_quyen
):
    """USER-004."""
    data = user_service.update_user(
        user_id, body.model_dump(), actor=user, **_ip_ua(request)
    )
    return ok(data, "Đã cập nhật")


@router.patch("/{user_id}/status")
async def set_status(
    user_id: int, body: UserStatusIn, request: Request, user: dict = _can_quyen
):
    """USER-005 — khoá đòi hết khách/việc đang giữ (FR-002), thu hồi phiên ngay."""
    data = user_service.set_status(
        user_id, body.status, actor=user, reason=body.reason, **_ip_ua(request)
    )
    return ok(data, "Đã đổi trạng thái")


@router.post("/{user_id}/reset-password")
async def reset_password(user_id: int, request: Request, user: dict = _can_quyen):
    """FR-002 'Đặt lại mật khẩu' — mật khẩu mới chỉ hiện MỘT lần."""
    return ok(
        user_service.reset_password(user_id, actor=user, **_ip_ua(request)),
        "Đã cấp mật khẩu mới — mọi phiên của nhân viên này bị đăng xuất",
    )


@router.post("/{user_id}/transfer-customers")
async def transfer_customers(
    user_id: int, body: TransferIn, request: Request, user: dict = _can_quyen
):
    """USER-006 — chuyển toàn bộ khách/lead/kế hoạch chăm/việc đang mở."""
    data = user_service.transfer_customers(
        user_id, body.model_dump(), actor=user, **_ip_ua(request)
    )
    return ok(data, "Đã chuyển toàn bộ cho người nhận")
