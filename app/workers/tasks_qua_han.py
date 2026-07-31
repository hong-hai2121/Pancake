"""Worker B4: quét việc QUÁ HẠN định kỳ để "báo quản lý theo SLA" (mục 19 BRD).

Mỗi vòng gọi task_service.quet_qua_han(): đánh dấu escalated_at MỘT lần cho
từng task trễ hạn + ghi audit `task_escalated` — màn Nhật ký (A4) lọc theo
action này là ra danh sách cần nhắc; dashboard B11 sẽ hiện đếm. Dời lịch xong
task lại đủ điều kiện được quét lần sau (escalated_at bị xoá khi reschedule).

Nhẹ (1 câu UPDATE mỗi 5 phút) nên chạy luôn, không cần công tắc .env riêng.
"""

import asyncio
import logging

log = logging.getLogger(__name__)

_CHU_KY_GIAY = 300


async def task_escalation_loop() -> None:
    from app.services import task_service

    while True:
        try:
            so = await asyncio.to_thread(task_service.quet_qua_han)
            if so:
                log.info("[tasks] %s viec qua han vua duoc danh dau bao quan ly", so)
        except Exception:  # noqa: BLE001 — worker nền không được chết vì 1 vòng lỗi
            log.exception("[tasks] quet qua han loi — bo qua vong nay")
        await asyncio.sleep(_CHU_KY_GIAY)
