"""Truy vấn crm.conversations + crm.messages (FR-012 · CONV-001…006).

Chỉ SQL — luật (gắn khách, gán nhân viên, gửi tin) nằm ở
services/conversation_service.py. Nguyên tắc FR-012 "không chỉnh sửa nội dung
gốc" cài ngay ở đây: upsert tin nhắn ON CONFLICT DO NOTHING — tin đã có thì
KHÔNG BAO GIỜ update content, kể cả Pancake trả bản khác.
"""

import json

from app.db.client import get_pg_pool


# ------------------------------------------------------------------ hội thoại

def list_conversations(
    *, customer_id: int | None = None, page_id: int | None = None,
    q: str = "", limit: int = 20, offset: int = 0,
) -> tuple[list[dict], int]:
    """CONV-001 — mới nhất trước; kèm tên khách/page cho màn danh sách."""
    dk, tham_so = ["1=1"], []
    if customer_id:
        dk.append("c.customer_id = %s")
        tham_so.append(customer_id)
    if page_id:
        dk.append("c.page_id = %s")
        tham_so.append(page_id)
    if q.strip():
        dk.append("(k.full_name ilike %s or c.snippet ilike %s)")
        tham_so += [f"%{q.strip()}%"] * 2
    where = " and ".join(dk)
    pool = get_pg_pool()
    with pool.connection() as conn:
        total = conn.execute(
            f"""
            select count(*) as n from crm.conversations c
              left join crm.customers k on k.id = c.customer_id
             where {where}
            """,
            tham_so,
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            select c.id, c.customer_id, c.page_id, c.external_conversation_id,
                   c.status, c.last_message_at, c.snippet, c.message_count,
                   c.unread_count, c.assignee_user_id, c.messages_synced_at,
                   c.external_updated_at, c.source,
                   k.full_name       as customer_name,
                   p.name            as page_name,
                   p.external_page_id,
                   u.name            as assignee_name,
                   (select count(*) from crm.messages m
                     where m.conversation_id = c.id) as stored_messages
              from crm.conversations c
              left join crm.customers k on k.id = c.customer_id
              left join crm.pages     p on p.id = c.page_id
              left join crm.users     u on u.id = c.assignee_user_id
             where {where}
             order by c.last_message_at desc nulls last, c.id desc
             limit %s offset %s
            """,
            [*tham_so, limit, offset],
        ).fetchall()
    return rows, total


def get(conv_id: int) -> dict | None:
    """CONV-002 — một hội thoại kèm khách/page/nhân viên."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select c.*, k.full_name as customer_name, p.name as page_name,
                   p.external_page_id, u.name as assignee_name,
                   (select count(*) from crm.messages m
                     where m.conversation_id = c.id) as stored_messages
              from crm.conversations c
              left join crm.customers k on k.id = c.customer_id
              left join crm.pages     p on p.id = c.page_id
              left join crm.users     u on u.id = c.assignee_user_id
             where c.id = %s
            """,
            (conv_id,),
        ).fetchone()


def attach_customer(conv_id: int, customer_id: int) -> dict | None:
    """CONV-004 — gắn (hoặc gắn LẠI) hội thoại vào khách."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.conversations set customer_id = %s where id = %s "
            "returning *",
            (customer_id, conv_id),
        ).fetchone()


def assign(conv_id: int, user_id: int | None) -> dict | None:
    """CONV-005 — gán nhân viên CRM phụ trách hội thoại (None = bỏ gán)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.conversations set assignee_user_id = %s where id = %s "
            "returning *",
            (user_id, conv_id),
        ).fetchone()


# ------------------------------------------------------------------ tin nhắn

def list_messages(
    conv_id: int, *, limit: int = 50, offset: int = 0,
) -> tuple[list[dict], int]:
    """CONV-003 — CŨ trước MỚI sau (đọc như khung chat), phân trang từ cuối."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        total = conn.execute(
            "select count(*) as n from crm.messages where conversation_id = %s",
            (conv_id,),
        ).fetchone()["n"]
        # Lấy trang từ ĐUÔI (tin mới nhất) rồi lật lại cho đúng chiều đọc.
        rows = conn.execute(
            """
            select * from (
                select m.*, u.name as sender_user_name
                  from crm.messages m
                  left join crm.users u on u.id = m.sender_user_id
                 where m.conversation_id = %s
                 order by m.sent_at desc, m.id desc
                 limit %s offset %s
            ) trang order by sent_at asc, id asc
            """,
            (conv_id, limit, offset),
        ).fetchall()
    return rows, total


def upsert_messages(conv_id: int, msgs: list[dict]) -> int:
    """Ghi mẻ tin nhắn, idempotent theo (conversation_id, external_message_id).

    DO NOTHING chứ không DO UPDATE — luật FR-012: nội dung gốc đã lưu thì
    không sửa. Trả về số dòng THÊM MỚI thật sự.
    """
    if not msgs:
        return 0
    them = 0
    pool = get_pg_pool()
    with pool.connection() as conn:
        for m in msgs:
            row = conn.execute(
                """
                insert into crm.messages
                       (conversation_id, external_message_id, sender_type,
                        sender_user_id, sender_external_id, sender_name,
                        content, msg_type, attachments, sent_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                        coalesce(nullif(%s,'')::timestamptz, now()))
                on conflict (conversation_id, external_message_id)
                    where external_message_id is not null
                    do nothing
                returning id
                """,
                (
                    conv_id,
                    m.get("external_message_id") or None,
                    m.get("sender_type") or "customer",
                    m.get("sender_user_id"),
                    m.get("sender_external_id") or None,
                    m.get("sender_name") or None,
                    m.get("content") or "",
                    m.get("msg_type") or "text",
                    json.dumps(m.get("attachments") or [], ensure_ascii=False),
                    str(m.get("sent_at") or ""),
                ),
            ).fetchone()
            if row:
                them += 1
    return them


def danh_dau_msg_sync(conv_id: int) -> None:
    """Đóng dấu "tin nhắn đã tươi tới thời điểm này" sau một lượt kéo trọn vẹn."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.conversations set messages_synced_at = now() where id = %s",
            (conv_id,),
        )


def hoi_thoai_cho_dong_bo(limit: int = 20) -> list[dict]:
    """Hội thoại có tin mới hơn lần kéo trước — worker nhặt mỗi vòng.

    "Cũ nhất chưa kéo" xếp sau "vừa có tin mới": ưu tiên hội thoại đang nóng
    (external_updated_at mới) để CRM hiển thị kịp; hội thoại tồn chưa kéo lần
    nào (messages_synced_at null) đi cùng đợt, backfill lo phần lịch sử sâu.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select c.id, c.external_conversation_id, c.customer_id,
                   c.external_updated_at, c.messages_synced_at,
                   p.external_page_id, p.name as page_name,
                   ci.external_customer_id
              from crm.conversations c
              join crm.pages p on p.id = c.page_id
              -- lateral + limit 1: khách lỡ có 2 dòng định danh trên cùng page
              -- thì hội thoại vẫn chỉ xuất hiện MỘT lần trong mẻ
              left join lateral (
                    select external_customer_id from crm.customer_identities x
                     where x.customer_id = c.customer_id and x.page_id = c.page_id
                       and x.external_customer_id is not null
                     limit 1
              ) ci on true
             where c.external_conversation_id is not null
               and p.external_page_id <> ''
               and (c.messages_synced_at is null
                    or c.external_updated_at > c.messages_synced_at)
             order by c.external_updated_at desc nulls last
             limit %s
            """,
            (limit,),
        ).fetchall()


def doi_chieu_pancake(external_conversation_id: str) -> dict | None:
    """Một hội thoại Pancake đã đổ vào CRM thành những gì — màn Thử API.

    Trả đúng 5 thứ crm_sync sinh ra (khách · hội thoại · thẻ · nhân viên xử lý ·
    tin nhắn) để đối chiếu tận mắt với JSON gốc Pancake vừa gọi ở trên.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select c.id                      as conversation_id,
                   c.external_conversation_id,
                   c.snippet, c.message_count, c.unread_count,
                   c.last_message_at, c.external_updated_at, c.messages_synced_at,
                   c.source,
                   p.external_page_id, p.name as page_name, p.sync_enabled,
                   k.id                      as customer_id,
                   k.full_name               as khach,
                   k.primary_phone           as sdt,
                   k.status                  as trang_thai_khach,
                   k.created_at              as khach_tao_luc,
                   c.assignee_external_id,
                   u.name                    as nhan_vien_xu_ly,
                   (select count(*) from crm.messages m
                     where m.conversation_id = c.id)            as so_tin_da_luu,
                   (select coalesce(json_agg(t.name order by t.name), '[]'::json)
                      from crm.customer_tags ct
                      join crm.tags t on t.id = ct.tag_id
                     where ct.customer_id = k.id)               as the
              from crm.conversations c
              join crm.pages p on p.id = c.page_id
              left join crm.customers k on k.id = c.customer_id
              left join crm.users u on u.id = c.assignee_user_id
             where c.external_conversation_id = %s
             limit 1
            """,
            (str(external_conversation_id),),
        ).fetchone()


def dem_ton_dong() -> dict:
    """Đếm hội thoại chưa kéo tin / đã tươi — cho màn Tích hợp + backfill."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return dict(conn.execute(
            """
            select count(*)                                            as tong,
                   count(*) filter (where messages_synced_at is null)  as chua_keo,
                   count(*) filter (where external_updated_at > messages_synced_at)
                                                                       as co_tin_moi
              from crm.conversations
             where external_conversation_id is not null
            """
        ).fetchone())
