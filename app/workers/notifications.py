"""Worker màn 3: quét 11 nguồn sinh thông báo + dọn thông báo cũ đã đọc.

Chạy tách khỏi các worker khác vì nó chỉ đọc/ghi DB nội bộ (không gọi Pancake),
nhịp thưa (mặc định 5 phút). Công tắc `NOTIFY_SCAN_ENABLED` mặc định **BẬT** —
khác các đồng bộ Pancake: thông báo không tạo dữ liệu nghiệp vụ, chỉ nhặt sự
việc đã có sẵn trong DB nên bật luôn là an toàn.
"""

import asyncio
import logging
import time

from app.core import runtime_config as cfg

log = logging.getLogger(__name__)

last_run: dict = {"luc": None, "ket_qua": None, "loi": None}

_DON_RAC_MOI = 24 * 3600.0   # dọn thông báo cũ 1 lần/ngày


async def notifications_loop() -> None:
    from app.db.repositories import notification_repo
    from app.services import notification_service

    lan_don_rac = 0.0
    while True:
        await asyncio.sleep(cfg.so("notify_scan_interval", 300))
        if not cfg.bat("notify_scan_enabled"):
            continue
        try:
            ket_qua = await asyncio.to_thread(notification_service.quet_tat_ca)
            last_run.update(luc=time.strftime("%H:%M:%S"), ket_qua=ket_qua, loi=None)
            if sum(ket_qua.values()):
                log.info("[notify] thông báo mới: %s",
                         {k: v for k, v in ket_qua.items() if v})

            if time.monotonic() - lan_don_rac > _DON_RAC_MOI:
                lan_don_rac = time.monotonic()
                xoa = await asyncio.to_thread(
                    notification_repo.don_rac, int(cfg.so("notify_keep_days", 60)))
                if xoa:
                    log.info("[notify] dọn %s thông báo đã đọc quá cũ", xoa)
        except Exception as err:  # noqa: BLE001 — worker nền không chết vì 1 vòng lỗi
            last_run.update(luc=time.strftime("%H:%M:%S"), loi=str(err))
            log.exception("[notify] vòng quét lỗi — bỏ qua vòng này")
