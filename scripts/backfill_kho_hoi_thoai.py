"""Lấp dữ liệu đầy đủ (cột `raw` + SĐT, người gửi cuối…) cho hội thoại CŨ trong kho.

Vì sao cần: kho `watcher.hoi_thoai` ban đầu chỉ lưu 12 trường rút gọn. Sau khi
thêm cột `raw` + nhóm cột mới, dòng CŨ vẫn trống các cột đó — và worker poller
sẽ KHÔNG tự lấp, vì nó cố tình chỉ ghi những hội thoại mới hơn mốc đã biết (xem
`_fetch_page` trong app/workers/poller.py). Script này chạy MỘT LẦN để kéo lại
một mẻ lớn của từng page rồi ghi đè đầy đủ.

    python -m scripts.backfill_kho_hoi_thoai              # xem trước, KHÔNG ghi
    python -m scripts.backfill_kho_hoi_thoai --apply      # ghi thật
    python -m scripts.backfill_kho_hoi_thoai --apply --limit 200   # kéo sâu hơn

Đi NHẸ TAY với Pancake: mỗi lượt chỉ 2 page song song và nghỉ giữa các lượt —
Pancake trả 429 chỉ sau vài lời gọi dồn dập. Với ~22 page thì chạy hết khoảng
1 phút.

Giới hạn không tránh được: API chỉ trả về N hội thoại MỚI NHẤT của mỗi page, nên
hội thoại quá cũ (rơi khỏi khung đó) sẽ mãi không có `raw`. Tăng `--limit` để
với sâu hơn.
"""

import argparse
import asyncio
import sys

from app.db import inbox_store
from app.pancake.client import close_http, enabled_pages, fetch_conversations_fresh

# Số page gọi song song + nghỉ giữa 2 lượt (giây) — cố ý chậm hơn worker.
_SONG_SONG = 2
_NGHI = 1.5


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="ghi thật (mặc định chạy khô)")
    ap.add_argument("--limit", type=int, default=50,
                    help="số hội thoại mới nhất kéo về mỗi page (mặc định 50)")
    args = ap.parse_args()

    truoc = await asyncio.to_thread(inbox_store.stats_raw)
    print(f"Kho hiện có {truoc['tong']} hội thoại, {truoc['co_raw']} dòng đã có `raw`.")
    pages = await enabled_pages()
    print(f"{len(pages)} page đang BẬT · sẽ kéo {args.limit} hội thoại/page "
          f"({_SONG_SONG} page song song, nghỉ {_NGHI}s giữa các lượt)")

    if not args.apply:
        print("\n(chạy khô — thêm --apply để ghi thật)")
        await close_http()
        return 0

    tong_ghi = loi = 0
    for i in range(0, len(pages), _SONG_SONG):
        lo = pages[i:i + _SONG_SONG]

        async def one(page: dict) -> int:
            convs = await fetch_conversations_fresh(page["id"], limit=args.limit)
            if not convs:
                return 0
            await asyncio.to_thread(
                inbox_store.upsert_conversations,
                page["id"], page.get("name") or "", convs,
            )
            return len(convs)

        for page, kq in zip(lo, await asyncio.gather(*(one(p) for p in lo),
                                                    return_exceptions=True)):
            ten = (page.get("name") or page["id"])[:40]
            if isinstance(kq, int):
                tong_ghi += kq
                print(f"  {ten:<42} {kq} hội thoại")
            else:
                loi += 1
                print(f"  {ten:<42} LỖI {type(kq).__name__}: {str(kq)[:60]}")
        if i + _SONG_SONG < len(pages):
            await asyncio.sleep(_NGHI)

    sau = await asyncio.to_thread(inbox_store.stats_raw)
    print(f"\nĐã gửi {tong_ghi} hội thoại vào kho ({loi} page lỗi).")
    print(f"Dòng có `raw`: {truoc['co_raw']} -> {sau['co_raw']} / {sau['tong']}")
    await close_http()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
