"""Truy vấn CHỈ ĐỌC cho bộ màn CRM tạm (khung) — xem app/web/routes/crm.py.

Mỗi hàm phục vụ đúng 1 màn. Toàn bộ đọc schema `crm` (+ vài con số watcher qua
inbox_store ở tầng route). Khi các lát cắt B1…B11 làm thật, màn nào có nghiệp vụ
riêng sẽ thay các hàm này bằng service + repo chuyên; phần còn lại giữ nguyên.
"""

import time

from app.db.client import get_pg_pool

# Menu trái vẽ ở MỌI trang nên số lead theo giai đoạn được cache ngắn —
# lệch tối đa 15 giây, đổi lại không phải query mỗi lần chuyển trang.
_SALE_MENU_CACHE: tuple[float, list[dict]] | None = None


def sale_menu(ttl: float = 15.0) -> list[dict]:
    """Khối 'Sale' ở sidebar: 13 giai đoạn pipeline + số lead ĐANG ĐỨNG ở từng
    cột — đếm y hệt `pipeline_board` để số trên menu khớp số trên bảng.

    Lead ở giai đoạn kết thúc (Đã chốt / Từ chối…) đều có closed_at, nên KHÔNG
    lọc closed_at ở đây — lọc đi thì các cột kết thúc luôn hiện 0."""
    global _SALE_MENU_CACHE
    if _SALE_MENU_CACHE and time.time() - _SALE_MENU_CACHE[0] < ttl:
        return _SALE_MENU_CACHE[1]
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            select s.id, s.name, s.is_closed, count(c.id) as so_lead
              from crm.pipeline_stages s
              left join crm.leads l on l.stage_id = s.id
              left join crm.customers c on c.id = l.customer_id
                    and c.deleted_at is null
             group by s.id, s.name, s.is_closed
             order by s.sort_order
            """
        ).fetchall()
    _SALE_MENU_CACHE = (time.time(), rows)
    return rows


# ------------------------------------------------------------ Trang chủ (màn 2)
def _quan_cua_toi(conn, user_id: int) -> list[int]:
    """Trưởng nhóm: id mọi thành viên các đội mình quản (kể cả chính mình).
    Tra DB teams.manager_id — KHÔNG tin token (cùng nếp user_service.pham_vi_doi)."""
    rows = conn.execute(
        "select u.id from crm.users u join crm.teams t on t.id = u.team_id "
        "where t.manager_id = %s",
        (user_id,),
    ).fetchall()
    ids = {r["id"] for r in rows}
    ids.add(user_id)
    return list(ids)


def _viec_cua(conn, scope: list[int]) -> dict:
    """Đếm việc hôm nay / quá hạn / sắp tới 7 ngày của một nhóm người (B4) —
    đúng 3 ô lớn trên đầu Trang chủ."""
    return conn.execute(
        """
        select
          count(*) filter (where due_at::date = current_date and due_at >= now()) as hom_nay,
          count(*) filter (where due_at < now())                                  as qua_han,
          count(*) filter (where due_at > now()
                             and due_at::date <= current_date + 7)                as sap_toi
          from crm.tasks
         where status in ('open','in_progress') and assigned_to = any(%s)
        """,
        (scope,),
    ).fetchone()


def trang_chu(nhom: str, user_id: int) -> dict:
    """Màn 2 — Trang chủ theo vai trò: mỗi nhóm vai trò một bộ số riêng.

    `nhom` ∈ chu_dn · admin · sale · sale_tn · cskh · cskh_tn · marketing ·
    ke_toan · chuyen_mon · khac (vai trò lạ — chỉ hiện việc của tôi).
    Số nào phụ thuộc lát cắt chưa chạy (B8/B9…) thì trung thực ra 0."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        scope = (
            _quan_cua_toi(conn, user_id)
            if nhom in ("sale_tn", "cskh_tn") else [user_id]
        )
        data: dict = {"viec": _viec_cua(conn, scope)}

        if nhom in ("sale", "sale_tn"):
            data["lead"] = conn.execute(
                """
                select
                  count(*) filter (where closed_at is null)                       as mo,
                  count(*) filter (where closed_at is null
                                     and created_at::date = current_date)        as moi_hom_nay,
                  count(*) filter (where closed_at is null
                                     and temperature = 'nong')                   as nong,
                  count(*) filter (where closed_at is null
                                     and first_contact_at is null
                                     and sla_due_at < now())                     as qua_sla,
                  count(*) filter (where closed_at is null
                                     and next_action_at < now())                 as hen_tre
                  from crm.leads where owner_id = any(%s)
                """,
                (scope,),
            ).fetchone()
            data["don"] = conn.execute(
                """
                select
                  count(*) filter (where created_at >= date_trunc('month', now())) as don_thang,
                  coalesce(sum(total_amount) filter (where status = 'delivered'
                       and delivered_at >= date_trunc('month', now())), 0)         as doanh_thu_thang
                  from crm.orders where sale_owner_id = any(%s)
                """,
                (scope,),
            ).fetchone()
            data["can_lam"] = conn.execute(
                """
                select l.id, c.full_name, s.name as stage, l.temperature,
                       l.next_action_at, u.name as nguoi
                  from crm.leads l
                  join crm.customers c on c.id = l.customer_id
                  join crm.pipeline_stages s on s.id = l.stage_id
                  left join crm.users u on u.id = l.owner_id
                 where l.owner_id = any(%s) and l.closed_at is null
                 order by coalesce(l.next_action_at, l.sla_due_at) nulls last, l.id
                 limit 10
                """,
                (scope,),
            ).fetchall()
            if nhom == "sale_tn":
                data["hang_doi"] = conn.execute(
                    "select count(*) as n from crm.leads "
                    "where owner_id is null and closed_at is null"
                ).fetchone()["n"]
                data["theo_nv"] = conn.execute(
                    """
                    select u.name,
                           count(l.id) filter (where l.closed_at is null)      as mo,
                           count(l.id) filter (where l.closed_at is null
                                                 and l.next_action_at < now()) as tre,
                           count(l.id) filter (where l.closed_at is null
                                                 and l.temperature = 'nong')   as nong
                      from crm.users u
                      left join crm.leads l on l.owner_id = u.id
                     where u.id = any(%s) and u.status = 'active'
                     group by u.id, u.name order by u.name
                    """,
                    (scope,),
                ).fetchall()

        elif nhom in ("cskh", "cskh_tn"):
            # Đơn 'pending' là bước CS01 "xác nhận đơn" — B8 mới gán cskh_owner
            # nên đếm toàn hệ thống (đơn chưa có người nhận cũng phải thấy).
            data["so"] = conn.execute(
                """
                select
                  (select count(*) from crm.orders where status = 'pending')   as don_cho_xn,
                  (select count(*) from crm.care_plan_steps s
                     join crm.care_plans p on p.id = s.care_plan_id
                    where s.status not in ('done','skipped')
                      and s.planned_at::date <= current_date
                      and (p.owner_id = any(%(scope)s) or p.owner_id is null)) as moc_den_han,
                  (select count(*) from crm.repurchase_opportunities
                    where stage not in ('won','lost')
                      and (owner_id = any(%(scope)s) or owner_id is null))     as mua_lai
                """,
                {"scope": scope},
            ).fetchone()
            data["moc"] = conn.execute(
                """
                select s.step_code, s.planned_at, s.status, c.full_name as khach
                  from crm.care_plan_steps s
                  join crm.care_plans p on p.id = s.care_plan_id
                  join crm.customers c on c.id = p.customer_id
                 where s.status not in ('done','skipped')
                   and (p.owner_id = any(%s) or p.owner_id is null)
                 order by s.planned_at limit 10
                """,
                (scope,),
            ).fetchall()
            if nhom == "cskh_tn":
                data["theo_nv"] = conn.execute(
                    """
                    select u.name,
                           count(t.id)                                      as dang_mo,
                           count(t.id) filter (where t.due_at < now())      as qua_han
                      from crm.users u
                      left join crm.tasks t on t.assigned_to = u.id
                           and t.status in ('open','in_progress')
                     where u.id = any(%s) and u.status = 'active'
                     group by u.id, u.name order by u.name
                    """,
                    (scope,),
                ).fetchall()

        elif nhom == "marketing":
            data["ads"] = conn.execute(
                """
                select
                  coalesce(sum(spend) filter (where ngay >= current_date - 6), 0)  as chi_7n,
                  coalesce(sum(spend), 0)                                          as chi_30n,
                  count(distinct external_id) filter (where spend > 0)             as ad_co_chi
                  from crm.ad_metrics_daily
                 where entity_type = 'ad' and ngay >= current_date - 29
                """
            ).fetchone()
            data["moi"] = conn.execute(
                """
                select
                  (select count(*) from crm.leads
                    where created_at >= now() - interval '7 days')     as lead_7n,
                  (select count(*) from crm.customers
                    where created_at >= now() - interval '7 days')     as khach_7n,
                  (select coalesce(sum(total_amount), 0) from crm.orders
                    where status = 'delivered'
                      and delivered_at >= now() - interval '30 days')  as doanh_thu_30n
                """
            ).fetchone()

        elif nhom == "ke_toan":
            data["theo_tt"] = {
                r["status"]: r for r in conn.execute(
                    "select status, count(*) as n, coalesce(sum(total_amount),0) "
                    "as tien from crm.orders group by status"
                ).fetchall()
            }
            data["thang"] = conn.execute(
                """
                select
                  coalesce(sum(total_amount) filter (where status = 'delivered'
                       and delivered_at >= date_trunc('month', now())), 0) as doanh_thu_thang,
                  coalesce(sum(total_amount) filter (where status = 'delivered'
                       and delivered_at::date = current_date), 0)          as doanh_thu_hom_nay
                  from crm.orders
                """
            ).fetchone()
            data["rows"] = conn.execute(
                """
                select o.id, o.external_order_id, o.status, o.total_amount,
                       o.created_at, c.full_name as khach
                  from crm.orders o
                  left join crm.customers c on c.id = o.customer_id
                 order by o.id desc limit 10
                """
            ).fetchall()

        elif nhom == "chuyen_mon":
            data["so"] = conn.execute(
                """
                select
                  (select count(*) from crm.clinical_escalations
                    where status = 'pending')                          as ca_cho,
                  (select count(*) from crm.clinical_escalations
                    where status = 'pending' and assigned_to = %s)     as ca_cua_toi,
                  (select count(*) from crm.treatment_recommendations
                    where status = 'pending_approval')                 as de_xuat_cho,
                  (select count(*) from crm.products
                    where approval_status = 'pending')                 as sp_cho_duyet,
                  (select count(*) from crm.customers
                    where safety_flag = 'red')                         as khach_do,
                  (select count(*) from crm.customers
                    where safety_flag = 'yellow')                      as khach_vang
                """,
                (user_id,),
            ).fetchone()
            data["ca"] = conn.execute(
                """
                select e.reason, e.risk_level, e.created_at,
                       c.full_name as khach, u.name as giao_cho
                  from crm.clinical_escalations e
                  join crm.customers c on c.id = e.customer_id
                  left join crm.users u on u.id = e.assigned_to
                 where e.status = 'pending'
                 order by e.created_at desc limit 10
                """
            ).fetchall()

        elif nhom == "admin":
            data["so"] = conn.execute(
                """
                select
                  (select count(*) from crm.users where status = 'active')  as nv_active,
                  (select count(*) from crm.user_sessions
                    where created_at::date = current_date)                  as phien_hom_nay,
                  (select count(*) from crm.sync_errors
                    where status = 'pending')                               as loi_cho,
                  (select count(*) from crm.sync_errors
                    where status = 'given_up')                              as loi_bo_cuoc,
                  (select count(*) from crm.audit_logs
                    where created_at::date = current_date)                  as thao_tac_hom_nay
                """
            ).fetchone()
            data["audit_moi"] = conn.execute(
                """
                select a.action, a.object_type, a.created_at, u.name as user_name
                  from crm.audit_logs a left join crm.users u on u.id = a.user_id
                 order by a.id desc limit 8
                """
            ).fetchall()

        elif nhom == "chu_dn":
            data["so"] = conn.execute(
                """
                select
                  (select count(*) from crm.customers)                          as khach,
                  (select count(*) from crm.leads where closed_at is null)      as lead_mo,
                  (select count(*) from crm.tasks
                    where status in ('open','in_progress') and due_at < now())  as viec_qua_han,
                  (select count(*) from crm.orders
                    where created_at >= date_trunc('month', now()))             as don_thang,
                  (select coalesce(sum(total_amount),0) from crm.orders
                    where status = 'delivered'
                      and delivered_at >= date_trunc('month', now()))           as doanh_thu_thang,
                  (select count(*) from crm.repurchase_opportunities
                    where stage not in ('won','lost'))                          as co_hoi_mua_lai
                """
            ).fetchone()
            data["ads"] = conn.execute(
                """
                select
                  coalesce(sum(spend), 0) as chi_30n,
                  (select coalesce(sum(total_amount), 0) from crm.orders
                    where status = 'delivered'
                      and delivered_at >= now() - interval '30 days') as doanh_thu_30n
                  from crm.ad_metrics_daily
                 where entity_type = 'ad' and ngay >= current_date - 29
                """
            ).fetchone()

    return data


def dashboard() -> dict:
    """Màn Tổng quan: các con số đếm thẳng từ DB — bảng trống thì ra 0, trung thực."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        so = conn.execute(
            """
            select
              (select count(*) from crm.customers)                                as khach,
              (select count(*) from crm.leads where closed_at is null)            as lead_mo,
              (select count(*) from crm.tasks where status in ('open','in_progress')
                 and due_at::date = current_date)                                 as viec_hom_nay,
              (select count(*) from crm.tasks where status in ('open','in_progress')
                 and due_at < now())                                              as viec_qua_han,
              (select count(*) from crm.orders)                                   as don,
              (select coalesce(sum(total_amount),0) from crm.orders
                 where status = 'delivered')                                      as doanh_thu_giao,
              (select count(*) from crm.repurchase_opportunities
                 where stage not in ('won','lost'))                               as co_hoi_mua_lai,
              (select count(*) from crm.users where status = 'active')            as nhan_vien
            """
        ).fetchone()
        theo_stage = conn.execute(
            """
            select s.name, s.is_closed, count(l.id) as so_lead
              from crm.pipeline_stages s
              left join crm.leads l on l.stage_id = s.id and l.closed_at is null
             group by s.id, s.name, s.is_closed
             order by s.sort_order
            """
        ).fetchall()
        audit_moi = conn.execute(
            """
            select a.action, a.object_type, a.created_at, u.name as user_name
              from crm.audit_logs a left join crm.users u on u.id = a.user_id
             order by a.id desc limit 6
            """
        ).fetchall()
    return {"so": so, "theo_stage": theo_stage, "audit_moi": audit_moi}


def list_customers(q: str = "", limit: int = 50) -> tuple[list[dict], int]:
    """Màn Khách hàng (màn 8, khung): tìm theo tên/SĐT/mã."""
    where, ts = "true", []
    if q:
        where = "(full_name ilike %s or primary_phone ilike %s or customer_code ilike %s)"
        ts = [f"%{q}%"] * 3
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"""
            select c.id, c.customer_code, c.full_name, c.primary_phone, c.province,
                   c.status, c.created_at, c.synced_at,
                   -- BRD mục 4: dữ liệu để dựng nút "mở đúng hội thoại Pancake";
                   -- lấy hội thoại MỚI NHẤT của khách, đọc DB chứ không gọi API.
                   hi.external_page_id, hi.external_conversation_id
              from crm.customers c
              left join lateral (
                    select p.external_page_id, cv.external_conversation_id
                      from crm.conversations cv
                      join crm.pages p on p.id = cv.page_id
                     where cv.customer_id = c.id
                     order by cv.last_message_at desc nulls last
                     limit 1
              ) hi on true
             where {where}
             order by c.id desc limit %s
            """,
            (*ts, limit),
        ).fetchall()
        total = conn.execute(
            f"select count(*) as n from crm.customers c where {where}", ts or None
        ).fetchone()["n"]
    return rows, total


# ==================================== Khách hàng — bảng đầy đủ (màn 8, bản mẫu)
# Giao diện port từ mẫu Kallet: mỗi hàng cần thêm số lần mua · tổng chi · ngày
# nhận hàng cuối · tương tác cuối · lần chăm sóc cuối · người phụ trách ·
# fanpage. Gom hết vào MỘT câu (lateral join) thay vì N+1 truy vấn theo hàng.
#
# QUY ƯỚC ĐẾM — dùng chung cho cả bảng lẫn 5 ô đếm nên hai chỗ không lệch nhau:
#   * "đơn đã chốt" = crm.orders có status ngoài (draft, cancelled, returned)
#   * Lần mua        = số đơn đã chốt
#   * Tổng chi       = tổng total_amount của các đơn đó
#   * Nhận hàng cuối = max(delivered_at); chưa giao đơn nào -> rỗng ("chưa mua")
#   * Tình trạng tính theo số ngày kể từ Nhận hàng cuối, đúng ngưỡng của mẫu:
#     ≤180 đang chăm · 181–210 sắp buông · >210 ngủ.
_KH_SONG = "c.deleted_at is null and c.status <> 'merged'"

_KH_DON = """
    left join lateral (
          select count(*)                         as so_lan_mua,
                 coalesce(sum(o.total_amount), 0) as tong_chi,
                 max(o.delivered_at)              as nhan_hang_cuoi
            from crm.orders o
           where o.customer_id = c.id
             and o.status not in ('draft', 'cancelled', 'returned')
    ) dh on true
"""

# Hội thoại MỚI NHẤT: lấy fanpage (cột "Khách" ở mẫu in tên page dưới số điện
# thoại), mốc tương tác cuối và cặp id để dựng link mở Pancake.
_KH_HOI_THOAI = """
    left join lateral (
          select cv.page_id, cv.last_message_at, cv.external_conversation_id
            from crm.conversations cv
           where cv.customer_id = c.id
           order by cv.last_message_at desc nulls last
           limit 1
    ) hc on true
    left join crm.pages p on p.id = hc.page_id
"""

# "Cửa gửi tin" của Meta tính từ tin CUỐI CÙNG CỦA KHÁCH — crm.conversations chỉ
# có last_message_at (tin của bất kỳ bên nào) nên phải mượn kho hội thoại của
# worker (`watcher.hoi_thoai`, cùng DB, khoá chính (page_id, conv_id) nên tra
# theo index). Kho có thể chưa tồn tại ở máy mới cài -> dò một lần rồi nhớ, thiếu
# thì trả cột rỗng và giao diện hiện "chưa rõ cửa" thay vì đoán bừa.
_KHO_HT: bool | None = None


def _co_kho_hoi_thoai(conn) -> bool:
    global _KHO_HT
    if _KHO_HT is None:
        _KHO_HT = conn.execute(
            "select to_regclass('watcher.hoi_thoai') is not null as co"
        ).fetchone()["co"]
    return _KHO_HT


_KH_CUA_JOIN = """
    left join watcher.hoi_thoai ht
           on ht.page_id = p.external_page_id
          and ht.conv_id = hc.external_conversation_id
"""

_KH_CHAM = """
    left join lateral (
          select ci.created_at as cham_luc, u.name as cham_boi
            from crm.care_interactions ci
            left join crm.users u on u.id = ci.user_id
           where ci.customer_id = c.id
           order by ci.created_at desc
           limit 1
    ) cs on true
"""

# Một lượt quét bảng phân công cho cả 2 vai (thay vì 4 câu con lồng nhau).
_KH_PHU_TRACH = """
    left join lateral (
          select max(u.name)    filter (where a.assignment_type = 'sale') as sale_ten,
                 max(a.user_id) filter (where a.assignment_type = 'sale') as sale_id,
                 max(u.name)    filter (where a.assignment_type = 'cskh') as cskh_ten,
                 max(a.user_id) filter (where a.assignment_type = 'cskh') as cskh_id
            from crm.customer_assignments a
            join crm.users u on u.id = a.user_id
           where a.customer_id = c.id and a.end_at is null
    ) pt on true
"""

def _kh_join_loc(owner_id: int, page_id: int) -> str:
    """Join TỐI THIỂU đủ để lọc + sắp xếp + đếm tổng.

    Chạy trên toàn bộ khách sống (vài chục nghìn dòng) nên chỉ kéo theo đúng
    thứ bộ lọc đang cần: bảng đơn luôn cần (lọc lẫn sắp xếp), phân công và hội
    thoại chỉ khi người dùng lọc theo nhân viên / fanpage.
    """
    return (_KH_DON
            + (_KH_PHU_TRACH if owner_id else "")
            + (_KH_HOI_THOAI if page_id else ""))


def _kh_join_hien(co_cua: bool) -> str:
    """Join phần chỉ để HIỂN THỊ — chạy sau khi đã cắt còn 1 trang (≤100 dòng)."""
    return (_KH_HOI_THOAI + (_KH_CUA_JOIN if co_cua else "")
            + _KH_CHAM + _KH_PHU_TRACH)

# Số ngày kể từ lần nhận hàng cuối — viết một chỗ vì cả bộ lọc lẫn ô đếm dùng.
_KH_NGAY = "(now()::date - dh.nhan_hang_cuoi::date)"


# ------------------------------------------------------ T4: hết số ghi cứng
# Ba dải tình trạng chăm sóc (đang chăm · sắp buông · ngủ) TRƯỚC ĐÂY ghi cứng
# 180/210 — số của thang chăm CŨ (30·60·90·120·150·180, buông 210). Thang thật
# bây giờ là C6: D45 → D195 cách nhau 15 ngày, buông ở `cskh_leave_days`.
# Ghi cứng nghĩa là admin đổi mốc trên web mà màn Khách hàng vẫn đếm theo số cũ
# — số hiện ra không khớp bảng việc, và không ai hiểu vì sao.
#
# Nguồn sự thật: bảng `crm.care_milestones` (thang thật) + cài đặt
# `cskh_leave_days` (mốc rời bảng). Hỏng/rỗng thì lùi về 180/210 như cũ.
def _moc_roi_bang() -> int:
    """Quá bao nhiêu ngày không mua thì khách RỜI bảng việc (coi như ngủ)."""
    try:
        from app.core import runtime_config

        return int(runtime_config.so("cskh_leave_days", 210))
    except Exception:  # noqa: BLE001 — màn khách không được chết vì cài đặt
        return 210


def _moc_cham_cuoi() -> int:
    """Mốc chăm CUỐI CÙNG của thang — hết mốc này là bước sang dải "sắp buông".

    Lấy mốc lớn nhất đang bật, KHÔNG kể mốc rời bảng. Thang C6 mặc định cho
    195 (D45…D195, buông 210)."""
    roi = _moc_roi_bang()
    try:
        pool = get_pg_pool()
        with pool.connection() as conn:
            r = conn.execute(
                "select max(offset_days) as n from crm.care_milestones "
                "where active and dept = 'cskh' and offset_days < %s",
                (roi,),
            ).fetchone()
        if r and r["n"]:
            return int(r["n"])
    except Exception:  # noqa: BLE001 — bảng chưa có thì dùng số cũ
        pass
    return min(180, roi - 1)


def dai_cham_soc() -> tuple[int, int]:
    """(mốc chăm cuối, mốc rời bảng) — mọi chỗ chia dải phải gọi hàm này."""
    roi = _moc_roi_bang()
    cuoi = _moc_cham_cuoi()
    # Cấu hình lộn xộn (mốc chăm >= mốc buông) thì tự kéo về cho dải không rỗng.
    return (min(cuoi, roi - 1), roi)

# Khoảng "ngày mua cuối" của bộ lọc mẫu -> (từ, đến); None = không chặn đầu đó.
KH_BUCKET: dict[str, tuple[int, int | None]] = {
    "0-30": (0, 30), "31-60": (31, 60), "61-90": (61, 90),
    "91-120": (91, 120), "121-150": (121, 150), "151-180": (151, 180),
    "181-210": (181, 210), "gt210": (211, None),
}


def _kh_loc(q: str, tt: str, bucket: str, owner_id: int, page_id: int,
            so_mua: str, chi_tu, chi_den, tier: str = "") -> tuple[list[str], list]:
    """Dựng mệnh đề WHERE + tham số cho bảng khách (dùng lại ở câu đếm tổng)."""
    dk, ts = [_KH_SONG], []
    # C1 — hạng thẻ. 'chua_xep' là hạng thứ 6 (card_rank NULL), KHÔNG phải một
    # dòng trong card_ranks: xem đầu scripts/seed_uu_dai.py.
    if tier == "chua_xep":
        dk.append("c.card_rank is null")
    elif tier:
        dk.append("c.card_rank = %s")
        ts.append(tier)
    if q:
        dk.append("(c.full_name ilike %s or c.primary_phone like %s"
                  " or c.customer_code ilike %s)")
        ts += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if tt == "chua_mua":
        dk.append("dh.nhan_hang_cuoi is null")
    elif tt in ("active", "fading", "sleep"):
        cuoi, roi = dai_cham_soc()          # T4 — không còn ghi cứng 180/210
        if tt == "active":
            dk.append(f"dh.nhan_hang_cuoi is not null and {_KH_NGAY} <= %s")
            ts.append(cuoi)
        elif tt == "fading":
            dk.append(f"dh.nhan_hang_cuoi is not null "
                      f"and {_KH_NGAY} between %s and %s")
            ts += [cuoi + 1, roi]
        else:
            dk.append(f"dh.nhan_hang_cuoi is not null and {_KH_NGAY} > %s")
            ts.append(roi)
    if bucket in KH_BUCKET:
        tu, den = KH_BUCKET[bucket]
        dk.append(f"dh.nhan_hang_cuoi is not null and {_KH_NGAY} >= %s")
        ts.append(tu)
        if den is not None:
            dk.append(f"{_KH_NGAY} <= %s")
            ts.append(den)
    if owner_id:
        dk.append("(pt.sale_id = %s or pt.cskh_id = %s)")
        ts += [owner_id, owner_id]
    if page_id:
        dk.append("p.id = %s")
        ts.append(page_id)
    if so_mua in ("1", "2", "3"):
        dk.append("dh.so_lan_mua = %s")
        ts.append(int(so_mua))
    elif so_mua == "4":
        dk.append("dh.so_lan_mua >= 4")
    if chi_tu is not None:
        dk.append("dh.tong_chi >= %s")
        ts.append(chi_tu)
    if chi_den is not None:
        dk.append("dh.tong_chi <= %s")
        ts.append(chi_den)
    return dk, ts


def khach_hang_bang(*, q: str = "", tt: str = "", bucket: str = "",
                    owner_id: int = 0, page_id: int = 0, so_mua: str = "",
                    chi_tu: float | None = None, chi_den: float | None = None,
                    tier: str = "",
                    limit: int = 30, offset: int = 0) -> tuple[list[dict], int]:
    """Một trang của bảng khách + TỔNG số khách khớp bộ lọc (để phân trang).

    HAI BƯỚC cố ý: câu trong chỉ lọc/sắp/cắt trang (join tối thiểu), câu ngoài
    mới bồi mấy thứ chỉ để hiển thị. Gộp một câu thì Postgres phải chạy toàn bộ
    lateral cho cả chục nghìn khách rồi mới LIMIT — chậm gấp mấy lần.
    """
    dk, ts = _kh_loc(q, tt, bucket, owner_id, page_id, so_mua, chi_tu, chi_den,
                     tier)
    where = " and ".join(dk)
    loc_join = _kh_join_loc(owner_id, page_id)
    pool = get_pg_pool()
    with pool.connection() as conn:
        cua = ("ht.last_customer_at" if _co_kho_hoi_thoai(conn) else "null::text")
        total = conn.execute(
            f"select count(*) as n from crm.customers c {loc_join} where {where}",
            ts or None,
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            with trang as (
                select c.id, dh.so_lan_mua, dh.tong_chi, dh.nhan_hang_cuoi,
                       case when dh.nhan_hang_cuoi is null then null
                            else {_KH_NGAY} end as ngay_tu_mua
                  from crm.customers c {loc_join}
                 where {where}
                 order by dh.nhan_hang_cuoi desc nulls last, c.id desc
                 limit %s offset %s
            )
            select c.id, c.customer_code, c.full_name, c.primary_phone,
                   c.province, c.status, c.source, c.created_at,
                   c.card_rank, c.last_delivered_at,
                   -- C1: khách có hạng mà quá hạn không nhận hàng thì quyền lợi
                   -- tụt 1 bậc (hạng hiển thị GIỮ NGUYÊN) — cột này để bảng gắn
                   -- dấu, tuyệt đối không dùng để đổi c.card_rank.
                   (c.card_rank is not null and c.last_delivered_at is not null
                    and c.last_delivered_at
                        < now() - make_interval(days => %s)) as giam_quyen_loi,
                   t.so_lan_mua, t.tong_chi, t.nhan_hang_cuoi, t.ngay_tu_mua,
                   hc.last_message_at, hc.external_conversation_id,
                   p.external_page_id, p.name as page_name,
                   {cua}                                   as last_customer_at,
                   cs.cham_luc, cs.cham_boi,
                   pt.sale_ten, pt.cskh_ten
              from trang t
              join crm.customers c on c.id = t.id
              {_kh_join_hien(_co_kho_hoi_thoai(conn))}
             order by t.nhan_hang_cuoi desc nulls last, c.id desc
            """,
            # Thứ tự tham số theo THỨ TỰ XUẤT HIỆN trong câu: WHERE của CTE →
            # limit/offset → mốc giảm quyền lợi ở SELECT ngoài.
            [*ts, limit, offset, _ngay_giam_quyen_loi()],
        ).fetchall()
    return rows, total


def _ngay_giam_quyen_loi() -> int:
    """Mốc "180 ngày không nhận hàng thì tụt quyền lợi" — đọc cài đặt chạy để
    admin đổi được, hỏng thì lùi về 180 (xem services/voucher_service)."""
    try:
        from app.core import runtime_config

        return int(runtime_config.so("card_rank_downgrade_days", 180))
    except Exception:  # noqa: BLE001 — bảng khách không được chết vì cài đặt
        return 180


def khach_hang_dem() -> dict:
    """5 ô đếm đầu màn — đếm trên TOÀN BỘ khách sống, không theo bộ lọc.

    Chỉ cần bảng đơn nên không kéo theo mấy lateral join còn lại của bảng.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            with m as (
                select (select max(o.delivered_at) from crm.orders o
                         where o.customer_id = c.id
                           and o.status not in ('draft','cancelled','returned')
                       ) as mua_cuoi
                  from crm.customers c
                 where {_KH_SONG}
            )
            select count(*)                                         as tong,
                   count(*) filter (
                       where mua_cuoi is not null
                         and now()::date - mua_cuoi::date <= %(cuoi)s) as dang_cham,
                   count(*) filter (
                       where mua_cuoi is not null
                         and now()::date - mua_cuoi::date
                             between %(cuoi)s + 1 and %(roi)s
                   )                                                as sap_buong,
                   count(*) filter (
                       where mua_cuoi is not null
                         and now()::date - mua_cuoi::date > %(roi)s)  as ngu,
                   count(*) filter (where mua_cuoi is null)          as chua_mua
              from m
            """,
            dict(zip(("cuoi", "roi"), dai_cham_soc())),
        ).fetchone()


def khach_hang_fanpages() -> list[dict]:
    """Danh sách fanpage cho ô lọc (chỉ page thật sự có hội thoại gắn khách)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select p.id, p.name
              from crm.pages p
             where exists (select 1 from crm.conversations cv
                            where cv.page_id = p.id and cv.customer_id is not null)
             order by p.name
            """
        ).fetchall()


# ------------------------------------------ Bảng chăm sóc theo mốc (màn 11)
# Hội thoại Pancake MỚI NHẤT của khách — dùng chung cho thẻ trên bảng và khung
# làm việc bên phải (đọc DB, không gọi API Pancake mỗi lần mở màn — luật mục 4).
_HOI_THOAI_MOI = """
    left join lateral (
          select p.external_page_id, p.name as page_name,
                 cv.external_conversation_id, cv.message_count, cv.last_message_at
            from crm.conversations cv
            join crm.pages p on p.id = cv.page_id
           where cv.customer_id = c.id
           order by cv.last_message_at desc nulls last
           limit 1
    ) hi on true
"""


def _ngay(v: str):
    """'YYYY-MM-DD' -> date; rỗng hoặc sai định dạng -> None (bỏ qua bộ lọc)."""
    from datetime import date

    try:
        return date.fromisoformat((v or "").strip())
    except ValueError:
        return None


def _loc_bang_cham_soc(
    q: str, owner_id: int | None, temperature: str, moc: str, tu: str, den: str,
) -> tuple[str, dict]:
    """Mảnh WHERE + tham số dùng chung cho 3 câu của bảng chăm sóc (đếm cột,
    lấy thẻ, tính chỉ số) — sửa một chỗ là cả 3 câu cùng đổi."""
    dk = ["c.deleted_at is null"]
    ts: dict = {}
    if q.strip():
        dk.append("(c.full_name ilike %(q)s or c.primary_phone ilike %(q)s "
                  "or c.customer_code ilike %(q)s)")
        ts["q"] = f"%{q.strip()}%"
    if owner_id:
        dk.append("l.owner_id = %(own)s")
        ts["own"] = owner_id
    if temperature:
        dk.append("l.temperature = %(nhiet)s")
        ts["nhiet"] = temperature
    # Mốc bám đuổi: tính trên next_action_at của lead ĐANG MỞ
    if moc == "qua_han":
        dk.append("l.closed_at is null and l.next_action_at < now()")
    elif moc == "hom_nay":
        dk.append("l.closed_at is null and l.next_action_at::date = current_date")
    elif moc == "chua_hen":
        dk.append("l.closed_at is null and l.next_action_at is null")
    # Thời điểm tạo = ngày khách vào (khớp bộ lọc "Thời điểm tạo" trên thanh lọc).
    # Ngày gõ sai/bịa trong URL thì BỎ QUA chứ không để Postgres ném lỗi 500.
    if (d := _ngay(tu)) is not None:
        dk.append("l.created_at >= %(tu)s")
        ts["tu"] = d
    if (d := _ngay(den)) is not None:
        dk.append("l.created_at < %(den)s + 1")
        ts["den"] = d
    return " and ".join(dk), ts


def pipeline_board(
    *,
    st: int = 0,
    q: str = "",
    owner_id: int | None = None,
    temperature: str = "",
    moc: str = "",
    tu: str = "",
    den: str = "",
    moi_cot: int = 12,
) -> dict:
    """Màn 11 — bảng chăm sóc theo mốc: mọi giai đoạn + thẻ khách mỗi cột.

    Trả `{"stages": [...], "kpi": {...}}`. Số đếm và chỉ số tính trên TOÀN bộ
    lead khớp bộ lọc (không cắt theo `st`) để bấm qua lại giữa các cột thì dải
    chỉ số vẫn đứng yên; `st` chỉ giới hạn danh sách thẻ phải lấy về.

    Khác bản khung cũ: KHÔNG bỏ lead đã đóng — lead nằm ở giai đoạn kết thúc
    (Đã chốt / Từ chối…) luôn có closed_at, lọc đi thì các cột đó rỗng vĩnh viễn.

    `moi_cot` — số thẻ tối đa mỗi cột (xem 1 cột thì route truyền số lớn hơn).
    """
    where, ts = _loc_bang_cham_soc(q, owner_id, temperature, moc, tu, den)
    pool = get_pg_pool()
    with pool.connection() as conn:
        stages = conn.execute(
            f"""
            select s.id, s.code, s.name, s.is_closed, s.sort_order,
                   coalesce(n.so, 0) as so_lead
              from crm.pipeline_stages s
              left join (
                    select l.stage_id, count(*) as so
                      from crm.leads l
                      join crm.customers c on c.id = l.customer_id
                     where {where}
                     group by l.stage_id
              ) n on n.stage_id = s.id
             order by s.sort_order
            """,
            ts or None,
        ).fetchall()

        kpi = conn.execute(
            f"""
            select count(*)                                          as tong,
                   count(*) filter (where l.closed_at is null)       as dang_mo,
                   count(*) filter (where l.closed_at is null
                                      and l.temperature = 'nong')    as nong,
                   count(*) filter (where l.closed_at is null
                                      and l.next_action_at < now())  as qua_han,
                   count(*) filter (where s.code = 'da_chot')        as da_chot
              from crm.leads l
              join crm.customers c on c.id = l.customer_id
              join crm.pipeline_stages s on s.id = l.stage_id
             where {where}
            """,
            ts or None,
        ).fetchone()

        loc_cot = " and l.stage_id = %(st)s" if st else ""
        the = conn.execute(
            f"""
            select * from (
              select l.id, l.stage_id, l.customer_id, l.temperature, l.priority,
                     l.source, l.next_action_at, l.stage_entered_at,
                     l.first_contact_at, l.sla_due_at, l.closed_at, l.created_at,
                     c.full_name, c.primary_phone, c.province, c.customer_code,
                     u.name as owner_name,
                     hi.external_page_id, hi.external_conversation_id,
                     hi.message_count, hi.last_message_at, hi.page_name,
                     row_number() over (
                         partition by l.stage_id
                         order by (l.next_action_at is null), l.next_action_at,
                                  l.created_at desc
                     ) as rn
                from crm.leads l
                join crm.customers c on c.id = l.customer_id
                left join crm.users u on u.id = l.owner_id
                {_HOI_THOAI_MOI}
               where {where}{loc_cot}
            ) t
             where rn <= %(so)s
             order by stage_id, rn
            """,
            {**ts, "st": st, "so": moi_cot},
        ).fetchall()

    theo_cot: dict[int, list[dict]] = {}
    for r in the:
        theo_cot.setdefault(r["stage_id"], []).append(r)
    for s in stages:
        s["leads"] = theo_cot.get(s["id"], [])
    return {"stages": stages, "kpi": dict(kpi or {})}


def pipeline_lead(lead_id: int) -> dict | None:
    """Khung làm việc bên phải màn 11 — hồ sơ khách tiềm năng đang chọn:
    lead + khách + người phụ trách + hội thoại Pancake mới nhất, kèm danh sách
    giai đoạn của đúng pipeline đó và nhật ký chuyển cột."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        lead = conn.execute(
            f"""
            select l.*, s.code as stage_code, s.name as stage_name, s.is_closed,
                   s.sort_order,
                   c.full_name, c.primary_phone, c.province, c.customer_code,
                   c.status as kh_status,
                   u.name as owner_name,
                   hi.external_page_id, hi.external_conversation_id,
                   hi.message_count, hi.last_message_at, hi.page_name
              from crm.leads l
              join crm.pipeline_stages s on s.id = l.stage_id
              join crm.customers c on c.id = l.customer_id
              left join crm.users u on u.id = l.owner_id
              {_HOI_THOAI_MOI}
             where l.id = %s
            """,
            (lead_id,),
        ).fetchone()
        if lead is None:
            return None
        lead["stages"] = conn.execute(
            "select id, code, name, is_closed, sort_order "
            "from crm.pipeline_stages where pipeline_id = %s order by sort_order",
            (lead["pipeline_id"],),
        ).fetchall()
        lead["lich_su"] = conn.execute(
            """
            select h.changed_at, h.reason, h.note,
                   sf.name as from_stage_name, st.name as to_stage_name,
                   u.name as changed_by_name
              from crm.lead_stage_history h
              left join crm.pipeline_stages sf on sf.id = h.from_stage_id
              join crm.pipeline_stages st on st.id = h.to_stage_id
              left join crm.users u on u.id = h.changed_by
             where h.lead_id = %s
             order by h.changed_at desc
             limit 20
            """,
            (lead_id,),
        ).fetchall()
    return lead


# Cache số đếm menu CSKH theo user (menu vẽ ở MỌI trang) — cùng nếp sale_menu
_CSKH_MENU_CACHE: dict[int | None, tuple[float, dict]] = {}


def menu_cskh_counts(user_id: int | None, ttl: float = 15.0) -> dict:
    """Số đếm nhỏ cho mục menu 'Chăm sóc khách hàng' (sidebar) — 1 câu SQL,
    cache 15 giây theo người dùng.

    Việc hôm nay/quá hạn/sắp tới đếm THEO NGƯỜI đăng nhập (khớp màn Công việc
    mặc định 'việc của tôi'); chăm sóc + mua lại đếm toàn hệ thống."""
    cu = _CSKH_MENU_CACHE.get(user_id)
    if cu and time.time() - cu[0] < ttl:
        return cu[1]
    loc = "and t.assigned_to = %(u)s" if user_id else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        row = conn.execute(
            f"""
            select
              (select count(*) from crm.tasks t
                where t.status in ('open','in_progress')
                  and t.due_at::date = current_date and t.due_at >= now() {loc}) as hom_nay,
              (select count(*) from crm.tasks t
                where t.status in ('open','in_progress')
                  and t.due_at < now() {loc}) as qua_han,
              (select count(*) from crm.tasks t
                where t.status in ('open','in_progress')
                  and t.due_at::date > current_date {loc}) as sap_toi,
              (select count(*) from crm.care_plans) as cham_soc,
              (select count(*) from crm.repurchase_opportunities
                where stage not in ('won','lost')) as mua_lai
            """,
            {"u": user_id},
        ).fetchone()
    _CSKH_MENU_CACHE[user_id] = (time.time(), row)
    return row


def tasks_groups(assigned_to: int | None = None) -> dict:
    """Màn Công việc (màn 12/26): quá hạn / hôm nay / sắp tới.

    `assigned_to` — B4: màn mặc định lọc theo người đăng nhập, None = cả đội."""
    pool = get_pg_pool()

    def _pick(conn, where: str) -> list[dict]:
        loc_nguoi = "and t.assigned_to = %(ai)s" if assigned_to else ""
        return conn.execute(
            f"""
            select t.id, t.title, t.task_type, t.due_at, t.priority, t.status,
                   c.full_name as khach, u.name as nguoi_lam
              from crm.tasks t
              left join crm.customers c on c.id = t.customer_id
              left join crm.users u on u.id = t.assigned_to
             where t.status in ('open','in_progress') and {where} {loc_nguoi}
             order by t.due_at limit 30
            """,
            {"ai": assigned_to},
        ).fetchall()

    with pool.connection() as conn:
        return {
            "qua_han": _pick(conn, "t.due_at < now()"),
            "hom_nay": _pick(conn, "t.due_at::date = current_date and t.due_at >= now()"),
            "sap_toi": _pick(conn, "t.due_at::date > current_date"),
        }


def orders_summary() -> dict:
    """Màn Đơn hàng (màn 21, khung): đếm theo trạng thái + 30 đơn mới nhất."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        theo_tt = conn.execute(
            "select status, count(*) as n, coalesce(sum(total_amount),0) as tien "
            "from crm.orders group by status"
        ).fetchall()
        rows = conn.execute(
            """
            select o.id, o.external_order_id, o.order_type, o.status, o.total_amount,
                   o.created_at, c.full_name as khach, u.name as sale
              from crm.orders o
              left join crm.customers c on c.id = o.customer_id
              left join crm.users u on u.id = o.sale_owner_id
             order by o.id desc limit 30
            """
        ).fetchall()
    return {"theo_trang_thai": {r["status"]: r for r in theo_tt}, "rows": rows}


def care_board() -> dict:
    """Màn Chăm sóc (màn 27 — B9 đổ dữ liệu THẬT): cột C01-C09 đếm từ
    care_plans.cskh_state + mốc chờ làm + danh sách kế hoạch đang chạy."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        cot = conn.execute(
            """
            select r.code, r.name, count(p.id) as n
              from crm.ref_codes r
              left join crm.care_plans p on p.cskh_state = r.code
                   and p.status = 'active'
             where r.group_code = 'cskh_state' and r.status = 'active'
             group by r.code, r.name, r.sort_order
             order by r.sort_order
            """
        ).fetchall()
        so = conn.execute(
            """
            select
              (select count(*) from crm.care_plans where status = 'active') as ke_hoach_chay,
              (select count(*) from crm.care_plan_steps s
                 join crm.care_plans p on p.id = s.care_plan_id
                where s.status in ('pending','due')
                  and s.planned_at::date <= current_date
                  and p.status = 'active')                                   as moc_den_han,
              (select count(*) from crm.customers where do_not_contact)      as ngung_lien_he
            """
        ).fetchone()
        moc = conn.execute(
            """
            select s.step_code, s.planned_at, s.status, s.care_plan_id,
                   c.full_name as khach, u.name as phu_trach
              from crm.care_plan_steps s
              join crm.care_plans p on p.id = s.care_plan_id
              join crm.customers c on c.id = p.customer_id
              left join crm.users u on u.id = p.owner_id
             where s.status in ('pending','due') and p.status = 'active'
               and not c.do_not_contact
             order by s.planned_at limit 30
            """
        ).fetchall()
        ke_hoach = conn.execute(
            """
            select p.id, p.cskh_state, p.cycle_no, p.actual_start_date,
                   c.full_name as khach, u.name as phu_trach,
                   (select count(*) from crm.care_plan_steps s
                     where s.care_plan_id = p.id and s.status = 'done') as moc_xong,
                   (select count(*) from crm.care_plan_steps s
                     where s.care_plan_id = p.id)                       as moc_tong
              from crm.care_plans p
              join crm.customers c on c.id = p.customer_id
              left join crm.users u on u.id = p.owner_id
             where p.status = 'active'
             order by p.id desc limit 50
            """
        ).fetchall()
    return {"cot": cot, "so": so, "moc": moc, "ke_hoach": ke_hoach}


def repurchase_summary() -> dict:
    """Màn Mua lại (màn 39-40, khung)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        theo_stage = conn.execute(
            "select stage, count(*) as n from crm.repurchase_opportunities group by stage"
        ).fetchall()
        rows = conn.execute(
            """
            select r.id, r.stage, r.expected_close_date, r.expected_value,
                   c.full_name as khach, u.name as phu_trach
              from crm.repurchase_opportunities r
              join crm.customers c on c.id = r.customer_id
              left join crm.users u on u.id = r.owner_id
             order by r.expected_close_date nulls last limit 30
            """
        ).fetchall()
    return {"theo_stage": {r["stage"]: r["n"] for r in theo_stage}, "rows": rows}


def products_treatments() -> dict:
    """Màn Sản phẩm & liệu trình (màn 42/44) — `id` để bấm sang chi tiết 43/45."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        san_pham = conn.execute(
            "select id, product_code, name, product_type, price, status, "
            "approval_status from crm.products order by name limit 100"
        ).fetchall()
        lieu_trinh = conn.execute(
            "select id, template_code, name, problem_group, level, base_price, "
            "duration_days, status from crm.treatment_templates order by name limit 100"
        ).fetchall()
    return {"san_pham": san_pham, "lieu_trinh": lieu_trinh}
