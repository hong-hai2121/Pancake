"""Truy vấn C5 — thang bám đuổi Sale + bảng việc (port mẫu Kallet
includes/sale_buoc.php · includes/board_rules.php).

Chỉ SQL. Luật (con trỏ chỉ tiến · nhảy cóc · trần bước/ngày · cửa giờ) nằm ở
services/sale_service.py.
"""

from app.core.ngay import hom_nay
from app.db.client import get_pg_pool


# ------------------------------------------------------------------ thang bước
def thang() -> list[dict]:
    """Các bước ĐANG DÙNG, theo thứ tự. Thang rỗng = mọi luật thang tự tắt."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.sale_steps where status = 'active' "
            "order by step_no"
        ).fetchall()


def luu_buoc(step_no: int, **f) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.sale_steps
                   (step_no, name, work, keywords_agent, keywords_customer)
            values (%(step_no)s, %(name)s, %(work)s, %(kw_nv)s, %(kw_kh)s)
            on conflict (step_no) do update set
                name = excluded.name, work = excluded.work,
                keywords_agent = excluded.keywords_agent,
                keywords_customer = excluded.keywords_customer
            returning *
            """,
            {"step_no": step_no, **f},
        ).fetchone()


# ------------------------------------------------------------------ tin nhắn
def tin_cua_lead(customer_id: int, tu_ngay, gioi_han: int = 500) -> list[dict]:
    """Tin hai chiều của khách kể từ NGÀY BẬT THANG, theo đúng thứ tự thời gian.

    Lấy `gioi_han` tin CUỐI rồi lật lại (không phải tin ĐẦU): hội thoại dài
    vượt trần thì các tin MỚI NHẤT mới là thứ cần đọc — bản cũ của mẫu lấy tin
    đầu nên con trỏ đóng băng vĩnh viễn với khách nhắn nhiều.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select huong, nguoi_that, noi_dung, co_anh, sent_at,
                   sender_user_id from (
                select case when m.sender_type = 'customer' then 'khach'
                            else 'shop' end                     as huong,
                       -- Tin MÁY (bot/không rõ người) vẫn được tính bước, nhưng
                       -- CHỈ khi dò ra đúng từ khoá — xem sale_service.do_buoc.
                       (m.sender_type = 'agent'
                        and m.sender_user_id is not null)        as nguoi_that,
                       m.content                                as noi_dung,
                       (coalesce(m.msg_type, '') = 'image'
                        or m.attachments is not null)            as co_anh,
                       m.sent_at, m.sender_user_id, m.id
                  from crm.messages m
                  join crm.conversations cv on cv.id = m.conversation_id
                 where cv.customer_id = %(kh)s and m.sent_at >= %(tu)s
                   and m.sender_type in ('customer', 'agent', 'bot')
                 order by m.sent_at desc, m.id desc
                 limit %(lim)s
            ) t order by t.sent_at, t.id
            """,
            {"kh": customer_id, "tu": tu_ngay, "lim": gioi_han},
        ).fetchall()


def moc_tin(customer_id: int) -> dict | None:
    """Ba mốc quyết định "ai nhắn cuối": tin khách cuối · tin shop cuối · tin
    của NGƯỜI THẬT cuối (loại tin bot/máy — chúng không tính là đã tư vấn)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select max(m.sent_at) filter (where m.sender_type = 'customer')
                       as khach_cuoi,
                   max(m.sent_at) filter (where m.sender_type = 'agent')
                       as shop_cuoi,
                   max(m.sent_at) filter (where m.sender_type = 'agent'
                                            and m.sender_user_id is not null)
                       as nguoi_cuoi
              from crm.messages m
              join crm.conversations cv on cv.id = m.conversation_id
             where cv.customer_id = %s
            """,
            (customer_id,),
        ).fetchone()


# ------------------------------------------------------------------ con trỏ
def dat_con_tro(lead_id: int, buoc: int, luc, *, cong_dem: bool = True) -> dict | None:
    """Đẩy con trỏ. CHỈ TIẾN (điều kiện `sale_step < %s` ở WHERE).

    `cong_dem` — có tính vào trần bước/ngày không. Nhảy cóc do khách nói thì
    KHÔNG tính (khách nói toạc ra rồi, không phải nhân viên bắn tin cho xong)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            update crm.leads set
                   sale_step = %(buoc)s,
                   sale_step_at = %(luc)s,
                   sale_step_day = case when %(dem)s then %(ngay)s
                                        else sale_step_day end,
                   sale_step_count = case
                       when not %(dem)s then sale_step_count
                       when sale_step_day = %(ngay)s then sale_step_count + 1
                       else 1 end
             where id = %(id)s and sale_step < %(buoc)s
            returning *
            """,
            {"id": lead_id, "buoc": buoc, "luc": luc, "dem": cong_dem,
             "ngay": hom_nay()},
        ).fetchone()


def dat_lai_con_tro(lead_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.leads set sale_step = 0, sale_step_at = null, "
            "sale_step_day = null, sale_step_count = 0 where id = %s",
            (lead_id,))


def dat_con_tro_tay(lead_id: int, buoc: int) -> dict | None:
    """Nhân viên kéo thẻ sang cột "Bước N" ⇒ con trỏ = N-1 (đã làm tới N-1,
    việc kế đúng là N). Đây là đường DUY NHẤT cho phép con trỏ LÙI."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.leads set sale_step = %s, sale_step_at = now() "
            "where id = %s returning *", (max(0, buoc), lead_id),
        ).fetchone()


def danh_dau_tra_loi(lead_id: int, luc) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.leads set replied_at = greatest(coalesce(replied_at, "
            "%s), %s) where id = %s", (luc, luc, lead_id))


# ------------------------------------------------------------------ cột đặt tay
def dat_cot(lead_id: int, cot: str | None, nguoi: int | None) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        # Ép kiểu ::text cho tham số cột: nhả cột thì truyền NULL, mà NULL trần
        # trong `case when ... is null` làm Postgres không đoán được kiểu.
        return conn.execute(
            "update crm.leads set board_column = %(cot)s::text, "
            "board_column_at = case when %(cot)s::text is null then null "
            "                       else now() end, "
            "board_column_by = %(nv)s where id = %(id)s returning *",
            {"cot": cot, "nv": nguoi, "id": lead_id},
        ).fetchone()


def nha_cot_da_cu() -> int:
    """Cột đặt tay TỰ NHẢ khi khách nhắn mới SAU lúc đặt.

    Không có bước này thì "Từ chối đợt này" kẹt vĩnh viễn — khách quay lại nhắn
    mà thẻ vẫn nằm im trong cột Từ chối, không ai thấy."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            """
            update crm.leads l set board_column = null, board_column_at = null
             where l.board_column is not null
               and l.board_column <> 'ngung'
               and exists (
                   select 1 from crm.messages m
                     join crm.conversations cv on cv.id = m.conversation_id
                    where cv.customer_id = l.customer_id
                      and m.sender_type = 'customer'
                      and m.sent_at > l.board_column_at)
            """
        )
        return cur.rowcount or 0


# ------------------------------------------------------------------ bảng việc
_CHON_BANG = """
    l.id, l.customer_id, l.owner_id, l.sale_step, l.sale_step_at,
    l.sale_step_day, l.sale_step_count, l.replied_at, l.board_column,
    l.board_column_at, l.next_action_at, l.temperature, l.closed_at,
    l.created_at, l.stage_id,
    c.full_name, c.primary_phone, c.card_rank, c.do_not_contact,
    u.name as owner_name,
    s.code as stage_code, s.name as stage_name,
    ht.khach_cuoi, ht.shop_cuoi, ht.nguoi_cuoi,
    p.external_page_id, cv.external_conversation_id,
    (select count(*) from crm.care_interactions ci
      where ci.customer_id = l.customer_id
        and ci.verify_status <> 'bac_bo'
        and (ci.action_at at time zone 'Asia/Ho_Chi_Minh')::date
            = (now() at time zone 'Asia/Ho_Chi_Minh')::date) as cham_hom_nay
"""

_TU_BANG = """
    from crm.leads l
    join crm.customers c on c.id = l.customer_id
    left join crm.users u on u.id = l.owner_id
    left join crm.pipeline_stages s on s.id = l.stage_id
    left join lateral (
        select max(m.sent_at) filter (where m.sender_type = 'customer')
                   as khach_cuoi,
               max(m.sent_at) filter (where m.sender_type = 'agent')
                   as shop_cuoi,
               max(m.sent_at) filter (where m.sender_type = 'agent'
                                        and m.sender_user_id is not null)
                   as nguoi_cuoi
          from crm.messages m
          join crm.conversations c2 on c2.id = m.conversation_id
         where c2.customer_id = l.customer_id
    ) ht on true
    left join lateral (
        select cv.external_conversation_id, cv.page_id
          from crm.conversations cv where cv.customer_id = l.customer_id
         order by cv.last_message_at desc nulls last limit 1
    ) cv on true
    left join crm.pages p on p.id = cv.page_id
"""


def bang_viec(*, owner_id: int | None = None, q: str = "",
              limit: int = 500) -> list[dict]:
    """Lead ĐANG MỞ của Sale — service tự xếp vào cột."""
    dk, ts = ["l.closed_at is null", "c.deleted_at is null"], {"lim": limit}
    if owner_id:
        dk.append("l.owner_id = %(nv)s")
        ts["nv"] = owner_id
    if q.strip():
        dk.append("(c.full_name ilike %(q)s or c.primary_phone like %(q)s)")
        ts["q"] = f"%{q.strip()}%"
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON_BANG} {_TU_BANG} where {' and '.join(dk)} "
            "order by l.next_action_at nulls last, l.id desc limit %(lim)s",
            ts,
        ).fetchall()


def get_lead_bang(lead_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON_BANG} {_TU_BANG} where l.id = %s", (lead_id,)
        ).fetchone()


def lead_can_do(*, gioi_han: int = 300) -> list[dict]:
    """Lead cần chạy lại bộ dò con trỏ: đang mở và CÓ TIN MỚI sau lần dò cuối."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select l.id, l.customer_id, l.sale_step, l.sale_step_at
              from crm.leads l
             where l.closed_at is null
               and exists (
                   select 1 from crm.messages m
                     join crm.conversations cv on cv.id = m.conversation_id
                    where cv.customer_id = l.customer_id
                      and m.sent_at > coalesce(l.sale_step_at,
                                               to_timestamp(0)))
             order by l.id limit %s
            """,
            (gioi_han,),
        ).fetchall()


def dong_lead(lead_id: int, ly_do: str | None = None) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.leads set closed_at = now() where id = %s returning *",
            (lead_id,),
        ).fetchone()
