"""Truy vấn crm.customers + identities + tags + assignments (B1).

Chỉ SQL — luật (chống trùng, gộp, phân công) nằm ở services/customer_service.py.
Mọi câu ghi rõ `crm.` (crm.customers ≠ watcher.customers — xem .env).

Quy ước "khách sống" = deleted_at is null AND status <> 'merged'.
"""

import json

from app.db.client import get_pg_pool

_SONG = "c.deleted_at is null and c.status <> 'merged'"


# ------------------------------------------------------------------ CRUD

def get_customer(customer_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select c.*,
                   (select json_agg(json_build_object(
                            'id', t.id, 'name', t.name, 'type', t.type))
                      from crm.customer_tags ct
                      join crm.tags t on t.id = ct.tag_id
                     where ct.customer_id = c.id)              as tags,
                   (select json_agg(json_build_object(
                            'user_id', a.user_id, 'name', u.name,
                            'assignment_type', a.assignment_type))
                      from crm.customer_assignments a
                      join crm.users u on u.id = a.user_id
                     where a.customer_id = c.id and a.end_at is null) as nguoi_phu_trach
            from crm.customers c
            where c.id = %s
            """,
            (customer_id,),
        ).fetchone()


def create_customer(fields: dict) -> dict:
    cot = list(fields)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"insert into crm.customers ({', '.join(cot)}) "
            f"values ({', '.join(['%s'] * len(cot))}) returning *",
            list(fields.values()),
        ).fetchone()


def update_customer(customer_id: int, fields: dict) -> dict | None:
    if fields:
        dat = ", ".join(f"{c} = %s" for c in fields)
        pool = get_pg_pool()
        with pool.connection() as conn:
            conn.execute(
                f"update crm.customers set {dat} where id = %s",
                [*fields.values(), customer_id],
            )
    return get_customer(customer_id)


def soft_delete(customer_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.customers set deleted_at = now() where id = %s",
            (customer_id,),
        )


def list_customers(
    *,
    keyword: str = "",
    status: str | None = None,
    source: str | None = None,
    owner_id: int | None = None,          # đang phụ trách (mọi vai)
    assignment_type: str | None = None,   # sale / cskh / chuyen_mon
    tag_id: int | None = None,
    has_order: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """CUSTOMER-001 — bộ lọc màn 8 (phần dữ liệu đã tồn tại ở lát này)."""
    dk = [_SONG]
    ts: list = []
    if keyword:
        dk.append("(c.full_name ilike %s or c.primary_phone like %s or c.customer_code ilike %s)")
        ts += [f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"]
    if status:
        dk.append("c.status = %s"); ts.append(status)
    if source:
        dk.append("c.source = %s"); ts.append(source)
    if owner_id is not None:
        sub = "select 1 from crm.customer_assignments a where a.customer_id = c.id and a.user_id = %s and a.end_at is null"
        ts.append(owner_id)
        if assignment_type:
            sub += " and a.assignment_type = %s"; ts.append(assignment_type)
        dk.append(f"exists ({sub})")
    if tag_id is not None:
        dk.append("exists (select 1 from crm.customer_tags ct where ct.customer_id = c.id and ct.tag_id = %s)")
        ts.append(tag_id)
    if has_order is True:
        dk.append("exists (select 1 from crm.orders o where o.customer_id = c.id and o.status <> 'cancelled')")
    elif has_order is False:
        dk.append("not exists (select 1 from crm.orders o where o.customer_id = c.id and o.status <> 'cancelled')")
    where = " and ".join(dk)

    pool = get_pg_pool()
    with pool.connection() as conn:
        total = conn.execute(
            f"select count(*) as n from crm.customers c where {where}", ts
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            select c.*,
                   (select u.name from crm.customer_assignments a
                     join crm.users u on u.id = a.user_id
                    where a.customer_id = c.id and a.assignment_type = 'sale'
                      and a.end_at is null limit 1) as sale_phu_trach,
                   (select u.name from crm.customer_assignments a
                     join crm.users u on u.id = a.user_id
                    where a.customer_id = c.id and a.assignment_type = 'cskh'
                      and a.end_at is null limit 1) as cskh_phu_trach
            from crm.customers c
            where {where}
            order by c.created_at desc
            limit %s offset %s
            """,
            [*ts, limit, offset],
        ).fetchall()
        return rows, total


# ------------------------------------------------------------------ chống trùng (FR-011)

def find_by_external_id(platform: str, external_customer_id: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select c.* from crm.customer_identities i
            join crm.customers c on c.id = i.customer_id
            where i.platform = %s and i.external_customer_id = %s and {_SONG}
            limit 1
            """,
            (platform, external_customer_id),
        ).fetchone()


def find_by_psid(page_id: int, psid: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select c.* from crm.customer_identities i
            join crm.customers c on c.id = i.customer_id
            where i.page_id = %s and i.psid = %s and {_SONG}
            limit 1
            """,
            (page_id, psid),
        ).fetchone()


def find_by_phone(phone: str) -> list[dict]:
    """Trả DANH SÁCH — số nhà dùng chung nên 1 số có thể ra nhiều khách."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select c.* from crm.customers c where c.primary_phone = %s and {_SONG}",
            (phone,),
        ).fetchall()


def find_by_conversation(page_id: int, external_conversation_id: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select c.* from crm.conversations v
            join crm.customers c on c.id = v.customer_id
            where v.page_id = %s and v.external_conversation_id = %s and {_SONG}
            limit 1
            """,
            (page_id, external_conversation_id),
        ).fetchone()


def find_duplicate_groups(limit: int = 50) -> list[dict]:
    """CUSTOMER-006 — nhóm nghi trùng theo SĐT chuẩn hoá (khách sống có >1 hồ sơ)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select c.primary_phone,
                   json_agg(json_build_object(
                       'id', c.id, 'full_name', c.full_name, 'status', c.status,
                       'created_at', c.created_at) order by c.id) as members
            from crm.customers c
            where c.primary_phone is not null and {_SONG}
            group by c.primary_phone
            having count(*) > 1
            order by count(*) desc
            limit %s
            """,
            (limit,),
        ).fetchall()


# ------------------------------------------------------------------ identities

def list_identities(customer_id: int) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.customer_identities where customer_id = %s order by id",
            (customer_id,),
        ).fetchall()


def add_identity(
    *, customer_id: int, platform: str | None,
    external_customer_id: str | None, psid: str | None, page_id: int | None,
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.customer_identities
                   (customer_id, platform, external_customer_id, psid, page_id)
            values (%s, %s, %s, %s, %s) returning *
            """,
            (customer_id, platform, external_customer_id, psid, page_id),
        ).fetchone()


# ------------------------------------------------------------------ conversations (B2)

def upsert_conversation(
    *, customer_id: int, page_id: int, external_conversation_id: str,
    last_message_at: str | None,
    source: str = "pancake",
    external_updated_at: str | None = None,
    assignee_external_id: str | None = None,
    assignee_user_id: int | None = None,
    external_tags: list | None = None,
    snippet: str | None = None,
    message_count: int | None = None,
    unread_count: int | None = None,
) -> dict:
    """1 hội thoại 1 dòng theo (page, external id). Hội thoại cũ chưa định danh
    được khách (customer_id null) thì lần đồng bộ sau bồi vào.

    Phần lưu vết đồng bộ (BRD mục 4): `source` · `external_updated_at` = mốc
    updated_at BÊN PANCAKE · `synced_at` = now() mỗi lần chạm tới. Nhân viên xử
    lý bên Pancake giữ cả bản gốc (assignee_external_id) lẫn bản đã ánh xạ về
    CRM (assignee_user_id) — chưa ánh xạ thì để rỗng, KHÔNG chặn đồng bộ.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.conversations
                   (customer_id, page_id, external_conversation_id, last_message_at,
                    source, external_updated_at, synced_at, assignee_external_id,
                    assignee_user_id, external_tags, snippet, message_count, unread_count)
            values (%s, %s, %s, %s::timestamptz, %s, %s::timestamptz, now(), %s, %s,
                    %s::jsonb, %s, %s, %s)
            on conflict (page_id, external_conversation_id) do update set
                customer_id     = coalesce(crm.conversations.customer_id, excluded.customer_id),
                last_message_at = greatest(
                    coalesce(crm.conversations.last_message_at, excluded.last_message_at),
                    excluded.last_message_at),
                source              = coalesce(excluded.source, crm.conversations.source),
                external_updated_at = greatest(
                    coalesce(crm.conversations.external_updated_at, excluded.external_updated_at),
                    excluded.external_updated_at),
                synced_at            = now(),
                assignee_external_id = coalesce(excluded.assignee_external_id,
                                                crm.conversations.assignee_external_id),
                assignee_user_id     = coalesce(excluded.assignee_user_id,
                                                crm.conversations.assignee_user_id),
                external_tags        = excluded.external_tags,
                snippet              = coalesce(excluded.snippet, crm.conversations.snippet),
                message_count        = coalesce(excluded.message_count,
                                                crm.conversations.message_count),
                unread_count         = coalesce(excluded.unread_count,
                                                crm.conversations.unread_count)
            returning *
            """,
            (
                customer_id, page_id, external_conversation_id, last_message_at,
                source, external_updated_at, assignee_external_id, assignee_user_id,
                json.dumps(external_tags or [], ensure_ascii=False),
                snippet, message_count, unread_count,
            ),
        ).fetchone()


def danh_dau_dong_bo(customer_id: int) -> None:
    """Đóng dấu `synced_at` cho khách (mục 4 — biết dữ liệu tươi tới đâu)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.customers set synced_at = now() where id = %s", (customer_id,)
        )


# ------------------------------------------------------------------ tags

def get_tag(tag_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.tags where id = %s", (tag_id,)
        ).fetchone()


def find_or_create_tag(name: str, type_: str | None) -> dict:
    """FR-023 — unique (type, name); có rồi thì dùng lại, chưa có thì tạo."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "select * from crm.tags where name = %s and type is not distinct from %s",
            (name, type_),
        ).fetchone()
        if row:
            return row
        return conn.execute(
            "insert into crm.tags (name, type) values (%s, %s) returning *",
            (name, type_),
        ).fetchone()


def add_tag(customer_id: int, tag_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "insert into crm.customer_tags (customer_id, tag_id) values (%s, %s) "
            "on conflict do nothing",
            (customer_id, tag_id),
        )


def remove_tag(customer_id: int, tag_id: int) -> int:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "delete from crm.customer_tags where customer_id = %s and tag_id = %s",
            (customer_id, tag_id),
        ).rowcount


# ------------------------------------------------------------------ phân công

def assign(
    *, customer_id: int, user_id: int, assignment_type: str
) -> dict:
    """Đóng dòng đang mở cùng loại (nếu có) + mở dòng mới — giữ trọn lịch sử."""
    pool = get_pg_pool()
    with pool.connection() as conn, conn.transaction():
        cu = conn.execute(
            """
            update crm.customer_assignments set end_at = now()
            where customer_id = %s and assignment_type = %s and end_at is null
            returning user_id
            """,
            (customer_id, assignment_type),
        ).fetchone()
        moi = conn.execute(
            "insert into crm.customer_assignments (customer_id, user_id, assignment_type) "
            "values (%s, %s, %s) returning *",
            (customer_id, user_id, assignment_type),
        ).fetchone()
        return {**moi, "nguoi_cu_id": cu["user_id"] if cu else None}


def assignment_history(customer_id: int) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select a.*, u.name as user_name
            from crm.customer_assignments a
            join crm.users u on u.id = a.user_id
            where a.customer_id = %s
            order by a.start_at desc
            """,
            (customer_id,),
        ).fetchall()


# ------------------------------------------------------------------ gộp khách (FR-022)

# Bảng chỉ cần đổi customer_id thẳng (không có ràng buộc duy nhất theo khách)
_BANG_DOI_THANG = [
    "conversations", "calls", "leads", "consultation_sessions",
    "safety_screenings", "orders", "customer_treatments", "care_plans",
    "care_interactions", "tasks", "repurchase_opportunities",
    "funnel_events", "lead_attributions", "ai_recommendations", "handovers",
]


def merge_into(primary_id: int, dup_id: int) -> dict[str, int]:
    """Dồn toàn bộ dữ liệu con của `dup` sang `primary` trong MỘT transaction.

    Bảng có ràng buộc duy nhất theo khách xử lý riêng: dòng của dup mà primary
    đã có tương đương thì BỎ (không mất dữ liệu gốc nào khác — FR-022).
    Hồ sơ phụ KHÔNG xoá: status='merged' + merged_into_id (đặc tả cấm mất lịch sử).
    """
    so: dict[str, int] = {}
    pool = get_pg_pool()
    with pool.connection() as conn, conn.transaction():
        for bang in _BANG_DOI_THANG:
            so[bang] = conn.execute(
                f"update crm.{bang} set customer_id = %s where customer_id = %s",
                (primary_id, dup_id),
            ).rowcount

        # identities: bỏ dòng đụng unique (external id / page+psid) rồi mới dồn
        conn.execute(
            """
            delete from crm.customer_identities d
            where d.customer_id = %(dup)s and exists (
                select 1 from crm.customer_identities p
                where p.customer_id = %(pri)s
                  and ((p.platform = d.platform
                        and p.external_customer_id = d.external_customer_id
                        and d.external_customer_id is not null)
                    or (p.page_id = d.page_id and p.psid = d.psid
                        and d.psid is not null)))
            """,
            {"dup": dup_id, "pri": primary_id},
        )
        so["customer_identities"] = conn.execute(
            "update crm.customer_identities set customer_id = %s where customer_id = %s",
            (primary_id, dup_id),
        ).rowcount

        # tags: PK (customer, tag) — chép bỏ trùng rồi xoá bên dup
        conn.execute(
            """
            insert into crm.customer_tags (customer_id, tag_id)
            select %s, tag_id from crm.customer_tags where customer_id = %s
            on conflict do nothing
            """,
            (primary_id, dup_id),
        )
        so["customer_tags"] = conn.execute(
            "delete from crm.customer_tags where customer_id = %s", (dup_id,)
        ).rowcount

        # triệu chứng: unique (customer, symptom) — như tags
        conn.execute(
            """
            insert into crm.customer_symptoms
                   (customer_id, symptom_id, severity, frequency, started_at, is_primary)
            select %s, symptom_id, severity, frequency, started_at, is_primary
            from crm.customer_symptoms where customer_id = %s
            on conflict (customer_id, symptom_id) do nothing
            """,
            (primary_id, dup_id),
        )
        so["customer_symptoms"] = conn.execute(
            "delete from crm.customer_symptoms where customer_id = %s", (dup_id,)
        ).rowcount

        # thành viên chiến dịch: unique (campaign, customer)
        conn.execute(
            """
            update crm.reactivation_members m set customer_id = %(pri)s
            where m.customer_id = %(dup)s and not exists (
                select 1 from crm.reactivation_members p
                where p.campaign_id = m.campaign_id and p.customer_id = %(pri)s)
            """,
            {"dup": dup_id, "pri": primary_id},
        )
        so["reactivation_members"] = conn.execute(
            "delete from crm.reactivation_members where customer_id = %s", (dup_id,)
        ).rowcount

        # phân công: đóng dòng mở của dup nếu primary ĐANG có người cùng vai
        # (chỉ mục uq_customer_assignments_active cấm 2 dòng mở cùng loại)
        conn.execute(
            """
            update crm.customer_assignments a set end_at = now()
            where a.customer_id = %(dup)s and a.end_at is null and exists (
                select 1 from crm.customer_assignments p
                where p.customer_id = %(pri)s
                  and p.assignment_type = a.assignment_type and p.end_at is null)
            """,
            {"dup": dup_id, "pri": primary_id},
        )
        so["customer_assignments"] = conn.execute(
            "update crm.customer_assignments set customer_id = %s where customer_id = %s",
            (primary_id, dup_id),
        ).rowcount

        # đánh dấu hồ sơ phụ
        conn.execute(
            "update crm.customers set status = 'merged', merged_into_id = %s "
            "where id = %s",
            (primary_id, dup_id),
        )
    return so


# ------------------------------------------------------------------ timeline (CUSTOMER-008)

def timeline(customer_id: int, limit: int = 100) -> list[dict]:
    """Dòng thời gian gộp từ các bảng ĐÃ có dữ liệu ở lát này.

    Mỗi dòng: {loai, luc, mo_ta, ref_id}. Nguồn sẽ nở thêm theo B5-B9
    (tư vấn, chăm sóc, mua lại) — cấu trúc trả về giữ nguyên.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            (select 'message' as loai, m.sent_at as luc,
                    left(coalesce(m.content, ''), 120) as mo_ta, m.id as ref_id
             from crm.messages m
             join crm.conversations v on v.id = m.conversation_id
             where v.customer_id = %(c)s)
            union all
            (select 'call', c2.started_at,
                    concat(c2.direction, ' · ', coalesce(c2.status, '')), c2.id
             from crm.calls c2 where c2.customer_id = %(c)s)
            union all
            (select 'lead_stage', h.changed_at,
                    concat('Lead #', l.id, ' → ', s.name), h.id
             from crm.lead_stage_history h
             join crm.leads l on l.id = h.lead_id
             join crm.pipeline_stages s on s.id = h.to_stage_id
             where l.customer_id = %(c)s)
            union all
            (select 'order', o.created_at,
                    concat('Đơn ', coalesce(o.external_order_id, o.id::text),
                           ' · ', o.status), o.id
             from crm.orders o where o.customer_id = %(c)s)
            union all
            (select 'task', t.created_at,
                    concat(t.task_type, ' · ', t.status), t.id
             from crm.tasks t where t.customer_id = %(c)s)
            union all
            (select 'care', ci.created_at,
                    left(coalesce(ci.summary, 'chăm sóc'), 120), ci.id
             from crm.care_interactions ci where ci.customer_id = %(c)s)
            order by luc desc nulls last
            limit %(n)s
            """,
            {"c": customer_id, "n": limit},
        ).fetchall()
