"""Nghiệp vụ công việc (B4 — mục 19 BRD). KHÔNG import FastAPI.

Task engine DÙNG CHUNG cho Sale, CSKH, chuyên môn, vận hành. Luật trọng yếu
(mục 19) cài hết ở đây, API/web chỉ là vỏ:

  * Mọi việc phải có NGƯỜI PHỤ TRÁCH (đang active) và HẠN (due_at).
  * KHÔNG đóng việc nếu thiếu KẾT QUẢ — complete bắt buộc `result`.
  * Quá hạn: hiện đỏ ở màn (so due_at với now lúc đọc) + worker quét đánh dấu
    `escalated_at` MỘT lần và ghi audit "báo quản lý" (`quet_qua_han`).
  * Dời lịch/chuyển người/huỷ đều phải có LÝ DO — vào audit, khỏi cãi nhau sau.

`actor` = payload token người thao tác (cùng nếp user_service/lead_service).
"""

from datetime import datetime, timezone

from psycopg.errors import ForeignKeyViolation

from app.core.errors import ApiError
from app.db.repositories import audit_repo, task_repo, user_repo

# 8 loại việc — mục 19 BRD ("gọi, nhắn, gửi nội dung, xác nhận đơn, chăm,
# mua lại, xử lý sự cố, duyệt chuyên môn"). Template theo pipeline/care plan
# sẽ sinh task với đúng các mã này ở B8/B9.
LOAI_VIEC: dict[str, str] = {
    "goi": "Gọi điện",
    "nhan_tin": "Nhắn tin",
    "gui_noi_dung": "Gửi nội dung",
    "xac_nhan_don": "Xác nhận đơn",
    "cham_soc": "Chăm sóc",
    "mua_lai": "Mua lại",
    "xu_ly_su_co": "Xử lý sự cố",
    "duyet_chuyen_mon": "Duyệt chuyên môn",
}

_DANG_MO = ("open", "in_progress")


def _audit(actor: dict | None, **kw) -> None:
    audit_repo.ghi(
        user_id=int(actor["sub"]) if actor else None,
        object_type="tasks", **kw,
    )


def _lay(task_id: int) -> dict:
    task = task_repo.get_task(task_id)
    if not task:
        raise ApiError("NOT_FOUND", "Không tìm thấy công việc")
    return task


def _phai_dang_mo(task: dict) -> None:
    if task["status"] not in _DANG_MO:
        raise ApiError(
            "CONFLICT",
            f"Việc đã {'hoàn thành' if task['status'] == 'done' else 'huỷ'} — "
            "không sửa được nữa",
        )


def _kiem_nguoi(user_id: int) -> dict:
    nguoi = user_repo.get_user(user_id)
    if not nguoi:
        raise ApiError("NOT_FOUND", "Không tìm thấy người phụ trách")
    if nguoi["status"] != "active":
        raise ApiError("CONFLICT", "Người phụ trách đang bị khoá — chọn người khác")
    return nguoi


def _kiem_lien_ket(related_type: str | None, related_id: int | None) -> None:
    if bool(related_type) != bool(related_id):
        raise ApiError("VALIDATION_ERROR",
                       "related_type và related_id phải đi cùng nhau")
    if related_type and not task_repo.ton_tai_lien_ket(related_type, related_id):
        raise ApiError("NOT_FOUND",
                       f"Không tìm thấy {related_type} #{related_id} để gắn việc")


def create_task(data: dict, *, actor: dict | None = None) -> dict:
    """TASK-003. Luật mục 19: bắt buộc owner + due_at, loại việc phải chuẩn."""
    if data.get("task_type") not in LOAI_VIEC:
        raise ApiError(
            "VALIDATION_ERROR",
            "Loại việc không hợp lệ — dùng một trong: " + ", ".join(LOAI_VIEC),
            errors={"task_type": "không hợp lệ"},
        )
    if not data.get("assigned_to"):
        raise ApiError("MISSING_REQUIRED_DATA",
                       "Mọi việc phải có người phụ trách (mục 19 BRD)")
    if not data.get("due_at"):
        raise ApiError("MISSING_REQUIRED_DATA",
                       "Mọi việc phải có hạn xử lý due_at (mục 19 BRD)")
    _kiem_nguoi(data["assigned_to"])
    _kiem_lien_ket(data.get("related_type"), data.get("related_id"))

    try:
        task = task_repo.create_task(
            title=data.get("title"), task_type=data["task_type"],
            assigned_to=data["assigned_to"], due_at=data["due_at"],
            priority=data.get("priority") or "normal",
            customer_id=data.get("customer_id"),
            related_type=data.get("related_type"),
            related_id=data.get("related_id"),
            created_by=int(actor["sub"]) if actor else None,
        )
    except ForeignKeyViolation as err:
        raise ApiError("NOT_FOUND", "customer_id không tồn tại") from err
    _audit(actor, action="task_create", object_id=task["id"],
           new_value={k: str(task[k]) for k in
                      ("task_type", "assigned_to", "due_at", "priority")})
    return task


def update_task(task_id: int, data: dict, *, actor: dict | None = None) -> dict:
    """TASK-004: sửa mô tả/ưu tiên/gắn khách; đổi trạng thái CHỈ cho phép
    open→in_progress (bắt tay vào làm) hoặc →cancelled kèm lý do. Đóng việc
    phải đi đường complete_task — không cho lách luật kết quả (mục 19)."""
    task = _lay(task_id)
    _phai_dang_mo(task)
    data = {k: v for k, v in data.items() if v is not None}

    trang_thai = data.get("status")
    if trang_thai:
        if trang_thai == "done":
            raise ApiError("CONFLICT",
                           "Đóng việc phải qua /complete kèm kết quả (mục 19 BRD)")
        if trang_thai == "cancelled" and not (data.get("reason") or "").strip():
            raise ApiError("MISSING_REQUIRED_DATA", "Huỷ việc phải ghi lý do")
        if trang_thai not in ("in_progress", "cancelled"):
            raise ApiError("VALIDATION_ERROR", "status chỉ nhận in_progress/cancelled")
    if "task_type" in data and data["task_type"] not in LOAI_VIEC:
        raise ApiError("VALIDATION_ERROR", "Loại việc không hợp lệ")
    if "related_type" in data or "related_id" in data:
        _kiem_lien_ket(data.get("related_type", task["related_type"]),
                       data.get("related_id", task["related_id"]))

    ly_do = data.pop("reason", None)
    truoc, sau = {}, {}
    for k, v in data.items():
        if task.get(k) != v:
            truoc[k], sau[k] = task.get(k), v
    if not sau:
        return task
    task_repo.update_task(task_id, sau)
    _audit(actor, action="task_update", object_id=task_id,
           old_value={k: str(v) for k, v in truoc.items()},
           new_value={k: str(v) for k, v in sau.items()}, reason=ly_do)
    return task_repo.get_task(task_id)


def complete_task(task_id: int, result: str, *, actor: dict | None = None) -> dict:
    """TASK-005 — LUẬT CỨNG mục 19: không đóng nếu thiếu kết quả."""
    task = _lay(task_id)
    _phai_dang_mo(task)
    if not (result or "").strip():
        raise ApiError(
            "MISSING_REQUIRED_DATA",
            f"Không đóng việc nếu thiếu kết quả — ghi rõ kết quả "
            f"{LOAI_VIEC.get(task['task_type'], task['task_type'])} (mục 19 BRD)",
        )
    task_repo.complete_task(task_id, result.strip())
    _audit(actor, action="task_complete", object_id=task_id,
           old_value={"status": task["status"]},
           new_value={"status": "done", "result": result.strip()[:500]})
    return task_repo.get_task(task_id)


def reschedule_task(
    task_id: int, due_at: datetime, *, reason: str = "",
    actor: dict | None = None,
) -> dict:
    """TASK-006: dời lịch phải có lý do; hạn mới không được ở quá khứ."""
    task = _lay(task_id)
    _phai_dang_mo(task)
    if not (reason or "").strip():
        raise ApiError("MISSING_REQUIRED_DATA", "Dời lịch phải ghi lý do")
    if due_at <= datetime.now(timezone.utc):
        raise ApiError("VALIDATION_ERROR", "Hạn mới phải ở tương lai")
    task_repo.reschedule_task(task_id, due_at)
    _audit(actor, action="task_reschedule", object_id=task_id,
           old_value={"due_at": str(task["due_at"])},
           new_value={"due_at": str(due_at)}, reason=reason.strip())
    return task_repo.get_task(task_id)


def reassign_task(
    task_id: int, user_id: int, *, reason: str = "", actor: dict | None = None
) -> dict:
    """TASK-007: chuyển người phải có lý do (như chuyển lead FR-031)."""
    task = _lay(task_id)
    _phai_dang_mo(task)
    if task["assigned_to"] == user_id:
        return task
    if not (reason or "").strip():
        raise ApiError("MISSING_REQUIRED_DATA", "Chuyển người phụ trách phải ghi lý do")
    nguoi = _kiem_nguoi(user_id)
    task_repo.reassign_task(task_id, user_id)
    _audit(actor, action="task_reassign", object_id=task_id,
           old_value={"assigned_to": task["assigned_to"]},
           new_value={"assigned_to": user_id, "ten": nguoi["name"]},
           reason=reason.strip())
    return task_repo.get_task(task_id)


def list_today(user_id: int) -> list[dict]:
    """TASK-008: việc hôm nay CỦA MỘT NGƯỜI (kèm cờ tre_han để màn tô đỏ)."""
    return task_repo.list_today(user_id)


def list_overdue(user_id: int | None = None) -> list[dict]:
    """TASK-009."""
    return task_repo.list_overdue(user_id)


def quet_qua_han() -> int:
    """Worker gọi định kỳ: đánh dấu leo thang MỘT LẦN mỗi task quá hạn + ghi
    audit 'task_escalated' (báo quản lý theo SLA — mục 19). Màn Nhật ký (A4)
    và dashboard B11 đọc từ đây; đổi kênh báo (Telegram...) chỉ sửa chỗ này."""
    danh_dau = task_repo.danh_dau_leo_thang()
    for t in danh_dau:
        _audit(None, action="task_escalated", object_id=t["id"],
               reason=f"qua han {t['due_at']:%d/%m %H:%M}, "
                      f"nguoi phu trach user#{t['assigned_to']} — bao quan ly")
    return len(danh_dau)
