"""TASK-001…009 (B4 — task engine chung Sale/CSKH, mục 19 BRD).

Route là lớp mỏng: mọi luật nằm ở services/task_service.py (kiểm bằng
scripts/thu_b4.py). Quyền: đọc = `customer.view` · ghi = `customer.edit`
(việc luôn xoay quanh khách) — Sale/CSKH/trưởng nhóm đều có sẵn cặp này.
"""

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_permission
from app.core.errors import ApiError
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.db.repositories import task_repo
from app.schemas.task import (
    TaskCompleteIn, TaskCreateIn, TaskReassignIn, TaskRescheduleIn, TaskUpdateIn,
)
from app.services import task_service

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

_xem = Depends(require_permission("customer.view"))
_sua = Depends(require_permission("customer.edit"))


# /tasks/today và /tasks/overdue phải khai TRƯỚC /tasks/{task_id} kẻo bị nuốt
# (bài học route matching của B3).

@router.get("/today")
async def tasks_today(user_id: int | None = Query(None), user: dict = _xem):
    """TASK-008 — mặc định việc CỦA MÌNH; truyền user_id để xem người khác
    (trưởng nhóm coi việc của đội)."""
    return ok({"items": task_service.list_today(user_id or int(user["sub"]))})


@router.get("/overdue")
async def tasks_overdue(user_id: int | None = Query(None), _user: dict = _xem):
    """TASK-009 — việc đang mở mà trễ hạn (màn tô đỏ dựa vào đây)."""
    return ok({"items": task_service.list_overdue(user_id)})


@router.get("")
async def list_tasks(
    assigned_to: int | None = Query(None),
    customer_id: int | None = Query(None),
    status: str = Query("", pattern="^(open|in_progress|done|cancelled)?$"),
    task_type: str = "",
    qua_han: bool = False,
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _xem,
):
    """TASK-001 — lọc theo người/khách/trạng thái/loại; `qua_han=true` = trễ hạn."""
    rows, total = task_repo.list_tasks(
        assigned_to=assigned_to, customer_id=customer_id, status=status,
        task_type=task_type, qua_han=qua_han, limit=pt.limit, offset=pt.offset,
    )
    return ok(bao_trang(rows, total, pt))


@router.get("/{task_id}")
async def get_task(task_id: int, _user: dict = _xem):
    """TASK-002."""
    task = task_repo.get_task(task_id)
    if not task:
        raise ApiError("NOT_FOUND", "Không tìm thấy công việc")
    return ok(task)


@router.post("", status_code=201)
async def create_task(body: TaskCreateIn, user: dict = _sua):
    """TASK-003 — owner + due_at bắt buộc (mục 19 BRD)."""
    return ok(task_service.create_task(body.model_dump(), actor=user), "Đã tạo việc")


@router.put("/{task_id}")
async def update_task(task_id: int, body: TaskUpdateIn, user: dict = _sua):
    """TASK-004 — đóng việc KHÔNG đi đường này (dùng /complete)."""
    return ok(task_service.update_task(task_id, body.model_dump(), actor=user),
              "Đã cập nhật")


@router.post("/{task_id}/complete")
async def complete_task(task_id: int, body: TaskCompleteIn, user: dict = _sua):
    """TASK-005 — thiếu kết quả là bị chặn (mục 19 BRD)."""
    return ok(task_service.complete_task(task_id, body.result, actor=user),
              "Đã hoàn thành")


@router.post("/{task_id}/reschedule")
async def reschedule_task(task_id: int, body: TaskRescheduleIn, user: dict = _sua):
    """TASK-006 — hạn mới ở tương lai + lý do; xoá dấu leo thang cũ."""
    return ok(
        task_service.reschedule_task(
            task_id, body.due_at, reason=body.reason, actor=user
        ),
        "Đã dời lịch",
    )


@router.post("/{task_id}/reassign")
async def reassign_task(task_id: int, body: TaskReassignIn, user: dict = _sua):
    """TASK-007 — người nhận phải active, có lý do."""
    return ok(
        task_service.reassign_task(
            task_id, body.user_id, reason=body.reason, actor=user
        ),
        "Đã chuyển người phụ trách",
    )
