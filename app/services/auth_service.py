"""Nghiệp vụ đăng nhập (A2 — docs/A2-DANG-NHAP.md mục 3.3, FR-001).

KHÔNG import FastAPI — nhận giá trị vào, trả dict/raise AuthError, để test được
chay không cần dựng HTTP. Cả API JSON lẫn form web đều gọi xuống đây.

Nguyên tắc báo lỗi: sai tài khoản hay sai mật khẩu đều trả CHUNG một câu
("Sai tài khoản hoặc mật khẩu") — không để kẻ dò đoán được tài khoản nào tồn tại.
Riêng khoá tạm và tài khoản bị vô hiệu thì nói rõ, vì người dùng thật cần biết.
"""

from datetime import datetime, timedelta, timezone

from app.core import security
from app.core.config import settings
from app.core.errors import ApiError
from app.db.repositories import audit_repo, auth_repo


class AuthError(ApiError):
    """Lỗi nghiệp vụ đăng nhập — là ApiError nên exception handler chung (A3)
    tự đổi thành JSON envelope, route không cần try/except."""


_MSG_SAI = "Sai tài khoản hoặc mật khẩu"


def _phat_token(user: dict, *, ip: str | None, user_agent: str | None) -> dict:
    """Đăng nhập đã hợp lệ: tạo phiên + phát cặp token. Dùng chung cho login/refresh."""
    perms = auth_repo.get_role_permissions(user.get("role_id"))
    refresh = security.new_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_ttl_days
    )
    session_id = auth_repo.create_session(
        user_id=user["id"],
        refresh_token_hash=security.hash_refresh_token(refresh),
        ip=ip,
        user_agent=user_agent,
        expires_at=expires_at,
    )
    access = security.create_access_token(
        user_id=user["id"],
        username=user.get("username") or "",
        name=user.get("name") or "",
        role=user.get("role_name") or "",
        permissions=perms,
        session_id=session_id,
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_minutes * 60,
        "user": {
            "id": user["id"],
            "name": user.get("name"),
            "username": user.get("username"),
            "email": user.get("email"),
            "role": user.get("role_name") or "",
            "permissions": perms,
        },
    }


def login(
    login_name: str,
    password: str,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Luồng FR-001 đầy đủ. Trả dict token + user; sai thì raise AuthError."""
    login_name = (login_name or "").strip()
    user = auth_repo.get_user_by_login(login_name) if login_name else None

    # 1. Tài khoản không tồn tại — vẫn ghi audit (kèm tên gõ vào, KHÔNG kèm mật khẩu)
    if not user:
        audit_repo.ghi(
            action="login_failed", object_type="users",
            reason=f"tai khoan khong ton tai: {login_name[:80]}",
            ip=ip, user_agent=user_agent,
        )
        raise AuthError("UNAUTHORIZED", _MSG_SAI)

    # 2. Đang bị khoá tạm (FR-001: sai quá số lần quy định)
    locked_until = user.get("locked_until")
    if locked_until and locked_until > datetime.now(timezone.utc):
        con_lai = int((locked_until - datetime.now(timezone.utc)).total_seconds() // 60) + 1
        audit_repo.ghi(
            action="login_failed", object_type="users", object_id=user["id"],
            user_id=user["id"], reason="dang bi khoa tam",
            ip=ip, user_agent=user_agent,
        )
        raise AuthError(
            "ACCOUNT_LOCKED",
            f"Tài khoản tạm khoá do sai mật khẩu nhiều lần — thử lại sau {con_lai} phút",
        )

    # 3. Tài khoản bị vô hiệu (nghỉ việc / bị khoá tay)
    if user.get("status") != "active":
        audit_repo.ghi(
            action="login_failed", object_type="users", object_id=user["id"],
            user_id=user["id"], reason=f"status={user.get('status')}",
            ip=ip, user_agent=user_agent,
        )
        raise AuthError("ACCOUNT_DISABLED", "Tài khoản đã bị khoá — liên hệ Admin")

    # 4. Kiểm mật khẩu; sai lần thứ N thì đặt khoá tạm
    if not security.verify_password(password, user.get("password_hash")):
        so_lan = auth_repo.record_login_failure(user["id"])
        if so_lan >= settings.login_max_failed:
            auth_repo.lock_user(
                user["id"],
                datetime.now(timezone.utc)
                + timedelta(minutes=settings.login_lock_minutes),
            )
        audit_repo.ghi(
            action="login_failed", object_type="users", object_id=user["id"],
            user_id=user["id"], reason=f"sai mat khau (lan {so_lan})",
            ip=ip, user_agent=user_agent,
        )
        if so_lan >= settings.login_max_failed:
            raise AuthError(
                "ACCOUNT_LOCKED",
                f"Sai mật khẩu {so_lan} lần — tài khoản tạm khoá "
                f"{settings.login_lock_minutes} phút",
            )
        raise AuthError("UNAUTHORIZED", _MSG_SAI)

    # 5. Hợp lệ: phát token, reset đếm sai, ghi audit
    ket_qua = _phat_token(user, ip=ip, user_agent=user_agent)
    auth_repo.mark_login_success(user["id"])
    audit_repo.ghi(
        action="login", object_type="users", object_id=user["id"],
        user_id=user["id"], ip=ip, user_agent=user_agent,
    )
    return ket_qua


def refresh(
    refresh_token: str,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Đổi refresh token còn hiệu lực lấy access token mới (AUTH-002).

    KHÔNG xoay refresh token — phiên giữ nguyên tới khi hết 14 ngày hoặc logout;
    chỉ cập nhật last_used_at để màn lịch sử đăng nhập (A5) biết phiên còn sống.
    """
    session = auth_repo.get_active_session(security.hash_refresh_token(refresh_token or ""))
    if not session:
        raise AuthError("UNAUTHORIZED", "Phiên đăng nhập hết hạn — đăng nhập lại")
    if session.get("status") != "active":
        raise AuthError("ACCOUNT_DISABLED", "Tài khoản đã bị khoá — liên hệ Admin")

    perms = auth_repo.get_role_permissions(session.get("role_id"))
    access = security.create_access_token(
        user_id=session["user_id"],
        username=session.get("username") or "",
        name=session.get("name") or "",
        role=session.get("role_name") or "",
        permissions=perms,
        session_id=session["id"],
    )
    auth_repo.touch_session(session["id"])
    return {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_minutes * 60,
    }


def logout(
    refresh_token: str,
    *,
    user_id: int | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Thu hồi phiên của refresh token (AUTH-003). Token lạ/hết hạn thì thôi —
    logout phải luôn 'thành công' phía người dùng."""
    session = auth_repo.get_active_session(security.hash_refresh_token(refresh_token or ""))
    if session:
        auth_repo.revoke_session(session["id"])
        audit_repo.ghi(
            action="logout", object_type="users", object_id=session["user_id"],
            user_id=session["user_id"], ip=ip, user_agent=user_agent,
        )
    elif user_id:
        # Không còn refresh (cookie phiên đã mất) nhưng vẫn ghi dấu đăng xuất
        audit_repo.ghi(
            action="logout", object_type="users", object_id=user_id,
            user_id=user_id, ip=ip, user_agent=user_agent,
        )


def change_password(
    user_id: int,
    old_password: str,
    new_password: str,
    *,
    keep_session_id: int | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> int:
    """AUTH-005. Đổi xong thu hồi MỌI phiên khác của user (mục 3.2 mô tả A2).

    Trả về số phiên bị thu hồi. `keep_session_id` = phiên đang thao tác (giữ lại).
    """
    if len(new_password or "") < 8:
        raise AuthError("VALIDATION_ERROR", "Mật khẩu mới phải từ 8 ký tự")
    user = auth_repo.get_user_by_id(user_id)
    if not user or user.get("status") != "active":
        raise AuthError("ACCOUNT_DISABLED", "Tài khoản đã bị khoá — liên hệ Admin")
    if not security.verify_password(old_password, user.get("password_hash")):
        audit_repo.ghi(
            action="change_password_failed", object_type="users", object_id=user_id,
            user_id=user_id, reason="sai mat khau cu", ip=ip, user_agent=user_agent,
        )
        raise AuthError("UNAUTHORIZED", "Mật khẩu hiện tại không đúng")

    auth_repo.update_password(user_id, security.hash_password(new_password))
    so_thu_hoi = auth_repo.revoke_all_sessions(user_id, keep_session_id=keep_session_id)
    audit_repo.ghi(
        action="change_password", object_type="users", object_id=user_id,
        user_id=user_id, reason=f"thu hoi {so_thu_hoi} phien khac",
        ip=ip, user_agent=user_agent,
    )
    return so_thu_hoi
