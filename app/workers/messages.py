"""Worker FR-012: kéo nội dung tin nhắn Pancake về crm.messages.

Vòng riêng, tách khỏi poller (poller phục vụ bot phải nhanh; kéo tin tốn
1 lời gọi/hội thoại). Công tắc `MSG_SYNC_ENABLED` mặc định TẮT — bật ở màn
Cài đặt khi muốn tab Hội thoại trong CRM có nội dung thật. Nhịp + số hội
thoại mỗi vòng đọc lại MỖI LƯỢT (đổi trên web là lượt sau ăn ngay).
"""

import asyncio
import logging
import time

from app.core import runtime_config as cfg

log = logging.getLogger(__name__)

last_run: dict = {"luc": None, "ket_qua": None, "loi": None}


async def messages_loop() -> None:
    from app.integrations.pancake import message_sync

    while True:
        await asyncio.sleep(cfg.so("msg_sync_interval", 120))
        if not cfg.bat("msg_sync_enabled"):
            continue
        try:
            ket_qua = await message_sync.dong_bo_lo(int(cfg.so("msg_sync_batch", 20)))
            last_run.update(luc=time.strftime("%H:%M:%S"), ket_qua=ket_qua, loi=None)
            if ket_qua["hoi_thoai"] or ket_qua["loi"]:
                log.info("[msg] keo tin nhan: %s", ket_qua)
        except Exception as err:  # noqa: BLE001 — worker nền không chết vì 1 vòng lỗi
            last_run.update(luc=time.strftime("%H:%M:%S"), loi=str(err))
            log.exception("[msg] vong keo tin loi — bo qua vong nay")
