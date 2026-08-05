"""Truy vấn C4 — thư viện kịch bản · kho data · giám sát (soi tin).

Port từ mẫu Kallet: kich-ban.php · kho-data.php · lich-su.php ·
includes/xac_minh.php.
"""

import json

from app.core.ngay import hom_nay
from app.db.client import get_pg_pool


# ============================================================ THƯ VIỆN KỊCH BẢN
def kich_ban(*, kind: str = "", tu_khoa: str = "", tinh_huong: str = "",
             trang_thai: str = "active", limit: int = 100,
             offset: int = 0) -> tuple[list[dict], int]:
    """Tìm trong thư viện. Tìm trên cột BỎ DẤU nên gõ "dau da day" vẫn ra
    "đau dạ dày" — xem services/tieng_viet.py."""
    dk, ts = ["true"], {}
    if kind:
        dk.append("s.kind = %(k)s")
        ts["k"] = kind
    if trang_thai:
        dk.append("s.status = %(tt)s")
        ts["tt"] = trang_thai
    if tinh_huong:
        dk.append("s.situation = %(th)s")
        ts["th"] = tinh_huong
    if tu_khoa:
        from app.services.tieng_viet import chuan_hoa

        dk.append("(s.body_nodiacritic ilike %(kw)s or s.title ilike %(kw2)s "
                  "or s.tags ilike %(kw2)s)")
        ts["kw"] = f"%{chuan_hoa(tu_khoa)}%"
        ts["kw2"] = f"%{tu_khoa}%"
    where = " and ".join(dk)
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"select s.* from crm.sale_scripts s where {where} "
            "order by s.use_count desc, s.sort_order, s.id "
            "limit %(l)s offset %(o)s",
            {**ts, "l": limit, "o": offset},
        ).fetchall()
        tong = conn.execute(
            f"select count(*) as n from crm.sale_scripts s where {where}", ts
        ).fetchone()["n"]
    return rows, tong


def get_kich_ban(script_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute("select * from crm.sale_scripts where id = %s",
                            (script_id,)).fetchone()


def luu_kich_ban(**f) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        if f.get("id"):
            return conn.execute(
                """
                update crm.sale_scripts set kind = %(kind)s,
                       situation = %(situation)s, milestone = %(milestone)s,
                       channel = %(channel)s, title = %(title)s, body = %(body)s,
                       body_nodiacritic = %(body_nodiacritic)s, tags = %(tags)s
                 where id = %(id)s returning *
                """, f,
            ).fetchone()
        return conn.execute(
            """
            insert into crm.sale_scripts
                   (kind, situation, milestone, channel, title, body,
                    body_nodiacritic, tags, created_by)
            values (%(kind)s, %(situation)s, %(milestone)s, %(channel)s,
                    %(title)s, %(body)s, %(body_nodiacritic)s, %(tags)s,
                    %(created_by)s)
            returning *
            """, f,
        ).fetchone()


def doi_trang_thai_kich_ban(script_id: int, trang_thai: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.sale_scripts set status = %s where id = %s returning *",
            (trang_thai, script_id),
        ).fetchone()


def cong_luot_dung(script_id: int) -> None:
    """Đếm lượt CHÉP — nền cho báo cáo "kịch bản chết"."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("update crm.sale_scripts set use_count = use_count + 1 "
                     "where id = %s", (script_id,))


def tinh_huong_co() -> list[str]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select distinct situation from crm.sale_scripts "
            "where situation <> '' order by situation"
        ).fetchall()
    return [r["situation"] for r in rows]


def luat_goi_y() -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select r.*, s.title, s.body, s.kind
              from crm.script_suggest_rules r
              left join crm.sale_scripts s on s.id = r.script_id
             where r.status = 'active' and s.status = 'active'
             order by r.id
            """
        ).fetchall()


def luat_goi_y_tat_ca() -> list[dict]:
    """CẢ luật đang tắt + luật trỏ vào kịch bản đã ẩn — màn cấu hình phải thấy
    hết để bật lại/sửa được. (Khác `luat_goi_y()` chỉ trả phần đang chạy.)"""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select r.*, s.title, s.status as script_status
              from crm.script_suggest_rules r
              left join crm.sale_scripts s on s.id = r.script_id
             order by r.id desc
            """
        ).fetchall()


def kich_ban_chon(limit: int = 800) -> list[dict]:
    """Kịch bản đang dùng, cho ô <select> của màn Gợi ý."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select id, title from crm.sale_scripts where status = 'active' "
            "order by title limit %s", (limit,),
        ).fetchall()


def doi_trang_thai_luat_goi_y(rule_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.script_suggest_rules set status = "
            "case when status = 'active' then 'inactive' else 'active' end "
            "where id = %s returning *", (rule_id,),
        ).fetchone()


def luu_luat_goi_y(keywords: str, script_id: int) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.script_suggest_rules (keywords, script_id) "
            "values (%s, %s) returning *", (keywords, script_id),
        ).fetchone()


def xoa_luat_goi_y(rule_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("delete from crm.script_suggest_rules where id = %s",
                     (rule_id,))


# ==================================================================== KHO DATA
def khach_chua_chia(limit: int = 200) -> list[dict]:
    """Khách CHƯA có người phụ trách.

    Mẫu chốt: nhóm này KHÔNG lên bảng việc và KHÔNG chạy đồng hồ SLA — chưa
    giao cho ai thì không thể tính là ai đó chậm."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select c.id, c.full_name, c.primary_phone, c.source, c.created_at,
                   c.card_rank,
                   (select count(*) from crm.orders o
                     where o.customer_id = c.id) as so_don
              from crm.customers c
             where c.deleted_at is null and c.status <> 'merged'
               and not exists (select 1 from crm.customer_assignments a
                                where a.customer_id = c.id and a.end_at is null)
             order by c.created_at desc limit %s
            """,
            (limit,),
        ).fetchall()


def khach_ket(limit: int = 100) -> list[dict]:
    """"Khách kẹt không chia được" — chưa ai phụ trách VÀ mọi nhân viên đều
    đang bị khoá thu hồi với khách này. Không có màn này thì họ nằm im mãi mà
    không ai biết."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select c.id, c.full_name, c.primary_phone, c.created_at,
                   count(b.id) as so_khoa,
                   max(b.block_until) as khoa_den
              from crm.customers c
              join crm.recall_blocks b on b.customer_id = c.id
                                      and b.block_until >= %s
             where c.deleted_at is null and c.status <> 'merged'
               and not exists (select 1 from crm.customer_assignments a
                                where a.customer_id = c.id and a.end_at is null)
             group by c.id
             order by so_khoa desc, c.created_at limit %s
            """,
            (hom_nay(), limit),
        ).fetchall()


def ghi_chia(customer_id: int, *, tu: int | None, den: int | None,
             hanh_dong: str, ly_do: str = "", may: bool = False,
             boi: int | None = None) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.assignment_logs (customer_id, from_user_id, "
            "to_user_id, action, reason, by_machine, by_user) "
            "values (%s, %s, %s, %s, %s, %s, %s) returning *",
            (customer_id, tu, den, hanh_dong, ly_do, may, boi),
        ).fetchone()


def nhat_ky_chia(*, customer_id: int | None = None,
                 limit: int = 200) -> list[dict]:
    dk = "where l.customer_id = %(kh)s" if customer_id else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select l.*, c.full_name as customer_name,
                   ut.name as from_name, ud.name as to_name,
                   ub.name as by_name
              from crm.assignment_logs l
              join crm.customers c on c.id = l.customer_id
              left join crm.users ut on ut.id = l.from_user_id
              left join crm.users ud on ud.id = l.to_user_id
              left join crm.users ub on ub.id = l.by_user
              {dk}
             order by l.id desc limit %(l)s
            """,
            {"kh": customer_id, "l": limit},
        ).fetchall()


def khoa_thu_hoi(customer_id: int, user_id: int, den_ngay, ly_do: str = "") -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.recall_blocks (customer_id, user_id, block_until, "
            "reason) values (%s, %s, %s, %s) returning *",
            (customer_id, user_id, den_ngay, ly_do),
        ).fetchone()


def dang_bi_khoa(customer_id: int, user_id: int) -> bool:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select exists (select 1 from crm.recall_blocks where customer_id = "
            "%s and user_id = %s and block_until >= %s) as co",
            (customer_id, user_id, hom_nay()),
        ).fetchone()["co"]


def ghi_xuat(user_id: int | None, scope: str, so_dong: int,
             loc: dict | None = None) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.export_logs (user_id, scope, row_count, filters) "
            "values (%s, %s, %s, %s) returning *",
            (user_id, scope, so_dong,
             json.dumps(loc or {}, ensure_ascii=False)),
        ).fetchone()


def nhat_ky_xuat(limit: int = 100) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select e.*, u.name as user_name from crm.export_logs e "
            "left join crm.users u on u.id = e.user_id "
            "order by e.id desc limit %s", (limit,),
        ).fetchall()


def ghi_gop(primary_id: int, merged_id: int, snapshot: dict,
            boi: int | None) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.merge_logs (primary_customer_id, "
            "merged_customer_id, snapshot, by_user) values (%s, %s, %s, %s) "
            "returning *",
            (primary_id, merged_id, json.dumps(snapshot, ensure_ascii=False,
                                               default=str), boi),
        ).fetchone()


def nhat_ky_gop(limit: int = 100) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select m.*, cp.full_name as primary_name,
                   cm.full_name as merged_name, u.name as by_name
              from crm.merge_logs m
              join crm.customers cp on cp.id = m.primary_customer_id
              join crm.customers cm on cm.id = m.merged_customer_id
              left join crm.users u on u.id = m.by_user
             order by m.id desc limit %s
            """,
            (limit,),
        ).fetchall()


def danh_dau_tach_lai(merge_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.merge_logs set undone = true where id = %s and not "
            "undone returning *", (merge_id,),
        ).fetchone()


def bo_qua_trung(phone: str, ly_do: str, boi: int | None) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.merge_ignored (phone, reason, by_user) "
            "values (%s, %s, %s) on conflict (phone) do nothing returning *",
            (phone, ly_do, boi),
        ).fetchone()


def phone_bo_qua() -> set[str]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute("select phone from crm.merge_ignored").fetchall()
    return {r["phone"] for r in rows}


# ================================================================= SOI TIN
def cong_hom_nay(customer_id: int, user_id: int, action_kind: str,
                 ngay) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select * from crm.care_interactions
             where customer_id = %s and user_id = %s and action_kind = %s
               and (action_at at time zone 'Asia/Ho_Chi_Minh')::date = %s
             limit 1
            """,
            (customer_id, user_id, action_kind, ngay),
        ).fetchone()


def ghi_cong(*, customer_id: int, user_id: int, action_kind: str,
             channel: str, verify_source: str, verify_status: str,
             action_at, verify_reason: str = "",
             summary: str = "") -> dict | None:
    """Ghi 1 công. Trùng (đã có công cùng ngày) thì DB tự chặn bằng unique
    index — trả None chứ không ném lỗi lên tận giao diện."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.care_interactions
                   (customer_id, user_id, action_kind, channel, contacted,
                    summary, action_at, verify_source, verify_status,
                    verified_at, verify_reason)
            values (%(kh)s, %(nv)s, %(hd)s, %(kenh)s, true, %(tt)s, %(luc)s,
                    %(nguon)s, %(tt_xm)s,
                    case when %(tt_xm)s = 'da_xac_minh' then now() end,
                    %(ly_do)s)
            on conflict do nothing
            returning *
            """,
            {"kh": customer_id, "nv": user_id, "hd": action_kind,
             "kenh": channel, "tt": summary, "luc": action_at,
             "nguon": verify_source, "tt_xm": verify_status,
             "ly_do": verify_reason},
        ).fetchone()


def nang_cong(cong_id: int, ly_do: str) -> dict | None:
    """Bằng chứng đến SAU: nâng bản tự khai/bị bác cùng ngày lên đã xác minh."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.care_interactions set verify_status = 'da_xac_minh', "
            "verified_at = now(), verify_reason = %s "
            "where id = %s and verify_status <> 'da_xac_minh' returning *",
            (ly_do, cong_id),
        ).fetchone()


def cong_cho_soi(limit: int = 500) -> list[dict]:
    """Công TỰ KHAI chưa soi — worker soi tin nhặt từ đây."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select ci.*, c.full_name as customer_name, u.name as user_name
              from crm.care_interactions ci
              join crm.customers c on c.id = ci.customer_id
              left join crm.users u on u.id = ci.user_id
             where ci.verify_status = 'tu_khai_chua_soi'
               and ci.action_kind is not null
             order by ci.action_at limit %s
            """,
            (limit,),
        ).fetchall()


def tin_trong_cua(customer_id: int, tu, den) -> list[dict]:
    """Tin của NHÂN VIÊN gửi cho khách trong cửa sổ soi (±1 ngày).

    Chỉ lấy `sender_type = 'agent'`: tin của khách không phải bằng chứng nhân
    viên đã làm việc."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select m.id, m.content, m.sender_name, m.sender_user_id, m.sent_at
              from crm.messages m
              join crm.conversations cv on cv.id = m.conversation_id
             where cv.customer_id = %s and m.sender_type = 'agent'
               and m.sent_at between %s and %s
             order by m.sent_at
            """,
            (customer_id, tu, den),
        ).fetchall()


def dat_ket_qua_soi(cong_id: int, *, trang_thai: str, ly_do: str,
                    nguon: str | None = None, boi: int | None = None) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            update crm.care_interactions
               set verify_status = %(tt)s, verify_reason = %(ld)s,
                   verified_at = now(), verified_by = %(boi)s,
                   verify_source = coalesce(%(nguon)s, verify_source)
             where id = %(id)s returning *
            """,
            {"id": cong_id, "tt": trang_thai, "ld": ly_do, "boi": boi,
             "nguon": nguon},
        ).fetchone()


def bang_cong(*, trang_thai: str = "", user_id: int | None = None,
              limit: int = 200) -> list[dict]:
    dk, ts = ["ci.action_kind is not null"], {"l": limit}
    if trang_thai:
        dk.append("ci.verify_status = %(tt)s")
        ts["tt"] = trang_thai
    if user_id:
        dk.append("ci.user_id = %(nv)s")
        ts["nv"] = user_id
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select ci.*, c.full_name as customer_name,
                   c.primary_phone as customer_phone,
                   u.name as user_name, ux.name as verified_by_name
              from crm.care_interactions ci
              join crm.customers c on c.id = ci.customer_id
              left join crm.users u on u.id = ci.user_id
              left join crm.users ux on ux.id = ci.verified_by
             where {' and '.join(dk)}
             order by ci.action_at desc nulls last, ci.id desc
             limit %(l)s
            """,
            ts,
        ).fetchall()


def dem_cong() -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            """
            select count(*) filter (where verify_status = 'da_xac_minh')      as xac_minh,
                   count(*) filter (where verify_status = 'tu_khai_chua_soi') as cho_soi,
                   count(*) filter (where verify_status = 'bac_bo')           as bac_bo,
                   count(*)                                                   as tong
              from crm.care_interactions where action_kind is not null
            """
        ).fetchone()
    return dict(r)
