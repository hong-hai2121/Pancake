"""API trung tâm thông báo — NOTIFY-001…004 (màn 3).

Route là lớp mỏng: 11 nguồn quét + luật gửi cho ai nằm ở
services/notification_service.py.

Quyền: KHÔNG đòi quyền riêng — ai đăng nhập cũng xem được thông báo CỦA MÌNH
(mọi truy vấn lọc theo user_id trong token, không có đường xem của người khác).
"""

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.schemas.notification import NotificationSettingsIn
from app.services import notification_service

router = APIRouter(prefix="/api/v1", tags=["notifications"])


def _uid(user: dict) -> int:
    return int(user.get("sub") or 0)


@router.get("/notifications")
async def list_notifications(
    chua_doc: bool = False,
    type: str = Query("", alias="type"),
    pt: PhanTrang = Depends(phan_trang),
    user: dict = Depends(get_current_user),
):
    """NOTIFY-001 — thông báo của tôi; chưa đọc lên đầu, mới nhất trước."""
    rows, total = notification_service.danh_sach(
        _uid(user), chua_doc=chua_doc, type_=type,
        limit=pt.limit, offset=pt.offset)
    data = bao_trang(rows, total, pt)
    data["chua_doc"] = notification_service.dem_chua_doc(_uid(user))
    return ok(data)


@router.post("/notifications/read-all")
async def read_all(user: dict = Depends(get_current_user)):
    """NOTIFY-003 — đánh dấu tất cả đã đọc (khai TRƯỚC {id} để không bị nuốt)."""
    return ok(notification_service.danh_dau_doc_het(user), "Đã đọc tất cả")


@router.post("/notifications/{notification_id}/read")
async def read_one(notification_id: int, user: dict = Depends(get_current_user)):
    """NOTIFY-002 — đánh dấu một thông báo đã đọc."""
    return ok(notification_service.danh_dau_doc(notification_id, user),
              "Đã đánh dấu đã đọc")


@router.get("/notification-settings")
async def get_settings(user: dict = Depends(get_current_user)):
    """Đủ 11 loại kèm nhãn + đang bật/tắt (thiếu dòng trong DB = bật)."""
    return ok(notification_service.lay_cai_dat(user))


@router.put("/notification-settings")
async def put_settings(
    body: NotificationSettingsIn, user: dict = Depends(get_current_user),
):
    """NOTIFY-004 — bật/tắt từng loại cho riêng mình."""
    return ok(notification_service.dat_cai_dat(body.settings, user),
              "Đã lưu cài đặt thông báo")
