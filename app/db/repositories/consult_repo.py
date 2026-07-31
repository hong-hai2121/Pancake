"""SQL hồ sơ tư vấn + sàng lọc an toàn (B5 — FR-050…053).

Gồm 6 nhóm bảng: consultation_sessions/answers · customer_symptoms ·
examinations · current_medications/previous_treatments · safety_screenings ·
clinical_escalations. Luật (red flag, chặn đề xuất, chuyển chuyên môn...)
nằm ở app/services/consult_service.py.
"""

from app.db.client import get_pg_pool


# ------------------------------------------------------------------ phiên tư vấn
def create_session(
    *, customer_id: int, lead_id: int | None, user_id: int | None,
    channel: str | None,
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.consultation_sessions
                   (customer_id, lead_id, user_id, channel, started_at)
            values (%s, %s, %s, %s, now())
            returning id, customer_id, lead_id, user_id, channel,
                      started_at, completed_at, risk_level
            """,
            (customer_id, lead_id, user_id, channel),
        ).fetchone()


def get_session(session_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select s.*, c.full_name as customer_name, u.name as user_name
              from crm.consultation_sessions s
              join crm.customers c on c.id = s.customer_id
              left join crm.users u on u.id = s.user_id
             where s.id = %s
            """,
            (session_id,),
        ).fetchone()


def save_answers(session_id: int, answers: list[dict]) -> int:
    """CONSULT-003: chèn từng câu trả lời (giữ mọi lần khai — lịch sử khai thác;
    câu MỚI NHẤT mỗi mã là câu có hiệu lực)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        for a in answers:
            conn.execute(
                """
                insert into crm.consultation_answers
                       (session_id, question_code, answer_text, answer_value, captured_at)
                values (%s, %s, %s, %s, now())
                """,
                (session_id, a["question_code"], a.get("answer_text"),
                 a.get("answer_value")),
            )
    return len(answers)


def list_answers(session_id: int) -> list[dict]:
    """Câu MỚI NHẤT của từng question_code trong phiên."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select distinct on (question_code)
                   question_code, answer_text, answer_value, captured_at
              from crm.consultation_answers
             where session_id = %s
             order by question_code, captured_at desc, id desc
            """,
            (session_id,),
        ).fetchall()


def complete_session(session_id: int, risk_level: str) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.consultation_sessions "
            "set completed_at = now(), risk_level = %s where id = %s",
            (risk_level, session_id),
        )


# ------------------------------------------------------------------ triệu chứng
def list_symptom_catalog() -> list[dict]:
    """SYMPTOM-001 — danh mục seed từ scripts/seed_danh_muc.py."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select id, code, name, group_name from crm.symptoms "
            "order by group_name, id"
        ).fetchall()


def upsert_customer_symptom(customer_id: int, symptom_id: int, fields: dict) -> dict:
    """SYMPTOM-002: mỗi khách mỗi triệu chứng 1 dòng (unique) — khai lại thì cập nhật."""
    cho_phep = {"severity", "frequency", "started_at", "is_primary",
                "occurs_when", "meal_relation", "note"}
    gan = {k: v for k, v in fields.items() if k in cho_phep}
    cot = ", ".join(gan)
    cap_nhat = ", ".join(f"{k} = excluded.{k}" for k in gan)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            insert into crm.customer_symptoms (customer_id, symptom_id, {cot})
            values (%s, %s, {', '.join(['%s'] * len(gan))})
            on conflict (customer_id, symptom_id) do update set {cap_nhat}
            returning *
            """,
            (customer_id, symptom_id, *gan.values()),
        ).fetchone()


def get_customer_symptom(customer_id: int, cs_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.customer_symptoms where id = %s and customer_id = %s",
            (cs_id, customer_id),
        ).fetchone()


def update_customer_symptom(cs_id: int, fields: dict) -> None:
    cho_phep = {"severity", "frequency", "started_at", "is_primary",
                "occurs_when", "meal_relation", "note"}
    gan = {k: v for k, v in fields.items() if k in cho_phep}
    if not gan:
        return
    dat = ", ".join(f"{k} = %s" for k in gan)
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            f"update crm.customer_symptoms set {dat} where id = %s",
            (*gan.values(), cs_id),
        )


def list_customer_symptoms(customer_id: int) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select cs.*, s.code as symptom_code, s.name as symptom_name,
                   s.group_name
              from crm.customer_symptoms cs
              join crm.symptoms s on s.id = cs.symptom_id
             where cs.customer_id = %s
             order by cs.is_primary desc, cs.severity desc nulls last
            """,
            (customer_id,),
        ).fetchall()


# ------------------------------------------------------------------ khám / thuốc
def add_examination(customer_id: int, fields: dict, created_by: int | None) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.examinations
                   (customer_id, exam_type, exam_date, facility, conclusion,
                    file_url, created_by)
            values (%s, %s, %s, %s, %s, %s, %s) returning *
            """,
            (customer_id, fields["exam_type"], fields.get("exam_date"),
             fields.get("facility"), fields.get("conclusion"),
             fields.get("file_url"), created_by),
        ).fetchone()


def list_examinations(customer_id: int) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.examinations where customer_id = %s "
            "order by exam_date desc nulls last, id desc",
            (customer_id,),
        ).fetchall()


def add_medication(customer_id: int, fields: dict, created_by: int | None) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.current_medications
                   (customer_id, name, dosage, duration, is_active, effect,
                    reaction, created_by)
            values (%s, %s, %s, %s, %s, %s, %s, %s) returning *
            """,
            (customer_id, fields["name"], fields.get("dosage"),
             fields.get("duration"), fields.get("is_active", True),
             fields.get("effect"), fields.get("reaction"), created_by),
        ).fetchone()


def add_previous_treatment(
    customer_id: int, fields: dict, created_by: int | None
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.previous_treatments
                   (customer_id, name, duration, result, note, created_by)
            values (%s, %s, %s, %s, %s, %s) returning *
            """,
            (customer_id, fields["name"], fields.get("duration"),
             fields.get("result"), fields.get("note"), created_by),
        ).fetchone()


# ------------------------------------------------------------------ sàng lọc
def add_screening(
    customer_id: int, *, screening_type: str, value: str | None,
    risk_level: str, requires_review: bool,
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.safety_screenings
                   (customer_id, screening_type, value, risk_level, requires_review)
            values (%s, %s, %s, %s, %s) returning *
            """,
            (customer_id, screening_type, value, risk_level, requires_review),
        ).fetchone()


def list_active_screenings(customer_id: int) -> list[dict]:
    """Phiếu CÒN HIỆU LỰC (chưa được chuyên môn gỡ) — đầu vào của rule FR-053."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.safety_screenings "
            "where customer_id = %s and cleared_at is null "
            "order by created_at desc",
            (customer_id,),
        ).fetchall()


def clear_screenings(customer_id: int, cleared_by: int | None) -> int:
    """Gỡ phiếu bằng dấu vết (cleared_at/by), KHÔNG delete — FR-053."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.safety_screenings "
            "set cleared_at = now(), cleared_by = %s "
            "where customer_id = %s and cleared_at is null",
            (cleared_by, customer_id),
        ).rowcount


def set_customer_flag(customer_id: int, flag: str | None) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.customers set safety_flag = %s where id = %s",
            (flag, customer_id),
        )


def get_customer_flag(customer_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select id, full_name, safety_flag from crm.customers where id = %s",
            (customer_id,),
        ).fetchone()


# ------------------------------------------------------------------ chuyển chuyên môn
def create_escalation(
    *, customer_id: int, source: str, reason: str, risk_level: str | None,
    task_id: int | None, created_by: int | None, assigned_to: int | None,
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.clinical_escalations
                   (customer_id, source, reason, risk_level, task_id,
                    created_by, assigned_to)
            values (%s, %s, %s, %s, %s, %s, %s) returning *
            """,
            (customer_id, source, reason, risk_level, task_id,
             created_by, assigned_to),
        ).fetchone()


def get_escalation(escalation_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select e.*, c.full_name as customer_name, u.name as assignee_name
              from crm.clinical_escalations e
              join crm.customers c on c.id = e.customer_id
              left join crm.users u on u.id = e.assigned_to
             where e.id = %s
            """,
            (escalation_id,),
        ).fetchone()


def has_pending_escalation(customer_id: int) -> bool:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select 1 from crm.clinical_escalations "
            "where customer_id = %s and status = 'pending' limit 1",
            (customer_id,),
        ).fetchone() is not None


def list_escalations(
    status: str = "pending", *, limit: int = 50, offset: int = 0,
) -> tuple[list[dict], int]:
    dieu_kien, tham_so = "true", []
    if status:
        dieu_kien = "e.status = %s"
        tham_so.append(status)
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"""
            select e.*, c.full_name as customer_name, u.name as assignee_name
              from crm.clinical_escalations e
              join crm.customers c on c.id = e.customer_id
              left join crm.users u on u.id = e.assigned_to
             where {dieu_kien}
             order by e.created_at desc limit %s offset %s
            """,
            (*tham_so, limit, offset),
        ).fetchall()
        total = conn.execute(
            f"select count(*) as n from crm.clinical_escalations e where {dieu_kien}",
            tham_so or None,
        ).fetchone()["n"]
    return rows, total


def resolve_escalation(
    escalation_id: int, *, resolution: str, resolved_by: int | None
) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            update crm.clinical_escalations
               set status = 'resolved', resolution = %s,
                   resolved_by = %s, resolved_at = now()
             where id = %s
            """,
            (resolution, resolved_by, escalation_id),
        )


def nguoi_chuyen_mon() -> dict | None:
    """Người chuyên môn active đầu tiên — nơi nhận task duyet_chuyen_mon.
    Chưa có ai thì trả None (escalation vẫn tạo, task đành bỏ)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select u.id, u.name from crm.users u
              join crm.roles r on r.id = u.role_id
             where r.name = 'Người chuyên môn' and u.status = 'active'
             order by u.id limit 1
            """
        ).fetchone()
