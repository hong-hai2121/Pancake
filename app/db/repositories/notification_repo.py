"""Truy vấn crm.notifications + notification_settings (màn 3 · NOTIFY-001…004).

Chỉ SQL — 11 nguồn quét và luật gửi cho ai nằm ở services/notification_service.py.
"""

from app.db.client import get_pg_pool


def day(
    *, user_id: int, type_: str, title: str, dedupe_key: str,
    body: str | None = None, link: str | None = None,
    priority: str = "normal",
    related_type: str | None = None, related_id: int | None = None,
) -> bool:
    """Đẩy 1 thông báo. Trả True nếu vừa TẠO MỚI thật sự.

    `on conflict do nothing` theo (user_id, dedupe_key): worker quét lại mỗi
    vài phút vẫn chỉ một dòng cho mỗi sự việc — kể cả khi người ta đã đọc và
    sự việc vẫn còn đó (đọc rồi thì không réo lại nữa).
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """
            insert into crm.notifications
                   (user_id, type, title, body, link, priority,
                    related_type, related_id, dedupe_key)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (user_id, dedupe_key) do nothing
            returning id
            """,
            (user_id, type_, title, body, link, priority,
             related_type, related_id, dedupe_key),
        ).fetchone()
    return row is not None


def list_notifications(
    *, user_id: int, chua_doc: bool = False, type_: str = "",
    limit: int = 20, offset: int = 0,
) -> tuple[list[dict], int]:
    """NOTIFY-001 — mới nhất trước, của ĐÚNG người đang đăng nhập."""
    dk, ts = ["user_id = %s"], [user_id]
    if chua_doc:
        dk.append("read_at is null")
    if type_:
        dk.append("type = %s")
        ts.append(type_)
    where = " and ".join(dk)
    pool = get_pg_pool()
    with pool.connection() as conn:
        total = conn.execute(
            f"select count(*) as n from crm.notifications where {where}", ts
        ).fetchone()["n"]
        rows = conn.execute(
            f"select * from crm.notifications where {where} "
            "order by read_at is null desc, created_at desc limit %s offset %s",
            [*ts, limit, offset],
        ).fetchall()
    return rows, total


def dem_chua_doc(user_id: int) -> dict:
    """Số chưa đọc tổng + tách theo loại — chuông trên thanh menu + màn 3."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select type, count(*) as n from crm.notifications "
            "where user_id = %s and read_at is null group by type",
            (user_id,),
        ).fetchall()
    theo_loai = {r["type"]: r["n"] for r in rows}
    return {"tong": sum(theo_loai.values()), "theo_loai": theo_loai}


def danh_dau_doc(notification_id: int, user_id: int) -> dict | None:
    """NOTIFY-002 — chỉ đánh dấu được thông báo CỦA MÌNH (user_id trong WHERE)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.notifications set read_at = now() "
            "where id = %s and user_id = %s and read_at is null returning *",
            (notification_id, user_id),
        ).fetchone()


def get(notification_id: int, user_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.notifications where id = %s and user_id = %s",
            (notification_id, user_id),
        ).fetchone()


def danh_dau_doc_het(user_id: int) -> int:
    """NOTIFY-003 — trả số dòng vừa đánh dấu."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.notifications set read_at = now() "
            "where user_id = %s and read_at is null",
            (user_id,),
        ).rowcount


# ------------------------------------------------------------------ cài đặt
def cai_dat(user_id: int) -> dict:
    """{type: enabled} — CHỈ các loại người đó đã đổi; thiếu = bật."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select type, enabled from crm.notification_settings where user_id = %s",
            (user_id,),
        ).fetchall()
    return {r["type"]: r["enabled"] for r in rows}


def dat_cai_dat(user_id: int, doi: dict[str, bool]) -> None:
    """NOTIFY-004 — lưu cả mẻ, upsert theo (user, type)."""
    if not doi:
        return
    pool = get_pg_pool()
    with pool.connection() as conn, conn.transaction():
        for loai, bat in doi.items():
            conn.execute(
                """
                insert into crm.notification_settings (user_id, type, enabled)
                values (%s, %s, %s)
                on conflict (user_id, type) do update
                    set enabled = excluded.enabled, updated_at = now()
                """,
                (user_id, loai, bool(bat)),
            )


def dang_tat(loai: str) -> set[int]:
    """Tập user_id đã TẮT loại này — nguồn quét bỏ qua họ, khỏi ghi rác."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select user_id from crm.notification_settings "
            "where type = %s and enabled = false",
            (loai,),
        ).fetchall()
    return {r["user_id"] for r in rows}


# ------------------------------------------------------------------ người nhận
def users_theo_vai_tro(ten_vai_tro: str) -> list[int]:
    """Người đang active của MỘT vai trò — dùng khi bản ghi chưa gán ai mà
    việc đó thuộc đúng một bộ phận (ca lâm sàng -> Người chuyên môn, giống
    chỗ B5 giao task duyet_chuyen_mon)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select u.id from crm.users u join crm.roles r on r.id = u.role_id "
            "where r.name = %s and u.status = 'active'",
            (ten_vai_tro,),
        ).fetchall()
    return [r["id"] for r in rows]


def users_co_quyen(ma_quyen: str) -> list[int]:
    """Ai đang có quyền này (qua vai trò) — dùng cho thông báo "gửi bộ phận":
    nội dung chờ duyệt -> content.approve, lỗi đồng bộ -> integration.manage."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            select u.id from crm.users u
              join crm.role_permissions rp on rp.role_id = u.role_id
              join crm.permissions p on p.id = rp.permission_id
             where p.code = %s and u.status = 'active'
            """,
            (ma_quyen,),
        ).fetchall()
    return [r["id"] for r in rows]


def don_rac(ngay: int = 60) -> int:
    """Xoá thông báo ĐÃ ĐỌC quá cũ — bảng này phình nhanh, giữ 60 ngày là đủ.

    Chưa đọc thì KHÔNG xoá dù cũ mấy (người ta chưa xem thì chưa được mất)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "delete from crm.notifications where read_at is not null "
            "and read_at < now() - make_interval(days => %s::int)",
            (ngay,),
        ).rowcount
