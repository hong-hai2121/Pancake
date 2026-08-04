"""Seed nhóm ƯU ĐÃI + TIỀN — hạng thẻ, quyền lợi, bậc lương (C1 + C2).

Nạp vào schema `crm`:
  1. card_ranks         — 5 bậc thang hạng thẻ + ngưỡng chi tiêu
  2. card_rank_benefits — quyền lợi khai theo BẬC SO SÁNH ĐƯỢC (nền cho luật
                          "180 ngày không mua thì hưởng quyền lợi thấp hơn 1 bậc")
  3. commission_tiers · care_bonus_tiers · hot_bonus_tiers — bậc hoa hồng,
     thưởng chăm sóc, thưởng nóng theo VAI TRÒ (C2)

Về hạng thứ 6 "Chưa xếp hạng": CỐ Ý không có dòng trong card_ranks. Khách chưa
đủ ngưỡng nào thì `customers.card_rank` để NULL — thêm một dòng "chua_xep_hang"
vào bậc thang sẽ khiến luật "chỉ nâng" coi nó là một hạng thật và không ai thoát
ra được nữa.

Idempotent: chạy lại thì CẬP NHẬT tên/ngưỡng theo file này (đây là nguồn sự
thật của bậc thang, không phải DB). Quyền lợi thì xoá-rồi-nạp-lại theo hạng.

Chạy:  python scripts/seed_uu_dai.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.client import get_pg_pool  # noqa: E402

# (mã, tên, emoji, ngưỡng từ, ngưỡng đến, thứ tự)
# Ngưỡng theo mẫu: Diamond >10tr · Gold 5–10tr · Silver 3–<5tr · Member 1–<3tr
# · New Member >0–<1tr. `den = None` = không có trần (hạng cao nhất).
HANG_THE: list[tuple[str, str, str, int, int | None, int]] = [
    ("diamond",    "Diamond",    "💎", 10_000_000, None,        5),
    ("gold",       "Gold",       "🥇",  5_000_000, 10_000_000,  4),
    ("silver",     "Silver",     "🥈",  3_000_000,  5_000_000,  3),
    ("member",     "Member",     "🎫",  1_000_000,  3_000_000,  2),
    ("new_member", "New Member", "🆕",          1,  1_000_000,  1),
]

# Quyền lợi mẫu — khai bằng cặp (tên quyền lợi, giá trị) để SO SÁNH ĐƯỢC giữa
# các bậc. Đây là số gợi ý; sửa ở màn Cài đặt → Hạng thẻ cho khớp chính sách thật.
QUYEN_LOI: dict[str, list[tuple[str, str]]] = {
    "diamond":    [("Chiết khấu", "15%"), ("Quà sinh nhật", "có"),
                   ("Freeship", "mọi đơn"), ("Ưu tiên tư vấn", "có")],
    "gold":       [("Chiết khấu", "10%"), ("Quà sinh nhật", "có"),
                   ("Freeship", "đơn từ 500k")],
    "silver":     [("Chiết khấu", "7%"), ("Freeship", "đơn từ 1tr")],
    "member":     [("Chiết khấu", "5%")],
    "new_member": [("Chiết khấu", "3%")],
}


# ============================================================
# C2 — bậc lương/thưởng. TẤT CẢ là số GỢI Ý để màn hình có dữ liệu chạy thật;
# sửa cho khớp chính sách công ty ở màn /crm/bac-luong.
# ============================================================

# Lương cứng mặc định theo vai trò (đè riêng từng người ở users.base_salary)
LUONG_CUNG: dict[str, int] = {
    "Sale": 5_000_000, "Trưởng nhóm Sale": 8_000_000,
    "CSKH": 5_000_000, "Trưởng nhóm CSKH": 8_000_000,
    "Marketing": 8_000_000, "Kế toán": 8_000_000,
    "Người chuyên môn": 10_000_000,
}

# Hoa hồng: (ngưỡng doanh thu ĐÃ THU của kỳ, kiểu, giá trị).
# Áp bậc CAO NHẤT chạm tới — KHÔNG cộng dồn các bậc.
HOA_HONG: dict[str, list[tuple[int, str, float]]] = {
    "Sale": [(50_000_000, "phan_tram", 2), (100_000_000, "phan_tram", 3),
             (200_000_000, "phan_tram", 4)],
    "Trưởng nhóm Sale": [(100_000_000, "phan_tram", 2),
                          (200_000_000, "phan_tram", 3)],
    "CSKH": [(30_000_000, "phan_tram", 2), (60_000_000, "phan_tram", 3)],
    "Trưởng nhóm CSKH": [(60_000_000, "phan_tram", 2),
                          (120_000_000, "phan_tram", 3)],
}

# Thưởng chăm sóc: (ngưỡng giá trị TỪNG ĐƠN, kiểu, giá trị).
# LUẬT 1 — khoản này CỘNG THÊM vào hoa hồng, không thay thế.
THUONG_CHAM: dict[str, list[tuple[int, str, float]]] = {
    "CSKH": [(0, "tien", 20_000), (1_000_000, "tien", 50_000),
             (3_000_000, "phan_tram", 3)],
    "Trưởng nhóm CSKH": [(0, "tien", 10_000), (3_000_000, "phan_tram", 2)],
}

# Thưởng nóng: (kiểu xét, ngưỡng, kiểu thưởng, giá trị).
# LUẬT 2 — hai kiểu CHẠY SONG SONG và CỘNG DỒN.
THUONG_NONG: dict[str, list[tuple[str, int, str, float]]] = {
    "Sale": [("doanh_thu_ngay", 10_000_000, "tien", 200_000),
             ("doanh_thu_ngay", 20_000_000, "tien", 500_000),
             ("gia_tri_don", 5_000_000, "tien", 100_000),
             ("gia_tri_don", 10_000_000, "tien", 300_000)],
    "CSKH": [("doanh_thu_ngay", 5_000_000, "tien", 100_000),
             ("gia_tri_don", 3_000_000, "tien", 100_000)],
}


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        for ma, ten, emoji, tu, den, thu_tu in HANG_THE:
            conn.execute(
                """
                insert into crm.card_ranks
                       (code, name, emoji, min_spent, max_spent, sort_order)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (code) do update set
                    name = excluded.name, emoji = excluded.emoji,
                    min_spent = excluded.min_spent,
                    max_spent = excluded.max_spent,
                    sort_order = excluded.sort_order
                """,
                (ma, ten, emoji, tu, den, thu_tu),
            )

        for ma, ds in QUYEN_LOI.items():
            conn.execute("delete from crm.card_rank_benefits where rank_code = %s",
                         (ma,))
            for i, (khoa, gia_tri) in enumerate(ds):
                conn.execute(
                    "insert into crm.card_rank_benefits "
                    "(rank_code, benefit_key, benefit_value, sort_order) "
                    "values (%s, %s, %s, %s)",
                    (ma, khoa, gia_tri, i),
                )

        # --- C2: bậc lương/thưởng theo vai trò ---
        vai = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        for bang, ds in (("commission_tiers", HOA_HONG),
                         ("care_bonus_tiers", THUONG_CHAM)):
            for ten_vai, bac in ds.items():
                rid = vai.get(ten_vai)
                if not rid:
                    continue
                conn.execute(f"delete from crm.{bang} where role_id = %s", (rid,))
                for i, (nguong, kieu, gia_tri) in enumerate(bac):
                    conn.execute(
                        f"insert into crm.{bang} (role_id, min_revenue, kind, "
                        "value, sort_order) values (%s, %s, %s, %s, %s)",
                        (rid, nguong, kieu, gia_tri, i))
        for ten_vai, bac in THUONG_NONG.items():
            rid = vai.get(ten_vai)
            if not rid:
                continue
            conn.execute("delete from crm.hot_bonus_tiers where role_id = %s",
                         (rid,))
            for i, (kieu_xet, nguong, kieu, gia_tri) in enumerate(bac):
                conn.execute(
                    "insert into crm.hot_bonus_tiers (role_id, basis, threshold,"
                    " kind, value, sort_order) values (%s, %s, %s, %s, %s, %s)",
                    (rid, kieu_xet, nguong, kieu, gia_tri, i))
        # Lương cứng mặc định theo vai trò (đè riêng từng người ở users.base_salary)
        for ten_vai, tien in LUONG_CUNG.items():
            conn.execute("update crm.roles set base_salary = %s where name = %s",
                         (tien, ten_vai))

        # In KHÔNG dấu: console Windows dùng cp1252, gặp chữ có dấu là ném
        # UnicodeEncodeError NGAY TRONG khối `with` -> rollback mất cả seed.
        for cau, nhan in [
            ("select count(*) as n from crm.card_ranks", "hang the"),
            ("select count(*) as n from crm.card_rank_benefits", "quyen loi"),
            ("select count(*) as n from crm.vouchers", "voucher"),
            ("select count(*) as n from crm.commission_tiers", "bac hoa hong"),
            ("select count(*) as n from crm.care_bonus_tiers", "bac thuong cham"),
            ("select count(*) as n from crm.hot_bonus_tiers", "bac thuong nong"),
        ]:
            print(f"  {nhan}: {conn.execute(cau).fetchone()['n']}")
    print("Seed uu dai xong. Bam 'Tinh lai hang' o man /crm/hang-the de xep "
          "hang cho khach theo nguong vua nap.")


if __name__ == "__main__":
    main()
