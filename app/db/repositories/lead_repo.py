"""Truy vấn crm.leads + pipeline (B3 — docs/B3-LEAD-PIPELINE.md).

Chỉ SQL, không luật nghiệp vụ — luật nằm ở app/services/lead_service.py.
Mọi câu đều ghi rõ tiền tố `crm.` (tránh trúng nhầm watcher.customers).
"""

from datetime import datetime

from app.db.client import get_pg_pool


# ------------------------------------------------------------------ pipeline

def get_pipeline_by_name(name: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.pipelines where name = %s", (name,)
        ).fetchone()


def get_pipeline(pipeline_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.pipelines where id = %s", (pipeline_id,)
        ).fetchone()


def list_pipelines() -> list[dict]:
    """PIPELINE-001 — kèm số giai đoạn + số lead đang mở để màn cấu hình nhìn nhanh."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select p.*,
                   (select count(*) from crm.pipeline_stages s where s.pipeline_id = p.id) as so_giai_doan,
                   (select count(*) from crm.leads l where l.pipeline_id = p.id and l.closed_at is null) as so_lead_mo
            from crm.pipelines p
            order by p.id
            """,
        ).fetchall()


def create_pipeline(name: str, type_: str | None) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.pipelines (name, type) values (%s, %s) returning *",
            (name, type_),
        ).fetchone()


def list_stages(pipeline_id: int) -> list[dict]:
    """PIPELINE-003 — kèm số lead đang đứng ở từng giai đoạn (đếm cho Kanban)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select s.*,
                   (select count(*) from crm.leads l where l.stage_id = s.id) as so_lead
            from crm.pipeline_stages s
            where s.pipeline_id = %s
            order by s.sort_order
            """,
            (pipeline_id,),
        ).fetchall()


def upsert_stage(
    *, pipeline_id: int, code: str, name: str, sort_order: int, is_closed: bool
) -> dict:
    """PIPELINE-004 — thêm/sửa theo (pipeline_id, code); KHÔNG xoá giai đoạn
    (lead cũ còn trỏ vào — muốn bỏ thì đổi tên/đẩy sort_order, quyết sau)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.pipeline_stages (pipeline_id, code, name, sort_order, is_closed)
            values (%s, %s, %s, %s, %s)
            on conflict (pipeline_id, code) do update
                set name = excluded.name, sort_order = excluded.sort_order,
                    is_closed = excluded.is_closed
            returning *
            """,
            (pipeline_id, code, name, sort_order, is_closed),
        ).fetchone()


def get_stage(stage_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.pipeline_stages where id = %s", (stage_id,)
        ).fetchone()


def get_stage_by_code(pipeline_id: int, code: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.pipeline_stages where pipeline_id = %s and code = %s",
            (pipeline_id, code),
        ).fetchone()


def first_stage(pipeline_id: int) -> dict | None:
    """Giai đoạn mở đầu = sort_order nhỏ nhất, không phải giai đoạn kết thúc."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.pipeline_stages "
            "where pipeline_id = %s and not is_closed "
            "order by sort_order limit 1",
            (pipeline_id,),
        ).fetchone()


# ------------------------------------------------------------------ lead CRUD

def get_lead(lead_id: int) -> dict | None:
    """Lead kèm mã/tên giai đoạn — service cần stage code để áp luật."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select l.*, s.code as stage_code, s.name as stage_name, s.is_closed
            from crm.leads l
            join crm.pipeline_stages s on s.id = l.stage_id
            where l.id = %s
            """,
            (lead_id,),
        ).fetchone()


def create_lead(
    *,
    customer_id: int,
    pipeline_id: int,
    stage_id: int,
    owner_id: int | None,
    source: str | None,
    temperature: str | None,
    priority: str,
    sla_due_at: datetime | None,
) -> dict:
    """Tạo lead + dòng lịch sử đầu tiên (from_stage rỗng) trong 1 transaction."""
    pool = get_pg_pool()
    with pool.connection() as conn, conn.transaction():
        lead = conn.execute(
            """
            insert into crm.leads (customer_id, pipeline_id, stage_id, owner_id,
                                   source, temperature, priority, sla_due_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (customer_id, pipeline_id, stage_id, owner_id,
             source, temperature, priority, sla_due_at),
        ).fetchone()
        conn.execute(
            "insert into crm.lead_stage_history (lead_id, to_stage_id, changed_by) "
            "values (%s, %s, %s)",
            (lead["id"], stage_id, owner_id),
        )
        return lead


def move_stage(
    *,
    lead_id: int,
    from_stage_id: int,
    to_stage_id: int,
    changed_by: int | None,
    reason: str | None,
    note: str | None,
    closed: bool,
) -> None:
    """Đổi giai đoạn + ghi lịch sử — 1 transaction, không bao giờ lệch nhau (FR-041)."""
    pool = get_pg_pool()
    with pool.connection() as conn, conn.transaction():
        conn.execute(
            """
            update crm.leads
               set stage_id = %s, stage_entered_at = now(),
                   closed_at = case when %s then now() else null end
             where id = %s
            """,
            (to_stage_id, closed, lead_id),
        )
        conn.execute(
            """
            insert into crm.lead_stage_history
                   (lead_id, from_stage_id, to_stage_id, changed_by, reason, note)
            values (%s, %s, %s, %s, %s, %s)
            """,
            (lead_id, from_stage_id, to_stage_id, changed_by, reason, note),
        )


def set_owner(lead_id: int, owner_id: int | None, sla_due_at: datetime | None) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.leads set owner_id = %s, sla_due_at = %s where id = %s",
            (owner_id, sla_due_at, lead_id),
        )


def set_next_action(lead_id: int, next_action_at: datetime | None) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.leads set next_action_at = %s where id = %s",
            (next_action_at, lead_id),
        )


def set_first_contact(lead_id: int) -> None:
    """Chỉ ghi lần ĐẦU — gọi lặp không đè mốc cũ (FR-042 đo tương tác đầu)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.leads set first_contact_at = now() "
            "where id = %s and first_contact_at is null",
            (lead_id,),
        )


# ------------------------------------------------------------------ luật hỗ trợ

def customer_has_order(customer_id: int) -> bool:
    """FR-040: chuyển 'Đã chốt' phải có đơn (đơn nháp cũng tính — vừa lên đơn)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "select 1 from crm.orders where customer_id = %s "
            "and status <> 'cancelled' limit 1",
            (customer_id,),
        ).fetchone()
        return row is not None


def count_lost_reasons(lead_id: int) -> int:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select count(*) as n from crm.lead_lost_reasons where lead_id = %s",
            (lead_id,),
        ).fetchone()["n"]


def add_lost_reason(
    *, lead_id: int, lost_reason_id: int, note: str | None,
    evidence_type: str | None = None, evidence_id: int | None = None,
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.lead_lost_reasons
                   (lead_id, lost_reason_id, note, evidence_type, evidence_id)
            values (%s, %s, %s, %s, %s) returning *
            """,
            (lead_id, lost_reason_id, note, evidence_type, evidence_id),
        ).fetchone()


def pick_sale_round_robin() -> dict | None:
    """FR-030 kiểu 'vòng tròn theo tải': Sale active đang giữ ÍT lead mở nhất.

    Mới hỗ trợ 1 kiểu chia; các kiểu theo Page/ca/khu vực/chiến dịch chờ dữ liệu
    của B1/B2 (xem mô tả B3 mục 'hoãn').
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select u.id, u.name, count(l.id) as dang_giu
            from crm.users u
            join crm.roles r on r.id = u.role_id and r.name = 'Sale'
            left join crm.leads l on l.owner_id = u.id and l.closed_at is null
            where u.status = 'active'
            group by u.id, u.name
            order by count(l.id) asc, u.id asc
            limit 1
            """,
        ).fetchone()


# ------------------------------------------------------------------ danh sách

def stage_history(lead_id: int) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select h.*, sf.name as from_stage_name, st.name as to_stage_name,
                   u.name as changed_by_name
            from crm.lead_stage_history h
            left join crm.pipeline_stages sf on sf.id = h.from_stage_id
            join crm.pipeline_stages st on st.id = h.to_stage_id
            left join crm.users u on u.id = h.changed_by
            where h.lead_id = %s
            order by h.changed_at desc
            """,
            (lead_id,),
        ).fetchall()


def list_leads(
    *,
    customer_id: int | None = None,
    owner_id: int | None = None,
    pipeline_id: int | None = None,
    stage_id: int | None = None,
    temperature: str | None = None,
    trang_thai: str = "open",   # open | closed | all
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """LEAD-001 — danh sách kèm tên khách/giai đoạn/người giữ, lọc như màn 11.

    Trả (rows, total) cho bao_trang của A3.
    """
    dieu_kien = ["true"]
    thamso: list = []
    if customer_id is not None:
        dieu_kien.append("l.customer_id = %s"); thamso.append(customer_id)
    if owner_id is not None:
        dieu_kien.append("l.owner_id = %s"); thamso.append(owner_id)
    if pipeline_id is not None:
        dieu_kien.append("l.pipeline_id = %s"); thamso.append(pipeline_id)
    if stage_id is not None:
        dieu_kien.append("l.stage_id = %s"); thamso.append(stage_id)
    if temperature:
        dieu_kien.append("l.temperature = %s"); thamso.append(temperature)
    if trang_thai == "open":
        dieu_kien.append("l.closed_at is null")
    elif trang_thai == "closed":
        dieu_kien.append("l.closed_at is not null")
    where = " and ".join(dieu_kien)

    pool = get_pg_pool()
    with pool.connection() as conn:
        total = conn.execute(
            f"select count(*) as n from crm.leads l where {where}", thamso
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            select l.*, s.code as stage_code, s.name as stage_name, s.is_closed,
                   c.full_name as customer_name, u.name as owner_name
            from crm.leads l
            join crm.pipeline_stages s on s.id = l.stage_id
            join crm.customers c on c.id = l.customer_id
            left join crm.users u on u.id = l.owner_id
            where {where}
            order by l.created_at desc
            limit %s offset %s
            """,
            [*thamso, limit, offset],
        ).fetchall()
        return rows, total


def update_lead(lead_id: int, fields: dict) -> dict | None:
    """LEAD-004 — chỉ nhận cột đã lọc trắng ở service (source/temperature/...)."""
    if not fields:
        return get_lead(lead_id)
    dat = ", ".join(f"{cot} = %s" for cot in fields)
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            f"update crm.leads set {dat} where id = %s",
            [*fields.values(), lead_id],
        )
    return get_lead(lead_id)


def list_queue(limit: int = 50) -> list[dict]:
    """FR-032: hàng đợi = lead chưa có người nhận, chưa đóng — cũ nhất trước."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.leads "
            "where owner_id is null and closed_at is null "
            "order by created_at limit %s",
            (limit,),
        ).fetchall()


def list_overdue(limit: int = 50) -> list[dict]:
    """LEAD-008: quá hạn SLA mà chưa có tương tác đầu, chưa đóng."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.leads "
            "where closed_at is null and first_contact_at is null "
            "and sla_due_at is not null and sla_due_at < now() "
            "order by sla_due_at limit %s",
            (limit,),
        ).fetchall()


def list_hot(limit: int = 50) -> list[dict]:
    """LEAD-009: lead nóng chưa đóng, việc gần hạn trước."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.leads "
            "where temperature = 'nong' and closed_at is null "
            "order by next_action_at nulls last limit %s",
            (limit,),
        ).fetchall()
