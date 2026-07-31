"""Băm mật khẩu + phát/kiểm token (A2 — docs/A2-DANG-NHAP.md).

3 nhóm hàm thuần, KHÔNG đụng DB và KHÔNG import FastAPI:

  * bcrypt   : `hash_password` / `verify_password`
  * JWT      : `create_access_token` / `decode_access_token` (HS256, sống 30')
  * refresh  : `new_refresh_token` (ngẫu nhiên 256-bit) + `hash_refresh_token`
               (DB chỉ giữ SHA-256 — lộ DB cũng không dùng lại được token)

Payload access token mang sẵn vai trò + danh sách quyền, nên middleware và
phân quyền A3 đọc thẳng từ token, không phải query DB mỗi request.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


# ------------------------------------------------------------------ mật khẩu
def hash_password(plain: str) -> str:
    """Băm bcrypt (salt sinh mới mỗi lần — 2 lần băm cùng 1 mật khẩu ra 2 chuỗi khác nhau)."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str | None) -> bool:
    """So mật khẩu với chuỗi băm. Hash rỗng (tài khoản SSO chưa đặt mật khẩu) -> False."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:  # chuỗi trong DB không phải định dạng bcrypt
        return False


# ------------------------------------------------------------------ JWT access
def _secret() -> str:
    if not settings.jwt_secret:
        raise RuntimeError(
            "Thiếu JWT_SECRET trong .env — sinh bằng: "
            "python -c \"import secrets;print(secrets.token_hex(32))\""
        )
    return settings.jwt_secret


def create_access_token(
    *,
    user_id: int,
    username: str,
    name: str,
    role: str,
    permissions: list[str],
    session_id: int,
) -> str:
    """Phát JWT sống `access_token_ttl_minutes` phút, mang đủ danh tính + quyền.

    `sid` = id dòng user_sessions sinh ra token này — để về sau (A3+) có thể
    đối chiếu thu hồi mà không phá cấu trúc token.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),          # chuẩn JWT: sub phải là chuỗi
        "username": username,
        "name": name,
        "role": role,
        "perms": permissions,
        "sid": session_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    """Giải mã + kiểm chữ ký/hạn. Hỏng kiểu gì cũng trả None (không phân biệt lý do)."""
    if not token:
        return None
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None


# ------------------------------------------------------------------ refresh
def new_refresh_token() -> str:
    """Chuỗi ngẫu nhiên 256-bit, URL-safe (~43 ký tự)."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 hex — dùng làm khoá tra trong user_sessions."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
