"""Màn 13 (tư vấn khách) · 14 (phiếu khai thác) · 15 (đề xuất liệu trình).

Ba màn của đặc tả đi chung một khu vực làm việc `/crm/tu-van/{customer_id}`
chia 3 tab, vì thực tế Sale làm liền mạch: nhìn hội thoại → khai thác → đề
xuất. Tách 3 URL riêng thì phải nhảy qua lại và mất ngữ cảnh khách.

Luật hiển thị bám B5/B6: cờ ĐỎ thì chặn đề xuất ngay trên màn (không đợi bấm
mới báo lỗi); mục sàng lọc đỏ/vàng tô khác nhau; thiếu câu bắt buộc thì liệt kê
rõ thiếu gì.
"""

from html import escape

from app.integrations.pancake.links import link_hoi_thoai
from app.web.shell import render_shell, stat

from app.web.views.crm import _bang, _dt, _e, _tien

_TABS = [("tu-van", "💬 Tư vấn"), ("khai-thac", "📋 Khai thác tình trạng"),
         ("de-xuat", "💊 Đề xuất liệu trình")]

_MUC_CO = {"red": ("err", "🔴"), "yellow": ("warn", "🟡")}


def _dau(kh: dict, tab: str) -> str:
    co = ""
    if kh.get("safety_flag") in _MUC_CO:
        tone, icon = _MUC_CO[kh["safety_flag"]]
        nhan = "Cờ đỏ — CHẶN đề xuất" if kh["safety_flag"] == "red" else "Cờ vàng"
        co = f'<span class="pill {tone}">{icon} {nhan}</span>'
    tabs = "".join(
        f'<a class="tab{" on" if ma == tab else ""}" '
        f'href="/crm/tu-van/{kh["id"]}?tab={ma}">{escape(nhan)}</a>'
        for ma, nhan in _TABS
    )
    return (
        '<p style="margin-bottom:10px">'
        f'<a class="btn sm" href="/crm/khach-hang/{kh["id"]}">← Hồ sơ 360°</a></p>'
        '<div class="card" style="margin-bottom:14px">'
        f"<h3 style='margin:0 0 4px'>{_e(kh['full_name'])} {co}</h3>"
        f"<p class='note' style='margin:0'>SĐT {_e(kh['primary_phone'])} · "
        f"trạng thái {_e(kh['status'])}</p></div>"
        f'<nav class="tabs">{tabs}</nav>'
    )


# ------------------------------------------------------------------ màn 13
def _tab_tu_van(kh: dict, d: dict) -> str:
    """Hiển thị SONG SONG: hội thoại khách | hồ sơ + checklist + gợi ý."""
    tin = ""
    for m in d["tin"]:
        ben = m["sender_type"] in ("agent", "bot")
        le = "margin-left:auto;background:#e8f0fe" if ben else ""
        tin += (
            f'<div style="max-width:80%;{le};border:1px solid var(--border);'
            'border-radius:10px;padding:7px 9px;margin:5px 0">'
            f'<div class="note" style="font-size:11px">{_e(m.get("sender_name"))} · '
            f'{_dt(m["sent_at"])}</div>'
            f'<div style="white-space:pre-wrap">{_e(m["content"])}</div></div>'
        )
    if not tin:
        tin = ('<p class="note">Chưa kéo nội dung tin nhắn về CRM — bật '
               '<b>Kéo nội dung tin nhắn</b> ở <a href="/quan-tri/cai-dat">Cài đặt</a>.</p>')

    # checklist 7 câu bắt buộc (CONSULT-005)
    ck = ""
    for ma, nhan in d["cau_hoi"].items():
        co = ma in d["da_co"]
        ck += (f'<li>{"✅" if co else "⬜"} {escape(nhan)}'
               f'{"" if co else " <span class=note>— còn thiếu</span>"}</li>')

    # sàng lọc đã làm / chưa làm
    sl = ""
    for ma, (nhan, muc) in d["sang_loc"].items():
        r = d["da_sang_loc"].get(ma)
        icon = _MUC_CO[muc][1]
        if r:
            sl += (f'<li>{icon} <b>{escape(nhan)}</b>: {_e(r["value"])} '
                   f'<span class="note">({_e(r["risk_level"])})</span></li>')
    if not sl:
        sl = '<li class="note">Chưa sàng lọc mục nào</li>'

    lt = "".join(
        f'<li>{escape(t["name"])} <span class="note">— {_tien(t["base_price"])}</span></li>'
        for t in d["lieu_trinh_goi_y"][:5]
    ) or '<li class="note">Chưa có gợi ý (khai thác triệu chứng trước)</li>'

    link = link_hoi_thoai(d.get("external_page_id") or "",
                          d.get("external_conversation_id") or "")
    nut = (
        (f'<a class="btn sm" href="{escape(link)}" target="_blank" rel="noopener">'
         "💬 Mở Pancake</a> " if link else "")
        + (f'<a class="btn sm" href="tel:{escape(kh["primary_phone"] or "")}">📞 Gọi</a> '
           if kh.get("primary_phone") else "")
        + f'<a class="btn sm" href="/crm/tu-van/{kh["id"]}?tab=khai-thac">'
          "📋 Khai thác</a> "
        + f'<a class="btn sm" href="/crm/tu-van/{kh["id"]}?tab=de-xuat">💊 Đề xuất</a> '
        + f'<form method="post" action="/crm/tu-van/{kh["id"]}/chuyen-chuyen-mon" '
          'style="display:inline">'
          '<input type="text" name="reason" placeholder="Lý do chuyển *" required '
          'style="width:190px"> <button class="btn sm">🩺 Chuyển chuyên môn</button></form>'
    )

    return (
        f'<div class="card" style="margin-bottom:14px">{nut}</div>'
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">'
        '<div class="card"><h3>Hội thoại khách</h3>'
        f'<div style="display:flex;flex-direction:column;max-height:520px;'
        f'overflow:auto">{tin}</div></div>'
        '<div>'
        '<div class="card"><h3>Checklist câu hỏi bắt buộc</h3>'
        f'<ul style="margin:0;padding-left:18px">{ck}</ul></div>'
        '<div class="card" style="margin-top:14px"><h3>Sàng lọc an toàn</h3>'
        f'<ul style="margin:0;padding-left:18px">{sl}</ul></div>'
        '<div class="card" style="margin-top:14px"><h3>Liệu trình có thể cân nhắc</h3>'
        f'<ul style="margin:0;padding-left:18px">{lt}</ul></div>'
        "</div></div>"
    )


# ------------------------------------------------------------------ màn 14
def _tab_khai_thac(kh: dict, d: dict) -> str:
    """Phiếu khai thác: triệu chứng (dữ liệu cấu trúc) + 11 mục sàng lọc."""
    # --- triệu chứng đã khai ---
    da_khai = "".join(
        f"<tr><td>{_e(r['symptom_name'])}</td><td>{_e(r['severity'])}</td>"
        f"<td>{_e(r['frequency'])}</td><td>{_e(r.get('occurs_when'))}</td>"
        f"<td>{_e(r.get('meal_relation'))}</td></tr>"
        for r in d["trieu_chung"]
    )
    opt_tc = "".join(
        f'<option value="{s["id"]}">{escape(s["name"])}</option>'
        for s in d["danh_muc_trieu_chung"]
    )
    form_tc = (
        f'<form class="form" method="post" action="/crm/tu-van/{kh["id"]}/trieu-chung" '
        'style="margin-top:10px"><div class="grid2">'
        f'<label>Triệu chứng<select name="symptom_id" required>{opt_tc}</select></label>'
        '<label>Mức độ 0-10<input type="number" name="severity" min="0" max="10"></label>'
        '<label>Tần suất<select name="frequency"><option value="">—</option>'
        '<option value="rare">Hiếm</option><option value="sometimes">Thỉnh thoảng</option>'
        '<option value="often">Thường xuyên</option><option value="daily">Hàng ngày</option>'
        '<option value="constant">Liên tục</option></select></label>'
        '<label>Liên quan bữa ăn<select name="meal_relation"><option value="">—</option>'
        '<option value="truoc_an">Trước ăn</option><option value="sau_an">Sau ăn</option>'
        '<option value="khi_doi">Khi đói</option>'
        '<option value="khong_lien_quan">Không liên quan</option></select></label>'
        '<label>Thời điểm xuất hiện<input type="text" name="occurs_when" '
        'placeholder="vd đêm, sáng sớm"></label>'
        '<label>Ghi chú thêm<input type="text" name="note"></label>'
        '</div><p class="note">FR-050: phải có <b>mức độ</b> hoặc <b>tần suất</b> — '
        "ghi chú KHÔNG thay được dữ liệu cấu trúc.</p>"
        '<button class="btn primary">➕ Lưu triệu chứng</button></form>'
    )

    # --- 11 mục sàng lọc ---
    o_sl = ""
    for ma, (nhan, muc) in d["sang_loc"].items():
        r = d["da_sang_loc"].get(ma)
        icon = _MUC_CO[muc][1]
        hien = (f'<span class="pill {_MUC_CO[muc][0]}">đã ghi: {_e(r["value"])}</span>'
                if r else '<span class="note">chưa ghi</span>')
        o_sl += (
            f'<form method="post" action="/crm/tu-van/{kh["id"]}/sang-loc" '
            'style="display:flex;gap:8px;align-items:center;margin:6px 0;flex-wrap:wrap">'
            f'<input type="hidden" name="screening_type" value="{ma}">'
            f'<span style="min-width:210px">{icon} <b>{escape(nhan)}</b></span>'
            '<input type="text" name="value" placeholder="Trả lời / mô tả" '
            'style="flex:1;min-width:160px" required>'
            f'<button class="btn sm">Lưu</button>{hien}</form>'
        )

    canh = ""
    if kh.get("safety_flag") == "red":
        canh = ('<div class="flash err" style="margin-bottom:14px">🔴 Khách đang có '
                "<b>cờ đỏ</b> — mọi đề xuất liệu trình bị CHẶN cho tới khi Người "
                "chuyên môn gỡ cờ (FR-053).</div>")

    return (
        canh
        + '<div class="card"><h3>Triệu chứng đã khai (màn 14)</h3>'
        + _bang(["Triệu chứng", "Mức độ", "Tần suất", "Thời điểm", "Bữa ăn"],
                da_khai, "Chưa khai triệu chứng nào")
        + form_tc + "</div>"
        + '<div class="card" style="margin-top:14px">'
          "<h3>11 mục sàng lọc an toàn (FR-053)</h3>"
          '<p class="note">🔴 = báo động, ghi vào là CHẶN đề xuất + mở ca chuyên môn '
          "ngay · 🟡 = thận trọng, đề xuất phải chuyên môn duyệt.</p>"
        + o_sl + "</div>"
    )


# ------------------------------------------------------------------ màn 15
def _tab_de_xuat(kh: dict, d: dict) -> str:
    if d.get("bi_chan"):
        return ('<div class="flash err">🔴 <b>Không đề xuất được</b> — '
                f"{escape(d['bi_chan'])}<br>Gỡ cờ phải qua Người chuyên môn "
                "(SAFETY-005), Sale không tự bỏ qua được (FR-062).</div>")
    if d.get("thieu_du_lieu"):
        return ('<div class="flash warn">⚠ Chưa đủ dữ liệu để đề xuất: '
                f"{escape(d['thieu_du_lieu'])}<br>"
                f'<a class="btn sm" href="/crm/tu-van/{kh["id"]}?tab=khai-thac" '
                'style="margin-top:8px">📋 Sang khai thác</a></div>')

    kq = d["ket_qua"]
    hien = ""
    for t in kq.get("de_xuat") or []:
        ly_do = "".join(f"<li>{escape(str(x))}</li>" for x in (t.get("ly_do") or []))
        cb = "".join(f"<li>⚠ {escape(str(x))}</li>" for x in (t.get("canh_bao") or []))
        can_duyet = bool(t.get("canh_bao"))
        hien += (
            '<div class="card" style="margin-top:14px">'
            f"<h3>{_e(t['name'])} <span class='pill'>{_tien(t['base_price'])}</span>"
            + (' <span class="pill warn">cần chuyên môn duyệt</span>'
               if can_duyet else "")
            + "</h3>"
            f"<p class='note'>Nhóm {_e(t.get('problem_group'))} · "
            f"{_e(t.get('duration_days'))} ngày</p>"
            + (f"<p><b>Vì sao phù hợp:</b></p><ul>{ly_do}</ul>" if ly_do else "")
            + (f"<ul style='color:var(--warn)'>{cb}</ul>" if cb else "")
            + f'<form method="post" action="/crm/tu-van/{kh["id"]}/chon-lieu-trinh">'
              f'<input type="hidden" name="template_id" value="{t["template_id"]}">'
              '<input type="text" name="note" placeholder="Ghi chú (không bắt buộc)" '
              'style="width:260px"> '
              '<button class="btn primary">✔ Chọn liệu trình này</button></form>'
            "</div>"
        )
    if not hien:
        hien = ('<div class="flash warn" style="margin-top:14px">Không mẫu liệu trình '
                "nào khớp hồ sơ khách hiện tại.</div>")

    loai = "".join(
        f"<tr><td>{_e(t['name'])}</td><td>{_e('; '.join(map(str, t.get('loai_vi') or [])))}</td></tr>"
        for t in (kq.get("loai_tru") or [])
    )
    cb_chung = "".join(
        f'<li>{escape(str(x))}</li>' for x in (kq.get("canh_bao_chung") or []))

    da_luu = "".join(
        f"<tr><td>{_e(r['template_name'])}</td>"
        f"<td><span class='pill'>{_e(r['status'])}</span></td>"
        f"<td>{_e(r['nguoi_de_xuat'])}</td><td>{_dt(r['created_at'])}</td></tr>"
        for r in d.get("da_de_xuat") or []
    )

    return (
        (f'<div class="flash warn"><ul style="margin:0;padding-left:18px">{cb_chung}'
         "</ul></div>" if cb_chung else "")
        + '<div class="stats">'
        + stat("Mẫu phù hợp", str(len(kq.get("de_xuat") or [])), tone="ok")
        + stat("Bị loại trừ", str(len(kq.get("loai_tru") or [])))
        + "</div>"
        + hien
        + '<div class="card" style="margin-top:14px"><h3>Mẫu bị loại trừ &amp; lý do</h3>'
        + _bang(["Mẫu liệu trình", "Loại vì"], loai, "Không mẫu nào bị loại")
        + "</div>"
        + '<div class="card" style="margin-top:14px"><h3>Đề xuất đã lưu</h3>'
        + _bang(["Mẫu", "Trạng thái", "Người đề xuất", "Lúc"], da_luu,
                "Chưa lưu đề xuất nào")
        + "</div>"
    )


def render_tu_van(kh: dict, tab: str, d: dict,
                  ok_msg: str = "", error: str = "") -> str:
    flash = ""
    if ok_msg:
        flash = f'<div class="flash ok" style="margin-bottom:14px">{escape(ok_msg)}</div>'
    if error:
        flash = f'<div class="flash err" style="margin-bottom:14px">{escape(error)}</div>'

    if tab == "khai-thac":
        than, sub = _tab_khai_thac(kh, d), "Màn 14 — phiếu khai thác tình trạng"
    elif tab == "de-xuat":
        than, sub = _tab_de_xuat(kh, d), "Màn 15 — đề xuất liệu trình theo rule engine"
    else:
        than, sub = _tab_tu_van(kh, d), "Màn 13 — hội thoại · hồ sơ · checklist · gợi ý"

    body = _dau(kh, tab) + f'<div style="margin-top:14px">{flash}{than}</div>'
    return render_shell(f"Tư vấn {kh['full_name']}", "crm-customers", body,
                        heading="Tư vấn khách hàng", sub=sub)
