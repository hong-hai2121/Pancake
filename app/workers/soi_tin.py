"""Worker C4: soi tin nhắn thật để xác minh công chăm sóc.

Mỗi vòng nhặt các bản TỰ KHAI chưa soi, đọc tin nhắn của nhân viên trong cửa
±1 ngày quanh lúc khai, tìm bằng chứng:

  * hành động 'nhan'  → có tin nào của chính nhân viên đó gửi cho khách không
  * hành động 'goi'   → có câu báo đã gọi không ("e vừa gọi c rồi ạ") — cuộc
    gọi không đi qua hệ thống nên đây là bằng chứng duy nhất

Chưa tới hạn thì để nguyên chờ lượt sau, KHÔNG bác vội — bác oan một lần là
nhân viên mất niềm tin vào cả hệ thống.

Nhịp 15 phút; công tắc `verify_scan_enabled` ở màn Cài đặt.
"""

import asyncio
import logging

log = logging.getLogger(__name__)

_CHU_KY_GIAY = 900


async def soi_tin_loop() -> None:
    from app.core import runtime_config

    while True:
        try:
            if runtime_config.bat("verify_scan_enabled"):
                kq = await asyncio.to_thread(_mot_vong)
                if kq and kq["soi"]:
                    log.info("[soi_tin] soi %s ban: %s xac minh, %s bac",
                             kq["soi"], kq.get("da_xac_minh", 0),
                             kq.get("bac_bo", 0))
        except Exception:  # noqa: BLE001 — worker nền không chết vì 1 vòng lỗi
            log.exception("[soi_tin] mot vong loi — bo qua")
        await asyncio.sleep(_CHU_KY_GIAY)


def _mot_vong() -> dict:
    from app.services import giam_sat_service

    return giam_sat_service.soi_hang_loat()
