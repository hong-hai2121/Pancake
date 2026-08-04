"""Màn ĐƠN HÀNG (C7 — port `don-hang.php` của mẫu Kallet).

Ở đây là phần "màn hình" của đơn: nhãn tiếng Việt, khoảng thời gian chọn nhanh,
danh mục cột xuất Excel, dựng CSV, và LUẬT PHẠM VI XEM. Nghiệp vụ đơn (11 trạng
thái, luật chuyển, phân loại đầu/mua lại) vẫn ở `order_service` — đừng chép
sang đây.

KHÔNG import FastAPI (quy ước services/) — route chỉ là lớp mỏng gọi xuống.
"""

import csv
import io

from app.core import ngay as ngay_vn
from app.core.errors import ApiError
from app.db.repositories import audit_repo, don_hang_repo

# ------------------------------------------------------------------ nhãn
# 11 trạng thái chuẩn (order_service.ORDER_STATUSES) → nhãn + màu + mã POS gốc.
# Mẫu chỉ có 10 trạng thái và gộp khác ta; giữ 11 của mình, chỉ mượn CÁCH BÀY:
# mỗi trạng thái một cặp màu + tooltip nói rõ nó ứng với mã POS nào.
TRANG_THAI: dict[str, dict] = {
    "draft":             {"ten": "Nháp",         "lop": "mo",   "pos": "0 Mới"},
    "pending":           {"ten": "Chờ xác nhận", "lop": "tin",  "pos": "0 Mới"},
    "confirmed":         {"ten": "Đã xác nhận",  "lop": "tin",  "pos": "1 Đã xác nhận · 11 Chờ hàng"},
    "packing":           {"ten": "Đang đóng gói", "lop": "cho", "pos": "12 Chờ in · 13 Đã in"},
    "awaiting_shipment": {"ten": "Chờ chuyển",   "lop": "cho",  "pos": "9 Chờ chuyển hàng"},
    "shipping":          {"ten": "Đang giao",    "lop": "cho",  "pos": "2 Đã gửi · 8 Đang chuyển"},
    "delivered":         {"ten": "Giao thành công", "lop": "xong", "pos": "3 Đã nhận"},
    "collected":         {"ten": "Đã thu tiền",  "lop": "xong", "pos": "3 Đã nhận + đã đối soát"},
    "returning":         {"ten": "Đang hoàn",    "lop": "cho",  "pos": "4 Đang hoàn (tiền CÒN tính)"},
    "returned":          {"ten": "Đã hoàn",      "lop": "hong", "pos": "5 Đã hoàn (TRỪ doanh thu)"},
    "cancelled":         {"ten": "Huỷ",          "lop": "mo",   "pos": "6 Huỷ · 7 Xoá"},
}

LOAI_DON = {"new": "Đơn đầu", "repurchase": "Mua lại",
            "upsell": "Bán thêm", "exchange": "Đơn đổi"}
CONG_SUC = {"cham_soc": "Do chăm sóc", "tu_nhien": "Tự nhiên"}


# ------------------------------------------------------------------ khoảng ngày
def khoang_ngay(ma: str, tu: str = "", den: str = "") -> tuple[str, str, str]:
    """(nhãn, từ, đến) cho ô "Khoảng thời gian". Ngày tính theo GIỜ VN.

    `ma='tuy_chon'` thì dùng thẳng tu/den người gõ; mã lạ rơi về "Mọi thời
    gian" (không lọc) chứ không nổ — bộ lọc trên URL là thứ ai cũng sửa tay.
    """
    h = ngay_vn.hom_nay()
    dau_thang = h.replace(day=1)
    thang_truoc_cuoi = dau_thang - _ngay(1)
    bang = {
        "all":       ("Mọi thời gian", None, None),
        "today":     ("Hôm nay", h, h),
        "yesterday": ("Hôm qua", h - _ngay(1), h - _ngay(1)),
        "7d":        ("7 ngày qua", h - _ngay(6), h),
        "30d":       ("30 ngày qua", h - _ngay(29), h),
        "90d":       ("90 ngày qua", h - _ngay(89), h),
        "thisweek":  ("Đầu tuần đến nay", h - _ngay(h.weekday()), h),
        "thismonth": ("Đầu tháng đến nay", dau_thang, h),
        "lastmonth": ("Tháng trước", thang_truoc_cuoi.replace(day=1),
                      thang_truoc_cuoi),
        "ytd":       ("Từ đầu năm", h.replace(month=1, day=1), h),
    }
    if ma == "tuy_chon" and (tu or den):
        a, b = (tu or den), (den or tu)
        if a > b:
            a, b = b, a
        return "Tuỳ chọn", a, b
    nhan, a, b = bang.get(ma) or bang["all"]
    return nhan, (a.isoformat() if a else ""), (b.isoformat() if b else "")


def _ngay(n: int):
    from datetime import timedelta

    return timedelta(days=n)


# Thứ tự hiện trong menu chọn nhanh (mã, nhãn) — lấy nhãn từ chính `khoang_ngay`
# để không có hai chỗ ghi tên khác nhau.
CHON_NHANH = [(ma, khoang_ngay(ma)[0]) for ma in
              ("all", "today", "yesterday", "7d", "30d", "90d",
               "thisweek", "thismonth", "lastmonth", "ytd")]


# ------------------------------------------------------------------ phạm vi xem
def pham_vi(user: dict | None) -> int | None:
    """Người này chỉ được xem đơn CỦA MÌNH thì trả về id, xem hết thì None.

    Mẫu dùng quyền `data.xem_toan_bo_khach`; bên ta gần nghĩa nhất là
    `revenue.view` (Chủ DN · Admin · Kế toán · trưởng nhóm) — người được xem
    doanh thu công ty thì xem được mọi đơn. Sale/CSKH chỉ thấy đơn mình phụ
    trách, giống mẫu.
    """
    quyen = (user or {}).get("perms") or []
    if "revenue.view" in quyen:
        return None
    return int(user["sub"]) if user and user.get("sub") else None


def kiem_quyen_xem(user: dict | None) -> None:
    if "order.view" not in ((user or {}).get("perms") or []):
        raise ApiError("FORBIDDEN", "Màn Đơn hàng cần quyền order.view")


# ------------------------------------------------------------------ xuất Excel
# Danh mục cột CHỌN ĐƯỢC khi xuất (mẫu: od_export_fields). Thứ tự khai báo ở
# đây CŨNG LÀ thứ tự cột trong file — người dùng tích lung tung vẫn ra file
# xếp cùng một kiểu, dán vào mẫu báo cáo cũ là khớp.
COT_XUAT: dict[str, str] = {
    "ma_don":     "Mã đơn",
    "khach":      "Tên khách",
    "sdt":        "SĐT",
    "ngay_dat":   "Ngày đặt",
    "ngay_giao":  "Ngày giao thành công",
    "trang_thai": "Trạng thái",
    "pos_status": "Mã trạng thái POS",
    "loai_don":   "Lần mua",
    "cong_suc":   "Công sức",
    "quang_cao":  "Quảng cáo",
    "ma_ads":     "Mã ads",
    "gia_tri":    "Giá trị",
    "tra_truoc":  "Trả trước",
    "cod":        "COD",
    "ky_luong":   "Kỳ lương",
    "sale":       "Sale (CRM)",
    "cskh":       "CSKH (CRM)",
    "nv_pos":     "Nhân viên POS",
    "page":       "Fanpage",
    "pos_link":   "Link POS",
}

# Không tích gì thì xuất đúng bộ này (bộ "vừa đủ đọc" của mẫu).
COT_MAC_DINH = ["ma_don", "khach", "sdt", "ngay_dat", "trang_thai", "loai_don",
                "cong_suc", "quang_cao", "gia_tri", "tra_truoc", "cod",
                "ky_luong", "nv_pos"]


def chon_cot(tho) -> list[str]:
    """Lọc danh sách cột người dùng gửi lên → giữ ĐÚNG thứ tự khai báo."""
    xin = {str(x) for x in (tho or []) if str(x) in COT_XUAT}
    if not xin:
        return list(COT_MAC_DINH)
    return [k for k in COT_XUAT if k in xin]


def link_pos(r: dict) -> str:
    """Đường mở đơn này bên POS. Rỗng khi thiếu shop/mã hệ thống."""
    if not r.get("pos_shop_id") or not r.get("pos_order_id"):
        return ""
    return (f"https://pos.pancake.vn/shop/{r['pos_shop_id']}/order"
            f"?order_id={r['pos_order_id']}")


def ma_don(r: dict) -> str:
    """Mã đơn hiển thị: mã POS người dùng thấy → mã đơn ngoài → #id nội bộ."""
    return (r.get("pos_display_id") or r.get("external_order_id")
            or f"#{r['id']}")


def _o(khoa: str, r: dict):
    """Một ô CSV theo mã cột."""
    if khoa == "ma_don":
        return ma_don(r)
    if khoa == "khach":
        return r.get("khach") or ""
    if khoa == "sdt":
        return r.get("sdt") or ""
    if khoa == "ngay_dat":
        return _ngay_gio(r.get("ngay_dat"))
    if khoa == "ngay_giao":
        return _ngay_gio(r.get("delivered_at"))
    if khoa == "trang_thai":
        return (TRANG_THAI.get(r.get("status") or "") or {}).get(
            "ten", r.get("status") or "")
    if khoa == "pos_status":
        return "" if r.get("pos_status") is None else r["pos_status"]
    if khoa == "loai_don":
        return LOAI_DON.get(r.get("order_type") or "", r.get("order_type") or "")
    if khoa == "cong_suc":
        return CONG_SUC.get(r.get("effort_axis") or "", "")
    if khoa == "quang_cao":
        return "Có ads" if r.get("ads_attributed") else "Không ads"
    if khoa == "ma_ads":
        return r.get("pos_ad_id") or ""
    if khoa in ("gia_tri", "tra_truoc", "cod"):
        v = {"gia_tri": r.get("total_amount"), "tra_truoc": r.get("prepaid_amount"),
             "cod": r.get("cod_amount")}[khoa]
        # Ô trống ≠ 0đ: POS không gửi số thì để trống, đừng bịa số 0.
        return "" if v is None else int(v)
    if khoa == "ky_luong":
        return r.get("payroll_period") or ""
    if khoa == "sale":
        return r.get("sale_ten") or ""
    if khoa == "cskh":
        return r.get("cskh_ten") or ""
    if khoa == "nv_pos":
        return r.get("nv_pos") or ""
    if khoa == "page":
        return r.get("page_ten") or r.get("pos_page_id") or ""
    if khoa == "pos_link":
        return link_pos(r)
    return ""


def _ngay_gio(v) -> str:
    if not v:
        return ""
    try:
        return v.astimezone(ngay_vn.MUI_GIO).strftime("%d/%m/%Y %H:%M")
    except (AttributeError, ValueError):
        return str(v)


def xuat_csv(loc: dict, cot: list[str], *, sort: str = "ngay",
             dir_: str = "desc", ids: list[int] | None = None,
             user: dict | None = None) -> tuple[str, str]:
    """Dựng nội dung CSV + tên file. Đòi `data.export`, ghi audit (FR-181).

    Hai lối vào:
      * `ids=None`  — xuất TOÀN BỘ đơn khớp bộ lọc (đọc theo lô 2.000);
      * `ids=[…]`   — xuất đúng những đơn đã tích, và 🔒 vẫn gắn lại phạm vi
        xem của người bấm (id đơn đoán được — xem don_hang_repo.theo_ids).

    Định dạng: BOM UTF-8 + dấu chấm phẩy, cùng nếp với các file xuất khác của
    dự án (Excel bản VN mở thẳng, không phải qua bước Import Text).
    """
    if "data.export" not in ((user or {}).get("perms") or []):
        raise ApiError("FORBIDDEN", "Xuất dữ liệu cần quyền data.export (FR-181)")
    kiem_quyen_xem(user)
    cot = chon_cot(cot)
    cua_toi = pham_vi(user)

    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\n")
    w.writerow([COT_XUAT[k] for k in cot])
    so_dong = 0
    if ids is not None:
        for r in don_hang_repo.theo_ids(ids, nguoi_xem=cua_toi):
            w.writerow([_o(k, r) for k in cot])
            so_dong += 1
    else:
        f = {**loc, "nguoi_xem": cua_toi}
        for mot_lo in don_hang_repo.xuat_theo_lo(f, sort=sort, dir_=dir_):
            for r in mot_lo:
                w.writerow([_o(k, r) for k in cot])
            so_dong += len(mot_lo)

    audit_repo.ghi(
        user_id=int(user["sub"]) if user and user.get("sub") else None,
        action="order_export", object_type="orders",
        new_value={"so_dong": so_dong, "so_cot": len(cot),
                   "theo_tich": ids is not None},
    )
    ten = f"don-hang-{ngay_vn.bay_gio():%Y%m%d-%H%M%S}.csv"
    return "﻿" + out.getvalue(), ten


# ------------------------------------------------------------------ đọc màn
def man_hinh(loc: dict, *, sort: str = "ngay", dir_: str = "desc",
             size: int = 30, trang: int = 1, user: dict | None = None) -> dict:
    """Gom đủ dữ liệu một lượt vẽ màn: thẻ chỉ số · bảng · ô lọc.

    Thẻ chỉ số đếm trên CẢ BỘ LỌC (không phải trang đang xem) — đổi bộ lọc là
    mọi con số đổi theo, giống mẫu.
    """
    kiem_quyen_xem(user)
    cua_toi = pham_vi(user)
    f = {**loc, "nguoi_xem": cua_toi}
    size = size if size in (30, 50, 100) else 30
    trang = max(1, trang)
    rows, tong = don_hang_repo.bang(f, sort=sort, dir_=dir_, limit=size,
                                    offset=(trang - 1) * size)
    return {
        "rows": rows,
        "tong": tong,
        "chi_so": don_hang_repo.chi_so(f),
        "trang": trang,
        "size": size,
        "so_trang": max(1, -(-tong // size)),
        "chi_don_cua_toi": cua_toi is not None,
    }
