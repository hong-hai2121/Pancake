"""AUDIT-001/002 (A4) — xem nhật ký hoạt động. Quyền `audit.view`."""

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_permission
from app.core.errors import ApiError
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.db.repositories import audit_repo

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit"])

_can_quyen = Depends(require_permission("audit.view"))


@router.get("")
async def list_logs(
    user_id: int | None = Query(None),
    action: str = "",
    object_type: str = "",
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _can_quyen,
):
    """AUDIT-001 — mới nhất trước, lọc theo người/hành động/loại đối tượng."""
    rows, total = audit_repo.list_logs(
        user_id=user_id, action=action, object_type=object_type,
        limit=pt.limit, offset=pt.offset,
    )
    return ok(bao_trang(rows, total, pt))


@router.get("/{audit_id}")
async def get_log(audit_id: int, _user: dict = _can_quyen):
    """AUDIT-002 — chi tiết 1 dòng kèm giá trị cũ/mới đầy đủ."""
    row = audit_repo.get_log(audit_id)
    if not row:
        raise ApiError("NOT_FOUND", "Không tìm thấy dòng nhật ký")
    return ok(row)
