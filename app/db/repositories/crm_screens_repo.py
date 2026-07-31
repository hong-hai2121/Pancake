"""Truy vấn CHỈ ĐỌC cho bộ màn CRM tạm (khung) — xem app/web/routes/crm.py.

Mỗi hàm phục vụ đúng 1 màn. Toàn bộ đọc schema `crm` (+ vài con số watcher qua
inbox_store ở tầng route). Khi các lát cắt B1…B11 làm thật, màn nào có nghiệp vụ
riêng sẽ thay các hàm này bằng service + repo chuyên; phần còn lại giữ nguyên.
"""

from app.db.client import get_pg_pool


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
            select id, customer_code, full_name, primary_phone, province, status, created_at
              from crm.customers where {where}
             order by id desc limit %s
            """,
            (*ts, limit),
        ).fetchall()
        total = conn.execute(
            f"select count(*) as n from crm.customers where {where}", ts or None
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


def tasks_groups() -> dict:
    """Màn Công việc (màn 12/26, khung): quá hạn / hôm nay / sắp tới."""
    pool = get_pg_pool()

    def _pick(conn, where: str) -> list[dict]:
        return conn.execute(
            f"""
            select t.id, t.task_type, t.due_at, t.priority, t.status,
                   c.full_name as khach, u.name as nguoi_lam
              from crm.tasks t
              left join crm.customers c on c.id = t.customer_id
              left join crm.users u on u.id = t.assigned_to
             where t.status in ('open','in_progress') and {where}
             order by t.due_at limit 30
            """
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
