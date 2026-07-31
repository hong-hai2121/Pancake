"""SQL quản lý nhân viên (A5 — USER-001…006): crm.users + user_sessions.

Chỉ đọc/ghi; luật nghiệp vụ (khoá phải chuyển khách trước, audit...) nằm ở
app/services/user_service.py. Mọi câu lệnh ghi rõ tiền tố `crm.`.
"""

from app.db.client import get_pg_pool

# Cột trả cho danh sách/chi tiết — KHÔNG bao giờ kéo password_hash ra ngoài repo
_COLS = """
    u.id, u.name, u.email, u.username, u.phone, u.status,
    u.team_id, t.name as team_name, u.role_id, r.name as role_name,
    u.failed_login_count, u.locked_until, u.last_login_at, u.created_at, u.updated_at
"""
_FROM = """
    from crm.users u
    left join crm.roles r on r.id = u.role_id
    left join crm.teams t on t.id = u.team_id
"""


def list_users(
    *,
    q: str = "",
    role_id: int | None = None,
    team_id: int | None = None,
    status: str = "",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """USER-001: danh sách + tổng số (cho phân trang), lọc theo PDF API."""
    dieu_kien, tham_so = ["true"], []
    if q:
        dieu_kien.append("(u.name ilike %s or u.email ilike %s or u.username ilike %s)")
        tham_so += [f"%{q}%"] * 3
    if role_id is not None:
        dieu_kien.append("u.role_id = %s")
        tham_so.append(role_id)
    if team_id is not None:
        dieu_kien.append("u.team_id = %s")
        tham_so.append(team_id)
    if status:
        dieu_kien.append("u.status = %s")
        tham_so.append(status)
    where = " and ".join(dieu_kien)

    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"select {_COLS} {_FROM} where {where} "
            "order by u.name limit %s offset %s",
            (*tham_so, limit, offset),
        ).fetchall()
        total = conn.execute(
            f"select count(*) as n from crm.users u where {where}", tham_so or None
        ).fetchone()["n"]
    return rows, total


def get_user(user_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_COLS} {_FROM} where u.id = %s", (user_id,)
        ).fetchone()


def create_user(
    *, name: str, email: str, username: str, password_hash: str,
    phone: str | None, role_id: int | None, team_id: int | None,
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.users (name, email, username, password_hash, phone,
                                   role_id, team_id)
            values (%s, %s, %s, %s, %s, %s, %s)
            returning id, name, email, username, phone, status, role_id, team_id
            """,
            (name, email, username, password_hash, phone, role_id, team_id),
        ).fetchone()


def update_user(user_id: int, fields: dict) -> None:
    """USER-004: chỉ nhận cột cho phép — chống lọt password_hash/status qua đường sửa."""
    cho_phep = {"name", "email", "username", "phone", "role_id", "team_id"}
    gan = {k: v for k, v in fields.items() if k in cho_phep}
    if not gan:
        return
    dat = ", ".join(f"{k} = %s" for k in gan)
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            f"update crm.users set {dat} where id = %s", (*gan.values(), user_id)
        )


def set_status(user_id: int, status: str) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.users set status = %s where id = %s", (status, user_id)
        )


def dem_so_huu(user_id: int) -> dict:
    """Đếm những gì user còn ĐANG phụ trách — điều kiện FR-002 trước khi khoá.

    `customer_assignments` chỉ tính dòng đang mở (end_at null); leads/care_plans/
    repurchase chỉ tính bản ghi chưa đóng nếu bảng có cột trạng thái phù hợp —
    hiện đếm thô toàn bộ dòng trỏ về user (bảng còn trống, siết lại ở lát B).
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select
              (select count(*) from crm.customer_assignments
                where user_id = %(u)s and end_at is null)           as khach_dang_giu,
              (select count(*) from crm.leads where owner_id = %(u)s)        as leads,
              (select count(*) from crm.care_plans where owner_id = %(u)s)   as care_plans,
              (select count(*) from crm.repurchase_opportunities
                where owner_id = %(u)s)                                       as co_hoi_mua_lai,
              (select count(*) from crm.tasks
                where assigned_to = %(u)s and status not in ('done','cancelled')) as viec_dang_mo
            """,
            {"u": user_id},
        ).fetchone()


def chuyen_so_huu(
    tu_user: int,
    sang_user: int,
    *,
    transfer_leads: bool,
    transfer_care_plans: bool,
    transfer_open_tasks: bool,
) -> dict:
    """USER-006: chuyển toàn bộ sở hữu. Trả về số dòng đã chuyển theo từng loại.

    customer_assignments là bảng LỊCH SỬ: đóng dòng cũ (end_at=now) + mở dòng
    mới cho người nhận — người cũ vẫn tra được (FR-002: dữ liệu cũ giữ nguyên).
    """
    ket_qua: dict[str, int] = {}
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            update crm.customer_assignments set end_at = now()
             where user_id = %s and end_at is null
            returning customer_id, assignment_type
            """,
            (tu_user,),
        ).fetchall()
        for r in rows:
            conn.execute(
                "insert into crm.customer_assignments (customer_id, user_id, assignment_type) "
                "values (%s, %s, %s)",
                (r["customer_id"], sang_user, r["assignment_type"]),
            )
        ket_qua["khach"] = len(rows)

        if transfer_leads:
            ket_qua["leads"] = conn.execute(
                "update crm.leads set owner_id = %s where owner_id = %s",
                (sang_user, tu_user),
            ).rowcount
        if transfer_care_plans:
            ket_qua["care_plans"] = conn.execute(
                "update crm.care_plans set owner_id = %s where owner_id = %s",
                (sang_user, tu_user),
            ).rowcount
            ket_qua["co_hoi_mua_lai"] = conn.execute(
                "update crm.repurchase_opportunities set owner_id = %s where owner_id = %s",
                (sang_user, tu_user),
            ).rowcount
        if transfer_open_tasks:
            ket_qua["viec_dang_mo"] = conn.execute(
                "update crm.tasks set assigned_to = %s "
                "where assigned_to = %s and status not in ('done','cancelled')",
                (sang_user, tu_user),
            ).rowcount
    return ket_qua


def list_sessions(user_id: int, limit: int = 10) -> list[dict]:
    """Lịch sử đăng nhập + thiết bị của 1 user (màn 66 — hồ sơ nhân viên)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select id, ip_address::text as ip, user_agent, created_at,
                   last_used_at, expires_at, revoked_at
              from crm.user_sessions
             where user_id = %s
             order by created_at desc
             limit %s
            """,
            (user_id, limit),
        ).fetchall()
