"""Worker mục 4: chạy lại hàng đợi lỗi đồng bộ + canh sức khoẻ token.

Hai việc, cùng một nhịp (mặc định 5 phút):

  1. **Retry queue** — bản ghi nào đồng bộ hỏng đã nằm sẵn ở `crm.sync_errors`
     kèm NGUYÊN VĂN dữ liệu; tới hạn thì chạy lại từ payload đó, KHÔNG gọi lại
     Pancake (dữ liệu cũ gọi lại cũng không còn). Backoff 5' → 15' → 45' → …,
     quá 5 lần thì given_up chờ người xử lý tay.
  2. **Cảnh báo token** — luật mục 4 "Token lỗi/hết hạn phải cảnh báo": mỗi
     `SYNC_TOKEN_CHECK_HOURS` giờ kiểm một lần, hỏng thì đánh dấu `token_status`
     để màn Tích hợp báo đỏ (+ log cảnh báo cho người vận hành thấy ngay).

Worker này chạy kể cả khi CRM_SYNC_ENABLED/POS_SYNC_ENABLED đang TẮT: lúc đó
hàng đợi rỗng nên nó gần như không tốn gì, còn tắt hẳn thì lỗi tồn đọng không ai
dọn. Công tắc riêng: `SYNC_RETRY_ENABLED`.
"""

import asyncio
import logging
import time

from app.core import runtime_config as cfg

log = logging.getLogger(__name__)

last_run: dict = {"luc": None, "ket_qua": None, "loi": None, "token": None}


async def _kiem_token() -> dict:
    """Kiểm token của mọi kết nối; trả {tên kết nối: ok?}."""
    from app.db.repositories import integration_repo
    from app.services import integration_service

    ra: dict[str, bool] = {}
    integration_service.dam_bao_ket_noi()
    for acc in await asyncio.to_thread(integration_repo.list_accounts):
        kq = await integration_service.kiem_tra_ket_noi(acc["id"])
        ra[acc["name"]] = bool(kq.get("ok"))
        if not kq.get("ok"):
            log.warning("[sync] TOKEN HỎNG · %s · %s", acc["name"], kq.get("message"))
    return ra


async def sync_retry_loop() -> None:
    from app.services import integration_service

    lan_kiem_token = 0.0
    while True:
        # Đọc lại MỖI vòng (không dùng settings.* đọc-một-lần) — đổi trên màn
        # Cài đặt là lượt sau ăn ngay, khỏi khởi động lại server.
        await asyncio.sleep(cfg.so("sync_retry_interval", 300))
        if not cfg.bat("sync_retry_enabled"):
            continue
        try:
            ket_qua = await asyncio.to_thread(
                integration_service.chay_hang_doi, int(cfg.so("sync_retry_batch", 50)))
            last_run.update(luc=time.strftime("%H:%M:%S"), ket_qua=ket_qua, loi=None)
            if ket_qua["da_thu"]:
                log.info("[sync] hang doi loi: %s", ket_qua)

            if time.monotonic() - lan_kiem_token > cfg.so("sync_token_check_hours", 6) * 3600:
                lan_kiem_token = time.monotonic()
                last_run["token"] = await _kiem_token()
        except Exception as err:  # noqa: BLE001 — worker nền không chết vì 1 vòng lỗi
            last_run.update(luc=time.strftime("%H:%M:%S"), loi=str(err))
            log.exception("[sync] vong retry loi — bo qua vong nay")
