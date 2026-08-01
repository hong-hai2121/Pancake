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
    """Khối 'Sale' ở sidebar: 13 giai đoạn pipeline + số lead ĐANG MỞ từng cột
    (khớp với Kanban màn 11 — lead đóng không tính)."""
    global _SALE_MENU_CACHE
    if _SALE_MENU_CACHE and time.time() - _SALE_MENU_CACHE[0] < ttl:
        return _SALE_MENU_CACHE[1]
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            select s.id, s.name, s.is_closed, count(l.id) as so_lead
              from crm.pipeline_stages s
              left join crm.leads l on l.stage_id = s.id and l.closed_at is null
             group by s.id, s.name, s.is_closed
             order by s.sort_order
            """
        ).fetchall()
    _SALE_MENU_CACHE = (time.time(), rows)
    return rows


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


def pipeline_board() -> list[dict]:
    """Màn Pipeline Sale (màn 11, khung): 13 cột + tối đa 5 thẻ lead mỗi cột."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        stages = conn.execute(
            """
            select s.id, s.name, s.is_closed, count(l.id) as so_lead
              from crm.pipeline_stages s
              left join crm.leads l on l.stage_id = s.id and l.closed_at is null
             group by s.id, s.name, s.is_closed
             order by s.sort_order
            """
        ).fetchall()
        for s in stages:
            s["leads"] = conn.execute(
                """
                select l.id, c.full_name, l.temperature, l.next_action_at
                  from crm.leads l join crm.customers c on c.id = l.customer_id
                 where l.stage_id = %s and l.closed_at is null
                 order by l.updated_at desc limit 5
                """,
                (s["id"],),
            ).fetchall()
    return stages


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
    """Màn Chăm sóc (màn 26-27, khung): cột C01-C09 từ ref_codes + mốc chăm đến hạn."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        cot = conn.execute(
            "select code, name from crm.ref_codes "
            "where group_code = 'cskh_state' and status = 'active' order by sort_order"
        ).fetchall()
        so = conn.execute(
            """
            select
              (select count(*) from crm.care_plans where status = 'active') as ke_hoach_chay,
              (select count(*) from crm.care_plan_steps
                 where status not in ('done','skipped') and planned_at::date <= current_date) as moc_den_han
            """
        ).fetchone()
        moc = conn.execute(
            """
            select s.step_code, s.planned_at, s.status, c.full_name as khach
              from crm.care_plan_steps s
              join crm.care_plans p on p.id = s.care_plan_id
              join crm.customers c on c.id = p.customer_id
             where s.status not in ('done','skipped')
             order by s.planned_at limit 30
            """
        ).fetchall()
    return {"cot": cot, "so": so, "moc": moc}


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
    """Màn Sản phẩm & liệu trình (màn 42/44, khung)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        san_pham = conn.execute(
            "select product_code, name, product_type, price, status, approval_status "
            "from crm.products order by name limit 100"
        ).fetchall()
        lieu_trinh = conn.execute(
            "select template_code, name, problem_group, level, base_price, "
            "duration_days, status from crm.treatment_templates order by name limit 100"
        ).fetchall()
    return {"san_pham": san_pham, "lieu_trinh": lieu_trinh}
