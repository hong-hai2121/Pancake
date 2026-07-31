"""Dựng HTML bộ màn CRM tạm (khung) — tuyến đường /crm/*.

Nguyên tắc của bộ khung:
  * Cấu trúc màn đúng theo "Danh sách màn hình CRM" (số màn ghi ở từng hàm).
  * Số liệu là THẬT từ schema `crm` — bảng trống thì hiện 0/danh sách trống,
    kèm ghi chú lát cắt nào (B1…B11) sẽ đổ dữ liệu vào.
  * Khi lát cắt đó làm thật, thay phần thân màn; khung + menu giữ nguyên.
"""

from html import escape

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
def render_khach_hang(rows: list[dict], total: int, q: str) -> str:
    dong = "".join(
        f"<tr><td>{_e(r['customer_code'])}</td><td><b>{_e(r['full_name'])}</b></td>"
        f"<td>{_e(r['primary_phone'])}</td><td>{_e(r['province'])}</td>"
        f"<td><span class='pill'>{_e(r['status'])}</span></td>"
        f"<td>{_dt(r['created_at'])}</td></tr>"
        for r in rows
    )
    body = (
        _ghi_chu("B1 (khách 360°) + B2 (đồng bộ Pancake)",
                 "hồ sơ khách tự tạo từ hội thoại, chống trùng, gộp khách, mở hồ sơ 360°")
        + f'<form class="card form" method="get" action="/crm/khach-hang" '
          'style="margin-bottom:14px"><div class="grid2">'
          f'<label>Tìm (tên / SĐT / mã)<input type="text" name="q" value="{escape(q)}"></label>'
          '<label>&nbsp;<button class="btn primary">Tìm</button></label></div></form>'
        + _bang(
            ["Mã", "Họ tên", "Điện thoại", "Tỉnh", "Trạng thái", "Tạo lúc"],
            dong, "Chưa có khách trong CRM — B2 nối poller Pancake sẽ tự đổ vào đây",
        )
        + f'<p class="note" style="margin-top:8px">Tổng: {total} khách</p>'
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


def render_don_hang(data: dict) -> str:
    pills = "".join(
        f'<div class="stat"><div class="s-label">{escape(nhan)}</div>'
        f'<div class="s-value">{data["theo_trang_thai"].get(ma, {}).get("n", 0)}</div></div>'
        for ma, nhan in _TT_DON
    )
    dong = "".join(
        f"<tr><td>{_e(r['external_order_id']) if r['external_order_id'] else '#' + str(r['id'])}</td>"
        f"<td>{_e(r['khach'])}</td><td>{_e(r['sale'])}</td>"
        f"<td>{'mua lại' if r['order_type'] == 'repurchase' else _e(r['order_type'])}</td>"
        f"<td><span class='pill'>{_e(r['status'])}</span></td>"
        f"<td>{_tien(r['total_amount'])}</td><td>{_dt(r['created_at'])}</td></tr>"
        for r in data["rows"]
    )
    body = (
        _ghi_chu("B7 (đơn hàng)", "đồng bộ đơn Pancake, ánh xạ trạng thái, phân loại "
                 "đơn đầu/mua lại, lịch sử trạng thái")
        + f'<div class="stats">{pills}</div>'
        + _bang(["Mã đơn", "Khách", "Sale", "Loại", "Trạng thái", "Giá trị", "Tạo lúc"],
                dong, "Chưa có đơn — B7 sẽ đồng bộ từ Pancake về đây")
    )
    return render_shell("Đơn hàng", "crm-orders", body,
                        heading="Đơn hàng", sub="Màn 21 — danh sách đơn")


# ------------------------------------------------------------ Chăm sóc (màn 26-27)
def render_cham_soc(data: dict) -> str:
    cot = "".join(
        f'<div class="kcol"><h4>{escape(c["code"])} · {escape(c["name"])}'
        '<span class="kcount">0</span></h4></div>'
        for c in data["cot"]
    )
    moc = "".join(
        f"<tr><td><span class='pill'>{_e(m['step_code'])}</span></td>"
        f"<td>{_e(m['khach'])}</td><td>{_dt(m['planned_at'])}</td>"
        f"<td>{_e(m['status'])}</td></tr>"
        for m in data["moc"]
    )
    so = data["so"]
    body = (
        _ghi_chu("B8 (bàn giao) + B9 (chăm 11 bước)", "đơn giao thành công tự tạo kế "
                 "hoạch chăm; mốc CS01-CS11 sinh từ ngày bắt đầu dùng thật")
        + '<div class="stats">'
        + stat("Kế hoạch đang chăm", str(so["ke_hoach_chay"]))
        + stat("Mốc đến hạn", str(so["moc_den_han"]),
               tone="warn" if so["moc_den_han"] else "")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Pipeline CSKH (C01-C09 — '
          'đã seed từ BRD)</h3><div class="kanban">' + cot + "</div></div>"
        + '<div class="card" style="margin-top:14px"><h3>Mốc chăm chờ làm</h3>'
        + _bang(["Mốc", "Khách", "Lịch hẹn", "Trạng thái"], moc,
                "Chưa có mốc chăm — xuất hiện khi B8/B9 chạy")
        + "</div>"
    )
    return render_shell("Chăm sóc", "crm-care", body,
                        heading="Chăm sóc sau bán",
                        sub="Màn 26-27 — bảng việc CSKH + pipeline C01-C09")


# ------------------------------------------------------------ Mua lại (màn 39-40)
_TT_MUA_LAI = [
    ("identified", "Chưa đến hạn"), ("contacted", "Đang tư vấn"),
    ("negotiating", "Chờ quyết định"), ("won", "Đã mua"),
    ("lost", "Mất cơ hội"), ("postponed", "Hoãn"),
]


def render_mua_lai(data: dict) -> str:
    pills = "".join(
        f'<div class="stat"><div class="s-label">{escape(nhan)}</div>'
        f'<div class="s-value">{data["theo_stage"].get(ma, 0)}</div></div>'
        for ma, nhan in _TT_MUA_LAI
    )
    dong = "".join(
        f"<tr><td>{_e(r['khach'])}</td><td>{_e(r['phu_trach'])}</td>"
        f"<td><span class='pill'>{_e(r['stage'])}</span></td>"
        f"<td>{_d(r['expected_close_date'])}</td><td>{_tien(r['expected_value'])}</td></tr>"
        for r in data["rows"]
    )
    body = (
        _ghi_chu("B10 (mua lại & khách ngủ)", "cơ hội tự tạo ở mốc ngày 20, tính ngày "
                 "dự kiến hết theo liều thật, chuỗi cứu cơ hội ngày 28")
        + f'<div class="stats">{pills}</div>'
        + _bang(["Khách", "Phụ trách", "Giai đoạn", "Dự kiến chốt", "Giá trị"],
                dong, "Chưa có cơ hội mua lại — sinh tự động khi B9/B10 chạy")
    )
    return render_shell("Mua lại", "crm-repurchase", body,
                        heading="Mua lại", sub="Màn 39-40 — cơ hội mua lại")


# ------------------------------------------------------------ Sản phẩm (màn 42/44)
def render_san_pham(data: dict) -> str:
    sp = "".join(
        f"<tr><td>{_e(r['product_code'])}</td><td><b>{_e(r['name'])}</b></td>"
        f"<td>{_e(r['product_type'])}</td><td>{_tien(r['price'])}</td>"
        f"<td>{_e(r['status'])}</td><td>{_e(r['approval_status'])}</td></tr>"
        for r in data["san_pham"]
    )
    lt = "".join(
        f"<tr><td>{_e(r['template_code'])}</td><td><b>{_e(r['name'])}</b></td>"
        f"<td>{_e(r['problem_group'])}</td><td>{_e(r['level'])}</td>"
        f"<td>{_tien(r['base_price'])}</td><td>{_e(r['duration_days'])} ngày</td>"
        f"<td>{_e(r['status'])}</td></tr>"
        for r in data["lieu_trinh"]
    )
    body = (
        _ghi_chu("B6 (sản phẩm & liệu trình)", "nhập danh mục, versioning giá, "
                 "rule engine điều kiện phù hợp/loại trừ, duyệt chuyên môn")
        + '<div class="card"><h3>Sản phẩm (màn 42)</h3>'
        + _bang(["Mã", "Tên", "Nhóm", "Giá", "Bán", "Kiểm duyệt"], sp,
                "Chưa có sản phẩm — B6 nhập danh mục")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Mẫu liệu trình (màn 44)</h3>'
        + _bang(["Mã", "Tên", "Nhóm vấn đề", "Cấp", "Giá", "Thời gian", "Trạng thái"],
                lt, "Chưa có mẫu liệu trình — B6 nhập danh mục")
        + "</div>"
    )
    return render_shell("Sản phẩm & liệu trình", "crm-products", body,
                        heading="Sản phẩm & liệu trình",
                        sub="Màn 42 + 44 — danh mục bán hàng")
