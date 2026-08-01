"""Worker B9: nhịp tim của quy trình chăm 11 bước (FR-100…110).

Mỗi vòng gọi care_service.quet_moc():
  1. Mốc tới lịch (planned_at <= now) chuyển pending → due.
  2. Mốc due có người phụ trách mà chưa có việc nhắc → tạo việc 'cham_soc'
     đúng người, hạn = lịch mốc (idempotent — còn task đang mở thì thôi).
Khách do_not_contact bị lọc ngay trong SQL (AU11 — dừng mọi automation).

Nhẹ (2 câu SQL + vài insert mỗi 5 phút, thuần DB nội bộ) nên chạy luôn như
worker tasks-qua-han của B4, không cần công tắc .env riêng.
"""

import asyncio
import logging

log = logging.getLogger(__name__)

_CHU_KY_GIAY = 300


async def care_steps_loop() -> None:
    from app.services import care_service

    while True:
        try:
            kq = await asyncio.to_thread(care_service.quet_moc)
            if kq["due"] or kq["viec_moi"]:
                log.info("[care] %s moc toi han, %s viec nhac vua tao",
                         kq["due"], kq["viec_moi"])
        except Exception:  # noqa: BLE001 — worker nền không được chết vì 1 vòng lỗi
            log.exception("[care] quet moc cham loi — bo qua vong nay")
        await asyncio.sleep(_CHU_KY_GIAY)
