"""crm.audit_logs — bảng CHỈ GHI THÊM (FR-180).

`ghi(...)` dùng ở MỌI thao tác ghi dữ liệu (A4); `list_logs`/`get_log` phục vụ
API AUDIT-001/002 + màn 77. Ghi audit là best-effort: lỗi ở đây KHÔNG được làm
hỏng thao tác chính (đăng nhập vẫn phải thành công kể cả khi ghi log trục
trặc) — nhưng in cảnh báo để không nuốt lỗi âm thầm.
"""

import sys

from psycopg.types.json import Jsonb

from app.db.client import get_pg_pool


def ghi(
    *,
    action: str,
    object_type: str,
    user_id: int | None = None,
    object_id: int | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    reason: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Chèn 1 dòng audit. TUYỆT ĐỐI không đưa mật khẩu/token vào old/new_value."""
    # Cột ip_address kiểu inet: chuỗi không phải IP (TestClient gửi 'testclient',
    # proxy lạ gửi hostname) sẽ làm INSERT hỏng -> mất vết audit lặng lẽ. Lọc trước.
    if ip:
        import ipaddress

        try:
            ipaddress.ip_address(ip)
        except ValueError:
            ip = None
    try:
        pool = get_pg_pool()
        with pool.connection() as conn:
            conn.execute(
                """
                insert into crm.audit_logs
                       (user_id, action, object_type, object_id,
                        old_value, new_value, reason, ip_address, user_agent)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id, action, object_type, object_id,
                    Jsonb(old_value) if old_value is not None else None,
                    Jsonb(new_value) if new_value is not None else None,
                    reason, ip, user_agent,
                ),
            )
    except Exception as err:  # noqa: BLE001 — best-effort, xem docstring
        print(
            f"[audit] KHONG ghi duoc audit_logs ({action}): {err}",
            file=sys.stderr,
        )


def list_logs(
    *,
    user_id: int | None = None,
    action: str = "",
    object_type: str = "",
    object_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """AUDIT-001: mới nhất trước, kèm tên người thao tác."""
    dieu_kien, tham_so = ["true"], []
    if user_id is not None:
        dieu_kien.append("a.user_id = %s")
        tham_so.append(user_id)
    if action:
        dieu_kien.append("a.action = %s")
        tham_so.append(action)
    if object_type:
        dieu_kien.append("a.object_type = %s")
        tham_so.append(object_type)
    if object_id is not None:
        dieu_kien.append("a.object_id = %s")
        tham_so.append(object_id)
    where = " and ".join(dieu_kien)

    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"""
            select a.id, a.user_id, u.name as user_name, a.action, a.object_type,
                   a.object_id, a.reason, a.ip_address::text as ip, a.created_at
              from crm.audit_logs a
              left join crm.users u on u.id = a.user_id
             where {where}
             order by a.id desc
             limit %s offset %s
            """,
            (*tham_so, limit, offset),
        ).fetchall()
        total = conn.execute(
            f"select count(*) as n from crm.audit_logs a where {where}",
            tham_so or None,
        ).fetchone()["n"]
    return rows, total


def nhat_ky_cai_dat(limit: int = 60) -> list[dict]:
    """Nhật ký CẤU HÌNH (C8, màn Cài đặt → mục Nhật ký).

    Khác `list_logs`: hàm kia CỐ Ý không kéo `old_value`/`new_value` (bảng danh
    sách 30 dòng mà kéo cả jsonb thì nặng vô ích). Nhật ký cấu hình lại sống
    bằng đúng hai cột đó — người xem cần thấy "đổi từ gì sang gì", không phải
    chỉ biết "có ai đó đã đổi".
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select a.id, a.user_id, u.name as user_name, a.action,
                   a.old_value, a.new_value, a.created_at
              from crm.audit_logs a
              left join crm.users u on u.id = a.user_id
             where (a.object_type = 'app_settings'
                        and a.action in ('setting_update', 'setting_reset'))
                -- T3: ngưỡng hạng thẻ giờ cũng sửa NGAY TRÊN màn Cài đặt, nên
                -- phải hiện ở đây; lọc theo mình bảng app_settings sẽ bỏ sót.
                or a.action = 'sua_nguong_hang_the'
             order by a.id desc limit %s
            """,
            (limit,),
        ).fetchall()


def get_log(audit_id: int) -> dict | None:
    """AUDIT-002: chi tiết 1 dòng, kèm old/new value đầy đủ."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select a.*, a.ip_address::text as ip, u.name as user_name
              from crm.audit_logs a
              left join crm.users u on u.id = a.user_id
             where a.id = %s
            """,
            (audit_id,),
        ).fetchone()
