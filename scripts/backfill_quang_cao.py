"""Backfill cây quảng cáo + CHI PHÍ theo ngày từ Pancake POS Ads Manager.

Worker `ads_cost` chỉ giữ tươi hôm nay/hôm qua; lịch sử đổ về bằng script này.
Idempotent: mỗi (thực thể, ngày) một dòng, chạy lại là ghi đè chứ không cộng dồn.

Chạy:
    python scripts/backfill_quang_cao.py                      # 30 ngày gần nhất
    python scripts/backfill_quang_cao.py --so-ngay 90         # 90 ngày
    python scripts/backfill_quang_cao.py --tu 2026-06-01 --den 2026-06-30
    python scripts/backfill_quang_cao.py --bo-qua-ngay-da-co  # chỉ ngày còn thiếu

Mỗi ngày = 3 lời gọi API (campaign/adset/ad), nên 90 ngày ~ 270 lời gọi — chạy
mất vài phút, cứ để nó chạy. `--nghi` giãn nhịp nếu POS trả 429.
"""

import argparse
import asyncio
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.repositories import ads_repo                      # noqa: E402
from app.integrations.pancake_pos import ads_sync             # noqa: E402


def _ngay(chuoi: str | None) -> date | None:
    return datetime.fromisoformat(chuoi).date() if chuoi else None


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--so-ngay", type=int, default=30, help="Số ngày gần nhất (mặc định 30)")
    p.add_argument("--tu", help="Từ ngày (ISO) — dùng thay --so-ngay")
    p.add_argument("--den", help="Đến ngày (ISO), mặc định hôm nay")
    p.add_argument("--bo-qua-ngay-da-co", action="store_true",
                   help="Bỏ qua ngày đã có dữ liệu chi phí")
    p.add_argument("--nghi", type=float, default=0.0,
                   help="Nghỉ bao nhiêu giây giữa 2 ngày (khi POS trả 429)")
    p.add_argument("--bo-qua-cay", action="store_true",
                   help="Chỉ kéo chi phí, không đồng bộ lại cây")
    args = p.parse_args()

    den = _ngay(args.den) or date.today()
    tu = _ngay(args.tu) or (den - timedelta(days=args.so_ngay - 1))
    if tu > den:
        print(f"[backfill-ads] --tu ({tu}) muộn hơn --den ({den})")
        return 2

    bat_dau = time.monotonic()
    if not args.bo_qua_cay:
        so_ngay_cay = (date.today() - tu).days + 1
        cay = await ads_sync.dong_bo_cay(so_ngay=max(so_ngay_cay, 30))
        print(f"[backfill-ads] cây quảng cáo: {cay}")

    da_co = ads_repo.ngay_da_co_chi_phi(tu.isoformat(), den.isoformat()) \
        if args.bo_qua_ngay_da_co else set()

    tong = {"dong": 0, "loi": 0, "ngay": 0, "bo_qua_ngay": 0}
    n = tu
    while n <= den:
        if n in da_co:
            tong["bo_qua_ngay"] += 1
            n += timedelta(days=1)
            continue
        kq = await ads_sync.dong_bo_chi_phi(n)
        tong["ngay"] += 1
        tong["dong"] += kq["cap_nhat"]
        tong["loi"] += kq["loi"]
        print(f"[backfill-ads] {n}: {kq['cap_nhat']} dòng"
              f"{' · LỖI' if kq['loi'] else ''}")
        if args.nghi:
            await asyncio.sleep(args.nghi)
        n += timedelta(days=1)

    thieu = ads_sync.thong_ke_thieu_chi_phi()
    giay = round(time.monotonic() - bat_dau, 1)
    print(f"\n[backfill-ads] XONG {tu} → {den} trong {giay}s: {tong}")
    if thieu["ad_co_doanh_thu"]:
        print(f"[backfill-ads] {thieu['ad_co_chi_phi']}/{thieu['ad_co_doanh_thu']} "
              "quảng cáo có doanh thu là có chi phí — phần còn lại thuộc tài khoản "
              "quảng cáo chưa nối vào POS (POS → Ads Manager → thêm tài khoản)")
    return 1 if tong["loi"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
