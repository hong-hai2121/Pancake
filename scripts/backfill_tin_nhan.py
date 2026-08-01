"""Backfill FR-012 — kéo LỊCH SỬ tin nhắn về crm.messages cho hội thoại cũ.

Worker msg-sync chỉ đuổi theo hội thoại CÓ TIN MỚI; kho hội thoại đã đồng bộ
từ trước (B2/backfill_crm_tu_watcher) thì `messages_synced_at` còn trống —
script này quét hết một lượt, chạy TAY, chạy lại được (idempotent nhờ unique
(conversation_id, external_message_id)).

Mỗi hội thoại tốn 1 lời gọi Pancake nên có nghỉ giữa nhịp (--nghi, mặc định
0.5s ~ 7200 hội thoại/giờ). Pancake giới hạn quota thì tăng lên.

Chạy:
    python scripts/backfill_tin_nhan.py                # toàn bộ tồn đọng
    python scripts/backfill_tin_nhan.py --gioi-han 200 # thử 200 hội thoại đầu
    python scripts/backfill_tin_nhan.py --nghi 1.0     # giãn nhịp gọi
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.repositories import conversation_repo  # noqa: E402
from app.integrations.pancake import client, message_sync  # noqa: E402


async def main(gioi_han: int, nghi: float) -> None:
    ton = conversation_repo.dem_ton_dong()
    print(f"Kho hội thoại: {ton['tong']} · chưa kéo tin: {ton['chua_keo']}"
          f" · có tin mới: {ton['co_tin_moi']}")
    lam = min(gioi_han, ton["chua_keo"] + ton["co_tin_moi"]) if gioi_han else None
    print(f"Bắt đầu kéo{f' (giới hạn {lam})' if lam else ''}, nghỉ {nghi}s/hội thoại…")

    xong = tin = 0
    da_loi: set[int] = set()   # mốc tươi của conv lỗi KHÔNG nhích -> sẽ bị nhặt
    bat_dau = time.monotonic()  # lại mãi; phiên này bỏ qua, worker/lượt sau kéo bù
    het = False
    while not het:
        # Nhặt theo mẻ nhỏ: mỗi hội thoại kéo xong là đóng dấu ngay nên vòng
        # sau tự trôi sang mẻ kế — dừng giữa chừng không mất gì.
        me = [c for c in conversation_repo.hoi_thoai_cho_dong_bo(limit=50 + len(da_loi))
              if c["id"] not in da_loi]
        if not me:
            break
        for conv in me:
            if gioi_han and xong + len(da_loi) >= gioi_han:
                het = True
                break
            try:
                tin += await message_sync.dong_bo_mot(conv)
                xong += 1
            except Exception as err:  # noqa: BLE001 — ghi nhận rồi đi tiếp
                da_loi.add(conv["id"])
                print(f"  LOI  conv {conv['external_conversation_id']}: "
                      f"{type(err).__name__}: {err}", file=sys.stderr)
            if xong % 100 == 0 and xong:
                toc_do = xong / (time.monotonic() - bat_dau)
                print(f"  … {xong} hội thoại · {tin} tin · {len(da_loi)} lỗi"
                      f" · {toc_do:.1f} hội thoại/s")
            await asyncio.sleep(nghi)

    print(f"XONG: {xong} hội thoại · {tin} tin nhắn mới · {len(da_loi)} lỗi"
          f" · {time.monotonic() - bat_dau:.0f}s")
    if da_loi:
        print("Hội thoại lỗi sẽ được worker msg-sync/retry kéo lại (mốc tươi chưa đóng).")
    await client.http().aclose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gioi-han", type=int, default=0,
                   help="chỉ kéo ngần này hội thoại (0 = hết tồn đọng)")
    p.add_argument("--nghi", type=float, default=0.5,
                   help="giây nghỉ giữa 2 hội thoại (chống 429)")
    a = p.parse_args()
    asyncio.run(main(a.gioi_han, a.nghi))
