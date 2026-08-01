"""Dựng HTML bộ màn CRM tạm (khung) — tuyến đường /crm/*.

Nguyên tắc của bộ khung:
  * Cấu trúc màn đúng theo "Danh sách màn hình CRM" (số màn ghi ở từng hàm).
  * Số liệu là THẬT từ schema `crm` — bảng trống thì hiện 0/danh sách trống,
    kèm ghi chú lát cắt nào (B1…B11) sẽ đổ dữ liệu vào.
  * Khi lát cắt đó làm thật, thay phần thân màn; khung + menu giữ nguyên.
"""

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


def _card(tieu_de: str, ruot: str, note: str = "") -> str:
    ghi = f'<p class="note" style="margin:8px 0 0">{escape(note)}</p>' if note else ""
    return (f'<div class="card" style="margin-top:14px"><h3>{escape(tieu_de)}</h3>'
            f"{ruot}{ghi}</div>")


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
    viec = data.get("viec") or {"hom_nay": 0, "qua_han": 0}
    chao = (
        '<div class="card" style="display:flex;gap:14px;align-items:center;'
        'flex-wrap:wrap;justify-content:space-between">'
        f"<div><h3 style='margin:0'>👋 Chào {escape(ten)}</h3>"
        f"<p class='note' style='margin:4px 0 0'>{escape(vai)} · "
        f"{_THU[hom_nay.weekday()]}, {hom_nay.strftime('%d/%m/%Y')}</p></div>"
        f'<div style="display:flex;gap:8px;flex-wrap:wrap">{nut}</div></div>'
    )

    khoi = ""
    # --- dải "việc của tôi" chung mọi vai trò (trưởng nhóm = cả đội) ---
    cua_ai = "cả đội" if nhom in ("sale_tn", "cskh_tn") else "của tôi"
    khoi += (
        '<div class="stats" style="margin-top:14px">'
        + stat(f"Việc hôm nay ({cua_ai})", str(viec["hom_nay"]), href="/crm/cong-viec")
        + stat(f"Việc quá hạn ({cua_ai})", str(viec["qua_han"]),
               tone="err" if viec["qua_han"] else "", href="/crm/cong-viec")
    )

    if nhom in ("sale", "sale_tn"):
        lead, don = data["lead"], data["don"]
        khoi += (
            stat("Lead đang mở", str(lead["mo"]), href="/crm/pipeline")
            + stat("Lead mới hôm nay", str(lead["moi_hom_nay"]), href="/crm/pipeline")
            + stat("Lead nóng 🔥", str(lead["nong"]), tone="warn" if lead["nong"] else "",
                   href="/crm/pipeline")
            + stat("Quá SLA nhận", str(lead["qua_sla"]),
                   tone="err" if lead["qua_sla"] else "", href="/crm/pipeline")
            + stat("Trễ hẹn hành động", str(lead["hen_tre"]),
                   tone="err" if lead["hen_tre"] else "", href="/crm/pipeline")
            + stat("Doanh thu giao TC tháng", _tien(don["doanh_thu_thang"]),
                   hint=f"{don['don_thang']} đơn tạo trong tháng", href="/crm/don-hang")
        )
        if nhom == "sale_tn":
            khoi += stat("Hàng đợi chưa nhận", str(data["hang_doi"]),
                         tone="warn" if data["hang_doi"] else "", href="/crm/pipeline")
        khoi += "</div>"
        dong = "".join(
            f"<tr><td><b>{_e(r['full_name'])}</b></td><td>{_e(r['stage'])}</td>"
            f"<td>{_e(r['temperature'])}</td><td>{_dt(r['next_action_at'])}</td>"
            f"<td>{_e(r['nguoi'])}</td></tr>"
            for r in data["can_lam"]
        )
        khoi += _card(
            "Lead cần hành động sớm nhất",
            _bang(["Khách", "Giai đoạn", "Nhiệt", "Hẹn kế tiếp", "Phụ trách"],
                  dong, "Chưa có lead nào được giao"),
        )
        if nhom == "sale_tn":
            nv = "".join(
                f"<tr><td>{_e(r['name'])}</td><td>{r['mo']}</td>"
                f"<td>{r['tre']}</td><td>{r['nong']}</td></tr>"
                for r in data["theo_nv"]
            )
            khoi += _card(
                "Tải theo nhân viên trong đội",
                _bang(["Nhân viên", "Lead mở", "Trễ hẹn", "Nóng"], nv,
                      "Đội chưa có thành viên"),
            )

    elif nhom in ("cskh", "cskh_tn"):
        so = data["so"]
        khoi += (
            stat("Đơn chờ xác nhận (CS01)", str(so["don_cho_xn"]),
                 tone="warn" if so["don_cho_xn"] else "", href="/crm/don-hang")
            + stat("Mốc chăm đến hạn", str(so["moc_den_han"]),
                   tone="warn" if so["moc_den_han"] else "", href="/crm/cham-soc")
            + stat("Cơ hội mua lại đang mở", str(so["mua_lai"]), href="/crm/mua-lai")
            + "</div>"
        )
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
        khoi += (
            stat("Chi phí QC 7 ngày", _tien(ads["chi_7n"]), href="/crm/quang-cao")
            + stat("Chi phí QC 30 ngày", _tien(ads["chi_30n"]), href="/crm/quang-cao")
            + stat("Ad có chi phí (30n)", str(ads["ad_co_chi"]), href="/crm/quang-cao")
            + stat("ROAS 30 ngày", roas,
                   hint="doanh thu giao TC / chi phí", href="/crm/quang-cao")
            + stat("Lead mới 7 ngày", str(moi["lead_7n"]), href="/crm/pipeline")
            + stat("Khách mới 7 ngày", str(moi["khach_7n"]), href="/crm/khach-hang")
            + "</div>"
        )
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

        khoi += (
            stat("Doanh thu giao TC hôm nay", _tien(thang["doanh_thu_hom_nay"]),
                 href="/crm/don-hang")
            + stat("Doanh thu giao TC tháng", _tien(thang["doanh_thu_thang"]),
                   href="/crm/don-hang")
            + stat("Chờ xác nhận", str(n("pending")), href="/crm/don-hang")
            + stat("Đang giao", str(n("shipping")), href="/crm/don-hang")
            + stat("Giao thành công", str(n("delivered")), tone="ok", href="/crm/don-hang")
            + stat("Hoàn", str(n("returned") + n("returning")),
                   tone="err" if n("returned") + n("returning") else "",
                   href="/crm/don-hang")
            + "</div>"
        )
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
        khoi += (
            stat("Ca chuyển chuyên môn chờ", str(so["ca_cho"]),
                 tone="err" if so["ca_cho"] else "")
            + stat("Giao cho tôi", str(so["ca_cua_toi"]),
                   tone="warn" if so["ca_cua_toi"] else "")
            + stat("Đề xuất chờ duyệt", str(so["de_xuat_cho"]),
                   tone="warn" if so["de_xuat_cho"] else "", href="/crm/san-pham")
            + stat("SP/nội dung chờ duyệt", str(so["sp_cho_duyet"]), href="/crm/san-pham")
            + stat("Khách cờ đỏ", str(so["khach_do"]),
                   tone="err" if so["khach_do"] else "", href="/crm/khach-hang")
            + stat("Khách cờ vàng", str(so["khach_vang"]),
                   tone="warn" if so["khach_vang"] else "", href="/crm/khach-hang")
            + "</div>"
        )
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
        so = data["so"]
        khoi += (
            stat("Nhân viên hoạt động", str(so["nv_active"]), href="/quan-tri/nhan-vien")
            + stat("Phiên đăng nhập hôm nay", str(so["phien_hom_nay"]))
            + stat("Lỗi đồng bộ chờ thử lại", str(so["loi_cho"]),
                   tone="warn" if so["loi_cho"] else "", href="/quan-tri/tich-hop/loi")
            + stat("Lỗi bỏ cuộc (cần xử tay)", str(so["loi_bo_cuoc"]),
                   tone="err" if so["loi_bo_cuoc"] else "", href="/quan-tri/tich-hop/loi")
            + stat("Thao tác hôm nay", str(so["thao_tac_hom_nay"]),
                   href="/quan-tri/nhat-ky")
            + "</div>"
        )
        audit = "".join(
            f"<tr><td>{_dt(a['created_at'])}</td><td>{_e(a['user_name'])}</td>"
            f"<td><span class='pill'>{_e(a['action'])}</span></td>"
            f"<td>{_e(a['object_type'])}</td></tr>"
            for a in data["audit_moi"]
        )
        khoi += _card(
            "Hoạt động gần đây",
            _bang(["Lúc", "Ai", "Hành động", "Đối tượng"], audit, "Chưa có hoạt động"),
        )

    elif nhom == "chu_dn":
        so, ads = data["so"], data["ads"]
        chi_30 = float(ads["chi_30n"] or 0)
        dt_30 = float(ads["doanh_thu_30n"] or 0)
        roas = f"{dt_30 / chi_30:,.2f}" if chi_30 > 0 else "—"
        khoi += (
            stat("Khách hàng", str(so["khach"]), href="/crm/khach-hang")
            + stat("Lead đang mở", str(so["lead_mo"]), href="/crm/pipeline")
            + stat("Đơn trong tháng", str(so["don_thang"]), href="/crm/don-hang")
            + stat("Doanh thu giao TC tháng", _tien(so["doanh_thu_thang"]),
                   href="/crm/don-hang")
            + stat("Chi phí QC 30 ngày", _tien(ads["chi_30n"]), href="/crm/quang-cao")
            + stat("ROAS 30 ngày", roas, href="/crm/quang-cao")
            + stat("Việc quá hạn toàn cty", str(so["viec_qua_han"]),
                   tone="err" if so["viec_qua_han"] else "", href="/crm/cong-viec")
            + stat("Cơ hội mua lại", str(so["co_hoi_mua_lai"]), href="/crm/mua-lai")
            + "</div>"
        )
        khoi += _card(
            "Đi sâu hơn",
            '<p style="margin:0">Mở <a href="/crm/tong-quan">Tổng quan chi tiết</a> '
            '(lead theo 13 giai đoạn, hoạt động gần đây) hoặc '
            '<a href="/crm/quang-cao">Nguồn quảng cáo</a> (ROAS từng ad).</p>',
        )

    else:  # vai trò lạ / chưa gán — chỉ việc của tôi + hướng dẫn
        khoi += "</div>" + _card(
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
        + stat("Lead đang mở", str(so["lead_mo"]), href="/crm/pipeline")
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
        + '<div class="card" style="margin-top:14px"><h3>Lead theo giai đoạn '
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


# ------------------------------------------------------------ Pipeline (màn 11)
def render_pipeline(stages: list[dict], st: int = 0) -> str:
    """`st` — id giai đoạn cần tô sáng (bấm 'cột trên bảng' từ khối Sale
    ở menu trái); 0 = không tô gì."""
    cot = ""
    for s in stages:
        the = "".join(
            '<div class="kcard">'
            f"<b>{_e(l['full_name'])}</b>"
            f"<div class='note'>{_e(l['temperature'])} · hẹn {_dt(l['next_action_at'])}</div>"
            "</div>"
            for l in s["leads"]
        )
        hl = " hl" if s["id"] == st else ""
        cot += (
            f'<div class="kcol{" closed" if s["is_closed"] else ""}{hl}">'
            f"<h4>{escape(s['name'])}<span class='kcount'>{s['so_lead']}</span></h4>"
            f"{the}</div>"
        )
    body = (
        _ghi_chu("B3 (lead & pipeline)", "kéo thả thẻ, luật chặn chuyển trạng thái, "
                 "chia lead tự động, SLA — tầng luật đã xong, chờ nối")
        + '<style>.kcol.hl{outline:2px solid var(--accent);outline-offset:2px;'
          "border-radius:10px}</style>"
        + f'<div class="kanban card">{cot}</div>'
    )
    # cuộn ngang tới cột được tô (kanban 13 cột tràn màn hình)
    js = ("var c=document.querySelector('.kcol.hl');"
          "if(c)c.scrollIntoView({block:'nearest',inline:'center'});") if st else ""
    return render_shell("Pipeline Sale", "crm-pipeline", body,
                        heading="Pipeline Sale",
                        sub="Màn 11 — Kanban 13 giai đoạn (đã seed từ BRD)",
                        script=js)


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
                        sub="Màn 3 — 11 loại: lead mới · việc đến hạn/quá hạn · "
                            "khách cần gọi lại · phản ứng · chuyển chuyên môn · "
                            "đơn giao/hoàn · mua lại · chờ duyệt · lỗi đồng bộ")
