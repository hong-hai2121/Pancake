"""Dựng HTML màn 9 (Hồ sơ khách hàng 360°) và màn 10 (Hợp nhất khách trùng).

Màn 9 chia đúng 9 khu vực của "Danh sách màn hình CRM": Tổng quan · Hội thoại ·
Cuộc gọi · Hồ sơ tư vấn · Liệu trình · Đơn hàng · Chăm sóc · Marketing · Lịch
sử thay đổi. Mỗi khu vực là một tab, nạp theo `?tab=` để mở hồ sơ không phải
kéo hết mọi bảng.
"""

from html import escape

from app.integrations.pancake.links import link_hoi_thoai
from app.web.shell import render_shell, stat

from app.web.views.crm import _bang, _d, _dt, _e, _tien

TABS = [
    ("tong-quan", "Tổng quan"), ("hoi-thoai", "Hội thoại"),
    ("cuoc-goi", "Cuộc gọi"), ("tu-van", "Hồ sơ tư vấn"),
    ("lieu-trinh", "Liệu trình"), ("don-hang", "Đơn hàng"),
    ("cham-soc", "Chăm sóc"), ("marketing", "Marketing"),
    ("lich-su", "Lịch sử thay đổi"),
]

_MAU_CO = {"red": ("err", "🔴 Cờ đỏ"), "yellow": ("warn", "🟡 Cờ vàng")}


def _tabs(customer_id: int, dang_mo: str) -> str:
    html = ""
    for ma, nhan in TABS:
        cls = "tab on" if ma == dang_mo else "tab"
        html += (f'<a class="{cls}" href="/crm/khach-hang/{customer_id}?tab={ma}">'
                 f"{escape(nhan)}</a>")
    return f'<nav class="tabs">{html}</nav>'


def _dau_trang(kh: dict) -> str:
    """Dải đầu hồ sơ: tên, SĐT, mã, cờ an toàn, người phụ trách, thẻ."""
    co = ""
    if kh.get("safety_flag") in _MAU_CO:
        tone, nhan = _MAU_CO[kh["safety_flag"]]
        co = f'<span class="pill {tone}">{nhan}</span> '
    the = "".join(
        f'<span class="pill">{escape(t["name"])}</span> '
        for t in (kh.get("tags") or [])
    )
    return (
        '<div class="card" style="margin-bottom:14px">'
        f"<h3 style='margin:0 0 6px'>{_e(kh['full_name'])} {co}"
        f"<span class='pill'>{_e(kh['status'])}</span></h3>"
        f"<p class='note' style='margin:0'>Mã {_e(kh['customer_code'])} · "
        f"SĐT {_e(kh['primary_phone'])} · Tạo {_dt(kh['created_at'])}</p>"
        f"<p class='note' style='margin:6px 0 0'>Sale: <b>{_e(kh['sale_phu_trach'])}</b>"
        f" · CSKH: <b>{_e(kh['cskh_phu_trach'])}</b></p>"
        + (f'<div style="margin-top:8px">{the}</div>' if the else "")
        + "</div>"
    )


def _tab_tong_quan(kh: dict) -> str:
    lead = kh.get("lead") or {}
    o_so = (
        '<div class="stats">'
        + stat("Tổng chi tiêu", _tien(kh["tong_chi_tieu"]))
        + stat("Số đơn", str(kh["so_don"]))
        + stat("Mua gần nhất", _dt(kh["mua_cuoi"]))
        + stat("Giai đoạn Sale", _e(lead.get("stage_name")))
        + "</div>"
    )
    canh_bao = ""
    if kh.get("canh_bao"):
        muc = "".join(
            f"<li><b>{_e(c['screening_type'])}</b>: {_e(c['value'])} "
            f"<span class='note'>({_e(c['risk_level'])} · {_dt(c['created_at'])})</span></li>"
            for c in kh["canh_bao"]
        )
        canh_bao = ('<div class="flash err" style="margin-bottom:14px">'
                    f"⚠ Cảnh báo an toàn đang mở:<ul style='margin:6px 0 0'>{muc}</ul>"
                    "</div>")
    viec = "".join(
        f"<tr><td>{_e(v['title'] or v['task_type'])}</td><td>{_e(v['task_type'])}</td>"
        f"<td>{_dt(v['due_at'])}</td><td>{_e(v['priority'])}</td>"
        f"<td>{_e(v['nguoi'])}</td></tr>"
        for v in kh.get("viec_tiep") or []
    )
    khoi_lead = ""
    if lead:
        khoi_lead = (
            '<div class="card" style="margin-top:14px"><h3>Lead hiện tại</h3>'
            f"<p>Giai đoạn <b>{_e(lead.get('stage_name'))}</b> · "
            f"nhiệt {_e(lead.get('temperature'))} · "
            f"hẹn kế tiếp {_dt(lead.get('next_action_at'))} · "
            f"phụ trách {_e(lead.get('owner_name'))}"
            f"{' · <b>đã đóng</b>' if lead.get('closed_at') else ''}</p>"
            f'<a class="btn sm" href="/crm/pipeline">Mở Kanban</a></div>'
        )
    return (
        canh_bao + o_so + khoi_lead
        + '<div class="card" style="margin-top:14px"><h3>Công việc tiếp theo</h3>'
        + _bang(["Việc", "Loại", "Hạn", "Ưu tiên", "Phụ trách"], viec,
                "Không có việc nào đang mở")
        + "</div>"
    )


def _tab_hoi_thoai(rows: list[dict], tin: list[dict], conv_mo: int) -> str:
    dong = ""
    for r in rows:
        link = link_hoi_thoai(r.get("external_page_id") or "",
                              r.get("external_conversation_id") or "")
        nut_pancake = (f'<a class="btn sm" href="{escape(link)}" target="_blank" '
                       'rel="noopener">💬 Pancake</a> ' if link else "")
        dam = " primary" if r["id"] == conv_mo else ""
        dong += (
            f"<tr><td>{_e(r['page_name'])}</td>"
            f"<td>{_e(r['snippet'])}</td><td>{_dt(r['last_message_at'])}</td>"
            f"<td>{r['tin_da_luu']}/{_e(r['message_count'])}</td>"
            f"<td>{_e(r['assignee_name'])}</td>"
            f'<td>{nut_pancake}<a class="btn sm{dam}" '
            f'href="/crm/khach-hang/{r["customer_id"] if "customer_id" in r else ""}'
            f'?tab=hoi-thoai&conv={r["id"]}">Xem tin</a></td></tr>'
        )
    khung = ""
    if conv_mo:
        if tin:
            bong = ""
            for m in tin:
                ben = "agent" if m["sender_type"] in ("agent", "bot") else "customer"
                mau = "#e8f0fe" if ben == "agent" else "var(--card)"
                le = "margin-left:auto" if ben == "agent" else ""
                ten = m.get("sender_name") or m["sender_type"]
                anh = ""
                for a in (m.get("attachments") or []):
                    if a.get("url"):
                        anh += (f'<div><a href="{escape(a["url"])}" target="_blank" '
                                f'rel="noopener">📎 {escape(a.get("type") or "file")}</a></div>')
                bong += (
                    f'<div style="max-width:70%;{le};background:{mau};border:1px solid '
                    'var(--border);border-radius:10px;padding:8px 10px;margin:6px 0">'
                    f'<div class="note" style="font-size:11px">{escape(str(ten))} · '
                    f'{_dt(m["sent_at"])}</div>'
                    f'<div style="white-space:pre-wrap">{_e(m["content"])}</div>'
                    f"{anh}</div>"
                )
            khung = ('<div class="card" style="margin-top:14px"><h3>Nội dung hội thoại'
                     f'</h3><div style="display:flex;flex-direction:column">{bong}</div>'
                     "</div>")
        else:
            khung = ('<div class="flash warn" style="margin-top:14px">Hội thoại này '
                     "chưa kéo nội dung tin nhắn về CRM. Bật <b>Kéo nội dung tin nhắn"
                     '</b> ở <a href="/quan-tri/cai-dat">Cài đặt</a>, hoặc chạy '
                     "<code>scripts/backfill_tin_nhan.py</code>.</div>")
    return (
        _bang(["Page", "Tin cuối", "Lúc", "Tin đã lưu", "Nhân viên", ""], dong,
              "Khách chưa có hội thoại nào trong CRM")
        + khung
    )


def _tab_cuoc_goi() -> str:
    return ('<div class="flash warn">📞 Tổng đài chưa nối — phần ghi âm, transcript '
            "và điểm AI thuộc giai đoạn <b>C-MVP3</b> (màn 18-20 + 74).</div>")


def _tab_tu_van(d: dict) -> str:
    tc = "".join(
        f"<tr><td>{_e(r['symptom_name'])}</td><td>{_e(r['group_name'])}</td>"
        f"<td>{_e(r.get('severity'))}</td><td>{_e(r.get('frequency'))}</td>"
        f"<td>{_e(r.get('occurs_when'))}</td><td>{_e(r.get('meal_relation'))}</td></tr>"
        for r in d["trieu_chung"]
    )
    kham = "".join(
        f"<tr><td>{_e(r['exam_type'])}</td><td>{_d(r['exam_date'])}</td>"
        f"<td>{_e(r['facility'])}</td><td>{_e(r['conclusion'])}</td></tr>"
        for r in d["kham"]
    )
    thuoc = "".join(
        f"<tr><td>{_e(r['name'])}</td><td>{_e(r['dosage'])}</td>"
        f"<td>{_e(r['duration'])}</td><td>{_e(r.get('reaction'))}</td></tr>"
        for r in d["thuoc"]
    )
    sl = "".join(
        f"<tr><td>{_e(r['screening_type'])}</td><td>{_e(r['value'])}</td>"
        f"<td><span class='pill {'err' if r['risk_level'] in ('high','critical') else ''}'>"
        f"{_e(r['risk_level'])}</span></td><td>{_dt(r['created_at'])}</td></tr>"
        for r in d["sang_loc"]
    )
    ca = "".join(
        f"<tr><td>{_e(r['reason'])}</td><td>{_e(r['source'])}</td>"
        f"<td>{_e(r['risk_level'])}</td><td>{_e(r['status'])}</td>"
        f"<td>{_dt(r['created_at'])}</td></tr>"
        for r in d["ca_chuyen_mon"]
    )
    return (
        '<div class="card"><h3>Triệu chứng</h3>'
        + _bang(["Triệu chứng", "Nhóm", "Mức độ", "Tần suất", "Thời điểm", "Bữa ăn"],
                tc, "Chưa khai thác triệu chứng") + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Kết quả khám / nội soi</h3>'
        + _bang(["Loại", "Ngày", "Cơ sở", "Kết luận"], kham, "Chưa có kết quả khám")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Thuốc đang dùng</h3>'
        + _bang(["Thuốc", "Liều", "Thời gian", "Phản ứng"], thuoc, "Không dùng thuốc gì")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Sàng lọc an toàn (FR-053)</h3>'
        + _bang(["Mục", "Trả lời", "Mức rủi ro", "Lúc"], sl, "Chưa sàng lọc")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Ca chuyển chuyên môn</h3>'
        + _bang(["Lý do", "Nguồn", "Mức", "Trạng thái", "Lúc"], ca, "Không có ca nào")
        + "</div>"
    )


def _tab_lieu_trinh(d: dict) -> str:
    khoi = ""
    for lt in d["lieu_trinh"]:
        sp = "".join(
            f"<tr><td>{_e(i['product_name'])}</td><td>{_e(i['quantity'])}</td>"
            f"<td>{_e(i['dose_text'])}</td><td>{_d(i.get('actual_start_date'))}</td></tr>"
            for i in lt["items"]
        )
        khoi += (
            '<div class="card" style="margin-top:14px">'
            f"<h3>{_e(lt['template_name'])} "
            f"<span class='pill'>{_e(lt['status'])}</span></h3>"
            f"<p class='note'>Bắt đầu {_d(lt['start_date'])} · dự kiến hết "
            f"{_d(lt['expected_end_date'])} · duyệt bởi {_e(lt['approved_by_name'])}</p>"
            + _bang(["Sản phẩm", "SL", "Cách dùng", "Bắt đầu thật"], sp,
                    "Chưa có sản phẩm trong liệu trình")
            + "</div>"
        )
    dx = "".join(
        f"<tr><td>{_e(r['template_name'])}</td>"
        f"<td><span class='pill'>{_e(r['status'])}</span></td>"
        f"<td>{_e(r['nguoi_de_xuat'])}</td><td>{_dt(r['created_at'])}</td></tr>"
        for r in d["de_xuat"]
    )
    return (
        (khoi or '<div class="flash warn">Khách chưa có liệu trình nào đang dùng.</div>')
        + '<div class="card" style="margin-top:14px"><h3>Đề xuất liệu trình (B6)</h3>'
        + _bang(["Mẫu", "Trạng thái", "Người đề xuất", "Lúc"], dx, "Chưa có đề xuất")
        + "</div>"
    )


def _tab_don_hang(rows: list[dict]) -> str:
    dong = "".join(
        f'<tr><td><a href="/crm/don-hang/{r["id"]}">#{r["id"]}</a></td>'
        f"<td>{_e(r['order_type'])}</td>"
        f"<td><span class='pill'>{_e(r['status'])}</span></td>"
        f"<td>{_tien(r['total_amount'])}</td><td>{_dt(r['created_at'])}</td>"
        f"<td>{_dt(r['delivered_at'])}</td><td>{_e(r['sale_name'])}</td></tr>"
        for r in rows
    )
    return _bang(["Đơn", "Loại", "Trạng thái", "Giá trị", "Tạo", "Giao", "Sale"],
                 dong, "Khách chưa có đơn nào")


def _tab_cham_soc(d: dict) -> str:
    khoi = ""
    for bg in d["ban_giao"]:
        du = ("<span class='pill ok'>Đủ</span>" if bg["is_complete"]
              else "<span class='pill err'>Thiếu</span>")
        khoi += (
            '<div class="card" style="margin-top:14px">'
            f"<h3>Phiếu bàn giao #{bg['id']} "
            f"<span class='pill'>{_e(bg['status'])}</span> {du}</h3>"
            f"<p class='note'>Sale {_e(bg['sale_name'])} → CSKH {_e(bg['cskh_name'])}"
            f" · dự kiến bắt đầu {_d(bg['expected_start_date'])}</p>"
            f'<a class="btn sm" href="/crm/ban-giao/{bg["id"]}">Mở phiếu</a></div>'
        )
    for kh in d["ke_hoach"]:
        moc = "".join(
            f"<tr><td><span class='pill'>{_e(m['step_code'])}</span></td>"
            f"<td>{_dt(m['planned_at'])}</td><td>{_e(m['status'])}</td>"
            f"<td>{_e(m.get('result_code'))}</td><td>{_dt(m['completed_at'])}</td></tr>"
            for m in kh["moc"]
        )
        khoi += (
            '<div class="card" style="margin-top:14px">'
            f"<h3>Kế hoạch chăm #{kh['id']} "
            f"<span class='pill'>{_e(kh.get('cskh_state') or kh['status'])}</span></h3>"
            f"<p class='note'>Phụ trách {_e(kh['owner_name'])} · bắt đầu "
            f"{_dt(kh['started_at'])}</p>"
            + _bang(["Mốc", "Kế hoạch", "Trạng thái", "Kết quả", "Hoàn thành"],
                    moc, "Chưa sinh mốc nào")
            + f'<a class="btn sm" href="/crm/cham-soc/{kh["id"]}">Mở phiếu chăm</a>'
            "</div>"
        )
    ml = "".join(
        f"<tr><td>{_e(r['next_template_name'])}</td>"
        f"<td><span class='pill'>{_e(r['stage'])}</span></td>"
        f"<td>{_d(r['expected_close_date'])}</td><td>{_tien(r['expected_value'])}</td>"
        f"<td>{_e(r['owner_name'])}</td></tr>"
        for r in d["mua_lai"]
    )
    return (
        (khoi or '<div class="flash warn">Khách chưa được bàn giao CSKH '
                 "(chỉ sinh khi đơn giao thành công).</div>")
        + '<div class="card" style="margin-top:14px"><h3>Cơ hội mua lại</h3>'
        + _bang(["Liệu trình kế", "Giai đoạn", "Dự kiến chốt", "Giá trị", "Phụ trách"],
                ml, "Chưa có cơ hội mua lại")
        + "</div>"
    )


def _tab_marketing(d: dict) -> str:
    dong = ""
    for r in d["quy_nguon"]:
        utm = r.get("utm") or {}
        dong += (
            f"<tr><td><span class='pill'>{_e(r['touch_type'])}</span></td>"
            f"<td>{_e(r['campaign_name'])}</td><td>{_e(r['adset_name'])}</td>"
            f"<td>{_e(r['ad_name'] or r['external_ad_id'])}</td>"
            f"<td>{_e(utm.get('campaign'))}</td><td>{_e(r['source'])}</td>"
            f"<td>{_dt(r['attributed_at'])}</td></tr>"
        )
    dt = (d.get("doanh_thu") or {}).get("tong")
    return (
        '<div class="stats">' + stat("Doanh thu vòng đời", _tien(dt)) + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Quy nguồn quảng cáo</h3>'
        + _bang(["Chạm", "Chiến dịch", "Nhóm QC", "Quảng cáo", "UTM", "Nguồn", "Lúc"],
                dong, "Chưa quy được nguồn — đơn/hội thoại không mang ad_id")
        + '<p class="note" style="margin-top:8px">Chi phí phân bổ theo từng quảng cáo '
          'xem ở <a href="/crm/quang-cao">Nguồn quảng cáo</a>.</p></div>'
    )


def _tab_lich_su(rows: list[dict]) -> str:
    dong = ""
    for r in rows:
        cu, moi = r.get("old_value"), r.get("new_value")
        dong += (
            f"<tr><td>{_dt(r['created_at'])}</td><td>{_e(r['user_name'])}</td>"
            f"<td>{_e(r['action'])}</td><td>{_e(r['object_type'])}</td>"
            f"<td><code style='font-size:11px'>{_e(cu)}</code></td>"
            f"<td><code style='font-size:11px'>{_e(moi)}</code></td></tr>"
        )
    return _bang(["Lúc", "Ai", "Hành động", "Đối tượng", "Trước", "Sau"], dong,
                 "Chưa có thay đổi nào được ghi")


def render_ho_so(kh: dict, tab: str, data, conv_mo: int = 0) -> str:
    """Màn 9 — hồ sơ 360°. `data` là dữ liệu của ĐÚNG tab đang mở."""
    if tab == "hoi-thoai":
        than = _tab_hoi_thoai(data["hoi_thoai"], data["tin"], conv_mo)
    elif tab == "cuoc-goi":
        than = _tab_cuoc_goi()
    elif tab == "tu-van":
        than = _tab_tu_van(data)
    elif tab == "lieu-trinh":
        than = _tab_lieu_trinh(data)
    elif tab == "don-hang":
        than = _tab_don_hang(data)
    elif tab == "cham-soc":
        than = _tab_cham_soc(data)
    elif tab == "marketing":
        than = _tab_marketing(data)
    elif tab == "lich-su":
        than = _tab_lich_su(data)
    else:
        than = _tab_tong_quan(kh)

    body = (
        '<p style="margin-bottom:10px">'
        '<a class="btn sm" href="/crm/khach-hang">← Danh sách khách</a> '
        f'<a class="btn sm primary" href="/crm/tu-van/{kh["id"]}">'
        "💬 Vào tư vấn (màn 13-15)</a></p>"
        + _dau_trang(kh) + _tabs(kh["id"], tab)
        + f'<div style="margin-top:14px">{than}</div>'
    )
    return render_shell(f"Hồ sơ {kh['full_name']}", "crm-customers", body,
                        heading="Hồ sơ khách hàng 360°",
                        sub="Màn 9 — toàn bộ vòng đời khách trong một chỗ")


# ------------------------------------------------------- màn 22 chi tiết đơn
def _o_pos(raw: dict, *khoa: str):
    """Moi một trường trong `pos_raw` (đơn POS 102 trường) — thiếu thì None."""
    for k in khoa:
        v = (raw or {}).get(k)
        if v not in (None, "", {}):
            return v
    return None


def render_chi_tiet_don(d: dict) -> str:
    """Màn 22 — chi tiết đơn hàng: khách · hàng · tiền · địa chỉ · vận chuyển ·
    lịch sử trạng thái · việc & liệu trình liên quan · nguồn quảng cáo."""
    raw = d.get("pos_raw") or {}
    hang = "".join(
        f"<tr><td>{_e(i['product_code'])}</td><td>{_e(i['product_name'])}</td>"
        f"<td>{_e(i['template_name'])}</td><td>{_e(i['quantity'])}</td>"
        f"<td>{_tien(i['unit_price'])}</td><td>{_tien(i.get('line_total'))}</td></tr>"
        for i in d["items"]
    )
    ls = "".join(
        f"<tr><td>{_dt(h['created_at'])}</td>"
        f"<td><span class='pill'>{_e(h.get('from_status'))}</span> → "
        f"<span class='pill'>{_e(h.get('to_status'))}</span></td>"
        f"<td>{_e(h['changed_by_name'])}</td><td>{_e(h.get('reason'))}</td></tr>"
        for h in d["lich_su"]
    )
    viec = "".join(
        f"<tr><td>{_e(v['title'] or v['task_type'])}</td><td>{_dt(v['due_at'])}</td>"
        f"<td>{_e(v['status'])}</td><td>{_e(v['nguoi'])}</td></tr>"
        for v in d["viec"]
    )
    lt = "".join(
        f"<tr><td>{_e(t['template_name'])}</td><td>{_e(t['status'])}</td>"
        f"<td>{_d(t['start_date'])}</td><td>{_d(t['expected_end_date'])}</td></tr>"
        for t in d["lieu_trinh"]
    )
    qn = "".join(
        f"<tr><td>{_e(a['touch_type'])}</td>"
        f"<td>{_e(a['ad_name'] or a['external_ad_id'])}</td>"
        f"<td>{_e((a.get('utm') or {}).get('campaign'))}</td>"
        f"<td>{_e(a['source'])}</td></tr>"
        for a in d["quy_nguon"]
    )

    dia_chi = _o_pos(raw, "shipping_address", "bill_full_address")
    if isinstance(dia_chi, dict):
        dia_chi = ", ".join(str(v) for v in (
            dia_chi.get("full_address"), dia_chi.get("address"),
            dia_chi.get("commune_name"), dia_chi.get("district_name"),
            dia_chi.get("province_name")) if v)
    van_chuyen = _o_pos(raw, "partner")
    if isinstance(van_chuyen, dict):
        van_chuyen = (f"{van_chuyen.get('partner_name') or '—'} · mã vận đơn "
                      f"{van_chuyen.get('extend_code') or '—'}")

    bg = d.get("ban_giao")
    nut_bg = (f'<a class="btn sm" href="/crm/ban-giao/{bg["id"]}">Mở phiếu bàn giao</a>'
              if bg else "")

    body = (
        '<p style="margin-bottom:10px">'
        '<a class="btn sm" href="/crm/don-hang">← Danh sách đơn</a></p>'
        + '<div class="card" style="margin-bottom:14px">'
        f"<h3 style='margin:0 0 6px'>Đơn #{d['id']} "
        f"<span class='pill'>{_e(d['status'])}</span> "
        f"<span class='pill'>{_e(d['order_type'])}</span></h3>"
        '<p class="note" style="margin:0">Khách '
        f'<a href="/crm/khach-hang/{d["customer_id"]}">'
        f"<b>{_e(d['customer_name'])}</b></a>"
        f" · {_e(d['customer_phone'])} · mã ngoài {_e(d['external_order_id'])}</p>"
        f"<p class='note' style='margin:6px 0 0'>Sale {_e(d['sale_name'])} · "
        f"CSKH {_e(d['cskh_name'])} · tạo {_dt(d['created_at'])} · "
        f"giao {_dt(d['delivered_at'])}</p>"
        f"<div style='margin-top:8px'>{nut_bg}</div></div>"
        + '<div class="stats">'
        + stat("Giá trị đơn", _tien(d["total_amount"]))
        + stat("Thanh toán", _e(_o_pos(raw, "cod", "prepaid") or "—"))
        + stat("Trạng thái POS", _e(d.get("pos_status")))
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Sản phẩm</h3>'
        + _bang(["Mã", "Tên", "Liệu trình", "SL", "Đơn giá", "Thành tiền"], hang,
                "Đơn POS chưa đồng bộ dòng hàng (SP POS chưa ánh xạ crm.products) — "
                "nguyên văn nằm ở pos_raw")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Giao hàng &amp; thanh toán</h3>'
        f"<p><b>Địa chỉ:</b> {_e(dia_chi)}</p>"
        f"<p><b>Vận chuyển:</b> {_e(van_chuyen)}</p>"
        f"<p><b>Giảm giá:</b> {_e(_o_pos(raw, 'total_discount'))} · "
        f"<b>Phí ship:</b> {_e(_o_pos(raw, 'shipping_fee'))}</p></div>"
        + '<div class="card" style="margin-top:14px"><h3>Lịch sử trạng thái '
          "(không bao giờ xoá — FR-080)</h3>"
        + _bang(["Lúc", "Chuyển", "Người đổi", "Lý do"], ls, "Chưa có bước nào")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Liệu trình liên quan</h3>'
        + _bang(["Mẫu", "Trạng thái", "Bắt đầu", "Dự kiến hết"], lt,
                "Đơn này chưa gắn liệu trình")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Công việc liên quan</h3>'
        + _bang(["Việc", "Hạn", "Trạng thái", "Phụ trách"], viec, "Không có việc nào")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Nguồn quảng cáo</h3>'
        + _bang(["Chạm", "Quảng cáo", "UTM chiến dịch", "Nguồn"], qn,
                "Đơn không mang ad_id / post_id")
        + "</div>"
    )
    return render_shell(f"Đơn #{d['id']}", "crm-orders", body,
                        heading=f"Chi tiết đơn #{d['id']}",
                        sub="Màn 22 — hàng · tiền · giao nhận · lịch sử · liên quan")


# ------------------------------------------------------------ màn 10 gộp trùng
def render_gop_trung(nhom: list[dict], ok_msg: str = "", error: str = "") -> str:
    """Màn 10 — hợp nhất khách trùng: mỗi nhóm nghi trùng một thẻ, chọn hồ sơ
    chính rồi gộp (FR-022 — hồ sơ phụ chuyển `merged`, KHÔNG xoá)."""
    khoi = ""
    for i, n in enumerate(nhom):
        ho_so = n["ho_so"] or []
        dong = ""
        radio = ""
        for h in ho_so:
            dong += (
                f'<tr><td><a href="/crm/khach-hang/{h["id"]}">#{h["id"]}</a></td>'
                f"<td>{_e(h.get('ma'))}</td><td><b>{_e(h.get('ten'))}</b></td>"
                f"<td>{_e(h.get('sdt'))}</td><td>{_e(str(h.get('tao') or '')[:10])}</td>"
                "</tr>"
            )
            radio += (
                '<label style="display:inline-flex;gap:5px;align-items:center;'
                'margin-right:14px">'
                f'<input type="radio" name="chinh" value="{h["id"]}" required>'
                f'<span>#{h["id"]} {escape(str(h.get("ten") or ""))}</span></label>'
            )
        khoi += (
            '<div class="card" style="margin-top:14px">'
            f"<h3>{_e(n['ly_do'])} <span class='pill warn'>{n['so_ho_so']} hồ sơ</span></h3>"
            + _bang(["ID", "Mã", "Họ tên", "SĐT", "Tạo"], dong, "")
            + '<form method="post" action="/crm/gop-trung" style="margin-top:10px">'
            f'<input type="hidden" name="nhom" value="{escape(str(n["ly_do"]))}">'
            + "".join(f'<input type="hidden" name="ids" value="{h["id"]}">'
                      for h in ho_so)
            + "<p style='margin:0 0 8px'><b>Giữ hồ sơ chính:</b></p>"
            + radio
            + '<div style="margin-top:10px"><button class="btn primary" '
              'onclick="return confirm(\'Gộp các hồ sơ còn lại vào hồ sơ chính? '
              'Hồ sơ phụ chuyển trạng thái merged, không xoá.\')">'
              "🔗 Gộp vào hồ sơ chính</button></div></form></div>"
        )

    flash = ""
    if ok_msg:
        flash = f'<div class="flash ok" style="margin-bottom:14px">{escape(ok_msg)}</div>'
    if error:
        flash = f'<div class="flash err" style="margin-bottom:14px">{escape(error)}</div>'

    body = (
        flash
        + '<div class="stats">' + stat("Nhóm nghi trùng", str(len(nhom)),
                                       tone="warn" if nhom else "") + "</div>"
        + (khoi or '<div class="card" style="margin-top:14px">'
                   '<p class="note">Không phát hiện hồ sơ nghi trùng nào. '
                   "Máy dò theo <b>số điện thoại giống nhau</b> và "
                   "<b>Facebook ID trùng trên cùng page</b>.</p></div>")
        + '<p class="note" style="margin-top:14px">Gộp dồn dữ liệu 20 bảng trong MỘT '
          "giao dịch (đơn · hội thoại · lead · liệu trình · việc…); hồ sơ phụ chuyển "
          "trạng thái <code>merged</code> và KHÔNG bị xoá, nên tra ngược được. "
          "Xem lịch sử gộp ở <a href='/quan-tri/nhat-ky'>Nhật ký hoạt động</a>.</p>"
    )
    return render_shell("Hợp nhất khách trùng", "crm-customers", body,
                        heading="Hợp nhất khách trùng",
                        sub="Màn 10 — dò theo SĐT và Facebook ID (FR-022)")
