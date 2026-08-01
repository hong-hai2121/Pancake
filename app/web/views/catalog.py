"""Màn 43 (chi tiết sản phẩm) · 45 (chi tiết mẫu liệu trình) · 46 (luật liệu trình).

Ba màn CHI TIẾT của khu danh mục; màn 42/44 là hai danh sách ở
`app/web/views/crm.py` (bấm một dòng là sang đây).

Luật B6 phản ánh lên màn: đổi giá tự sinh phiên bản (đơn cũ giữ giá cũ), sửa
nội dung là quay về `pending` chờ duyệt, và **nội dung cấm** bày tách hẳn khỏi
nội dung Sale được nói.
"""

from html import escape

from app.web.shell import render_shell, stat

from app.web.views.crm import _bang, _d, _dt, _e, _tien

_TT_DUYET = {"draft": ("", "Nháp"), "pending": ("warn", "Chờ duyệt"),
             "approved": ("ok", "Đã duyệt"), "rejected": ("err", "Từ chối")}

# 4 kiểu điều kiện của rule engine (condition_json) — nhãn tiếng Việt cho màn 46
_KIEU_DK = {
    "screening": "Mục sàng lọc an toàn",
    "symptom": "Triệu chứng + mức tối thiểu",
    "symptom_group": "Nhóm triệu chứng",
    "safety_flag": "Cờ an toàn của khách",
}
_LOAI_LUAT = {
    "exclusion": ("err", "Loại trừ — khớp là KHÔNG hiện mẫu"),
    "suitable": ("ok", "Phù hợp — phải khớp mới hiện"),
    "warning": ("warn", "Cảnh báo — hiện nhưng phải chuyên môn duyệt"),
}


def _pill_duyet(tt: str) -> str:
    tone, nhan = _TT_DUYET.get(tt, ("", tt))
    return f'<span class="pill {tone}">{escape(nhan)}</span>'


# ------------------------------------------------------------------ màn 43
def render_chi_tiet_sp(sp: dict, phien_ban: list[dict]) -> str:
    pb = "".join(
        f"<tr><td>v{_e(r.get('version_no'))}</td><td>{_tien(r.get('price'))}</td>"
        f"<td>{_e(r.get('approval_status'))}</td><td>{_dt(r['created_at'])}</td></tr>"
        for r in phien_ban
    )
    noi_dung = ""
    for cot, nhan, mau in (
        ("ingredients", "Thành phần", ""),
        ("approved_claims", "Công dụng ĐƯỢC duyệt", "ok"),
        ("usage_text", "Cách dùng", ""),
        ("target_group", "Đối tượng phù hợp", ""),
        ("contraindications", "Điều kiện KHÔNG phù hợp", "warn"),
        ("sale_talking_points", "Nội dung Sale được nói", ""),
        ("prohibited_claims", "NỘI DUNG CẤM nói", "err"),
        ("source_docs", "Tài liệu nguồn", ""),
    ):
        gt = sp.get(cot)
        if gt in (None, ""):
            continue
        vien = f' style="border-left:3px solid var(--{mau});padding-left:10px"' if mau else ""
        noi_dung += (f'<div{vien} style="margin:10px 0">'
                     f"<b>{escape(nhan)}</b>"
                     f'<div style="white-space:pre-wrap">{_e(gt)}</div></div>')
    if not noi_dung:
        noi_dung = ('<p class="note">Sản phẩm chưa nhập nội dung chi tiết '
                    "(thành phần, công dụng được duyệt, nội dung cấm…).</p>")

    body = (
        '<p style="margin-bottom:10px">'
        '<a class="btn sm" href="/crm/san-pham">← Danh mục</a></p>'
        '<div class="card" style="margin-bottom:14px">'
        f"<h3 style='margin:0 0 4px'>{_e(sp['name'])} {_pill_duyet(sp['approval_status'])}"
        f" <span class='pill'>{_e(sp['status'])}</span></h3>"
        f"<p class='note' style='margin:0'>Mã {_e(sp['product_code'])} · "
        f"nhóm {_e(sp['product_type'])} · quy cách {_e(sp['package'])} · "
        f"{_e(sp['units_per_package'])} đơn vị/hộp</p></div>"
        + '<div class="stats">'
        + stat("Giá hiện tại", _tien(sp["price"]))
        + stat("Số phiên bản giá", str(len(phien_ban)))
        + "</div>"
        + f'<div class="card" style="margin-top:14px"><h3>Nội dung</h3>{noi_dung}</div>'
        + '<div class="card" style="margin-top:14px">'
          "<h3>Lịch sử phiên bản (đổi giá tự snapshot — đơn cũ giữ giá cũ)</h3>"
        + _bang(["Phiên bản", "Giá", "Duyệt", "Lúc"], pb, "Chưa có phiên bản nào")
        + "</div>"
    )
    return render_shell(f"SP {sp['name']}", "crm-products", body,
                        heading="Chi tiết sản phẩm",
                        sub="Màn 43 — nội dung được nói / nội dung cấm / phiên bản giá")


# ------------------------------------------------------------------ màn 45
def render_chi_tiet_lt(tpl: dict) -> str:
    sp = "".join(
        f"<tr><td>{_e(i['product_code'])}</td><td>{_e(i['product_name'])}</td>"
        f"<td>{_e(i['quantity'])}</td><td>{_e(i.get('dose_text'))}</td>"
        f"<td>{'có' if i.get('is_optional') else '—'}</td></tr>"
        for i in tpl["items"]
    )
    luat = _bang_luat(tpl["rules"])
    body = (
        '<p style="margin-bottom:10px">'
        '<a class="btn sm" href="/crm/san-pham?tab=lieu-trinh">← Danh mục</a> '
        f'<a class="btn sm" href="/crm/san-pham/lieu-trinh/{tpl["id"]}/luat">'
        "⚙️ Luật liệu trình (màn 46)</a></p>"
        '<div class="card" style="margin-bottom:14px">'
        f"<h3 style='margin:0 0 4px'>{_e(tpl['name'])} "
        f"<span class='pill'>{_e(tpl['status'])}</span></h3>"
        f"<p class='note' style='margin:0'>Mã {_e(tpl['template_code'])} v"
        f"{_e(tpl.get('version_no'))} · nhóm vấn đề {_e(tpl['problem_group'])} · "
        f"cấp độ {_e(tpl['level'])}</p></div>"
        + '<div class="stats">'
        + stat("Giá bộ", _tien(tpl["base_price"]))
        + stat("Thời gian dùng", f"{_e(tpl['duration_days'])} ngày")
        + stat("Số sản phẩm", str(len(tpl["items"])))
        + stat("Số luật", str(len(tpl["rules"])))
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Sản phẩm trong bộ</h3>'
        + _bang(["Mã", "Sản phẩm", "SL", "Cách dùng", "Tuỳ chọn"], sp,
                "Mẫu chưa có sản phẩm nào")
        + "</div>"
        + '<div class="card" style="margin-top:14px">'
          "<h3>Luật áp dụng (rút gọn — sửa ở màn 46)</h3>" + luat + "</div>"
    )
    return render_shell(f"Liệu trình {tpl['name']}", "crm-products", body,
                        heading="Chi tiết mẫu liệu trình",
                        sub="Màn 45 — sản phẩm · giá · thời gian · luật áp dụng")


def _bang_luat(rules: list[dict]) -> str:
    """Điều kiện lưu ở `condition_json` dạng {type, code|group, min_severity},
    câu hiển thị ở `action_json.message` (xem treatment_service.add_rule)."""
    dong = ""
    for r in rules:
        tone, nhan = _LOAI_LUAT.get(r["rule_type"], ("", r["rule_type"]))
        cond = r.get("condition_json") or {}
        act = r.get("action_json") or {}
        kieu = _KIEU_DK.get(cond.get("type"), cond.get("type") or "—")
        muc = cond.get("code") or cond.get("group") or cond.get("flag") or "—"
        nguong = (f" ≥ {cond['min_severity']}"
                  if cond.get("min_severity") is not None else "")
        dong += (
            f"<tr><td><span class='pill {tone}'>{escape(nhan.split(' — ')[0])}</span></td>"
            f"<td>{escape(str(kieu))}</td>"
            f"<td><code>{escape(str(muc))}{escape(nguong)}</code></td>"
            f"<td>{_e(act.get('message'))}</td>"
            f"<td>{_e(r.get('priority'))}</td></tr>"
        )
    return _bang(["Loại", "Kiểu điều kiện", "Áp cho", "Thông báo cho Sale", "Ưu tiên"],
                 dong, "Mẫu này chưa có luật nào — mọi khách đều thấy mẫu này")


# ------------------------------------------------------------------ màn 46
def render_luat_lt(tpl: dict, ok_msg: str = "", error: str = "") -> str:
    """Màn 46 — cấu hình luật: khi nào được chọn / bị chặn / cần duyệt."""
    flash = ""
    if ok_msg:
        flash = f'<div class="flash ok" style="margin-bottom:14px">{escape(ok_msg)}</div>'
    if error:
        flash = f'<div class="flash err" style="margin-bottom:14px">{escape(error)}</div>'

    giai_thich = "".join(
        f'<li><span class="pill {tone}">{escape(nhan.split(" — ")[0])}</span> '
        f"{escape(nhan.split(' — ', 1)[1])}</li>"
        for _ma, (tone, nhan) in _LOAI_LUAT.items()
    )
    opt_loai = "".join(
        f'<option value="{ma}">{escape(nhan.split(" — ")[0])}</option>'
        for ma, (_t, nhan) in _LOAI_LUAT.items()
    )
    opt_kieu = "".join(
        f'<option value="{ma}">{escape(nhan)}</option>'
        for ma, nhan in _KIEU_DK.items()
    )

    body = (
        '<p style="margin-bottom:10px">'
        f'<a class="btn sm" href="/crm/san-pham/lieu-trinh/{tpl["id"]}">← Chi tiết mẫu</a></p>'
        + flash
        + '<div class="card" style="margin-bottom:14px">'
        f"<h3 style='margin:0'>{_e(tpl['name'])}</h3>"
        f"<p class='note' style='margin:4px 0 0'>Mã {_e(tpl['template_code'])} · "
        f"nhóm {_e(tpl['problem_group'])}</p></div>"
        + '<div class="card"><h3>Ba loại luật</h3>'
          f'<ul style="margin:0;padding-left:18px">{giai_thich}</ul>'
          '<p class="note" style="margin:8px 0 0">Luật nằm trong DB '
          "(<code>treatment_rules</code>) — engine đọc mỗi lần đề xuất, "
          "sửa ở đây là lần tư vấn sau ăn ngay, không phải sửa code.</p></div>"
        + '<div class="card" style="margin-top:14px"><h3>Luật đang có</h3>'
        + _bang_luat(tpl["rules"]) + "</div>"
        + '<form class="card form" method="post" style="margin-top:14px" '
          f'action="/crm/san-pham/lieu-trinh/{tpl["id"]}/luat"><h3>Thêm luật</h3>'
          '<div class="grid2">'
          f'<label>Loại luật<select name="rule_type" required>{opt_loai}</select></label>'
          f'<label>Kiểu điều kiện<select name="cond_type" required>{opt_kieu}</select></label>'
          '<label>Áp cho (mã) *<input type="text" name="code" required '
          'placeholder="sàng lọc: benh_nen · triệu chứng: mã · cờ: red/yellow"></label>'
          '<label>Mức tối thiểu (kiểu triệu chứng)<input type="number" '
          'name="min_severity" min="0" max="10"></label>'
          '<label>Thông báo hiện cho Sale *<input type="text" name="message" required '
          'placeholder="vd Khách có bệnh nền — cần chuyên môn duyệt"></label>'
          '<label>Ưu tiên<input type="number" name="priority" value="0"></label>'
          "</div>"
          '<button class="btn primary" style="margin-top:10px">➕ Thêm luật</button>'
          "</form>"
    )
    return render_shell(f"Luật {tpl['name']}", "crm-products", body,
                        heading="Luật liệu trình",
                        sub="Màn 46 — khi nào được chọn · bị chặn · cần duyệt")
