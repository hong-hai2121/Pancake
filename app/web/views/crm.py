"""Dựng HTML bộ màn CRM tạm (khung) — tuyến đường /crm/*.

Nguyên tắc của bộ khung:
  * Cấu trúc màn đúng theo "Danh sách màn hình CRM" (số màn ghi ở từng hàm).
  * Số liệu là THẬT từ schema `crm` — bảng trống thì hiện 0/danh sách trống,
    kèm ghi chú lát cắt nào (B1…B11) sẽ đổ dữ liệu vào.
  * Khi lát cắt đó làm thật, thay phần thân màn; khung + menu giữ nguyên.
"""

from datetime import datetime
from html import escape

from app.integrations.pancake.links import link_hoi_thoai
from app.web.shell import render_shell, stat


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _dt(v) -> str:
    return v.strftime("%d/%m %H:%M") if v else "—"


def _d(v) -> str:
    return v.strftime("%d/%m/%Y") if v else "—"


def _tien(v) -> str:
    try:
        return f"{float(v):,.0f} ₫".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _ghi_chu(lat: str, chi_tiet: str) -> str:
    """Dải ghi chú 'màn khung' — nói rõ chỗ này chờ lát cắt nào."""
    return (
        '<div class="flash warn" style="margin-bottom:14px">🔨 Màn khung (tạm) — '
        f"<b>{escape(lat)}</b> sẽ đổ dữ liệu: {escape(chi_tiet)}</div>"
    )


def _bang(cols: list[str], rows_html: str, rong: str) -> str:
    head = "".join(f"<th>{escape(c)}</th>" for c in cols)
    body = rows_html or f'<tr><td colspan="{len(cols)}" class="note">{escape(rong)}</td></tr>'
    return (
        f'<div class="tblwrap card"><table class="tbl"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


# ------------------------------------------------------------ Trang chủ (màn 2)
_THU = ["Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy", "Chủ nhật"]

# Nhãn + nút lối tắt cho từng nhóm vai trò (màn 2 — mỗi vị trí một dashboard)
_LOI_TAT: dict[str, list[tuple[str, str]]] = {
    "sale":       [("/crm/pipeline", "🎯 Pipeline của tôi"),
                   ("/crm/cong-viec", "🗓️ Việc hôm nay"),
                   ("/crm/khach-hang", "👤 Khách hàng")],
    "sale_tn":    [("/crm/pipeline", "🎯 Pipeline cả đội"),
                   ("/crm/cong-viec?pham_vi=tatca", "🗓️ Việc cả đội"),
                   ("/quan-tri/nhan-vien", "👥 Đội của tôi")],
    "cskh":       [("/crm/cong-viec", "🗓️ Việc hôm nay"),
                   ("/crm/cham-soc", "💚 Chăm sóc"),
                   ("/crm/mua-lai", "🔄 Mua lại")],
    "cskh_tn":    [("/crm/cong-viec?pham_vi=tatca", "🗓️ Việc cả đội"),
                   ("/crm/cham-soc", "💚 Chăm sóc"),
                   ("/quan-tri/nhan-vien", "👥 Đội của tôi")],
    "marketing":  [("/crm/quang-cao", "📣 Nguồn quảng cáo"),
                   ("/crm/khach-hang", "👤 Khách hàng")],
    "ke_toan":    [("/crm/don-hang", "🧾 Đơn hàng"),
                   ("/quan-tri/nhan-vien/xuat-excel", "⬇ Xuất dữ liệu")],
    "chuyen_mon": [("/crm/san-pham", "🏷️ Sản phẩm & liệu trình"),
                   ("/crm/khach-hang", "👤 Khách hàng")],
    "admin":      [("/quan-tri/nhan-vien", "👥 Nhân viên"),
                   ("/quan-tri/tich-hop", "🔌 Tích hợp"),
                   ("/quan-tri/cai-dat", "⚙️ Cài đặt")],
    "chu_dn":     [("/crm/tong-quan", "📊 Tổng quan chi tiết"),
                   ("/crm/quang-cao", "📣 Quảng cáo"),
                   ("/quan-tri/nhan-vien", "👥 Nhân viên")],
    "khac":       [("/crm/cong-viec", "🗓️ Việc của tôi")],
}

# Tiêu đề lớn đầu trang chủ — nói ngay người xem đang xem BÁO CÁO GÌ (bố cục Kallet)
_HM_TIEU_DE: dict[str, str] = {
    "chu_dn":     "📊 Báo cáo cả team Sale &amp; CSKH",
    "admin":      "📊 Báo cáo cả team Sale &amp; CSKH",
    "sale":       "🎯 Việc bán hàng của tôi",
    "sale_tn":    "🎯 Báo cáo đội Sale",
    "cskh":       "💗 Việc chăm sóc của tôi",
    "cskh_tn":    "💗 Báo cáo đội CSKH",
    "marketing":  "📣 Hiệu quả quảng cáo",
    "ke_toan":    "🧾 Đơn hàng &amp; doanh thu",
    "chuyen_mon": "🩺 Hồ sơ cần chuyên môn",
    "khac":       "🏠 Trang chủ",
}


def _card(tieu_de: str, ruot: str, note: str = "") -> str:
    ghi = f'<p class="note" style="margin:8px 0 0">{escape(note)}</p>' if note else ""
    return (f'<div class="card" style="margin-top:14px"><h3>{escape(tieu_de)}</h3>'
            f"{ruot}{ghi}</div>")


# --- mảnh dựng Trang chủ (bố cục Kallet) -----------------------------------
def _hm_panel(tieu_de: str, ruot: str, phu: str = "") -> str:
    dau = (f'<div class="panel-t">{tieu_de}'
           + (f"<small>{phu}</small>" if phu else "") + "</div>") if tieu_de else ""
    return f'<div class="panel">{dau}{ruot}</div>'


def _hm_bigkpi(so: str, nhan: str, bieu: str, tone: str, href: str) -> str:
    """Ô số lớn trên đầu trang chủ (3 ô: hôm nay · quá hạn · sắp tới)."""
    return (
        f'<a class="bigkpi {tone}" href="{escape(href)}">'
        f'<span class="bk-ic">{bieu}</span>'
        f'<span><span class="bk-n">{escape(so)}</span>'
        f'<span class="bk-l">{nhan} ›</span></span></a>'
    )


def _hm_o(so: str, nhan: str, mau: str = "", href: str = "") -> str:
    """Ô số nhỏ trong thẻ đội."""
    ruot = (f'<div class="n{" " + mau if mau else ""}">{escape(so)}</div>'
            f'<div class="l">{nhan}</div>')
    return (f'<a class="kpi2" href="{escape(href)}">{ruot}</a>' if href
            else f'<div class="kpi2">{ruot}</div>')


def _hm_the_doi(bieu: str, ten: str, lop: str, o: str, link: tuple[str, str] = (),
                thanh: str = "") -> str:
    """Thẻ một đội: đầu thẻ + lưới ô số + (tuỳ chọn) thanh doanh thu dưới cùng."""
    xem = (f'<a class="tc-link" href="{escape(link[0])}">{escape(link[1])} ›</a>'
           if link else "")
    return (
        f'<div class="teamcard"><div class="tc-head">'
        f'<span class="tc-ic {lop}">{bieu}</span><b>{escape(ten)}</b>{xem}</div>'
        f'<div class="kpis2">{o}</div>{thanh}</div>'
    )


def _hm_thanh_tien(lop: str, nhan: str, tien, phu: str, href: str) -> str:
    """Thanh doanh thu dưới đáy thẻ đội. `phu` là dòng phụ ĐÃ soạn sẵn (mỗi vai
    trò đối chiếu một thứ khác nhau: đã thu · số đơn · doanh thu hôm nay)."""
    return (
        f'<a class="revbar {lop}" href="{escape(href)}"><span>{escape(nhan)}</span>'
        f"<b>{_tien(tien)}<small>{phu}</small></b></a>"
    )


def _hm_chon_ky(ky: dict) -> str:
    """Thanh chọn kỳ: 5 nút nhanh (liên kết) + ô từ/đến. Không cần JS."""
    from datetime import date, timedelta

    h = date.today()
    dau_thang = h.replace(day=1)
    san = [("Hôm nay", h, h),
           ("Hôm qua", h - timedelta(days=1), h - timedelta(days=1)),
           ("7 ngày qua", h - timedelta(days=6), h),
           ("30 ngày qua", h - timedelta(days=29), h),
           ("Đầu tháng đến nay", dau_thang, h)]
    seg = "".join(
        f'<a class="{"on" if ky.get("tu") == a.isoformat() and ky.get("den") == b.isoformat() else ""}"'
        f' href="/crm/trang-chu?tu={a}&den={b}">{escape(ten)}</a>'
        for ten, a, b in san
    )
    return _hm_panel(
        "",
        f'<div class="rf-quick"><span class="rf-lb">⚡ Xem nhanh</span>'
        f'<span class="rf-seg">{seg}</span></div>'
        '<form class="rf-row" method="get" action="/crm/trang-chu">'
        '<label class="rf-field"><span class="rf-ov">Từ ngày</span>'
        f'<input type="date" name="tu" value="{escape(str(ky.get("tu") or ""))}"></label>'
        '<label class="rf-field"><span class="rf-ov">Đến ngày</span>'
        f'<input type="date" name="den" value="{escape(str(ky.get("den") or ""))}"></label>'
        '<button class="rf-go">Xem báo cáo</button></form>',
    )


def _hm_bieu_do(chuoi: list[dict]) -> str:
    """Cột doanh thu theo ngày — SVG dựng tay (dự án không có thư viện biểu đồ).

    Mỗi ngày 2 cột: Sale (bán mới = tổng − mua lại) và CSKH (mua lại)."""
    if not chuoi:
        return ('<div class="lp-mut">Chưa có đơn giao thành công nào trong kỳ '
                "— biểu đồ hiện khi có dữ liệu.</div>")
    rong, cao, le_d, le_t = 900, 190, 24, 8
    cot = [(r["ngay"], float(r["tong"] or 0) - float(r["mua_lai"] or 0),
            float(r["mua_lai"] or 0)) for r in chuoi]
    dinh = max([s + c for _, s, c in cot] + [1])
    buoc = (rong - le_t * 2) / len(cot)
    w = max(3.0, min(18.0, buoc / 3))
    than, nhan = "", ""
    for i, (ngay, s, c) in enumerate(cot):
        x = le_t + buoc * i + buoc / 2
        for gia_tri, lop, lech in ((s, "bs", -w - 1), (c, "bc", 1)):
            h = (cao - le_d) * gia_tri / dinh
            if h > 0:
                than += (f'<rect class="{lop}" x="{x + lech:.1f}" '
                         f'y="{cao - le_d - h:.1f}" width="{w:.1f}" '
                         f'height="{h:.1f}" rx="2"><title>{ngay:%d/%m} · '
                         f'{"Sale" if lop == "bs" else "CSKH"}: '
                         f"{gia_tri:,.0f}đ</title></rect>")
        # nhãn ngày: thưa dần khi kỳ dài, khỏi chồng chữ
        if len(cot) <= 12 or i % max(1, len(cot) // 10) == 0:
            nhan += (f'<text x="{x:.1f}" y="{cao - 8}" text-anchor="middle">'
                     f"{ngay:%d/%m}</text>")
    luoi = "".join(
        f'<line class="gl" x1="0" y1="{(cao - le_d) * k / 3:.1f}" x2="{rong}" '
        f'y2="{(cao - le_d) * k / 3:.1f}"/>' for k in range(4)
    )
    return (
        f'<svg class="hm-chart" viewBox="0 0 {rong} {cao}" role="img" '
        f'aria-label="Doanh thu giao thành công theo ngày">'
        f"{luoi}{than}{nhan}</svg>"
        '<div class="hm-legend">'
        '<span><i style="background:var(--hot)"></i>Sale (bán mới)</span>'
        '<span><i style="background:#3b82f6"></i>CSKH (mua lại)</span>'
        f"<span>Đỉnh cột: {_tien(dinh)}</span></div>"
    )


def _hm_khoi_ca_doi(bc: dict) -> str:
    """Khối "báo cáo cả team Sale & CSKH" của Trang chủ Chủ DN / Admin.

    `bc` = `report_service.bao_cao_ca_doi()`. Khoá `tien` rỗng nghĩa là người
    xem KHÔNG có revenue.view — bỏ hẳn khối tiền/biểu đồ/xếp hạng thay vì bày
    số 0 (đúng nếp FR-173: ẩn theo quyền, không bịa)."""
    ky, doi, tl = bc["ky"], bc["doi"], bc["ti_le"]
    tien = bc.get("tien") or {}

    def drill(metric: str) -> str:
        return (f'/crm/bao-cao/chi-tiet?metric={metric}'
                f'&tu={ky["tu"]}&den={ky["den"]}')

    def pt(v) -> str:
        return "—" if v is None else f"{v}%"

    def n(v) -> str:
        return f"{int(v or 0):,}".replace(",", ".")

    khoi = _hm_chon_ky(ky) + '<div class="hm-2col">' + _hm_the_doi(
        "🧑‍💼", "Đội Sale", "sale",
        _hm_o(n(doi["lead_moi"]), "🆕 Khách tiềm năng mới", "pink",
              drill("lead_moi"))
        + _hm_o(n(doi["lead_lien_he"]), "💬 Đã liên hệ được", "",
                drill("lead_lien_he"))
        + _hm_o(n(doi["lead_chot"]), "✅ Chốt đơn", "green", drill("lead_chot"))
        + _hm_o(pt(tl["chot"]), "🎯 Tỉ lệ chốt", "")
        + _hm_o(n(doi["don_tao"]), "🧾 Đơn tạo", "", drill("don_tao"))
        + _hm_o(n(doi["don_giao"]), "🚚 Đơn giao thành công", "green",
                drill("don_giao")),
        ("/crm/bao-cao?tab=sale", "Xem báo cáo"),
        _hm_thanh_tien(
            "sale", "Doanh thu Sale (đơn bán mới)",
            tien.get("doanh_thu_len_don_sale"),
            "· ✅ đã thu " + _tien(float(tien.get("doanh_thu_giao") or 0)
                                  - float(tien.get("doanh_thu_mua_lai") or 0)),
            drill("doanh_thu_len_don_sale")) if tien else "",
    ) + _hm_the_doi(
        "💬", "Đội CSKH", "cskh",
        _hm_o(n(doi["moc_den_han"]), "📞 Mốc chăm đến hạn",
              "blue" if doi["moc_den_han"] else "", drill("moc_den_han"))
        + _hm_o(n(doi["moc_hoan_thanh"]), "☑️ Mốc đã làm", "",
                drill("moc_hoan_thanh"))
        + _hm_o(pt(tl["dung_han"]), "⭐ Làm đúng hạn", "green")
        + _hm_o(n(doi["ban_giao_moi"]), "🤝 Khách mới bàn giao", "",
                drill("ban_giao_moi"))
        + _hm_o(n(doi["co_hoi_mo"]), "🔄 Cơ hội mua lại đang mở", "",
                drill("co_hoi_mo"))
        + _hm_o(n(doi["viec_qua_han"]), "⚠️ Việc quá hạn",
                "red" if doi["viec_qua_han"] else "", drill("viec_qua_han")),
        ("/crm/bao-cao?tab=cskh", "Xem báo cáo"),
        _hm_thanh_tien(
            "cskh", "Doanh thu CSKH (đơn chăm sóc)",
            tien.get("doanh_thu_len_don_cskh"),
            "· ✅ đã thu " + _tien(tien.get("doanh_thu_mua_lai")),
            drill("doanh_thu_len_don_cskh")) if tien else "",
    ) + "</div>"

    if not tien:
        return khoi + _hm_panel(
            "💰 Doanh thu",
            '<div class="lp-mut">Tài khoản của bạn không có quyền '
            "<b>revenue.view</b> nên phần doanh thu, biểu đồ và xếp hạng theo "
            "tiền được ẩn.</div>")

    khoi += _hm_panel(
        "💰 Doanh thu toàn công ty",
        '<div class="stats">'
        + stat("💰 Lên đơn · Tổng", _tien(tien["doanh_thu_len_don"]),
               hint=f'✅ Đã thu: {_tien(tien["doanh_thu_giao"])}',
               href=drill("doanh_thu_len_don"))
        + stat("🎯 Sale (đơn bán mới)", _tien(tien["doanh_thu_len_don_sale"]),
               href=drill("doanh_thu_len_don_sale"))
        + stat("💗 CSKH (đơn chăm sóc)", _tien(tien["doanh_thu_len_don_cskh"]),
               hint=f'✅ Đã thu: {_tien(tien["doanh_thu_mua_lai"])}',
               href=drill("doanh_thu_len_don_cskh"))
        + "</div>"
        '<p class="note" style="margin:10px 0 0">💰 <b>Lên đơn</b> = tiền đơn '
        "tạo trong kỳ ở <b>mọi trạng thái</b> (bỏ huỷ/hoàn) · ✅ <b>Đã thu</b> = "
        "đơn đã <b>giao thành công</b>. Bấm số để xem đúng danh sách đơn của "
        "kỳ đang lọc.</p>",
        f'· {ky["tu"]} → {ky["den"]}',
    )

    khoi += _hm_panel("📈 Doanh thu theo thời gian",
                      _hm_bieu_do(bc["theo_ngay"]),
                      "· đơn giao thành công từng ngày")

    xh_s = "".join(
        f'<tr><td><a href="/crm/dashboard-sale?user_id={r["id"]}'
        f'&tu={ky["tu"]}&den={ky["den"]}">{_e(r["name"])}</a></td>'
        f'<td class="num">{r["chot"]}</td>'
        f'<td class="num"><b>{_tien(r["doanh_thu"])}</b></td></tr>'
        for r in bc["xh_sale"]
    )
    xh_c = "".join(
        f'<tr><td><a href="/crm/dashboard-cskh?user_id={r["id"]}'
        f'&tu={ky["tu"]}&den={ky["den"]}">{_e(r["name"])}</a></td>'
        f'<td class="num">{r["moc_xong"]}</td>'
        f'<td class="num"><b>{_tien(r["doanh_thu_mua_lai"])}</b></td></tr>'
        for r in bc["xh_cskh"]
    )
    khoi += (
        '<div class="rankwrap">'
        + _hm_xep_hang("🏆 Xếp hạng đội Sale · theo doanh thu",
                       ["Nhân viên", "Chốt", "Doanh thu ▾"], xh_s)
        + _hm_xep_hang("🏆 Xếp hạng CSKH · theo doanh thu mua lại",
                       ["Nhân viên", "Mốc xong", "Doanh thu ▾"], xh_c)
        + "</div>"
        '<p class="note">💡 Hai bảng cùng thước đo <b>doanh thu giao thành '
        "công</b> trong kỳ — bấm tên nhân viên để mở dashboard riêng của họ.</p>"
    )
    return khoi


def _hm_xep_hang(tieu_de: str, cot: list[str], dong: str) -> str:
    than = dong or (f'<tr><td colspan="{len(cot)}" class="lp-mut">'
                    "Chưa có số liệu trong kỳ</td></tr>")
    # cột đầu là tên người (căn trái), các cột số căn phải
    dau = "".join(
        ("<th>" if i == 0 else '<th class="num">') + escape(c) + "</th>"
        for i, c in enumerate(cot)
    )
    return _hm_panel(
        tieu_de,
        f'<table class="rtbl"><thead><tr>{dau}</tr></thead>'
        f"<tbody>{than}</tbody></table>",
    )


def render_trang_chu(nhom: str, data: dict, user: dict) -> str:
    """Màn 2 — Trang chủ theo vai trò: 9 vị trí, mỗi vị trí một bộ số + lối tắt.

    Nguyên tắc: số THẬT từ DB (lát chưa chạy thì 0), khối nào phụ thuộc lát sau
    (B8/B9…) có ghi chú ngay dưới khối. `nhom` do route ánh xạ từ vai trò token."""
    from datetime import datetime

    hom_nay = datetime.now()
    ten = user.get("name") or user.get("username") or "bạn"
    vai = user.get("role") or ""
    nut = "".join(
        f'<a class="btn sm" href="{href}">{nhan}</a>'
        for href, nhan in _LOI_TAT.get(nhom, _LOI_TAT["khac"])
    )
    viec = data.get("viec") or {"hom_nay": 0, "qua_han": 0, "sap_toi": 0}
    cua_ai = "cả đội" if nhom in ("sale_tn", "cskh_tn") else "của tôi"

    # --- đầu trang: tiêu đề theo vai trò + lời chào + lối tắt (bố cục Kallet) ---
    chao = (
        f'<div class="hm-h1">{_HM_TIEU_DE.get(nhom, "🏠 Trang chủ")}'
        f'<span class="dt">· {_THU[hom_nay.weekday()]}, '
        f'{hom_nay.strftime("%d/%m/%Y")}</span></div>'
        f'<div class="hm-sub">Xin chào <b>{escape(ten)}</b> · Vai trò: '
        f'<b>{escape(vai or "chưa gán")}</b> · Phạm vi: <b>{cua_ai}</b> · '
        "💡 bấm vào từng chỉ số để mở trang chi tiết</div>"
        + (f'<div class="rf-quick" style="margin-bottom:14px">{nut}</div>'
           if nut else "")
    )

    # --- 3 ô lớn: việc hôm nay · quá hạn · sắp tới 7 ngày (mọi vai trò) ---
    khoi = (
        '<div class="kpi3">'
        + _hm_bigkpi(f'{viec["hom_nay"]:,}'.replace(",", "."),
                     f"Cần làm hôm nay ({cua_ai})", "💗", "warn", "/crm/cong-viec")
        + _hm_bigkpi(f'{viec["qua_han"]:,}'.replace(",", "."),
                     f"Quá hạn ({cua_ai})", "⏰",
                     "err" if viec["qua_han"] else "", "/crm/cong-viec")
        + _hm_bigkpi(f'{viec.get("sap_toi", 0):,}'.replace(",", "."),
                     f"Sắp tới 7 ngày ({cua_ai})", "📅", "info", "/crm/cong-viec")
        + "</div>"
    )

    if nhom in ("sale", "sale_tn"):
        lead, don = data["lead"], data["don"]
        o_sale = (
            _hm_o(str(lead["mo"]), "🎯 Khách tiềm năng đang mở", "pink",
                  "/crm/pipeline")
            + _hm_o(str(lead["moi_hom_nay"]), "🆕 Mới hôm nay", "", "/crm/pipeline")
            + _hm_o(str(lead["nong"]), "🔥 Đang nóng",
                    "warn" if lead["nong"] else "", "/crm/pipeline?temperature=nong")
            + _hm_o(str(lead["qua_sla"]), "⚠️ Quá SLA nhận",
                    "red" if lead["qua_sla"] else "", "/crm/pipeline")
            + _hm_o(str(lead["hen_tre"]), "⏰ Trễ hẹn chăm",
                    "red" if lead["hen_tre"] else "", "/crm/pipeline?moc=qua_han")
            + _hm_o(str(don["don_thang"]), "🧾 Đơn tạo trong tháng", "",
                    "/crm/don-hang")
        )
        if nhom == "sale_tn":
            o_sale += _hm_o(str(data["hang_doi"]), "📥 Hàng đợi chưa ai nhận",
                            "warn" if data["hang_doi"] else "", "/crm/pipeline")
        khoi += '<div class="hm-2col">' + _hm_the_doi(
            "🧑‍💼", "Đội Sale" if nhom == "sale_tn" else "Việc bán của tôi", "sale",
            o_sale, ("/crm/pipeline", "Mở bảng chăm sóc"),
            _hm_thanh_tien("sale", "Doanh thu giao thành công trong tháng",
                           don["doanh_thu_thang"],
                           f'· 🧾 {don["don_thang"]} đơn tạo trong tháng',
                           "/crm/don-hang"),
        ) + "</div>"
        dong = "".join(
            f"<tr><td><b>{_e(r['full_name'])}</b></td><td>{_e(r['stage'])}</td>"
            f"<td>{_e(r['temperature'])}</td><td>{_dt(r['next_action_at'])}</td>"
            f"<td>{_e(r['nguoi'])}</td></tr>"
            for r in data["can_lam"]
        )
        khoi += _card(
            "Khách tiềm năng cần hành động sớm nhất",
            _bang(["Khách", "Giai đoạn", "Nhiệt", "Hẹn kế tiếp", "Phụ trách"],
                  dong, "Chưa có khách tiềm năng nào được giao"),
        )
        if nhom == "sale_tn":
            nv = "".join(
                f"<tr><td>{_e(r['name'])}</td><td>{r['mo']}</td>"
                f"<td>{r['tre']}</td><td>{r['nong']}</td></tr>"
                for r in data["theo_nv"]
            )
            khoi += _card(
                "Tải theo nhân viên trong đội",
                _bang(["Nhân viên", "Khách tiềm năng mở", "Trễ hẹn", "Nóng"], nv,
                      "Đội chưa có thành viên"),
            )

    elif nhom in ("cskh", "cskh_tn"):
        so = data["so"]
        khoi += '<div class="hm-2col">' + _hm_the_doi(
            "💬", "Đội CSKH" if nhom == "cskh_tn" else "Việc chăm sóc của tôi",
            "cskh",
            _hm_o(str(so["don_cho_xn"]), "🛍️ Đơn chờ xác nhận (CS01)",
                  "warn" if so["don_cho_xn"] else "", "/crm/don-hang")
            + _hm_o(str(so["moc_den_han"]), "📞 Mốc chăm đến hạn",
                    "blue" if so["moc_den_han"] else "", "/crm/cham-soc")
            + _hm_o(str(so["mua_lai"]), "🔄 Cơ hội mua lại đang mở", "",
                    "/crm/mua-lai"),
            ("/crm/cham-soc", "Mở bảng chăm sóc"),
        ) + "</div>"
        moc = "".join(
            f"<tr><td><span class='pill'>{_e(m['step_code'])}</span></td>"
            f"<td>{_e(m['khach'])}</td><td>{_dt(m['planned_at'])}</td>"
            f"<td>{_e(m['status'])}</td></tr>"
            for m in data["moc"]
        )
        khoi += _card(
            "Mốc chăm chờ làm",
            _bang(["Mốc", "Khách", "Lịch hẹn", "Trạng thái"], moc,
                  "Chưa có mốc chăm — sinh tự động khi B8/B9 chạy"),
            note="Kế hoạch chăm tự tạo khi đơn giao thành công (B8 bàn giao + B9 chăm 11 bước)",
        )
        if nhom == "cskh_tn":
            nv = "".join(
                f"<tr><td>{_e(r['name'])}</td><td>{r['dang_mo']}</td>"
                f"<td>{r['qua_han']}</td></tr>"
                for r in data["theo_nv"]
            )
            khoi += _card(
                "Việc theo nhân viên trong đội",
                _bang(["Nhân viên", "Việc đang mở", "Quá hạn"], nv,
                      "Đội chưa có thành viên"),
            )

    elif nhom == "marketing":
        ads, moi = data["ads"], data["moi"]
        chi_30 = float(ads["chi_30n"] or 0)
        dt_30 = float(moi["doanh_thu_30n"] or 0)
        roas = f"{dt_30 / chi_30:,.2f}" if chi_30 > 0 else "—"
        khoi += '<div class="hm-2col">' + _hm_the_doi(
            "📣", "Quảng cáo 30 ngày", "sale",
            _hm_o(_tien(ads["chi_7n"]), "💸 Chi phí 7 ngày", "", "/crm/quang-cao")
            + _hm_o(_tien(ads["chi_30n"]), "💸 Chi phí 30 ngày", "",
                    "/crm/quang-cao")
            + _hm_o(str(ads["ad_co_chi"]), "🎬 Ad có chi phí", "",
                    "/crm/quang-cao")
            + _hm_o(roas, "📈 ROAS 30 ngày", "green" if chi_30 else "",
                    "/crm/quang-cao")
            + _hm_o(str(moi["lead_7n"]), "🆕 Khách tiềm năng mới 7 ngày", "pink",
                    "/crm/pipeline")
            + _hm_o(str(moi["khach_7n"]), "👤 Khách mới 7 ngày", "",
                    "/crm/khach-hang"),
            ("/crm/quang-cao", "Mở nguồn quảng cáo"),
        ) + "</div>"
        khoi += _card(
            "Đi sâu hơn",
            '<p style="margin:0">Mở <a href="/crm/quang-cao">Nguồn quảng cáo</a> để xem '
            "cây chiến dịch → nhóm → quảng cáo, phễu và phiếu sức khỏe từng ad.</p>",
            note="Doanh thu quy nguồn chỉ có số khi bật đồng bộ đơn POS (màn Cài đặt)",
        )

    elif nhom == "ke_toan":
        tt, thang = data["theo_tt"], data["thang"]

        def n(ma: str) -> int:
            return tt.get(ma, {}).get("n", 0)

        hoan = n("returned") + n("returning")
        khoi += '<div class="hm-2col">' + _hm_the_doi(
            "🧾", "Đơn & doanh thu", "cskh",
            _hm_o(str(n("pending")), "⏳ Chờ xác nhận", "warn" if n("pending") else "",
                  "/crm/don-hang?status=pending")
            + _hm_o(str(n("shipping")), "🚚 Đang giao", "blue",
                    "/crm/don-hang?status=shipping")
            + _hm_o(str(n("delivered")), "✅ Giao thành công", "green",
                    "/crm/don-hang?status=delivered")
            + _hm_o(str(hoan), "↩️ Hoàn", "red" if hoan else "", "/crm/don-hang"),
            ("/crm/don-hang", "Mở danh sách đơn"),
            _hm_thanh_tien("sale", "Doanh thu giao thành công trong tháng",
                           thang["doanh_thu_thang"],
                           f'· 📅 hôm nay {_tien(thang["doanh_thu_hom_nay"])}',
                           "/crm/don-hang"),
        ) + "</div>"
        dong = "".join(
            f"<tr><td>{_e(r['external_order_id']) if r['external_order_id'] else '#' + str(r['id'])}</td>"
            f"<td>{_e(r['khach'])}</td><td><span class='pill'>{_e(r['status'])}</span></td>"
            f"<td>{_tien(r['total_amount'])}</td><td>{_dt(r['created_at'])}</td></tr>"
            for r in data["rows"]
        )
        khoi += _card(
            "Đơn mới nhất",
            _bang(["Mã đơn", "Khách", "Trạng thái", "Giá trị", "Tạo lúc"], dong,
                  "Chưa có đơn — bật đồng bộ POS ở màn Cài đặt"),
        )

    elif nhom == "chuyen_mon":
        so = data["so"]
        khoi += '<div class="hm-2col">' + _hm_the_doi(
            "🩺", "Chuyên môn & an toàn", "cskh",
            _hm_o(str(so["ca_cho"]), "🚨 Ca chuyển chuyên môn chờ",
                  "red" if so["ca_cho"] else "")
            + _hm_o(str(so["ca_cua_toi"]), "🙋 Giao cho tôi",
                    "warn" if so["ca_cua_toi"] else "")
            + _hm_o(str(so["de_xuat_cho"]), "📋 Đề xuất chờ duyệt",
                    "warn" if so["de_xuat_cho"] else "", "/crm/san-pham")
            + _hm_o(str(so["sp_cho_duyet"]), "🏷️ SP/nội dung chờ duyệt", "",
                    "/crm/san-pham")
            + _hm_o(str(so["khach_do"]), "🔴 Khách cờ đỏ",
                    "red" if so["khach_do"] else "", "/crm/khach-hang")
            + _hm_o(str(so["khach_vang"]), "🟡 Khách cờ vàng",
                    "warn" if so["khach_vang"] else "", "/crm/khach-hang"),
        ) + "</div>"
        ca = "".join(
            f"<tr><td><b>{_e(r['khach'])}</b></td><td>{_e(r['risk_level'])}</td>"
            f"<td>{_e(r['reason'])}</td><td>{_e(r['giao_cho'])}</td>"
            f"<td>{_dt(r['created_at'])}</td></tr>"
            for r in data["ca"]
        )
        khoi += _card(
            "Ca đang chờ xử lý",
            _bang(["Khách", "Mức rủi ro", "Lý do", "Giao cho", "Mở lúc"], ca,
                  "Không có ca nào chờ — sàng lọc an toàn (B5) tự mở ca khi có red flag"),
        )

    elif nhom == "admin":
        # Admin trước hết là người điều hành: bày báo cáo cả 2 đội y như Chủ DN,
        # rồi mới tới khối kỹ thuật (tài khoản, lỗi đồng bộ, nhật ký).
        so = data["so"]
        khoi += _hm_khoi_ca_doi(data["bc"]) if data.get("bc") else ""
        audit = "".join(
            f"<tr><td>{_dt(a['created_at'])}</td><td>{_e(a['user_name'])}</td>"
            f"<td><span class='pill'>{_e(a['action'])}</span></td>"
            f"<td>{_e(a['object_type'])}</td></tr>"
            for a in data["audit_moi"]
        )
        khoi += _hm_panel(
            "🛠️ Vận hành hệ thống",
            '<div class="kpis2">'
            + _hm_o(str(so["nv_active"]), "👥 Nhân viên hoạt động", "",
                    "/quan-tri/nhan-vien")
            + _hm_o(str(so["phien_hom_nay"]), "🔑 Phiên đăng nhập hôm nay")
            + _hm_o(str(so["loi_cho"]), "🔁 Lỗi đồng bộ chờ thử lại",
                    "warn" if so["loi_cho"] else "", "/quan-tri/tich-hop/loi")
            + _hm_o(str(so["loi_bo_cuoc"]), "⛔ Lỗi bỏ cuộc (xử tay)",
                    "red" if so["loi_bo_cuoc"] else "", "/quan-tri/tich-hop/loi")
            + _hm_o(str(so["thao_tac_hom_nay"]), "📝 Thao tác hôm nay", "",
                    "/quan-tri/nhat-ky")
            + "</div>"
            '<div style="margin-top:12px">'
            + _bang(["Lúc", "Ai", "Hành động", "Đối tượng"], audit,
                    "Chưa có hoạt động")
            + "</div>",
            "· tài khoản · đồng bộ · nhật ký",
        )

    elif nhom == "chu_dn":
        so, ads = data["so"], data["ads"]
        chi_30 = float(ads["chi_30n"] or 0)
        dt_30 = float(ads["doanh_thu_30n"] or 0)
        roas = f"{dt_30 / chi_30:,.2f}" if chi_30 > 0 else "—"
        khoi += _hm_khoi_ca_doi(data["bc"]) if data.get("bc") else ""
        khoi += _hm_panel(
            "🏢 Toàn công ty (không phụ thuộc kỳ lọc)",
            '<div class="kpis2">'
            + _hm_o(str(so["khach"]), "👤 Khách hàng", "", "/crm/khach-hang")
            + _hm_o(str(so["lead_mo"]), "🎯 Khách tiềm năng đang mở", "pink",
                    "/crm/pipeline")
            + _hm_o(str(so["don_thang"]), "🧾 Đơn trong tháng", "",
                    "/crm/don-hang")
            + _hm_o(_tien(ads["chi_30n"]), "💸 Chi phí QC 30 ngày", "",
                    "/crm/quang-cao")
            + _hm_o(roas, "📈 ROAS 30 ngày", "green" if chi_30 else "",
                    "/crm/quang-cao")
            + _hm_o(str(so["viec_qua_han"]), "⚠️ Việc quá hạn toàn cty",
                    "red" if so["viec_qua_han"] else "", "/crm/cong-viec")
            + _hm_o(str(so["co_hoi_mua_lai"]), "🔄 Cơ hội mua lại", "",
                    "/crm/mua-lai")
            + "</div>"
            '<p class="note" style="margin:10px 0 0">Đi sâu hơn: '
            '<a href="/crm/tong-quan">Tổng quan chi tiết</a> · '
            '<a href="/crm/quang-cao">Nguồn quảng cáo</a> (ROAS từng ad).</p>',
        )

    else:  # vai trò lạ / chưa gán — chỉ việc của tôi + hướng dẫn
        khoi += _card(
            "Chưa nhận diện vai trò",
            '<p style="margin:0">Tài khoản của bạn chưa thuộc nhóm dashboard nào — '
            'vẫn xem được <a href="/crm/cong-viec">Công việc</a> và các màn được cấp '
            "quyền. Liên hệ Admin để gán đúng vai trò.</p>",
        )

    return render_shell(
        "Trang chủ", "crm-home", chao + khoi,
        heading="Trang chủ",
        sub=f"Màn 2 — mỗi vai trò một dashboard riêng · bạn đang xem bản: <b>{escape(vai or 'chưa gán vai trò')}</b>",
    )


# ------------------------------------------------------------ Tổng quan (màn 4)
def render_tong_quan(data: dict, tieu_cuc: int | None) -> str:
    so = data["so"]
    tiles = (
        '<div class="stats">'
        + stat("Khách hàng", str(so["khach"]), href="/crm/khach-hang")
        + stat("Khách tiềm năng đang mở", str(so["lead_mo"]), href="/crm/pipeline")
        + stat("Việc hôm nay", str(so["viec_hom_nay"]), href="/crm/cong-viec")
        + stat("Việc quá hạn", str(so["viec_qua_han"]),
               tone="err" if so["viec_qua_han"] else "", href="/crm/cong-viec")
        + stat("Đơn hàng", str(so["don"]), href="/crm/don-hang")
        + stat("Doanh thu giao TC", _tien(so["doanh_thu_giao"]), href="/crm/don-hang")
        + stat("Cơ hội mua lại", str(so["co_hoi_mua_lai"]), href="/crm/mua-lai")
        + stat("Hội thoại tiêu cực", "—" if tieu_cuc is None else str(tieu_cuc),
               tone="warn" if tieu_cuc else "", href="/cam-xuc")
        + "</div>"
    )

    cot_stage = "".join(
        f'<div class="kcol{" closed" if s["is_closed"] else ""}">'
        f"<h4>{escape(s['name'])}<span class='kcount'>{s['so_lead']}</span></h4></div>"
        for s in data["theo_stage"]
    )
    audit = "".join(
        f"<tr><td>{_dt(a['created_at'])}</td><td>{_e(a['user_name'])}</td>"
        f"<td><span class='pill'>{_e(a['action'])}</span></td>"
        f"<td>{_e(a['object_type'])}</td></tr>"
        for a in data["audit_moi"]
    )

    body = (
        _ghi_chu("B1→B11", "mỗi ô số sẽ sống dần theo từng lát cắt; số hiện tại "
                 "đếm thật từ DB (trống thì 0)")
        + tiles
        + '<div class="card" style="margin-top:14px"><h3>Khách tiềm năng theo giai đoạn '
          '(13 giai đoạn — B3)</h3><div class="kanban">' + cot_stage + "</div></div>"
        + '<div class="card" style="margin-top:14px"><h3>Hoạt động gần đây</h3>'
        + _bang(["Lúc", "Ai", "Hành động", "Đối tượng"], audit, "Chưa có hoạt động")
        + "</div>"
    )
    return render_shell(
        "Tổng quan CRM", "crm-overview", body,
        heading="Tổng quan",
        sub="Toàn cảnh vận hành — mọi ô số bấm được để mở danh sách (FR-173)",
    )


# ------------------------------------------------------------ Khách hàng (màn 8)
def render_khach_hang(rows: list[dict], total: int, q: str,
                      loc: dict | None = None,
                      nhan_vien: list[dict] | None = None) -> str:
    dong = ""
    for r in rows:
        # BRD mục 4 — "Nút mở đúng hội thoại Pancake từ hồ sơ CRM". Link ghép từ
        # dữ liệu đã đồng bộ trong DB; khách chưa có hội thoại thì không hiện nút.
        link = link_hoi_thoai(r.get("external_page_id") or "",
                              r.get("external_conversation_id") or "")
        nut = (
            f'<a class="btn sm" href="{escape(link)}" target="_blank" rel="noopener"'
            ' title="Mở hội thoại bên Pancake">💬 Pancake</a>' if link else "—"
        )
        dong += (
            f"<tr><td>{_e(r['customer_code'])}</td>"
            f'<td><a href="/crm/khach-hang/{r["id"]}"><b>{_e(r["full_name"])}</b></a></td>'
            f"<td>{_e(r['primary_phone'])}</td><td>{_e(r['province'])}</td>"
            f"<td><span class='pill'>{_e(r['status'])}</span></td>"
            f"<td>{_dt(r['created_at'])}</td>"
            f'<td>{nut} <a class="btn sm" href="/crm/khach-hang/{r["id"]}">Hồ sơ 360°</a>'
            "</td></tr>"
        )
    loc = loc or {}
    o_tt = "".join(
        f'<option value="{ma}"{" selected" if loc.get("status") == ma else ""}>'
        f"{escape(nhan)}</option>"
        for ma, nhan in [("", "— Mọi trạng thái —"), ("new", "Mới"),
                         ("consulting", "Đang tư vấn"), ("customer", "Đã mua"),
                         ("treating", "Đang dùng liệu trình"),
                         ("completed", "Hoàn thành"), ("churned", "Rời bỏ"),
                         ("blocked", "Chặn")]
    )
    o_nv = "".join(
        f'<option value="{u["id"]}"'
        f'{" selected" if loc.get("owner_id") == u["id"] else ""}>'
        f"{escape(u['name'])}</option>" for u in (nhan_vien or [])
    )
    o_mua = "".join(
        f'<option value="{ma}"{" selected" if loc.get("has_order") == ma else ""}>'
        f"{escape(nhan)}</option>"
        for ma, nhan in [("", "— Đã mua / chưa —"), ("1", "Đã mua"),
                         ("0", "Chưa mua")]
    )
    body = (
        '<form class="card form" method="get" action="/crm/khach-hang" '
        'style="margin-bottom:14px"><div class="grid2">'
        f'<label>Tìm (tên / SĐT / mã)<input type="text" name="q" value="{escape(q)}"></label>'
        f'<label>Trạng thái<select name="status">{o_tt}</select></label>'
        f'<label>Người phụ trách<select name="owner_id">'
        f'<option value="">— Mọi nhân viên —</option>{o_nv}</select></label>'
        f'<label>Mua hàng<select name="has_order">{o_mua}</select></label>'
        "</div>"
        '<div style="margin-top:10px"><button class="btn primary">🔍 Lọc</button> '
        '<a class="btn sm" href="/crm/khach-hang">Xoá lọc</a></div>'
        '<p class="note" style="margin:8px 0 0">Bấm tên khách để mở '
        '<b>hồ sơ 360°</b> (màn 9) · '
        '<a href="/crm/khach-hang/gop-trung">🔗 Hợp nhất khách trùng</a> (màn 10)</p>'
        "</form>"
        + _bang(
            ["Mã", "Họ tên", "Điện thoại", "Tỉnh", "Trạng thái", "Tạo lúc", ""],
            dong, "Không có khách nào khớp bộ lọc",
        )
        + f'<p class="note" style="margin-top:8px">Hiện {len(rows)} / tổng {total} '
          "khách khớp lọc</p>"
    )
    return render_shell("Khách hàng CRM", "crm-customers", body,
                        heading="Khách hàng", sub="Màn 8 — danh sách tất cả khách hàng")


# ------------------------------------- Bảng chăm sóc theo mốc (màn 11 — B3)
# Biểu tượng từng giai đoạn (mã seed ở scripts/seed_danh_muc.py). Giai đoạn tự
# thêm ở màn cấu hình pipeline rơi về dấu chấm tròn.
_LP_ICON = {
    "lead_moi": "🆕", "chua_lien_he": "📞", "da_ket_noi": "🔗",
    "dang_khai_thac": "🔍", "da_tu_van": "💬", "da_bao_gia": "🏷️",
    "dang_can_nhac": "🤔", "hen_goi_lai": "⏰", "can_bam_duoi": "🎯",
    "da_chot": "✅", "khong_phu_hop": "🚫", "tu_choi": "❌", "mat_lien_lac": "📵",
}
# Nhiệt độ lead (crm.leads.temperature — CHECK nong/am/lanh)
_LP_NHIET = {"nong": ("🔥", "Nóng", "lp-hot"),
             "am": ("🌤️", "Ấm", "lp-warm"),
             "lanh": ("❄️", "Lạnh", "lp-cold")}
# Dải nhóm thẻ trong một cột, theo mốc phải chăm tiếp (next_action_at)
_LP_BAND = [("qua_han", "Quá hạn"), ("hom_nay", "Hôm nay"), ("mai", "Ngày mai"),
            ("sap_toi", "Sắp tới"), ("chua_hen", "Chưa đặt hẹn"),
            ("da_dong", "Đã đóng")]


def _lp_url(loc: dict, **doi) -> str:
    """Đường dẫn màn 11 giữ nguyên bộ lọc hiện tại, chỉ đổi vài tham số.

    Giá trị rỗng/0 bị bỏ khỏi query cho URL sạch; khoá bắt đầu bằng `_` là dữ
    liệu phụ mang kèm cho lớp vẽ (vd danh sách nhân viên), không phải bộ lọc."""
    from urllib.parse import urlencode

    p = {**loc, **doi}
    goi = {k: v for k, v in p.items()
           if not k.startswith("_") and v not in ("", 0, None)}
    return "/crm/pipeline" + (f"?{urlencode(goi)}" if goi else "")


def _lp_moc(v) -> tuple[str, str, str]:
    """(mã dải, nhãn hạn, class thẻ) suy từ `next_action_at` của lead."""
    if v is None:
        return "chua_hen", "chưa đặt hẹn", ""
    now = datetime.now().astimezone()
    ngay = (v.astimezone().date() - now.date()).days
    if v.astimezone() < now:
        tre = (now.date() - v.astimezone().date()).days
        return "qua_han", ("quá hạn hôm nay" if tre == 0 else f"quá hạn {tre} ngày"), "od"
    if ngay == 0:
        return "hom_nay", f"hẹn hôm nay {v.astimezone():%H:%M}", ""
    if ngay == 1:
        return "mai", f"hẹn mai {v.astimezone():%H:%M}", ""
    return "sap_toi", f"hẹn {v.astimezone():%d/%m}", ""


def _lp_dai(l: dict) -> tuple[str, str, str]:
    """Như `_lp_moc` nhưng hồ sơ ĐÃ ĐÓNG (giai đoạn kết thúc) thì không còn mốc
    chăm nữa — xếp riêng một dải, khỏi bị tô đỏ 'quá hạn' oan."""
    if l.get("closed_at"):
        return "da_dong", f"đóng {l['closed_at'].astimezone():%d/%m/%Y}", ""
    return _lp_moc(l["next_action_at"])


def _lp_the(l: dict, loc: dict, dang_chon: int) -> str:
    """Một thẻ khách trên cột."""
    _, han, tone = _lp_dai(l)
    link = link_hoi_thoai(l.get("external_page_id") or "",
                          l.get("external_conversation_id") or "")
    chat = (f'<a class="lp-c-chat" href="{escape(link)}" target="_blank" '
            'rel="noopener" title="Mở hội thoại bên Pancake">💬</a>' if link else "")
    bieu, nhan, mau = _LP_NHIET.get(l.get("temperature") or "", ("", "", ""))
    nhiet = (f'<span class="lp-pill {mau}">{bieu} {escape(nhan)}</span>'
             if bieu else "")
    bieu_han = "🔒" if l.get("closed_at") else "⏰"
    meta = [f'<span class="{tone}">{bieu_han} {escape(han)}</span>' if tone
            else f"<span>{bieu_han} {escape(han)}</span>"]
    if l.get("message_count"):
        meta.append(f'<span>✉️ {l["message_count"]}</span>')
    if l.get("owner_name"):
        meta.append(f'<span>👤 {escape(l["owner_name"])}</span>')
    else:
        meta.append('<span class="od">👤 chưa ai nhận</span>')
    lop = " on" if l["id"] == dang_chon else ""
    if tone:
        lop += " od"
    elif l.get("closed_at"):
        lop += " won"
    return (
        f'<div class="lp-card{lop}">'
        f'<a class="lp-card-lk" href="{escape(_lp_url(loc, st=l["stage_id"], lead=l["id"]))}">'
        f'<span class="lp-c-top"><span class="lp-c-name">{_e(l["full_name"])}</span>'
        f"{nhiet}</span>"
        f'<span class="lp-c-meta">{"".join(meta)}</span></a>'
        f"{chat}</div>"
    )


def _lp_cot(s: dict, loc: dict, mau: str, dang_chon: int) -> str:
    """Một cột giai đoạn: đầu cột (màu riêng) + thẻ chia theo dải mốc."""
    nhom: dict[str, list[str]] = {}
    for l in s["leads"]:
        band, _, _ = _lp_dai(l)
        nhom.setdefault(band, []).append(_lp_the(l, loc, dang_chon))
    than = ""
    for ma, nhan in _LP_BAND:
        if ma in nhom:
            than += (f'<div class="lp-band">{escape(nhan)}'
                     f"<span>{len(nhom[ma])}</span></div>" + "".join(nhom[ma]))
    if not than:
        than = '<div class="lp-col-e">Không có khách nào ở cột này</div>'
    con = s["so_lead"] - len(s["leads"])
    if con > 0:
        than += (f'<div class="lp-band">'
                 f'<a href="{escape(_lp_url(loc, st=s["id"], lead=0))}">'
                 f"còn {con} khách nữa — xem cả cột →</a></div>")
    return (
        f'<section class="lp-col{" closed" if s["is_closed"] else ""}" '
        f'style="--c:{mau}">'
        f'<header class="lp-col-h"><span>{_LP_ICON.get(s["code"], "●")}</span>'
        f'<a class="lp-col-t" href="{escape(_lp_url(loc, st=s["id"], lead=0))}">'
        f'{escape(s["name"])}</a>'
        f'<span class="lp-col-n">{s["so_lead"]}</span></header>'
        f'<div class="lp-col-b">{than}</div></section>'
    )


def _lp_khung_lam_viec(lead: dict | None, loc: dict, nhan_vien: list[dict],
                       ly_do: list[dict]) -> str:
    """Khung làm việc bên phải — hồ sơ khách đang chọn + thao tác thật.

    Mỗi thao tác là một form POST riêng (không JS): chuyển giai đoạn đi qua đủ
    luật chặn FR-040 ở lead_service, sai luật thì route đẩy lỗi lên dải flash.
    """
    if lead is None:
        return (
            '<div class="lp-pane"><div class="lp-pane-empty">'
            "<div style='font-size:34px'>🎯</div>"
            "<h3>Chọn một khách để bắt đầu chăm</h3>"
            "<p>Bấm vào thẻ khách bên trái để mở hồ sơ: đổi giai đoạn, đặt lịch "
            "nhắc lại, chia lại cho nhân viên khác và xem nhật ký chuyển cột.</p>"
            "</div></div>"
        )
    ve = _lp_url(loc, st=lead["stage_id"], lead=lead["id"])
    goc = f"/crm/pipeline/{lead['id']}"
    link = link_hoi_thoai(lead.get("external_page_id") or "",
                          lead.get("external_conversation_id") or "")

    # --- đầu khung: tên + lối tắt sang hồ sơ 360° / hội thoại Pancake ---
    nut = (f'<a class="lp-btn ghost" href="/crm/khach-hang/{lead["customer_id"]}">'
           "👤 Hồ sơ 360°</a>")
    if link:
        nut += (f'<a class="lp-btn ghost" href="{escape(link)}" target="_blank" '
                'rel="noopener">💬 Pancake</a>')
    bieu, nhan, mau = _LP_NHIET.get(lead.get("temperature") or "", ("", "", ""))
    nhiet = f'<span class="lp-pill {mau}">{bieu} {escape(nhan)}</span>' if bieu else ""
    dau = (
        '<div class="lp-dw-h"><div class="lp-dw-h1">'
        f'<h2>{_e(lead["full_name"])}</h2>{nhiet}'
        f'<span style="margin-left:auto">{nut}</span></div>'
        '<div class="lp-dw-h2">'
        f'<span>📞 {_e(lead["primary_phone"])}</span>'
        f'<span>📍 {_e(lead["province"])}</span>'
        f'<span>👤 {_e(lead.get("owner_name"))}</span>'
        f'<span>🏷️ {_e(lead.get("page_name") or lead.get("source"))}</span>'
        "</div></div>"
    )

    # --- giai đoạn: mỗi nút là một lần chuyển cột, kèm lý do + lịch hẹn ---
    buoc = ""
    for s in lead["stages"]:
        bieu_gd = _LP_ICON.get(s["code"], "●")
        if s["id"] == lead["stage_id"]:
            buoc += (f'<span class="lp-step on">{bieu_gd} '
                     f'{escape(s["name"])}</span>')
        else:
            buoc += (f'<button class="lp-step" name="stage_id" value="{s["id"]}">'
                     f'{bieu_gd} {escape(s["name"])}</button>')
    o_ly_do = "".join(
        f'<option value="{r["id"]}">{escape(r["name"])}</option>'
        for r in (ly_do or [])
    )
    khoi_gd = (
        '<div class="lp-dw-s"><div class="lp-dw-lbl">Giai đoạn theo dõi</div>'
        f'<form method="post" action="{goc}/giai-doan">'
        f'<input type="hidden" name="ve" value="{escape(ve)}">'
        f'<div class="lp-steps">{buoc}</div>'
        '<div class="lp-inl" style="margin-top:10px">'
        '<input type="text" name="reason" style="flex:1;min-width:200px" '
        'placeholder="Lý do / ghi chú (bắt buộc với Đã báo giá · Đang cân nhắc)">'
        '<input type="datetime-local" name="next_action_at" '
        'title="Lịch hẹn tiếp theo — bắt buộc với Đang cân nhắc">'
        f'<select name="lost_reason_id" title="Lý do chuẩn khi đóng hồ sơ">'
        f'<option value="">— Lý do chưa mua (khi Từ chối / Không phù hợp / '
        f"Mất liên lạc) —</option>{o_ly_do}</select>"
        "</div>"
        '<p class="lp-mut" style="margin:8px 0 0">Luật FR-040: '
        '<b>Đã chốt</b> phải có đơn hàng · <b>Từ chối / Không phù hợp / Mất liên '
        "lạc</b> phải chọn lý do chuẩn ở ô trên.</p>"
        "</form></div>"
    )

    # --- các con số của lead ---
    _, han, _ = _lp_dai(lead)
    o_cot = ""
    if lead.get("stage_entered_at"):
        ngay = (datetime.now().astimezone()
                - lead["stage_entered_at"].astimezone()).days
        o_cot = f"{ngay} ngày"
    khoi_so = (
        '<div class="lp-dw-s"><div class="lp-dw-lbl">Thông tin &amp; mốc</div>'
        '<div class="lp-facts">'
        f'<div><span>Vào ngày</span><b>{_d(lead["created_at"])}</b></div>'
        f'<div><span>Ở cột này</span><b>{o_cot or "—"}</b></div>'
        f'<div><span>Mốc chăm tiếp</span><b>{escape(han)}</b></div>'
        f'<div><span>Chạm đầu tiên</span>'
        f'<b>{_dt(lead["first_contact_at"]) if lead.get("first_contact_at") else "chưa"}</b></div>'
        f'<div><span>Tin nhắn</span><b>{lead.get("message_count") or 0}</b></div>'
        f'<div><span>Mã khách</span><b>{_e(lead["customer_code"])}</b></div>'
        "</div></div>"
    )

    # --- thao tác nhanh: đặt nhắc · đổi nhiệt độ · chia lại ---
    o_nv = "".join(
        f'<option value="{u["id"]}">{escape(u["name"])}</option>'
        for u in nhan_vien
    )
    o_nhiet = (
        '<option value="" disabled'
        f'{" selected" if not lead.get("temperature") else ""}>— chưa chấm —</option>'
        + "".join(
            f'<option value="{ma}"'
            f'{" selected" if lead.get("temperature") == ma else ""}>'
            f"{bieu} {escape(ten)}</option>"
            for ma, (bieu, ten, _) in _LP_NHIET.items()
        )
    )
    khoi_tt = (
        '<div class="lp-dw-s"><div class="lp-dw-lbl">Thao tác nhanh</div>'
        f'<form class="lp-inl" method="post" action="{goc}/hen">'
        f'<input type="hidden" name="ve" value="{escape(ve)}">'
        '<input type="datetime-local" name="next_action_at" required>'
        '<button class="lp-btn">⏰ Đặt nhắc lại</button></form>'
        f'<form class="lp-inl" method="post" action="{goc}/nhiet" '
        'style="margin-top:9px">'
        f'<input type="hidden" name="ve" value="{escape(ve)}">'
        f'<select name="temperature">{o_nhiet}</select>'
        '<button class="lp-btn ghost">🌡️ Đổi nhiệt độ</button></form>'
        f'<form class="lp-inl" method="post" action="{goc}/chia-lai" '
        'style="margin-top:9px">'
        f'<input type="hidden" name="ve" value="{escape(ve)}">'
        f'<select name="owner_id" required>'
        f'<option value="">— Chia lại cho… —</option>{o_nv}</select>'
        '<input type="text" name="reason" placeholder="Lý do chuyển (FR-031)">'
        '<button class="lp-btn ghost">🤝 Chuyển người</button></form>'
        "</div>"
    )

    # --- nhật ký chuyển cột (lead_stage_history) ---
    dong = "".join(
        f"<li><time>{_dt(h['changed_at'])}</time><div>"
        + (f"{_e(h['from_stage_name'])} → " if h.get("from_stage_name") else "Tạo mới → ")
        + f"<b>{_e(h['to_stage_name'])}</b>"
        + (f" · {escape(h['changed_by_name'])}" if h.get("changed_by_name") else "")
        + (f"<div class='lp-mut'>{escape(h['reason'])}</div>" if h.get("reason") else "")
        + "</div></li>"
        for h in lead["lich_su"]
    )
    khoi_ls = (
        '<div class="lp-dw-s"><div class="lp-dw-lbl">Nhật ký chăm sóc</div>'
        + (f'<ul class="lp-log">{dong}</ul>' if dong
           else '<div class="lp-mut">Chưa có hoạt động nào được ghi lại.</div>')
        + "</div>"
    )
    return f'<div class="lp-pane">{dau}{khoi_gd}{khoi_so}{khoi_tt}{khoi_ls}</div>'


def _lp_thanh_loc(loc: dict, nhan_vien: list[dict]) -> str:
    """Thanh lọc: tìm kiếm · nhân viên · nhiệt độ · thời điểm tạo · Pipeline|Bảng."""
    from datetime import date, timedelta

    o_nv = "".join(
        f'<option value="{u["id"]}"'
        f'{" selected" if str(loc.get("owner_id")) == str(u["id"]) else ""}>'
        f"{escape(u['name'])}</option>" for u in nhan_vien
    )
    o_nhiet = "".join(
        f'<option value="{ma}"{" selected" if loc.get("temperature") == ma else ""}>'
        f"{escape(nhan)}</option>"
        for ma, nhan in [("", "— Mọi nhiệt độ —"), ("nong", "🔥 Nóng"),
                         ("am", "🌤️ Ấm"), ("lanh", "❄️ Lạnh")]
    )
    o_moc = "".join(
        f'<option value="{ma}"{" selected" if loc.get("moc") == ma else ""}>'
        f"{escape(nhan)}</option>"
        for ma, nhan in [("", "— Mọi mốc chăm —"), ("qua_han", "⏰ Quá hạn"),
                         ("hom_nay", "📅 Hẹn hôm nay"),
                         ("chua_hen", "❔ Chưa đặt hẹn")]
    )
    # Nút sẵn cho khoảng ngày: là LIÊN KẾT (giữ nguyên bộ lọc còn lại) nên
    # không cần một dòng JS nào.
    hom_nay = date.today()
    dau_thang = hom_nay.replace(day=1)
    thang_truoc_cuoi = dau_thang - timedelta(days=1)
    san = [
        ("Hôm nay", hom_nay, hom_nay),
        ("Hôm qua", hom_nay - timedelta(days=1), hom_nay - timedelta(days=1)),
        ("7 ngày qua", hom_nay - timedelta(days=6), hom_nay),
        ("30 ngày qua", hom_nay - timedelta(days=29), hom_nay),
        ("90 ngày qua", hom_nay - timedelta(days=89), hom_nay),
        ("Đầu tháng đến nay", dau_thang, hom_nay),
        ("Tháng trước", thang_truoc_cuoi.replace(day=1), thang_truoc_cuoi),
    ]
    chip = "".join(
        f'<a class="lp-chip'
        f'{" on" if loc.get("tu") == a.isoformat() and loc.get("den") == b.isoformat() else ""}"'
        f' href="{escape(_lp_url(loc, tu=a.isoformat(), den=b.isoformat(), lead=0))}">'
        f"{escape(ten)}</a>"
        for ten, a, b in san
    )
    nhan_ky = (f'{loc["tu"] or "…"} → {loc["den"] or "…"}'
               if (loc.get("tu") or loc.get("den")) else "Mọi thời điểm")
    an = "".join(
        f'<input type="hidden" name="{k}" value="{escape(str(loc.get(k) or ""))}">'
        for k in ("st", "xem") if loc.get(k)
    )
    xem = loc.get("xem") or "pipeline"
    return (
        '<div class="lp-fbar">'
        '<form class="lp-frow" method="get" action="/crm/pipeline">'
        f"{an}"
        '<span class="lp-search">🔍<input type="text" name="q" '
        f'value="{escape(str(loc.get("q") or ""))}" '
        'placeholder="Tìm tên · SĐT · mã khách"></span>'
        f'<select class="lp-sel" name="owner_id">'
        f'<option value="">— Mọi nhân viên —</option>{o_nv}</select>'
        f'<select class="lp-sel" name="temperature">{o_nhiet}</select>'
        f'<select class="lp-sel" name="moc">{o_moc}</select>'
        '<details class="lp-ct"><summary>📅 '
        f"<b>{escape(nhan_ky)}</b> ▾</summary>"
        '<div class="lp-ctpop"><div class="lp-ctpop-h">Lọc theo thời điểm tạo'
        "<span> · ngày khách vào hội thoại</span></div>"
        f'<div class="lp-ctpre">{chip}</div>'
        '<div class="lp-ctrange">'
        f'<label>Từ ngày<input type="date" name="tu" '
        f'value="{escape(str(loc.get("tu") or ""))}"></label>'
        f'<label>Đến ngày<input type="date" name="den" '
        f'value="{escape(str(loc.get("den") or ""))}"></label></div>'
        '<div class="lp-ctpop-f"><button class="lp-btn">Áp dụng</button>'
        f'<a class="lp-btn ghost" href="{escape(_lp_url(loc, tu=0, den=0, lead=0))}">'
        "Xoá khoảng ngày</a></div></div></details>"
        '<button class="lp-btn">Lọc</button>'
        f'<a class="lp-btn ghost" href="{escape(_lp_url({"st": loc.get("st")}))}">'
        "Xoá lọc</a>"
        '<span style="margin-left:auto"></span>'
        '<span class="lp-toggle">'
        f'<a class="{"on" if xem != "bang" else ""}" '
        f'href="{escape(_lp_url(loc, xem=0))}">▦ Pipeline</a>'
        f'<a class="{"on" if xem == "bang" else ""}" '
        f'href="{escape(_lp_url(loc, xem="bang", lead=0))}">☰ Bảng</a></span>'
        "</form></div>"
    )


def _lp_bang(stages: list[dict], loc: dict) -> str:
    """Chế độ 'Bảng' — mỗi giai đoạn một khối xổ/thu, bên trong là danh sách."""
    from app.web.shell import mau_giai_doan

    khoi = ""
    dau_tien = True                       # khối đầu tiên xổ sẵn cho đỡ trống trơn
    for i, s in enumerate(stages):
        if not s["so_lead"]:
            continue
        dong = ""
        for l in s["leads"]:
            _, han, tone = _lp_dai(l)
            bieu, nhan, mau = _LP_NHIET.get(l.get("temperature") or "", ("", "", ""))
            dong += (
                '<div class="lp-tr">'
                f'<span><a href="{escape(_lp_url(loc, st=s["id"], lead=l["id"], xem=0))}">'
                f'<b>{_e(l["full_name"])}</b></a></span>'
                f'<span>{_e(l["primary_phone"])}</span>'
                f'<span>{_e(l.get("owner_name"))}</span>'
                f'<span class="{tone}">⏰ {escape(han)}</span>'
                + (f'<span class="lp-pill {mau}">{bieu} {escape(nhan)}</span>'
                   if bieu else "<span>—</span>")
                + "</div>"
            )
        con = s["so_lead"] - len(s["leads"])
        if con > 0:
            dong += (f'<div class="lp-tr"><span><a href="'
                     f'{escape(_lp_url(loc, st=s["id"], xem=0))}">'
                     f"còn {con} khách nữa — mở cột →</a></span></div>")
        st = int(loc.get("st") or 0)
        xo = s["id"] == st if st else dau_tien
        dau_tien = False
        khoi += (
            f'<details class="lp-acc" style="--c:{mau_giai_doan(i)}"'
            f'{" open" if xo else ""}>'
            f'<summary><span>{_LP_ICON.get(s["code"], "●")}</span>'
            f'<span class="lp-acc-t">{escape(s["name"])}</span>'
            f'<span class="lp-acc-n">{s["so_lead"]} khách</span><span>▾</span></summary>'
            '<div class="lp-th"><span>Khách</span><span>Điện thoại</span>'
            "<span>Phụ trách</span><span>Mốc chăm</span><span>Nhiệt độ</span></div>"
            f"{dong}</details>"
        )
    return (f'<div class="lp-tbl">{khoi}</div>' if khoi else
            '<div class="lp-empty">Không có khách tiềm năng nào khớp bộ lọc.</div>')


def render_pipeline(board: dict, *, st: int = 0, lead: dict | None = None,
                    loc: dict | None = None, nhan_vien: list[dict] | None = None,
                    ly_do: list[dict] | None = None,
                    ok_msg: str = "", error: str = "") -> str:
    """Màn 11 — bảng chăm sóc theo mốc (bố cục Kallet).

    board  — `crm_screens_repo.pipeline_board()`: {"stages": [...], "kpi": {...}}
    st     — cột đang mở (0 = xem hết các cột); có `st` thì bày thêm khung làm
             việc bên phải cho khách đang chọn.
    lead   — `crm_screens_repo.pipeline_lead()` của khách đang chọn (có thể None)
    loc    — bộ lọc hiện hành (q/owner_id/temperature/moc/tu/den/xem) để dựng lại
             mọi liên kết mà không mất lọc.
    ly_do  — danh mục lý do chưa mua (crm.lead_reasons) cho ô đóng hồ sơ.
    """
    from app.web.shell import flash, mau_giai_doan

    loc = dict(loc or {})
    nhan_vien = nhan_vien or []
    ly_do = ly_do or []
    stages = board.get("stages") or []
    kpi = board.get("kpi") or {}
    xem = loc.get("xem") or "pipeline"
    # Màu cột = màu chấm cùng giai đoạn ở menu trái (theo sort_order)
    mau_cot = {s["id"]: mau_giai_doan(i) for i, s in enumerate(stages)}

    tong = kpi.get("tong") or 0
    ti_le = f"{(kpi.get('da_chot') or 0) * 100 / tong:.1f}%" if tong else "—"
    cot_chot = next((s for s in stages if s["code"] == "da_chot"), None)
    url_chot = _lp_url(loc, st=(cot_chot or {}).get("id") or 0,
                       moc=0, temperature=0, lead=0)
    dai_kpi = (
        '<div class="lp-kpi">'
        f'<a class="{"on" if not (loc.get("temperature") or loc.get("moc")) else ""}" '
        f'href="{escape(_lp_url(loc, temperature=0, moc=0, lead=0))}">'
        f'<b>{tong}</b><span>Tất cả khách tiềm năng</span></a>'
        f'<a class="{"on" if loc.get("temperature") == "nong" else ""}" '
        f'href="{escape(_lp_url(loc, temperature="nong", moc=0, lead=0))}">'
        f'<b>{kpi.get("nong") or 0}</b><span>🔥 Đang nóng</span></a>'
        f'<a class="{"on" if loc.get("moc") == "qua_han" else ""}" '
        f'href="{escape(_lp_url(loc, moc="qua_han", temperature=0, lead=0))}">'
        f'<b>{kpi.get("qua_han") or 0}</b><span>⏰ Quá hạn chăm</span></a>'
        f'<a class="{"on" if cot_chot and st == cot_chot["id"] else ""}" '
        f'href="{escape(url_chot)}">'
        f'<b>{kpi.get("da_chot") or 0}</b><span>✅ Đã chốt</span></a>'
        f'<div class="lp-kpi-flat"><b>{ti_le}</b><span>Tỉ lệ chốt</span></div>'
        "</div>"
    )

    dang_xem = ""
    cot = next((s for s in stages if s["id"] == st), None) if st else None
    if cot:
        mau = mau_cot[cot["id"]]
        dang_xem = (
            '<div class="lp-fbar"><div class="lp-frow">'
            '<span class="lp-flbl">Đang xem cột:</span>'
            f'<span class="lp-chip on" style="background:{mau};border-color:{mau}">'
            f'{_LP_ICON.get(cot["code"], "●")} '
            f'{escape(cot["name"])} · {cot["so_lead"]}</span>'
            f'<a class="lp-chip" href="{escape(_lp_url(loc, st=0, lead=0))}">'
            "Xem tất cả cột</a></div></div>"
        )

    quy_tac = (
        '<details class="lp-rules"><summary>⚙️ <b>Quy tắc tự động</b>'
        '<span class="lp-mut"> — luật đang chạy khi chuyển cột, bấm để xem</span>'
        '<span style="margin-left:auto">▾</span></summary>'
        '<div class="lp-rules-b"><ul>'
        "<li>Khách mới phải có người nhận trong <b>5 phút</b>, "
        "phải chạm được khách trong <b>15 phút</b> (FR-042) — quá hạn thì thẻ "
        "hiện <b>chưa ai nhận</b>.</li>"
        "<li>Chuyển <b>Đã báo giá</b> phải ghi liệu trình + giá đã báo vào lý do.</li>"
        "<li>Chuyển <b>Đang cân nhắc</b> phải có lý do <i>và</i> lịch hẹn tiếp theo.</li>"
        "<li>Chuyển <b>Đã chốt</b> chỉ được khi khách <b>đã có đơn hàng</b>.</li>"
        "<li>Đóng ở <b>Từ chối · Không phù hợp · Mất liên lạc</b> phải có "
        "lý do chuẩn (danh mục lý do chưa mua).</li>"
        "<li>Sang <b>Đã kết nối</b> hệ thống tự ghi mốc <b>chạm đầu tiên</b>.</li>"
        "</ul>"
        '<div class="lp-rules-n">Mọi lần chuyển cột đều ghi <b>nhật ký</b> '
        "(ai chuyển, từ cột nào, lý do) — xem ở khung làm việc bên phải.</div>"
        "</div></details>"
    )

    if xem == "bang":
        than = _lp_bang(stages, loc)
    else:
        hien = [s for s in stages if s["id"] == st] if st else stages
        cot_html = "".join(
            _lp_cot(s, loc, mau_cot[s["id"]], (lead or {}).get("id") or 0)
            for s in hien
        )
        if not cot_html:
            cot_html = ('<div class="lp-empty">Chưa có giai đoạn nào — chạy '
                        "<code>scripts/seed_danh_muc.py</code> để nạp pipeline "
                        "Bán mới.</div>")
        khung = _lp_khung_lam_viec(lead, loc, nhan_vien, ly_do) if st else ""
        than = (f'<div class="lp-board{" one" if st else ""}">'
                f"{cot_html}{khung}</div>")

    body = (flash(ok_msg, error) + dai_kpi + _lp_thanh_loc(loc, nhan_vien)
            + dang_xem + quy_tac + than)
    hom_nay = datetime.now().astimezone().strftime("%d/%m/%Y")
    return render_shell(
        "Khách tiềm năng", "crm-pipeline", body,
        heading="Bảng chăm sóc theo mốc",
        sub=f"Khách tiềm năng của Sale, xếp theo giai đoạn bám đuổi · {hom_nay}",
    )


# ------------------------------------------------------------ Công việc (màn 12/26)
def render_cong_viec(nhom: dict, *, pham_vi: str = "minh") -> str:
    from app.services.task_service import LOAI_VIEC  # nhãn tiếng Việt 8 loại việc

    def _rows(items):
        return "".join(
            f"<tr><td>{_e(LOAI_VIEC.get(t['task_type'], t['task_type']))}"
            + (f"<div class='note' style='margin:2px 0 0'>{_e(t['title'])}</div>"
               if t.get("title") else "")
            + f"</td><td>{_e(t['khach'])}</td>"
            f"<td>{_e(t['nguoi_lam'])}</td><td>{_dt(t['due_at'])}</td>"
            f"<td><span class='pill'>{_e(t['priority'])}</span></td>"
            f"<td>{_e(t['status'])}</td></tr>"
            for t in items
        )

    # Chuyển phạm vi: việc của tôi (mặc định) <-> cả đội
    nut = (
        '<a class="btn sm" href="/crm/cong-viec?pham_vi=tatca">Xem cả đội</a>'
        if pham_vi != "tatca"
        else '<a class="btn sm" href="/crm/cong-viec">Chỉ việc của tôi</a>'
    )
    cols = ["Loại việc", "Khách", "Người làm", "Hạn", "Ưu tiên", "Trạng thái"]
    body = (
        f'<div class="card" style="margin-bottom:14px;display:flex;gap:10px;'
        f'align-items:center"><b>{"Việc của tôi" if pham_vi != "tatca" else "Cả đội"}</b>'
        f"{nut}<span class='note' style='margin:0'>quá hạn được worker quét 5'/lần, "
        "đánh dấu + ghi nhật ký báo quản lý (mục 19 BRD)</span></div>"
        + f'<div class="card"><h3>🔴 Quá hạn ({len(nhom["qua_han"])})</h3>'
        + _bang(cols, _rows(nhom["qua_han"]), "Không có việc quá hạn") + "</div>"
        + f'<div class="card" style="margin-top:14px"><h3>Hôm nay ({len(nhom["hom_nay"])})</h3>'
        + _bang(cols, _rows(nhom["hom_nay"]), "Hôm nay chưa có việc") + "</div>"
        + f'<div class="card" style="margin-top:14px"><h3>Sắp tới ({len(nhom["sap_toi"])})</h3>'
        + _bang(cols, _rows(nhom["sap_toi"]), "Chưa có việc xếp lịch") + "</div>"
    )
    return render_shell("Công việc", "crm-tasks", body,
                        heading="Công việc", sub="Màn 12 + 26 — việc của Sale và CSKH (B4)")


# ------------------------------------------------------------ Đơn hàng (màn 21)
_TT_DON = [
    ("draft", "Nháp"), ("confirmed", "Đã xác nhận"), ("packing", "Đang xử lý"),
    ("shipping", "Đang giao"), ("delivered", "Giao thành công"),
    ("returned", "Hoàn"), ("cancelled", "Huỷ"),
]


def render_don_hang(data: dict, loc: dict | None = None) -> str:
    loc = loc or {}
    pills = "".join(
        f'<a class="stat link" href="/crm/don-hang?status={ma}">'
        f'<div class="s-label">{escape(nhan)}</div>'
        f'<div class="s-value">{data["theo_trang_thai"].get(ma, {}).get("n", 0)}</div>'
        "</a>"
        for ma, nhan in _TT_DON
    )
    o_tt = "".join(
        f'<option value="{ma}"{" selected" if loc.get("status") == ma else ""}>'
        f"{escape(nhan)}</option>"
        for ma, nhan in [("", "— Mọi trạng thái —"), *_TT_DON,
                         ("pending", "Chờ xác nhận"),
                         ("awaiting_shipment", "Chờ gửi"),
                         ("collected", "Đã thu tiền"), ("returning", "Đang hoàn")]
    )
    o_loai = "".join(
        f'<option value="{ma}"{" selected" if loc.get("order_type") == ma else ""}>'
        f"{escape(nhan)}</option>"
        for ma, nhan in [("", "— Mọi loại —"), ("new", "Đơn đầu"),
                         ("repurchase", "Mua lại"), ("upsell", "Bán thêm"),
                         ("exchange", "Đổi hàng")]
    )
    form = (
        '<form class="card form" method="get" action="/crm/don-hang" '
        'style="margin:14px 0"><div class="grid2">'
        f'<label>Tìm (khách / SĐT / mã đơn)<input type="text" name="q" '
        f'value="{escape(str(loc.get("q") or ""))}"></label>'
        f'<label>Trạng thái<select name="status">{o_tt}</select></label>'
        f'<label>Loại đơn<select name="order_type">{o_loai}</select></label>'
        f'<label>Từ ngày<input type="date" name="tu" '
        f'value="{escape(str(loc.get("tu") or ""))}"></label>'
        "</div>"
        '<div style="margin-top:10px"><button class="btn primary">🔍 Lọc</button> '
        '<a class="btn sm" href="/crm/don-hang">Xoá lọc</a></div></form>'
    )
    dong = ""
    for r in data["rows"]:
        ma = _e(r["external_order_id"]) if r["external_order_id"] else f"#{r['id']}"
        loai = "mua lại" if r["order_type"] == "repurchase" else _e(r["order_type"])
        dong += (
            f'<tr><td><a href="/crm/don-hang/{r["id"]}">{ma}</a></td>'
            f"<td>{_e(r['khach'])}</td><td>{_e(r['sale'])}</td><td>{loai}</td>"
            f"<td><span class='pill'>{_e(r['status'])}</span></td>"
            f"<td>{_tien(r['total_amount'])}</td><td>{_dt(r['created_at'])}</td>"
            f'<td><a class="btn sm" href="/crm/don-hang/{r["id"]}">Chi tiết</a></td></tr>'
        )
    # Python 3.11: không lồng f-string cùng loại nháy -> dựng sẵn phần đuôi
    duoi_tong = f" / tổng {data['tong']} khớp lọc" if data.get("tong") else ""
    body = (
        f'<div class="stats">{pills}</div>' + form
        + _bang(["Mã đơn", "Khách", "Sale", "Loại", "Trạng thái", "Giá trị",
                 "Tạo lúc", ""],
                dong, "Không có đơn nào khớp bộ lọc")
        + f'<p class="note" style="margin-top:8px">Hiện {len(data["rows"])} đơn'
          f"{duoi_tong}</p>"
    )
    return render_shell("Đơn hàng", "crm-orders", body,
                        heading="Đơn hàng",
                        sub="Màn 21 — danh sách đơn, bấm ô trạng thái để lọc nhanh")


# ------------------------------------------------------------ Chăm sóc (màn 26-27)
def render_cham_soc(data: dict) -> str:
    """Màn 27 (B9 — THẬT): pipeline C01-C09 đếm từ care_plans.cskh_state,
    mốc chờ làm, danh sách kế hoạch đang chạy (bấm vào mở phiếu chăm)."""
    cot = "".join(
        f'<div class="kcol"><h4>{escape(c["code"])} · {escape(c["name"])}'
        f'<span class="kcount">{c["n"]}</span></h4></div>'
        for c in data["cot"]
    )
    moc = "".join(
        f"<tr><td><span class='pill'>{_e(m['step_code'])}</span></td>"
        f"<td>{_e(m['khach'])}</td><td>{_e(m['phu_trach'])}</td>"
        f"<td>{_dt(m['planned_at'])}</td><td>{_e(m['status'])}</td>"
        f"<td><a class='btn sm' href='/crm/cham-soc/{m['care_plan_id']}'>Mở phiếu</a></td></tr>"
        for m in data["moc"]
    )
    kh = "".join(
        f"<tr><td><a href='/crm/cham-soc/{k['id']}'><b>{_e(k['khach'])}</b></a></td>"
        f"<td><span class='pill'>{_e(k['cskh_state'])}</span></td>"
        f"<td>LT{k['cycle_no']}</td><td>{_d(k['actual_start_date'])}</td>"
        f"<td>{k['moc_xong']}/{k['moc_tong']}</td><td>{_e(k['phu_trach'])}</td></tr>"
        for k in data["ke_hoach"]
    )
    so = data["so"]
    body = (
        '<div class="stats">'
        + stat("Kế hoạch đang chăm", str(so["ke_hoach_chay"]))
        + stat("Mốc đến hạn", str(so["moc_den_han"]),
               tone="warn" if so["moc_den_han"] else "")
        + stat("Khách ngừng liên hệ", str(so["ngung_lien_he"]),
               tone="err" if so["ngung_lien_he"] else "")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Pipeline CSKH C01-C09 '
          '(màn 27)</h3><div class="kanban">' + cot + "</div></div>"
        + '<div class="card" style="margin-top:14px"><h3>Mốc chăm chờ làm</h3>'
        + _bang(["Mốc", "Khách", "Phụ trách", "Lịch hẹn", "Trạng thái", ""], moc,
                "Chưa có mốc chờ — kế hoạch sinh tự động khi đơn giao thành công (B8)")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Kế hoạch đang chạy</h3>'
        + _bang(["Khách", "Cột", "Chu kỳ", "Bắt đầu dùng", "Mốc xong", "Phụ trách"],
                kh, "Chưa có kế hoạch chăm nào")
        + "</div>"
    )
    return render_shell("Chăm sóc", "crm-care", body,
                        heading="Chăm sóc sau bán",
                        sub="Màn 27 — pipeline C01-C09 + mốc CS01-CS11 (B9, dữ liệu thật)")


# ------------------------------------------------------ phiếu chăm (màn 28-38)
# Nhãn tiếng Việt cho trường phiếu — trường lạ tự hiện bằng chính tên mã
_NHAN_TRUONG = {
    "order_confirmed": "Xác nhận đúng đơn", "amount_confirmed": "Xác nhận số tiền",
    "address_confirmed": "Xác nhận địa chỉ", "next_contact_at": "Hẹn liên hệ tiếp",
    "received_status": "Tình trạng nhận hàng", "zalo_connected": "Đã kết nối Zalo",
    "guidance_sent": "Đã gửi hướng dẫn", "care_owner_id": "Người chăm (id)",
    "actual_start_date": "Ngày bắt đầu dùng THẬT", "started": "Đã bắt đầu dùng?",
    "not_started_reason": "Lý do chưa dùng", "rescheduled_start_date": "Hẹn ngày bắt đầu",
    "adherence_level": "Mức tuân thủ", "adverse_event": "Phản ứng bất lợi",
    "bowel_status": "Tình trạng phân", "symptom_snapshot": "Triệu chứng hiện tại",
    "meal_relation": "Liên quan bữa ăn", "diet_compliance": "Thực hiện chế độ ăn",
    "symptom_change": "Triệu chứng thay đổi", "score_before": "Điểm trước (0-10)",
    "score_current": "Điểm hiện tại (0-10)", "response_level": "Mức đáp ứng",
    "consultation_note": "Ghi chú tư vấn", "remaining_quantity": "Số sản phẩm còn",
    "estimated_end_date": "Ngày dự kiến hết", "repurchase_readiness": "Mức sẵn sàng",
    "objection_primary": "Băn khoăn chính", "response_summary": "Tổng kết kết quả",
    "recommendation_id": "Mã đề xuất (nếu có)", "repurchase_status": "Kết quả mua lại",
    "followup_at": "Lịch theo sát", "lost_reason": "Lý do chưa mua",
    "objection_evidence": "Bằng chứng chat/call", "next_action": "Hành động tiếp",
    "do_not_contact": "Khách yêu cầu NGỪNG liên hệ", "cycle_no": "Chu kỳ",
    "next_repurchase_date": "Hẹn mua tiếp", "maintenance_plan": "Kế hoạch duy trì",
    "next_review_at": "Hẹn đánh giá lại", "repurchase_status_note": "Ghi chú",
}
_CHECKBOX = {"order_confirmed", "amount_confirmed", "address_confirmed",
             "zalo_connected", "guidance_sent", "do_not_contact"}
_MAP_DUONG = {  # step_code -> đường phiếu API/web (khớp care_service._PHIEU_MOC)
    "CS01": "order-confirmation", "CS02": "onboarding", "CS03": "start-usage",
    "CS04": "day-4", "CS05": "day-10", "CS06": "day-15", "CS07": "day-20",
    "CS08": "day-25", "CS09": "day-28", "CS10": "treatment-2", "CS11": "treatment-3",
}


def _o_nhap(truong: str, bo: dict[str, list[str]], rs: list[tuple[str, str]]) -> str:
    """Một ô nhập của phiếu — kiểu ô suy từ TÊN trường (bộ giá trị → select,
    *_date/_at → lịch, điểm → số, xác nhận → checkbox, còn lại → text)."""
    nhan = escape(_NHAN_TRUONG.get(truong, truong))
    if truong in bo:
        opts = "".join(f'<option value="{escape(v)}">{escape(v)}</option>'
                       for v in bo[truong])
        return (f'<label>{nhan}<select name="{truong}">'
                f'<option value="">—</option>{opts}</select></label>')
    if truong == "received_status":
        return (f'<label>{nhan}<select name="received_status">'
                '<option value="">—</option><option value="du_hang">Đủ hàng</option>'
                '<option value="thieu_loi">Thiếu/lỗi hàng</option>'
                '<option value="chua_nhan">Chưa nhận</option></select></label>')
    if truong == "repurchase_status":
        return (f'<label>{nhan}<select name="repurchase_status">'
                '<option value="">—</option><option value="da_mua">Đã mua</option>'
                '<option value="hen_mua">Hẹn mua</option>'
                '<option value="chua_mua">Chưa mua</option>'
                '<option value="tu_choi">Từ chối</option></select></label>')
    if truong == "response_level":
        opts = "".join(f'<option value="{ma}">{ma} — {escape(ten)}</option>'
                       for ma, ten in rs)
        return (f'<label>{nhan}<select name="response_level">'
                f'<option value="">—</option>{opts}</select></label>')
    if truong == "started":
        return (f'<label>{nhan}<select name="started">'
                '<option value="true">Đã dùng</option>'
                '<option value="false">Chưa dùng</option></select></label>')
    if truong in _CHECKBOX:
        return (f'<label class="ck"><input type="checkbox" name="{truong}" '
                f'value="true"> {nhan}</label>')
    if truong.endswith("_date"):
        return f'<label>{nhan}<input type="date" name="{truong}"></label>'
    if truong.endswith("_at"):
        return f'<label>{nhan}<input type="datetime-local" name="{truong}"></label>'
    if truong in ("score_before", "score_current"):
        return (f'<label>{nhan}<input type="number" name="{truong}" '
                'min="0" max="10" step="1"></label>')
    if truong.endswith("_id") or truong.endswith("_quantity") or truong == "cycle_no":
        return f'<label>{nhan}<input type="number" name="{truong}"></label>'
    return f'<label>{nhan}<input type="text" name="{truong}"></label>'


def render_ke_hoach_cham(
    plan: dict, buoc: dict[str, dict], bo: dict[str, list[str]],
    rs: list[tuple[str, str]], *, chuoi: dict | None = None,
    ok_msg: str = "", error: str = "",
) -> str:
    """Màn 28-38 gộp MỘT màn: dòng thời gian 11 mốc + phiếu của mốc đang mở
    (trường bắt buộc đọc từ ref_codes — thêm trường là việc seed, khỏi sửa màn)."""
    from app.web.shell import flash

    dong_moc = ""
    form_html = ""
    for s in plan["steps"]:
        code = s["step_code"] or "khac"
        thong_tin = buoc.get(code, {})
        mau = {"done": "✅", "skipped": "⏭️", "due": "🔴", "failed": "⚠️"}.get(
            s["status"], "⬜")
        dong_moc += (
            f"<tr><td>{mau} <b>{escape(code)}</b></td>"
            f"<td>{_e(thong_tin.get('name'))}</td><td>{_dt(s['planned_at'])}</td>"
            f"<td>{_e(s['status'])}</td><td>{_e(s['result_code'])}</td>"
            f"<td>{_dt(s['completed_at'])}</td></tr>"
        )
        # phiếu cho mốc MỞ sớm nhất (due trước, pending sau) — mỗi lần 1 phiếu
        if not form_html and s["status"] in ("due", "pending") \
                and code in _MAP_DUONG:
            o_nhap = "".join(_o_nhap(t, bo, rs)
                             for t in (thong_tin.get("du_lieu_bat_buoc") or []))
            duong = _MAP_DUONG[code]
            form_html = (
                f'<div class="card" style="margin-top:14px">'
                f"<h3>Phiếu {escape(code)} — {_e(thong_tin.get('name'))}</h3>"
                f"<p class='note'>Kích hoạt: {_e(thong_tin.get('kich_hoat'))} · "
                f"Kênh: {_e(thong_tin.get('kenh'))} · Ngoại lệ: "
                f"{_e(thong_tin.get('ngoai_le'))}</p>"
                f'<form class="form" method="post" '
                f'action="/crm/cham-soc/{plan["id"]}/phieu/{duong}">'
                '<div class="grid2">'
                '<label>Kết quả liên hệ<select name="contact_result">'
                + "".join(f'<option value="{escape(v)}">{escape(v)}</option>'
                          for v in bo.get("contact_result", ["Kết nối"]))
                + "</select></label>"
                + o_nhap
                + '<label>Ghi chú<input type="text" name="note"></label>'
                "</div>"
                '<button class="btn primary" style="margin-top:10px">Lưu phiếu</button>'
                "</form>"
                f'<form method="post" action="/crm/cham-soc/moc/{s["id"]}/bo-qua" '
                'style="margin-top:8px;display:flex;gap:8px">'
                '<input type="text" name="reason" placeholder="Lý do bỏ qua (bắt buộc)">'
                '<button class="btn sm">Bỏ qua mốc</button></form>'
                "</div>"
            )
    # --- màn 38: chuỗi không phản hồi (FR-110) — nhắn → gọi → nhắn → gọi ---
    _KENH = {1: ("message", "Nhắn tin"), 2: ("call", "Gọi điện"),
             3: ("message", "Nhắn tin"), 4: ("call", "Gọi điện")}
    if chuoi:
        lan_ke = len(chuoi.get("attempts") or []) + 1
        dong_cham = "".join(
            f"<tr><td>Lần {a['attempt_no']}</td>"
            f"<td>{'Nhắn' if a['channel'] == 'message' else 'Gọi'}</td>"
            f"<td>{_e(a['result'])}</td><td>{_e(a['note'])}</td>"
            f"<td>{_dt(a['attempted_at'])}</td></tr>"
            for a in (chuoi.get("attempts") or [])
        )
        kq_opts = "".join(
            f'<option value="{escape(v)}">{escape(v)}</option>'
            for v in bo.get("contact_result", []))
        if lan_ke <= 4:
            ma_kenh, ten_kenh = _KENH[lan_ke]
            form_cham = (
                f'<form method="post" action="/crm/cham-soc/chuoi/{chuoi["id"]}/cham" '
                'class="form" style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">'
                f'<input type="hidden" name="channel" value="{ma_kenh}">'
                f"<b>Lần {lan_ke}/4 — {ten_kenh}</b>"
                f'<label>Kết quả<select name="result">{kq_opts}</select></label>'
                '<label>Ghi chú<input type="text" name="note"></label>'
                '<button class="btn primary">Ghi lần chạm</button></form>'
            )
        else:
            form_cham = '<p class="note">Đã đủ 4 lần — chuỗi sẽ tự đóng.</p>'
        chuoi_html = (
            '<div class="card" style="margin-top:14px">'
            "<h3>📵 Chuỗi không phản hồi đang chạy (màn 38)</h3>"
            + _bang(["Lần", "Kênh", "Kết quả", "Ghi chú", "Lúc"], dong_cham,
                    "Chưa ghi lần chạm nào — thứ tự chuẩn: nhắn → gọi → nhắn → gọi")
            + form_cham
            + f'<form method="post" action="/crm/cham-soc/chuoi/{chuoi["id"]}/dong" '
              'style="margin-top:8px;display:flex;gap:8px">'
              '<select name="outcome"><option value="responded">Khách đã phản hồi</option>'
              '<option value="lost_contact">Tạm mất liên lạc (C08)</option>'
              '<option value="do_not_contact">Khách yêu cầu dừng</option></select>'
              '<input type="text" name="reason" placeholder="Lý do">'
              '<button class="btn sm">Đóng chuỗi</button></form>'
            + "</div>"
        )
    else:
        chuoi_html = (
            '<div class="card" style="margin-top:14px">'
            "<h3>📵 Không phản hồi (màn 38)</h3>"
            '<p class="note">Khách im lặng? Mở chuỗi chuẩn FR-110: nhắn → gọi → '
            "nhắn → gọi; đủ 4 lần chưa được thì tự chuyển Tạm mất liên lạc (C08).</p>"
            f'<form method="post" action="/crm/cham-soc/{plan["id"]}/chuoi/mo">'
            '<button class="btn">Mở chuỗi không phản hồi</button></form></div>'
        )
    # AU11 — khách chủ động đòi dừng mọi liên hệ
    chuoi_html += (
        '<div class="card" style="margin-top:14px"><h3>⛔ Ngừng liên hệ (AU11)</h3>'
        f'<form method="post" action="/crm/cham-soc/{plan["id"]}/ngung-lien-he" '
        'style="display:flex;gap:8px">'
        '<input type="text" name="reason" placeholder="Lý do (bắt buộc)" style="flex:1">'
        '<button class="btn sm" style="color:var(--err)">Khách yêu cầu DỪNG</button>'
        "</form><p class='note' style='margin:8px 0 0'>Dừng mọi automation: mốc chờ "
        "bỏ qua, chuỗi đóng, pipeline về C09 — chỉ mở lại khi khách đồng ý mới.</p></div>"
    )

    khach_note = ""
    if plan.get("do_not_contact"):
        khach_note = ('<div class="flash err">⛔ Khách đã yêu cầu NGỪNG liên hệ '
                      "(C09) — không ghi phiếu mới</div>")
        form_html = ""
        chuoi_html = ""
    body = (
        flash(ok_msg, error)
        + khach_note
        + '<div class="stats">'
        + stat("Khách", _e(plan["customer_name"]))
        + stat("Cột pipeline", _e(plan["cskh_state"]))
        + stat("Chu kỳ", f"LT{plan['cycle_no']}")
        + stat("Bắt đầu dùng thật", _d(plan.get("actual_start_date")),
               hint="mốc 4/10/15/20/25 tính từ ngày này (FR-102)")
        + stat("Người chăm", _e(plan.get("owner_name")))
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>11 mốc chăm (CS01-CS11)</h3>'
        + _bang(["Mốc", "Tên", "Lịch hẹn", "Trạng thái", "Kết quả", "Hoàn thành"],
                dong_moc, "Chưa sinh mốc — bấm sinh mốc hoặc chờ B8 tạo")
        + "</div>"
        + form_html
        + chuoi_html
    )
    return render_shell(
        f"Chăm sóc — {plan['customer_name']}", "crm-care", body,
        heading=f"Kế hoạch chăm #{plan['id']} — {plan['customer_name']}",
        sub="Màn 28-38 — phiếu theo mốc; trường bắt buộc đọc từ danh mục BRD bảng 18",
    )


# ------------------------------------------------------------ Mua lại (màn 39-40)
_STAGE_MUA_LAI = {          # nhãn bước do NGƯỜI làm (cột stage DB)
    "identified": "Mới nhận diện", "contacted": "Đang tư vấn",
    "negotiating": "Chờ quyết định", "won": "Đã mua", "lost": "Chưa mua",
    "postponed": "Hoãn",
}


def render_mua_lai(rows: list[dict], nhan_dem: list[tuple[str, str, int]],
                   *, ok_msg: str = "", error: str = "") -> str:
    """Màn 39-40 (B10 — THẬT): 9 nhãn FR-122 suy từ ngày + bảng cơ hội có nút
    chuyển bước ngay trên dòng (lost bắt lý do — service chặn)."""
    from app.services.repurchase_service import TRANSITIONS
    from app.web.shell import flash

    pills = "".join(
        f'<div class="stat{" warn" if ma in ("den_han", "qua_han") and n else ""}">'
        f'<div class="s-label">{escape(ten)}</div><div class="s-value">{n}</div></div>'
        for ma, ten, n in nhan_dem
    )
    dong = ""
    for r in rows:
        buoc_ke = sorted(TRANSITIONS.get(r["stage"], set()))
        form = "—"
        if buoc_ke:
            opts = "".join(
                f'<option value="{b}">{escape(_STAGE_MUA_LAI.get(b, b))}</option>'
                for b in buoc_ke)
            form = (
                f'<form method="post" action="/crm/mua-lai/{r["id"]}/chuyen" '
                'style="display:flex;gap:4px">'
                f'<select name="stage">{opts}</select>'
                '<input type="text" name="reason" placeholder="lý do (nếu chưa mua)" '
                'style="width:120px"><button class="btn sm">Chuyển</button></form>'
            )
        dong += (
            f"<tr><td><b>{_e(r['customer_name'])}</b></td>"
            f"<td>{_e(r['owner_name'])}</td>"
            f"<td><span class='pill'>{_e(r.get('display_label'))}</span>"
            f"<div class='note' style='margin:2px 0 0'>"
            f"{escape(_STAGE_MUA_LAI.get(r['stage'], r['stage']))}</div></td>"
            f"<td>{_d(r['expected_close_date'])}</td>"
            f"<td>{_tien(r['expected_value'])}</td>"
            f"<td>{_e(r.get('readiness'))}</td>"
            f"<td>{_e(r.get('next_template_name'))}</td><td>{form}</td></tr>"
        )
    body = (
        flash(ok_msg, error)
        + f'<div class="stats">{pills}</div>'
        + '<div class="card" style="margin-top:14px"><h3>Cơ hội mua lại '
          '(màn 39-40)</h3>'
        + _bang(["Khách", "Phụ trách", "Trạng thái", "Ngày hết dự kiến",
                 "Giá trị", "Sẵn sàng", "LT tiếp theo", "Chuyển bước"],
                dong, "Chưa có cơ hội — tự sinh từ phiếu chăm ngày 20 (B9)")
        + '</div><p class="note" style="margin-top:8px">Trạng thái thời gian '
          "(chưa/sắp/đến hạn/quá hạn/khách ngủ) tự suy từ ngày hết dự kiến — "
          'khách im ắng lâu xem ở <a href="/crm/khach-ngu">màn Khách ngủ (41)</a>.</p>'
    )
    return render_shell("Mua lại", "crm-repurchase", body,
                        heading="Mua lại",
                        sub="Màn 39-40 — pipeline FR-122 (B10, dữ liệu thật)")


# ------------------------------------------------------------ Khách ngủ (màn 41)
def render_khach_ngu(
    data: dict, bao_cao: list[dict], cskh: list[dict], *,
    tu_ngay: int, gia_tri_tu: str = "", ok_msg: str = "", error: str = "",
) -> str:
    """Màn 41 (B10 — THẬT): rổ 30/60/90/180 ngày + gán chiến dịch tái kích hoạt
    + báo cáo doanh thu từng chiến dịch (FR-123)."""
    from app.web.shell import flash

    tab = "".join(
        f'<a class="btn sm{" primary" if tu_ngay == n else ""}" '
        f'href="/crm/khach-ngu?tu_ngay={n}">≥ {n} ngày '
        f'({data["buckets"].get(str(n), 0) if tu_ngay <= n else "…"})</a>'
        for n in (30, 60, 90, 180)
    )
    dong = "".join(
        f'<tr><td><input type="checkbox" name="ids" value="{r["id"]}" '
        f'form="f-gan"></td>'
        f"<td><b>{_e(r['full_name'])}</b></td><td>{_e(r['primary_phone'])}</td>"
        f"<td>{_dt(r['lan_cuoi'])}</td><td><b>{r['ngay_ngu']}</b> ngày</td>"
        f"<td>{_tien(r['tong_mua'])}</td><td>{r['so_don']}</td>"
        f"<td>{'📣 #' + str(r['campaign_id']) if r['campaign_id'] else '—'}</td></tr>"
        for r in data["items"]
    )
    opts_cd = "".join(
        f'<option value="{c["id"]}">{escape(c["name"])}</option>'
        for c in bao_cao if c["status"] == "running")
    opts_cskh = "".join(
        f'<option value="{u["id"]}">{escape(u["name"])}</option>' for u in cskh)
    form_gan = (
        '<form id="f-gan" method="post" action="/crm/khach-ngu/gan" class="form" '
        'style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">'
        f'<label>Chiến dịch có sẵn<select name="campaign_id">'
        f'<option value="">— tạo mới —</option>{opts_cd}</select></label>'
        '<label>Hoặc tên chiến dịch mới<input type="text" name="ten_moi" '
        'placeholder="vd: Đánh thức T8"></label>'
        f'<label>Giao cho<select name="assigned_to"><option value="">—</option>'
        f"{opts_cskh}</select></label>"
        '<label class="ck"><input type="checkbox" name="tao_viec" value="1" checked> '
        "Tạo việc mua lại</label>"
        '<button class="btn primary">Gán khách đã tick</button></form>'
    )
    bc = "".join(
        f"<tr><td>{_e(c['name'])}</td><td>{_e(c['status'])}</td>"
        f"<td>{c['so_khach']}</td><td>{c['chuyen_doi']}</td>"
        f"<td><b>{_tien(c['doanh_thu'])}</b></td><td>{_dt(c['start_at'])}</td></tr>"
        for c in bao_cao
    )
    body = (
        flash(ok_msg, error)
        + '<div class="card" style="display:flex;gap:8px;align-items:center;'
          f'flex-wrap:wrap"><b>Ngưỡng ngủ:</b>{tab}'
          '<form method="get" action="/crm/khach-ngu" style="display:flex;gap:6px">'
          f'<input type="hidden" name="tu_ngay" value="{tu_ngay}">'
          f'<input type="number" name="gia_tri_tu" value="{escape(gia_tri_tu)}" '
          'placeholder="Tổng mua từ (₫)" style="width:150px">'
          '<button class="btn sm">Lọc giá trị</button></form></div>'
        + f'<div class="card" style="margin-top:14px"><h3>Khách ngủ ≥ {tu_ngay} '
          f'ngày ({len(data["items"])})</h3>'
        + _bang(["✓", "Khách", "Điện thoại", "Mua lần cuối", "Ngủ", "Tổng mua",
                 "Số đơn", "Chiến dịch"], dong,
                "Không có khách ngủ ở ngưỡng này 🎉")
        + form_gan + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Doanh thu tái kích hoạt '
          "theo chiến dịch</h3>"
        + _bang(["Chiến dịch", "Trạng thái", "Số khách", "Chuyển đổi",
                 "Doanh thu sau gán", "Bắt đầu"], bc,
                "Chưa có chiến dịch — tick khách rồi gán ở trên")
        + "</div>"
    )
    return render_shell("Khách ngủ", "crm-sleeping", body,
                        heading="Khách ngủ & tái kích hoạt",
                        sub="Màn 41 — FR-123: ngưỡng 30/60/90/180 ngày, doanh thu đo tự động khi khách có đơn mới")


# ------------------------------------------------------------ Sản phẩm (màn 42/44)
def render_san_pham(data: dict) -> str:
    sp = "".join(
        f"<tr><td>{_e(r['product_code'])}</td>"
        f'<td><a href="/crm/san-pham/sp/{r["id"]}"><b>{_e(r["name"])}</b></a></td>'
        f"<td>{_e(r['product_type'])}</td><td>{_tien(r['price'])}</td>"
        f"<td>{_e(r['status'])}</td><td>{_e(r['approval_status'])}</td>"
        f'<td><a class="btn sm" href="/crm/san-pham/sp/{r["id"]}">Chi tiết</a></td></tr>'
        for r in data["san_pham"]
    )
    lt = "".join(
        f"<tr><td>{_e(r['template_code'])}</td>"
        f'<td><a href="/crm/san-pham/lieu-trinh/{r["id"]}"><b>{_e(r["name"])}</b></a></td>'
        f"<td>{_e(r['problem_group'])}</td><td>{_e(r['level'])}</td>"
        f"<td>{_tien(r['base_price'])}</td><td>{_e(r['duration_days'])} ngày</td>"
        f"<td>{_e(r['status'])}</td>"
        f'<td><a class="btn sm" href="/crm/san-pham/lieu-trinh/{r["id"]}">Chi tiết</a> '
        f'<a class="btn sm" href="/crm/san-pham/lieu-trinh/{r["id"]}/luat">⚙️ Luật</a>'
        "</td></tr>"
        for r in data["lieu_trinh"]
    )
    trong_dm = ""
    if not data["san_pham"] and not data["lieu_trinh"]:
        trong_dm = ('<div class="flash warn" style="margin-bottom:14px">⚠ Danh mục đang '
                    "TRỐNG — chưa nhập sản phẩm/mẫu liệu trình thật. Chưa nhập thì màn "
                    "<b>Đề xuất liệu trình</b> (màn 15) không có gì để gợi ý.</div>")
    body = (
        trong_dm
        + '<div class="card"><h3>Sản phẩm (màn 42)</h3>'
        + _bang(["Mã", "Tên", "Nhóm", "Giá", "Bán", "Kiểm duyệt", ""], sp,
                "Chưa có sản phẩm nào trong danh mục")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Mẫu liệu trình (màn 44)</h3>'
        + _bang(["Mã", "Tên", "Nhóm vấn đề", "Cấp", "Giá", "Thời gian",
                 "Trạng thái", ""],
                lt, "Chưa có mẫu liệu trình nào")
        + "</div>"
    )
    return render_shell("Sản phẩm & liệu trình", "crm-products", body,
                        heading="Sản phẩm & liệu trình",
                        sub="Màn 42 + 44 — danh mục bán hàng")


# ------------------------------------------------------------ Bàn giao (màn 24-25)
_TT_BAN_GIAO = {
    "pending":   ("Chờ gán CSKH", "warn"),
    "assigned":  ("Chờ nhận", ""),
    "accepted":  ("Đã nhận", "ok"),
    "returned":  ("Trả lại Sale", "err"),
    "completed": ("Hoàn tất", "ok"),
}


def _pill_tt(status: str) -> str:
    nhan, tone = _TT_BAN_GIAO.get(status, (status, ""))
    return f"<span class='pill {tone}'>{escape(nhan)}</span>"


def render_ban_giao(rows: list[dict], total: int, dem: dict, tt: str) -> str:
    """Màn 24 — danh sách khách chờ bàn giao (B8, dữ liệu THẬT)."""
    chip = "".join(
        f'<a class="btn sm{" primary" if tt == ma else ""}" '
        f'href="/crm/ban-giao{f"?tt={ma}" if ma else ""}">{escape(nhan)}'
        f'{f" · {dem[ma]}" if dem.get(ma) else ""}</a> '
        for ma, nhan in [("", "Tất cả"), ("cho", "Chờ xử lý"),
                         ("accepted", "Đã nhận"), ("returned", "Trả lại")]
    )
    dong = ""
    for r in rows:
        ho_so = ("<span class='pill ok'>Đủ</span>" if r["is_complete"] else
                 f"<span class='pill err'>Thiếu {len(r['missing_fields'] or [])}</span>")
        dong += (
            f"<tr><td><b>{_e(r['customer_name'])}</b>"
            f"<div class='note'>{_e(r['customer_phone'])}</div></td>"
            f"<td>{_e(r['sale_name'])}</td>"
            f"<td>{_e(r['order_code'])}<div class='note'>{_tien(r['order_amount'])}</div></td>"
            f"<td>{_e(r['treatment_name'] or r['treatment_summary'])}</td>"
            f"<td>{_dt(r['delivered_at'])}</td><td>{_e(r['cskh_name'])}</td>"
            f"<td>{ho_so}</td><td>{_pill_tt(r['status'])}</td>"
            f"<td><a class='btn sm' href='/crm/ban-giao/{r['id']}'>Mở phiếu</a></td></tr>"
        )
    body = (
        '<div class="stats">'
        + stat("Chờ gán CSKH", str(dem.get("pending", 0)),
               tone="warn" if dem.get("pending") else "")
        + stat("Chờ nhận", str(dem.get("assigned", 0)))
        + stat("Trả lại Sale", str(dem.get("returned", 0)),
               tone="err" if dem.get("returned") else "")
        + stat("Đã nhận", str(dem.get("accepted", 0)), tone="ok")
        + "</div>"
        + f'<div style="margin:14px 0 10px">{chip}</div>'
        + _bang(
            ["Khách", "Sale chốt", "Đơn", "Liệu trình", "Giao lúc", "CSKH",
             "Hồ sơ", "Trạng thái", ""],
            dong,
            "Chưa có phiếu — đơn chuyển 'giao thành công' sẽ tự sinh phiếu (FR-090)",
        )
        + f'<p class="note" style="margin-top:8px">Tổng: {total} phiếu</p>'
    )
    return render_shell("Bàn giao CSKH", "crm-handover", body,
                        heading="Bàn giao Sale → CSKH",
                        sub="Màn 24 — đơn giao thành công tự sinh phiếu, "
                            "CSKH nhận khi hồ sơ đủ (FR-090/091)")


def render_phieu_ban_giao(h: dict, cskh: list[dict],
                          ok_msg: str = "", error: str = "") -> str:
    """Màn 25 — phiếu bàn giao: 8 trường bắt buộc (thiếu tô đỏ) + hành động."""
    thieu = set(h.get("thieu") or [])

    def o(cot: str, nhan: str, bat_buoc: bool = True) -> str:
        do = " style='border-color:#e5484d'" if bat_buoc and nhan in thieu else ""
        sao = " *" if bat_buoc else ""
        return (f"<label>{escape(nhan)}{sao}<textarea name='{cot}' rows='2'{do}>"
                f"{escape(str(h.get(cot) or ''))}</textarea></label>")

    form_phieu = (
        f'<form class="card form" method="post" action="/crm/ban-giao/{h["id"]}/luu">'
        "<h3>Nội dung phiếu (FR-091 — 8 trường * bắt buộc)</h3><div class='grid2'>"
        + o("customer_condition", "Tình trạng khách")
        + o("treatment_summary", "Liệu trình")
        + o("dose_text", "Cách dùng")
        + o("notes", "Lưu ý")
        + o("comorbidities", "Bệnh nền")
        + o("current_medications", "Thuốc đang dùng")
        + o("concerns", "Băn khoăn")
        + o("cskh_watch_points", "Vấn đề CSKH cần theo dõi")
        + o("main_symptoms", "Triệu chứng chính", False)
        + o("sale_discussed", "Điều Sale đã trao đổi", False)
        + o("promises_made", "Cam kết đã nói", False)
        + ("<label>Ngày dự kiến bắt đầu<input type='date' name='expected_start_date' "
           f"value='{h['expected_start_date'] or ''}'></label>")
        + "</div><button class='btn primary' style='margin-top:10px'>💾 Lưu phiếu</button>"
          "</form>"
    )

    opt = "".join(
        f"<option value='{u['id']}'{' selected' if u['id'] == h.get('cskh_user_id') else ''}>"
        f"{escape(u['name'])}</option>" for u in cskh)
    hanh_dong = ""
    if h["status"] in ("pending", "assigned"):
        hanh_dong = (
            '<div class="card" style="margin-top:14px"><h3>Hành động</h3>'
            f'<form method="post" action="/crm/ban-giao/{h["id"]}/nhan" '
            'style="display:inline-block;margin-right:8px">'
            '<button class="btn primary">✅ Nhận bàn giao</button></form>'
            f'<form method="post" action="/crm/ban-giao/{h["id"]}/gan" '
            'style="display:inline-block;margin-right:8px">'
            f'<select name="user_id">{opt}</select> '
            '<button class="btn sm">👤 Gán CSKH</button></form>'
            f'<form method="post" action="/crm/ban-giao/{h["id"]}/tra-lai" '
            'style="display:inline-block">'
            '<input type="text" name="reason" placeholder="Lý do trả lại *" required> '
            '<button class="btn sm">↩ Trả lại Sale</button></form>'
            "<p class='note' style='margin-top:8px'>Hồ sơ thiếu thì KHÔNG nhận được "
            "— bổ sung phiếu hoặc trả lại Sale (FR-091)</p></div>"
        )
    elif h["status"] == "returned":
        hanh_dong = (
            '<div class="flash warn" style="margin-top:14px">↩ Phiếu đã trả lại Sale'
            f" — lý do: <b>{_e(h.get('returned_reason'))}</b>. Sale bổ sung đủ 8 trường"
            " là phiếu tự quay lại Chờ nhận.</div>"
        )

    canh_bao = ""
    if thieu:
        canh_bao = ('<div class="flash warn" style="margin-bottom:14px">⚠ Thiếu: '
                    + escape(" · ".join(sorted(thieu))) + "</div>")
    if ok_msg:
        canh_bao = f'<div class="flash ok" style="margin-bottom:14px">{escape(ok_msg)}</div>' + canh_bao
    if error:
        canh_bao = f'<div class="flash err" style="margin-bottom:14px">{escape(error)}</div>' + canh_bao

    tom_tat = (
        '<div class="card" style="margin-bottom:14px"><h3>'
        f"{_e(h['customer_name'])} {_pill_tt(h['status'])}</h3>"
        f"<p class='note'>SĐT {_e(h['customer_phone'])} · Đơn {_e(h['order_code'])} "
        f"({_tien(h['order_amount'])}) · Giao {_dt(h['delivered_at'])} · "
        f"Sale chốt: {_e(h['sale_name'])} · CSKH: {_e(h['cskh_name'])}</p></div>"
    )
    body = (
        f'<p style="margin-bottom:10px"><a class="btn sm" href="/crm/ban-giao">← Danh sách</a></p>'
        + canh_bao + tom_tat + form_phieu + hanh_dong
    )
    return render_shell("Phiếu bàn giao", "crm-handover", body,
                        heading=f"Phiếu bàn giao #{h['id']}",
                        sub="Màn 25 — nội dung Sale bàn giao cho CSKH")


# ------------------------------------------------------------ Thông báo (màn 3)
_ICON_TB = {
    "lead_moi": "🆕", "viec_sap_den_han": "⏰", "viec_qua_han": "🔴",
    "khach_can_goi_lai": "📞", "khach_co_phan_ung": "⚠️",
    "khach_can_chuyen_chuyen_mon": "🩺", "don_giao_thanh_cong": "📦",
    "don_hoan": "↩️", "khach_den_han_mua_lai": "🔄",
    "noi_dung_cho_duyet": "📝", "loi_dong_bo": "🔌",
}
_TONE_TB = {"urgent": "err", "high": "warn", "normal": "", "low": ""}


def render_thong_bao(rows: list[dict], total: int, dem: dict,
                     loai: dict, tt_loc: str, chi_chua_doc: bool,
                     cai_dat: list[dict], ok_msg: str = "") -> str:
    """Màn 3 — trung tâm thông báo: 11 loại, lọc, đánh dấu đã đọc, cài đặt."""
    # Python 3.11 trên máy này: KHÔNG lồng nháy cùng loại trong f-string, không
    # backslash trong biểu thức f-string -> dựng sẵn từng mảnh ra biến.
    tong_chua_doc = dem["tong"]
    hau_to_tong = f" · {tong_chua_doc}" if tong_chua_doc else ""
    on_tat_ca = "" if (tt_loc or chi_chua_doc) else " primary"
    on_chua_doc = " primary" if (chi_chua_doc and not tt_loc) else ""
    chip = (
        f'<a class="btn sm{on_tat_ca}" href="/crm/thong-bao">Tất cả</a> '
        f'<a class="btn sm{on_chua_doc}" href="/crm/thong-bao?chua_doc=1">'
        f"Chưa đọc{hau_to_tong}</a> "
    )
    for ma, (nhan, _uu, _link) in loai.items():
        so = dem["theo_loai"].get(ma, 0)
        hau_to = f" · {so}" if so else ""
        on = " primary" if tt_loc == ma else ""
        chip += (
            f'<a class="btn sm{on}" href="/crm/thong-bao?type={ma}">'
            f"{_ICON_TB.get(ma, '')} {escape(nhan)}{hau_to}</a> "
        )

    dong = ""
    for r in rows:
        moi = r["read_at"] is None
        tone = _TONE_TB.get(r["priority"], "")
        nut = (
            f'<form method="post" action="/crm/thong-bao/{r["id"]}/da-doc" '
            'style="display:inline"><button class="btn sm">✓ Đã đọc</button></form>'
            if moi else '<span class="note">đã đọc</span>'
        )
        mo = (f'<a class="btn sm" href="{escape(r["link"])}">Mở</a> '
              if r.get("link") else "")
        dam = ' style="font-weight:600"' if moi else ""
        nhan_loai = loai.get(r["type"], (r["type"],))[0]
        dong += (
            f"<tr{dam}>"
            f'<td>{_ICON_TB.get(r["type"], "•")}</td>'
            f'<td>{_e(r["title"])}'
            f'<div class="note" style="font-weight:400">{_e(r["body"])}</div></td>'
            f'<td><span class="pill {tone}">{_e(nhan_loai)}</span></td>'
            f'<td>{_dt(r["created_at"])}</td><td>{mo}{nut}</td></tr>'
        )

    o_cai_dat = ""
    for c in cai_dat:
        tick = " checked" if c["enabled"] else ""
        o_cai_dat += (
            '<label style="display:flex;gap:8px;align-items:center">'
            f'<input type="checkbox" name="{c["type"]}"{tick}>'
            f'<span>{_ICON_TB.get(c["type"], "")} {escape(c["label"])}</span></label>'
        )

    body = (
        (f'<div class="flash ok" style="margin-bottom:14px">{escape(ok_msg)}</div>'
         if ok_msg else "")
        + '<div class="stats">'
        + stat("Chưa đọc", str(tong_chua_doc), tone="warn" if tong_chua_doc else "")
        + stat("Tổng thông báo", str(total))
        + "</div>"
        + '<div style="margin:14px 0 10px;display:flex;gap:6px;flex-wrap:wrap;'
          'align-items:center">' + chip
        + ('<form method="post" action="/crm/thong-bao/doc-het" '
           'style="margin-left:auto"><button class="btn">✓ Đánh dấu tất cả đã đọc'
           "</button></form>" if tong_chua_doc else "")
        + "</div>"
        + _bang(["", "Nội dung", "Loại", "Lúc", ""], dong,
                "Không có thông báo nào — worker quét 5 phút/lần "
                "(bật/tắt ở Quản trị → Cài đặt)")
        + '<details class="card" style="margin-top:14px"><summary>'
          "<b>⚙️ Cài đặt thông báo của tôi (NOTIFY-004)</b></summary>"
          '<form method="post" action="/crm/thong-bao/cai-dat" style="margin-top:10px">'
          '<div class="grid2">' + o_cai_dat + "</div>"
          '<p class="note" style="margin:8px 0">Bỏ tick loại nào là ngừng nhận '
          "loại đó — chỉ ảnh hưởng tài khoản của bạn.</p>"
          '<button class="btn primary">💾 Lưu cài đặt</button></form></details>'
    )
    return render_shell("Thông báo", "crm-notify", body,
                        heading="Trung tâm thông báo",
                        sub="Màn 3 — 11 loại: khách tiềm năng mới · việc đến hạn/quá hạn · "
                            "khách cần gọi lại · phản ứng · chuyển chuyên môn · "
                            "đơn giao/hoàn · mua lại · chờ duyệt · lỗi đồng bộ")
