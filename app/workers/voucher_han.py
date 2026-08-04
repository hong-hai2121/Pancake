"""Worker C1: đóng voucher quá hạn + làm mới hạng thẻ mỗi ngày.

Hai việc chạy chung một vòng vì cùng nhịp (ngày) và cùng đụng tới hồ sơ khách:

  1. Voucher qua ngày mà chưa dùng → `het_han_khong_dung`. Không có bước này
     thì màn Voucher vẫn đếm chúng là "còn hạn", và luật C7 ("còn voucher thì
     tắt mốc chăm chuẩn") sẽ khoá lịch chăm của khách vĩnh viễn.
  2. Xếp lại hạng thẻ theo tổng chi tiêu — CHỈ NÂNG (xem voucher_service).
     Khách mua xong được lên hạng ngay hôm sau chứ không phải chờ admin bấm.

Công tắc `voucher_expire_scan_enabled` ở màn Cài đặt tắt được cả hai việc.
Nhịp 1 giờ chứ không phải 24 giờ: server hay được khởi động lại, ngủ nguyên
ngày thì có hôm không chạy lượt nào. Chạy thừa vô hại — cả hai thao tác đều
idempotent (điều kiện WHERE tự loại dòng đã xử lý).
"""

import asyncio
import logging

log = logging.getLogger(__name__)

_CHU_KY_GIAY = 3600


async def voucher_han_loop() -> None:
    from app.core import runtime_config

    while True:
        try:
            if runtime_config.bat("voucher_expire_scan_enabled"):
                await asyncio.to_thread(_mot_vong)
        except Exception:  # noqa: BLE001 — worker nền không chết vì 1 vòng lỗi
            log.exception("[voucher] quet han loi — bo qua vong nay")
        await asyncio.sleep(_CHU_KY_GIAY)


def _mot_vong() -> None:
    from app.db.repositories import voucher_repo
    from app.services import voucher_service

    so = voucher_repo.het_han_hang_loat()
    if so:
        log.info("[voucher] %s voucher qua han -> het_han_khong_dung", so)
    kq = voucher_service.tinh_lai_hang()
    if kq["len_hang"]:
        log.info("[voucher] %s khach LEN hang the", kq["len_hang"])
