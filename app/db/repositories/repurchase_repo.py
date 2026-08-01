"""Truy vấn crm.repurchase_opportunities + reactivation_* (B10 — FR-120…123).

Chỉ SQL — luật (9 trạng thái hiển thị suy từ stage + ngày, công thức ngày hết,
ngưỡng khách ngủ 30/60/90/180) nằm ở services/repurchase_service.py.
"""

from app.db.client import get_pg_pool

_CHON = """
    r.*,
    c.full_name        as customer_name,
    c.primary_phone    as customer_phone,
    c.do_not_contact   as do_not_contact,
    u.name             as owner_name,
    tt_cu.name         as current_treatment_name,
    tt_moi.name        as next_template_name
"""
_TU = """
    from crm.repurchase_opportunities r
    join crm.customers c on c.id = r.customer_id
    left join crm.users u on u.id = r.owner_id
    left join crm.customer_treatments ct on ct.id = r.current_treatment_id
    left join crm.treatment_templates tt_cu on tt_cu.id = ct.template_id
    left join crm.treatment_templates tt_moi on tt_moi.id = r.next_template_id
"""


def get(opportunity_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON} {_TU} where r.id = %s", (opportunity_id,)
        ).fetchone()


def list_opps(
    *, stage: str = "", owner_id: int | None = None,
    customer_id: int | None = None, dang_mo: bool | None = None,
    limit: int = 50, offset: int = 0,
) -> tuple[list[dict], int]:
    dk, ts = ["true"], {}
    if stage:
        dk.append("r.stage = %(st)s")
        ts["st"] = stage
    if owner_id:
        dk.append("r.owner_id = %(ow)s")
        ts["ow"] = owner_id
    if customer_id:
        dk.append("r.customer_id = %(kh)s")
        ts["kh"] = customer_id
    if dang_mo is True:
        dk.append("r.stage not in ('won','lost')")
    where = " and ".join(dk)
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"select {_CHON} {_TU} where {where} "
            "order by r.expected_close_date nulls last, r.id desc "
            "limit %(l)s offset %(o)s",
            {**ts, "l": limit, "o": offset},
        ).fetchall()
        total = conn.execute(
            f"select count(*) as n {_TU} where {where}", ts or None
        ).fetchone()["n"]
    return rows, total


def create(data: dict) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.repurchase_opportunities
                   (customer_id, current_treatment_id, next_template_id,
                    owner_id, expected_close_date, expected_value, readiness,
                    stage_moved_at)
            values (%(customer_id)s, %(current_treatment_id)s,
                    %(next_template_id)s, %(owner_id)s,
                    %(expected_close_date)s, %(expected_value)s,
                    %(readiness)s, now())
            returning *
            """,
            {k: data.get(k) for k in
             ("customer_id", "current_treatment_id", "next_template_id",
              "owner_id", "expected_close_date", "expected_value", "readiness")},
        ).fetchone()


def update(opportunity_id: int, **fields) -> dict | None:
    cho_phep = {"next_template_id", "expected_close_date", "expected_value",
                "readiness", "owner_id", "current_treatment_id",
                "lost_reason_id", "lost_note"}
    fields = {k: v for k, v in fields.items() if k in cho_phep}
    if not fields:
        return get(opportunity_id)
    dat = ", ".join(f"{k} = %({k})s" for k in fields)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"update crm.repurchase_opportunities set {dat} "
            "where id = %(id)s returning *",
            {**fields, "id": opportunity_id},
        ).fetchone()


def move_stage(opportunity_id: int, stage: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.repurchase_opportunities set stage = %s, "
            "stage_moved_at = now() where id = %s returning *",
            (stage, opportunity_id),
        ).fetchone()


def sap_den_han(trong_ngay: int, owner_id: int | None = None) -> list[dict]:
    """REPURCHASE-008 — cơ hội MỞ có ngày hết trong `trong_ngay` ngày tới."""
    loc = "and r.owner_id = %(ow)s" if owner_id else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select {_CHON} {_TU}
             where r.stage not in ('won','lost')
               and r.expected_close_date is not null
               and r.expected_close_date between current_date
                   and current_date + %(n)s {loc}
             order by r.expected_close_date limit 200
            """,
            {"n": trong_ngay, "ow": owner_id},
        ).fetchall()


def qua_han(owner_id: int | None = None) -> list[dict]:
    """REPURCHASE-009 — cơ hội MỞ đã trượt ngày dự kiến."""
    loc = "and r.owner_id = %(ow)s" if owner_id else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select {_CHON} {_TU}
             where r.stage not in ('won','lost')
               and r.expected_close_date < current_date {loc}
             order by r.expected_close_date limit 200
            """,
            {"ow": owner_id},
        ).fetchall()


def dem_theo_stage() -> dict[str, int]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select stage, count(*) as n from crm.repurchase_opportunities "
            "group by stage"
        ).fetchall()
    return {r["stage"]: r["n"] for r in rows}


# ------------------------------------------------------------ FR-120 nguồn số
def lieu_trinh(customer_treatment_id: int) -> dict | None:
    """Liệu trình + số ngày mẫu + ngày bắt đầu thật (care plan B9) + ngày giao."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select ct.*, tt.duration_days, tt.name as template_name,
                   o.delivered_at,
                   p.actual_start_date as care_start_date
              from crm.customer_treatments ct
              left join crm.treatment_templates tt on tt.id = ct.template_id
              left join crm.orders o on o.id = ct.order_id
              left join lateral (
                    select actual_start_date from crm.care_plans
                     where customer_treatment_id = ct.id
                       and actual_start_date is not null
                     order by id desc limit 1
              ) p on true
             where ct.id = %s
            """,
            (customer_treatment_id,),
        ).fetchone()


def adherence_gan_nhat(customer_id: int) -> str | None:
    """Mức tuân thủ mới nhất từ phiếu chăm B9 (CS04/CS05/CS10) — FR-120
    'điều chỉnh theo dùng thiếu liều'."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            """
            select s.data->>'adherence_level' as muc
              from crm.care_plan_steps s
              join crm.care_plans p on p.id = s.care_plan_id
             where p.customer_id = %s and s.data ? 'adherence_level'
             order by s.completed_at desc nulls last, s.id desc limit 1
            """,
            (customer_id,),
        ).fetchone()
    return r["muc"] if r else None


def luu_ngay_het(customer_treatment_id: int, ngay_het) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.customer_treatments set expected_end_date = %s "
            "where id = %s",
            (ngay_het, customer_treatment_id),
        )


def dong_bo_ngay_het_sang_co_hoi(customer_id: int, ngay_het) -> None:
    """Cơ hội đang MỞ của khách ăn theo ngày hết mới tính lại."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.repurchase_opportunities set expected_close_date = %s "
            "where customer_id = %s and stage not in ('won','lost')",
            (ngay_het, customer_id),
        )


def ly_do_chuan(code: str) -> dict | None:
    """9 lý do chưa mua BRD nằm ở lead_reasons (seed_danh_muc) — dùng chung."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select id, code, name from crm.lead_reasons where code = %s",
            (code,),
        ).fetchone()


# ------------------------------------------------------------ FR-123 khách ngủ
def khach_ngu(tu_ngay: int, *, gia_tri_tu=None, limit: int = 500) -> list[dict]:
    """Khách từng mua (có đơn giao TC) mà im ắng >= `tu_ngay` ngày; loại khách
    đã yêu cầu ngừng liên hệ. `gia_tri_tu` — lọc theo tổng đã mua (FR-123)."""
    loc_gia_tri = "and k.tong_mua >= %(gt)s" if gia_tri_tu is not None else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select c.id, c.full_name, c.primary_phone, k.lan_cuoi, k.tong_mua,
                   k.so_don,
                   (current_date - k.lan_cuoi::date)         as ngay_ngu,
                   cd.campaign_id                            as campaign_id
              from crm.customers c
              join lateral (
                    select max(o.delivered_at) as lan_cuoi,
                           coalesce(sum(o.total_amount)
                                filter (where o.status = 'delivered'), 0) as tong_mua,
                           count(*) filter (where o.status = 'delivered') as so_don
                      from crm.orders o where o.customer_id = c.id
              ) k on true
              left join lateral (
                    select m.campaign_id from crm.reactivation_members m
                      join crm.reactivation_campaigns cp on cp.id = m.campaign_id
                     where m.customer_id = c.id and cp.status = 'running'
                     order by m.id desc limit 1
              ) cd on true
             where c.status <> 'deleted' and not c.do_not_contact
               and k.lan_cuoi is not null
               and k.lan_cuoi < now() - make_interval(days => %(n)s)
               {loc_gia_tri}
             order by k.lan_cuoi
             limit %(l)s
            """,
            {"n": tu_ngay, "gt": gia_tri_tu, "l": limit},
        ).fetchall()


# ------------------------------------------------------------ chiến dịch tái kích hoạt
def tao_chien_dich(*, name: str, segment_rule: dict) -> dict:
    import json

    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.reactivation_campaigns (name, segment_rule_json, "
            "status, start_at) values (%s, %s, 'running', now()) returning *",
            (name, json.dumps(segment_rule, ensure_ascii=False)),
        ).fetchone()


def get_chien_dich(campaign_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.reactivation_campaigns where id = %s",
            (campaign_id,),
        ).fetchone()


def them_thanh_vien(campaign_id: int, customer_id: int,
                    assigned_to: int | None) -> dict | None:
    """1 khách 1 dòng mỗi chiến dịch (unique) — trùng thì bỏ qua."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.reactivation_members (campaign_id, customer_id, "
            "assigned_to) values (%s, %s, %s) on conflict do nothing returning *",
            (campaign_id, customer_id, assigned_to),
        ).fetchone()


def bao_cao_chien_dich() -> list[dict]:
    """FR-123 'đo doanh thu tái kích hoạt': doanh thu = đơn giao TC của thành
    viên TẠO SAU khi khách được đưa vào chiến dịch."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select cp.id, cp.name, cp.status, cp.start_at,
                   count(m.id)                                       as so_khach,
                   count(m.id) filter (where m.status = 'converted') as chuyen_doi,
                   coalesce(sum(dt.tien), 0)                         as doanh_thu
              from crm.reactivation_campaigns cp
              left join crm.reactivation_members m on m.campaign_id = cp.id
              left join lateral (
                    select sum(o.total_amount) as tien
                      from crm.orders o
                     where o.customer_id = m.customer_id
                       and o.status = 'delivered'
                       and o.created_at >= m.created_at
              ) dt on true
             group by cp.id
             order by cp.id desc
            """
        ).fetchall()


def danh_dau_chuyen_doi(customer_id: int) -> int:
    """Khách trong chiến dịch RUNNING vừa có đơn mới → member 'converted'
    (đo tự động, không chờ tay). Trả số dòng đổi."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            """
            update crm.reactivation_members m set status = 'converted',
                   result = coalesce(m.result, 'co don moi')
              from crm.reactivation_campaigns cp
             where cp.id = m.campaign_id and cp.status = 'running'
               and m.customer_id = %s and m.status <> 'converted'
            """,
            (customer_id,),
        )
        return cur.rowcount or 0
