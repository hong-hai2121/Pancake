"""Worker Đợt 3: mỗi ngày một lượt, luồng tự động SINH VIỆC cho nhân viên.

🔴 Worker này KHÔNG gửi tin. Nó gọi `auto_flow.sinh_viec()` — hàm đó đặt một
dòng vào `crm.tasks` rồi thôi. Người vẫn là người đọc và bấm gửi. Xem đầu
`services/auto_flow.py` để biết ba tầng chặn đường gửi.

Hai công tắc phải BẬT thì worker mới làm gì:
  * `auto_flow_task_enabled` — mặc định TẮT.
  * chính luồng đó ở trạng thái `active`.

Nhịp: kiểm mỗi 15 phút, nhưng CHỈ chạy khi tới `af_gio_quet` và hôm nay chưa
chạy. Không ngủ thẳng 24 giờ vì server hay được khởi động lại — ngủ nguyên ngày
thì có hôm không chạy lượt nào. Chạy thừa cũng vô hại: khoá duy nhất
(luồng, khách, ngày) ở DB làm mọi lượt sau trong ngày thành không-làm-gì.
"""

import asyncio
import logging

log = logging.getLogger(__name__)

_CHU_KY_GIAY = 900          # 15 phút
_da_chay: dict[str, object] = {"ngay": None}


async def auto_flow_viec_loop() -> None:
    from app.core import runtime_config

    while True:
        try:
            if runtime_config.bat("auto_flow_task_enabled"):
                await asyncio.to_thread(_mot_vong)
        except Exception:  # noqa: BLE001 — worker nền không chết vì 1 vòng lỗi
            log.exception("[auto-flow] quet loi — bo qua vong nay")
        await asyncio.sleep(_CHU_KY_GIAY)


def _mot_vong() -> None:
    from app.core.ngay import bay_gio, hom_nay
    from app.db.repositories import auto_flow_repo
    from app.services import auto_flow

    nay = hom_nay()
    if _da_chay["ngay"] == nay:
        return
    if bay_gio().hour < auto_flow.gio_quet():
        return                      # chưa tới giờ quét
    _da_chay["ngay"] = nay

    ds = auto_flow_repo.dang_chay()
    if not ds:
        log.info("[auto-flow] khong co luong nao dang bat")
        return
    tong = 0
    for f in ds:
        try:
            kq = auto_flow.sinh_viec(dict(f))
        except Exception:  # noqa: BLE001 — 1 luồng hỏng không dừng các luồng kia
            log.exception("[auto-flow] luong #%s loi", f["id"])
            continue
        tong += kq["da_sinh"]
        log.info("[auto-flow] luong #%s «%s»: xet %s · sinh %s viec · bo qua %s",
                 f["id"], f["name"], kq["xet"], kq["da_sinh"], kq["bo_qua"])
    log.info("[auto-flow] xong luot ngay %s — %s viec moi, 0 tin gui di",
             nay, tong)
