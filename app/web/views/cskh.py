"""Màn BẢNG VIỆC CSKH (C6 — port mẫu Kallet `index.php?bp=cskh`).

Trong mẫu, CSKH KHÔNG phải một nhóm màn: `cham-soc.php` chỉ là 10 dòng chuyển
hướng sang `index.php?bp=cskh`. Toàn bộ nghiệp vụ gói trong MỘT bảng việc, bố
cục bốn tầng — và bản này dựng lại đúng bốn tầng đó:

    1. thanh công cụ  — đổi bộ phận · đã xong hôm nay · tìm · Bảng|Pipeline
    2. dải bộ lọc     — dải ngày nhận · nhân viên · fanpage · cột · hạng thẻ
    3. dải trạng thái — khách ngủ · đã ẩn N khách đã chăm · đang bày N/M thẻ
    4. tab đếm        — Việc hôm nay · Quá hạn · Chờ khách trả lời

Dùng chung bộ CSS `bv-*` với [sale.py] (bảng việc Sale) — hai bảng phải nhìn
như một hệ, vì cùng một người mở cả hai mỗi ngày.

Bốn luật giao diện của mẫu, giữ nguyên:

  * **Câu việc 📌 không bao giờ chung chung.** Cột gấp phải nói rõ khách đang ở
    nhịp nào / vì lý do gì — "voucher còn 7 ngày" khác hẳn "HẾT HẠN HÔM NAY".
  * **Màu không đứng một mình**, luôn kèm chữ. Riêng thanh tiến trình mốc là
    cái bẫy: nó đầy dần về phía XẤU (khách sắp rời bỏ) trong khi mắt đọc "đầy =
    tốt" ⇒ bắt buộc xanh→vàng→đỏ **và** luôn kèm chữ mốc.
  * **Cột máy suy ra hoàn toàn thì KHÔNG cho kéo tay** — kéo vào đó là nói dối
    dữ liệu; ô chọn cột tự ẩn những cột này.
  * **Số trên tab và ô lọc đếm cả phạm vi lọc**, không phải trang đang xem —
    nên phải nói rõ khi danh sách bị cắt, kẻo hai con số đá nhau.

Và hai nút đóng khách CỐ Ý khác nhau (mẫu chốt, đừng gộp):
  🚫 **Từ chối** — đóng đợt này, KHÔNG hỏi xác nhận, khách nhắn lại là thẻ tự
     quay về bảng.
  ⛔ **Ngừng liên hệ** — dừng hẳn, CÓ hỏi + bắt buộc lý do, thẻ không tự quay lại.
"""

from html import escape
from urllib.parse import quote

from app.services import cskh_service as svc
from app.web.shell import _icon, render_shell

DUONG = "/crm/bang-viec-cskh"


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _d(v) -> str:
    return v.strftime("%d/%m/%Y") if v else "—"


def _so(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".")


def _tien(n) -> str:
    try:
        return f"{float(n or 0):,.0f}đ".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _truoc(dt) -> str:
    """'3 giờ trước' — nhân viên đọc khoảng cách nhanh hơn đọc mốc tuyệt đối."""
    if not dt:
        return "—"
    from app.core.ngay import bay_gio

    giay = (bay_gio() - dt).total_seconds()
    if giay < 3600:
        return f"{int(giay // 60)} phút trước"
    if giay < 86400:
        return f"{int(giay // 3600)} giờ trước"
    return f"{int(giay // 86400)} ngày trước"


def _url(hien_tai: dict, **doi) -> str:
    """Đường dẫn màn này với bộ lọc hiện tại, ghi đè vài tham số."""
    tham = dict(hien_tai)
    tham.update(doi)
    cai = [(k, v) for k, v in tham.items() if v not in ("", None, 0)]
    duoi = "&".join(f"{k}={quote(str(v))}" for k, v in cai)
    return DUONG + (f"?{duoi}" if duoi else "")


def _giu_an(loc: dict, bo: tuple = ()) -> str:
    """Bộ lọc hiện tại dưới dạng input ẩn — để form này không XOÁ bộ lọc của
    form kia. Hai form GET rời nhau trên cùng một màn thì mỗi form chỉ gửi đúng
    ô của nó; thiếu chỗ này là bấm tìm xong mất sạch bộ lọc."""
    return "".join(
        f'<input type="hidden" name="{escape(k)}" value="{escape(str(v))}">'
        for k, v in loc.items() if k not in bo and v not in ("", None, 0))


def _xo(ten: str, dang_chon: str, muc: list[tuple[str, str]],
        nhan_de: str = "") -> str:
    """Một ô xổ trong dải lọc — tự gửi form khi đổi."""
    o = "".join(
        f'<option value="{escape(str(g))}"'
        f'{" selected" if str(g) == str(dang_chon) else ""}>{escape(n)}</option>'
        for g, n in muc)
    tip = f' title="{escape(nhan_de)}"' if nhan_de else ""
    return (f'<select class="bv-sel" name="{escape(ten)}"{tip} '
            f'onchange="this.form.requestSubmit()">{o}</select>')


# ------------------------------------------------------------------ tầng 1
def _thanh_cong_cu(loc: dict, che_do: str, xong: int) -> str:
    """Tầng 1 của mẫu — đổi bộ phận · đã xong hôm nay · ô tìm · chọn chế độ.

    Mẫu gộp cả tiêu đề vào đây; bên này tiêu đề đã nằm ở topbar của
    `render_shell` nên bỏ, giữ nguyên phần còn lại và thứ tự trái→phải.
    """
    bp = ('<div class="bv-seg2">'
          '<a href="/crm/bang-viec">🎯 Sale</a>'
          f'<a class="on" href="{DUONG}">💗 CSKH</a></div>')
    # Đổi chế độ thì BỎ focus: focus là cách xem của Pipeline, mang nó sang chế
    # độ Bảng thì bấm "Bảng" xong màn vẫn y nguyên, nhìn như nút hỏng.
    mode = "".join(
        f'<a class="{"on" if che_do == ma else ""}" '
        f'href="{escape(_url(loc, cd=ma, col="", kh=0))}">{escape(nhan)}</a>'
        for ma, nhan in [("bang", "Bảng"), ("pipeline", "Pipeline")])
    return (
        '<div class="bv-bar1">' + bp
        + '<span class="bv-gap"></span>'
        + f'<span class="bv-done">{_icon("check")}Hôm nay đã xong: '
          f"<b>{_so(xong)}</b></span>"
        # Ô tìm là form RIÊNG (mẫu cũng vậy): gõ xong Enter là đi luôn, không
        # phải chờ dải lọc bên dưới.
        + f'<form class="bv-find" method="get" action="{DUONG}">'
          f'<input type="hidden" name="cd" value="{escape(che_do)}">'
        + _giu_an(loc, bo=("q", "cd"))
        + _icon("search")
        + f'<input name="q" value="{escape(loc.get("q") or "")}" '
          'placeholder="Tìm khách, SĐT…"></form>'
        + f'<div class="bv-seg2 bv-mode">{mode}</div>'
        "</div>"
    )


def _dai_ctkm(ctkm: dict | None) -> str:
    """Dải đợt khuyến mãi đang chạy + nút Chép.

    Mẫu để dải này ngay trên bảng việc vì nhân viên KHÔNG vào được màn Cài đặt
    (đòi quyền riêng) — đây là đường duy nhất để họ đọc nội dung ưu đãi. Đọc
    một lần, chép một nút, dùng cả ngày.
    """
    if not ctkm:
        return ""
    ten = escape((ctkm.get("name") or "").strip())
    nd = (ctkm.get("content") or "").strip()
    if not nd:
        return (f'<div class="cs-ctkm"><b>🎁 Đang chạy khuyến mãi: {ten}</b>'
                '<div class="thieu">Chưa nhập nội dung ưu đãi — nhắc quản lý '
                'điền ở <a href="/crm/cskh/khuyen-mai">Đợt khuyến mãi CSKH</a>.'
                "</div></div>")
    return (
        f'<div class="cs-ctkm"><b>🎁 Đang chạy khuyến mãi: {ten}</b>'
        f'<div class="nd" id="ctkmNd">{escape(nd)}</div>'
        '<button type="button" class="kh-btn" onclick="'
        "navigator.clipboard.writeText("
        "document.getElementById('ctkmNd').innerText)"
        ".then(()=>{this.textContent='Đã chép'})"
        '">Chép</button></div>')


# ------------------------------------------------------------------ tầng 2
def _o_dai_ngay(loc: dict) -> str:
    """Ô lọc "ngày nhận hàng" — dải sẵn sinh từ chính ngưỡng cột, kèm lối tự
    nhập. Chọn "Chăm định kỳ" là ra đúng nhóm khách của cột đó, không lệch."""
    dai = loc.get("dai") or ""
    o = _xo("dai", dai,
            [("", "Ngày nhận hàng: tất cả")] + svc.dai_presets()
            + [("tuy", "Tự nhập số ngày…")],
            "Lọc theo khách nhận hàng cách đây bao nhiêu ngày — cùng thang với "
            "cột trên bảng")
    if dai != "tuy":
        return o
    # Hai ô nhập tay CHỈ hiện khi chọn "tự nhập". Mẫu từng để chúng đứng cạnh
    # ô dải sẵn — hai giọng nói cùng một chuyện, nhìn không biết cái nào đang
    # có hiệu lực.
    return o + (
        '<div class="bv-ngay" title="Số NGÀY kể từ ngày nhận hàng cuối">'
        + _icon("calendar")
        + "<span>Nhận cách đây:</span>"
          f'<input type="number" name="ntu" min="0" '
          f'value="{escape(str(loc.get("ntu") or ""))}" placeholder="từ" '
          'style="width:56px" onchange="this.form.requestSubmit()">'
          "<span>–</span>"
          f'<input type="number" name="nden" min="0" '
          f'value="{escape(str(loc.get("nden") or ""))}" placeholder="đến" '
          'style="width:56px" onchange="this.form.requestSubmit()">'
          "<span>ngày</span></div>")


def _dai_loc(loc: dict, che_do: str, quan_ly: bool, so_the: int, *,
             cot: list[dict], dem_cot: dict, ds_nv: list[dict],
             ds_page: list[dict], ds_hang: list[dict],
             cham_tran: bool) -> str:
    """Tầng 2 của mẫu — dải bộ lọc, nối THẬT xuống DB.

    Thứ tự trái→phải giữ đúng mẫu: dải ngày nhận · nhân viên · fanpage · trạng
    thái · hạng thẻ · xoá lọc.

    Ô "nhân viên" chỉ in cho quản lý. Nhân viên thường thấy một ô chữ "Của tôi"
    y như mẫu — nói rõ phạm vi đang bó, chứ không để trống làm người ta tưởng
    đang xem hết.
    """
    co_loc = any(loc.get(k) for k in
                 ("q", "viec", "hien_da_cham", "nv", "page", "tt", "hang",
                  "dai", "ntu", "nden"))
    xoa = (f'<a class="bv-xoa" href="{escape(_url({"cd": che_do}))}">'
           f'{_icon("x")}Xoá lọc</a>' if co_loc else "")
    # Ô trạng thái kèm số THẬT trong phạm vi lọc hiện tại. Chạm trần quét thì
    # gắn "≥" — nói "42" khi mình chỉ đếm được tới 3000 dòng là nói quá chắc.
    dau = "≥" if cham_tran else ""
    o_tt = _xo("tt", loc.get("tt") or "",
               [("", "Tất cả trạng thái")]
               + [(c["ma"], f'{c["ten"]} ({dau}{dem_cot.get(c["ma"], 0)})')
                  for c in cot],
               "Lọc theo cột trên bảng — số trong ngoặc đếm trong phạm vi lọc "
               "hiện tại")
    o_nv = (_xo("nv", loc.get("nv") or "",
                [("", "Mọi nhân viên"), ("none", "— Chưa gán —")]
                + [(str(n["id"]), f'{n["name"]} ({n["so_khach"]})')
                   for n in ds_nv])
            if quan_ly else
            f'<span class="bv-ro">{_icon("user")}Của tôi</span>')
    o_page = _xo("page", str(loc.get("page") or 0),
                 [("0", "Tất cả fanpage")]
                 + [(str(p["id"]), f'{p["name"]} ({p["so_khach"]})')
                    for p in ds_page])
    # "Chưa xếp hạng" là trạng thái thứ 6 có thật (chi tiêu đúng 0đ), mẫu đếm
    # riêng — không phải rác dữ liệu nên phải có mục chọn.
    o_hang = _xo("hang", loc.get("hang") or "",
                 [("", "Hạng thẻ: tất cả")]
                 + [(h["code"], f'{h.get("emoji") or ""} {h["name"]}'.strip())
                    for h in ds_hang]
                 + [("chua_xep_hang", "Chưa xếp hạng")])
    return (
        f'<form class="bv-bar2" method="get" action="{DUONG}">'
        f'<input type="hidden" name="cd" value="{escape(che_do)}">'
        + _giu_an(loc, bo=("cd", "nv", "page", "tt", "hang", "dai", "ntu",
                           "nden", "hien_da_cham"))
        + _o_dai_ngay(loc) + o_nv + o_page + o_tt + o_hang
        + '<label class="bv-ck"><input type="checkbox" name="hien_da_cham" '
          'value="1"'
        + (" checked" if loc.get("hien_da_cham") else "")
        + ' onchange="this.form.requestSubmit()"> Hiện cả khách đã chăm hôm '
          "nay</label>"
        + xoa
        + '<span class="bv-gap"></span>'
          f'<span class="bv-cnt">{_so(so_the)} thẻ</span></form>'
    )


# ------------------------------------------------------------------ tầng 3–4
def _tab_dem(dem: dict, loc: dict) -> str:
    """Tầng 4 của mẫu — ĐÚNG 3 tab, bấm là đặt bộ lọc.

    Tab 2 và 3 chính là bộ lọc CỘT (mẫu cũng trỏ thẳng `?status=<cột>`), nên
    chúng dùng chung tham số `tt` với ô xổ trạng thái — hai đường vào cùng một
    bộ lọc thì phải cùng một tham số, không thì bấm cái này ô kia không sáng.
    """
    ra = ""
    bat_viec = bool(loc.get("viec"))
    ra += (f'<a class="bv-tab{" on" if bat_viec else ""}" '
           f'href="{escape(_url(loc, viec=0 if bat_viec else 1, tt=""))}">'
           f'Việc hôm nay <b>{_so(dem.get("viec_hom_nay"))}</b></a>')
    for ma, nhan, lop in (("qua_han", "Quá hạn", "err"),
                          ("nhac_goi", "Chờ khách trả lời", "")):
        on = (loc.get("tt") or "") == ma
        # Bấm lại tab đang bật = bỏ lọc. Mẫu không có, nhưng thiếu nó thì không
        # có đường nào quay về "xem tất cả" ngoài việc bấm Xoá lọc.
        ra += (f'<a class="bv-tab{" on" if on else ""}" '
               f'href="{escape(_url(loc, tt="" if on else ma, viec=0))}">'
               f'{escape(nhan)} <b class="{lop}">{_so(dem.get(ma))}</b></a>')
    return f'<div class="bv-tabs">{ra}</div>'


def _dai_ngu(n: int) -> str:
    """Khách đã quá ngày buông. Họ không nằm trong bảng nhưng vẫn là khách của
    mình — giấu hẳn thì đội tưởng đã mất."""
    if not n:
        return ""
    return ('<div class="bv-note">' + _icon("clock")
            + f"<span><b>{_so(n)}</b> khách <b>đang ngủ</b> (quá "
              f"{svc.ngay_buong()} ngày không mua) — chỉ chăm khi có chiến "
              "dịch.</span>"
              '<a href="/crm/khach-ngu">Xem</a></div>')


def _dai_da_an(data: dict, loc: dict) -> str:
    """Bảng ngắn hơn mình tưởng mà không nói lý do là người dùng tưởng mất
    khách."""
    if loc.get("hien_da_cham"):
        return ('<div class="bv-note">' + _icon("check-check")
                + "<span>Đang hiện <b>cả</b> khách đã chăm hôm nay.</span>"
                f'<a href="{escape(_url(loc, hien_da_cham=0))}">Ẩn lại</a>'
                "</div>")
    if not data.get("da_an"):
        return ""
    return ('<div class="bv-note">' + _icon("check-check")
            + f'<span>Đã ẩn <b>{_so(data["da_an"])}</b> khách <b>đã chăm hôm '
              "nay</b> — khách nhắn lại sẽ tự hiện lại.</span>"
            f'<a href="{escape(_url(loc, hien_da_cham=1))}">Xem lại</a></div>')


def _dai_cat(data: dict) -> str:
    """Số ở tab đếm cả phạm vi lọc, danh sách dưới chỉ bày tối đa `HIEN_TOI_DA`
    thẻ gấp nhất. Không nói ra thì hai con số đá nhau."""
    tong, hien = data.get("tong") or 0, len(data["the"])
    if tong <= hien:
        return ""
    return ('<div class="bv-note"><span>Đang bày <b>' + _so(hien)
            + "</b> thẻ gấp nhất trong <b>" + _so(tong)
            + "</b> thẻ khớp bộ lọc. Lọc theo cột hoặc nhân viên để xem hết."
              "</span></div>")


def _dai_luat(data: dict) -> str:
    """Một dòng nói thang nào đang điều khiển bảng — người dùng phải biết vì
    sao thẻ xếp như đang thấy.

    Mẫu KHÔNG có bảng báo xanh "mọi thứ đang chạy tốt": trên một màn làm việc
    mở suốt ngày, băng-rôn báo trạng thái bình thường chỉ là nhiễu, đọc vài hôm
    là mắt bỏ qua luôn — kể cả hôm nó đổi thành báo lỗi thật. Nên thông tin ở
    lại, hình thức hạ xuống một dòng ghi chú như bảng Sale.
    """
    if not data["bat"]:
        return ""
    nhip = " · ".join(str(n) for n in svc.nhip_voucher())
    return ('<div class="bv-note"><span>🤖 <b>Quy trình CSKH 3 giai đoạn đang '
            f"BẬT</b> — mốc đầu D{svc.moc_dau()}, cách nhau {svc.moc_cach()} "
            f"ngày, buông ở D{svc.ngay_buong()}; nhắc hạn voucher trước {nhip} "
            "ngày. Cột do máy suy từ <b>ngày nhận hàng cuối</b> + voucher + tin "
            "nhắn.</span>"
            '<a href="/quan-tri/cai-dat?sec=moc#k1d">Sửa thang</a></div>')


def _bang_bao(data: dict) -> str:
    """Cảnh báo cấu hình — CHỈ hiện khi có thứ thật sự cần người xử."""
    if not data["bat"]:
        return (
            '<div class="flash warn">⚙️ <b>Quy trình CSKH 3 giai đoạn đang '
            "TẮT</b> — bảng đang xếp cột theo dải ngày cũ (30 · 60 · 150). Bật "
            'ở <a href="/quan-tri/cai-dat?sec=vong_doi">Cài đặt → Vòng đời '
            "khách</a> sau khi đã dựng thang mốc và điền mệnh giá voucher máy "
            "tặng.</div>")
    mg = svc.menh_gia_voucher()
    if mg <= 0:
        return (
            '<div class="flash warn">✅ Quy trình CSKH đang BẬT (mốc đầu D'
            f"{svc.moc_dau()}, cách nhau {svc.moc_cach()} ngày, buông ở D"
            f"{svc.ngay_buong()}) — nhưng <b>mệnh giá máy tặng đang là 0 ⇒ máy "
            "KHÔNG tự tặng voucher</b>, nhân viên phải tặng tay ở màn Ưu đãi."
            "</div>")
    return ""


# ------------------------------------------------------------------ thẻ khách
def _chip(chu: str, mau: str, nen: str) -> str:
    return (f'<span class="cs-chip" style="color:{mau};background:{nen};'
            f'border-color:{mau}33">{escape(chu)}</span>')


def _thanh_moc(kh: dict, thang: dict, tong_moc: int) -> str:
    """Thanh tiến trình thang mua lại — CÁI BẪY của mẫu, đọc kỹ.

    Thanh này đầy dần về phía XẤU: đầy = khách sắp rời bỏ, trong khi mắt người
    đọc "thanh đầy = tốt". Nên bắt buộc hai thứ, không được bỏ thứ nào:
      * màu xanh → vàng → đỏ theo độ đầy,
      * LUÔN kèm chữ mốc bên cạnh.
    """
    mm = kh.get("moc")
    if not mm or not tong_moc:
        return ""
    i = thang.get(mm["code"], 0) + 1
    pct = max(6, round(i * 100 / tong_moc))
    mau = "#2EAD6E" if pct < 45 else ("#D98410" if pct < 75 else "#E5484D")
    return (f'<div class="cs-thanh" title="Mốc {i}/{tong_moc} của thang mua '
            f'lại — càng đầy càng gần lúc khách rời bỏ">'
            f'<div class="ray"><span style="width:{pct}%;background:{mau}">'
            f'</span></div>'
            f'<b style="color:{mau}">D{mm["offset_days"]} · mốc {i}/{tong_moc}'
            "</b></div>")


def _nut_dong(kh: dict) -> str:
    """Hai nút đóng khách — khác nhau CỐ Ý, đừng gộp."""
    return (
        f'<form method="post" action="{DUONG}/{kh["id"]}/tu-choi" '
        'class="vc-inline"><button class="kh-btn" type="submit" '
        'title="Đóng ĐỢT NÀY — mốc sau vẫn chăm. Khách nhắn lại là thẻ tự '
        'quay về bảng">🚫 Từ chối</button></form>'
        f'<form method="post" action="{DUONG}/{kh["id"]}/ngung" '
        'class="vc-inline" onsubmit="return confirm(\'NGỪNG LIÊN HỆ hẳn khách '
        "này?\\n\\nKhác với Từ chối: thẻ KHÔNG tự quay lại, mọi luồng tự động "
        "cũng dừng.')\">"
        '<input name="ly_do" required placeholder="Lý do (bắt buộc)" '
        'style="width:150px">'
        '<button class="kh-btn" type="submit" title="Dừng hẳn mọi liên hệ — '
        'bắt buộc ghi lý do">⛔ Ngừng</button></form>')


def _chips(kh: dict) -> str:
    d = kh.get("ngay")
    ra = ""
    if d is not None:
        ra += _chip(f"nhận hàng {int(d)} ngày trước", "#3B62D9", "#E7EDFB")
    if kh.get("moc_lo"):
        ra += _chip(f'lỡ {kh["moc_lo"]} mốc', "#B0413E", "#FBE6E6")
    if (v := kh.get("voucher")):
        ma = (v.get("code") or "").strip() or "chưa báo mã"
        ra += _chip(f'🎟️ {ma} · {_tien(v.get("amount"))}', "#B87514", "#FDF1DC")
    if kh.get("goi"):
        kq = {"nghe": "đã gọi · nghe máy", "khong_nghe": "đã gọi · không nghe",
              "hen_goi_lai": "đã gọi · hẹn gọi lại"}
        ra += _chip(kq.get(kh["goi"].get("call_result") or "", "đã gọi"),
                    "#5A5A5A", "#EDEDF0")
    if int(kh.get("dang_chay") or 0) > 0:
        ra += _chip("đang có đơn chạy", "#8E5E9C", "#F1E7F5")
    return ra


def _thao_tac(kh: dict, cot_keo: list[dict], sua: bool) -> str:
    """Hàng nút trên thẻ. Nút nào chưa có backend thì để KHOÁ kèm tooltip nói rõ
    làm ở đâu — bày nút bấm không ăn còn tệ hơn không bày."""
    cid = kh["id"]
    link = ""
    if kh.get("external_page_id") and kh.get("external_conversation_id"):
        from app.integrations.pancake.links import link_hoi_thoai

        u = link_hoi_thoai(kh["external_page_id"],
                           kh["external_conversation_id"])
        if u:
            link = (f'<a class="kh-ic" href="{escape(u)}" target="_blank" '
                    'rel="noopener" title="Mở hội thoại bên Pancake">'
                    f'{_icon("external-link")}</a>')
    ra = (f'<a class="kh-ic go" href="/crm/khach-hang/{cid}?tab=hoi-thoai" '
          f'title="Mở hội thoại trong CRM">{_icon("message-circle")}</a>{link}'
          # 📖 Thư viện kịch bản = CHÉP TAY, khác hẳn máy bắn tin. Mẫu dặn
          # riêng đừng gộp hai thứ này.
          f'<a class="kh-ic" href="/crm/kich-ban" '
          f'title="Thư viện kịch bản — chép tay, KHÔNG gửi gì">'
          f'{_icon("book-open")}</a>'
          f'<a class="kh-ic" href="/crm/uu-dai?kh={cid}" '
          f'title="Tặng voucher — làm ở màn Ưu đãi; tặng xong khách tự rời cột '
          f'«Cần tặng voucher»">{_icon("ticket")}</a>')
    if not sua:
        return f'<div class="bv-f">{ra}</div>'
    ra += (f'<form method="post" action="{DUONG}/{cid}/cham" '
           'class="vc-inline"><button class="kh-btn" type="submit" '
           'title="Ghi một lượt chăm — ĐÓNG mốc đang mở của khách">✔️ Đã chăm'
           "</button></form>")
    # Ba kết quả gọi chứ không một nút "đã gọi" trơn: máy PHẢI biết kết quả mới
    # đẩy khách đi tiếp (nghe máy → tặng voucher · không nghe → thôi, không gọi
    # lần hai).
    ra += (f'<form method="post" action="{DUONG}/{cid}/goi" class="vc-inline">'
           '<select name="ket_qua">'
           '<option value="nghe">☎️ nghe máy</option>'
           '<option value="khong_nghe">📵 không nghe</option>'
           '<option value="hen_goi_lai">🕐 hẹn gọi lại</option></select>'
           '<button class="kh-btn" type="submit" title="Ghi nhận đã gọi khách">'
           "Ghi</button></form>")
    chon = "".join(f'<option value="{c["ma"]}">{escape(c["ten"])}</option>'
                   for c in cot_keo if c["ma"] != kh["cot"])
    ra += (f'<form method="post" action="{DUONG}/{cid}/cot" class="vc-inline">'
           '<select name="cot" onchange="this.form.requestSubmit()">'
           f'<option value="">↔ chuyển cột…</option>{chon}</select></form>')
    if kh.get("cskh_column"):
        ra += (f'<form method="post" action="{DUONG}/{cid}/mo-lai" '
               'class="vc-inline"><button class="kh-btn" type="submit" '
               'title="Nhả cột đặt tay, trả thẻ về cho máy xếp">↺ Máy xếp'
               "</button></form>")
    return f'<div class="bv-f">{ra}</div>'


def _the(kh: dict, cot_keo: list[dict], sua: bool, thang: dict,
         tong_moc: int) -> str:
    """Một thẻ khách trên pipeline."""
    gap = kh["cot"] in svc.COT_GAP
    hang = kh.get("card_rank")
    tien = _tien(kh.get("total_spent"))
    dau_hang = (f'<span class="kh-nho">{escape(str(hang))} · {tien}</span>'
                if hang else f'<span class="kh-nho">{tien}</span>')
    # Tên khách để riêng: f-string lồng nháy cùng loại là cú pháp 3.12+, mà máy
    # chạy 3.11 — viết gọn ở đây là trang trắng ở đó.
    ten = _e(kh.get("full_name") or "#" + str(kh["id"]))
    return (
        f'<div class="bv-the{" nong" if gap else ""}">'
        f'<div class="bv-h"><a class="kh-name" '
        f'href="/crm/khach-hang/{kh["id"]}">{ten}</a>'
        + ('<span class="bv-nong">💬 chờ đáp</span>' if kh.get("cho_dap")
           else "")
        + '<span class="kh-sp"></span>'
          f'<span class="kh-nho">{_truoc(kh.get("khach_cuoi"))}</span></div>'
        f'<div class="kh-sub">{_e(kh.get("primary_phone"))} · '
        f'{_e(kh.get("owner_name"))}</div>'
        f"<div class=\"kh-sub\">{dau_hang}</div>"
        + _thanh_moc(kh, thang, tong_moc)
        + f'<div class="bv-viec{" urgent" if gap else ""}">📌 '
          f'{escape(kh.get("cau_viec") or "")}</div>'
        + f'<div class="cs-meta">{_chips(kh)}</div>'
        + _thao_tac(kh, cot_keo, sua)
        + (f'<details class="bv-nut"><summary>Đóng khách</summary>'
           f'<div class="ds-acts">{_nut_dong(kh)}</div></details>'
           if sua else "")
        + "</div>"
    )


def _pipeline(data: dict, sua: bool, thang: dict, tong_moc: int,
              loc: dict) -> str:
    cot_keo = [c for c in data["cot"] if c["keo"]]
    cot = ""
    for c in data["cot"]:
        ds = data["theo_cot"].get(c["ma"]) or []
        # Cột đóng mà rỗng thì khỏi chiếm chỗ — bảng đã 12 cột, cuộn ngang mỏi.
        if not ds and c["ma"] in svc.COT_KHONG_VIEC:
            continue
        the = "".join(_the(k, cot_keo, sua, thang, tong_moc) for k in ds) or (
            '<div class="bv-rong">—</div>')
        # Tên cột là LINK mở focus (mẫu: "Chỉ xem cột này + hội thoại").
        cot += (f'<div class="bv-cot"><div class="bv-cot-h" '
                f'style="border-color:{c["mau"]}">'
                f'<a href="{escape(_url(loc, col=c["ma"], cd="pipeline"))}" '
                f'title="Chỉ xem cột này + hội thoại"><b>{escape(c["ten"])}</b>'
                "</a>"
                f'<span class="bv-dem">{len(ds)}</span></div>'
                f'<div class="bv-cot-h2">📌 {escape(c["viec"])}</div>'
                + ("" if c["keo"] else
                   '<div class="bv-khoa">🔒 máy suy ra — không kéo tay</div>')
                + f"{the}</div>")
    return f'<div class="bv-board">{cot}</div>'


# ------------------------------------------------------------------ focus cột
def _hang_hoi_thoai(kh: dict, ht: dict | None, loc: dict, dang_mo: int) -> str:
    """Một dòng trong danh sách hội thoại bên phải màn focus."""
    mo = int(kh["id"]) == dang_mo
    chua_doc = int((ht or {}).get("unread_count") or 0) > 0
    xem = (ht or {}).get("snippet") or ""
    xem = xem[:70] + ("…" if len(xem) > 70 else "") if xem else "—"
    return (f'<a class="cs-row{" on" if mo else ""}" '
            f'href="{escape(_url(loc, col=loc.get("col"), kh=kh["id"]))}">'
            + _icon("mail-warning" if chua_doc else "message-circle")
            + '<span class="ruot">'
              f'<span class="d1"><b>{_e(kh.get("full_name"))}</b>'
              f'<i>{_truoc((ht or {}).get("last_message_at"))}</i></span>'
              f'<span class="d2">{escape(xem)}</span></span>'
            + ('<span class="cham"></span>' if chua_doc else "")
            + "</a>")


def _khung_chat(kh: dict, ht: dict | None, tin: list[dict], loc: dict) -> str:
    """Khung chat mở tại chỗ — cột phải của màn focus.

    Mẫu nạp tin bằng JS qua API riêng. Bên ta dựng thẳng ở server: cả màn này
    vốn đã là form + tải lại trang, đẻ thêm một tầng API chỉ để đỡ một lượt tải
    là thêm một nguồn dữ liệu thứ hai phải giữ cho khớp.
    """
    dong = ""
    for m in tin:
        ben = "agent" if m["sender_type"] in ("agent", "bot") else "customer"
        ten = m.get("sender_user_name") or m["sender_type"]
        dong += (f'<div class="cs-msg {ben}"><div class="bong">'
                 f'<div class="ai">{_e(ten)} · {_truoc(m.get("sent_at"))}</div>'
                 f'<div class="noi">{_e(m.get("content"))}</div></div></div>')
    if not dong:
        dong = ('<div class="cs-rong-chat">Chưa kéo được tin nào của hội thoại '
                "này về kho. Mở bên Pancake để xem đầy đủ.</div>")
    pc = ""
    if (ht or {}).get("external_page_id") and (ht or {}).get(
            "external_conversation_id"):
        from app.integrations.pancake.links import link_hoi_thoai

        u = link_hoi_thoai(ht["external_page_id"],
                           ht["external_conversation_id"])
        if u:
            pc = (f'<a class="kh-ic" href="{escape(u)}" target="_blank" '
                  f'rel="noopener" title="Mở bên Pancake">'
                  f'{_icon("external-link")}</a>')
    ten = _e(kh.get("full_name"))
    return (
        '<div class="cs-chat">'
        '<div class="dau">'
        f'<a class="kh-ic" href="{escape(_url(loc, col=loc.get("col"), kh=0))}"'
        f' title="Về danh sách hội thoại">{_icon("chevron-left")}</a>'
        f'<div class="ten"><b>{ten}</b>'
        f'<span>{_e(kh.get("primary_phone"))} · CSKH</span></div>'
        f'{pc}'
        f'<a class="kh-ic" href="/crm/khach-hang/{kh["id"]}?tab=hoi-thoai" '
        f'title="Mở đầy đủ ở hồ sơ khách">{_icon("eye")}</a>'
        "</div>"
        f'<div class="than">{dong}</div>'
        '<div class="chan">Gõ tin ở màn Hội thoại hoặc bên Pancake — khung này '
        "để ĐỌC nhanh trong lúc chạy bảng việc.</div>"
        "</div>")


def _focus(data: dict, focus: dict, loc: dict, sua: bool, thang: dict,
           tong_moc: int) -> str:
    """Màn FOCUS 1 CỘT của mẫu: trái = thẻ của cột · phải = hội thoại.

    Có mặt để nhân viên "cày" hết một cột mà không phải nhảy qua lại giữa bảng
    việc và màn Hội thoại — đó là cách họ làm việc thật cả buổi sáng.
    """
    c = focus["cot_meta"]
    ds = data["theo_cot"].get(c["ma"]) or []
    cot_keo = [x for x in data["cot"] if x["keo"]]
    the = "".join(_the(k, cot_keo, sua, thang, tong_moc) for k in ds) or (
        '<div class="bv-rong">Cột này chưa có khách nào.</div>')
    ht_map = focus.get("ht") or {}
    kh_mo = focus.get("kh") or 0

    if kh_mo and focus.get("kh_data"):
        phai = _khung_chat(focus["kh_data"], ht_map.get(kh_mo), focus["tin"],
                           loc)
    else:
        hang = "".join(_hang_hoi_thoai(k, ht_map.get(int(k["id"])), loc, kh_mo)
                       for k in ds)
        phai = ('<div class="cs-ds">'
                f'<div class="dau">{_icon("messages-square")}'
                f'<b>Hội thoại · {escape(c["ten"])}</b>'
                "<span>bấm để mở hội thoại</span></div>"
                + (f'<div class="than">{hang}</div>' if hang else
                   '<div class="cs-rong-chat">Cột này chưa có khách nào.</div>')
                + "</div>")
    return (
        '<div class="cs-focus">'
        '<div class="trai">'
        f'<div class="dau"><span class="cham" style="background:{c["mau"]}">'
        f'</span><b>{escape(c["ten"])}</b>'
        f'<a href="{escape(_url(loc, col="", kh=0))}" title="Bỏ focus, xem tất '
        f'cả cột">{_icon("x")}</a>'
        f'<span class="dem">{len(ds)}</span></div>'
        f'<div class="goi-y">📌 {escape(c["viec"])}</div>'
        f"{the}</div>"
        f'<div class="phai">{phai}</div>'
        "</div>")


def _bang(data: dict, sua: bool) -> str:
    ten_cot = {c["ma"]: c for c in data["cot"]}
    than = ""
    for kh in data["the"]:
        c = ten_cot.get(kh["cot"])
        mm = kh.get("moc")
        o_moc = "D" + str(mm["offset_days"]) if mm else "—"
        o_ngay = int(kh["ngay"]) if kh.get("ngay") is not None else "—"
        than += (
            "<tr>"
            f'<td><a class="kh-name" href="/crm/khach-hang/{kh["id"]}">'
            f'{_e(kh.get("full_name"))}</a>'
            f'<div class="kh-sub">{_e(kh.get("primary_phone"))}</div></td>'
            f'<td><span class="kh-st chua" style="background:'
            f'{c["mau"] if c else "var(--soft)"}22;color:'
            f'{c["mau"] if c else "var(--sub)"}">'
            f'{escape(c["ten"] if c else kh["cot"])}</span>'
            f'<div class="kh-nho">{escape(kh["cot_vi_sao"])}</div></td>'
            f'<td class="num">{o_ngay}</td>'
            f'<td class="kh-nho">{o_moc}</td>'
            f'<td>📌 {escape(kh.get("cau_viec") or "")}'
            f'<div class="cs-meta">{_chips(kh)}</div></td>'
            f'<td>{_e(kh.get("owner_name"))}</td>'
            f'<td class="kh-nho">{_truoc(kh.get("khach_cuoi"))}</td>'
            + (f'<td><div class="ds-acts">{_nut_dong(kh)}</div></td>'
               if sua else "<td>—</td>")
            + "</tr>")
    than = than or ('<tr><td colspan="8" class="rong">Không có khách nào — '
                    "hoặc đã chăm hết hôm nay 🎉</td></tr>")
    return ('<div class="kh-card"><div class="kh-tblwrap">'
            '<table class="kh-tbl"><thead><tr>'
            '<th>Khách</th><th>Cột</th><th class="num">Ngày</th><th>Mốc</th>'
            "<th>Việc cần làm</th><th>Phụ trách</th><th>Khách nhắn</th>"
            "<th>Đóng khách</th></tr></thead>"
            f"<tbody>{than}</tbody></table></div></div>")


def _rong(data: dict, loc: dict, quan_ly: bool, che_do: str) -> str:
    """Bảng trống thì phải nói RÕ vì sao trống + cách xem tiếp.

    Màn trống không giải thích là nguồn gốc câu "sao không có dữ liệu" — người
    dùng không có cách nào biết là do bộ lọc hay do hệ thống hỏng."""
    if data["the"]:
        return ""
    if loc.get("viec"):
        return ('<div class="flash warn">Không còn <b>việc nào hôm nay</b> '
                "trong phạm vi đang lọc 🎉 "
                f'<a href="{escape(_url(loc, viec=0))}">Xem tất cả</a> để soi '
                "lại cả vòng chăm.</div>")
    dang_loc = [ten for khoa, ten in (
        ("nv", "nhân viên"), ("page", "fanpage"), ("tt", "cột"),
        ("hang", "hạng thẻ"), ("dai", "ngày nhận hàng"),
        ("ntu", "ngày nhận hàng"), ("nden", "ngày nhận hàng"),
        ("q", "từ khoá tìm")) if loc.get(khoa)]
    if dang_loc:
        # Bộ lọc đang bật thì PHẢI đổ tại bộ lọc. Nói "chưa có khách nào" trong
        # khi người ta vừa chọn một fanpage là chỉ sai chỗ, và họ sẽ đi tìm lỗi
        # ở kho dữ liệu chứ không nghĩ tới cái ô mình vừa bấm.
        ten = " · ".join(dict.fromkeys(dang_loc))
        return ('<div class="flash warn">Không có khách nào khớp bộ lọc đang '
                f"bật (<b>{escape(ten)}</b>). "
                f'<a href="{escape(_url({"cd": che_do}))}">Xoá lọc</a> để xem '
                "lại toàn bộ.</div>")
    if not quan_ly:
        return ('<div class="flash warn">Bạn <b>chưa được giao khách CSKH '
                "nào</b> đang trong vòng chăm, nên bảng trống. Nếu bạn chắc là "
                "mình có khách, báo quản lý kiểm tra phần chia khách.</div>")
    return ('<div class="flash warn">Chưa có khách nào trong vòng chăm — hoặc '
            "mọi khách đều đã được chăm hôm nay. Bật <b>“Hiện cả khách đã chăm "
            "hôm nay”</b> ở trên để kiểm.</div>")


_CSS = """
<style>
.cs-ctkm{display:flex;align-items:flex-start;gap:11px;flex-wrap:wrap;
  background:var(--soft);border:1px solid var(--accent);border-radius:12px;
  padding:11px 14px;margin-bottom:12px;font-size:13px;line-height:1.55}
.cs-ctkm b{flex:1 1 100%}
.cs-ctkm .nd{flex:1 1 auto;min-width:0;white-space:pre-wrap;color:var(--sub)}
.cs-ctkm .thieu{flex:1 1 100%;color:var(--warn)}
.cs-meta{display:flex;gap:5px;flex-wrap:wrap;align-items:center;margin-top:6px}
.cs-chip{font-size:10.5px;font-weight:700;border-radius:99px;padding:1px 7px;
  border:1px solid transparent;white-space:nowrap}
.cs-thanh{display:flex;align-items:center;gap:7px;margin-top:7px;font-size:10.5px}
.cs-thanh .ray{flex:1 1 auto;height:5px;border-radius:99px;
  background:var(--soft);overflow:hidden}
.cs-thanh .ray span{display:block;height:100%;border-radius:99px}
.cs-tbl{width:100%;border-collapse:collapse;font-size:13px}
.cs-tbl th,.cs-tbl td{padding:8px 10px;border-bottom:1px solid var(--border);
  text-align:left;vertical-align:top}
.cs-tbl th{font-size:11.5px;color:var(--sub);text-transform:uppercase;
  letter-spacing:.04em}
/* ---------- focus 1 cột: trái thẻ · phải hội thoại (mẫu index.php?col=) ---- */
.cs-focus{display:flex;gap:14px;align-items:stretch;
  height:calc(100vh - 300px);min-height:420px}
.cs-focus .trai{flex:0 0 300px;width:300px;background:var(--soft);
  border-radius:14px;padding:12px 10px;overflow-y:auto}
.cs-focus .trai .dau{display:flex;align-items:center;gap:8px;padding:0 4px 6px;
  font-size:13px}
.cs-focus .trai .dau .cham{width:9px;height:9px;border-radius:3px;flex:0 0 auto}
.cs-focus .trai .dau b{flex:1 1 auto;min-width:0;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.cs-focus .trai .dau a{color:var(--sub);display:flex;flex:0 0 auto}
.cs-focus .trai .dau .ico{width:14px;height:14px}
.cs-focus .trai .dem{background:var(--card);border-radius:99px;padding:1px 8px;
  font-size:11px;font-weight:700;color:var(--sub);flex:0 0 auto}
.cs-focus .trai .goi-y{font-size:10.5px;color:var(--sub);padding:0 4px 9px}
.cs-focus .phai{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;
  border:1px solid var(--border);border-radius:14px;background:var(--card);
  overflow:hidden}
.cs-ds,.cs-chat{display:flex;flex-direction:column;min-height:0;flex:1 1 auto}
.cs-ds .dau,.cs-chat .dau{flex:0 0 auto;display:flex;align-items:center;gap:9px;
  padding:13px 16px;border-bottom:1px solid var(--border);font-size:13.5px}
.cs-ds .dau span{font-size:12px;color:var(--sub)}
.cs-ds .dau .ico{width:16px;height:16px;color:var(--accent)}
.cs-ds .than,.cs-chat .than{flex:1 1 auto;min-height:0;overflow-y:auto}
.cs-row{display:flex;align-items:center;gap:11px;padding:11px 16px;
  border-bottom:1px solid var(--border);text-decoration:none;color:var(--text)}
.cs-row:hover{background:var(--soft)}
.cs-row.on{background:var(--soft);box-shadow:inset 3px 0 0 var(--accent)}
.cs-row .ico{width:16px;height:16px;color:var(--sub);flex:0 0 auto}
.cs-row .ruot{flex:1 1 auto;min-width:0}
.cs-row .d1{display:flex;align-items:center;gap:8px;font-size:13px}
.cs-row .d1 b{flex:1 1 auto;min-width:0;overflow:hidden;white-space:nowrap;
  text-overflow:ellipsis}
.cs-row .d1 i{font-style:normal;font-size:11px;color:var(--sub);flex:0 0 auto}
.cs-row .d2{display:block;font-size:12.5px;color:var(--sub);overflow:hidden;
  white-space:nowrap;text-overflow:ellipsis}
.cs-row .cham{width:8px;height:8px;border-radius:99px;background:var(--err);
  flex:0 0 auto}
.cs-chat .dau .ten{flex:1 1 auto;min-width:0}
.cs-chat .dau .ten b{display:block;overflow:hidden;white-space:nowrap;
  text-overflow:ellipsis}
.cs-chat .dau .ten span{font-size:11.5px;color:var(--sub)}
.cs-chat .than{background:var(--soft);padding:14px;display:flex;
  flex-direction:column;gap:7px}
.cs-msg{display:flex}
.cs-msg.agent{justify-content:flex-end}
.cs-msg .bong{max-width:74%;background:var(--card);border:1px solid var(--border);
  border-radius:11px;padding:7px 10px;font-size:12.5px;line-height:1.5}
.cs-msg.agent .bong{background:var(--accent);border-color:var(--accent);
  color:#fff}
.cs-msg .ai{font-size:10.5px;opacity:.75;margin-bottom:2px}
.cs-msg .noi{white-space:pre-wrap}
.cs-chat .chan{flex:0 0 auto;padding:9px 16px;border-top:1px solid var(--border);
  font-size:11.5px;color:var(--sub)}
.cs-rong-chat{padding:40px 20px;text-align:center;color:var(--sub);
  font-size:12.5px}
@media (max-width:1100px){
  .cs-focus{flex-direction:column;height:auto}
  .cs-focus .trai{flex:0 0 auto;width:auto}
}
</style>
"""


def render_bang_viec(data: dict, user: dict, loc: dict, *, sua: bool = False,
                     che_do: str = "bang", quan_ly: bool = False,
                     ds_nv: list[dict] | None = None,
                     ds_page: list[dict] | None = None,
                     ds_hang: list[dict] | None = None,
                     focus: dict | None = None,
                     flash: str = "", loi: str = "") -> str:
    """Bảng việc CSKH — cột do máy suy ra từ NGÀY NHẬN HÀNG CUỐI."""
    # Thang mốc đọc MỘT LẦN cho cả bảng: mỗi thẻ tự hỏi lại là vài trăm lượt
    # dựng cùng một danh sách.
    thang_ds = svc.moc_thang()
    thang = {m["code"]: i for i, m in enumerate(thang_ds)}

    dau = ('<div class="bv-head">'
           + _thanh_cong_cu(loc, che_do, data.get("xong_hom_nay") or 0)
           + _dai_loc(loc, che_do, quan_ly,
                      data.get("tong") or len(data["the"]),
                      cot=data["cot"], dem_cot=data.get("dem_cot") or {},
                      ds_nv=ds_nv or [], ds_page=ds_page or [],
                      ds_hang=ds_hang or [],
                      cham_tran=bool(data.get("cham_tran")))
           + _tab_dem(data["dem"], loc)
           + "</div>")
    # `.content.full` là flex HÀNG và chỉ chờ ĐÚNG MỘT con (xem shell.py) — hai
    # tầng đầu/thân để trần sẽ đứng cạnh nhau. Bọc lại thành cột.
    body = (
        _CSS + '<div class="bv-wrap">' + dau
        + '<div class="bv-than">'
        + (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + (f'<div class="flash err">{escape(loi)}</div>' if loi else "")
        + _bang_bao(data)
        + _dai_luat(data)
        + _dai_ctkm(data.get("ctkm"))
        + _dai_ngu(data.get("khach_ngu") or 0)
        + _dai_da_an(data, loc)
        + _dai_cat(data)
        + ("" if focus else _rong(data, loc, quan_ly, che_do))
        + (_focus(data, focus, loc, sua, thang, len(thang_ds)) if focus
           else _pipeline(data, sua, thang, len(thang_ds), loc)
           if che_do == "pipeline" else _bang(data, sua))
        + '<p class="note" style="margin-top:10px">🚫 <b>Từ chối</b> = đóng đợt '
          "này, khách nhắn lại là thẻ <b>tự quay về</b> bảng (không hỏi xác "
          "nhận vì bấm nhiều lần trong ngày). ⛔ <b>Ngừng liên hệ</b> = dừng "
          "hẳn mọi luồng tự động, có hỏi + bắt buộc lý do. Đây là <b>vòng đời "
          'khách sau khi nhận hàng</b> — khác <a href="/crm/cham-soc">Chăm sóc '
          "C01-C09</a> (liệu trình của MỘT đơn).</p>"
        + "</div></div>"
    )
    return render_shell(
        "Bảng việc CSKH", "crm-cskh-board", body,
        heading="Bảng việc CSKH",
        sub="Vòng đời khách sau khi nhận hàng: cảm ơn → voucher → thang mua lại",
        full=True,
    )


# ------------------------------------------------------------------ khuyến mãi
def render_khuyen_mai(ds: list[dict], user: dict, *, sua: bool = False,
                      flash: str = "", loi: str = "") -> str:
    """Đợt khuyến mãi CSKH — nhập tay từng đợt.

    Cố ý KHÔNG lấy tự động từ Chiến dịch / Flash sale: mốc khuyến mãi gửi thẳng
    nội dung này cho khách, đoán mò là gửi sai ưu đãi.
    """
    hang = ""
    for r in ds:
        tt = "✅ đang bật" if r["active"] else "⏸️ tắt"
        han = f'{_d(r.get("start_on"))} → {_d(r.get("end_on"))}'
        nut = ""
        if sua:
            nut = (
                f'<form method="post" action="/crm/cskh/khuyen-mai/{r["id"]}'
                '/bat" style="display:inline"><button class="btn" '
                f'type="submit">{"Tắt" if r["active"] else "Bật"}</button>'
                "</form> "
                f'<form method="post" action="/crm/cskh/khuyen-mai/{r["id"]}'
                '/xoa" style="display:inline" '
                "onsubmit=\"return confirm('Xoá đợt này?')\">"
                '<button class="btn" type="submit">Xoá</button></form>')
        hang += (f"<tr><td><b>{_e(r.get('name'))}</b><br>"
                 '<span style="color:var(--sub);font-size:12px">'
                 f"{_e(r.get('content'))}</span></td>"
                 f"<td>{han}</td><td>{tt}</td><td>{nut}</td></tr>")
    if not hang:
        hang = ('<tr><td colspan="4" style="color:var(--sub)">Chưa có đợt nào. '
                "Mốc khuyến mãi sẽ tạm chăm như mốc thường — máy KHÔNG bịa nội "
                "dung ưu đãi để gửi khách.</td></tr>")

    form = ""
    if sua:
        form = (
            '<div class="panel"><div class="panel-t">Thêm đợt khuyến mãi</div>'
            '<form method="post" action="/crm/cskh/khuyen-mai" '
            'class="kh-filters" style="flex-wrap:wrap">'
            '<input name="ten" placeholder="Tên đợt (VD: Ưu đãi tháng 8)" '
            'required style="min-width:220px">'
            '<input name="noi_dung" placeholder="Nội dung gửi khách" '
            'style="min-width:320px">'
            '<label style="font-size:12.5px">Từ <input type="date" '
            'name="tu_ngay"></label>'
            '<label style="font-size:12.5px">Đến <input type="date" '
            'name="den_ngay"></label>'
            '<label style="font-size:12.5px;display:inline-flex;gap:6px;'
            'align-items:center"><input type="checkbox" name="bat" value="1"> '
            "Bật ngay</label>"
            '<button class="btn primary" type="submit">Lưu đợt</button>'
            "</form></div>")

    bao = ""
    if flash:
        bao += f'<div class="flash ok">{escape(flash)}</div>'
    if loi:
        bao += f'<div class="flash err">{escape(loi)}</div>'

    body = (_CSS + bao + form
            + '<div class="panel"><div class="panel-t">Các đợt đã khai</div>'
            '<table class="cs-tbl"><thead><tr><th>Đợt</th><th>Thời gian</th>'
            "<th>Tình trạng</th><th></th></tr></thead>"
            f"<tbody>{hang}</tbody></table></div>")
    return render_shell(
        "Đợt khuyến mãi CSKH", "crm-cskh-board", body,
        heading="Đợt khuyến mãi CSKH",
        sub="Mốc chăm có cờ khuyến mãi (D45 · D75 · D105 …) lấy nội dung từ đợt "
            "ĐANG CHẠY hôm nay. Không có đợt nào thì mốc đó chăm như mốc thường.",
        actions=f'<a class="btn" href="{DUONG}">← Bảng việc CSKH</a>',
    )
