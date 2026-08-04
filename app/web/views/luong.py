"""Màn nhóm TIỀN — Thu nhập của tôi · Lương thưởng · Đối soát (C2).

Nguồn mẫu: `luong.php` (thu nhập của CHÍNH mình) · `luong-thuong.php` (bảng
lương toàn đội) · `doi-soat.php` (duyệt thưởng chăm sóc theo 3 rổ).

Hai điểm giao diện của mẫu được giữ nguyên vì chúng chống hiểu nhầm về TIỀN:

  * Mọi con số doanh thu **ghi rõ "lên đơn" hay "đã thu"** — hai số này khác
    nhau và người xem luôn hỏi "sao lệch?" nếu không nói rõ.
  * Khoản thưởng nào cũng **tra ngược được**: bấm ra danh sách ngày/đơn sinh
    ra nó. Số tiền mà nhân viên không tự kiểm được là số gây cãi nhau.
"""

from html import escape
from urllib.parse import quote

from app.web.shell import _icon, render_shell

_THANG_VI = ["", "Một", "Hai", "Ba", "Tư", "Năm", "Sáu", "Bảy", "Tám", "Chín",
             "Mười", "Mười Một", "Mười Hai"]


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _tien(n) -> str:
    try:
        return f"{float(n or 0):,.0f} ₫".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _tien_gon(n) -> str:
    """>=1tr → '1,2 tr' · còn lại → '750k' (kiểu mẫu)."""
    try:
        v = float(n or 0)
    except (TypeError, ValueError):
        return "0k"
    am = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000:
        s = f"{v / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{am}{s}".replace(".", ",") + " tr"
    return f"{am}{round(v / 1000):,}k".replace(",", ".")


def _ky_vi(ky: str) -> str:
    try:
        nam, thang = int(ky[:4]), int(ky[5:])
        return f"Tháng {_THANG_VI[thang]} {nam}"
    except (ValueError, IndexError):
        return ky


def _chon_ky(ky: str, cac_ky: list[str], duong_dan: str) -> str:
    """Ô chọn kỳ. Kỳ hiện tại luôn có mặt kể cả khi chưa ai chốt lương."""
    ds = list(dict.fromkeys([ky, *cac_ky]))
    o = "".join(f'<option value="{escape(k)}"{" selected" if k == ky else ""}>'
                f"{escape(_ky_vi(k))}</option>" for k in ds)
    return (f'<form method="get" action="{escape(duong_dan)}" class="kh-filters" '
            'style="margin:0">'
            f'<select name="ky" onchange="this.form.requestSubmit()">{o}</select>'
            "</form>")


def _o(nhan: str, gia_tri: str, phu: str = "", mau: str = "",
       href: str = "") -> str:
    ruot = (f'<span class="vc-vach" style="background:{mau or "var(--accent)"}">'
            "</span>"
            f'<div class="vc-num" style="color:{mau or "var(--accent)"}">'
            f"{escape(gia_tri)}</div>"
            f'<div class="vc-lbl">{escape(nhan)}</div>'
            f'<div class="vc-sub">{phu or "&nbsp;"}</div>')
    if href:
        return f'<a class="vc-tile" href="{escape(href)}">{ruot}</a>'
    return f'<div class="vc-tile">{ruot}</div>'


# ------------------------------------------------- Thu nhập của tôi (luong.php)
def _thanh_muc_tieu(net: float, muc_tieu: float) -> str:
    if muc_tieu <= 0:
        return ""
    pct = min(100, round(net / muc_tieu * 100))
    thieu = max(0, muc_tieu - net)
    return (
        '<div class="lg-goal"><div class="lg-goal-h">'
        f"<span>Mục tiêu tháng: <b>{_tien_gon(muc_tieu)}</b></span>"
        f'<span class="num">{pct}%</span></div>'
        f'<div class="lg-bar"><i style="width:{pct}%"></i></div>'
        + (f'<div class="note">Còn thiếu <b>{_tien_gon(thieu)}</b> nữa là đạt.'
           "</div>" if thieu else
           '<div class="note ok">🎉 Đã đạt mục tiêu tháng này.</div>')
        + "</div>"
    )


def _khoi_thuong_nong(ct: dict) -> str:
    """Giải thích thưởng nóng — bày cả HAI kiểu để thấy rõ chúng cộng dồn."""
    if not ct or not (ct["theo_ngay"] or ct["theo_don"]):
        return ('<p class="note">Chưa có khoản thưởng nóng nào trong kỳ. '
                "Bậc thưởng cấu hình ở <b>Quản trị → Bậc lương</b>.</p>")
    ngay = "".join(
        f'<tr><td>{x["ngay"].strftime("%d/%m/%Y")}</td>'
        f'<td class="money">{_tien(x["doanh_thu"])}</td>'
        f'<td class="money">≥ {_tien_gon(x["nguong"])}</td>'
        f'<td class="money">+{_tien(x["thuong"])}</td></tr>'
        for x in ct["theo_ngay"])
    don = "".join(
        f'<tr><td>{escape(str(x["ma_don"] or x["order_id"]))}</td>'
        f'<td class="money">{_tien(x["gia_tri"])}</td>'
        f'<td class="money">≥ {_tien_gon(x["nguong"])}</td>'
        f'<td class="money">+{_tien(x["thuong"])}</td></tr>'
        for x in ct["theo_don"])
    ra = ('<p class="note">Hai kiểu thưởng nóng chạy <b>song song</b> và '
          "<b>cộng dồn</b> — một đơn to trong một ngày to thì ăn cả hai.</p>")
    if ngay:
        ra += ('<h4 class="lg-h4">Theo doanh thu NGÀY</h4>'
               '<div class="kh-tblwrap"><table class="kh-tbl"><thead><tr>'
               '<th>Ngày</th><th class="num">Doanh thu ngày</th>'
               '<th class="num">Ngưỡng</th><th class="num">Thưởng</th>'
               f"</tr></thead><tbody>{ngay}</tbody></table></div>")
    if don:
        ra += ('<h4 class="lg-h4">Theo giá trị TỪNG ĐƠN</h4>'
               '<div class="kh-tblwrap"><table class="kh-tbl"><thead><tr>'
               '<th>Đơn</th><th class="num">Giá trị đơn</th>'
               '<th class="num">Ngưỡng</th><th class="num">Thưởng</th>'
               f"</tr></thead><tbody>{don}</tbody></table></div>")
    return ra


def _bang_don(rows: list[dict]) -> str:
    if not rows:
        return ('<p class="note">Chưa có đơn nào tính vào kỳ này.</p>')
    than = ""
    for o in rows:
        truc = ("💚 Chăm sóc" if o["effort_axis"] == "cham_soc"
                else ("📣 Quảng cáo" if o["ads_attributed"] else "🌱 Tự nhiên"))
        sua = (' <span class="lg-sua" title="Người đã sửa phân loại — máy thôi '
               'tự đổi">✎</span>' if o["classified_manually"] else "")
        duyet = {"duyet": '<span class="kh-st active">đã duyệt</span>',
                 "tu_choi": '<span class="kh-st sleep">bác</span>'}.get(
                     o.get("review_status"), '<span class="kh-none">chờ</span>')
        than += (
            "<tr>"
            f'<td>{_e(o["external_order_id"] or o["pos_order_id"] or o["id"])}</td>'
            f'<td><a class="kh-name" href="/crm/khach-hang/{o["customer_id"]}">'
            f'{_e(o["customer_name"])}</a></td>'
            f'<td class="money">{_tien(o["total_amount"])}</td>'
            f"<td>{truc}{sua}</td>"
            f'<td>{duyet if o["effort_axis"] == "cham_soc" else "—"}</td>'
            "</tr>")
    return ('<div class="kh-tblwrap"><table class="kh-tbl"><thead><tr>'
            '<th>Mã đơn</th><th>Khách</th><th class="num">Giá trị</th>'
            "<th>Phân loại</th><th>Thưởng chăm</th></tr></thead>"
            f"<tbody>{than}</tbody></table></div>")


def render_thu_nhap(data: dict, *, cac_ky: list[str], don: list[dict],
                    muc_tieu: float, flash: str = "", loi: str = "") -> str:
    """Màn "Thu nhập của tôi" — CHỈ xem của chính mình (không lộ lương người khác)."""
    ky = data["ky"]
    bao = (f'<div class="flash ok">{escape(flash)}</div>' if flash else
           (f'<div class="flash err">{escape(loi)}</div>' if loi else ""))
    khoa = ('<div class="flash warn">🔒 Kỳ này <b>đã chốt</b> — số liệu đóng '
            "băng. Sai lệch phát sinh sau sẽ ghi vào kỳ sau, không sửa ngược."
            "</div>" if data["dong_bang"] else "")
    bac = data.get("bac_hoa_hong")
    phu_hh = (f'bậc {_tien_gon(bac["min_revenue"])}+ · '
              + (f'{float(bac["value"]):g}%' if bac["kind"] == "phan_tram"
                 else _tien_gon(bac["value"]))
              if bac else "chưa cấu hình bậc")
    dc = data["dieu_chinh_chi_tiet"]
    dong_dc = "".join(
        f'<tr><td>{_e(r["reason"])}</td>'
        f'<td class="money" style="color:'
        f'{"var(--err)" if float(r["amount"]) < 0 else "var(--ok)"}">'
        f'{_tien(r["amount"])}</td></tr>' for r in dc)

    body = (
        bao + khoa
        + '<div class="lg-top">'
        + f'<div class="lg-net"><div class="lg-net-l">Thực nhận {_ky_vi(ky)}'
          "</div>"
          f'<div class="lg-net-v">{_tien(data["tong"])}</div>'
          f'<div class="lg-net-s">{data["so_don"]} đơn tính lương'
          + (f' · {data["so_don_hoan"]} đơn hoàn' if data["so_don_hoan"] else "")
          + "</div></div>"
        + _thanh_muc_tieu(float(data["tong"]), muc_tieu)
        + "</div>"
        + '<form class="lg-goal-f" method="post" action="/crm/thu-nhap/muc-tieu">'
          f'<input type="hidden" name="ky" value="{escape(ky)}">'
          "<label>Mục tiêu tháng (triệu)"
          f'<input type="number" name="trieu" min="1" max="999" '
          f'value="{round(muc_tieu / 1_000_000) or 9}"></label>'
          '<button class="kh-btn" type="submit">Lưu mục tiêu</button>'
          '<span class="note">Mục tiêu do BẠN tự đặt, quản lý không thấy.</span>'
          "</form>"
        + '<div class="vc-tiles">'
        + _o("Lương cứng", _tien_gon(data["luong_cung"]))
        + _o("Doanh thu LÊN ĐƠN", _tien_gon(data["len_don"]),
             "tổng giá trị đơn trong kỳ", "#4E7FE8")
        + _o("Doanh thu ĐÃ THU", _tien_gon(data["da_thu"]),
             "đơn đã giao/thu tiền", "#2EAD6E")
        + _o("Hoa hồng", _tien_gon(data["hoa_hong"]), escape(phu_hh), "#a8718f")
        + "</div>"
        + '<div class="vc-tiles">'
        + _o("Thưởng chăm sóc", _tien_gon(data["thuong_cham"]),
             "CỘNG THÊM vào hoa hồng", "#2EAD6E")
        + _o("Thưởng nóng", _tien_gon(data["thuong_nong"]),
             "2 kiểu cộng dồn", "#C25E00")
        + _o("Điều chỉnh", _tien_gon(data["dieu_chinh"]),
             f"{len(dc)} khoản" if dc else "không có",
             "var(--err)" if float(data["dieu_chinh"]) < 0 else "#4E7FE8")
        + _o("THỰC NHẬN", _tien_gon(data["tong"]), "đã gồm mọi khoản", "#7A308F")
        + "</div>"
        + '<div class="kh-card" style="padding:16px 18px">'
          '<div class="ht-h">🔥 Thưởng nóng — vì sao có khoản này</div>'
        + _khoi_thuong_nong(data.get("chi_tiet_thuong_nong") or {})
        + "</div>"
        + (('<div class="kh-card" style="padding:16px 18px;margin-top:14px">'
            '<div class="ht-h">Khoản điều chỉnh của kỳ</div>'
            '<div class="kh-tblwrap"><table class="kh-tbl"><thead><tr>'
            '<th>Lý do</th><th class="num">Số tiền</th></tr></thead>'
            f"<tbody>{dong_dc}</tbody></table></div>"
            '<p class="note">Số ÂM là truy thu: đơn hoàn/huỷ của kỳ TRƯỚC (kỳ '
            "đó đã chốt nên trừ sang đây).</p></div>") if dc else "")
        + '<div class="kh-card" style="padding:16px 18px;margin-top:14px">'
          '<div class="ht-h">Đơn tính vào kỳ này</div>'
        + _bang_don(don)
        + '<p class="note">Thấy đơn bị phân loại sai? Báo trưởng nhóm — sửa ở '
          "màn <b>Đối soát &amp; duyệt thưởng</b>, đổi phân loại thì tiền đi "
          "theo.</p></div>"
    )
    return render_shell(
        "Thu nhập của tôi", "crm-income", body,
        heading="Thu nhập của tôi",
        sub=f"{_ky_vi(ky)} · chỉ mình bạn xem được số này",
        actions=_chon_ky(ky, cac_ky, "/crm/thu-nhap"),
    )


# ------------------------------------------- Lương thưởng cả đội (luong-thuong)
def render_bang_luong(rows: list[dict], ky: str, *, cac_ky: list[str],
                      co_chot: bool, flash: str = "") -> str:
    tong = {k: sum(float(r[k] or 0) for r in rows) for k in
            ("base_salary", "commission", "care_bonus", "hot_bonus",
             "adjustment", "total", "revenue_booked", "revenue_collected")}
    da_chot = bool(rows) and all(r["frozen"] for r in rows)
    than = "".join(
        "<tr>"
        f'<td><a class="kh-name" href="/crm/thu-nhap?ky={quote(ky)}'
        f'&nv={r["user_id"]}">{_e(r["staff_name"])}</a>'
        f'<div class="kh-sub">{_e(r["role_name"])}</div></td>'
        f'<td class="money">{_tien_gon(r["revenue_booked"])}</td>'
        f'<td class="money">{_tien_gon(r["revenue_collected"])}</td>'
        f'<td class="money">{_tien_gon(r["base_salary"])}</td>'
        f'<td class="money">{_tien_gon(r["commission"])}</td>'
        f'<td class="money">{_tien_gon(r["care_bonus"])}</td>'
        f'<td class="money">{_tien_gon(r["hot_bonus"])}</td>'
        f'<td class="money">{_tien_gon(r["adjustment"])}</td>'
        f'<td class="money"><b>{_tien(r["total"])}</b></td>'
        f'<td>{"🔒 đã chốt" if r["frozen"] else "đang mở"}</td>'
        "</tr>" for r in rows) or (
        '<tr><td colspan="10" class="rong">Kỳ này chưa có dòng lương nào. '
        "Bấm <b>Tính lại kỳ</b> để dựng từ đơn hàng.</td></tr>")
    nut = (f'<form method="post" action="/crm/luong/tinh-lai" class="lg-act">'
           f'<input type="hidden" name="ky" value="{escape(ky)}">'
           '<button class="kh-btn" type="submit">Tính lại kỳ</button></form>'
           + (f'<form method="post" action="/crm/luong/chot" class="lg-act" '
              'onsubmit="return confirm(\'Chốt kỳ này? Sau khi chốt, số liệu '
              "ĐÓNG BĂNG — đơn hoàn phát sinh sau sẽ trừ vào kỳ sau chứ không "
              "sửa ngược.')\">"
              f'<input type="hidden" name="ky" value="{escape(ky)}">'
              '<button class="kh-btn go" type="submit">Chốt kỳ lương</button>'
              "</form>" if co_chot and not da_chot else "")) if co_chot else ""
    body = (
        (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + ('<div class="flash warn">🔒 Kỳ này đã chốt — mọi dòng đóng băng.'
           "</div>" if da_chot else "")
        + '<div class="vc-tiles">'
        + _o("Doanh thu LÊN ĐƠN", _tien_gon(tong["revenue_booked"]),
             "tổng giá trị đơn", "#4E7FE8")
        + _o("Doanh thu ĐÃ THU", _tien_gon(tong["revenue_collected"]),
             "đơn đã giao/thu tiền", "#2EAD6E")
        + _o("Quỹ lương kỳ", _tien_gon(tong["total"]),
             f"{len(rows)} người", "#7A308F")
        + _o("Thưởng chăm + nóng",
             _tien_gon(tong["care_bonus"] + tong["hot_bonus"]),
             "cộng THÊM vào hoa hồng", "#C25E00")
        + "</div>"
        + f'<div class="kh-card"><div class="kh-head">'
          f'<span class="cnt">Bảng lương {_ky_vi(ky)} · {len(rows)} người</span>'
          f'<div class="acts">{nut}</div></div>'
        + '<div class="kh-tblwrap"><table class="kh-tbl"><thead><tr>'
          '<th>Nhân viên</th><th class="num">Lên đơn</th>'
          '<th class="num">Đã thu</th><th class="num">Lương cứng</th>'
          '<th class="num">Hoa hồng</th><th class="num">Thưởng chăm</th>'
          '<th class="num">Thưởng nóng</th><th class="num">Điều chỉnh</th>'
          '<th class="num">Thực nhận</th><th>Tình trạng</th>'
          f"</tr></thead><tbody>{than}</tbody></table></div></div>"
        + '<p class="note" style="margin-top:10px">⚠️ <b>Thưởng chăm sóc cộng '
          "CHỒNG lên hoa hồng</b> — đây là cố ý, không phải tính hai lần. Hoa "
          "hồng trả cho doanh thu, thưởng chăm trả cho công kéo khách cũ quay "
          'lại. Duyệt từng đơn ở <a href="/crm/doi-soat">Đối soát &amp; duyệt '
          "thưởng</a>.</p>"
    )
    return render_shell(
        "Lương thưởng", "crm-payroll", body,
        heading="Lương thưởng",
        sub=f"Bảng lương cả đội · {_ky_vi(ky)}",
        actions=_chon_ky(ky, cac_ky, "/crm/luong"),
    )


# ----------------------------------------------------- Đối soát (doi-soat.php)
_RO_NHAN = [("all", "Tất cả"), ("fixed", "Đã sửa tay"),
            ("wonder", "Máy phân vân"), ("done", "Đã xử lý")]


def render_doi_soat(data: dict, *, flash: str = "", loi: str = "") -> str:
    ro = data["ro"]
    chip = "".join(
        f'<a class="ds-chip{" on" if ro == ma else ""}" '
        f'href="/crm/doi-soat?ro={ma}">{escape(nhan)} '
        f'<b>{data["dem"].get(ma, 0)}</b></a>' for ma, nhan in _RO_NHAN)
    than = ""
    for d in data["rows"]:
        xong = d["ro"] == "done"
        khoa = bool(d.get("ky_da_chot"))
        if xong:
            tt = ('<span class="kh-st active">✅ duyệt · '
                  + _tien_gon(d["review_amount"]) + "</span>"
                  if d["review_status"] == "duyet" else
                  f'<span class="kh-st sleep">🚫 bác</span>'
                  f'<div class="kh-sub">{_e(d["review_reason"])}</div>')
            thao_tac = f'<span class="kh-sub">bởi {_e(d["reviewed_by_name"])}</span>'
        else:
            tt = ('<span class="kh-st chua">chờ duyệt · '
                  + _tien_gon(d["thuong_uoc"]) + "</span>")
            if khoa:
                thao_tac = ('<span class="kh-none" title="Kỳ lương của đơn đã '
                            'chốt — không sửa ngược được">🔒 kỳ đã chốt</span>')
            else:
                thao_tac = (
                    f'<form method="post" action="/crm/doi-soat/{d["id"]}/duyet" '
                    'class="vc-inline"><button class="kh-btn go" type="submit">'
                    "Duyệt</button></form>"
                    f'<form method="post" action="/crm/doi-soat/{d["id"]}/bac" '
                    'class="vc-inline"><input name="ly_do" required '
                    'placeholder="Lý do bác (bắt buộc)">'
                    '<button class="kh-btn" type="submit">Bác</button></form>'
                    f'<form method="post" action="/crm/doi-soat/{d["id"]}/'
                    'phan-loai" class="vc-inline">'
                    '<input type="hidden" name="sang" value="quang_cao">'
                    '<button class="kh-btn" type="submit" title="Đơn này thật '
                    'ra do quảng cáo — chuyển đi thì thưởng chăm huỷ theo">'
                    "→ Quảng cáo</button></form>")
        sua = (f'<div class="kh-sub">✎ {_e(d["classify_reason"])}</div>'
               if d["classified_manually"] else "")
        than += (
            "<tr>"
            f'<td>{_e(d["external_order_id"] or d["pos_order_id"] or d["id"])}'
            f'<div class="kh-sub">kỳ {_e(d["payroll_period"])}</div></td>'
            f'<td><a class="kh-name" href="/crm/khach-hang/{d["customer_id"]}">'
            f'{_e(d["customer_name"])}</a></td>'
            f'<td>{_e(d["staff_name"])}</td>'
            f'<td class="money">{_tien(d["total_amount"])}</td>'
            f"<td>{tt}{sua}</td>"
            f'<td><div class="ds-acts">{thao_tac}</div></td>'
            "</tr>")
    than = than or ('<tr><td colspan="6" class="rong">Không có đơn nào trong '
                    "rổ này.</td></tr>")
    body = (
        (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + (f'<div class="flash err">{escape(loi)}</div>' if loi else "")
        + '<div class="vc-tiles">'
        + _o("Chờ duyệt", str(data["dem"]["fixed"] + data["dem"]["wonder"]),
             "đơn", "#C25E00")
        + _o("Tiền đang chờ duyệt", _tien_gon(data["cho_duyet"]),
             "chưa vào lương", "#7A308F")
        + _o("Đã xử lý", str(data["dem"]["done"]), "duyệt hoặc bác", "#2EAD6E")
        + "</div>"
        + f'<div class="ds-chips">{chip}</div>'
        + '<div class="kh-card">'
        + '<div class="kh-tblwrap"><table class="kh-tbl"><thead><tr>'
          '<th>Đơn</th><th>Khách</th><th>Nhân viên</th>'
          '<th class="num">Giá trị đơn</th><th>Thưởng chăm</th>'
          "<th>Thao tác</th></tr></thead>"
          f"<tbody>{than}</tbody></table></div></div>"
        + '<p class="note" style="margin-top:10px">Số thưởng <b>tính lại ở máy '
          "chủ</b> lúc bấm Duyệt — nút chỉ là lệnh, không phải nguồn số. "
          "<b>Bác thưởng bắt buộc ghi lý do.</b> Đơn có kỳ lương ĐÃ CHỐT thì "
          "khoá: muốn sửa phải ghi khoản điều chỉnh vào kỳ sau.</p>"
    )
    return render_shell(
        "Đối soát & duyệt thưởng", "crm-recon", body,
        heading="Đối soát & duyệt thưởng",
        sub="Thưởng chăm sóc từng đơn · 3 rổ suy từ dữ liệu",
    )


# ------------------------------------------------- Bậc lương (Quản trị → Tiền)
def _bang_bac(tieu_de: str, bang: str, cot: list[str], rows: list[dict],
              form: str, ghi_chu: str) -> str:
    than = "".join(
        "<tr>"
        f'<td>{_e(r["role_name"])}</td>'
        + "".join(f"<td>{c}</td>" for c in _o_bac(r, bang))
        + f'<td><form method="post" action="/crm/bac-luong/xoa" '
          f'class="vc-inline"><input type="hidden" name="bang" value="{bang}">'
          f'<input type="hidden" name="id" value="{r["id"]}">'
          '<button class="kh-btn" type="submit">Xoá</button></form></td>'
          "</tr>" for r in rows) or (
        f'<tr><td colspan="{len(cot) + 2}" class="rong">Chưa cấu hình bậc nào '
        "— khoản này sẽ tính ra 0.</td></tr>")
    return (
        '<div class="kh-card" style="padding:16px 18px;margin-top:14px">'
        f'<div class="ht-h">{escape(tieu_de)}</div>'
        + '<div class="kh-tblwrap"><table class="kh-tbl"><thead><tr>'
        + "<th>Vai trò</th>"
        + "".join(f"<th>{escape(c)}</th>" for c in cot)
        + "<th></th></tr></thead>"
        + f"<tbody>{than}</tbody></table></div>"
        + form
        + f'<p class="note">{ghi_chu}</p></div>'
    )


def _o_bac(r: dict, bang: str) -> list[str]:
    kieu = ("%" if r["kind"] == "phan_tram" else "₫")
    gia = (f'{float(r["value"]):g}%' if r["kind"] == "phan_tram"
           else _tien(r["value"]))
    if bang == "hot_bonus_tiers":
        nhan = ("doanh thu NGÀY" if r["basis"] == "doanh_thu_ngay"
                else "giá trị TỪNG ĐƠN")
        return [nhan, f'≥ {_tien(r["threshold"])}', gia]
    return [f'≥ {_tien(r["min_revenue"])}', gia]


def _form_bac(bang: str, vai_tro: list[dict], co_basis: bool,
              nhan_nguong: str) -> str:
    o_vt = "".join(f'<option value="{r["id"]}">{escape(r["name"])}</option>'
                   for r in vai_tro)
    basis = ('<label>Kiểu xét<select name="basis">'
             '<option value="doanh_thu_ngay">Doanh thu NGÀY</option>'
             '<option value="gia_tri_don">Giá trị TỪNG ĐƠN</option>'
             "</select></label>" if co_basis else "")
    return (
        '<form class="vc-form-r" method="post" action="/crm/bac-luong/them" '
        'style="margin-top:12px">'
        f'<input type="hidden" name="bang" value="{bang}">'
        f'<label>Vai trò<select name="role_id">{o_vt}</select></label>'
        + basis
        + f'<label>{escape(nhan_nguong)}<input name="nguong" inputmode="numeric" '
          'required placeholder="vd 50000000"></label>'
          '<label>Kiểu thưởng<select name="kind">'
          '<option value="phan_tram">Phần trăm</option>'
          '<option value="tien">Tiền cố định</option></select></label>'
          '<label>Giá trị<input name="value" inputmode="numeric" required '
          'placeholder="vd 3 hoặc 200000"></label>'
          '<button class="kh-btn go" type="submit">Thêm bậc</button>'
        "</form>"
    )


def render_bac_luong(hh: list[dict], tc: list[dict], tn: list[dict],
                     vai_tro: list[dict], *, flash: str = "",
                     loi: str = "") -> str:
    body = (
        (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + (f'<div class="flash err">{escape(loi)}</div>' if loi else "")
        + '<p class="note">Bậc treo theo <b>vai trò</b>. Lương cứng đặt ở '
          "<b>Quản trị → Nhân viên</b> (riêng từng người) hoặc mặc định theo "
          "vai trò.</p>"
        + _bang_bac(
            "Bậc hoa hồng (theo doanh thu ĐÃ THU của kỳ)", "commission_tiers",
            ["Ngưỡng doanh thu kỳ", "Hưởng"], hh,
            _form_bac("commission_tiers", vai_tro, False, "Ngưỡng doanh thu kỳ"),
            "Áp bậc CAO NHẤT mà doanh thu chạm tới — không cộng dồn các bậc.")
        + _bang_bac(
            "Bậc thưởng chăm sóc (theo giá trị TỪNG ĐƠN)", "care_bonus_tiers",
            ["Ngưỡng giá trị đơn", "Hưởng"], tc,
            _form_bac("care_bonus_tiers", vai_tro, False, "Ngưỡng giá trị đơn"),
            "Khoản này CỘNG THÊM vào hoa hồng (cố ý — xem ghi chú ở màn Lương "
            "thưởng). Chỉ đơn được DUYỆT ở màn Đối soát mới vào lương.")
        + _bang_bac(
            "Bậc thưởng nóng (2 kiểu chạy song song)", "hot_bonus_tiers",
            ["Kiểu xét", "Ngưỡng", "Hưởng"], tn,
            _form_bac("hot_bonus_tiers", vai_tro, True, "Ngưỡng"),
            "Hai kiểu CỘNG DỒN: một đơn to trong một ngày to thì ăn cả hai.")
    )
    return render_shell(
        "Bậc lương & thưởng", "crm-payroll", body,
        heading="Bậc lương & thưởng",
        sub="Cấu hình hoa hồng · thưởng chăm sóc · thưởng nóng theo vai trò",
    )
