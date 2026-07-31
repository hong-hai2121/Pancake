"""SQL công việc (B4 — TASK-001…009): crm.tasks.

Chỉ đọc/ghi; luật nghiệp vụ (owner+hạn bắt buộc, không đóng thiếu kết quả,
leo thang quá hạn...) nằm ở app/services/task_service.py. Trạng thái `overdue`
trong CHECK của schema KHÔNG dùng làm trạng thái lưu — quá hạn là chuyện SO
due_at VỚI now() lúc đọc (khỏi lệch đồng hồ giữa cột status và thực tế).
"""

from datetime import datetime

from app.db.client import get_pg_pool

_COLS = """
    t.id, t.title, t.task_type, t.priority, t.status, t.due_at,
    t.customer_id, c.full_name as customer_name,
    t.assigned_to, u.name as assignee_name,
    t.related_type, t.related_id, t.result,
    t.created_by, nb.name as created_by_name,
    t.completed_at, t.escalated_at, t.created_at, t.updated_at
"""
_FROM = """
    from crm.tasks t
    left join crm.customers c on c.id = t.customer_id
    left join crm.users u  on u.id  = t.assigned_to
    left join crm.users nb on nb.id = t.created_by
"""

# Task đang "sống" — chỉ nhóm này mới sửa/đóng/dời/chuyển được
_DANG_MO = "('open','in_progress')"


def list_tasks(
    *,
    assigned_to: int | None = None,
    customer_id: int | None = None,
    status: str = "",
    task_type: str = "",
    qua_han: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """TASK-001: danh sách + tổng số; `qua_han=True` = đang mở mà trễ hạn."""
    dieu_kien, tham_so = ["true"], []
    if assigned_to is not None:
        dieu_kien.append("t.assigned_to = %s")
        tham_so.append(assigned_to)
    if customer_id is not None:
        dieu_kien.append("t.customer_id = %s")
        tham_so.append(customer_id)
    if status:
        dieu_kien.append("t.status = %s")
        tham_so.append(status)
    if task_type:
        dieu_kien.append("t.task_type = %s")
        tham_so.append(task_type)
    if qua_han:
        dieu_kien.append(f"t.status in {_DANG_MO} and t.due_at < now()")
    where = " and ".join(dieu_kien)

    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"select {_COLS} {_FROM} where {where} "
            "order by t.due_at nulls last, t.id limit %s offset %s",
            (*tham_so, limit, offset),
        ).fetchall()
        total = conn.execute(
            f"select count(*) as n from crm.tasks t where {where}",
            tham_so or None,
        ).fetchone()["n"]
    return rows, total


def get_task(task_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_COLS} {_FROM} where t.id = %s", (task_id,)
        ).fetchone()


def create_task(
    *, title: str | None, task_type: str, assigned_to: int, due_at: datetime,
    priority: str, customer_id: int | None, related_type: str | None,
    related_id: int | None, created_by: int | None,
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """
            insert into crm.tasks (title, task_type, assigned_to, due_at, priority,
                                   customer_id, related_type, related_id, created_by)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (title, task_type, assigned_to, due_at, priority,
             customer_id, related_type, related_id, created_by),
        ).fetchone()
    return get_task(row["id"])


def update_task(task_id: int, fields: dict) -> None:
    """TASK-004: chỉ nhận cột cho phép — trạng thái/kết quả đi đường riêng
    (complete/reschedule/reassign) để luật mục 19 không bị lách."""
    cho_phep = {"title", "task_type", "priority", "customer_id",
                "related_type", "related_id", "status"}
    gan = {k: v for k, v in fields.items() if k in cho_phep}
    if not gan:
        return
    dat = ", ".join(f"{k} = %s" for k in gan)
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            f"update crm.tasks set {dat} where id = %s", (*gan.values(), task_id)
        )


def complete_task(task_id: int, result: str) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.tasks set status = 'done', result = %s, "
            "completed_at = now() where id = %s",
            (result, task_id),
        )


def reschedule_task(task_id: int, due_at: datetime) -> None:
    """Hạn mới thì xoá dấu leo thang — quá hạn tính lại từ đầu."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.tasks set due_at = %s, escalated_at = null where id = %s",
            (due_at, task_id),
        )


def reassign_task(task_id: int, user_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.tasks set assigned_to = %s where id = %s",
            (user_id, task_id),
        )


def list_today(assigned_to: int) -> list[dict]:
    """TASK-008 'Việc hôm nay' của MỘT người: đến hạn hôm nay + đang trễ."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select {_COLS}, (t.due_at < now()) as tre_han {_FROM}
             where t.assigned_to = %s and t.status in {_DANG_MO}
               and t.due_at::date <= current_date
             order by t.due_at
            """,
            (assigned_to,),
        ).fetchall()


def list_overdue(assigned_to: int | None = None) -> list[dict]:
    """TASK-009: đang mở mà trễ hạn (toàn hệ thống hoặc của một người)."""
    them, tham_so = "", []
    if assigned_to is not None:
        them = "and t.assigned_to = %s"
        tham_so.append(assigned_to)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_COLS} {_FROM} "
            f"where t.status in {_DANG_MO} and t.due_at < now() {them} "
            "order by t.due_at",
            tham_so or None,
        ).fetchall()


def danh_dau_leo_thang() -> list[dict]:
    """Đánh dấu MỘT LẦN các task quá hạn chưa báo (escalated_at null) — trả về
    danh sách vừa đánh để service ghi audit 'báo quản lý' từng cái."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            update crm.tasks t set escalated_at = now()
             where t.status in {_DANG_MO} and t.due_at < now()
               and t.escalated_at is null
            returning t.id, t.task_type, t.assigned_to, t.due_at
            """,
        ).fetchall()


def ton_tai_lien_ket(related_type: str, related_id: int) -> bool:
    """Quan hệ đa hình không đặt được FK (comment trong schema) — phần mềm tự
    kiểm bản ghi đích có thật trước khi gắn."""
    bang = {
        "lead": "crm.leads",
        "order": "crm.orders",
        "care_plan_step": "crm.care_plan_steps",
        "customer_treatment": "crm.customer_treatments",
        "repurchase_opportunity": "crm.repurchase_opportunities",
    }.get(related_type)
    if not bang:
        return False
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select 1 from {bang} where id = %s", (related_id,)
        ).fetchone() is not None
