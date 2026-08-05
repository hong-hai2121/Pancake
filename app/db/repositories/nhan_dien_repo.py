"""Truy vấn Đợt 2 — mẫu câu nhận diện (`crm.phrase_patterns`).

Chỉ SQL. Luật dò nằm ở `services/nhan_dien.py`.
"""

from app.core.errors import ApiError
from app.db.client import get_pg_pool

LOAI = ("goi", "chan", "voucher", "viet_tat")


def tat_ca(chi_active: bool = False) -> list[dict]:
    """Mọi mẫu, kể cả đang TẮT — màn cấu hình phải thấy hết để bật lại được."""
    dk = " where status = 'active'" if chi_active else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select * from crm.phrase_patterns{dk} order by kind, id"
        ).fetchall()


def them(kind: str, pattern: str, replacement: str | None = None,
         nguoi: int | None = None) -> dict:
    """Thêm một mẫu. Trùng (loại + mẫu) thì báo rõ chứ không nuốt im lặng:
    người dùng gõ lại một cụm đã có là họ tưởng nó chưa có."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        dong = conn.execute(
            """
            insert into crm.phrase_patterns (kind, pattern, replacement,
                                             created_by)
            values (%s, %s, %s, %s)
            on conflict do nothing returning *
            """,
            (kind, pattern, replacement, nguoi),
        ).fetchone()
    if dong is None:
        raise ApiError("VALIDATION_ERROR",
                       f"Mẫu «{pattern}» đã có trong danh sách này rồi.")
    return dong


def doi_trang_thai(pattern_id: int) -> dict | None:
    """Bật ↔ tắt. Tắt chứ KHÔNG xoá là cách thử "bỏ mẫu này đi thì sao" mà
    không mất luôn cụm chữ đã nghĩ ra."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.phrase_patterns set status = "
            "case when status = 'active' then 'inactive' else 'active' end "
            "where id = %s returning *", (pattern_id,),
        ).fetchone()


def xoa(pattern_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("delete from crm.phrase_patterns where id = %s",
                     (pattern_id,))
