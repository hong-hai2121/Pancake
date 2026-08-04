"""Worker C2: tính lại lương kỳ hiện tại + truy thu đơn hoàn kỳ đã chốt.

Hai việc:

  1. Tính lại lương KỲ HIỆN TẠI cho mọi người có đơn. Nhân viên mở màn "Thu
     nhập của tôi" lúc nào cũng thấy số mới, không phải chờ ai bấm nút. Kỳ đã
     chốt được repo từ chối ghi đè (`payrolls.frozen`) nên chạy thừa vô hại.
  2. LUẬT 3 — đơn hoàn/huỷ mà kỳ lương của nó ĐÃ CHỐT: ghi một dòng
     `payroll_adjustments` ÂM vào kỳ sau. Mỗi đơn đúng một lần (unique index
     trên order_id), nên chạy lại không nhân đôi khoản trừ.

Nhịp 30 phút: tiền không cần realtime, mà tính lương quét toàn bộ đơn của kỳ
nên cũng không nên chạy dày.
"""

import asyncio
import logging

log = logging.getLogger(__name__)

_CHU_KY_GIAY = 1800


async def luong_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_mot_vong)
        except Exception:  # noqa: BLE001 — worker nền không chết vì 1 vòng lỗi
            log.exception("[luong] tinh lai loi — bo qua vong nay")
        await asyncio.sleep(_CHU_KY_GIAY)


def _mot_vong() -> None:
    from app.services import payroll_service

    ds = payroll_service.tinh_ca_doi(ghi=True)
    if ds:
        log.info("[luong] da tinh lai %s dong luong ky hien tai", len(ds))
    truy_thu = payroll_service.truy_thu_don_hoan()
    if truy_thu:
        log.info("[luong] %s don hoan sau chot ky -> tru vao ky sau",
                 len(truy_thu))
