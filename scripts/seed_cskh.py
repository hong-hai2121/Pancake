"""Dựng THANG MỐC CSKH (C6) từ cấu hình đang chạy.

Thang KHÔNG chép tay: sinh từ ba con số ở Cài đặt → nhóm "Quy trình CSKH"
  * cskh_first_milestone  — mốc chăm định kỳ đầu tiên (mặc định 45)
  * cskh_milestone_gap    — hai mốc cách nhau (mặc định 15)
  * cskh_leave_days       — khách rời bảng (mặc định 210)

⇒ D45 · D60 · D75 · D90 · D105 · D120 · D135 · D150 · D165 · D180 · D195
  rồi D210 = BUÔNG. Cờ khuyến mãi gắn XEN KẼ (D45 · D75 · D105 · D135 · D165 ·
  D195) — mốc đó bám đuổi 3 ngày thay vì chăm thường.

Mặc định CHẠY KHÔ (chỉ in ra việc sẽ làm). Ghi thật thì thêm `--ghi`:
đây là dữ liệu điều khiển bảng việc của cả đội, sai là khách nhảy cột loạn
ngay trong giờ làm.

Chạy:
    python scripts/seed_cskh.py            # xem trước
    python scripts/seed_cskh.py --ghi      # ghi thật
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import cskh_service as svc  # noqa: E402


def main() -> None:
    ghi = "--ghi" in sys.argv
    print(f"Moc dau {svc.moc_dau()} · cach {svc.moc_cach()} ngay · "
          f"buong o {svc.ngay_buong()} ngay")
    print(f"Cong tac quy trinh CSKH: {'BAT' if svc.bat() else 'TAT'}")
    print(f"Menh gia may tang: {svc.menh_gia_voucher():,.0f}d · "
          f"han {svc.han_voucher()} ngay · nhip nhac {svc.nhip_voucher()}")
    print()

    viec = svc.seed_thang(dry=not ghi)
    if not viec:
        print("Thang moc da dung roi — khong co gi phai sua.")
    for v in viec:
        # In KHONG dau: console Windows cp1252 khong in duoc tieng Viet co dau.
        print("  " + " · ".join(f"{k}={v[k]}" for k in v))

    if not ghi:
        print("\n(CHAY KHO — them --ghi de ghi that)")
        return

    thang = svc.moc_thang()
    print(f"\nThang dang dung: {len(thang)} moc cham")
    for m in thang:
        print(f"  {m['code']:>10}  D{m['offset_days']:<4} cua so "
              f"{m['window_from']}-{m['window_to']}"
              f"{'  [KHUYEN MAI]' if m.get('promo') else ''}")
    print("\nXong. Mo /crm/bang-viec-cskh de xem bang viec.")


if __name__ == "__main__":
    main()
