"""Màn 21 — ĐƠN HÀNG (C7, port `don-hang.php` của mẫu Kallet).

Bố cục y mẫu: 5 thẻ chỉ số · ô tìm · dải lọc (khoảng thời gian + 7 ô) · bảng
11 cột có thanh tổng · chân phân trang · thanh nổi khi tích chọn · popover
chọn cột xuất Excel. Chỗ nào mẫu có mà dữ liệu bên ta chưa dựng nổi thì nói
thẳng ra bằng chữ, KHÔNG vẽ nút chết.

Dùng lại lớp CSS `kh-*` của màn Khách hàng (cùng một ngôn ngữ hình khối) và chỉ
thêm `dh-*` cho phần mẫu có riêng ở màn này — xem `_CSS` trong shell.py.
"""

from html import escape
from urllib.parse import quote

from app.services import don_hang_service as dv
from app.web.shell import _icon, render_shell

_TRANG = "/crm/don-hang"


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _so(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".")


def _tien(v) -> str:
    """Tiền gọn như mẫu: 0₫ · 710k · 7,9 tr · 1,2 tỷ."""
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        return "0₫"
    if n <= 0:
        return "0₫"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " tỷ"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " tr"
    return _so(round(n / 1000)) + "k"


def _tien_day(v) -> str:
    """Số tiền ĐẦY ĐỦ cho tooltip — chỗ nào cần đối chiếu thì phải thấy từng đồng."""
    try:
        return _so(int(float(v or 0))) + "đ"
    except (TypeError, ValueError):
        return "0đ"


def _ngay(v) -> str:
    if not v:
        return "—"
    try:
        from app.core.ngay import MUI_GIO

        return v.astimezone(MUI_GIO).strftime("%d/%m/%Y")
    except (AttributeError, ValueError):
        return str(v)


def _url(loc: dict, **doi) -> str:
    """Link màn này giữ nguyên bộ lọc, chỉ đổi vài tham số.

    Giá trị rỗng/0 bị bỏ khỏi query cho URL sạch; `trang=1` cũng bỏ vì đó là
    mặc định (link chia sẻ ngắn hơn, và bấm lọc luôn về trang 1).
    """
    t = {**loc, **doi}
    cai = [(k, v) for k, v in t.items()
           if v not in ("", None, 0) and not (k == "trang" and v == 1)]
    duoi = "&".join(f"{k}={quote(str(v))}" for k, v in cai)
    return _TRANG + (f"?{duoi}" if duoi else "")


def _chon(ten: str, muc: list[tuple[str, str]], dang_chon) -> str:
    """Một ô <select> của dải lọc; đổi là tự nộp form."""
    o = "".join(
        f'<option value="{escape(str(ma))}"'
        f'{" selected" if str(dang_chon or "") == str(ma) else ""}>'
        f"{escape(nhan)}</option>" for ma, nhan in muc)
    return (f'<select name="{ten}" onchange="this.form.requestSubmit()">'
            f"{o}</select>")


# ------------------------------------------------------------ 5 thẻ chỉ số
def _the_chi_so(cs: dict) -> str:
    """Dải 5 thẻ như mẫu. Tỉ lệ tính trên SỐ ĐƠN khớp bộ lọc; không có đơn nào
    thì hiện "—" chứ không phải 0% (0% nghĩa là "có đơn mà tịt", khác hẳn)."""
    tong = int(cs.get("so_don") or 0)

    def ti_le(n):
        return f"{round(int(n or 0) / tong * 100)}%" if tong else "—"

    the = [
        (_tien(cs.get("thanh_cong")), "doanh thu (giao thành công)", "var(--ok)"),
        (_so(tong), "số đơn", "var(--accent)"),
        (ti_le(cs.get("n_xong")), "tỉ lệ thành công", "var(--out)"),
        (ti_le(cs.get("n_hoan")), "tỉ lệ hoàn", "var(--err)"),
        (ti_le(cs.get("n_doi")), "tỉ lệ đổi hàng", "var(--warn)"),
    ]
    return '<div class="kh-tiles">' + "".join(
        f'<div class="kh-tile" style="--c:{mau}"><b></b>'
        f'<div class="n">{escape(gia_tri)}</div>'
        f'<div class="l">{escape(nhan)}</div></div>'
        for gia_tri, nhan, mau in the) + "</div>"


# ------------------------------------------------------------ dải lọc
def _dai_loc(loc: dict, nhan_vien, nv_pos, pages, ky_luong, co_xuat: bool) -> str:
    nhan_ky, _, _ = dv.khoang_ngay(loc.get("ky_han") or "all",
                                   loc.get("tu") or "", loc.get("den") or "")
    tt = [("", "Mọi trạng thái")] + [(ma, m["ten"])
                                     for ma, m in dv.TRANG_THAI.items()]
    loai = [("", "Mọi lần mua")] + list(dv.LOAI_DON.items())
    cs = [("", "Mọi công sức")] + list(dv.CONG_SUC.items())
    qc = [("", "Mọi quảng cáo"), ("co", "Có ads"), ("khong", "Không ads")]
    nv = [("", "Mọi nhân viên CRM")] + [(str(u["id"]), u["name"])
                                        for u in (nhan_vien or [])]
    nvp = [("", "Mọi nhân viên POS")] + [(t, t) for t in (nv_pos or [])]
    fp = [("", "Mọi fanpage")] + [
        (p["ma"], f'{p["ten"]} ({_so(p["so_don"])})') for p in (pages or [])]
    kl = [("", "Mọi kỳ lương")] + [(k, k) for k in (ky_luong or [])]
    han = [(ma, nhan) for ma, nhan in dv.CHON_NHANH]
    co_loc = any(loc.get(k) for k in
                 ("q", "status", "order_type", "effort", "ads", "nv", "nv_pos",
                  "page", "ky", "tu", "den")) or (loc.get("ky_han") or "all") != "all"
    # Ô "đơn / trang" nằm ở CHÂN BẢNG nhưng thuộc form này (form="dh-loc") — nên
    # KHÔNG khai thêm input ẩn `size` ở đây, hai ô cùng tên là server đọc nhầm.
    return (
        f'<form class="kh-filters" id="dh-loc" method="get" action="{_TRANG}">'
        f'<label class="kh-find">{_icon("search")}'
        f'<input name="q" value="{escape(loc.get("q") or "")}" '
        'placeholder="Tìm mã đơn · tên khách · số điện thoại…"></label>'
        f'<span class="dh-range">{_icon("calendar")}'
        f'<b>{escape(nhan_ky)}</b>{_chon("ky_han", han, loc.get("ky_han") or "all")}'
        '</span>'
        '<label class="dh-day"><span>từ</span>'
        f'<input type="date" name="tu" value="{escape(loc.get("tu") or "")}" '
        'onchange="this.form.requestSubmit()"></label>'
        '<label class="dh-day"><span>đến</span>'
        f'<input type="date" name="den" value="{escape(loc.get("den") or "")}" '
        'onchange="this.form.requestSubmit()"></label>'
        + _chon("status", tt, loc.get("status"))
        + _chon("order_type", loai, loc.get("order_type"))
        + _chon("effort", cs, loc.get("effort"))
        + _chon("ads", qc, loc.get("ads"))
        + _chon("nv", nv, loc.get("nv"))
        + _chon("nv_pos", nvp, loc.get("nv_pos"))
        + _chon("page", fp, loc.get("page"))
        + _chon("ky", kl, loc.get("ky"))
        + '<button class="kh-btn go">🔍 Lọc</button>'
        + (f'<a class="kh-clear" href="{_TRANG}">{_icon("filter-x")}Xoá lọc</a>'
           if co_loc else
           f'<span class="kh-clear off">{_icon("filter-x")}Xoá lọc</span>')
        + '<span class="kh-sp"></span>'
        + (_nut_xuat(loc) if co_xuat else
           '<span class="kh-clear off" title="Xuất dữ liệu cần quyền '
           'data.export">' + _icon("file-spreadsheet") + "Xuất Excel</span>")
        + "</form>"
    )


def _luoi_cot(lop: str, ten_o: str = "") -> str:
    """Lưới ô tích CHỌN CỘT — dùng ở CẢ HAI chỗ (popover trên và thanh nổi).

    Cùng lớp `dh-col` để JS giữ hai lưới khớp nhau. `ten_o` rỗng = ô tích không
    có name: lưới trên nằm trong form GET bộ lọc, có name là `cols` bị bơm vào
    mọi link lọc; JS tự dựng URL cho nó.
    """
    nm = f' name="{ten_o}"' if ten_o else ""
    o = "".join(
        f'<label title="{escape(nhan)}"><input type="checkbox" class="{lop}"'
        f'{nm} value="{ma}" onchange="dhTickCot(this)"'
        f'{" checked" if ma in dv.COT_MAC_DINH else ""}>'
        f"<span>{escape(nhan)}</span></label>"
        for ma, nhan in dv.COT_XUAT.items())
    return f'<div class="dh-cols">{o}</div>'


def _dau_popover(ten_dong: str) -> str:
    return ('<div class="dh-pop-h"><span>Chọn cột muốn xuất</span><span>'
            '<a href="javascript:void(0)" onclick="dhChonCot(1)">Chọn hết</a> · '
            '<a href="javascript:void(0)" onclick="dhChonCot(0)">Bỏ hết</a>'
            f"</span></div>{ten_dong}")


def _nut_xuat(loc: dict) -> str:
    """Nút "Xuất Excel" ở dải lọc — xuất TOÀN BỘ đơn khớp bộ lọc hiện tại."""
    return (
        '<span class="dh-wrap">'
        '<button type="button" class="kh-btn" onclick="dhPop(event,\'dh-pop\')">'
        + _icon("file-spreadsheet") + "Xuất Excel" + _icon("chevron-down")
        + "</button>"
        '<div class="dh-pop" id="dh-pop">'
        + _dau_popover(_luoi_cot("dh-col"))
        + '<button type="button" class="dh-go" onclick="dhXuatLoc()">'
          'Xuất <span class="dh-n">0</span> cột theo bộ lọc</button>'
        + "</div></span>"
    )


# ------------------------------------------------------------ bảng
def _sap(loc: dict, khoa: str, nhan: str) -> str:
    """Tiêu đề cột bấm được để đổi sắp xếp (mẫu chỉ cho 3 cột này)."""
    dang = loc.get("sort") or "ngay"
    huong = loc.get("dir") or "desc"
    moi = "asc" if (dang == khoa and huong == "desc") else "desc"
    mui = " ↑" if (dang == khoa and huong == "asc") else (
        " ↓" if dang == khoa else "")
    return (f'<a class="dh-sort" href="{escape(_url(loc, sort=khoa, dir=moi, trang=1))}">'
            f"{escape(nhan)}{mui}</a>")


def _pill(lop: str, chu: str, tip: str = "") -> str:
    t = f' title="{escape(tip)}"' if tip else ""
    return f'<span class="dh-pill {lop}"{t}>{escape(chu)}</span>'


def _o_ma_don(r: dict) -> str:
    """Ô mã đơn — mở thẳng đơn bên POS nếu có đủ shop + mã hệ thống."""
    ma = dv.ma_don(r)
    link = dv.link_pos(r)
    if link:
        return (f'<a class="dh-ma" href="{escape(link)}" target="_blank" '
                f'rel="noopener" title="Mở đơn này bên POS">{escape(ma)}</a>')
    return f'<span class="dh-ma">{escape(ma)}</span>'


def _o_khach(r: dict) -> str:
    tel = (r.get("sdt") or "").strip()
    o_tel = (f'<button type="button" class="kh-tel" data-so="{escape(tel)}" '
             f'title="Bấm để chép số">{escape(tel)}</button>' if tel else "")
    ten = escape(r.get("khach") or "—")
    if r.get("customer_id"):
        ten = (f'<a class="kh-name" href="/crm/khach-hang/{r["customer_id"]}">'
               f"{ten}</a>")
    return f'{ten}<div class="kh-sub">{o_tel}</div>'


def _o_tien(r: dict) -> str:
    v = r.get("total_amount")
    khong = not v or float(v) == 0
    chinh = (f'<div class="dh-0">0đ</div>' if khong else
             f'<div title="{escape(_tien_day(v))}">{_tien(v)}</div>')
    phu = ""
    # Chỉ hiện dòng phụ khi POS THẬT SỰ gửi số — trống ≠ 0đ.
    if r.get("prepaid_amount") is not None or r.get("cod_amount") is not None:
        phu = ('<div class="kh-nho">Trả trước '
               f'{_tien(r.get("prepaid_amount"))} · COD '
               f'{_tien(r.get("cod_amount"))}</div>')
    return chinh + phu


def _hang(r: dict) -> str:
    tt = dv.TRANG_THAI.get(r.get("status") or "") or {}
    lm = r.get("order_type") or ""
    cong = r.get("effort_axis") or ""
    nguoi = " · ".join(x for x in (r.get("sale_ten"), r.get("cskh_ten")) if x)
    link_hoi_thoai = (f'/crm/khach-hang/{r["customer_id"]}?tab=hoi-thoai'
                      if r.get("customer_id") else "")
    nut = (f'<a class="kh-ic go" href="{link_hoi_thoai}" '
           f'title="Mở hội thoại của khách">{_icon("message-circle")}</a>'
           if link_hoi_thoai else
           f'<span class="kh-ic" title="Đơn chưa gắn khách">'
           f'{_icon("message-circle")}</span>')
    return (
        "<tr>"
        f'<td><input type="checkbox" class="dh-tick" name="ids" '
        f'value="{r["id"]}" onclick="dhTick()"></td>'
        f"<td>{_o_ma_don(r)}<div class=\"kh-nho\">{_ngay(r.get('ngay_dat'))}</div></td>"
        f"<td>{_o_khach(r)}</td>"
        f'<td class="money">{_o_tien(r)}</td>'
        f'<td>{_pill(tt.get("lop", "mo"), tt.get("ten", r.get("status") or "—"), "POS: " + tt.get("pos", "—"))}</td>'
        f'<td>{_pill("lm-" + (lm or "no"), dv.LOAI_DON.get(lm, "—"))}</td>'
        f'<td>{_pill("cs-" + (cong or "no"), dv.CONG_SUC.get(cong, "—"))}</td>'
        f'<td>{_pill("ads" if r.get("ads_attributed") else "no", "Có ads" if r.get("ads_attributed") else "Không ads", _e(r.get("pos_ad_id")) if r.get("pos_ad_id") else "")}</td>'
        f'<td>{_e(r.get("page_ten") or r.get("pos_page_id"))}</td>'
        f'<td>{_e(nguoi or r.get("nv_pos"))}'
        + (f'<div class="kh-nho">POS</div>' if not nguoi and r.get("nv_pos") else "")
        + "</td>"
        f'<td><div class="kh-acts">{nut}'
        f'<a class="kh-ic" href="/crm/don-hang/{r["id"]}" title="Chi tiết đơn">'
        f'{_icon("external-link")}</a></div></td>'
        "</tr>"
    )


def _thanh_tong(cs: dict, tong: int, dau: int, so_dong: int) -> str:
    return (
        '<div class="kh-head"><span class="cnt">Đang xem '
        f'{dau + 1 if so_dong else 0}–{dau + so_dong} / {_so(tong)} đơn</span>'
        '<div class="dh-sum">'
        f'<span><b title="{escape(_tien_day(cs.get("len_don")))}">'
        f'{_tien(cs.get("len_don"))}</b>lên đơn</span>'
        f'<span><b class="ok" title="{escape(_tien_day(cs.get("thanh_cong")))}">'
        f'{_tien(cs.get("thanh_cong"))}</b>thành công</span>'
        f'<span><b>{_so(tong)}</b>số đơn</span>'
        "</div></div>"
    )


def _chan(loc: dict, trang: int, so_trang: int) -> str:
    o_size = "".join(
        f'<option value="{n}"{" selected" if n == int(loc.get("size") or 30) else ""}>'
        f"{n}</option>" for n in (30, 50, 100))
    return (
        '<div class="kh-foot"><div style="display:flex;align-items:center;gap:7px">'
        "<span>Hiển thị</span>"
        f'<select form="dh-loc" name="size" onchange="this.form.requestSubmit()">'
        f"{o_size}</select><span>đơn / trang</span></div>"
        '<div style="display:flex;align-items:center;gap:10px">'
        f"<span>Trang {trang} / {so_trang}</span><div class=\"kh-pager\">"
        + (f'<a class="kh-pg" href="{escape(_url(loc, trang=trang - 1))}" '
           f'aria-label="Trang trước">{_icon("chevron-left")}</a>' if trang > 1
           else f'<span class="kh-pg off">{_icon("chevron-left")}</span>')
        + (f'<a class="kh-pg" href="{escape(_url(loc, trang=trang + 1))}" '
           f'aria-label="Trang sau">{_icon("chevron-right")}</a>'
           if trang < so_trang else
           f'<span class="kh-pg off">{_icon("chevron-right")}</span>')
        + "</div></div></div>"
    )


def _thanh_noi(tong: int, co_xuat: bool) -> str:
    """Thanh nổi khi tích chọn đơn (mẫu: bulkbar). Ba luật của mẫu giữ nguyên:
    không tràn màn hình · không đè menu trái · không che chân phân trang."""
    xuat = (
        '<span class="dh-wrap">'
        '<button type="button" class="dh-bar-btn" onclick="dhPop(event,\'dh-pop2\')">'
        + _icon("file-spreadsheet") + "Xuất Excel</button>"
        '<div class="dh-pop up" id="dh-pop2">'
        + _dau_popover(_luoi_cot("dh-col", "cols"))
        + '<button type="submit" class="dh-go" onclick="return dhTruocKhiXuat()">'
          'Xuất <span class="dh-n">0</span> cột</button>'
        + "</div></span>"
    ) if co_xuat else (
        '<span class="dh-bar-btn off" title="Xuất dữ liệu cần quyền data.export">'
        + _icon("file-spreadsheet") + "Xuất Excel</span>")
    return (
        f'<div class="dh-bar" id="dh-bar" data-tong="{tong}">'
        '<span class="dh-bar-n">Đã chọn <b id="dh-dem">0</b> đơn</span>'
        '<span class="dh-bar-o" id="dh-khac"></span>'
        f'<button type="button" class="dh-bar-all" id="dh-all-btn" '
        f'onclick="dhChonCaBoLoc()">Chọn cả {_so(tong)} đơn khớp bộ lọc</button>'
        '<span class="dh-bar-vach"></span>'
        + xuat +
        '<button type="button" class="dh-bar-x" onclick="dhBoChon()" '
        'title="Bỏ chọn">×</button></div>'
    )


# ------------------------------------------------------------ trang
def render(data: dict, loc: dict, *, nhan_vien=None, nv_pos=None, pages=None,
           ky_luong=None, co_xuat: bool = False) -> str:
    """Vẽ cả màn. `data` là kết quả `don_hang_service.man_hinh`."""
    rows, tong, cs = data["rows"], data["tong"], data["chi_so"]
    dau = (data["trang"] - 1) * data["size"]
    cot = (
        '<th style="width:34px"><input type="checkbox" id="dh-head" '
        'onclick="dhTickTrang(this)" title="Chọn cả trang"></th>'
        f'<th>{_sap(loc, "ngay", "Mã đơn · ngày đặt")}</th>'
        "<th>Khách</th>"
        f'<th class="num">{_sap(loc, "gia", "Giá trị")}</th>'
        "<th>Trạng thái</th><th>Lần mua</th><th>Công sức</th><th>Quảng cáo</th>"
        "<th>Fanpage</th><th>Nhân viên</th>"
        '<th style="text-align:right">Thao tác</th>'
    )
    than = "".join(_hang(r) for r in rows) or (
        '<tr><td colspan="11" class="rong">'
        + ("Chưa có đơn nào — đơn về sau khi nối POS."
           if tong == 0 and not any(loc.get(k) for k in
                                    ("q", "status", "order_type", "effort",
                                     "ads", "nv", "nv_pos", "page", "ky",
                                     "tu", "den"))
           else "Không có đơn nào khớp bộ lọc — thử bỏ bớt điều kiện.")
        + "</td></tr>")
    pham_vi = (
        '<p class="note dh-scope">🔒 Bạn đang xem <b>đơn mình phụ trách</b> '
        "(cần quyền <code>revenue.view</code> để xem toàn bộ). Đơn đổ từ POS "
        "chưa gắn được nhân viên CRM nên phần lớn sẽ không hiện ở đây — dùng ô "
        "lọc <b>Nhân viên POS</b> ở màn của quản lý để tra.</p>"
        if data["chi_don_cua_toi"] else "")
    body = (
        _the_chi_so(cs)
        + _dai_loc(loc, nhan_vien, nv_pos, pages, ky_luong, co_xuat)
        # Form POST bọc cả bảng: tích chọn đơn rồi xuất đúng những đơn đã tích.
        + f'<form method="post" action="{_TRANG}/xuat" id="dh-form">'
        + f'<input type="hidden" name="ca_bo_loc" id="dh-ca-bo-loc" value="0">'
        + "".join(f'<input type="hidden" name="{k}" value="{escape(str(v))}">'
                  for k, v in loc.items() if v not in ("", None, 0))
        + '<div class="kh-card">'
        + _thanh_tong(cs, tong, dau, len(rows))
        + f'<div class="kh-tblwrap"><table class="kh-tbl dh-tbl"><thead><tr>{cot}'
          f"</tr></thead><tbody>{than}</tbody></table></div>"
        + _chan(loc, data["trang"], data["so_trang"])
        + "</div>"
        + _thanh_noi(tong, co_xuat)
        + "</form>"
        + pham_vi
        + '<p class="note">Đơn đồng bộ từ Pancake POS — màn này <b>chỉ đọc</b>. '
          'Bấm mã đơn để mở đơn bên POS, bấm tên khách để mở hồ sơ 360°.</p>'
        + '<div class="kh-toast"></div>'
    )
    return render_shell(
        "Đơn hàng", "crm-orders", body,
        heading="Đơn hàng",
        sub="Màn 21 — đồng bộ từ POS &amp; Pancake · chỉ đọc",
        script=_JS,
    )


# Tích chọn GIỮ QUA CÁC TRANG (sessionStorage) + hai lưới chọn cột đồng bộ
# nhau + nhớ bộ cột đã chọn. Chạy lại được nhiều lần: shell nạp lại script sau
# mỗi lượt điều hướng PJAX nên mọi thứ phải dựng từ DOM hiện tại, không giữ
# biến toàn cục giữa hai lần chạy.
_JS = """
(function(){
  var form = document.getElementById('dh-form');
  if (!form) return;
  var KHO = 'dh_tick', KHO_COT = 'dh_cot_v1';
  var bar = document.getElementById('dh-bar');
  var demO = document.getElementById('dh-dem');
  var khacO = document.getElementById('dh-khac');
  var caO = document.getElementById('dh-ca-bo-loc');
  // Tổng đơn khớp bộ lọc — server đóng dấu vào data-tong của thanh nổi, JS chỉ
  // đọc lại. Không nội suy số vào chuỗi JS (số 53.651 lọt vào code là vỡ cú pháp).
  var TONG = parseInt(bar.getAttribute('data-tong') || '0', 10);

  function oTich(){ return form.querySelectorAll('.dh-tick'); }
  function kho(){ try{ var a=JSON.parse(sessionStorage.getItem(KHO)||'[]');
                       return Array.isArray(a)?a:[]; }catch(e){ return []; } }
  function luu(a){ try{ sessionStorage.setItem(KHO, JSON.stringify(a)); }catch(e){} }
  // Đồng bộ kho theo ĐÚNG trang đang xem — không đụng id của trang khác.
  function dongBoTrang(){
    var giu = kho();
    oTich().forEach(function(x){
      var v = String(x.value), i = giu.indexOf(v);
      if (x.checked) { if (i < 0) giu.push(v); } else if (i >= 0) giu.splice(i,1);
    });
    luu(giu);
  }
  function veThanh(){
    var ca = caO.value === '1';
    var tren = form.querySelectorAll('.dh-tick:checked').length;
    var n = ca ? TONG : kho().length;
    demO.textContent = n.toLocaleString('vi-VN');
    var khac = ca ? 0 : Math.max(0, n - tren);
    khacO.textContent = khac ? ('+' + khac.toLocaleString('vi-VN') + ' ở trang khác') : '';
    khacO.style.display = khac ? 'inline-flex' : 'none';
    bar.style.display = n > 0 ? 'flex' : 'none';
    var h = document.getElementById('dh-head');
    if (h && !ca) { var t = oTich().length;
                    h.checked = t > 0 && tren === t; }
    datCho();
  }
  // Thanh nổi: không đè menu trái, không tràn ngang, không che chân phân trang.
  function datCho(){
    var side = document.querySelector('.side');
    var l = (side ? Math.round(side.getBoundingClientRect().width) : 0) + 12;
    bar.style.setProperty('--dhL', l + 'px');
    bar.style.setProperty('--dhMax', 'calc(100vw - ' + (l + 12) + 'px)');
    var c = document.querySelector('.content');
    if (c) c.style.paddingBottom = (bar.style.display === 'flex'
                                    ? (bar.offsetHeight + 34) : 24) + 'px';
  }
  window.dhTick = function(){ caO.value='0'; dongBoTrang(); veThanh(); };
  window.dhTickTrang = function(a){ caO.value='0';
    oTich().forEach(function(x){ x.checked = a.checked; });
    dongBoTrang(); veThanh(); };
  window.dhChonCaBoLoc = function(){ caO.value='1';
    oTich().forEach(function(x){ x.checked = true; });
    var h=document.getElementById('dh-head'); if(h) h.checked=true;
    dongBoTrang(); veThanh(); };
  window.dhBoChon = function(){ caO.value='0';
    oTich().forEach(function(x){ x.checked = false; });
    var h=document.getElementById('dh-head'); if(h) h.checked=false;
    luu([]); veThanh(); };

  // ---- popover chọn cột (2 cái, luôn khớp nhau + nhớ lựa chọn) ----
  window.dhPop = function(e, id){
    if (e) e.stopPropagation();
    var p = document.getElementById(id); if (!p) return;
    var mo = p.classList.contains('on');
    document.querySelectorAll('.dh-pop.on').forEach(function(x){ x.classList.remove('on'); });
    if (!mo) p.classList.add('on');
  };
  window.dhTickCot = function(el){
    if (el) document.querySelectorAll('.dh-col[value="'+el.value+'"]')
              .forEach(function(x){ x.checked = el.checked; });
    var thay = {}, a = [];
    document.querySelectorAll('.dh-col').forEach(function(x){
      if (!thay[x.value]) { thay[x.value] = 1; if (x.checked) a.push(x.value); } });
    try { localStorage.setItem(KHO_COT, JSON.stringify(a)); } catch(e){}
    document.querySelectorAll('.dh-n').forEach(function(n){ n.textContent = a.length; });
    return a;
  };
  window.dhChonCot = function(bat){
    document.querySelectorAll('.dh-col').forEach(function(x){ x.checked = !!bat; });
    dhTickCot();
  };
  window.dhTruocKhiXuat = function(){
    var n = caO.value === '1' ? TONG : kho().length;
    if (!n) { alert('Chưa chọn đơn nào.'); return false; }
    if (!dhTickCot().length) { alert('Tích ít nhất 1 cột để xuất.'); return false; }
    return true;
  };
  // Nút ở dải lọc: xuất TOÀN BỘ khớp bộ lọc — ô tích không có name nên tự dựng URL.
  window.dhXuatLoc = function(){
    var sel = dhTickCot();
    if (!sel.length) { alert('Tích ít nhất 1 cột để xuất.'); return false; }
    var u = new URL(location.href);
    u.pathname = u.pathname.replace(/\\/?$/, '') + '/xuat';
    u.searchParams.delete('cols');
    sel.forEach(function(v){ u.searchParams.append('cols', v); });
    document.querySelectorAll('.dh-pop.on').forEach(function(x){ x.classList.remove('on'); });
    location.href = u.toString();
    return false;
  };
  document.addEventListener('click', function(e){
    if (!e.target.closest('.dh-wrap'))
      document.querySelectorAll('.dh-pop.on').forEach(function(x){ x.classList.remove('on'); });
  }, true);

  // ---- nạp lại: tích đã lưu + bộ cột đã chọn + bơm id của trang khác khi gửi ----
  var giu = kho();
  if (giu.length) oTich().forEach(function(x){
    if (giu.indexOf(String(x.value)) >= 0) x.checked = true; });
  try {
    var cs = JSON.parse(localStorage.getItem(KHO_COT) || 'null');
    if (Array.isArray(cs) && cs.length)
      document.querySelectorAll('.dh-col').forEach(function(x){
        x.checked = cs.indexOf(x.value) >= 0; });
  } catch(e){}
  dhTickCot(); veThanh();
  form.addEventListener('submit', function(){
    if (caO.value === '1') return;          // cả bộ lọc → server tự truy vấn
    form.querySelectorAll('input.dh-ma-o').forEach(function(g){ g.remove(); });
    var co = {}; oTich().forEach(function(x){ co[String(x.value)] = 1; });
    kho().forEach(function(v){
      if (co[v]) return;                    // id này đã có ô tích trên trang
      var i = document.createElement('input');
      i.type='hidden'; i.name='ids'; i.value=v; i.className='dh-ma-o';
      form.appendChild(i);
    });
  });
  window.addEventListener('resize', datCho);

  // Bấm số điện thoại là chép — dùng chung toast của màn Khách hàng.
  var toast = document.querySelector('.kh-toast'), hen;
  document.querySelectorAll('.kh-tel').forEach(function(nut){
    nut.addEventListener('click', function(){
      var so = nut.getAttribute('data-so') || '';
      if (!toast) return;
      var xong = function(chu){ toast.textContent = chu; toast.classList.add('on');
        clearTimeout(hen); hen = setTimeout(function(){ toast.classList.remove('on'); }, 1600); };
      if (!navigator.clipboard) { xong('Trình duyệt không cho chép — ' + so); return; }
      navigator.clipboard.writeText(so).then(function(){ xong('Đã chép số ' + so); },
                                             function(){ xong('Không chép được — ' + so); });
    });
  });
})();
"""
