"""Truy vấn crm.care_plans / care_plan_steps / care_interactions /
symptom_assessments / no_response_sequences (B9 — FR-100…110).

Chỉ SQL — luật (mốc tính từ ngày bắt đầu THẬT, phiếu bắt buộc trường nào,
chuỗi không phản hồi 4 lần...) nằm ở services/care_service.py.

Danh mục 11 bước (tên, kích hoạt, trường bắt buộc, kênh) KHÔNG hard-code ở
đây — đọc từ crm.ref_codes nhóm `care_step` (seed_danh_muc.py, BRD bảng 18);
7 bộ giá trị phiếu chăm cũng vậy (bảng 19).
"""

import json

from app.db.client import get_pg_pool

# ------------------------------------------------------------ danh mục ref
def buoc_chuan() -> dict[str, dict]:
    """{CS01: {name, kich_hoat, kenh, du_lieu_bat_buoc[], ngoai_le}, …} —
    đọc từ ref_codes.extra (seed_danh_muc.py nhét dict phụ vào cột này)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select code, name, extra from crm.ref_codes "
            "where group_code = 'care_step' and status = 'active'"
        ).fetchall()
    out = {}
    for r in rows:
        extra = r["extra"] if isinstance(r["extra"], dict) else json.loads(r["extra"] or "{}")
        out[r["code"]] = {"name": r["name"], **extra}
    return out


def bo_gia_tri(group_code: str) -> list[str]:
    """1 trong 7 bộ giá trị phiếu chăm (adherence_level, adverse_event…)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select name from crm.ref_codes where group_code = %s "
            "and status = 'active' order by sort_order, id",
            (group_code,),
        ).fetchall()
    return [r["name"] for r in rows]


def ma_hop_le(group_code: str) -> set[str]:
    """Bộ MÃ của một nhóm ref (care_result RS01-12, cskh_state C01-09…)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select code from crm.ref_codes where group_code = %s and status = 'active'",
            (group_code,),
        ).fetchall()
    return {r["code"] for r in rows}


# ------------------------------------------------------------ kế hoạch chăm
_CHON_PLAN = """
    p.*,
    c.full_name       as customer_name,
    c.primary_phone   as customer_phone,
    c.do_not_contact  as do_not_contact,
    u.name            as owner_name,
    o.delivered_at    as delivered_at,
    o.id              as order_id
"""
_TU_PLAN = """
    from crm.care_plans p
    join crm.customers c on c.id = p.customer_id
    left join crm.users u on u.id = p.owner_id
    left join crm.handovers h on h.care_plan_id = p.id
    left join crm.orders o on o.id = h.order_id
"""


def get_plan(plan_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON_PLAN} {_TU_PLAN} where p.id = %s", (plan_id,)
        ).fetchone()


def plan_dang_chay_cua_khach(customer_id: int) -> dict | None:
    """Kế hoạch active MỚI NHẤT của khách — các phiếu CARE-STEP ghi vào đây."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON_PLAN} {_TU_PLAN} "
            "where p.customer_id = %s and p.status = 'active' "
            "order by p.id desc limit 1",
            (customer_id,),
        ).fetchone()


def list_plans(
    *, cskh_state: str = "", owner_id: int | None = None,
    customer_id: int | None = None, status: str = "",
    limit: int = 50, offset: int = 0,
) -> tuple[list[dict], int]:
    dk, ts = ["true"], {}
    if cskh_state:
        dk.append("p.cskh_state = %(st)s")
        ts["st"] = cskh_state
    if owner_id:
        dk.append("p.owner_id = %(ow)s")
        ts["ow"] = owner_id
    if customer_id:
        dk.append("p.customer_id = %(kh)s")
        ts["kh"] = customer_id
    if status:
        dk.append("p.status = %(tt)s")
        ts["tt"] = status
    where = " and ".join(dk)
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"select {_CHON_PLAN} {_TU_PLAN} where {where} "
            "order by p.id desc limit %(l)s offset %(o)s",
            {**ts, "l": limit, "o": offset},
        ).fetchall()
        total = conn.execute(
            f"select count(*) as n {_TU_PLAN} where {where}", ts or None
        ).fetchone()["n"]
    return rows, total


def create_plan(
    *, customer_id: int, customer_treatment_id: int | None = None,
    owner_id: int | None = None, cycle_no: int = 1,
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.care_plans (customer_id, customer_treatment_id, "
            "owner_id, cycle_no) values (%s, %s, %s, %s) returning *",
            (customer_id, customer_treatment_id, owner_id, cycle_no),
        ).fetchone()


def update_plan(plan_id: int, **fields) -> dict | None:
    """Chỉ nhận các cột cho phép — gọi sai tên cột là lỗi lập trình, cứ vỡ."""
    cho_phep = {"cskh_state", "actual_start_date", "started_at", "status",
                "ended_at", "owner_id", "cycle_no"}
    fields = {k: v for k, v in fields.items() if k in cho_phep}
    if not fields:
        return get_plan(plan_id)
    dat = ", ".join(f"{k} = %({k})s" for k in fields)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"update crm.care_plans set {dat} where id = %(id)s returning *",
            {**fields, "id": plan_id},
        ).fetchone()


def dem_theo_state() -> dict[str, int]:
    """Kanban màn 27: đếm kế hoạch ACTIVE theo cột C01-C09."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select cskh_state, count(*) as n from crm.care_plans "
            "where status = 'active' group by cskh_state"
        ).fetchall()
    return {r["cskh_state"]: r["n"] for r in rows}


# ------------------------------------------------------------ mốc chăm
_CHON_MOC = """
    s.*,
    p.customer_id     as customer_id,
    p.owner_id        as owner_id,
    p.cskh_state      as cskh_state,
    p.actual_start_date as actual_start_date,
    p.status          as plan_status,
    c.full_name       as customer_name,
    c.do_not_contact  as do_not_contact,
    u.name            as owner_name
"""
_TU_MOC = """
    from crm.care_plan_steps s
    join crm.care_plans p on p.id = s.care_plan_id
    join crm.customers c on c.id = p.customer_id
    left join crm.users u on u.id = p.owner_id
"""


def get_step(step_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON_MOC} {_TU_MOC} where s.id = %s", (step_id,)
        ).fetchone()


def list_steps(plan_id: int) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON_MOC} {_TU_MOC} where s.care_plan_id = %s "
            "order by s.planned_at nulls last, s.id",
            (plan_id,),
        ).fetchall()


def moc_theo_ma(plan_id: int, step_code: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON_MOC} {_TU_MOC} "
            "where s.care_plan_id = %s and s.step_code = %s limit 1",
            (plan_id, step_code),
        ).fetchone()


def them_moc(plan_id: int, step_code: str, planned_at) -> dict | None:
    """Idempotent nhờ uq_care_plan_steps_ma — mốc đã có thì trả None
    (sinh lại mốc KHÔNG đè lịch người dùng đã dời)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.care_plan_steps (care_plan_id, step_code, planned_at) "
            "values (%s, %s, %s) on conflict do nothing returning *",
            (plan_id, step_code, planned_at),
        ).fetchone()


def cap_nhat_moc(step_id: int, **fields) -> dict | None:
    cho_phep = {"status", "planned_at", "completed_at", "completed_by",
                "result_code", "note", "data"}
    fields = {k: v for k, v in fields.items() if k in cho_phep}
    if "data" in fields and not isinstance(fields["data"], str):
        fields["data"] = json.dumps(fields["data"], ensure_ascii=False)
    dat = ", ".join(f"{k} = %({k})s" for k in fields)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"update crm.care_plan_steps set {dat} where id = %(id)s returning *",
            {**fields, "id": step_id},
        ).fetchone()


def moc_den_han(*, qua_han: bool, owner_id: int | None = None) -> list[dict]:
    """CARE-009/010: mốc hôm nay (planned hôm nay, chưa xong) / quá hạn."""
    loc_ngay = (
        "s.planned_at < date_trunc('day', now())" if qua_han
        else "s.planned_at::date = current_date"
    )
    loc_nguoi = "and p.owner_id = %(ow)s" if owner_id else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON_MOC} {_TU_MOC} "
            f"where s.status in ('pending','due') and {loc_ngay} {loc_nguoi} "
            "  and p.status = 'active' and not c.do_not_contact "
            "order by s.planned_at limit 200",
            {"ow": owner_id},
        ).fetchall()


def danh_dau_due() -> int:
    """Worker: pending → due khi tới lịch (khách ngừng liên hệ thì thôi)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            """
            update crm.care_plan_steps s set status = 'due'
              from crm.care_plans p, crm.customers c
             where p.id = s.care_plan_id and c.id = p.customer_id
               and s.status = 'pending' and s.planned_at <= now()
               and p.status = 'active' and not c.do_not_contact
            """
        )
        return cur.rowcount or 0


def moc_can_tao_viec() -> list[dict]:
    """Mốc ĐANG due, plan có người phụ trách, CHƯA có task đang mở gắn vào —
    worker tạo việc 'cham_soc' nhắc đúng người (idempotent nhờ điều kiện này)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select {_CHON_MOC} {_TU_MOC}
             where s.status = 'due' and p.status = 'active'
               and p.owner_id is not null and not c.do_not_contact
               and not exists (
                   select 1 from crm.tasks t
                    where t.related_type = 'care_plan_step' and t.related_id = s.id
                      and t.status in ('open','in_progress'))
             limit 100
            """
        ).fetchall()


# ------------------------------------------------------------ tương tác + đánh giá
def tao_interaction(
    *, step_id: int | None, customer_id: int, user_id: int | None,
    channel: str | None, contacted: bool | None, summary: str | None,
    next_action_at=None,
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.care_interactions (care_plan_step_id, customer_id, "
            "user_id, channel, contacted, summary, next_action_at) "
            "values (%s, %s, %s, %s, %s, %s, %s) returning *",
            (step_id, customer_id, user_id, channel, contacted, summary,
             next_action_at),
        ).fetchone()


def get_interaction(interaction_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select i.*, c.full_name as customer_name from crm.care_interactions i "
            "join crm.customers c on c.id = i.customer_id where i.id = %s",
            (interaction_id,),
        ).fetchone()


def dem_lan_khong_ket_noi(step_id: int) -> int:
    """CS01 ngoại lệ FR-100: 'gọi 3 lần không được → báo Sale và quản lý'."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select count(*) as n from crm.care_interactions "
            "where care_plan_step_id = %s and contacted = false",
            (step_id,),
        ).fetchone()["n"]


def tao_assessment(
    *, interaction_id: int, symptom_id: int,
    before_score, current_score,
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.symptom_assessments (care_interaction_id, symptom_id, "
            "before_score, current_score) values (%s, %s, %s, %s) returning *",
            (interaction_id, symptom_id, before_score, current_score),
        ).fetchone()


def diem_nen_cua_khach(customer_id: int) -> dict[int, float]:
    """Điểm B5 khai ban đầu (customer_symptoms.severity) — mốc 'trước' mặc định."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select symptom_id, severity from crm.customer_symptoms "
            "where customer_id = %s and severity is not null",
            (customer_id,),
        ).fetchall()
    return {r["symptom_id"]: float(r["severity"]) for r in rows}


def assessments_cua_khach(customer_id: int) -> list[dict]:
    """ASSESSMENT-002: lịch sử điểm theo thời gian, mới nhất trước."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select a.*, sy.name as symptom_name, i.created_at as assessed_at,
                   s.step_code
              from crm.symptom_assessments a
              join crm.care_interactions i on i.id = a.care_interaction_id
              join crm.symptoms sy on sy.id = a.symptom_id
              left join crm.care_plan_steps s on s.id = i.care_plan_step_id
             where i.customer_id = %s
             order by a.id desc limit 200
            """,
            (customer_id,),
        ).fetchall()


def tien_trien(customer_id: int) -> list[dict]:
    """ASSESSMENT-003: mỗi triệu chứng — điểm nền B5 · điểm mới nhất · thay đổi."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select sy.id as symptom_id, sy.name as symptom_name,
                   cs.severity                as baseline,
                   moi.current_score          as latest,
                   moi.assessed_at
              from crm.customer_symptoms cs
              join crm.symptoms sy on sy.id = cs.symptom_id
              left join lateral (
                    select a.current_score, i.created_at as assessed_at
                      from crm.symptom_assessments a
                      join crm.care_interactions i on i.id = a.care_interaction_id
                     where i.customer_id = cs.customer_id
                       and a.symptom_id = cs.symptom_id
                     order by a.id desc limit 1
              ) moi on true
             where cs.customer_id = %s
             order by sy.name
            """,
            (customer_id,),
        ).fetchall()


# ------------------------------------------------------------ chuỗi không phản hồi
def chuoi_dang_chay(customer_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.no_response_sequences "
            "where customer_id = %s and status = 'active'",
            (customer_id,),
        ).fetchone()


def tao_chuoi(*, customer_id: int, step_id: int | None, started_by: int | None) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.no_response_sequences (customer_id, care_plan_step_id, "
            "started_by) values (%s, %s, %s) returning *",
            (customer_id, step_id, started_by),
        ).fetchone()


def get_chuoi(sequence_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        seq = conn.execute(
            "select q.*, c.full_name as customer_name "
            "from crm.no_response_sequences q "
            "join crm.customers c on c.id = q.customer_id where q.id = %s",
            (sequence_id,),
        ).fetchone()
        if seq:
            seq["attempts"] = conn.execute(
                "select * from crm.no_response_attempts where sequence_id = %s "
                "order by attempt_no",
                (sequence_id,),
            ).fetchall()
    return seq


def them_lan_cham(
    *, sequence_id: int, attempt_no: int, channel: str,
    result: str | None, note: str | None, attempted_by: int | None,
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.no_response_attempts (sequence_id, attempt_no, "
            "channel, result, note, attempted_by) "
            "values (%s, %s, %s, %s, %s, %s) returning *",
            (sequence_id, attempt_no, channel, result, note, attempted_by),
        ).fetchone()


def dong_chuoi(
    sequence_id: int, *, outcome: str, close_reason: str | None,
    closed_by: int | None,
) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.no_response_sequences set status = 'closed', outcome = %s, "
            "close_reason = %s, closed_by = %s, closed_at = now() "
            "where id = %s returning *",
            (outcome, close_reason, closed_by, sequence_id),
        ).fetchone()


# ------------------------------------------------------------ khách + mua lại
def set_do_not_contact(customer_id: int, *, flag: bool, reason: str | None) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.customers set do_not_contact = %s, "
            "do_not_contact_at = case when %s then now() else null end, "
            "do_not_contact_reason = %s where id = %s",
            (flag, flag, reason, customer_id),
        )


def get_customer(customer_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select id, full_name, do_not_contact, safety_flag from crm.customers "
            "where id = %s and status <> 'deleted'",
            (customer_id,),
        ).fetchone()


def co_hoi_dang_mo(customer_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.repurchase_opportunities "
            "where customer_id = %s and stage not in ('won','lost') "
            "order by id desc limit 1",
            (customer_id,),
        ).fetchone()


def tao_co_hoi_mua_lai(
    *, customer_id: int, current_treatment_id: int | None,
    owner_id: int | None, expected_close_date, expected_value,
) -> dict:
    """AU08 — CS07 tạo cơ hội; vòng đời cơ hội (pipeline mua lại) là việc B10."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.repurchase_opportunities (customer_id, "
            "current_treatment_id, owner_id, expected_close_date, expected_value) "
            "values (%s, %s, %s, %s, %s) returning *",
            (customer_id, current_treatment_id, owner_id, expected_close_date,
             expected_value),
        ).fetchone()


def cap_nhat_co_hoi(opportunity_id: int, *, stage: str, lost_reason_id=None) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.repurchase_opportunities set stage = %s, "
            "lost_reason_id = coalesce(%s, lost_reason_id) where id = %s",
            (stage, lost_reason_id, opportunity_id),
        )
