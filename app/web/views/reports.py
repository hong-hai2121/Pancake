"""Màn báo cáo B11: màn 4 (tổng quan) · 5-6 (dashboard Sale/CSKH) ·
60-64 (báo cáo kỳ) · trang drill-down FR-173.

Nguyên tắc FR-173: MỌI ô số là <a> trỏ /crm/bao-cao/chi-tiet?metric=…
với ĐÚNG kỳ lọc đang xem — số và danh sách không bao giờ lệch nhau.
Biểu đồ vẽ SVG thuần (không JS lib) — đủ đọc xu hướng, nhẹ trang.
"""

from html import escape

from app.web.shell import render_shell, stat, tabs_bar


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _tien(v) -> str:
    try:
        return f"{float(v):,.0f} ₫".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _so_hien(v) -> str:
    if v is None:
        return "—"
    f = float(v)
    return f"{f:,.0f}".replace(",", ".") if f == int(f) else f"{f:,.1f}"


def _bang(cols: list[str], rows_html: str, rong: str) -> str:
    head = "".join(f"<th>{escape(str(c))}</th>" for c in cols)
    body = rows_html or (f'<tr><td colspan="{len(cols)}" class="note">'
                         f"{escape(rong)}</td></tr>")
    return (f'<div class="tblwrap card"><table class="tbl"><thead><tr>{head}'
            f"</tr></thead><tbody>{body}</tbody></table></div>")


def _o(metric: str, nhan: str, gia_tri, ky: dict, *, tien: bool = False,
       tone: str = "", user_id: int | None = None) -> str:
    """Ô số bấm được — FR-173."""
    href = (f"/crm/bao-cao/chi-tiet?metric={metric}&tu={ky['tu']}&den={ky['den']}"
            + (f"&user_id={user_id}" if user_id else ""))
    return stat(nhan, _tien(gia_tri) if tien else _so_hien(gia_tri),
                tone=tone, href=href)


def _loc_ky(duong: str, ky: dict, them: str = "", hidden: str = "") -> str:
    return (f'<form class="card form" method="get" action="{duong}" '
            'style="margin-bottom:14px;display:flex;gap:8px;align-items:end;'
            'flex-wrap:wrap">'
            f"{hidden}{them}"
            f'<label>Từ ngày<input type="date" name="tu" value="{ky["tu"]}"></label>'
            f'<label>Đến ngày<input type="date" name="den" value="{ky["den"]}"></label>'
            '<button class="btn primary">Xem kỳ này</button></form>')


def _bieu_do_cot(ngay: list[dict]) -> str:
    """Doanh thu theo ngày — cột SVG thuần; hover ra số (title)."""
    if not ngay:
        return '<p class="note">Chưa có doanh thu trong kỳ</p>'
    cao_max = max(float(r["tong"]) for r in ngay) or 1
    w, h, gap = 18, 120, 4
    cot = ""
    for i, r in enumerate(ngay):
        tong, mua_lai = float(r["tong"]), float(r["mua_lai"])
        ch = round(tong / cao_max * (h - 10))
        cm = round(mua_lai / cao_max * (h - 10))
        x = i * (w + gap)
        cot += (
            f'<g><title>{r["ngay"]}: {_tien(tong)} ({r["so_don"]} đơn, '
            f"mua lại {_tien(mua_lai)})</title>"
            f'<rect x="{x}" y="{h - ch}" width="{w}" height="{ch}" rx="2" '
            'fill="var(--accent)" opacity="0.85"/>'
            f'<rect x="{x}" y="{h - cm}" width="{w}" height="{cm}" rx="2" '
            'fill="var(--hot)"/></g>'
        )
    rong = len(ngay) * (w + gap)
    return (f'<div style="overflow-x:auto"><svg width="{rong}" height="{h}" '
            f'viewBox="0 0 {rong} {h}">{cot}</svg></div>'
            '<p class="note" style="margin:4px 0 0">█ tổng · '
            '<span style="color:var(--hot)">█</span> phần mua lại — '
            "di chuột lên cột để xem số</p>")


def _pheu(pheu: list[dict], ky: dict) -> str:
    max_n = max((p["n"] for p in pheu), default=0) or 1
    dong = ""
    for p in pheu:
        rong = round(p["n"] / max_n * 100)
        dong += (
            f'<a class="fun-row" href="/crm/bao-cao/chi-tiet?metric={p["metric"]}'
            f'&tu={ky["tu"]}&den={ky["den"]}" style="display:flex;gap:10px;'
            'align-items:center;text-decoration:none;margin:4px 0">'
            f'<span style="width:130px">{escape(p["buoc"])}</span>'
            f'<span style="flex:1;background:var(--soft);border-radius:6px">'
            f'<span style="display:block;width:{max(rong, 2)}%;height:18px;'
            'background:var(--accent);border-radius:6px;opacity:0.8"></span></span>'
            f"<b style='width:70px;text-align:right'>{_so_hien(p['n'])}</b></a>"
        )
    return dong


# ------------------------------------------------------------ màn 4
def render_tong_quan(data: dict, user: dict | None) -> str:
    ky, so, ti_le = data["ky"], data["so"], data["ti_le"]
    tiles = (
        '<div class="stats">'
        + _o("khach_moi", "Khách mới", so["khach_moi"], ky)
        + _o("hoi_thoai_moi", "Hội thoại mới", so["hoi_thoai_moi"], ky)
        + _o("lead_moi", "Lead mới", so["lead_moi"], ky)
        + _o("lead_chua_lien_he", "Lead chưa liên hệ", so["lead_chua_lien_he"],
             ky, tone="warn" if so["lead_chua_lien_he"] else "")
        + _o("lead_qua_sla", "Lead quá SLA", so["lead_qua_sla"], ky,
             tone="err" if so["lead_qua_sla"] else "")
        + _o("don_tao", "Đơn mới", so["don_tao"], ky)
        + _o("don_giao", "Đơn giao TC", so["don_giao"], ky, tone="ok")
        + _o("don_hoan", "Đơn hoàn", so["don_hoan"], ky,
             tone="err" if so["don_hoan"] else "")
    )
    if so.get("doanh_thu_giao") is not None:
        tiles += (
            _o("doanh_thu_giao", "Doanh thu giao TC", so["doanh_thu_giao"],
               ky, tien=True)
            + _o("doanh_thu_mua_lai", "Doanh thu mua lại",
                 so["doanh_thu_mua_lai"], ky, tien=True)
        )
    if so.get("chi_phi_qc") is not None:
        tiles += _o("chi_phi_qc", "Chi phí QC", so["chi_phi_qc"], ky, tien=True)
        tiles += stat("ROAS kỳ này", _so_hien(so.get("roas")),
                      href="/crm/quang-cao")
    tiles += (
        _o("viec_qua_han", "Việc quá hạn", so["viec_qua_han"], ky,
           tone="err" if so["viec_qua_han"] else "")
        + _o("moc_den_han", "Mốc chăm đến hạn", so["moc_den_han"], ky,
             tone="warn" if so["moc_den_han"] else "")
        + _o("khach_phan_ung", "Khách có phản ứng", so["khach_phan_ung"], ky,
             tone="err" if so["khach_phan_ung"] else "")
        + _o("ban_giao_moi", "Bàn giao mới", so["ban_giao_moi"], ky)
        + _o("co_hoi_mo", "Cơ hội mua lại mở", so["co_hoi_mo"], ky)
        + "</div>"
    )
    tl = (
        f'<div class="stats" style="margin-top:14px">'
        + stat("Tỷ lệ liên hệ", f"{ti_le['lien_he'] or 0}%")
        + stat("Tỷ lệ chốt / lead mới", f"{ti_le['chot'] or 0}%")
        + stat("Tỷ lệ giao TC / đơn tạo", f"{ti_le['giao_tc'] or 0}%")
        + "</div>"
    )
    body = (
        _loc_ky("/crm/tong-quan", ky)
        + tiles + tl
        + '<div class="card" style="margin-top:14px"><h3>Doanh thu theo ngày</h3>'
        + _bieu_do_cot(data["doanh_thu_theo_ngay"]) + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Phễu Marketing → Sale '
          "→ Đơn (bấm từng bậc ra danh sách)</h3>"
        + _pheu(data["pheu"], ky) + "</div>"
        + '<p class="note" style="margin-top:8px">Báo cáo kỳ chi tiết: '
          '<a href="/crm/bao-cao?tab=sale">Sale</a> · '
          '<a href="/crm/bao-cao?tab=cskh">CSKH</a> · '
          '<a href="/crm/bao-cao?tab=marketing">Marketing</a> · '
          '<a href="/crm/bao-cao?tab=doanh-thu">Doanh thu</a> · '
          '<a href="/crm/bao-cao?tab=mua-lai">Mua lại</a> · '
          '<a href="/crm/bao-cao?tab=cong-viec">Công việc</a></p>'
    )
    return render_shell(
        "Tổng quan CRM", "crm-overview", body, heading="Tổng quan",
        sub="Màn 4 — B11: mọi ô số bấm được ra danh sách cùng điều kiện (FR-173)",
    )


# ------------------------------------------------------------ màn 5 + 6
def _chon_nguoi(duong: str, users: list[dict], chon_id: int, ky: dict) -> str:
    opts = "".join(
        f'<option value="{u["id"]}"{" selected" if u["id"] == chon_id else ""}>'
        f'{escape(u["name"])}</option>' for u in users)
    return _loc_ky(duong, ky,
                   them=f'<label>Nhân viên<select name="user_id">{opts}'
                        "</select></label>")


def render_dashboard_sale(data: dict, users: list[dict], chon_id: int) -> str:
    ky, so, tl = data["ky"], data["so"], data["ti_le"]
    u = data["user_id"]
    body = (
        _chon_nguoi("/crm/dashboard-sale", users, chon_id, ky)
        + '<div class="stats">'
        + _o("lead_moi", "Lead mới được giao", so["lead_moi"], ky, user_id=u)
        + _o("lead_chua_lien_he", "Chưa liên hệ", so["lead_chua_lien_he"], ky,
             tone="warn" if so["lead_chua_lien_he"] else "", user_id=u)
        + _o("lead_nong", "Lead nóng", so["lead_nong"], ky, user_id=u)
        + _o("lead_qua_sla", "Quá SLA", so["lead_qua_sla"], ky,
             tone="err" if so["lead_qua_sla"] else "", user_id=u)
        + _o("lead_bao_gia", "Đã báo giá", so["lead_bao_gia"], ky, user_id=u)
        + _o("lead_chot", "Đã chốt", so["lead_chot"], ky, tone="ok", user_id=u)
        + _o("don_giao", "Đơn giao TC", so["don_giao"], ky, user_id=u)
        + _o("doanh_thu_giao", "Doanh thu", so["doanh_thu_giao"], ky,
             tien=True, user_id=u)
        + _o("viec_qua_han", "Việc quá hạn", so["viec_qua_han"], ky,
             tone="err" if so["viec_qua_han"] else "", user_id=u)
        + "</div>"
        + '<div class="stats" style="margin-top:14px">'
        + stat("Tỷ lệ liên hệ", f"{tl['lien_he'] or 0}%")
        + stat("Tỷ lệ tư vấn", f"{tl['tu_van'] or 0}%")
        + stat("Tỷ lệ báo giá", f"{tl['bao_gia'] or 0}%")
        + stat("Tỷ lệ chốt", f"{tl['chot'] or 0}%")
        + "</div>"
        + '<p class="note" style="margin-top:8px">Điểm chất lượng chat/cuộc gọi '
          "— chờ tổng đài + AI chấm (C-MVP3), khung đã sẵn.</p>"
    )
    return render_shell("Dashboard Sale", "crm-reports", body,
                        heading="Dashboard Sale",
                        sub="Màn 5 — số của TỪNG Sale, mọi ô bấm ra danh sách")


def render_dashboard_cskh(data: dict, users: list[dict], chon_id: int) -> str:
    ky, so, tl = data["ky"], data["so"], data["ti_le"]
    u = data["user_id"]
    body = (
        _chon_nguoi("/crm/dashboard-cskh", users, chon_id, ky)
        + '<div class="stats">'
        + _o("ban_giao_moi", "Khách mới bàn giao", so["ban_giao_moi"], ky, user_id=u)
        + _o("moc_den_han", "Mốc đến hạn", so["moc_den_han"], ky,
             tone="warn" if so["moc_den_han"] else "", user_id=u)
        + _o("moc_hoan_thanh", "Mốc đã làm", so["moc_hoan_thanh"], ky, user_id=u)
        + _o("khach_phan_ung", "Khách có phản ứng", so["khach_phan_ung"], ky,
             tone="err" if so["khach_phan_ung"] else "", user_id=u)
        + _o("viec_qua_han", "Việc quá hạn", so["viec_qua_han"], ky,
             tone="err" if so["viec_qua_han"] else "", user_id=u)
        + _o("co_hoi_mo", "Cơ hội mua lại mở", so["co_hoi_mo"], ky, user_id=u)
        + _o("co_hoi_won", "Chốt mua lại", so["co_hoi_won"], ky,
             tone="ok", user_id=u)
        + _o("doanh_thu_mua_lai", "Doanh thu mua lại", so["doanh_thu_mua_lai"],
             ky, tien=True, user_id=u)
        + "</div>"
        + '<div class="stats" style="margin-top:14px">'
        + stat("Tỷ lệ mốc đúng hạn", f"{tl['moc_dung_han'] or 0}%")
        + "</div>"
        + '<p class="note" style="margin-top:8px">Khách đến từng mốc ngày '
          '4/10/15/20/25/28 xem trực tiếp ở <a href="/crm/cham-soc">màn Chăm sóc'
          "</a> (mốc chờ làm).</p>"
    )
    return render_shell("Dashboard CSKH", "crm-reports", body,
                        heading="Dashboard CSKH",
                        sub="Màn 6 — số của TỪNG CSKH, mọi ô bấm ra danh sách")


# ------------------------------------------------------------ màn 60-64
_TAB = [("sale", "Sale (60)"), ("cskh", "CSKH (61)"),
        ("marketing", "Marketing (62)"), ("don-hang", "Đơn hàng"),
        ("doanh-thu", "Doanh thu"), ("mua-lai", "Mua lại"),
        ("cong-viec", "Công việc (64)")]


def render_bao_cao(tab: str, data: dict, *, loi: str = "") -> str:
    ky = data.get("ky", {"tu": "", "den": ""})
    tabs = tabs_bar([(f"/crm/bao-cao?tab={t}&tu={ky['tu']}&den={ky['den']}",
                      nhan, t) for t, nhan in _TAB], tab)
    if loi:
        ruot = f'<div class="flash err">✕ {escape(loi)}</div>'
    elif tab == "sale":
        dong = "".join(
            f"<tr><td><b>{_e(r['name'])}</b></td><td>{r['lead_moi']}</td>"
            f"<td>{r['lien_he']} ({_e(r['tl_lien_he'])}%)</td>"
            f"<td>{r['tu_van']} ({_e(r['tl_tu_van'])}%)</td>"
            f"<td>{r['bao_gia']} ({_e(r['tl_bao_gia'])}%)</td>"
            f"<td>{r['chot']} ({_e(r['tl_chot'])}%)</td>"
            f"<td>{r['don_giao']}</td><td>{r['don_hoan']}</td>"
            f"<td><b>{_tien(r['doanh_thu'])}</b></td></tr>"
            for r in data["rows"])
        ruot = _bang(["Sale", "Lead", "Liên hệ", "Tư vấn", "Báo giá", "Chốt",
                      "Giao TC", "Hoàn", "Doanh thu"], dong,
                     "Chưa có Sale nào hoạt động trong kỳ") + \
            ('<p class="note">Điểm AI chấm chat/gọi — chờ C-MVP3. Tỷ lệ tính '
             "trên lead MỚI trong kỳ; lead vào bước đếm theo lịch sử FR-041.</p>")
    elif tab == "cskh":
        dong = "".join(
            f"<tr><td><b>{_e(r['name'])}</b></td><td>{r['khach_phu_trach']}</td>"
            f"<td>{r['moc_xong']}</td>"
            f"<td>{r['moc_dung_han']} ({_e(r['tl_dung_han'])}%)</td>"
            f"<td>{r['moc_qua_han']}</td><td>{r['viec_qua_han']}</td>"
            f"<td>{r['ke_hoach_lt2']}</td>"
            f"<td><b>{_tien(r['doanh_thu_mua_lai'])}</b></td></tr>"
            for r in data["rows"])
        ruot = _bang(["CSKH", "Khách phụ trách", "Mốc xong", "Đúng hạn",
                      "Mốc quá hạn", "Việc quá hạn", "Kế hoạch LT2+",
                      "DT mua lại"], dong, "Chưa có CSKH nào trong kỳ")
    elif tab == "marketing":
        so = data["so"]
        ly_do = "".join(
            f"<tr><td>{_e(r['ly_do'])}</td><td>{r['n']}</td></tr>"
            for r in data["ly_do_chua_chot"])
        ruot = (
            '<div class="stats">'
            + stat("Chi phí QC", _tien(so["chi_phi_qc"]))
            + stat("Hội thoại mới", _so_hien(so["hoi_thoai_moi"]))
            + stat("Khách mới", _so_hien(so["khach_moi"]))
            + stat("Lead mới", _so_hien(so["lead_moi"]))
            + stat("Chốt", _so_hien(so["lead_chot"]))
            + stat("Đơn giao TC", _so_hien(so["don_giao"]))
            + stat("Hoàn", _so_hien(so["don_hoan"]))
            + stat("Doanh thu", _tien(so["doanh_thu_giao"]))
            + stat("ROAS", _so_hien(so["roas"]))
            + stat("LTV/khách mua", _tien(so["ltv"]))
            + "</div>"
            + '<div class="card" style="margin-top:14px"><h3>Lý do chưa chốt '
              "(lead đóng-thua + cơ hội mất, FR-172)</h3>"
            + _bang(["Lý do", "Số ca"], ly_do, "Kỳ này không có ca thua nào 🎉")
            + '</div><p class="note">Chi tiết theo từng campaign/adset/ad: '
              '<a href="/crm/quang-cao">màn Nguồn quảng cáo (53-56)</a>.</p>'
        )
    elif tab == "don-hang":
        dong = "".join(
            f"<tr><td><span class='pill'>{_e(r['status'])}</span></td>"
            f"<td>{r['n']}</td><td>{_tien(r['tien'])}</td></tr>"
            for r in data["theo_trang_thai"])
        ruot = _bang(["Trạng thái", "Số đơn", "Giá trị"], dong,
                     "Không có đơn trong kỳ")
    elif tab == "doanh-thu":
        ruot = (
            '<div class="stats">'
            + stat("Tổng giao TC", _tien(data["tong"]))
            + stat("Bán mới", _tien(data["ban_moi"]))
            + stat("Mua lại", _tien(data["mua_lai"]))
            + "</div>"
            + '<div class="card" style="margin-top:14px"><h3>Theo ngày</h3>'
            + _bieu_do_cot(data["theo_ngay"]) + "</div>"
        )
    elif tab == "mua-lai":
        so = data["so"]
        cd = "".join(
            f"<tr><td>{_e(c['name'])}</td><td>{c['so_khach']}</td>"
            f"<td>{c['chuyen_doi']}</td><td><b>{_tien(c['doanh_thu'])}</b></td></tr>"
            for c in data["chien_dich"])
        ruot = (
            '<div class="stats">'
            + stat("Cơ hội đang mở", _so_hien(so["co_hoi_mo"]))
            + stat("Chốt được trong kỳ", _so_hien(so["co_hoi_won"]), tone="ok")
            + stat("Sắp đến hạn (7 ngày)", _so_hien(so["sap_den_han"]))
            + stat("Quá hạn", _so_hien(so["qua_han"]),
                   tone="err" if so["qua_han"] else "")
            + stat("Doanh thu mua lại", _tien(so["doanh_thu_mua_lai"]))
            + "</div>"
            + '<div class="card" style="margin-top:14px"><h3>Chiến dịch tái '
              "kích hoạt</h3>"
            + _bang(["Chiến dịch", "Khách", "Chuyển đổi", "Doanh thu"], cd,
                    "Chưa có chiến dịch") + "</div>"
        )
    else:  # cong-viec
        dong = "".join(
            f"<tr><td>{_e(r['task_type'])}</td><td>{r['tao']}</td>"
            f"<td>{r['xong']}</td><td>{r['dung_han']}</td>"
            f"<td>{r['dang_qua_han']}</td></tr>"
            for r in data["theo_loai"])
        ruot = _bang(["Loại việc", "Tạo trong kỳ", "Hoàn thành", "Đúng hạn",
                      "Đang quá hạn"], dong, "Không có việc trong kỳ")
    body = _loc_ky(
        "/crm/bao-cao", ky,
        hidden=f'<input type="hidden" name="tab" value="{escape(tab)}">',
    ) + ruot
    return render_shell("Báo cáo", "crm-reports", body, heading="Báo cáo",
                        sub="Màn 60-64 — FR-170…172, kỳ lọc dùng chung",
                        tabs=tabs)


# ------------------------------------------------------------ drill-down (FR-173)
def render_chi_tiet(kq: dict) -> str:
    rows = kq["rows"]
    cot = list(rows[0].keys()) if rows else (kq["cot"] or ["(trống)"])
    dong = "".join(
        "<tr>" + "".join(
            f"<td>{_tien(v) if ('tien' in c or c == 'so_tien') else _e(v)}</td>"
            for c, v in r.items()) + "</tr>"
        for r in rows)
    xuat = (f'/crm/bao-cao/xuat?metric={kq["metric"]}&tu={kq["ky"]["tu"]}'
            f'&den={kq["ky"]["den"]}'
            + (f'&user_id={kq["user_id"]}' if kq.get("user_id") else ""))
    body = (
        '<div class="card" style="display:flex;gap:14px;align-items:center;'
        'flex-wrap:wrap;justify-content:space-between">'
        f"<div><b>{escape(kq['ten'])}</b>"
        f"<p class='note' style='margin:4px 0 0'>Kỳ {kq['ky']['tu']} → "
        f"{kq['ky']['den']}"
        + (f" · nhân viên #{kq['user_id']}" if kq.get("user_id") else "")
        + f" · TỔNG: <b>{_so_hien(kq['tong'])}</b> — danh sách dưới dùng CÙNG "
          "điều kiện lọc (FR-173)</p></div>"
        f'<a class="btn" href="{xuat}" data-native download>⬇ Xuất CSV</a></div>'
        + _bang(kq["cot"] or cot, dong, "Không có dòng nào trong kỳ")
    )
    return render_shell(f"Chi tiết — {kq['ten']}", "crm-reports", body,
                        heading=kq["ten"],
                        sub="REPORT-010 — drill-down từ một ô số")
