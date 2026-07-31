"""Dependency xác thực + phân quyền cho route (A2 + A3).

Middleware trong app/main.py đã chặn "chưa đăng nhập" từ ngoài cửa; ở đây:
  * `get_current_user`        — đọc người dùng hiện tại (payload token)
  * `require_permission(mã)`  — chặn theo QUYỀN, dùng:
        user: dict = Depends(require_permission("customer.view"))
Quyền nằm sẵn trong access token (nạp lúc đăng nhập) nên không query DB —
đổi quyền của vai trò sẽ ăn ở lần refresh/đăng nhập kế (tối đa 30 phút).
"""

from fastapi import HTTPException, Request

from app.core.errors import ApiError
from app.core.security import decode_access_token


def user_from_request(request: Request) -> dict | None:
    """Lấy payload token: ưu tiên header Bearer (API), rớt xuống cookie (web)."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return decode_access_token(auth[7:].strip())
    return decode_access_token(request.cookies.get("access_token", ""))


def get_current_user(request: Request) -> dict:
    """Bản 'bắt buộc có' — middleware đã gắn sẵn vào request.state khi hợp lệ."""
    user = getattr(request.state, "user", None) or user_from_request(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={
                "success": False,
                "error_code": "UNAUTHORIZED",
                "message": "Chưa đăng nhập hoặc phiên đã hết hạn",
            },
        )
    return user


def require_permission(ma_quyen: str):
    """Factory dependency: user phải CÓ quyền `ma_quyen`, không thì FORBIDDEN (A3)."""

    def _check(request: Request) -> dict:
        user = get_current_user(request)
        if ma_quyen not in (user.get("perms") or []):
            raise ApiError(
                "FORBIDDEN",
                f"Bạn không có quyền này ({ma_quyen}) — liên hệ Admin nếu cần cấp",
            )
        return user

    return _check


def co_quyen(user: dict | None, ma_quyen: str) -> bool:
    """Kiểm quyền 'mềm' cho web/view (ẩn nút, ẩn mục menu) — không raise."""
    return bool(user) and ma_quyen in (user.get("perms") or [])
