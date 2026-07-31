"""Chuẩn hoá số điện thoại Việt Nam (B1 — FR-011 bước 'Chuẩn hóa số điện thoại').

Mọi chỗ ghi số vào crm.customers.primary_phone PHẢI đi qua normalize_phone()
— luật chống trùng theo SĐT chỉ đúng khi hai bên cùng một dạng.

Dạng chuẩn: 0xxxxxxxxx (10 số, đầu 0). Nhận vào mọi kiểu người gõ:
    "+84 90 123 4567" · "8490-123-4567" · "090.123.4567" · "0090123..." (lỗi kép)
Không ra được số hợp lệ thì trả None — KHÔNG lưu chuỗi rác vào cột số.
"""

import re

# Đầu số di động + cố định VN hiện hành (03x 05x 07x 08x 09x + cố định 02x)
_DAU_SO = re.compile(r"^0(2\d{9}|[35789]\d{8})$")


def normalize_phone(raw: str | None) -> str | None:
    """'+84901234567' / '84901234567' / '090 123 4567' -> '0901234567'; rác -> None."""
    if not raw:
        return None
    so = re.sub(r"[^\d+]", "", raw.strip())
    if so.startswith("+84"):
        so = "0" + so[3:]
    elif so.startswith("84") and len(so) >= 10:
        so = "0" + so[2:]
    so = re.sub(r"^00+", "0", so)          # gõ thừa số 0 đầu
    if not so.startswith("0") and len(so) in (9, 10):
        so = "0" + so                       # thiếu số 0 đầu (dán từ Excel hay gặp)
    return so if _DAU_SO.match(so) else None
