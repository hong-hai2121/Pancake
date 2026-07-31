"""AUTH-001…006 — 6 API xác thực dưới /api/v1/auth (A2, refactor A3).

Từ A3: khuôn phản hồi lấy từ app/core/response.py, lỗi nghiệp vụ (AuthError —
là ApiError) để exception handler chung trong app/main.py đổi thành JSON,
route không try/except nữa.
"""

from fastapi import APIRouter, Depends, Request

from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.response import ok
from app.schemas.auth import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    LogoutIn,
    RefreshIn,
)
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _ip_ua(request: Request) -> tuple[str | None, str]:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent", "")[:300]


@router.post("/login")
async def login(body: LoginIn, request: Request):
    """AUTH-001 — đăng nhập bằng username hoặc email."""
    ip, ua = _ip_ua(request)
    data = auth_service.login(body.username, body.password, ip=ip, user_agent=ua)
    return ok(data, "Đăng nhập thành công")


@router.post("/refresh")
async def refresh(body: RefreshIn, request: Request):
    """AUTH-002 — đổi refresh token lấy access token mới."""
    ip, ua = _ip_ua(request)
    return ok(auth_service.refresh(body.refresh_token, ip=ip, user_agent=ua))


@router.post("/logout")
async def logout(
    body: LogoutIn, request: Request, user: dict = Depends(get_current_user)
):
    """AUTH-003 — thu hồi phiên hiện tại."""
    ip, ua = _ip_ua(request)
    auth_service.logout(
        body.refresh_token, user_id=int(user["sub"]), ip=ip, user_agent=ua
    )
    return ok(message="Đã đăng xuất")


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """AUTH-004 — thông tin tài khoản hiện tại, đọc thẳng từ token (không query DB)."""
    return ok(
        {
            "id": int(user["sub"]),
            "username": user.get("username"),
            "name": user.get("name"),
            "role": user.get("role"),
            "permissions": user.get("perms", []),
        }
    )


@router.post("/change-password")
async def change_password(
    body: ChangePasswordIn, request: Request, user: dict = Depends(get_current_user)
):
    """AUTH-005 — đổi mật khẩu; thu hồi mọi phiên khác của chính mình."""
    ip, ua = _ip_ua(request)
    so_thu_hoi = auth_service.change_password(
        int(user["sub"]),
        body.old_password,
        body.new_password,
        keep_session_id=user.get("sid"),
        ip=ip,
        user_agent=ua,
    )
    return ok(
        {"revoked_sessions": so_thu_hoi},
        "Đã đổi mật khẩu — các thiết bị khác phải đăng nhập lại",
    )


@router.post("/forgot-password")
async def forgot_password(_body: ForgotPasswordIn):
    """AUTH-006 — CHƯA làm tự động (cần hạ tầng email, để sau). Trả hướng dẫn."""
    raise ApiError(
        "NOT_IMPLEMENTED",
        "Chưa hỗ trợ tự đặt lại mật khẩu — liên hệ Admin để được cấp lại",
    )
