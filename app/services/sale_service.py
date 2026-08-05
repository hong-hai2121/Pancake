"""Luật bộ phận SALE — thang bám đuổi + bảng việc (C5).

Port từ mẫu Kallet: `includes/sale_buoc.php` · `includes/board_rules.php`.

## Vì sao có file này

Pipeline 13 giai đoạn sẵn có bắt nhân viên TỰ KÉO thẻ. Thực tế: không ai kéo,
và bảng lúc nào cũng sai. Thang bám đuổi giải quyết bằng cách khác — **máy đọc
tin nhắn thật** rồi tự biết đã nói tới đâu với khách:

    con trỏ = 3  ⇒  đã báo giá, đã gửi feedback, đã hỏi lý do phân vân
                 ⇒  VIỆC CẦN LÀM là bước 4: gửi mã giảm giá

Hai thứ SỐNG SONG SONG, đừng gộp:
  * `leads.stage_id`  — giai đoạn do NGƯỜI đặt: "khách ở đâu trong quy trình"
  * `leads.sale_step` — con trỏ do MÁY dò:      "câu tiếp theo cần nói là gì"

## Năm luật đã trả giá để có

1. **NGÀY BẬT THANG** là chốt chặn quan trọng nhất. Không có nó, lượt dò đầu
   đọc CẢ LỊCH SỬ → khách nhắn qua lại vài tháng nhảy thẳng bước cuối → "hết
   thang" → rơi khỏi bảng việc. Cả bảng Sale trống trong một nốt nhạc.
2. **Con trỏ CHỈ TIẾN.** Đọc lại tin cũ không bao giờ kéo lùi ai.
3. **Mỗi tin nhảy tối đa `cua_so` bước.** Một cụm chữ lạc không được đẩy khách
   thẳng tới bước cuối rồi bị buông oan.
4. **Khách đang chờ trả lời thì con trỏ ĐỨNG YÊN** — việc lúc đó là ĐÁP KHÁCH.
5. **Nhảy cóc phải ĐƯỢC ĂN CẢ NGÃ VỀ KHÔNG**: đích xa hơn trần thì không nhảy
   tí nào. Nhảy nửa vời đẩy khách vào một bước chẳng liên quan gì tới điều họ
   vừa nói — còn tệ hơn đứng yên.

## Một cái bẫy ngôn ngữ (mẫu đo trên 53.000 tin thật rồi mới chốt)

Bỏ dấu tiếng Việt làm nhiều cụm đụng nhau. Ví dụ có thật: `"đắt"` → `"dat"`
đụng `"ĐẶT hàng"` (619 tin sai). Nên từ khoá phải là **cụm nhiều chữ**
(`"đắt quá"`, `"sao đắt"`), đừng bao giờ khai một từ đơn.
"""

import re
from datetime import timedelta

from app.core import runtime_config
from app.core.errors import ApiError
from app.core.ngay import bay_gio, hom_nay
from app.db.repositories import sale_repo as repo
from app.services import tieng_viet as tv


# ------------------------------------------------------------------ cấu hình
def ngay_bat_thang():
    """LUẬT 1 — chỉ đọc tin TỪ ngày này. Chưa đặt thì lấy hôm nay (mọi khách
    khởi động lại từ bước 0, an toàn)."""
    v = str(runtime_config.lay("sale_ladder_start") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        from datetime import date

        return date.fromisoformat(v)
    return hom_nay()


def cau_hinh() -> dict:
    """Mọi con số của thang — chỉnh ở Cài đặt, không phải sửa code."""
    return {
        "nghi": int(runtime_config.so("sale_step_rest_hours", 6)),
        "tran": int(runtime_config.so("sale_step_max_per_day", 2)),
        "cua_tu": int(runtime_config.so("sale_step_hour_from", 8)),
        "cua_den": int(runtime_config.so("sale_step_hour_to", 21)),
        "nong_gio": int(runtime_config.so("sale_hot_hours", 24)),
        "nong_buoc": int(runtime_config.so("sale_hot_max_steps", 3)),
        "cua_so": int(runtime_config.so("sale_step_window", 2)),
        "nhay": int(runtime_config.so("sale_step_skip_max", 3)),
        "ket_ngay": int(runtime_config.so("sale_stuck_days", 3)),
    }


def thang() -> dict[int, dict]:
    """Thang bước đang dùng, khoá theo step_no. Rỗng = mọi luật thang tự tắt."""
    return {int(r["step_no"]): dict(r) for r in repo.thang()}


def bat() -> bool:
    return bool(thang())


# ------------------------------------------------------------------ so khớp
def _khop_buoc(noi_dung: str, co_anh: bool, tu_khoa: str) -> str | None:
    """Tin này có khớp bộ từ khoá của một bước không? Trả cụm khớp để giải
    thích được, hoặc None.

    Ba từ ĐẶC BIỆT dò trên NGUYÊN VĂN (không bỏ dấu):
      #anh — tin có ảnh · #gia — tin có số tiền · #ma — tin có mã giảm
    """
    raw = noi_dung or ""
    for k in (tu_khoa or "").split(","):
        k = k.strip()
        if not k:
            continue
        if k.startswith("#"):
            if k == "#anh" and co_anh:
                return "#anh (tin có ảnh)"
            if k == "#gia" and _co_gia(raw):
                return "#gia (tin có số tiền)"
            if k == "#ma" and _co_ma_giam(raw):
                return "#ma (tin có mã giảm)"
            continue
        if tv.khop(k, raw):
            return k
    return None


_RE_GIA = re.compile(
    r"\d{2,4}\s?k\b|\d{1,3}[.,]\d{3}|\d{2,4}\s?(nghìn|nghin|ngàn|ngan|tr|triệu|trieu)",
    re.IGNORECASE)

# Mã giảm = cụm IN HOA có CẢ chữ lẫn số (SALE50K, UUDAI10).
_RE_MA = re.compile(r"\b(?=[A-Z0-9]{5,12}\b)(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]+\b")
# ...NHƯNG loại mã SKU / mã đơn (1-3 chữ đầu + dãy số + đuôi ngắn): AL414, DH123456.
# Mẫu đo trên 300.000 tin: không loại thì mọi khách nhận tin giới thiệu sản phẩm
# đều bị tính là "đã gửi mã giảm".
_RE_SKU = re.compile(r"^[A-Z]{1,3}\d{2,8}[A-Z]{0,2}$")


def _co_gia(raw: str) -> bool:
    return bool(_RE_GIA.search(raw or ""))


def _co_ma_giam(raw: str) -> bool:
    return any(not _RE_SKU.match(tk) for tk in _RE_MA.findall(raw or ""))


# ------------------------------------------------------------------ bộ dò
def do_buoc(customer_id: int) -> tuple[int, object | None, list[str]]:
    """Đọc lại con trỏ từ TIN NHẮN THẬT.

    Trả (bước, mốc tin làm nhích cuối, nhật ký giải thích). Nhật ký để màn hình
    trả lời được câu "vì sao khách này đang ở bước 4" — con số không giải thích
    được thì không ai tin.
    """
    buoc_ds = thang()
    if not buoc_ds:
        return 0, None, []
    cfg = cau_hinh()
    tin = repo.tin_cua_lead(customer_id, ngay_bat_thang())
    if not tin:
        return 0, None, []

    cao_nhat = max(buoc_ds)
    cur, at, ve = 0, None, []
    luot_mo = False          # đang trong một LƯỢT nhắn của shop?
    luot_da_tinh = False     # lượt này đã ăn 1 bước dự phòng chưa?
    dem_ngay: dict = {}      # ngày -> số bước nhích THẬT (trần/ngày)

    for m in tin:
        luc = m["sent_at"]
        raw = m["noi_dung"] or ""

        if m["huong"] == "khach":
            luot_mo, luot_da_tinh = False, False      # khách cắt lượt
            # 🐸 NHẢY CÓC — khách nói toạc điều đang vướng thì bỏ qua bước giữa.
            if cfg["nhay"] > 0 and raw:
                tran = min(cur + cfg["nhay"], cao_nhat)
                moc, vi_sao = cur, ""
                for b in sorted(buoc_ds):
                    dich = b - 1
                    if dich <= moc or dich > tran:
                        continue
                    kw = (buoc_ds[b].get("keywords_customer") or "").strip()
                    if not kw:
                        continue
                    if (trung := _khop_buoc(raw, False, kw)):
                        moc, vi_sao = dich, trung
                if moc > cur:
                    cur, at = moc, luc
                    ve.append(f'khách nói "{vi_sao}" → nhảy cóc tới bước {cur + 1}')
            continue

        # --- tin phía shop ---
        ngay = luc.date()
        het_tran = dem_ngay.get(ngay, 0) >= cfg["tran"]

        # 1) dò từ khoá — chính xác nhất, tin MÁY cũng được tính nếu đúng từ khoá
        trung_buoc, vi_sao = 0, ""
        for b in sorted(buoc_ds):
            if b <= cur or b > cur + cfg["cua_so"]:
                continue          # LUẬT 3 — mỗi tin nhảy tối đa cua_so bước
            if (t := _khop_buoc(raw, bool(m["co_anh"]),
                                buoc_ds[b].get("keywords_agent") or "")):
                trung_buoc, vi_sao = b, t
        if trung_buoc and not het_tran:
            cur, at = trung_buoc, luc
            dem_ngay[ngay] = dem_ngay.get(ngay, 0) + 1
            ve.append(f'shop nhắn "{vi_sao}" → bước {cur}')
            luot_mo, luot_da_tinh = True, True
            continue

        # 2) DỰ PHÒNG — không dò ra từ khoá nào thì mỗi LƯỢT nhắn tính 1 bước.
        #    CHỈ dành cho NGƯỜI THẬT: tin máy không có từ khoá thì không tính,
        #    nếu không bot chào tự động sẽ đẩy hết khách lên bước cao.
        if not m["nguoi_that"]:
            continue
        if not luot_mo:
            luot_mo, luot_da_tinh = True, False
        if not luot_da_tinh and cur < cao_nhat and not het_tran:
            cur, at = cur + 1, luc
            dem_ngay[ngay] = dem_ngay.get(ngay, 0) + 1
            luot_da_tinh = True
            ve.append(f"shop nhắn (không rõ bước) → dự phòng: bước {cur}")

    return cur, at, ve


def dong_bo_con_tro(lead_id: int, customer_id: int) -> dict | None:
    """Chạy bộ dò rồi ghi con trỏ. LUẬT 2 — repo chỉ ghi khi bước MỚI lớn hơn."""
    buoc, at, _ = do_buoc(customer_id)
    if not buoc:
        return None
    moc = repo.moc_tin(customer_id)
    if moc and moc["khach_cuoi"] and moc["shop_cuoi"] \
            and moc["khach_cuoi"] > moc["shop_cuoi"]:
        # Khách đáp sau tin shop = có đối thoại hai chiều → vào cột Tiềm năng
        repo.danh_dau_tra_loi(lead_id, moc["khach_cuoi"])
    return repo.dat_con_tro(lead_id, buoc, at or bay_gio())


def quet_tat_ca(gioi_han: int = 300) -> dict:
    """Một vòng worker: dò lại con trỏ cho lead có tin mới + nhả cột đã cũ."""
    nha = repo.nha_cot_da_cu()
    doi = 0
    for l in repo.lead_can_do(gioi_han=gioi_han):
        if dong_bo_con_tro(int(l["id"]), int(l["customer_id"])):
            doi += 1
    return {"quet": gioi_han, "doi_con_tro": doi, "nha_cot": nha}


# ------------------------------------------------------------------ bước kế
def cho_nhan_vien(l: dict) -> bool:
    """Khách ĐANG CHỜ nhân viên trả lời? (tin cuối là của khách).

    Dùng mốc tin của NGƯỜI THẬT chứ không phải tin shop bất kỳ: bot trả lời tự
    động không tính là đã tư vấn."""
    khach = l.get("khach_cuoi")
    if not khach:
        return False
    nguoi = l.get("nguoi_cuoi") or l.get("shop_cuoi")
    return not (nguoi and nguoi > khach)


def dang_nong(l: dict) -> bool:
    """Trong 24 giờ đầu kể từ lúc lead vào — giai đoạn nóng, bỏ cửa giờ."""
    cfg = cau_hinh()
    if cfg["nong_gio"] <= 0 or not l.get("created_at"):
        return False
    goc = l["created_at"]
    return (bay_gio() - goc).total_seconds() <= cfg["nong_gio"] * 3600


def trong_cua_gio(luc=None) -> bool:
    cfg = cau_hinh()
    if cfg["cua_tu"] == cfg["cua_den"]:
        return True                       # hai đầu bằng nhau = mở cả ngày
    h = (luc or bay_gio()).hour
    if cfg["cua_tu"] < cfg["cua_den"]:
        return cfg["cua_tu"] <= h < cfg["cua_den"]
    return h >= cfg["cua_tu"] or h < cfg["cua_den"]   # cửa vắt qua nửa đêm


def _moc_nghi(l: dict):
    """Mốc đo giờ nghỉ = tin shop cuối HOẶC lần nhích bước cuối, cái nào MUỘN
    hơn. Chính nhờ mốc này mà luật "đáp khách xong, im mấy giờ thì bước kế hiện
    ngay" tự đúng — khỏi cần luật riêng."""
    a, b = l.get("sale_step_at"), l.get("shop_cuoi")
    return max(x for x in (a, b) if x) if (a or b) else None


def dem_hom_nay(l: dict) -> int:
    return (int(l.get("sale_step_count") or 0)
            if l.get("sale_step_day") == hom_nay() else 0)


def buoc_ke(l: dict) -> dict | None:
    """Bước kế tiếp + VÌ SAO chưa đẩy được.

    None khi: thang tắt · khách đang chờ đáp · đã hết thang.
    `cho` = '' (sẵn sàng) | 'nghi' | 'cua' | 'tran'.
    """
    ds = thang()
    if not ds:
        return None
    if cho_nhan_vien(l):
        return None                  # việc lúc này là ĐÁP KHÁCH (LUẬT 4)
    cur = max(0, int(l.get("sale_step") or 0))
    ke = next((ds[b] for b in sorted(ds) if b > cur), None)
    if not ke:
        return None                  # hết thang → thôi bám đuổi
    cfg = cau_hinh()
    nong = dang_nong(l)
    cho = ""
    moc = _moc_nghi(l)
    gio_nghi = ((bay_gio() - moc).total_seconds() / 3600) if moc else None
    if cur > 0 and gio_nghi is not None and gio_nghi < cfg["nghi"]:
        cho = "nghi"
    elif not nong and not trong_cua_gio():
        cho = "cua"                  # giai đoạn nóng BỎ cửa giờ
    elif dem_hom_nay(l) >= (cfg["nong_buoc"] if nong else cfg["tran"]):
        cho = "tran"
    return {**dict(ke), "san_sang": cho == "", "cho": cho, "nong": nong}


def ly_do_cho(cho: str) -> str:
    cfg = cau_hinh()
    return {
        "nghi": f'nghỉ {cfg["nghi"]} giờ giữa 2 bước',
        "cua": f'ngoài cửa {cfg["cua_tu"]}h–{cfg["cua_den"]}h',
        "tran": "đủ bước hôm nay",
    }.get(cho, "")


def goi_y_cau(ke: dict | None, toi_da: int = 4) -> list[str]:
    """💬 Gợi ý câu chữ cho bước kế — hiện thẳng trên thẻ khách.

    Hai cái lợi, cái thứ hai mới là cái chính:
      1. Nhân viên khỏi phải nhớ bước này cần nói gì.
      2. Họ gõ theo gợi ý ⇒ bộ dò đọc ĐÚNG bước, thay vì rơi về dự phòng
         "1 lượt = 1 bước". Tức là bảng tự dạy người dùng nuôi chính nó.
    """
    if not ke:
        return []
    dac_biet = {"#anh": "kèm ảnh", "#gia": "kèm bảng giá", "#ma": "kèm mã giảm"}
    ra, da_co = [], set()
    for k in (ke.get("keywords_agent") or "").split(","):
        k = k.strip()
        if not k:
            continue
        chu = dac_biet.get(k, k)
        # Cặp có-dấu/không-dấu: chỉ giữ bản CÓ DẤU (máy bỏ dấu rồi, hiện 2 lần thừa)
        khoa = tv.chuan_hoa(chu)
        if khoa in da_co:
            continue
        da_co.add(khoa)
        ra.append(chu)
    return ra[:toi_da]


# ------------------------------------------------------------------ bảng việc
# Cột CỐ ĐỊNH hai đầu thang; giữa là các cột "Bước N" sinh từ crm.sale_steps.
COT_DAU = [("moi", "Mới chưa tư vấn", "#3B62D9", "Tư vấn khách mới — chưa ai đáp"),
           ("tiem_nang", "Tiềm năng", "#E0A417", "Khách đang quan tâm — chốt đơn")]
COT_CUOI = [
    ("hen_mua", "Hẹn mua", "#8E5E9C", "Tới ngày hẹn — nhắc chốt"),
    ("qua_han", "Quá hạn", "#B0413E", "Việc quá hạn — xử ngay"),
    ("tu_choi", "Từ chối", "#78909C", "Từ chối đợt này — chờ đợt sau"),
    ("da_chot", "Đã chốt đơn", "#2E7D32", "Đã chốt đơn"),
    ("ngung", "Ngừng chăm sóc", "#5A5A5A", "Đã ngừng chăm sóc"),
]
# Cột KHÔNG cho kéo tay: máy suy ra hoàn toàn, kéo vào là nói dối dữ liệu.
COT_KHONG_KEO = {"qua_han", "da_chot"}
_MAU_BUOC = ["#2EAD6E", "#4FA85A", "#7FA33F", "#A89A2A",
             "#C08A1E", "#C97416", "#CF5E12", "#C25E00"]


def cac_cot() -> list[dict]:
    """Danh sách cột bảng việc Sale, sinh động theo thang đang cấu hình."""
    ra = [{"ma": m, "ten": t, "mau": c, "viec": v, "keo": True}
          for m, t, c, v in COT_DAU]
    for i, b in enumerate(sorted(thang())):
        s = thang()[b]
        ra.append({
            "ma": f"buoc_{b}", "ten": f'Bước {b} · {s["name"]}',
            "mau": _MAU_BUOC[i % len(_MAU_BUOC)],
            "viec": s["work"] or s["name"], "keo": True, "buoc": b,
        })
    ra += [{"ma": m, "ten": t, "mau": c, "viec": v,
            "keo": m not in COT_KHONG_KEO} for m, t, c, v in COT_CUOI]
    return ra


def qua_han(l: dict) -> str:
    """Lead này có QUÁ HẠN không? Trả câu giải thích, hoặc '' nếu không.

    Hai ca, cố ý tách:
      * Ca 1 — khách MỚI vào mà hết giai đoạn nóng vẫn chưa đủ bước.
      * Ca 2 — thang ĐÃ chạy rồi kẹt quá lâu. Khách chưa nhích bước nào thì
        KHÔNG tính là kẹt: đó là kho lead cũ, không phải bị bỏ quên.
    """
    if not bat() or cho_nhan_vien(l):
        return ""
    cfg = cau_hinh()
    cur = int(l.get("sale_step") or 0)
    if cur >= max(thang()):
        return ""                    # đã đi hết thang
    bd = ngay_bat_thang()

    tao = l.get("created_at")
    if cfg["nong_gio"] > 0 and tao and tao.date() >= bd:
        gio = (bay_gio() - tao).total_seconds() / 3600
        if gio > cfg["nong_gio"] and cur < cfg["nong_buoc"]:
            return (f'Quá {cfg["nong_gio"]}h chưa đủ {cfg["nong_buoc"]} bước — '
                    f"đang ở bước {cur}")
    if cur > 0:
        moc = _moc_nghi(l)
        if moc and moc.date() >= bd:
            ngay_ket = (bay_gio() - moc).days
            if ngay_ket > cfg["ket_ngay"]:
                return f"Kẹt bước {cur + 1} đã {ngay_ket} ngày — xử ngay"
    return ""


def cot_cua(l: dict) -> tuple[str, str]:
    """Lead này nằm cột nào? Trả (mã cột, câu giải thích).

    Thứ tự xét CÓ Ý NGHĨA — đừng đảo:
      1. Cột người ĐẶT TAY thắng tất cả (nhưng đã tự nhả nếu khách nhắn lại).
      2. Đã chốt / ngừng — trạng thái cuối.
      3. HẸN MUA — có hẹn là đã có kế hoạch, không phải khách bị bỏ quên.
      4. QUÁ HẠN — việc gấp, nổi lên trước mọi cột bước.
      5. Cột bước theo con trỏ.
    """
    if l.get("board_column"):
        return l["board_column"], "người đặt tay"
    if l.get("do_not_contact"):
        return "ngung", "khách yêu cầu ngừng liên hệ"
    if (l.get("stage_code") or "") == "da_chot":
        return "da_chot", "đã chốt đơn"
    # 🚩 Hẹn mua phải xét TRƯỚC quá hạn. Trước đây nằm sau, nên dòng chú thích
    #    "hẹn trượt vẫn ở lại cột Hẹn mua" KHÔNG BAO GIỜ có hiệu lực: lead nào
    #    kẹt thang đủ lâu để người ta đặt hẹn thì cũng đã kẹt đủ lâu để `qua_han`
    #    bắt trước. Nhân viên đặt hẹn xong thấy thẻ nhảy sang "Quá hạn — xử
    #    ngay" là mất niềm tin vào bảng.
    #    Hẹn TRƯỢT ngày cũng ở lại đây (thẻ mang chữ "hẹn đã trượt") — hẹn trượt
    #    vẫn là hẹn, xử khác hẳn việc bị bỏ quên.
    if (hen := l.get("next_action_at")):
        from app.core.ngay import bay_gio

        return "hen_mua", ("hẹn đã trượt ngày" if hen < bay_gio()
                           else "có hẹn mua")
    if (ly_do := qua_han(l)):
        return "qua_han", ly_do
    cur = int(l.get("sale_step") or 0)
    if cur <= 0:
        # "Tiềm năng" = khách ĐÃ TỪNG trả lời sau tin shop (dấu replied_at).
        # Chưa ai nhắn gì thì là khách MỚI.
        return ("tiem_nang", "khách đã trả lời") if l.get("replied_at") \
            else ("moi", "chưa ai tư vấn")
    ds = thang()
    ke = next((b for b in sorted(ds) if b > cur), None)
    if ke is None:
        return "tu_choi", "đã đi hết thang bám đuổi"
    return f"buoc_{ke}", f"đã làm tới bước {cur}"


# Quét bao nhiêu lead để ĐẾM, và bày ra bao nhiêu thẻ.
#  Đếm phải phủ rộng hơn danh sách: số trên tab/ô lọc mà chỉ đếm trong 500 dòng
#  đang bày thì bấm vào cột nào cũng thấy số không khớp. Chạm trần quét thì màn
#  gắn dấu "≥" chứ không nói chắc (xem `cham_tran`).
QUET_TOI_DA = 3000
HIEN_TOI_DA = 500


def bang_viec(*, owner_id: int | None = None, q: str = "",
              an_da_cham: bool = True, staff_id: int | None = None,
              chua_gan: bool = False, page_id: int | None = None,
              tao_tu: str = "", tao_den: str = "",
              hoat_dong_ngay: int | None = None, trang_thai: str = "") -> dict:
    """Số liệu màn Bảng việc Sale: thẻ đã xếp cột + các ô đếm.

    `an_da_cham` — khách ĐÃ CHĂM HÔM NAY thì ẩn đi, TRỪ KHI khách nhắn lại SAU
    lần chăm (cần xử tiếp). Không có luật này thì bảng đầy thẻ đã làm xong.

    Bộ lọc (bước 2): `staff_id`/`chua_gan`/`page_id`/`tao_tu`/`tao_den`/
    `hoat_dong_ngay` lọc ở SQL (xem `repo.bang_viec`); riêng `trang_thai` lọc ở
    ĐÂY vì cột là thứ Python suy ra từ tin nhắn, SQL không biết.

    Thứ tự CÓ Ý NGHĨA: xếp cột cho toàn bộ phạm vi quét → đếm → rồi mới lọc theo
    cột và cắt danh sách. Đếm sau khi lọc thì mọi cột không được chọn đều về 0.
    """
    rows = repo.bang_viec(
        owner_id=owner_id, q=q,
        chi_inbox=bool(runtime_config.bat("board_chi_inbox")),
        limit=QUET_TOI_DA, staff_id=staff_id, chua_gan=chua_gan,
        page_id=page_id, tao_tu=tao_tu, tao_den=tao_den,
        hoat_dong_ngay=hoat_dong_ngay)
    cot_ds = cac_cot()
    theo_cot: dict[str, list] = {c["ma"]: [] for c in cot_ds}
    the: list[dict] = []
    # Đếm RIÊNG, không suy từ `the`: thẻ đã chăm bị `continue` bỏ khỏi `the` nên
    # đếm sau vòng lặp là ra 0. Màn cần cả hai số — "hôm nay đã xong N" (khích
    # lệ) và "đã ẩn N thẻ" (giải thích vì sao bảng ngắn hơn mình tưởng).
    xong_hom_nay = da_an = 0
    for r in rows:
        l = dict(r)
        if int(l.get("cham_hom_nay") or 0) > 0:
            xong_hom_nay += 1
        if an_da_cham and int(l.get("cham_hom_nay") or 0) > 0 \
                and not cho_nhan_vien(l):
            da_an += 1
            continue
        ma, vi_sao = cot_cua(l)
        ke = buoc_ke(l)
        l.update({
            "cot": ma, "cot_vi_sao": vi_sao, "buoc_ke": ke,
            "goi_y": goi_y_cau(ke),
            "cho_dap": cho_nhan_vien(l),
            "ly_do_cho": ly_do_cho(ke["cho"]) if ke else "",
            "qua_han": qua_han(l),
            # Cờ RIÊNG chứ không để giao diện đi so `cot_vi_sao`: đó là câu chữ
            # hiển thị, ai sửa một dấu là viền đỏ tắt im lặng, không test nào đỏ.
            "hen_tre": ma == "hen_mua" and bool(l.get("next_action_at"))
                       and l["next_action_at"] < bay_gio(),
        })
        the.append(l)
        theo_cot.setdefault(ma, []).append(l)

    # --- đếm TRƯỚC khi lọc theo cột ---
    dem = {
        "hom_nay": sum(1 for x in the
                       if x["buoc_ke"] and x["buoc_ke"]["san_sang"]),
        "qua_han": len(theo_cot.get("qua_han", [])),
        "vua_phan_hoi": sum(1 for x in the if x["cho_dap"]),
        "yeu_cau_chia": sum(1 for x in the if not x.get("owner_id")),
    }
    dem_cot = {c["ma"]: len(theo_cot.get(c["ma"], [])) for c in cot_ds}

    # --- lọc theo cột, rồi mới cắt danh sách bày ra ---
    if trang_thai and trang_thai in theo_cot:
        the = list(theo_cot[trang_thai])
        theo_cot = {k: (v if k == trang_thai else []) for k, v in theo_cot.items()}
    tong = len(the)
    if tong > HIEN_TOI_DA:
        the = the[:HIEN_TOI_DA]
        giu = {x["id"] for x in the}
        theo_cot = {k: [x for x in v if x["id"] in giu]
                    for k, v in theo_cot.items()}
    return {
        "cot": cot_ds,
        "theo_cot": theo_cot,
        "the": the,
        "tong": tong,
        "cham_tran": len(rows) >= QUET_TOI_DA,
        "xong_hom_nay": xong_hom_nay,
        "da_an": da_an,
        "dem": dem,
        "dem_cot": dem_cot,
    }


# ------------------------------------------------------------------ thao tác
def keo_the(lead_id: int, cot: str, *, nguoi: int | None = None) -> dict:
    """Kéo thẻ sang cột khác.

    Cột "Bước N" thì đặt luôn CON TRỎ = N-1 (đã làm tới N-1, việc kế đúng là N)
    — đây là đường DUY NHẤT cho phép con trỏ lùi, và có ghi dấu người đặt.
    """
    hop_le = {c["ma"]: c for c in cac_cot()}
    if cot not in hop_le:
        raise ApiError("VALIDATION_ERROR", f"Cột lạ: {cot}")
    if not hop_le[cot]["keo"]:
        raise ApiError(
            "CONFLICT",
            f'Cột "{hop_le[cot]["ten"]}" do máy suy ra, không kéo tay được — '
            "kéo vào đây là nói dối dữ liệu.")
    if (b := hop_le[cot].get("buoc")):
        repo.dat_con_tro_tay(lead_id, b - 1)
    kq = repo.dat_cot(lead_id, cot, nguoi)
    if not kq:
        raise ApiError("NOT_FOUND", "Không tìm thấy lead.")

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="keo_the_bang_viec", object_type="lead",
                   object_id=lead_id, user_id=nguoi,
                   new_value={"cot": cot})
    return dict(kq)


def tu_choi(lead_id: int, *, nguoi: int | None = None) -> dict:
    """🚫 TỪ CHỐI = đóng ĐỢT NÀY, đợt sau vẫn chăm. KHÔNG hỏi xác nhận.

    Cố ý không hỏi: nhân viên bấm nút này mấy chục lần một ngày, hỏi lại mỗi
    lần là họ bỏ luôn không bấm. Và nó có thể lùi được — khách nhắn lại là thẻ
    tự nhả khỏi cột (xem repo.nha_cot_da_cu)."""
    return keo_the(lead_id, "tu_choi", nguoi=nguoi)


def ngung_cham_soc(lead_id: int, ly_do: str, *,
                   nguoi: int | None = None) -> dict:
    """⛔ NGỪNG CHĂM SÓC = dừng HẲN tới khi khách nhắn lại trước. CÓ hỏi xác
    nhận (ở giao diện) và BẮT BUỘC ghi lý do.

    Khác hẳn Từ chối: thẻ KHÔNG tự nhả, nhân viên không tự kéo ra được. Đây là
    lý do `nha_cot_da_cu()` loại riêng cột 'ngung'."""
    ly_do = (ly_do or "").strip()
    if not ly_do:
        raise ApiError("VALIDATION_ERROR",
                       "Ngừng chăm sóc BẮT BUỘC ghi lý do.")
    kq = repo.dat_cot(lead_id, "ngung", nguoi)
    if not kq:
        raise ApiError("NOT_FOUND", "Không tìm thấy lead.")

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="ngung_cham_soc", object_type="lead",
                   object_id=lead_id, user_id=nguoi, reason=ly_do)
    return dict(kq)


def mo_lai(lead_id: int, *, nguoi: int | None = None) -> dict:
    """Nhả cột đặt tay, trả thẻ về cho máy xếp."""
    kq = repo.dat_cot(lead_id, None, nguoi)
    if not kq:
        raise ApiError("NOT_FOUND", "Không tìm thấy lead.")
    return dict(kq)


def dat_hen(lead_id: int, khi: str, *, nguoi: int | None = None) -> dict:
    """📌 Đặt hẹn mua. `khi` = 'YYYY-MM-DD' hoặc 'YYYY-MM-DDTHH:MM'; rỗng = xoá hẹn.

    KHÔNG chặn hẹn trong quá khứ: nhân viên hay ghi lại cái hẹn khách vừa nói
    hôm qua mà mình quên nhập. Hẹn quá ngày tự thành thẻ viền đỏ ở cột Hẹn mua,
    thấy ngay — chặn ở đây chỉ tổ làm họ bịa một ngày khác cho lọt.
    """
    khi = (khi or "").strip()
    luc = None
    if khi:
        from datetime import datetime

        try:
            luc = datetime.fromisoformat(khi).astimezone()
        except ValueError:
            raise ApiError("VALIDATION_ERROR",
                           f"Ngày hẹn không đọc được: {khi!r}") from None
    kq = repo.dat_hen(lead_id, luc)
    if not kq:
        raise ApiError("NOT_FOUND", "Không tìm thấy lead đang mở.")

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="dat_hen_mua" if luc else "xoa_hen_mua",
                   object_type="lead", object_id=lead_id, user_id=nguoi,
                   reason=khi)
    return dict(kq)


def tu_khai(lead_id: int, viec: str, *, nguoi: int | None = None) -> str:
    """✅ Tự khai đã nhắn / ☎️ đã gọi — đi qua CỔNG GHI CÔNG DUY NHẤT.

    Không tự ghi thẳng vào `care_interactions`: cổng đó còn lo chống trùng trong
    ngày, xếp trạng thái xác minh và ghi nguồn "người tự khai". Vòng qua nó là
    công tự khai lọt vào như công đã xác minh.
    """
    if viec not in ("nhan", "goi"):
        raise ApiError("VALIDATION_ERROR", f"Việc lạ: {viec!r}")
    if not nguoi:
        raise ApiError("VALIDATION_ERROR", "Chưa xác định người khai.")
    l = repo.get_lead_bang(lead_id)
    if not l:
        raise ApiError("NOT_FOUND", "Không tìm thấy lead.")

    from app.services import giam_sat_service

    return giam_sat_service.ghi_cong(int(l["customer_id"]), nguoi, viec)


# ------------------------------------------------- thanh hàng loạt (bước 6)
# Mẫu CẤM hai việc này làm hàng loạt (tài liệu C1) — và lệnh cấm có lý:
#   · tặng voucher  = phát tiền, bấm nhầm một cái mất cả lô
#   · ✅ tự khai    = khai công cho 200 khách trong một nhịp thì con số công
#                     hết nghĩa, mà bộ soi tin không cách nào bác lại kịp
# Nên ở đây KHÔNG có hai hành động đó, và đừng thêm vào.
HANG_LOAT = {"giao", "xuat"}


def giao_hang_loat(lead_ids: list[int], nv_ids: list[int], *,
                   nguoi: int | None = None) -> dict:
    """Giao/chia lô lead cho một hoặc nhiều nhân viên.

    Một người  -> giao hết cho người đó.
    Nhiều người -> CHIA ĐỀU kiểu chia bài (lead thứ i về người thứ i % N), y như
    mẫu. Chia đều theo thứ tự đang bày nên hai người không bị lệch quá 1 lead.
    """
    lead_ids = [int(x) for x in lead_ids if int(x) > 0]
    nv_ids = list(dict.fromkeys(int(x) for x in nv_ids if int(x) > 0))
    if not lead_ids:
        raise ApiError("VALIDATION_ERROR", "Chưa chọn thẻ nào.")
    if not nv_ids:
        raise ApiError("VALIDATION_ERROR", "Chưa chọn nhân viên nhận.")

    tui: dict[int, list[int]] = {u: [] for u in nv_ids}
    for i, lid in enumerate(lead_ids):
        tui[nv_ids[i % len(nv_ids)]].append(lid)
    doi = sum(repo.giao_lead(ds, u) for u, ds in tui.items() if ds)

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="giao_lead_hang_loat", object_type="lead",
                   object_id=None, user_id=nguoi,
                   reason=f"{doi} lead cho {len(nv_ids)} nhân viên")
    return {"doi": doi, "so_nv": len(nv_ids)}


# Cột xuất ra file. Thứ tự này là thứ tự cột trong CSV.
COT_XUAT = [
    ("id", "Mã lead"), ("full_name", "Tên khách"),
    ("primary_phone", "Điện thoại"), ("card_rank", "Hạng thẻ"),
    ("total_spent", "Tổng chi tiêu"), ("source", "Nguồn"),
    ("owner_name", "Phụ trách"), ("sale_step", "Bước đã gửi"),
    ("next_action_at", "Hẹn mua"), ("created_at", "Ngày nhắn lần đầu"),
]


def xuat_csv(lead_ids: list[int], *, co_sdt: bool = True) -> str:
    """Dựng nội dung CSV cho lô lead đã chọn.

    `co_sdt=False` -> cột Điện thoại ra "***". File này rời khỏi hệ thống là
    không thu về được, nên người không được xem SĐT trên màn thì cũng không
    được xuất SĐT ra file.
    """
    import csv
    import io

    rows = repo.lead_de_xuat([int(x) for x in lead_ids if int(x) > 0])
    if not rows:
        raise ApiError("VALIDATION_ERROR", "Chưa chọn thẻ nào để xuất.")
    dem = io.StringIO()
    w = csv.writer(dem)
    w.writerow([nhan for _, nhan in COT_XUAT])
    for r in rows:
        hang = []
        for khoa, _ in COT_XUAT:
            v = r.get(khoa)
            if khoa == "primary_phone" and not co_sdt:
                v = "***"
            elif hasattr(v, "strftime"):
                v = v.astimezone().strftime("%d/%m/%Y %H:%M")
            hang.append("" if v is None else v)
        w.writerow(hang)
    return dem.getvalue()


def dat_lai_thang(lead_id: int, *, nguoi: int | None = None) -> None:
    """Chạy lại thang từ bước 0 cho một lead (nút ở hồ sơ khách)."""
    repo.dat_lai_con_tro(lead_id)

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="dat_lai_thang_sale", object_type="lead",
                   object_id=lead_id, user_id=nguoi)


def luu_buoc(step_no: int, *, name: str, work: str = "",
             kw_nv: str = "", kw_kh: str = "", bat: bool | None = None) -> dict:
    """Sửa một bước của thang. Từ khoá phải là CỤM NHIỀU CHỮ — xem cái bẫy
    ngôn ngữ ở đầu file."""
    if step_no < 1:
        raise ApiError("VALIDATION_ERROR", "Số bước phải từ 1 trở lên.")
    if (xau := tu_khoa_qua_ngan(kw_nv)):
        raise ApiError(
            "VALIDATION_ERROR",
            f"Từ khoá quá ngắn, dễ khớp nhầm sau khi bỏ dấu: {', '.join(xau)}. "
            'Dùng CỤM nhiều chữ (vd "đắt quá" thay vì "đắt" — "đắt" bỏ dấu '
            'thành "dat", đụng luôn "đặt hàng").')
    return repo.luu_buoc(step_no, name=name.strip(), work=work.strip(),
                         kw_nv=gop(tach(kw_nv)), kw_kh=gop(tach(kw_kh)),
                         status=None if bat is None
                         else ("active" if bat else "inactive"))


# ---------------------------------------------------- 1A · làm việc với từ khoá
# Từ khoá lưu dạng MỘT CHUỖI "a, b, c" (khớp mẫu, và tiện cho bộ dò đọc thẳng).
# Giao diện lại cần từng cụm rời để vẽ thẻ bấm gỡ. Tách/gộp gom về hai hàm này
# để hai phía không bao giờ hiểu chuỗi khác nhau.
def tach(chuoi: str) -> list[str]:
    return [x.strip() for x in (chuoi or "").split(",") if x.strip()]


def gop(cum: list[str]) -> str:
    return ", ".join(cum)


def tu_khoa_qua_ngan(chuoi: str) -> list[str]:
    """Cụm ngắn tới mức nguy hiểm sau khi bỏ dấu (xem cái bẫy ngôn ngữ).

    Bỏ qua ba từ đặc biệt `#anh/#gia/#ma` — chúng không so chuỗi."""
    return [k for k in tach(chuoi)
            if not k.startswith("#") and " " not in k
            and len(tv.chuan_hoa(k)) <= 4]


def the_trung(chuoi: str) -> dict[int, str]:
    """Vị trí các cụm THỪA — chỉ khác nhau ở DẤU nên máy coi là một.

    Trả {chỉ số cụm thừa: cụm đầu tiên trùng với nó}. Mẫu để cả cặp
    "số đo"/"so do" trong seed; máy đã bỏ dấu cả hai phía nên cụm thứ hai không
    bắt thêm được gì, chỉ làm danh sách dài ra và người đọc tưởng đang phủ rộng
    hơn thực tế."""
    dau: dict[str, str] = {}
    ra: dict[int, str] = {}
    for i, k in enumerate(tach(chuoi)):
        khoa = tv.chuan_hoa(k)
        if khoa in dau:
            ra[i] = dau[khoa]
        else:
            dau[khoa] = k
    return ra


def go_the_trung(chuoi: str) -> str:
    """Bỏ mọi cụm thừa, GIỮ cụm xuất hiện trước (thường là bản CÓ DẤU)."""
    thua = set(the_trung(chuoi))
    return gop([k for i, k in enumerate(tach(chuoi)) if i not in thua])


# Ba cụm máy tự hiểu — hiện thành chữ người đọc được trên giao diện.
CUM_DAC_BIET = {"#anh": "tin có ảnh", "#gia": "tin có số tiền",
                "#ma": "tin có mã giảm"}


def cum_the(chuoi: str) -> list[dict]:
    """Danh sách cụm đã gắn nhãn, để giao diện vẽ thẻ mà không tự đoán gì."""
    thua = the_trung(chuoi)
    ra = []
    for i, k in enumerate(tach(chuoi)):
        dac = CUM_DAC_BIET.get(k.lower())
        ra.append({"i": i, "cum": k, "dac_biet": dac,
                   "trung_voi": thua.get(i)})
    return ra


def thu_mot_cau(cau: str, *, ai: str = "nv", co_anh: bool = False,
                kw_nv: dict[int, str] | None = None,
                kw_kh: dict[int, str] | None = None) -> dict:
    """🧪 Thử một câu — dán câu nhân viên (hoặc khách) hay gõ, xem máy hiểu là
    bước mấy.

    Chấm trên TỪ KHOÁ ĐANG GÕ TRÊN MÀN (`kw_nv`/`kw_kh` truyền vào), chưa lưu
    cũng thử được. Và gọi THẲNG `_khop_buoc()` — đúng hàm bộ dò thật dùng — nên
    kết quả ô thử KHÔNG BAO GIỜ lệch với lúc chạy thật.
    """
    ds = thang()
    cfg = cau_hinh()
    nguon = (kw_kh if ai == "kh" else kw_nv) or {}
    khop = []
    for b in sorted(ds):
        kw = nguon.get(b)
        if kw is None:                       # màn không gửi thì lấy bản đã lưu
            kw = (ds[b].get("keywords_customer") if ai == "kh"
                  else ds[b].get("keywords_agent")) or ""
        trung = [k["cum"] for k in cum_the(kw)
                 if _khop_buoc(cau, co_anh, k["cum"])]
        if trung:
            khop.append({"buoc": b, "ten": ds[b].get("name") or "",
                         "cum": trung})
    return {"ai": ai, "khop": khop,
            "cua_so": cfg["cua_so"], "nhay": cfg["nhay"]}
