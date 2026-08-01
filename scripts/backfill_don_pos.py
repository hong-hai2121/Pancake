"""Backfill đơn hàng Pancake POS về crm.orders (B7) — chạy tay, idempotent.

Worker pos_orders chỉ kéo đơn ĐỔI TỪ LÚC BẬT trở đi; đơn cũ (shop đang có ~53k)
đổ về bằng script này. Chạy lại thoải mái: đơn đã có + POS không đổi -> bỏ qua.

Chạy:
    python scripts/backfill_don_pos.py                     # toàn bộ, cũ -> mới
    python scripts/backfill_don_pos.py --tu 2026-07-01     # từ ngày (theo ngày TẠO đơn)
    python scripts/backfill_don_pos.py --tu 2026-07-01 --den 2026-08-01
    python scripts/backfill_don_pos.py --so-trang 5        # chạy thử 5 trang đầu

Lưu ý: kéo theo mốc TẠO ĐƠN (inserted_at) và lật trang từ CŨ -> MỚI để phân
loại đơn đầu/mua lại đúng ngay cả trong 1 lần chạy (đơn đầu của khách vào DB
trước đơn sau của chính khách đó).
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations.pancake_pos import client, pos_sync   # noqa: E402


def _unix(chuoi: str | None) -> int | None:
    if not chuoi:
        return None
    return int(datetime.fromisoformat(chuoi).timestamp())


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tu", help="Lấy đơn TẠO từ ngày này (ISO, vd 2026-07-01)")
    p.add_argument("--den", help="Đến ngày này (ISO)")
    p.add_argument("--so-trang", type=int, default=0, help="Giới hạn số trang (0 = hết)")
    p.add_argument("--page-size", type=int, default=100)
    args = p.parse_args()

    tong = {"tao_moi": 0, "cap_nhat": 0, "bo_qua": 0, "loi": 0}
    bat_dau = time.monotonic()

    # Trang đầu để biết total_pages, rồi đi NGƯỢC từ trang cuối về trang 1:
    # POS trả mới nhất trước, nên trang cuối = đơn cũ nhất -> xử lý trước.
    dau = await client.list_orders(
        page_number=1, page_size=args.page_size,
        since=_unix(args.tu), until=_unix(args.den),
        update_status="inserted_at",
    )
    total_pages = int(dau.get("total_pages") or 1)
    print(f"Tổng {dau.get('total_entries')} đơn / {total_pages} trang "
          f"(page_size={args.page_size})")

    cac_trang = list(range(total_pages, 0, -1))
    if args.so_trang:
        cac_trang = cac_trang[: args.so_trang]

    for i, trang in enumerate(cac_trang, 1):
        data = dau if trang == 1 else await client.list_orders(
            page_number=trang, page_size=args.page_size,
            since=_unix(args.tu), until=_unix(args.den),
            update_status="inserted_at",
        )
        dons = [d for d in data.get("data") or [] if isinstance(d, dict)]
        # Trong 1 trang cũng phải cũ -> mới (POS xếp mới nhất trước)
        ket_qua = await asyncio.to_thread(pos_sync.sync_batch, list(reversed(dons)))
        for k in tong:
            tong[k] += ket_qua[k]
        print(f"  [{i}/{len(cac_trang)}] trang {trang}: {len(dons)} đơn -> {ket_qua} "
              f"| cộng dồn: {tong}")

    phut = (time.monotonic() - bat_dau) / 60
    print(f"\nXong sau {phut:.1f} phút: {tong}")
    return 1 if tong["loi"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
