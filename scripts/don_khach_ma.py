"""Dọn "khách ma" tên `Khách chưa rõ tên` do script kiểm thử bỏ lại.

Vì sao có: `scripts/thu_b2.py` bắn một "row rác" (không tên, không định danh) để
thử `crm_sync.sync_batch` không vỡ. Row đó đẻ ra 1 khách mang tên mặc định
`Khách chưa rõ tên` + 1 lead tự động, mà hàm dọn của script chỉ xoá theo dấu
`__b2__` nên không với tới -> mỗi lần chạy bỏ lại 1 lead rác trên bảng việc Sale.
Gốc đã vá (`crm_sync._khong_khop_duoc`); script này dọn phần đã lỡ tích lại.

CHỈ xoá đúng dấu vân tay của rác: tên mặc định + nguồn pancake + không SĐT +
không định danh + không hội thoại + không đơn. Khách thật không thể rơi vào đây:
FR-020 bắt buộc mỗi hồ sơ có SĐT hoặc định danh MXH. Nhóm `pancake_pos` cùng tên
nhưng CÓ đơn thật (đơn nháp/huỷ 0đ bên POS không điền tên) — script không đụng.

Xoá khách là cascade: leads, lead_stage_history, tasks, customer_assignments...
đi theo. `crm.audit_logs` không có khoá ngoại nên vết tạo vẫn nằm lại — cố ý.

Chạy:  python scripts/don_khach_ma.py           # chạy khô, chỉ đếm và liệt kê
       python scripts/don_khach_ma.py --that    # xoá thật
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.client import get_pg_pool                    # noqa: E402

# Dấu vân tay của khách ma — dùng chung cho cả đếm lẫn xoá, khỏi lệch điều kiện.
_DIEU_KIEN = """
    c.full_name = 'Khách chưa rõ tên'
    and c.source = 'pancake'
    and c.primary_phone is null
    and not exists (select 1 from crm.customer_identities i where i.customer_id = c.id)
    and not exists (select 1 from crm.conversations v where v.customer_id = c.id)
    and not exists (select 1 from crm.orders o where o.customer_id = c.id)
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--that", action="store_true",
                    help="xoá thật (mặc định chỉ chạy khô)")
    args = ap.parse_args()

    pool = get_pg_pool()
    with pool.connection() as conn:
        rac = conn.execute(f"""
            select c.id, c.created_at,
                   (select count(*) from crm.leads l
                     where l.customer_id = c.id and l.closed_at is null) as lead_mo
              from crm.customers c where {_DIEU_KIEN} order by c.created_at
        """).fetchall()
        lead_mo_truoc = conn.execute(
            "select count(*) as n from crm.leads where closed_at is null"
        ).fetchone()["n"]
        # Nhóm cùng tên nhưng CÓ đơn thật — báo để biết, không xoá.
        con_lai = conn.execute(
            "select count(*) as n from crm.customers"
            " where full_name = 'Khách chưa rõ tên'"
        ).fetchone()["n"] - len(rac)

    print(f"Khách ma khớp dấu vân tay: {len(rac)}")
    print(f"  kèm theo {sum(r['lead_mo'] for r in rac)} lead đang mở "
          f"(bảng việc Sale hiện có {lead_mo_truoc} lead mở)")
    print(f"Cùng tên nhưng CÓ đơn/định danh thật — GIỮ NGUYÊN: {con_lai}")
    if rac:
        dau = ", ".join(str(r["id"]) for r in rac[:10])
        print(f"  id: {dau}{' ...' if len(rac) > 10 else ''}")
        print(f"  tạo từ {rac[0]['created_at']:%Y-%m-%d} đến "
              f"{rac[-1]['created_at']:%Y-%m-%d}")

    if not rac:
        print("Không có gì để dọn.")
        return
    if not args.that:
        print("\nCHẠY KHÔ — chưa xoá gì. Thêm --that để xoá thật.")
        return

    with pool.connection() as conn:
        n = conn.execute(
            f"delete from crm.customers c where {_DIEU_KIEN}"
        ).rowcount
        lead_mo_sau = conn.execute(
            "select count(*) as n from crm.leads where closed_at is null"
        ).fetchone()["n"]

    print(f"\nĐÃ XOÁ {n} khách ma.")
    print(f"Lead đang mở: {lead_mo_truoc} -> {lead_mo_sau} "
          f"(giảm {lead_mo_truoc - lead_mo_sau})")


if __name__ == "__main__":
    main()
