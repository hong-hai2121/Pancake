"""Màn nhóm ƯU ĐÃI — Voucher + Hạng thẻ (C1, port từ mẫu Kallet).

Nguồn mẫu: `voucher.php` (theo dõi voucher đã tặng) và `hang-the.php` (toàn
cảnh hạng thành viên). Giữ nguyên bố cục mẫu:

  Voucher : 4 ô số bấm-để-lọc → dải lọc → bảng → phân trang
  Hạng thẻ: dải cột hạng → khối "giảm quyền lợi ngầm" → bảng ngưỡng → quyền lợi

Luật giao diện của mẫu được tôn trọng nguyên vẹn: **màu không bao giờ đứng một
mình** (luôn kèm chữ/icon), và **ngưỡng chưa điền hiện chữ "chưa điền" màu cam
chứ không phải số 0** — 0 làm người dùng tưởng đã cấu hình xong.
"""

from html import escape
from urllib.parse import quote

from app.services import voucher_service as svc
from app.web.shell import _icon, render_shell


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _d(v) -> str:
    return v.strftime("%d/%m/%Y") if v else "—"


def _so(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".")


def _tien_gon(n) -> str:
    """Tiền rút gọn kiểu mẫu: >=1tr → '1,2tr' · còn lại → '50k'."""
    try:
        v = float(n or 0)
    except (TypeError, ValueError):
        return "0k"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}".replace(".", ",") + "tr"
    return f"{round(v / 1000)}k"


def _tien(n) -> str:
    try:
        return f"{float(n or 0):,.0f} ₫".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _url(loc: dict, **doi) -> str:
    tham = dict(loc)
    tham.update(doi)
    cai = [(k, v) for k, v in tham.items()
           if v not in ("", None, 0) and not (k == "trang" and v == 1)]
    duoi = "&".join(f"{k}={quote(str(v))}" for k, v in cai)
    return "/crm/voucher" + (f"?{duoi}" if duoi else "")


# ------------------------------------------------------------------ VOUCHER
# (mã trạng thái, nhãn ô lọc) — thứ tự theo mẫu, KHÔNG đổi mã DB
_TT_LOC = [
    ("", "Tất cả tình trạng"),
    ("con_han", "Còn hạn"),
    ("da_dung", "Đã dùng"),
    ("het_han_khong_dung", "Hết hạn không dùng"),
    ("da_tra_lai", "Đã trả lại"),
    ("chua_bao_ma", "Chưa báo mã"),
]


def _chon(ten: str, muc: list[tuple[str, str]], dang_chon) -> str:
    o = "".join(
        f'<option value="{escape(str(ma))}"'
        f'{" selected" if str(dang_chon or "") == str(ma) else ""}>'
        f"{escape(nhan)}</option>" for ma, nhan in muc)
    return f'<select name="{ten}" onchange="this.form.requestSubmit()">{o}</select>'


def _o_so(so: dict, loc: dict) -> str:
    """4 ô số đầu màn. Bấm ô = lọc theo trạng thái đó, bấm lại thì bỏ lọc.

    Ô "tiền đã phát" KHÔNG lọc được (không phải một trạng thái) nên vẽ thành
    thẻ tĩnh, tách rõ phần máy tặng và phần người tặng."""
    tong = float(so.get("tien_tong") or 0)
    may = float(so.get("tien_may") or 0)
    o = [
        ("con_han", _so(so.get("con_han")), "Đang còn hạn", "#2EAD6E", "", False),
        ("da_dung", _so(so.get("da_dung")), "Đã dùng", "#4E7FE8", "", False),
        ("", _tien_gon(tong), "Tiền đã phát", "#a8718f",
         f"🤖 {_tien_gon(may)} · 👤 {_tien_gon(tong - may)}", False),
        ("chua_bao_ma", _so(so.get("chua_bao_ma")), "CHƯA BÁO CHO KHÁCH",
         "#C25E00", "việc cần làm", True),
    ]
    ra = ""
    for ma, gia_tri, nhan, mau, phu, canh in o:
        bat = ma and (loc.get("tt") or "") == ma
        ruot = (f'<span class="vc-vach" style="background:{mau}"></span>'
                f'<div class="vc-num" style="color:{mau}">{escape(gia_tri)}</div>'
                f'<div class="vc-lbl">{escape(nhan)}</div>'
                f'<div class="vc-sub">{escape(phu) if phu else "&nbsp;"}</div>')
        lop = "vc-tile" + (" warn" if canh else "") + (" on" if bat else "")
        if ma:
            href = _url(loc, tt="" if bat else ma, trang=1)
            ra += (f'<a class="{lop}" style="--c:{mau}" '
                   f'href="{escape(href)}">{ruot}</a>')
        else:
            ra += f'<div class="{lop}" style="--c:{mau}">{ruot}</div>'
    return f'<div class="vc-tiles">{ra}</div>'


def _dai_loc(loc: dict, nhan_vien: list[dict], tong: int) -> str:
    nv = [("", "Tất cả nhân viên")] + [(str(u["id"]), u["name"] or f'#{u["id"]}')
                                       for u in (nhan_vien or [])]
    co_loc = any(loc.get(k) for k in ("tt", "kw", "by", "nv"))
    return (
        '<form class="kh-filters" id="vc-loc" method="get" action="/crm/voucher">'
        f'<label class="kh-find">{_icon("search")}'
        f'<input name="kw" value="{escape(loc.get("kw") or "")}" '
        'placeholder="Mã voucher · tên khách · số điện thoại…"></label>'
        + _chon("tt", _TT_LOC, loc.get("tt"))
        + _chon("by", [("", "Máy & Người tặng"), ("may", "🤖 Máy tặng"),
                       ("nguoi", "👤 Người tặng")], loc.get("by"))
        + _chon("nv", nv, loc.get("nv"))
        + '<button class="kh-btn go">🔍 Lọc</button>'
        + (f'<a class="kh-clear" href="/crm/voucher">{_icon("filter-x")}'
           "Xoá lọc</a>" if co_loc else
           f'<span class="kh-clear off">{_icon("filter-x")}Xoá lọc</span>')
        + '<span class="kh-sp"></span>'
        + f'<span class="cnt">{_so(tong)} voucher</span>'
        "</form>"
    )


def _form_tang(mo: bool, loi: str = "", gia_tri: dict | None = None) -> str:
    """Form "Tạo & tặng voucher". Chỉ hiện khi bấm nút hoặc khi vừa lỗi —
    lỗi mà ẩn form đi thì người dùng mất luôn thứ vừa gõ."""
    if not mo:
        return ""
    g = gia_tri or {}
    han = svc.han_mac_dinh()
    return (
        '<form class="vc-form" method="post" action="/crm/voucher/tang">'
        '<div class="vc-form-t">Tạo &amp; tặng voucher</div>'
        '<div class="vc-form-r">'
        '<label>SĐT khách (bắt buộc)'
        f'<input name="sdt" required value="{escape(g.get("sdt") or "")}" '
        'placeholder="0xxxxxxxxx"></label>'
        '<label>Mệnh giá (đ)'
        f'<input name="menh_gia" inputmode="numeric" required '
        f'value="{escape(g.get("menh_gia") or "")}"></label>'
        '<label>Mã (trống = báo sau)'
        f'<input name="ma" style="text-transform:uppercase" '
        f'value="{escape(g.get("ma") or "")}"></label>'
        f'<label style="flex:0 1 110px">Hạn (ngày)'
        f'<input type="number" name="han_ngay" min="1" value="{han}"></label>'
        '<label style="flex:2 1 180px">Ghi chú'
        f'<input name="ghi_chu" value="{escape(g.get("ghi_chu") or "")}"></label>'
        '<button class="kh-btn go" type="submit">Tặng</button>'
        '<a class="kh-clear" href="/crm/voucher">Huỷ</a>'
        "</div>"
        '<p class="note" style="margin:9px 0 0">Chỉ tặng được cho khách ĐÃ CÓ '
        "trong hệ thống (khớp theo SĐT). Voucher ghi loại “người tặng” gắn tên "
        "bạn; hệ thống <b>không gửi tin</b> cho khách — báo mã là việc của bạn."
        "</p></form>"
    )


def _hang_voucher(v: dict, co_sua: bool) -> str:
    st = svc.trang_thai_hien_thi(v)
    may = v.get("granted_by_kind") == "may"
    ai = ("🤖 Máy" if may else "👤 " + (v.get("granted_by_name") or "—"))
    mau_ai = "#4E7FE8" if may else "#a8718f"
    ma = (f'<button type="button" class="vc-ma" data-ma="{escape(v["code"])}" '
          f'title="Bấm để chép mã">{escape(v["code"])}{_icon("copy")}</button>'
          if v.get("code") else
          '<span class="kh-none">chưa có mã</span>')
    lech = ('<span class="vc-lech" title="POS giảm khác mệnh giá — cần soi lại. '
            f'POS giảm {_tien(v.get("pos_discount"))}">❓</span>'
            if svc.lech_tien(v) else "")
    thao_tac = ""
    if co_sua:
        if v.get("status") == "chua_bao_ma":
            thao_tac = (
                '<form method="post" class="vc-inline" '
                f'action="/crm/voucher/{v["id"]}/bao-ma">'
                '<input name="ma" placeholder="Nhập mã đã báo" required '
                'style="text-transform:uppercase">'
                '<button class="kh-btn go" type="submit">Lưu mã</button></form>')
        elif v.get("status") in ("con_han",):
            thao_tac = (
                '<form method="post" class="vc-inline" '
                f'action="/crm/voucher/{v["id"]}/trang-thai">'
                '<input type="hidden" name="trang_thai" value="da_dung">'
                '<button class="kh-btn" type="submit">Đánh dấu đã dùng</button>'
                "</form>")
    return (
        "<tr>"
        f"<td>{ma}</td>"
        f'<td><a class="kh-name" href="/crm/khach-hang/{v["customer_id"]}">'
        f'{escape(v.get("customer_name") or "(chưa có tên)")}</a>'
        f'<div class="kh-sub">{_e(v.get("customer_phone"))}</div></td>'
        f'<td class="money">{_tien_gon(v.get("amount"))}</td>'
        f'<td><span style="font-size:11px;font-weight:600;color:{mau_ai}">'
        f"{escape(ai)}</span></td>"
        f'<td class="kh-nho">{_d(v.get("granted_on"))} → {_d(v.get("expires_on"))}</td>'
        f'<td><span class="kh-st" style="background:{st["nen"]};color:{st["mau"]}">'
        f'{escape(st["chu"])}</span>{lech}</td>'
        f'<td style="text-align:right">{thao_tac}</td>'
        "</tr>"
    )


def _chan(loc: dict, tong: int, trang: int, so_trang: int) -> str:
    lui, tien = _url(loc, trang=trang - 1), _url(loc, trang=trang + 1)
    return (
        '<div class="kh-foot"><div>Hiển thị 30 voucher / trang</div>'
        '<div style="display:flex;align-items:center;gap:10px">'
        f"<span>Trang {trang} / {so_trang}</span><div class=\"kh-pager\">"
        + (f'<a class="kh-pg" href="{escape(lui)}" aria-label="Trang trước">'
           f'{_icon("chevron-left")}</a>' if trang > 1 else
           f'<span class="kh-pg off">{_icon("chevron-left")}</span>')
        + (f'<a class="kh-pg" href="{escape(tien)}" aria-label="Trang sau">'
           f'{_icon("chevron-right")}</a>' if trang < so_trang else
           f'<span class="kh-pg off">{_icon("chevron-right")}</span>')
        + "</div></div></div>"
    )


_VC_JS = """
(function(){
  document.querySelectorAll('.vc-ma').forEach(function(b){
    b.addEventListener('click', function(){
      var ma = b.getAttribute('data-ma') || '';
      if (navigator.clipboard) navigator.clipboard.writeText(ma);
      var cu = b.getAttribute('title');
      b.setAttribute('title', 'Đã chép ' + ma);
      setTimeout(function(){ b.setAttribute('title', cu || ''); }, 1600);
    });
  });
})();
"""


def render_voucher(rows: list[dict], tong: int, *, so: dict, loc: dict,
                   nhan_vien: list[dict], user: dict,
                   mo_form: bool = False, flash: str = "", loi: str = "",
                   gia_tri: dict | None = None) -> str:
    """Màn Voucher — theo dõi voucher đã tặng, máy và người tặng tách riêng."""
    from app.core.deps import co_quyen

    co_tang = co_quyen(user, "voucher.grant")
    trang = int(loc.get("trang") or 1)
    so_trang = max(1, -(-tong // 30))
    dau = (trang - 1) * 30
    than = "".join(_hang_voucher(v, co_tang) for v in rows) or (
        '<tr><td colspan="7" class="rong">Chưa có voucher nào khớp bộ lọc. '
        "Voucher tặng qua màn này hoặc do automation phát đều hiện ở đây."
        "</td></tr>")
    bao = ""
    if flash:
        bao = f'<div class="flash ok">{escape(flash)}</div>'
    elif loi:
        bao = f'<div class="flash err">{escape(loi)}</div>'
    body = (
        bao
        + _form_tang(mo_form or bool(loi), loi, gia_tri)
        + _o_so(so, loc)
        + _dai_loc(loc, nhan_vien, tong)
        + '<div class="kh-card"><div class="kh-head">'
        + f'<span class="cnt">Đang xem {dau + 1 if rows else 0}–'
        + f"{dau + len(rows)} / {_so(tong)} voucher</span></div>"
        + '<div class="kh-tblwrap"><table class="kh-tbl"><thead><tr>'
          "<th>Mã</th><th>Khách</th><th class=\"num\">Mệnh giá</th>"
          "<th>Ai tặng</th><th>Ngày tặng → hạn</th><th>Tình trạng</th>"
          '<th style="text-align:right">Thao tác</th>'
          f"</tr></thead><tbody>{than}</tbody></table></div>"
        + _chan(loc, tong, trang, so_trang)
        + "</div>"
        + '<p class="note" style="margin-top:10px">⚠️ Khách còn voucher hiệu '
          "lực thì <b>mọi mốc chăm chuẩn tạm tắt</b>, chỉ giữ mốc nhắc hạn "
          "voucher — tránh nhắn chồng lên nhau. Xem bậc thang hạng thẻ ở "
          '<a href="/crm/hang-the">Hạng thẻ</a>.</p>'
    )
    nut = ('<a class="kh-btn go" href="/crm/voucher?tang=1">🎟️ Tạo &amp; tặng '
           "voucher</a>" if co_tang else "")
    return render_shell(
        "Voucher", "crm-voucher", body,
        heading="Voucher",
        sub="Theo dõi voucher đã tặng · máy và người tặng tách riêng",
        actions=nut, script=_VC_JS,
    )


# ----------------------------------------------------------------- HẠNG THẺ
def _cot_hang(data: dict) -> str:
    """Dải cột hạng + ô "Chưa xếp hạng" (hạng thứ 6, viền đứt cho khác hẳn)."""
    ra = ""
    for h in data["bac"]:
        mat = h["mat"]
        icon = (h.get("emoji") or "").strip() or mat["icon"]
        n = data["dem"].get(h["code"], 0)
        ra += (f'<a class="ht-cot" style="background:{mat["nen"]}" '
               f'href="/crm/khach-hang?tier={escape(h["code"])}">'
               f'<div class="ic">{escape(icon)}</div>'
               f'<div class="n" style="color:{mat["mau"]}">{_so(n)}</div>'
               f'<div class="l" style="color:{mat["mau"]}">'
               f'{escape(h["name"])}</div></a>')
    ra += ('<a class="ht-cot chua" href="/crm/khach-hang?tier=chua_xep">'
           '<div class="ic">⬜</div>'
           f'<div class="n">{_so(data["chua_xep"])}</div>'
           '<div class="l">Chưa xếp hạng</div></a>')
    return f'<div class="ht-cots">{ra}</div>'


def _khoi_giam(data: dict) -> str:
    """Khối "giảm quyền lợi ngầm" — chép nguyên luật + cảnh báo KHÔNG báo khách."""
    chip = ""
    for h in data["bac"]:
        mat = h["mat"]
        icon = (h.get("emoji") or "").strip() or mat["icon"]
        thap = data["thap_hon"].get(h["code"])
        toi = f"như {thap}" if thap else "giữ nguyên (đáy thang)"
        chip += (f'<span class="ht-chip">{escape(icon)} '
                 f'<b>{escape(h["name"])}</b> → {escape(toi)}</span>')
    chip += ('<span class="ht-chip off">⬜ Chưa xếp hạng — bỏ qua</span>')
    return (
        '<div class="ht-warn"><div class="ht-warn-h">'
        f'⚠️ <b>{_so(data["giam_quyen_loi"])} khách</b> đang bị giảm quyền lợi '
        "ngầm"
        '<a class="kh-btn" href="/crm/khach-hang?tt=sleep">Xem danh sách</a>'
        "</div>"
        f'<p>Khách <b>{data["ngay_giam"]} ngày</b> không nhận hàng: '
        "<b>hạng hiển thị giữ nguyên</b>, nhưng hưởng quyền lợi "
        "<b>thấp hơn 1 bậc</b>. Mua lại là khôi phục ngay.</p>"
        '<p class="ht-cam">🔕 KHÔNG gửi tin thông báo cho khách — đây là luật '
        "ngầm nội bộ.</p>"
        f'<div class="ht-chips">{chip}</div></div>'
    )


def _bang_nguong(data: dict, co_sua: bool) -> str:
    """Bảng ngưỡng. Ngưỡng chưa điền hiện chữ "chưa điền" màu cam — KHÔNG phải 0."""
    dong = ""
    for h in data["bac"]:
        mat = h["mat"]
        icon = (h.get("emoji") or "").strip() or mat["icon"]
        if co_sua:
            gia_tri = "" if h["min_spent"] is None else f'{float(h["min_spent"]):.0f}'
            o = (f'<input class="ht-in num" type="number" min="0" step="1000" '
                 f'name="nguong" value="{gia_tri}" placeholder="chưa điền">')
            nut = '<button class="kh-btn" type="submit">Lưu</button>'
            o = (f'<form class="ht-row-f" method="post" '
                 f'action="/crm/hang-the/nguong">'
                 f'<input type="hidden" name="ma" value="{escape(h["code"])}">'
                 f"{o}{nut}</form>")
        else:
            o = (f'<span class="ht-in num">'
                 + (f'{float(h["min_spent"]):,.0f}'.replace(",", ".")
                    if h["min_spent"] is not None
                    else '<i class="ht-chua">chưa điền</i>') + "</span>")
        dong += (f'<div class="ht-row"><span class="ic">{escape(icon)}</span>'
                 f'<span class="ten">{escape(h["name"])}</span>'
                 f'<span class="tu">từ</span>{o}'
                 f'<span class="mo">đ · {escape(h["mo_ta_nguong"])}</span></div>')
    return f'<div class="ht-rows">{dong}</div>'


def _quyen_loi(data: dict) -> str:
    ql = data["quyen_loi"]
    if not any(ql.values()):
        return ('<p class="note">Chưa khai quyền lợi cho hạng nào. Chạy '
                "<code>python scripts/seed_uu_dai.py</code> để nạp bộ mẫu, "
                "rồi sửa cho khớp chính sách thật.</p>")
    ra = ""
    for h in data["bac"]:
        mat = h["mat"]
        icon = (h.get("emoji") or "").strip() or mat["icon"]
        ds = ql.get(h["code"]) or []
        the = "".join(
            f'<span class="ht-ql" style="background:{mat["nen"]}">'
            f'<b style="color:{mat["mau"]}">{escape(b["benefit_key"])}</b>'
            + (f' · {escape(b["benefit_value"])}' if b["benefit_value"] else "")
            + "</span>" for b in ds
        ) or '<span class="kh-none">— chưa khai quyền lợi —</span>'
        ra += (f'<div class="ht-qlrow"><div class="ten" '
               f'style="color:{mat["mau"]}">{escape(icon)} '
               f'{escape(h["name"])}</div><div class="ds">{the}</div></div>')
    return ra


def render_hang_the(data: dict, user: dict, *, flash: str = "") -> str:
    """Màn Hạng thẻ — toàn cảnh hạng thành viên, tính theo tổng chi tiêu."""
    from app.core.deps import co_quyen

    co_sua = co_quyen(user, "user.manage")
    khung = ('<div class="flash warn">Bảng <b>card_ranks</b> chưa có dữ liệu — '
             "đang hiện khung 5 hạng chuẩn. Chạy "
             "<code>python scripts/seed_uu_dai.py</code> để nạp ngưỡng."
             "</div>" if data.get("la_khung") else "")
    nut_tinh = ""
    if co_sua and not data.get("la_khung"):
        nut_tinh = (
            '<form method="post" action="/crm/hang-the/tinh-lai" '
            'onsubmit="return confirm(\'Xếp lại hạng cho '
            f'{_so(data["tong_khach"])} khách theo tổng chi tiêu hiện tại?'
            "\\n\\nCHỈ LÊN hạng — không ai bị tụt xuống.')\">"
            '<button class="kh-btn go" type="submit">Tính lại hạng</button>'
            "</form>")
    body = (
        (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + khung
        + _cot_hang(data)
        + _khoi_giam(data)
        + '<div class="kh-card" style="padding:16px 18px">'
        + '<div class="ht-h">Ngưỡng từng hạng' + nut_tinh + "</div>"
        + _bang_nguong(data, co_sua)
        + '<p class="note" style="margin-top:12px">Ngưỡng là <b>tổng tiền các '
          "đơn đã giao thành công</b>. Đổi ngưỡng xong phải bấm <b>Tính lại "
          "hạng</b> mới áp cho khách cũ; khách mới thì tính lúc đơn giao xong."
          "</p></div>"
        + '<div class="kh-card" style="padding:16px 18px;margin-top:14px">'
        + '<div class="ht-h">🎁 Quyền lợi từng hạng</div>'
        + _quyen_loi(data)
        + '<p class="note" style="margin-top:10px">Khai quyền lợi theo <b>bậc '
          "so sánh được</b> — đó là nền cho luật giảm quyền lợi ngầm ở khối "
          "trên (tụt 1 bậc chứ không phải mất hết).</p></div>"
    )
    return render_shell(
        "Hạng thẻ", "crm-rank", body,
        heading="Hạng thẻ",
        sub="Toàn cảnh hạng thành viên · tính theo tổng chi tiêu",
    )
