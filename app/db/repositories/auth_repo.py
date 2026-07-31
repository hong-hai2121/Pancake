"""SQL cho đăng nhập (A2): crm.users · crm.user_sessions · roles · permissions.

Mọi câu lệnh ghi RÕ tiền tố `crm.` — cùng DB còn schema `public` (bot) và
`watcher` (kho hội thoại), trong đó watcher.customers TRÙNG TÊN crm.customers.
Logic nghiệp vụ (đếm sai, khoá tạm...) nằm ở app/services/auth_service.py;
file này chỉ đọc/ghi.
"""

from datetime import datetime

from app.db.client import get_pg_pool


# ------------------------------------------------------------------ users
def get_user_by_login(login: str) -> dict | None:
    """Tìm theo username HOẶC email (không phân biệt hoa thường), kèm tên vai trò."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select u.id, u.name, u.email, u.username, u.status, u.password_hash,
                   u.failed_login_count, u.locked_until, u.role_id, u.team_id,
                   coalesce(r.name, '') as role_name
              from crm.users u
              left join crm.roles r on r.id = u.role_id
             where lower(u.username) = lower(%s) or lower(u.email) = lower(%s)
             limit 1
            """,
            (login, login),
        ).fetchone()


def get_user_by_id(user_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select u.id, u.name, u.email, u.username, u.status, u.password_hash,
                   u.role_id, u.team_id, coalesce(r.name, '') as role_name
              from crm.users u
              left join crm.roles r on r.id = u.role_id
             where u.id = %s
            """,
            (user_id,),
        ).fetchone()


def get_role_permissions(role_id: int | None) -> list[str]:
    """Danh sách mã quyền của vai trò (vd ['customer.view', ...]); không vai trò -> rỗng."""
    if role_id is None:
        return []
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            select p.code
              from crm.role_permissions rp
              join crm.permissions p on p.id = rp.permission_id
             where rp.role_id = %s
             order by p.code
            """,
            (role_id,),
        ).fetchall()
    return [r["code"] for r in rows]


def record_login_failure(user_id: int) -> int:
    """Cộng 1 lần sai, trả về tổng số lần sai liên tiếp hiện tại."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """
            update crm.users
               set failed_login_count = failed_login_count + 1
             where id = %s
         returning failed_login_count
            """,
            (user_id,),
        ).fetchone()
    return row["failed_login_count"] if row else 0


def lock_user(user_id: int, until: datetime) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.users set locked_until = %s where id = %s", (until, user_id)
        )


def mark_login_success(user_id: int) -> None:
    """Đăng nhập đúng: xoá đếm sai + mở khoá + ghi last_login_at (FR-001)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            update crm.users
               set failed_login_count = 0, locked_until = null, last_login_at = now()
             where id = %s
            """,
            (user_id,),
        )


def update_password(user_id: int, password_hash: str) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.users set password_hash = %s where id = %s",
            (password_hash, user_id),
        )


# ------------------------------------------------------------------ sessions
def _ip_hop_le(ip: str | None) -> str | None:
    """Cột ip_address kiểu inet — chuỗi không phải IP (vd 'testclient' của
    TestClient, hostname từ proxy lạ) mà chèn thẳng là login nổ 500. Không
    hợp lệ thì lưu NULL, đăng nhập vẫn phải thành công."""
    if not ip:
        return None
    import ipaddress

    try:
        ipaddress.ip_address(ip)
        return ip
    except ValueError:
        return None


def create_session(
    *,
    user_id: int,
    refresh_token_hash: str,
    ip: str | None,
    user_agent: str | None,
    expires_at: datetime,
) -> int:
    ip = _ip_hop_le(ip)
    pool = get_pg_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """
            insert into crm.user_sessions
                   (user_id, refresh_token_hash, ip_address, user_agent, expires_at)
            values (%s, %s, %s, %s, %s)
         returning id
            """,
            (user_id, refresh_token_hash, ip, user_agent, expires_at),
        ).fetchone()
    return row["id"]


def get_active_session(refresh_token_hash: str) -> dict | None:
    """Phiên CÒN hiệu lực khớp hash: chưa thu hồi, chưa hết hạn, kèm trạng thái user."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select s.id, s.user_id, s.expires_at, u.status,
                   u.name, u.username, u.role_id, coalesce(r.name,'') as role_name
              from crm.user_sessions s
              join crm.users u on u.id = s.user_id
              left join crm.roles r on r.id = u.role_id
             where s.refresh_token_hash = %s
               and s.revoked_at is null
               and s.expires_at > now()
            """,
            (refresh_token_hash,),
        ).fetchone()


def touch_session(session_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.user_sessions set last_used_at = now() where id = %s",
            (session_id,),
        )


def revoke_session(session_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.user_sessions set revoked_at = now() "
            "where id = %s and revoked_at is null",
            (session_id,),
        )


def revoke_all_sessions(user_id: int, keep_session_id: int | None = None) -> int:
    """Thu hồi mọi phiên của user (đổi mật khẩu). `keep_session_id` = phiên đang
    thao tác, giữ lại để người đổi không tự văng mình ra. Trả số phiên bị thu hồi."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            """
            update crm.user_sessions set revoked_at = now()
             where user_id = %s and revoked_at is null
               and (%s::bigint is null or id <> %s)
            """,
            (user_id, keep_session_id, keep_session_id),
        )
    return cur.rowcount
