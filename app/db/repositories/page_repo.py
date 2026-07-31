"""Truy vấn crm.pages (B2 — fanpage/kênh chat nối vào CRM)."""

from app.db.client import get_pg_pool


def find_or_create(*, platform: str, external_page_id: str, name: str) -> dict:
    """Unique (platform, external_page_id) — có rồi thì trả lại, tiện cập nhật tên."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.pages (platform, external_page_id, name)
            values (%s, %s, %s)
            on conflict (platform, external_page_id) do update set name = excluded.name
            returning *
            """,
            (platform, external_page_id, name),
        ).fetchone()
