"""Backfill B2: đổ kho hội thoại CŨ (watcher.hoi_thoai) vào CRM một lần.

Poller chỉ đồng bộ hội thoại MỚI từ lúc bật CRM_SYNC_ENABLED — kho cũ (~1.5k
hội thoại) chạy tay script này. Idempotent: chạy lại không tạo trùng (chống
trùng 4 bậc của FR-011 nằm trong customer_service.upsert_from_source).

Chạy:  python scripts/backfill_crm_tu_watcher.py           # toàn bộ
       python scripts/backfill_crm_tu_watcher.py --limit 50  # chạy thử
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.client import get_pg_pool                    # noqa: E402
from app.integrations.pancake import crm_sync            # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = toàn bộ")
    args = ap.parse_args()

    pool = get_pg_pool()
    with pool.connection() as conn:
        cau = (
            "select page_id, page_name, conv_id, customer_id, name, fb_id, "
            "phones, updated_at from watcher.hoi_thoai order by updated_at"
        )
        if args.limit:
            cau += f" limit {int(args.limit)}"
        rows = conn.execute(cau).fetchall()

    print(f"Đổ {len(rows)} hội thoại từ watcher.hoi_thoai vào CRM...")
    tong = {"tao_moi": 0, "cap_nhat": 0, "loi": 0}
    for i, r in enumerate(rows, 1):
        kq = crm_sync.sync_batch(r["page_id"], r.get("page_name") or "", [r])
        for k in tong:
            tong[k] += kq[k]
        if i % 200 == 0:
            print(f"  ...{i}/{len(rows)}  {tong}")

    print(f"XONG: {tong}")
    with pool.connection() as conn:
        n = conn.execute(
            "select count(*) as n from crm.customers where source = 'pancake'"
        ).fetchone()["n"]
        v = conn.execute("select count(*) as n from crm.conversations").fetchone()["n"]
        print(f"CRM hiện có: {n} khách nguồn pancake · {v} hội thoại")


if __name__ == "__main__":
    main()
