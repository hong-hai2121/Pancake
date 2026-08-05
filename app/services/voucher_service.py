"""Luật voucher + hạng thẻ (C1 — port từ mẫu Kallet voucher.php · hang-the.php).

Bốn luật mẫu ghi rõ "đừng sửa mất", chép sang đây nguyên vẹn:

  1. **Chỉ NÂNG hạng, không ai bị tụt.** Đơn hoàn/huỷ làm tổng chi tiêu giảm thì
     hạng vẫn giữ — hạ hạng khách là mất lòng khách, không phải chuyện của máy.
  2. **Giảm quyền lợi NGẦM sau 180 ngày không nhận hàng.** Hạng *hiển thị* giữ
     nguyên, chỉ *quyền lợi* tụt 1 bậc, và TUYỆT ĐỐI không gửi tin báo khách.
  3. **Còn voucher hiệu lực thì tắt mọi mốc chăm chuẩn**, chỉ giữ mốc nhắc hạn
     voucher (C7) — tránh nhắn chồng lên nhau.
  4. **Chưa báo mã ≠ lỗi dữ liệu** mà là VIỆC CẦN LÀM: voucher tạo không kèm mã
     nằm ở trạng thái `chua_bao_ma` cho tới khi nhân viên báo mã cho khách.
"""

from datetime import timedelta

from app.core import runtime_config
from app.core.errors import ApiError
from app.core.ngay import hom_nay
from app.db.repositories import voucher_repo as repo
from app.services.phone import normalize_phone

# Bộ mặt hiển thị theo mã hạng (chỉ là màu + icon). TÊN và NGƯỠNG luôn đọc từ
# bảng card_ranks — không bịa số trên giao diện.
MAT_HANG: dict[str, dict] = {
    "diamond":    {"icon": "💎", "mau": "#7A308F", "nen": "#EDE4F6"},
    "gold":       {"icon": "🥇", "mau": "#9A6B00", "nen": "#FBECC9"},
    "silver":     {"icon": "🥈", "mau": "#5B5B66", "nen": "#E7E7EC"},
    "member":     {"icon": "🎫", "mau": "#A23A94", "nen": "#F3E3F1"},
    "new_member": {"icon": "🆕", "mau": "#1E7A46", "nen": "#DFF3E6"},
}
MAT_CHUA_XEP = {"icon": "⬜", "mau": "#948A9C", "nen": "#F8F4F8"}


def mat_hang(ma: str | None) -> dict:
    if not ma:
        return MAT_CHUA_XEP
    return MAT_HANG.get(ma, {"icon": "🎖️", "mau": "#6E6177", "nen": "#F8F4F8"})


NHAN_TRANG_THAI = {
    "chua_bao_ma":        "Chưa báo mã",
    "con_han":            "Còn hạn",
    "da_dung":            "Đã dùng",
    "het_han_khong_dung": "Hết hạn (không dùng)",
    "da_tra_lai":         "Đã trả lại",
}


# Ba con số dưới đây CHỈNH ĐƯỢC ở màn Cài đặt (nhóm "Voucher & hạng thẻ").
# Đọc qua hàm chứ không hằng số module: đổi cài đặt là ăn ngay, khỏi restart.
def han_mac_dinh() -> int:
    """Số ngày hiệu lực khi người tặng không gõ hạn riêng."""
    return int(runtime_config.so("voucher_expiry_days", 30))


def ngay_sap_het() -> int:
    """Dưới ngần này ngày thì voucher tô ĐỎ + kèm chữ 'sắp hết'."""
    return int(runtime_config.so("voucher_warn_days", 3))


def giam_quyen_loi_bat() -> bool:
    """Đ2 — công tắc luật "giảm quyền lợi ngầm" (Cài đặt → Vòng đời khách).

    TẮT thì khách lâu không mua vẫn hưởng đủ quyền lợi hạng cũ. Đây là công tắc
    LUẬT, khác với `ngay_giam_quyen_loi()` là NGƯỠNG của luật.
    """
    return bool(runtime_config.bat("luat_giam_quyenloi_on"))


def ngay_giam_quyen_loi() -> int:
    """Luật 2. ĐỪNG nhầm với ba con số 180/180/210 khác nghĩa trong hệ thống
    (nhắc cuối · thôi phân công · rời bảng việc)."""
    return int(runtime_config.so("card_rank_downgrade_days", 180))


# ------------------------------------------------------------------ hiển thị
def trang_thai_hien_thi(v: dict) -> dict:
    """Nhãn + màu của một voucher. 'Còn hạn' được tách thêm mức 'sắp hết' theo
    số ngày còn lại — màu KHÔNG bao giờ đứng một mình, luôn kèm chữ."""
    tt = v.get("status")
    con = v.get("ngay_con_lai")
    if tt == "con_han":
        duoi = f" · {con} ngày" if con is not None and con >= 0 else ""
        if con is not None and 0 <= con <= ngay_sap_het():
            return {"chu": f"sắp hết{duoi}", "mau": "#E5484D",
                    "nen": "#FCE1E2", "gap": True}
        return {"chu": f"còn hạn{duoi}", "mau": "#2EAD6E",
                "nen": "#DDF3E8", "gap": False}
    bang = {
        "chua_bao_ma":        ("⚠️ chưa báo mã", "#C25E00", "#FFF0D6"),
        "da_dung":            ("✅ đã dùng", "#2EAD6E", "#DDF3E8"),
        "het_han_khong_dung": ("hết hạn không dùng", "#607D8B", "#ECEFF1"),
        "da_tra_lai":         ("đã trả lại", "#948A9C", "#F8F4F8"),
    }
    chu, mau, nen = bang.get(tt, (tt or "—", "#6E6177", "#F8F4F8"))
    return {"chu": chu, "mau": mau, "nen": nen, "gap": False}


def lech_tien(v: dict) -> bool:
    """Đơn đã dùng voucher nhưng POS giảm số khác mệnh giá → cần soi lại.
    Máy KHÔNG tự sửa, chỉ gắn dấu hỏi cho người kiểm."""
    return bool(
        v.get("status") == "da_dung"
        and v.get("pos_discount") is not None
        and float(v["pos_discount"]) != float(v.get("amount") or 0)
    )


# ------------------------------------------------------------------ thao tác
def tang_voucher(
    *, sdt: str = "", customer_id: int | None = None, menh_gia,
    ma: str = "", han_ngay: int = 0, ghi_chu: str = "",
    nguoi_tang: int | None = None, la_admin: bool = False,
) -> dict:
    """Tạo & tặng voucher cho khách CÓ SẴN trong hệ thống.

    Khớp khách theo SĐT đã chuẩn hoá (hoặc `customer_id` khi gọi từ hồ sơ
    khách). KHÔNG gửi tin cho khách — báo mã là việc của nhân viên.
    """
    from app.db.repositories import customer_repo

    if customer_id:
        khach = customer_repo.get_customer(customer_id)
    else:
        so_dt = normalize_phone(sdt)
        if not so_dt:
            raise ApiError("VALIDATION_ERROR", "Số điện thoại không hợp lệ.")
        # Số nhà dùng chung → có thể ra nhiều khách; lấy hồ sơ đầu tiên và để
        # người tặng tự kiểm bằng tên hiện trên thông báo thành công.
        ds = customer_repo.find_by_phone(so_dt)
        khach = ds[0] if ds else None
    if not khach:
        raise ApiError("NOT_FOUND", "Không tìm thấy khách theo SĐT đã nhập.")

    try:
        tien = float(str(menh_gia).replace(".", "").replace(",", "").strip() or 0)
    except ValueError:
        tien = 0
    if tien <= 0:
        raise ApiError("VALIDATION_ERROR", "Mệnh giá không hợp lệ.")

    ngay = han_ngay if han_ngay and han_ngay > 0 else han_mac_dinh()
    v = repo.tao(
        customer_id=int(khach["id"]),
        amount=tien,
        granted_on=hom_nay(),
        expires_on=hom_nay() + timedelta(days=ngay),
        code=(ma or "").strip().upper(),
        granted_by=nguoi_tang,
        granted_by_kind="nguoi" if nguoi_tang else "may",
        note=(ghi_chu or "")[:255],
    )
    return {**dict(v), "customer_name": khach.get("full_name")}


def bao_ma(voucher_id: int, ma: str, *, nguoi_sua: int | None = None) -> dict:
    """Báo mã cho voucher đang 'chưa báo mã' → chuyển sang 'còn hạn'."""
    ma = (ma or "").strip().upper()
    if not ma:
        raise ApiError("VALIDATION_ERROR", "Chưa nhập mã voucher.")
    v = repo.get(voucher_id)
    if not v:
        raise ApiError("NOT_FOUND", "Không tìm thấy voucher.")
    tt = "con_han" if v["status"] == "chua_bao_ma" else v["status"]
    return repo.cap_nhat(voucher_id, code=ma, status=tt, updated_by=nguoi_sua)


def doi_trang_thai(voucher_id: int, trang_thai: str, *,
                   nguoi_sua: int | None = None) -> dict:
    if trang_thai not in NHAN_TRANG_THAI:
        raise ApiError("VALIDATION_ERROR", f"Trạng thái lạ: {trang_thai}")
    v = repo.cap_nhat(voucher_id, status=trang_thai, updated_by=nguoi_sua)
    if not v:
        raise ApiError("NOT_FOUND", "Không tìm thấy voucher.")
    return v


def dang_co_voucher(customer_id: int) -> dict | None:
    """Luật 3 — nơi khác hỏi 'khách này còn voucher không?' để TẮT mốc chăm
    chuẩn. Trả voucher gần hết hạn nhất, hoặc None."""
    return repo.con_hieu_luc(customer_id)


# ------------------------------------------------------------------ hạng thẻ
def bac_thang() -> list[dict]:
    """Bậc thang hạng thẻ (cao → thấp), kèm mặt hiển thị và câu mô tả ngưỡng.

    Bảng rỗng → trả khung 5 hạng chuẩn với ngưỡng None ("chưa điền", tô cam ở
    màn Cài đặt) thay vì 0 — số 0 làm người dùng tưởng đã cấu hình xong."""
    ds = [dict(r) for r in repo.hang_the()]
    if not ds:
        ds = [
            {"code": ma, "name": ten, "emoji": "", "min_spent": None,
             "max_spent": None, "sort_order": tt, "khung": True}
            for ma, ten, tt in [
                ("diamond", "Diamond", 5), ("gold", "Gold", 4),
                ("silver", "Silver", 3), ("member", "Member", 2),
                ("new_member", "New Member", 1),
            ]
        ]
    for r in ds:
        r["mat"] = mat_hang(r["code"])
        r["mo_ta_nguong"] = _mo_ta_nguong(r)
    return ds


def _mo_ta_nguong(r: dict) -> str:
    tu, den = r.get("min_spent"), r.get("max_spent")
    if tu is None:
        return "chưa cấu hình ngưỡng"
    tu = float(tu)
    if tu <= 1:
        return "trên 0đ (đáy thang)"
    if den in (None, 0):
        return f"từ {tu:,.0f}đ trở lên".replace(",", ".")
    return f"{tu:,.0f} → {float(den):,.0f}đ".replace(",", ".")


def hang_thap_hon() -> dict[str, str | None]:
    """mã hạng → TÊN hạng thấp hơn 1 bậc (None nếu đã ở đáy thang).
    Dùng để nói rõ "giảm quyền lợi xuống như hạng nào"."""
    asc = [dict(r) for r in repo.hang_the_tang_dan()]
    ra: dict[str, str | None] = {}
    for i, r in enumerate(asc):
        ra[r["code"]] = asc[i - 1]["name"] if i > 0 else None
    return ra


def tinh_lai_hang(*, nguoi_chay: int | None = None) -> dict:
    """LUẬT 1 — xếp lại hạng cho toàn bộ khách, CHỈ NÂNG.

    Hai bước: làm mới tổng chi tiêu từ orders → nâng hạng theo ngưỡng. Hạng
    chưa điền ngưỡng bị bỏ qua (không kéo ai vào hạng chưa cấu hình).
    """
    so_chi_tieu = repo.lam_moi_chi_tieu()
    bac = [
        (r["code"], int(r["sort_order"]), r["min_spent"])
        for r in repo.hang_the() if r["min_spent"] is not None
    ]
    # nâng hạng đọc theo ngưỡng GIẢM DẦN — CASE dừng ở nhánh đầu khớp
    bac.sort(key=lambda x: float(x[2]), reverse=True)
    so_nang = repo.nang_hang(bac)

    from app.db.repositories import audit_repo

    audit_repo.ghi(
        action="tinh_lai_hang_the", object_type="card_rank",
        user_id=nguoi_chay,
        new_value={"khach_doi_chi_tieu": so_chi_tieu, "khach_len_hang": so_nang},
        reason="Tính lại hạng thẻ (chỉ nâng, không ai bị tụt)",
    )
    return {"chi_tieu": so_chi_tieu, "len_hang": so_nang}


def cap_nhat_hang_mot_khach(customer_id: int) -> str | None:
    """Bản MỘT KHÁCH của `tinh_lai_hang` — gọi ngay khi đơn của khách giao
    thành công, để khách lên hạng liền chứ không phải chờ worker chạy đêm.

    Cùng luật CHỈ NÂNG. Trả mã hạng mới nếu có đổi, None nếu giữ nguyên."""
    repo.lam_moi_chi_tieu_mot_khach(customer_id)
    bac = [(r["code"], int(r["sort_order"]), r["min_spent"])
           for r in repo.hang_the() if r["min_spent"] is not None]
    bac.sort(key=lambda x: float(x[2]), reverse=True)
    return repo.nang_hang_mot_khach(customer_id, bac)


def toan_canh() -> dict:
    """Số liệu màn Hạng thẻ: đếm theo hạng · chưa xếp hạng · giảm quyền lợi."""
    dem = repo.dem_theo_hang()
    bac = bac_thang()
    return {
        "bac": bac,
        "dem": dem,
        "chua_xep": dem.get("", 0),
        "tong_khach": repo.tong_khach(),
        # Luật TẮT thì không ai bị giảm — trả 0 chứ không phải đếm rồi hiện số
        # mà thực tế chẳng ai bị gì; số đó làm người xem tưởng luật đang chạy.
        "giam_quyen_loi": (repo.dem_giam_quyen_loi(ngay_giam_quyen_loi())
                           if giam_quyen_loi_bat() else 0),
        "luat_giam_bat": giam_quyen_loi_bat(),
        "ngay_giam": ngay_giam_quyen_loi(),
        "thap_hon": hang_thap_hon(),
        "quyen_loi": repo.quyen_loi(),
        "la_khung": bool(bac and bac[0].get("khung")),
    }
