"""Truy vấn C3 — chiến dịch 2 tầng + mẫu tin (port mẫu Kallet chien-dich.php ·
mau-tin.php).

Dùng LẠI `reactivation_campaigns` / `reactivation_members` của B10 (đã nới cột
ở init_crm.sql) chứ không đẻ bảng campaign thứ hai.
"""

import json

from app.core.ngay import hom_nay
from app.db.client import get_pg_pool


# ------------------------------------------------------------------ chiến dịch
def danh_sach(*, trang_thai: str = "") -> list[dict]:
    """Chiến dịch + số liệu 2 tầng đếm thẳng từ thành viên."""
    dk = "where cp.status = %s" if trang_thai else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select cp.*, u.name as created_by_name,
                   count(m.id)                                        as so_khach,
                   count(m.id) filter (where m.sent_at is not null)    as da_gui,
                   count(m.id) filter (where m.responded_at is not null) as da_tra_loi,
                   count(m.id) filter (where m.status = 'converted')   as ra_don,
                   count(m.id) filter (where m.status in
                        ('refused','unreachable'))                     as het_han,
                   coalesce(sum(dt.tien), 0)                           as doanh_thu
              from crm.reactivation_campaigns cp
              left join crm.users u on u.id = cp.created_by
              left join crm.reactivation_members m on m.campaign_id = cp.id
              left join lateral (
                    select sum(o.total_amount) as tien
                      from crm.orders o
                     where o.customer_id = m.customer_id
                       and o.status in ('delivered','collected')
                       and o.created_at >= m.created_at
              ) dt on true
              {dk}
             group by cp.id, u.name
             order by cp.id desc
            """,
            (trang_thai,) if trang_thai else None,
        ).fetchall()


def get(campaign_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select cp.*, u.name as created_by_name "
            "from crm.reactivation_campaigns cp "
            "left join crm.users u on u.id = cp.created_by where cp.id = %s",
            (campaign_id,),
        ).fetchone()


def tao(**f) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.reactivation_campaigns
                   (name, description, segment_rule_json, tier1_channel,
                    tier1_flow_id, template_id, batch_size,
                    batch_interval_days, deadline, created_by, status, start_at)
            values (%(name)s, %(description)s, %(rule)s, %(channel)s,
                    %(flow_id)s, %(template_id)s, %(batch_size)s,
                    %(batch_interval_days)s, %(deadline)s, %(created_by)s,
                    'draft', now())
            returning *
            """,
            {**f, "rule": json.dumps(f.get("rule") or {}, ensure_ascii=False)},
        ).fetchone()


def doi_trang_thai(campaign_id: int, trang_thai: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.reactivation_campaigns set status = %s, "
            "end_at = case when %s = 'finished' then now() else end_at end "
            "where id = %s returning *",
            (trang_thai, trang_thai, campaign_id),
        ).fetchone()


def nha_khach(campaign_id: int) -> int:
    """Đóng chiến dịch thì NHẢ khách chưa chốt.

    Không có bước này thì khách kẹt trạng thái 'đang chăm' VĨNH VIỄN và luật
    J5 (1 khách 1 chiến dịch) chặn họ khỏi mọi chiến dịch về sau."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            "update crm.reactivation_members set status = 'unreachable' "
            "where campaign_id = %s and status in ('pending','contacted')",
            (campaign_id,),
        )
        return cur.rowcount or 0


# ------------------------------------------------------------------ tệp khách
def _loc_sql(loc: dict) -> tuple[str, dict]:
    """WHERE chọn tệp khách — dùng CHUNG cho ĐẾM XEM TRƯỚC và INSERT nạp thật,
    để "thấy bao nhiêu thì nạp đúng bấy nhiêu"."""
    ngu_tu = int(loc.get("ngu_tu") or 0)
    ngu_den = loc.get("ngu_den")
    dk = ["c.deleted_at is null", "c.status <> 'merged'",
          "not c.do_not_contact", "c.last_delivered_at is not null",
          # Mốc ngày tính ở Python (giờ VN) — current_date của DB chạy UTC nên
          # chạy trước 07:00 sẽ lệch 1 ngày, ranh giới 151/181/210 chọn sai tệp.
          "c.last_delivered_at <= %(moc_tu)s"]
    ts = {"moc_tu": None, "moc_den": None}
    ts["moc_tu"] = _lui(ngu_tu)
    if ngu_den:
        dk.append("c.last_delivered_at >= %(moc_den)s")
        ts["moc_den"] = _lui(int(ngu_den))
    if loc.get("hang"):
        if loc["hang"] == "chua_xep":
            dk.append("c.card_rank is null")
        else:
            dk.append("c.card_rank = %(hang)s")
            ts["hang"] = loc["hang"]
    if loc.get("so_mua") == "1":
        dk.append("(select count(*) from crm.orders o where o.customer_id = c.id "
                  "and o.status in ('delivered','collected')) = 1")
    elif loc.get("so_mua") == "2p":
        dk.append("(select count(*) from crm.orders o where o.customer_id = c.id "
                  "and o.status in ('delivered','collected')) >= 2")
    # J5 — 1 khách không nằm 2 chiến dịch CÙNG LÚC
    dk.append("not exists (select 1 from crm.reactivation_members m "
              " where m.customer_id = c.id "
              "   and m.status in ('pending','contacted','responded'))")
    return " and ".join(dk), ts


def _lui(ngay: int):
    from datetime import timedelta

    return hom_nay() - timedelta(days=ngay)


def dem_xem_truoc(loc: dict) -> int:
    where, ts = _loc_sql(loc)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select count(*) as n from crm.customers c where {where}", ts
        ).fetchone()["n"]


def nap_khach(campaign_id: int, loc: dict, *, gan_cho: int | None = None,
              gioi_han: int = 20000) -> int:
    """Nạp tệp khách vào chiến dịch theo đúng bộ lọc vừa xem trước."""
    where, ts = _loc_sql(loc)
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            f"""
            insert into crm.reactivation_members
                   (campaign_id, customer_id, assigned_to, status)
            select %(cd)s, c.id, %(nv)s, 'pending'
              from crm.customers c where {where}
             limit %(lim)s
            on conflict do nothing
            """,
            {**ts, "cd": campaign_id, "nv": gan_cho, "lim": gioi_han},
        )
        return cur.rowcount or 0


def khach_chua_gui(campaign_id: int, so_luong: int) -> list[dict]:
    """Một đợt: khách trong chiến dịch chưa được gửi tin tầng 1."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select m.id as member_id, m.customer_id, c.full_name,
                   c.primary_phone,
                   cv.id as conversation_id,
                   cv.external_conversation_id, p.external_page_id
              from crm.reactivation_members m
              join crm.customers c on c.id = m.customer_id
              left join lateral (
                    select cv.id, cv.external_conversation_id, cv.page_id
                      from crm.conversations cv
                     where cv.customer_id = c.id
                     order by cv.last_message_at desc nulls last limit 1
              ) cv on true
              left join crm.pages p on p.id = cv.page_id
             where m.campaign_id = %s and m.sent_at is null
               and m.status = 'pending'
             order by m.id limit %s
            """,
            (campaign_id, so_luong),
        ).fetchall()


def danh_dau_da_gui(member_id: int, ket_qua: str) -> None:
    """CHỈ gọi khi GỬI THẬT — chế độ nháp không được 'tiêu' khách."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.reactivation_members set sent_at = now(), "
            "send_result = %s, status = 'contacted' where id = %s",
            (ket_qua, member_id),
        )


def ghi_nhip_dot(campaign_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("update crm.reactivation_campaigns set last_batch_at = "
                     "now() where id = %s", (campaign_id,))


def thanh_vien_dang_cham(customer_id: int) -> dict | None:
    """Khách này đang nằm trong chiến dịch nào (đang chăm)?"""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select m.*, cp.name as campaign_name, cp.status as campaign_status
              from crm.reactivation_members m
              join crm.reactivation_campaigns cp on cp.id = m.campaign_id
             where m.customer_id = %s
               and m.status in ('pending','contacted','responded')
             order by m.id desc limit 1
            """,
            (customer_id,),
        ).fetchone()


def danh_dau_tra_loi(member_id: int, task_id: int | None) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.reactivation_members set status = 'responded', "
            "responded_at = now(), task_id = coalesce(%s, task_id) "
            "where id = %s and responded_at is null returning *",
            (task_id, member_id),
        ).fetchone()


def thanh_vien(campaign_id: int, *, tang: str = "", limit: int = 200) -> list[dict]:
    """Thành viên của chiến dịch. `tang` = '1' (chưa trả lời) | '2' (đã trả lời)."""
    dk = {"1": "and m.responded_at is null",
          "2": "and m.responded_at is not null"}.get(tang, "")
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select m.*, c.full_name, c.primary_phone, c.card_rank,
                   u.name as assigned_name, t.title as task_title,
                   t.status as task_status
              from crm.reactivation_members m
              join crm.customers c on c.id = m.customer_id
              left join crm.users u on u.id = m.assigned_to
              left join crm.tasks t on t.id = m.task_id
              -- tasks.title thêm sau (alter ở init_crm.sql) nên luôn có cột
             where m.campaign_id = %s {dk}
             order by m.responded_at desc nulls last, m.id
             limit %s
            """,
            (campaign_id, limit),
        ).fetchall()


# ------------------------------------------------------------------ mẫu tin
def mau_tin(*, kind: str = "", trang_thai: str = "active") -> list[dict]:
    dk, ts = ["true"], {}
    if kind:
        dk.append("kind = %(k)s")
        ts["k"] = kind
    if trang_thai:
        dk.append("status = %(tt)s")
        ts["tt"] = trang_thai
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select * from crm.message_templates where {' and '.join(dk)} "
            "order by kind, code", ts or None,
        ).fetchall()


def get_mau(template_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.message_templates where id = %s", (template_id,)
        ).fetchone()


def get_mau_theo_ma(code: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.message_templates where code = %s", (code,)
        ).fetchone()


def luu_mau(**f) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.message_templates
                   (code, name, kind, meta_status, variables, body, created_by)
            values (%(code)s, %(name)s, %(kind)s, %(meta_status)s,
                    %(variables)s, %(body)s, %(created_by)s)
            on conflict (code) do update set
                name = excluded.name, kind = excluded.kind,
                meta_status = excluded.meta_status,
                variables = excluded.variables, body = excluded.body
            returning *
            """,
            f,
        ).fetchone()


def doi_trang_thai_mau(template_id: int, trang_thai: str) -> dict | None:
    """Mẫu cũ NGỪNG DÙNG chứ không xoá — tin đã gửi vẫn phải tra ngược được."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.message_templates set status = %s where id = %s "
            "returning *", (trang_thai, template_id),
        ).fetchone()


def cong_da_gui(template_id: int, so: int = 1) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("update crm.message_templates set sent_count = "
                     "sent_count + %s where id = %s", (so, template_id))
