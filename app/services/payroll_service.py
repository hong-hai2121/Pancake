"""Luật lương · thưởng · đối soát (C2 — port mẫu Kallet luong*.php, doi-soat.php).

Công thức một kỳ lương:

    tổng = lương cứng
         + hoa hồng            (bậc theo DOANH THU KỲ, lấy bậc cao nhất chạm tới)
         + thưởng chăm sóc     (từng ĐƠN đã được DUYỆT ở màn Đối soát)
         + thưởng nóng         (2 kiểu chạy song song, CỘNG DỒN)
         + điều chỉnh          (cộng/trừ, gồm truy thu đơn hoàn kỳ trước)

BA CHỖ MẪU DẶN "ĐỪNG SỬA CHO GỌN":

  1. **Thưởng chăm sóc CHỒNG LÊN hoa hồng.** Nhìn qua tưởng trả hai lần cho
     cùng một đơn nên rất dễ bị "sửa lỗi" thành thay thế. Đây là CỐ Ý: hoa hồng
     trả cho doanh thu, thưởng chăm trả cho CÔNG chăm khách cũ quay lại.

  2. **Thưởng nóng có hai kiểu chạy song song và CỘNG DỒN**: theo doanh thu
     NGÀY và theo giá trị TỪNG ĐƠN. Một đơn to trong một ngày to thì ăn cả hai.

  3. **Đơn hoàn/huỷ sau khi đã chốt lương → TRỪ KỲ SAU**, không sửa ngược kỳ cũ
     (tiền đã trả rồi). `payrolls.frozen` khoá kỳ; truy thu ghi một dòng
     `payroll_adjustments` âm, mỗi đơn đúng một lần.

Ngoài ra: "doanh thu LÊN ĐƠN" và "ĐÃ THU" là hai con số khác nhau, mọi chỗ bày
ra màn đều phải ghi rõ đang xem cái nào (luật vàng B3.1 của mẫu).
"""

from datetime import date

from app.core.errors import ApiError
from app.core.ngay import hom_nay
from app.db.repositories import payroll_repo as repo


def ky_hop_le(ky: str) -> str:
    """Chuẩn hoá kỳ 'YYYY-MM'; rỗng/sai → kỳ hiện tại."""
    ky = (ky or "").strip()
    if len(ky) == 7 and ky[4] == "-":
        try:
            int(ky[:4]), int(ky[5:])
            return ky
        except ValueError:
            pass
    return repo.ky_hien_tai()


def ky_ke_tiep(ky: str) -> str:
    nam, thang = int(ky[:4]), int(ky[5:])
    return f"{nam + 1}-01" if thang == 12 else f"{nam}-{thang + 1:02d}"


def _tien_bac(bac: dict, goc: float) -> float:
    """Một bậc quy ra tiền: phần trăm của `goc`, hoặc số tiền cố định."""
    gia_tri = float(bac["value"])
    if bac["kind"] == "phan_tram":
        return round(goc * gia_tri / 100)
    return gia_tri


def _bac_cao_nhat(bac: list[dict], moc: float, khoa_nguong: str) -> dict | None:
    """Bậc CAO NHẤT mà `moc` chạm tới. `bac` đã sắp ngưỡng tăng dần.

    KHÔNG cộng dồn các bậc: vượt bậc 3 thì hưởng bậc 3, không phải 1+2+3."""
    chon = None
    for b in bac:
        if moc >= float(b[khoa_nguong]):
            chon = b
    return chon


# ------------------------------------------------------------------ từng khoản
def hoa_hong(role_id: int | None, doanh_thu: float) -> tuple[float, dict | None]:
    """Hoa hồng của kỳ theo bậc doanh thu. Trả (tiền, bậc đang hưởng)."""
    if not role_id:
        return 0.0, None
    bac = repo.bac_hoa_hong(role_id)
    chon = _bac_cao_nhat(bac, doanh_thu, "min_revenue")
    return (_tien_bac(chon, doanh_thu), dict(chon)) if chon else (0.0, None)


def thuong_cham_mot_don(role_id: int | None, gia_tri_don: float) -> float:
    """LUẬT 1 — thưởng chăm của MỘT đơn, xét theo giá trị đơn đó.

    Dưới ngưỡng thấp nhất vẫn lấy bậc đầu (giống mẫu): đơn nhỏ vẫn có công chăm.
    """
    if not role_id:
        return 0.0
    bac = repo.bac_thuong_cham(role_id)
    if not bac:
        return 0.0
    chon = _bac_cao_nhat(bac, gia_tri_don, "min_revenue") or bac[0]
    return _tien_bac(chon, gia_tri_don)


def thuong_nong(role_id: int | None, user_id: int, ky: str) -> dict:
    """LUẬT 2 — hai kiểu chạy SONG SONG, kết quả CỘNG DỒN.

    * `doanh_thu_ngay` — mỗi NGÀY đạt ngưỡng thưởng một lần.
    * `gia_tri_don`    — mỗi ĐƠN đạt ngưỡng thưởng một lần.

    Trả chi tiết để màn Thu nhập giải thích được "vì sao có khoản này" — nhân
    viên không tin con số mình không tra ngược được.
    """
    if not role_id:
        return {"tong": 0.0, "theo_ngay": [], "theo_don": []}
    bac = repo.bac_thuong_nong(role_id)
    bac_ngay = [b for b in bac if b["basis"] == "doanh_thu_ngay"]
    bac_don = [b for b in bac if b["basis"] == "gia_tri_don"]

    theo_ngay = []
    for r in repo.doanh_thu_theo_ngay(user_id, ky) if bac_ngay else []:
        tien_ngay = float(r["tien"] or 0)
        chon = _bac_cao_nhat(bac_ngay, tien_ngay, "threshold")
        if chon:
            theo_ngay.append({"ngay": r["ngay"], "doanh_thu": tien_ngay,
                              "nguong": float(chon["threshold"]),
                              "thuong": _tien_bac(chon, tien_ngay)})

    theo_don = []
    if bac_don:
        for o in repo.don_trong_ky(user_id, ky):
            if o["status"] not in ("delivered", "collected"):
                continue
            tien_don = float(o["total_amount"] or 0)
            chon = _bac_cao_nhat(bac_don, tien_don, "threshold")
            if chon:
                theo_don.append({
                    "order_id": o["id"],
                    "ma_don": o["external_order_id"] or o["pos_order_id"],
                    "gia_tri": tien_don, "nguong": float(chon["threshold"]),
                    "thuong": _tien_bac(chon, tien_don)})

    tong = sum(x["thuong"] for x in theo_ngay) + sum(x["thuong"] for x in theo_don)
    return {"tong": float(tong), "theo_ngay": theo_ngay, "theo_don": theo_don}


# ------------------------------------------------------------------ tính kỳ
def tinh_luong(user_id: int, ky: str = "", *, ghi: bool = False) -> dict:
    """Tính lương một người cho một kỳ. `ghi=True` thì lưu vào crm.payrolls.

    Kỳ ĐÃ CHỐT: vẫn tính ra số để xem, nhưng repo từ chối ghi đè (`frozen`) nên
    con số đã trả tiền không bao giờ bị đổi sau lưng.
    """
    from app.db.repositories import user_repo

    ky = ky_hop_le(ky)
    nv = user_repo.get_user(user_id)
    if not nv:
        raise ApiError("NOT_FOUND", "Không tìm thấy nhân viên.")
    role_id = nv.get("role_id")

    tong_hop = repo.tong_hop_ky(user_id, ky)
    len_don = float(tong_hop["len_don"] or 0)
    da_thu = float(tong_hop["da_thu"] or 0)

    # Hoa hồng tính trên doanh thu ĐÃ THU — tiền chưa về thì chưa chia hoa hồng.
    hh, bac_hh = hoa_hong(role_id, da_thu)
    # LUẬT 1: cộng THÊM, không thay thế hoa hồng.
    tc = repo.thuong_cham_da_duyet(user_id, ky)
    tn = thuong_nong(role_id, user_id, ky)
    dc = repo.tong_dieu_chinh(user_id, ky)
    cung = repo.luong_cung(user_id)
    tong = cung + hh + tc + tn["tong"] + dc

    so = {"luong_cung": cung, "len_don": len_don, "da_thu": da_thu,
          "hoa_hong": hh, "thuong_cham": tc, "thuong_nong": tn["tong"],
          "dieu_chinh": dc, "tong": tong}
    dong_bang = False
    if ghi:
        dong = repo.luu_payroll(user_id, ky, so)
        dong_bang = bool(dong and dong["frozen"])
    else:
        cu = repo.get_payroll(user_id, ky)
        dong_bang = bool(cu and cu["frozen"])

    return {
        "user": dict(nv), "ky": ky, **so,
        "bac_hoa_hong": bac_hh,
        "chi_tiet_thuong_nong": tn,
        "so_don": int(tong_hop["so_don"] or 0),
        "so_don_hoan": int(tong_hop["so_don_hoan"] or 0),
        "dong_bang": dong_bang,
        "dieu_chinh_chi_tiet": [dict(r) for r in repo.dieu_chinh(user_id, ky)],
    }


def tinh_ca_doi(ky: str = "", *, ghi: bool = True) -> list[dict]:
    """Tính lương cho MỌI người có đơn trong kỳ (worker + nút Tính lại)."""
    ky = ky_hop_le(ky)
    return [tinh_luong(int(u["id"]), ky, ghi=ghi)
            for u in repo.nhan_vien_co_don(ky)]


def chot_ky(ky: str, nguoi: int | None = None) -> dict:
    """Chốt kỳ: tính lần cuối rồi ĐÓNG BĂNG. Sau đây mọi sai lệch đi kỳ sau."""
    ky = ky_hop_le(ky)
    tinh_ca_doi(ky, ghi=True)
    so = repo.chot_ky(ky, nguoi)

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="chot_ky_luong", object_type="payroll",
                   user_id=nguoi, new_value={"ky": ky, "so_dong": so},
                   reason="Chốt kỳ lương — khoá sửa, chênh lệch ghi kỳ sau")
    return {"ky": ky, "so_dong": so}


def truy_thu_don_hoan(*, nguoi: int | None = None) -> list[dict]:
    """LUẬT 3 — đơn hoàn/huỷ sau khi kỳ đã chốt: ghi khoản TRỪ vào KỲ SAU.

    Trừ đúng phần đã trả cho đơn đó: thưởng chăm đã duyệt + phần hoa hồng ứng
    với giá trị đơn theo bậc đang hưởng. KHÔNG đụng vào kỳ cũ.
    """
    ra = []
    for o in repo.don_hoan_sau_chot():
        ky_cu = o["payroll_period"]
        ky_moi = ky_ke_tiep(ky_cu)
        hh_don, _ = hoa_hong(o["staff_role_id"], float(o["total_amount"] or 0))
        so_tru = float(o["thuong_cham_da_tra"] or 0) + hh_don
        if so_tru <= 0:
            continue
        dong = repo.them_dieu_chinh(
            int(o["staff_id"]), ky_moi, -so_tru,
            f'Truy thu đơn {o["external_order_id"] or o["pos_order_id"] or o["id"]} '
            f'({"hoàn" if o["status"] == "returned" else "huỷ"}) — kỳ {ky_cu} '
            "đã chốt nên trừ vào kỳ này",
            order_id=int(o["id"]), nguoi=nguoi)
        if dong:
            ra.append(dict(dong))
    return ra


# ------------------------------------------------------------------ đối soát
def duyet_thuong_cham(order_id: int, *, nguoi: int | None = None) -> dict:
    """Duyệt thưởng chăm cho 1 đơn. Số tiền TÍNH LẠI ở máy chủ, không nhận số
    từ client — nút Duyệt trên màn chỉ là lệnh, không phải nguồn số."""
    don = _don_doi_soat(order_id)
    so_tien = thuong_cham_mot_don(don["staff_role_id"],
                                  float(don["total_amount"] or 0))
    kq = repo.duyet_thuong(order_id, so_tien=so_tien, nguoi=nguoi)

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="duyet_thuong_cham", object_type="order",
                   object_id=order_id, user_id=nguoi,
                   new_value={"so_tien": str(so_tien)},
                   reason=f"Duyệt thưởng chăm +{so_tien:,.0f}")
    return dict(kq)


def bac_thuong_cham(order_id: int, ly_do: str, *,
                    nguoi: int | None = None) -> dict:
    """Bác thưởng — BẮT BUỘC có lý do (mẫu: thu hồi phải ghi lý do)."""
    ly_do = (ly_do or "").strip()[:240]
    if not ly_do:
        raise ApiError("VALIDATION_ERROR",
                       "Phải ghi lý do khi bác thưởng chăm sóc.")
    _don_doi_soat(order_id)
    kq = repo.bac_thuong(order_id, ly_do, nguoi=nguoi)

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="tu_choi_thuong_cham", object_type="order",
                   object_id=order_id, user_id=nguoi, reason=ly_do)
    return dict(kq)


def doi_phan_loai(order_id: int, sang: str, *, nguoi: int | None = None,
                  ly_do: str = "") -> dict:
    """Đổi phân loại đơn — "đổi phân loại thì TIỀN ĐI THEO".

    `sang` = 'quang_cao' (rời diện thưởng chăm, huỷ luôn phiếu duyệt) hoặc
    'cham_soc' (đưa vào diện thưởng chăm). Kỳ đã chốt thì chặn — sửa được sẽ
    làm lệch số đã trả; muốn sửa phải đi đường điều chỉnh kỳ sau.
    """
    if sang not in ("quang_cao", "cham_soc"):
        raise ApiError("VALIDATION_ERROR", f"Phân loại lạ: {sang}")
    don = _don_doi_soat(order_id, doi_cham_soc=False)
    if don.get("ky_da_chot"):
        raise ApiError(
            "CONFLICT",
            "Kỳ lương của đơn này đã chốt — không sửa ngược được. Ghi một "
            "khoản điều chỉnh vào kỳ sau thay vì đổi phân loại.")
    mac_dinh = ("Đối soát: đổi sang Quảng cáo" if sang == "quang_cao"
                else "Đối soát: đổi sang Chăm sóc")
    kq = repo.phan_loai(
        order_id,
        effort_axis="tu_nhien" if sang == "quang_cao" else "cham_soc",
        ads_attributed=True if sang == "quang_cao" else None,
        bang_tay=True, ly_do=(ly_do or "").strip() or mac_dinh, nguoi=nguoi)
    if sang == "quang_cao":
        repo.xoa_duyet(order_id)      # rời diện thưởng chăm → huỷ phiếu duyệt

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="doi_phan_loai_don", object_type="order",
                   object_id=order_id, user_id=nguoi,
                   new_value={"sang": sang}, reason=ly_do or mac_dinh)
    return dict(kq or {})


def _don_doi_soat(order_id: int, *, doi_cham_soc: bool = True) -> dict:
    for d in repo.don_cho_doi_soat(limit=1000):
        if int(d["id"]) == order_id:
            return d
    if doi_cham_soc:
        raise ApiError("NOT_FOUND",
                       "Đơn không nằm trong diện thưởng chăm sóc.")
    from app.db.repositories import order_repo

    don = order_repo.get_order(order_id)
    if not don:
        raise ApiError("NOT_FOUND", "Không tìm thấy đơn.")
    return dict(don)


def bang_doi_soat(ro: str = "all") -> dict:
    """Số liệu màn Đối soát: 3 rổ + đếm từng rổ + tổng tiền đang chờ duyệt."""
    tat_ca = repo.don_cho_doi_soat(ro="all")
    for d in tat_ca:
        d["thuong_uoc"] = (float(d["review_amount"] or 0)
                           if d["review_status"] == "duyet"
                           else thuong_cham_mot_don(
                               d["staff_role_id"], float(d["total_amount"] or 0)))
    dem = {"all": len(tat_ca)}
    for khoa in ("fixed", "wonder", "done"):
        dem[khoa] = sum(1 for d in tat_ca if d["ro"] == khoa)
    cho_duyet = sum(d["thuong_uoc"] for d in tat_ca if d["ro"] != "done")
    return {
        "rows": tat_ca if ro in ("", "all") else
                [d for d in tat_ca if d["ro"] == ro],
        "dem": dem, "cho_duyet": cho_duyet, "ro": ro or "all",
    }


# ------------------------------------------------------------------ phân loại tự động
def phan_loai_tu_dong(order_id: int) -> str | None:
    """Máy phân trục CÔNG SỨC cho một đơn (chạy lúc đơn giao thành công).

    Quy tắc mẫu: đơn của khách ĐÃ TỪNG MUA mà có chạm chăm sóc trước khi đặt
    → 'cham_soc'; còn lại 'tu_nhien'. Đơn người đã sửa tay thì KHÔNG đụng vào.
    """
    from app.db.client import get_pg_pool

    pool = get_pg_pool()
    with pool.connection() as conn:
        o = conn.execute(
            "select id, customer_id, classified_manually, created_at, "
            "       delivered_at, order_type "
            "from crm.orders where id = %s", (order_id,),
        ).fetchone()
        if not o or o["classified_manually"]:
            return None
        # Có lần chăm sóc nào TRƯỚC lúc đơn được tạo không?
        co_cham = conn.execute(
            """
            select exists (
                select 1 from crm.care_interactions ci
                 where ci.customer_id = %(kh)s and ci.created_at < %(luc)s
                   and ci.created_at > %(luc)s - interval '60 days'
            ) as co
            """,
            {"kh": o["customer_id"], "luc": o["created_at"]},
        ).fetchone()["co"]
        # Chạm quảng cáo cuối (last-touch) — đọc SONG SONG, không cộng doanh thu
        co_ads = conn.execute(
            "select exists (select 1 from crm.lead_attributions a "
            " where a.customer_id = %s and a.touch_type = 'last') as co",
            (o["customer_id"],),
        ).fetchone()["co"]
    truc = "cham_soc" if (co_cham and o["order_type"] != "new") else "tu_nhien"
    repo.phan_loai(order_id, effort_axis=truc, ads_attributed=bool(co_ads))
    return truc


def ghi_ky_luong(order_id: int, ngay_giao: date | None = None) -> str:
    """Ghi CỨNG kỳ lương cho đơn lúc giao thành công + phân loại tự động."""
    ky = (ngay_giao or hom_nay()).strftime("%Y-%m")
    repo.dat_ky_luong(order_id, ky)
    phan_loai_tu_dong(order_id)
    return ky
