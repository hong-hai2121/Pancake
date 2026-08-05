"""Luật bộ phận CSKH — QUY TRÌNH BA GIAI ĐOẠN + bảng việc (C6).

Port từ mẫu Kallet: `includes/cskh_quy_trinh.php` (bản chốt 02/08/2026) và nửa
CSKH của `includes/board_rules.php`.

## Đây KHÔNG phải màn "Chăm sóc C01-C09" sẵn có

Hai thứ khác hẳn nhau, sống song song, đừng gộp:

  * `care_service` (B9) — **liệu trình của MỘT đơn**: onboarding, phiếu chăm
    ngày 4/10/15/20/25, đánh giá triệu chứng. Kết thúc khi hết liệu trình.
  * File này (C6) — **vòng đời khách SAU khi nhận hàng**: cảm ơn → voucher →
    thang mua lại. Chạy mãi cho tới khi khách rời bảng (mặc định 210 ngày).

## Ba giai đoạn, neo vào NGÀY NHẬN HÀNG CUỐI

    GĐ1 · ngày 0 → trước mốc đầu   cảm ơn → khách im thì gọi → tặng voucher
    GĐ2 · voucher còn hạn          nhắc 15 · 7 · 3 · 0 ngày TRƯỚC hết hạn
    GĐ3 · từ D45, mỗi 15 ngày      mốc XEN KẼ có khuyến mãi → bám đuổi 3 ngày,
                                   buông ở D210

## Sáu luật đã trả giá để có — ĐỪNG "sửa cho gọn"

1. **Đơn giao thành công: tiêu mã CŨ TRƯỚC, rồi mới xét tặng mã mới.** Ngược
   thứ tự là luật "mỗi khách 1 mã sống" tự chặn không cho tặng mã mới.
2. **Xét mã sống tại NGÀY ĐẶT ĐƠN, không phải ngày giao.** Khách đặt ngày 28
   (mã còn hạn) mà hàng về ngày 35 (mã hết hạn ngày 33) — xét lúc giao thì
   khách mua rồi vẫn bị coi là "không dùng voucher", bị đẩy sang GĐ3 và mất
   luôn mã mới.
3. **Việc tặng voucher CÒN NẰM ĐÓ cho tới khi tặng xong.** Bản đầu của mẫu kẹp
   `d <= lưới` với `d >= lưới` nên cột chỉ mở ĐÚNG 1 NGÀY — nhân viên bận hôm
   đó là khách rơi khỏi cột vĩnh viễn, GĐ2 không bao giờ khởi động.
4. **Mệnh giá 0 = máy KHÔNG tặng.** Voucher là tiền: thà không phát còn hơn
   phát bừa một mệnh giá đoán mò.
5. **Mốc khuyến mãi không có đợt nào đang chạy thì chăm như mốc thường** —
   không bịa nội dung khuyến mãi ra gửi khách.
6. **Khách đang có ĐƠN CHẠY thì rời hẳn bảng việc**, kể cả cột gấp. Hàng đang
   trên đường mà nhân viên nhắn mời mua lại là mất mặt với khách.

Công tắc tổng `cskh_flow_enabled` mặc định TẮT: bảng việc chạy y luật dải ngày
cũ (30/60/150) cho tới khi người dùng bật.
"""

from datetime import date, timedelta

from app.core import runtime_config
from app.core.errors import ApiError
from app.core.ngay import bay_gio, hom_nay
from app.db.repositories import cskh_repo as repo


# ------------------------------------------------------------------ cấu hình
def bat() -> bool:
    """Công tắc tổng của quy trình mới. TẮT = bảng việc chạy luật cũ."""
    return bool(runtime_config.bat("cskh_flow_enabled"))


def moc_dau() -> int:
    """Mốc chăm định kỳ ĐẦU TIÊN — số ngày kể từ ngày nhận hàng."""
    return max(1, int(runtime_config.so("cskh_first_milestone", 45)))


def moc_cach() -> int:
    """Hai mốc định kỳ liền nhau cách nhau mấy ngày."""
    return max(1, int(runtime_config.so("cskh_milestone_gap", 15)))


def ngay_buong() -> int:
    """Quá bao nhiêu ngày không nhận hàng thì khách RỜI bảng việc (coi là ngủ).

    ⚠️ 210 này KHÁC ba con số 180 của hệ thống (giảm quyền lợi hạng thẻ · nhắc
    cuối thang mua lại · thôi phân công). Xem docs/PORT-TU-MAU-KALLET.md.
    """
    return max(1, int(runtime_config.so("cskh_leave_days", 210)))


def qua_han_ngay() -> int:
    """Quá bấy nhiêu ngày kể từ khi mốc MỞ mà chưa chăm thì vào cột Quá hạn."""
    return max(1, int(runtime_config.so("cskh_overdue_days", 3)))


def luoi_ngay() -> int:
    """Lưới an toàn GĐ1: khách im đủ bấy nhiêu ngày thì VẪN tặng voucher."""
    return max(1, int(runtime_config.so("cskh_safety_days", 3)))


def ngay_goi() -> int:
    """Khách không phản hồi tin cảm ơn sau mấy ngày thì sinh việc GỌI."""
    return max(1, int(runtime_config.so("cskh_call_after_days", 1)))


def ctkm_ngay() -> int:
    """Đợt bám đuổi khuyến mãi kéo dài mấy ngày."""
    return max(1, int(runtime_config.so("cskh_promo_days", 3)))


def han_voucher() -> int:
    """Hạn voucher tính từ ngày phát.

    🔑 DÙNG LẠI khoá `voucher_expiry_days` màn Voucher đã dùng. Đẻ khoá riêng
    là hai nguồn cấu hình đá nhau: người tặng tay ăn số này, máy tặng ăn số kia.
    """
    return max(1, int(runtime_config.so("voucher_expiry_days", 30)))


def nhip_voucher() -> list[int]:
    """Các nhịp nhắc — số ngày TRƯỚC ngày hết hạn (0 = đúng ngày hết hạn).

    Đọc chuỗi "15,7,3,0" ở Cài đặt. Rác thì lùi về bộ mặc định chứ không tắt
    hẳn việc nhắc.
    """
    raw = str(runtime_config.lay("voucher_remind_days") or "")
    ra: list[int] = []
    for phan in raw.replace(";", ",").split(","):
        phan = phan.strip()
        if phan.lstrip("-").isdigit() and int(phan) >= 0:
            ra.append(int(phan))
    if not ra:
        ra = [15, 7, 3, 0]
    return sorted(set(ra), reverse=True)      # xa → gần, dò nhịp đúng thứ tự


def may_tu_tang_voucher() -> bool:
    """Đ2 — công tắc luật "máy tự tặng voucher sau đơn đầu".

    Tách khỏi mệnh giá CỐ Ý: mệnh giá = 0 nghĩa là CHƯA cấu hình, còn tắt công
    tắc này nghĩa là đã cấu hình xong nhưng tạm ngưng. Gộp làm một thì muốn tạm
    ngưng phải xoá mệnh giá đi, bật lại là phải nhớ mà gõ lại con số.
    """
    return bool(runtime_config.bat("voucher_first_auto_on"))


def menh_gia_voucher() -> float:
    """LUẬT 4 — mệnh giá máy tự tặng. 0 = máy KHÔNG tặng, để người tặng tay."""
    return max(0.0, float(runtime_config.so("voucher_first_value", 0)))


# ------------------------------------------------------------------ voucher
def voucher_song(customer_id: int, ngay=None):
    """Voucher khách đang cầm (None = không cầm mã nào)."""
    return repo.voucher_song(customer_id, ngay)


def duoc_tang_voucher(customer_id: int, ngay=None) -> bool:
    """Mỗi khách CHỈ 1 MÃ SỐNG — hết hạn hoặc đã dùng thì mới được tặng mã mới."""
    return repo.voucher_song(customer_id, ngay) is None


def _con_lai(v: dict, moc: date | None = None) -> int | None:
    """Số ngày còn lại của voucher (âm = đã quá hạn)."""
    het = v.get("expires_on") if v else None
    if not het:
        return None
    if not isinstance(het, date):
        het = date.fromisoformat(str(het)[:10])
    return (het - (moc or hom_nay())).days


def nhip_nhac_hom_nay(v: dict | None) -> int | None:
    """Hôm nay có rơi đúng nhịp nhắc của voucher này không?

    Trả số ngày còn lại nếu đúng nhịp; None nếu không phải nhịp nào.
    """
    if not v:
        return None
    con = _con_lai(v)
    if con is None or con < 0:
        return None                       # đã quá hạn — để lượt quét lo
    return con if con in nhip_voucher() else None


def cau_nhac_han(v: dict | None) -> str:
    """Câu việc cột "Nhắc hạn voucher" — nhãn ĐỘNG theo số ngày còn lại THẬT.

    Cố ý không dùng 4 câu cố định: nhân viên bỏ lỡ nhịp 15 ngày, khách trôi
    sang nhịp 7 thì vẫn phải hiện đúng "còn 7 ngày".
    """
    if not v:
        return ""
    ma = (v.get("code") or "").strip()
    ten = f"Voucher {ma}" if ma else "Voucher"
    con = _con_lai(v)
    if con is None:
        return ten
    if con < 0:
        # Mã quá hạn mà vẫn còn trạng thái "sống" ⇒ worker quét chưa chạy.
        # Nói thẳng ra để còn phát hiện, đừng im lặng.
        return f"{ten} ĐÃ QUÁ HẠN {abs(con)} ngày — kiểm tra lượt quét"
    if con == 0:
        return f"{ten} HẾT HẠN HÔM NAY — nhắc gấp"
    if con <= 3:
        return f"{ten} còn {con} ngày — sắp mất"
    if con <= 7:
        return f"{ten} còn {con} ngày — nhắc lần 2"
    return f"{ten} còn {con} ngày — nhắc khách dùng"


def don_thanh_cong(order_id: int, dry: bool = True) -> dict:
    """⚙️ ĐƠN GIAO THÀNH CÔNG → tiêu mã cũ, rồi mới xét tặng mã mới.

    Hai cái bẫy đã vá (LUẬT 1 và LUẬT 2 ở đầu file) nằm gọn trong hàm này —
    đọc kỹ trước khi đổi thứ tự hai bước.

    `dry=True` chỉ tính và kể việc, không ghi gì. Luôn chạy dry trước khi ghi
    thật khi soi tay: đây là tiền của khách.
    """
    ra: dict = {"don": int(order_id), "viec": []}
    o = repo.don(order_id)
    if not o:
        ra["viec"].append("không thấy đơn")
        return ra
    if (o.get("order_type") or "") == "exchange":
        ra["viec"].append("bỏ qua — đơn đổi (không tiêu mã, không sinh mã)")
        return ra
    if o["status"] not in ("delivered", "collected"):
        ra["viec"].append("bỏ qua — đơn chưa giao thành công")
        return ra

    cid = int(o["customer_id"])
    # NGÀY ĐẶT ĐƠN, không phải ngày giao — LUẬT 2.
    goc = o.get("ngay_dat") or o.get("created_at")
    ngay_dat = goc.date() if hasattr(goc, "date") else hom_nay()

    # ---- BƯỚC 1: tiêu mã cũ (xét theo NGÀY ĐẶT ĐƠN — LUẬT 2) ----
    cu = repo.voucher_song(cid, ngay_dat)
    if cu:
        ma = (cu.get("code") or "").strip() or "(chưa báo mã)"
        ra["viec"].append(f"tiêu mã {ma} — còn sống tại ngày đặt {ngay_dat}")
        if not dry:
            repo.tieu_voucher(int(cu["id"]), int(o["id"]))
        ra["tieu"] = int(cu["id"])
    else:
        ra["viec"].append("khách không cầm mã nào tại ngày đặt")

    # ---- BƯỚC 2: xét tặng mã mới (SAU bước 1 — LUẬT 1) ----
    # Chạy khô thì mã cũ chưa bị tiêu thật, phải tự trừ ra để lời kể không sai.
    con_song = repo.voucher_song(cid)
    if con_song and not (dry and cu and int(con_song["id"]) == int(cu["id"])):
        ra["viec"].append("không tặng — khách vẫn còn mã sống")
        return ra
    if not may_tu_tang_voucher():
        ra["viec"].append("không tặng — luật «máy tự tặng voucher sau đơn đầu» "
                          "đang TẮT (Cài đặt → Vòng đời khách)")
        return ra
    tien = menh_gia_voucher()
    if tien <= 0:
        ra["viec"].append("không tặng — CHƯA CẤU HÌNH mệnh giá "
                          "(Cài đặt → Ưu đãi → voucher_first_value)")
        return ra

    han = han_voucher()
    ra["viec"].append(f"tặng mã mới {tien:,.0f}đ · hạn {han} ngày"
                      .replace(",", "."))
    if not dry:
        v = repo.tang_voucher_may(
            cid, amount=tien, granted_on=hom_nay(),
            expires_on=hom_nay() + timedelta(days=han),
            note=f"máy tặng sau đơn giao thành công #{o['id']}",
            order_from_id=int(o["id"]))
        ra["tang"] = int(v["id"])
    return ra


# ------------------------------------------------------------------ thang mốc
def thang_mong_muon() -> list[dict]:
    """Bộ mốc MONG MUỐN theo cấu hình hiện tại — "bản thiết kế".

    Sinh từ 3 con số (mốc đầu · khoảng cách · ngày buông), KHÔNG chép tay danh
    sách: đổi cấu hình ở màn Cài đặt là thang tự đi theo.

    Mặc định 45/15/210 ⇒ D45·60·75·90·105·120·135·150·165·180·195 rồi D210 =
    BUÔNG. Cờ khuyến mãi gắn XEN KẼ, bắt đầu từ mốc đầu tiên.
    """
    dau, cach = moc_dau(), moc_cach()
    buong = max(dau + cach, ngay_buong())
    ra, i, d = [], 0, dau
    while d < buong:
        ra.append({
            "code": f"cskh_{d}", "offset_days": d,
            "window_from": d, "window_to": d + cach - 1,   # liền nhau, KHÔNG chồng
            "board_column": f"moc_{d}", "promo": i % 2 == 0, "buong": False,
        })
        d += cach
        i += 1
    # Mốc BUÔNG nằm NGOÀI vòng chăm, chỉ để đánh dấu khách rời bảng.
    ra.append({"code": f"cskh_{buong}", "offset_days": buong,
               "window_from": buong, "window_to": 99999,
               "board_column": "moc_out", "promo": False, "buong": True})
    return ra


def seed_thang(dry: bool = True) -> list[dict]:
    """Đưa bảng `care_milestones` về đúng bộ mốc mong muốn.

    `dry=True` CHỈ TÍNH, không ghi. Luôn chạy dry trước: đây là dữ liệu điều
    khiển bảng việc của cả đội, sai là khách nhảy cột loạn ngay trong giờ làm.
    """
    muon = thang_mong_muon()
    giu = {m["code"] for m in muon}
    dang_co = {r["code"]: dict(r) for r in repo.moc(chi_active=False)}
    viec: list[dict] = []

    for m in muon:
        cu = dang_co.get(m["code"])
        thuoc = {k: m[k] for k in ("offset_days", "window_from", "window_to",
                                   "board_column", "promo")}
        if not cu:
            viec.append({"viec": "them", "ma": m["code"],
                         "cua_so": f'{m["window_from"]}–{m["window_to"]}',
                         "ctkm": "có" if m["promo"] else "không"})
            if not dry:
                repo.luu_moc(m["code"], **thuoc)
            continue
        doi = any(cu.get(k) != v for k, v in thuoc.items()) or not cu["active"]
        if doi:
            viec.append({"viec": "sua", "ma": m["code"],
                         "cua_so_cu": f'{cu["window_from"]}–{cu["window_to"]}',
                         "cua_so_moi": f'{m["window_from"]}–{m["window_to"]}'})
        if not dry:
            repo.luu_moc(m["code"], **thuoc)

    # TẮT mốc cũ không còn trong bộ mới — TẮT chứ KHÔNG xoá (giữ lịch sử).
    for ma, r in dang_co.items():
        if ma in giu or not r["active"]:
            continue
        viec.append({"viec": "tat", "ma": ma, "ly_do": "không còn trong thang mới"})
        if not dry:
            repo.tat_moc(ma)
    return viec


_MAC_DINH_THANG = [
    {"code": "cskh_30", "offset_days": 30, "window_from": 16, "window_to": 45},
    {"code": "cskh_60", "offset_days": 60, "window_from": 46, "window_to": 75},
    {"code": "cskh_90", "offset_days": 90, "window_from": 76, "window_to": 105},
    {"code": "cskh_120", "offset_days": 120, "window_from": 106, "window_to": 135},
    {"code": "cskh_150", "offset_days": 150, "window_from": 136, "window_to": 165},
    {"code": "cskh_180", "offset_days": 180, "window_from": 166, "window_to": 210},
]


def moc_thang() -> list[dict]:
    """Thang mốc đang dùng — CHỈ mốc chăm.

    Bỏ mốc "buông" (cửa sổ 211–99999): nó nằm ngoài vòng chăm nên gắn nhãn
    "mốc 210 · chưa chăm" là vô nghĩa. Bảng rỗng → dùng bộ mặc định để bảng
    việc không chết trắng ở máy mới cài.
    """
    vong = ngay_buong()
    ra = [dict(r) for r in repo.moc()
          if r["board_column"] != "moc_out" and 0 < r["window_to"] <= vong]
    return ra or [{**m, "board_column": f'moc_{m["offset_days"]}',
                   "promo": False} for m in _MAC_DINH_THANG]


def moc_hien_tai(d: int | None) -> dict | None:
    """Mốc khách ĐANG ĐỨNG theo số ngày kể từ nhận hàng. None = chưa tới mốc đầu."""
    if d is None:
        return None
    for m in moc_thang():
        if m["window_from"] <= d <= m["window_to"]:
            return m
    return None


def _ngay_moc(kh: dict, cong: int = 0) -> date | None:
    """Ngày dương lịch ứng với mốc N của khách (ngày nhận hàng + N)."""
    nhan = kh.get("last_delivered_at")
    if not nhan:
        return None
    goc = nhan.date() if hasattr(nhan, "date") else date.fromisoformat(str(nhan)[:10])
    return goc + timedelta(days=int(cong))


def moc_da_cham(kh: dict, mm: dict | None) -> bool:
    """Đã chăm ở mốc đang đứng chưa? = có lượt chạm kể từ ngày VÀO cửa sổ mốc."""
    if not mm or not kh.get("cham_cuoi"):
        return False
    cham = kh["cham_cuoi"]
    cham = cham.date() if hasattr(cham, "date") else date.fromisoformat(str(cham)[:10])
    mo = _ngay_moc(kh, mm["window_from"])
    return mo is not None and cham >= mo


def moc_lo(kh: dict, d: int | None) -> int:
    """Số mốc đã trôi qua mà không ai chăm (nhãn "lỡ N mốc")."""
    if d is None or _ngay_moc(kh) is None:
        return 0
    cham = kh.get("cham_cuoi")
    cham = (cham.date() if hasattr(cham, "date")
            else date.fromisoformat(str(cham)[:10])) if cham else None
    n = 0
    for m in moc_thang():
        if m["window_to"] >= d:
            break                                   # cửa sổ chưa trôi qua
        if cham is None or cham < _ngay_moc(kh, m["window_from"]):
            n += 1
    return n


# ------------------------------------------------------------------ khuyến mãi
def ctkm_dang_chay() -> dict | None:
    return repo.ctkm_dang_chay()


def moc_la_ctkm(mm: dict | None) -> bool:
    return bool(mm and mm.get("promo"))


def ctkm_cau_viec(kh: dict, d: int | None, goi: dict | None = None) -> str:
    """Câu việc trong ĐỢT BÁM ĐUỔI của mốc khuyến mãi. '' = không thuộc đợt nào.

    Luật: ngày 1 gửi ưu đãi · khách PHẢN HỒI mà chưa đặt thì GỌI LUÔN ngày 1 ·
    khách im thì gọi ngày 2–3 · mỗi khách chỉ gọi 1 LẦN cả đợt · hết đợt không
    mua thì hẹn dịp sau, chờ mốc kế tiếp.
    """
    mm = moc_hien_tai(d)
    if not mm or not moc_la_ctkm(mm):
        return ""
    trong_dot = d - int(mm["window_from"]) + 1          # 1 · 2 · 3 …
    if trong_dot > ctkm_ngay():
        return ""                                        # hết đợt → hẹn dịp sau

    ct = ctkm_dang_chay()
    ten = (ct.get("name") or "").strip() if ct else ""
    if not moc_da_cham(kh, mm):
        # LUẬT 5 — không có đợt nào đang chạy thì không bịa nội dung ra gửi.
        return f"Gửi ưu đãi: {ten}" if ten else "Gửi ưu đãi khuyến mãi"
    if goi:
        return ""                                        # mỗi khách 1 cuộc gọi
    if _da_phan_hoi(kh):
        return "Khách đã trả lời mà chưa đặt — gọi push ngay"
    if trong_dot >= 2:
        return (f"Khách chưa phản hồi — gọi push "
                f"(ngày {trong_dot}/{ctkm_ngay()})")
    return f"Đã gửi ưu đãi: {ten} — chờ khách" if ten else "Đã gửi ưu đãi — chờ khách"


# ------------------------------------------------------------------ dải & cột
def nguong() -> tuple[int, int, int]:
    """NGƯỠNG dải ngày — NGUỒN DUY NHẤT của công thức ×4/×8.

    Bật quy trình mới: [D45, D105, D165]. Tắt: bộ cũ [30, 60, 150].
    Trước đây mẫu chép công thức này ba nơi, sửa một chỗ là hai chỗ kia lệch.
    """
    if not bat():
        return 30, 60, 150
    dau, cach = moc_dau(), moc_cach()
    return dau, dau + cach * 4, dau + cach * 8


def dai_ngay(d: int | None) -> str:
    """Số ngày kể từ nhận hàng → cột dải ngày. Gom 4 mốc một cột để bảng vẫn
    đúng 3 cột, nhân viên không phải học lại."""
    if d is None:
        return "moi_nhan_hang"
    dau, b1, b2 = nguong()
    if d < dau:
        return "moi_nhan_hang"
    if d < b1:
        return "cham_dinh_ky"
    if d < b2:
        return "den_ky_mua_lai"
    return "sap_roi_bo"


def dai_presets() -> list[tuple[str, str]]:
    """Dải "ngày nhận hàng" cho ô lọc nhanh — sinh từ ĐÚNG ngưỡng `nguong()`.

    Nhờ vậy bật/tắt công tắc hay đổi mốc đầu / khoảng cách ở Cài đặt là dải tự
    đi theo: chọn "Chăm định kỳ" luôn ra đúng nhóm khách của cột đó, không bao
    giờ lệch. Nhãn mượn TÊN CỘT thật (đổi tên ở 1H thì đây đổi theo).

    🔑 Không có dải "đã buông": khách quá ngày buông không đứng ở cột nào, bày
    ra là thêm một nút bấm vào chẳng thấy gì.
    """
    buong = ngay_buong()
    dau, b1, b2 = nguong()
    b1, b2 = min(b1, buong), min(b2, buong)
    ten = {c["ma"]: c["ten"] for c in cac_cot()}
    ra = [("0-3", "Vừa nhận hàng (0–3 ngày)")]
    if dau > 4:
        ra.append((f"0-{dau - 1}",
                   f'{ten.get("moi_nhan_hang", "Mới nhận hàng")} '
                   f"(0–{dau - 1} ngày)"))
    if b1 > dau:
        ra.append((f"{dau}-{b1 - 1}",
                   f'{ten.get("cham_dinh_ky", "Chăm định kỳ")} '
                   f"({dau}–{b1 - 1} ngày)"))
    if b2 > b1:
        ra.append((f"{b1}-{b2 - 1}",
                   f'{ten.get("den_ky_mua_lai", "Đến kỳ mua lại")} '
                   f"({b1}–{b2 - 1} ngày)"))
    if buong > b2:
        ra.append((f"{b2}-{buong}",
                   f'{ten.get("sap_roi_bo", "Sắp rời bỏ")} '
                   f"({b2}–{buong} ngày)"))
    return ra


def _da_phan_hoi(kh: dict) -> bool:
    """Khách có nói gì SAU khi nhận hàng không?"""
    nhan, cuoi = kh.get("last_delivered_at"), kh.get("khach_cuoi")
    return bool(nhan and cuoi and cuoi >= nhan)


def _cho_dap(kh: dict) -> float | None:
    """Khách đang CHỜ mình trả lời (tin cuối là của khách) đã mấy giờ?
    None = không chờ ai cả."""
    khach, shop = kh.get("khach_cuoi"), kh.get("shop_cuoi")
    if not khach or (shop and shop > khach):
        return None
    return (bay_gio() - khach).total_seconds() / 3600


def cot_gap(kh: dict, d: int | None, v: dict | None = None,
            goi: dict | None = None) -> str | None:
    """Cột GẤP của quy trình mới. None = khách không rơi vào cột gấp nào.

    Thứ tự xét quan trọng: việc gấp hơn đứng trước.
    """
    if d is None:
        return None
    # --- GĐ2: đang cầm mã và hôm nay đúng nhịp nhắc ---
    if v is not None and nhip_nhac_hom_nay(v) is not None:
        return "nhac_han_voucher"
    # --- GĐ1: ngày 0 → trước mốc định kỳ đầu ---
    if d < moc_dau() and not v:
        # LUẬT 3 — việc tặng CÒN NẰM ĐÓ cho tới khi tặng xong.
        if _da_phan_hoi(kh):
            return "can_tang_voucher"
        if d >= luoi_ngay():
            return "can_tang_voucher"
        if d >= ngay_goi() and not goi:
            return "nhac_goi"       # đã gọi rồi thì thôi, KHÔNG gọi lần 2
    return None


def qua_han_moc(kh: dict, d: int | None) -> int | None:
    """Quá hạn MỐC: quá N ngày kể từ khi mốc mở mà chưa chăm. None = chưa quá.

    Đây là nguồn quá hạn THỨ HAI, cộng thêm nguồn cũ (khách nhắn mà chưa ai
    đáp) — không đụng gì tới nguồn cũ.
    """
    mm = moc_hien_tai(d)
    if not mm or moc_da_cham(kh, mm):
        return None
    qua = d - int(mm["window_from"])
    return qua if qua > qua_han_ngay() else None


# Cột bảng việc CSKH. (mã, tên, màu, câu việc, cho kéo tay)
def cac_cot(goc: bool = False) -> list[dict]:
    """Cột bảng việc. Tên/câu đổi theo công tắc: TẮT thì y như cũ.

    `goc=True` trả về tên GỐC trong mã, bỏ qua phần người dùng đặt lại — màn
    Cài đặt 1H cần nó để in chữ mờ trong ô ("chữ gốc là gì nếu xoá trắng").

    Tên cột và câu việc 📌 sửa được ở **Cài đặt → Mốc thời gian → 1H**, lưu
    dưới khoá tự do `bn_cskh_<mã>` / `bw_cskh_<mã>`. Đổi ở đó là đổi MỌI nơi
    hiện tên cột (bảng · pipeline · ô lọc trạng thái) vì tất cả đều đọc qua
    hàm này — mẫu Kallet cũng gom về một cửa đúng như vậy.
    """
    tren = bat()
    dau, cach = moc_dau(), moc_cach()

    def mo_ta(i: int) -> str:
        """4 mốc gom vào một cột, kể tên ra cho nhân viên biết cột chứa gì."""
        return "·".join(str(dau + cach * k) for k in range(i, i + 4))

    ds = [
        ("nong", "Nóng", "#E5484D", "Khách vừa phản hồi — trả lời ngay", True),
        ("qua_han", "Quá hạn", "#B0413E", "Việc quá hạn — xử ngay", False),
        ("moi_nhan_hang", "Mới nhận hàng", "#3B62D9",
         "Khách mới nhận hàng — hỏi thăm", True),
        ("nhac_goi", "Nhắc gọi", "#C25E00", "Nhắn không thấy đáp — gọi điện", True),
        ("can_tang_voucher", "Cần tặng voucher", "#8E5E9C",
         "Tới mốc tặng voucher", True),
        ("nhac_han_voucher", "Nhắc hạn voucher", "#B87514",
         "Voucher sắp hết hạn — nhắc dùng", True),
        ("cham_dinh_ky", "Chăm định kỳ" if tren else "Chăm hàng tháng", "#2E7D32",
         f"Chăm định kỳ (mốc {mo_ta(0)})" if tren else "Chăm định kỳ (mốc 30)", True),
        ("den_ky_mua_lai", "Đến kỳ mua lại", "#E0A417",
         f"Tới kỳ mua lại ({mo_ta(4)})" if tren else "Tới kỳ mua lại (60·90·120)",
         True),
        ("sap_roi_bo", "Sắp rời bỏ", "#B0413E",
         f"Sắp rời bỏ ({mo_ta(8)}) — cứu" if tren else "Sắp rời bỏ (150·180) — cứu",
         True),
        ("da_mua_lai", "Đã mua lại", "#2E7D32", "Đã mua lại — xong đợt", True),
        ("tu_choi", "Từ chối", "#78909C", "Từ chối đợt này — chờ mốc sau", True),
        ("ngung", "Ngừng liên hệ", "#5A5A5A", "Khách yêu cầu ngừng — không nhắn",
         False),
    ]
    if goc:
        return [{"ma": m, "ten": t, "mau": c, "viec": v, "keo": k}
                for m, t, c, v, k in ds]
    # Đọc MỘT LẦN cho cả 12 cột. Gọi `lay_tu_do` từng khoá là 24 lượt quét bảng
    # cấu hình cho mỗi lần vẽ bảng việc.
    ten_dat = runtime_config.lay_tu_do_theo_tien_to("bn_cskh_")
    viec_dat = runtime_config.lay_tu_do_theo_tien_to("bw_cskh_")
    return [{"ma": m,
             "ten": (ten_dat.get(f"bn_cskh_{m}") or "").strip() or t,
             "mau": c,
             "viec": (viec_dat.get(f"bw_cskh_{m}") or "").strip() or v,
             "keo": k}
            for m, t, c, v, k in ds]


COT_GAP = ("nong", "qua_han", "nhac_goi", "can_tang_voucher", "nhac_han_voucher")
COT_KHONG_VIEC = ("da_mua_lai", "tu_choi", "ngung")


def cot_cua(kh: dict, v: dict | None = None,
            goi: dict | None = None) -> tuple[str, str]:
    """Khách này nằm cột nào? Trả (mã cột, câu giải thích).

    Thứ tự xét CÓ Ý NGHĨA — đừng đảo:
      1. Cột người ĐẶT TAY thắng tất cả (đã tự nhả nếu khách nhắn lại).
      2. Ngừng liên hệ — trạng thái cuối.
      3. NÓNG / chờ đáp quá lâu — việc trả lời khách, gấp nhất.
      4. Cột gấp của quy trình mới (voucher · gọi).
      5. Quá hạn mốc.
      6. Dải ngày.
    """
    if kh.get("cskh_column"):
        return kh["cskh_column"], "người đặt tay"
    if kh.get("do_not_contact"):
        return "ngung", "khách yêu cầu ngừng liên hệ"
    cho = _cho_dap(kh)
    if cho is not None and cho <= 24:
        return "nong", "khách vừa nhắn, chưa ai đáp"
    if cho is not None and cho <= 72:
        return "qua_han", f"khách chờ đáp đã {int(cho)} giờ"
    d = kh.get("ngay")
    d = int(d) if d is not None else None
    if not bat():
        return dai_ngay(d), "theo dải ngày (quy trình cũ)"
    if (gap := cot_gap(kh, d, v, goi)):
        return gap, "quy trình CSKH"
    if (qua := qua_han_moc(kh, d)) is not None:
        return "qua_han", f"quá hạn mốc {qua} ngày"
    return dai_ngay(d), "theo dải ngày"


def cau_viec(kh: dict, cot: str, d: int | None = None, v: dict | None = None,
             goi: dict | None = None) -> str:
    """Câu 📌 hiện trên thẻ khách. Cột gấp CẤM câu chung chung — phải nói rõ
    khách đang ở nhịp nào / vì lý do gì, vì hai nhịp khác nhau thì độ gấp khác
    hẳn."""
    if cot == "nhac_han_voucher":
        return cau_nhac_han(v)
    if cot == "can_tang_voucher":
        if goi and (goi.get("call_result") or "") == "nghe":
            return "Gọi được, không đổi hàng — tặng voucher"
        if _da_phan_hoi(kh):
            return "Khách hài lòng — tặng voucher"
        return f"Đủ {luoi_ngay()} ngày không phản hồi — tặng voucher"
    if cot == "nhac_goi":
        return "Khách chưa phản hồi tin cảm ơn — gọi hỏi thăm"
    if cot == "qua_han":
        qua = qua_han_moc(kh, d)
        if qua is None:
            return "Khách đang chờ trả lời — đáp ngay"
        mm = moc_hien_tai(d)
        return (f'Quá hạn mốc D{mm["offset_days"] if mm else "?"} — '
                f"{qua} ngày chưa chăm")
    if cot == "nong":
        return "Khách vừa nhắn — trả lời ngay"
    if bat() and (cau := ctkm_cau_viec(kh, d, goi)):
        return cau
    mm = moc_hien_tai(d)
    if mm:
        return f'Mốc D{mm["offset_days"]} — chăm định kỳ'
    return "Khách mới nhận hàng — hỏi thăm"


def la_viec(kh: dict, cot: str, d: int | None) -> bool:
    """Khách này có phải VIỆC HÔM NAY không?

    LUẬT 6 — khách đang có ĐƠN CHẠY rời hẳn bảng việc, KỂ CẢ cột gấp: hàng
    đang trên đường mà nhắn mời mua lại là mất mặt. Khách không biến mất khỏi
    hệ thống, chỉ không tính là việc phải làm hôm nay.
    """
    if cot in COT_KHONG_VIEC:
        return False
    dang_chay = int(kh.get("dang_chay") or 0) > 0
    if cot in ("nong", "qua_han"):
        # Việc TRẢ LỜI KHÁCH ⇒ chỉ tính khi khách đang chờ đáp. Đáp xong là hết
        # việc, thẻ rơi xuống xét tiếp mốc chăm bên dưới.
        if _cho_dap(kh) is not None:
            return True
    elif cot in COT_GAP and not dang_chay:
        return True
    if dang_chay:
        return False
    mm = moc_hien_tai(d)
    if mm:
        return not moc_da_cham(kh, mm)
    # Chưa tới mốc đầu: chỉ GĐ1 mới sinh việc. Khách đang giữ voucher chờ tới
    # mốc thì việc của họ đã nằm ở cột gấp rồi — không sinh việc thứ hai.
    if bat() and d is not None and d > luoi_ngay():
        return False
    # Khách mới nhận hàng: 1 việc hỏi thăm, chăm rồi là thôi (cửa sổ tính từ
    # đúng ngày nhận hàng).
    return not moc_da_cham(kh, {"window_from": 0, "window_to": 0})


def uu_tien(kh: dict, cot: str, d: int | None) -> tuple:
    """Khoá SẮP XẾP: cột gấp trước, rồi khách VỪA CHẠM MỐC, hoà thì ai nhắn
    gần đây lên trước."""
    tin = kh.get("khach_cuoi")
    tin = -tin.timestamp() if tin else 0
    if cot in COT_GAP:
        return 0, tin, 0
    mm = moc_hien_tai(d)
    if not mm:
        return 1, 900000 if d is None else max(0, d), tin
    cach = d - int(mm["offset_days"])
    return 1, cach if cach >= 0 else 1000 + abs(cach), tin


# ------------------------------------------------------------------ bảng việc
QUET_TOI_DA = 3000      # trần QUÉT — số trên tab/ô lọc đếm trong phạm vi này
HIEN_TOI_DA = 500       # trần BÀY ra màn, thẻ gấp nhất trước


def _da_cham_xong(kh: dict) -> bool:
    """Đã chăm hôm nay VÀ khách chưa nhắn lại sau đó → xong việc, ẩn khỏi bảng.

    Mốc so là GIỜ chăm chứ không phải ngày: nhân viên nhắn lúc 9h, khách đáp
    lúc 14h thì việc CHƯA xong — so theo ngày sẽ nuốt mất ca này.
    """
    if int(kh.get("cham_hom_nay") or 0) <= 0:
        return False
    khach, cham = kh.get("khach_cuoi"), kh.get("cham_cuoi")
    return not khach or not cham or khach <= cham


def bang_viec(*, owner_id: int | None = None, q: str = "",
              chi_viec: bool = False, an_da_cham: bool = True,
              staff_id: int | None = None, chua_gan: bool = False,
              page_id: int | None = None, hang_the: str = "",
              nhan_tu: int | None = None, nhan_den: int | None = None,
              trang_thai: str = "") -> dict:
    """Số liệu màn Bảng việc CSKH: thẻ đã xếp cột + các ô đếm.

    `an_da_cham` — khách ĐÃ CHĂM HÔM NAY thì ẩn đi, TRỪ KHI khách nhắn lại SAU
    lần chăm (còn phải xử tiếp). Không có luật này thì bảng đầy thẻ đã làm xong
    và không ai biết hôm nay còn việc gì.

    Bộ lọc `staff_id`/`chua_gan`/`page_id`/`hang_the`/`nhan_tu`/`nhan_den` lọc ở
    SQL; riêng `chi_viec` và `trang_thai` (cột) lọc ở ĐÂY vì cột là thứ Python
    suy ra từ ngày nhận hàng + voucher + tin nhắn, SQL không biết.

    Thứ tự CÓ Ý NGHĨA: xếp cột cho toàn bộ phạm vi quét → ĐẾM → rồi mới lọc và
    cắt danh sách. Đếm sau khi lọc thì mọi cột không được chọn đều về 0, mà ô
    lọc trạng thái lại đang bày chính mấy con số đó.
    """
    rows = repo.bang_viec(
        owner_id=owner_id, q=q, ngay_buong=ngay_buong(), limit=QUET_TOI_DA,
        staff_id=staff_id, chua_gan=chua_gan, page_id=page_id,
        hang_the=hang_the, nhan_tu=nhan_tu, nhan_den=nhan_den)
    ids = [int(r["id"]) for r in rows]
    v_map = repo.voucher_map(ids) if bat() else {}
    # Đợt gọi tính từ ngày vào cửa sổ mốc gần nhất — đơn giản hoá: lấy cả
    # khoảng bám đuổi dài nhất có thể (mốc cách nhau `moc_cach` ngày).
    goi_map = repo.goi_map(ids, hom_nay() - timedelta(days=moc_cach())) \
        if bat() else {}

    cot_ds = cac_cot()
    theo_cot: dict[str, list] = {c["ma"]: [] for c in cot_ds}
    the: list[dict] = []
    # Đếm RIÊNG, không suy từ `the`: thẻ đã chăm bị `continue` bỏ khỏi `the` nên
    # đếm sau vòng lặp là ra 0. Màn cần cả hai số — "hôm nay đã xong N" (khích
    # lệ) và "đã ẩn N thẻ" (giải thích vì sao bảng ngắn hơn mình tưởng).
    xong_hom_nay = da_an = 0
    for r in rows:
        kh = dict(r)
        if int(kh.get("cham_hom_nay") or 0) > 0:
            xong_hom_nay += 1
        if an_da_cham and _da_cham_xong(kh):
            da_an += 1
            continue
        d = int(kh["ngay"]) if kh.get("ngay") is not None else None
        v = v_map.get(int(kh["id"]))
        goi = goi_map.get(int(kh["id"]))
        ma, vi_sao = cot_cua(kh, v, goi)
        kh.update({
            "cot": ma, "cot_vi_sao": vi_sao, "la_viec": la_viec(kh, ma, d),
            "cau_viec": cau_viec(kh, ma, d, v, goi),
            "voucher": v, "goi": goi,
            "moc": moc_hien_tai(d), "moc_lo": moc_lo(kh, d),
            "cho_dap": _cho_dap(kh) is not None,
            "uu_tien": uu_tien(kh, ma, d),
        })
        the.append(kh)
        theo_cot.setdefault(ma, []).append(kh)
    for ds in theo_cot.values():
        ds.sort(key=lambda x: x["uu_tien"])
    # Chế độ Bảng đọc thẳng `the`, mà danh sách còn bị cắt ở `HIEN_TOI_DA` —
    # không xếp theo cùng khoá ưu tiên thì cái bị cắt đi lại là thẻ gấp nhất.
    the.sort(key=lambda x: x["uu_tien"])

    # --- đếm TRƯỚC khi lọc theo tab/cột ---
    dem = {
        "viec_hom_nay": sum(1 for x in the if x["la_viec"]),
        "qua_han": len(theo_cot.get("qua_han", [])),
        "nhac_goi": len(theo_cot.get("nhac_goi", [])),
        "vua_phan_hoi": sum(1 for x in the if x["cho_dap"]),
        "cho_tang_voucher": len(theo_cot.get("can_tang_voucher", [])),
        "nhac_han": len(theo_cot.get("nhac_han_voucher", [])),
        "tong": len(the),
    }
    dem_cot = {c["ma"]: len(theo_cot.get(c["ma"], [])) for c in cot_ds}

    # --- lọc tab/cột, rồi mới cắt danh sách bày ra ---
    if chi_viec:
        the = [x for x in the if x["la_viec"]]
    if trang_thai and trang_thai in theo_cot:
        the = [x for x in the if x["cot"] == trang_thai]
    tong = len(the)
    if tong > HIEN_TOI_DA:
        the = the[:HIEN_TOI_DA]
    giu = {x["id"] for x in the}
    theo_cot = {k: [x for x in v if x["id"] in giu]
                for k, v in theo_cot.items()}

    return {
        "cot": cot_ds, "theo_cot": theo_cot, "the": the,
        "tong": tong, "cham_tran": len(rows) >= QUET_TOI_DA,
        "xong_hom_nay": xong_hom_nay, "da_an": da_an,
        "bat": bat(), "ctkm": ctkm_dang_chay(),
        "khach_ngu": repo.dem_khach_ngu(ngay_buong()),
        "dem": dem, "dem_cot": dem_cot,
    }


# ------------------------------------------------------------------ thao tác
def keo_the(customer_id: int, cot: str, *, nguoi: int | None = None) -> dict:
    """Kéo thẻ sang cột khác. Cột do máy suy ra hoàn toàn thì không kéo được —
    kéo vào đó là nói dối dữ liệu."""
    hop_le = {c["ma"]: c for c in cac_cot()}
    if cot not in hop_le:
        raise ApiError("VALIDATION_ERROR", f"Cột lạ: {cot}")
    if not hop_le[cot]["keo"]:
        raise ApiError("CONFLICT",
                       f'Cột "{hop_le[cot]["ten"]}" do máy suy ra, không kéo '
                       "tay được.")
    kq = repo.dat_cot(customer_id, cot, nguoi)
    if not kq:
        raise ApiError("NOT_FOUND", "Không tìm thấy khách.")

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="keo_the_cskh", object_type="customer",
                   object_id=customer_id, user_id=nguoi, new_value={"cot": cot})
    return dict(kq)


def mo_lai(customer_id: int, *, nguoi: int | None = None) -> dict:
    """Nhả cột đặt tay, trả thẻ về cho máy xếp."""
    kq = repo.dat_cot(customer_id, None, nguoi)
    if not kq:
        raise ApiError("NOT_FOUND", "Không tìm thấy khách.")
    return dict(kq)


def ghi_goi(customer_id: int, ket_qua: str, *, nguoi: int | None = None,
            tom_tat: str = "") -> dict:
    """Ghi kết quả cuộc gọi GĐ1.

    Thiếu cột này thì máy không biết đẩy khách sang "tặng voucher" (nghe máy)
    hay để lại chờ (không nghe).
    """
    if ket_qua not in ("nghe", "khong_nghe", "hen_goi_lai"):
        raise ApiError("VALIDATION_ERROR", f"Kết quả gọi lạ: {ket_qua}")
    return dict(repo.ghi_goi(customer_id, ket_qua, nguoi=nguoi, tom_tat=tom_tat))


def ghi_cham(customer_id: int, *, nguoi: int | None = None,
             tom_tat: str = "") -> dict:
    """Đóng mốc đang mở của khách bằng một lượt chạm."""
    return dict(repo.ghi_cham(customer_id, nguoi=nguoi, tom_tat=tom_tat))


# ------------------------------------------------------------------ khuyến mãi
def luu_ctkm(promo_id: int | None, *, ten: str, noi_dung: str = "",
             tu_ngay=None, den_ngay=None, active: bool = False,
             nguoi: int | None = None) -> dict:
    ten = (ten or "").strip()
    if not ten:
        raise ApiError("VALIDATION_ERROR", "Đợt khuyến mãi phải có tên.")
    if tu_ngay and den_ngay and str(den_ngay) < str(tu_ngay):
        raise ApiError("VALIDATION_ERROR", "Ngày kết thúc trước ngày bắt đầu.")
    return dict(repo.ctkm_luu(
        promo_id, name=ten, content=(noi_dung or "").strip(),
        start_on=tu_ngay or None, end_on=den_ngay or None,
        active=bool(active), created_by=nguoi))


def xoa_ctkm(promo_id: int) -> None:
    repo.ctkm_xoa(promo_id)


def hook_don_giao_thanh_cong(order_id: int) -> dict | None:
    """Gọi từ `order_service` khi đơn chuyển sang giao thành công.

    Công tắc TẮT thì KHÔNG ĐỘNG GÌ tới voucher — bật/tắt phải đổi được hành vi
    ngay, không phải sửa code rồi restart.
    """
    if not bat():
        return None
    return don_thanh_cong(order_id, dry=False)
