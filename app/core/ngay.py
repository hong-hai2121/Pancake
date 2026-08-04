"""Ngày làm việc theo múi giờ NGHIỆP VỤ (Asia/Ho_Chi_Minh, UTC+7).

Vì sao cần file này: Postgres trong Docker chạy giờ **UTC**, nên `current_date`
của DB lệch với ngày người Việt đang sống tới 7 tiếng. Hệ quả thật đã gặp:

  * Tặng voucher trước 07:00 sáng → DB ghi `granted_on` LÙI 1 NGÀY, voucher
    hiển thị "tặng hôm qua" và hạn tính sai 1 ngày.
  * Quét voucher hết hạn bằng `expires_on < current_date` → voucher hết hạn
    hôm nay phải chờ thêm 7 tiếng mới bị đóng.

Mẫu Kallet vấp đúng lỗi này rồi vá bằng cách dùng `date()` của PHP thay cho
`CURDATE()` của MySQL (xem ghi chú trong `voucher.php`). Ta làm y hệt: **mọi
mốc ngày của nghiệp vụ tính ở Python rồi truyền xuống SQL**, không để DB tự
điền `current_date` cho cột ngày mang nghĩa nghiệp vụ.

Cột `created_at`/`updated_at` (dấu vết kỹ thuật) thì vẫn để DB đóng dấu bằng
`now()` — chúng là timestamptz nên không có chuyện lệch ngày.
"""

from datetime import date, datetime, timedelta, timezone

# UTC+7 cố định: Việt Nam không có giờ mùa hè nên khỏi cần tzdata/ZoneInfo
# (gói này thiếu trên nhiều bản Windows rút gọn).
MUI_GIO = timezone(timedelta(hours=7))


def bay_gio() -> datetime:
    """Thời điểm hiện tại theo giờ VN (có tzinfo)."""
    return datetime.now(MUI_GIO)


def hom_nay() -> date:
    """Ngày hôm nay theo giờ VN — dùng thay `current_date` của DB."""
    return bay_gio().date()


def sau_ngay(n: int) -> date:
    """Ngày hôm nay + n ngày (giờ VN). n âm = lùi về quá khứ."""
    return hom_nay() + timedelta(days=n)
