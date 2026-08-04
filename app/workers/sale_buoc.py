"""Worker C5: dò lại con trỏ thang bám đuổi Sale từ tin nhắn thật.

Mỗi vòng làm hai việc:

  1. **Nhả cột đặt tay đã cũ** — thẻ bị đặt "Từ chối đợt này" mà khách nhắn
     lại SAU lúc đặt thì tự quay về bảng. Không có bước này thì khách quay lại
     mà thẻ vẫn nằm im trong cột Từ chối, không ai thấy.
  2. **Dò lại con trỏ** cho lead có tin mới. Con trỏ CHỈ TIẾN nên chạy lại
     bao nhiêu lần cũng không sai.

Nhịp 10 phút: nhân viên nhắn xong muốn thấy bước kế hiện lên khá nhanh, nhưng
dò một lead phải đọc tới 500 tin nên cũng không chạy dày hơn được.

Công tắc `sale_scan_enabled` ở Cài đặt → Thang bám đuổi Sale.
"""

import asyncio
import logging

log = logging.getLogger(__name__)

_CHU_KY_GIAY = 600


async def sale_buoc_loop() -> None:
    from app.core import runtime_config

    while True:
        try:
            if runtime_config.bat("sale_scan_enabled"):
                kq = await asyncio.to_thread(_mot_vong)
                if kq and (kq["doi_con_tro"] or kq["nha_cot"]):
                    log.info("[sale_buoc] %s the doi con tro · %s the nha cot",
                             kq["doi_con_tro"], kq["nha_cot"])
        except Exception:  # noqa: BLE001 — worker nền không chết vì 1 vòng lỗi
            log.exception("[sale_buoc] mot vong loi — bo qua")
        await asyncio.sleep(_CHU_KY_GIAY)


def _mot_vong() -> dict:
    from app.services import sale_service

    return sale_service.quet_tat_ca()
