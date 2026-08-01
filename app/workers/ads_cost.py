"""Worker mục 4 (nguồn quảng cáo): kéo cây quảng cáo + chi phí theo ngày.

Nhịp: mỗi `ADS_SYNC_INTERVAL` giây (mặc định 6 giờ) làm 2 việc:
  1. đồng bộ CÂY (campaign → adset → ad) — cấu trúc ít đổi nên hỏi thưa cũng đủ;
  2. đồng bộ CHI PHÍ của **hôm nay và hôm qua** — số của ngày đang chạy còn nhảy,
     mà Facebook cũng chốt số muộn, nên ngày hôm qua phải hỏi lại ít nhất một lần
     nữa. Ghi đè theo (thực thể, ngày) nên hỏi lại bao nhiêu lần cũng không cộng dồn.

Lịch sử xa hơn KHÔNG tự về — chạy `scripts/backfill_quang_cao.py --so-ngay 90`.

Công tắc `ADS_SYNC_ENABLED` mặc định TẮT (giống CRM_SYNC/POS_SYNC): bật lên là
bắt đầu gọi Pancake POS đều đặn.
"""

import asyncio
import logging
import time
from datetime import date, timedelta

from app.core import runtime_config as cfg

log = logging.getLogger(__name__)

last_run: dict = {"luc": None, "cay": None, "chi_phi": None, "loi": None}


async def ads_cost_loop() -> None:
    from app.integrations.pancake_pos import ads_sync

    while True:
        await asyncio.sleep(cfg.so("ads_sync_interval", 21600))
        if not cfg.bat("ads_sync_enabled"):
            continue
        try:
            cay = await ads_sync.dong_bo_cay(so_ngay=int(cfg.so("ads_sync_tree_days", 90)))
            tong = {"cap_nhat": 0, "loi": 0}
            for lui in (0, 1):
                kq = await ads_sync.dong_bo_chi_phi(date.today() - timedelta(days=lui))
                tong["cap_nhat"] += kq["cap_nhat"]
                tong["loi"] += kq["loi"]
            last_run.update(luc=time.strftime("%H:%M:%S"), cay=cay, chi_phi=tong,
                            loi=None)
            log.info("[ads] cay=%s chi_phi=%s", cay, tong)
        except Exception as err:  # noqa: BLE001 — worker nền không chết vì 1 vòng lỗi
            last_run.update(luc=time.strftime("%H:%M:%S"), loi=str(err))
            log.exception("[ads] vong dong bo quang cao loi — bo qua vong nay")
