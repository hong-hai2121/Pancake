"""Worker B7: kéo đơn Pancake POS mới cập nhật về crm.orders theo chu kỳ.

Chiến lược POLL BÙ: mỗi vòng hỏi POS "đơn nào ĐỔI từ mốc lần trước tới giờ"
(lọc updateStatus=updated_at) rồi đổ qua pos_sync. Webhook POS (PUT /shops/{id}
bật webhook_types=["orders"]) sẽ thay thế vai trò chính KHI app đã có domain
công khai — hiện app chạy local, POS không gọi vào được, nên poll là đường duy
nhất. Mốc lần trước trừ lùi 120s (đè lên nhau một đoạn) để không lọt đơn đổi
đúng khe giữa 2 vòng; trùng thì pos_sync tự bỏ qua (idempotent).

Đơn CŨ (trước lúc bật worker) không tự về — chạy scripts/backfill_don_pos.py.

Công tắc: POS_SYNC_ENABLED trong .env (mặc định TẮT — giống CRM_SYNC_ENABLED).
Task chỉ được tạo khi có đủ PANCAKE_POS_API_KEY + PANCAKE_POS_SHOP_ID (xem
app/main.py); công tắc kiểm lại mỗi vòng nên .env bật/tắt chỉ cần restart server.
"""

import asyncio
import logging
import time

from app.core.config import settings

log = logging.getLogger(__name__)

# Soi nhanh qua /poller giống 2 worker kia
last_run: dict = {"luc": None, "ket_qua": None, "loi": None}


async def pos_orders_loop() -> None:
    from app.integrations.pancake_pos import client, pos_sync

    # Vòng đầu kéo lùi 1 chu kỳ cho ấm máy; lịch sử xa hơn là việc của backfill.
    moc_truoc = time.time() - settings.pos_sync_interval

    while True:
        await asyncio.sleep(settings.pos_sync_interval)
        if not settings.pos_sync_enabled:
            continue
        try:
            since = int(moc_truoc - 120)   # đè 120s — thà trùng (tự bỏ qua) còn hơn lọt
            moc_truoc = time.time()

            dons: list[dict] = []
            trang = 1
            while True:
                data = await client.list_orders(
                    page_number=trang, page_size=100,
                    since=since, update_status="updated_at",
                )
                mot_trang = [d for d in data.get("data") or [] if isinstance(d, dict)]
                dons.extend(mot_trang)
                if trang >= int(data.get("total_pages") or 1) or not mot_trang:
                    break
                trang += 1

            if dons:
                ket_qua = await asyncio.to_thread(pos_sync.sync_batch, dons)
                last_run.update(luc=time.strftime("%H:%M:%S"), ket_qua=ket_qua, loi=None)
                if ket_qua["tao_moi"] or ket_qua["cap_nhat"] or ket_qua["loi"]:
                    log.info("[pos] %s don POS: %s", len(dons), ket_qua)
        except Exception as err:  # noqa: BLE001 — worker nền không chết vì 1 vòng lỗi
            last_run.update(luc=time.strftime("%H:%M:%S"), loi=str(err))
            log.exception("[pos] keo don POS loi — bo qua vong nay")
