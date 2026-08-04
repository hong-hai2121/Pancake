"""Màn BẢNG VIỆC SALE (C5 — port mẫu Kallet trang-chu.php + board_rules.php).

Hai chế độ xem CÙNG một tập thẻ:
  * **Bảng**    — 1 khách 1 dòng, xem nhanh, lọc gọn.
  * **Pipeline** — cột theo bước thang, kéo thẻ được.

Ba thứ giao diện KHÔNG được bỏ, vì thiếu là bảng thành vô dụng:

  1. **Câu việc cần làm trên từng thẻ** (📌). Nhân viên mở bảng ra phải biết
     NGAY phải gõ gì, không phải đoán.
  2. **Gợi ý câu chữ cho bước kế.** Họ gõ theo gợi ý ⇒ bộ dò đọc đúng bước ⇒
     bảng tự dạy người dùng nuôi chính nó.
  3. **Lý do thẻ đang chờ** ("nghỉ 6 giờ giữa 2 bước", "ngoài cửa 8h–21h").
     Thẻ xám không giải thích được là nhân viên tưởng hệ thống hỏng.

Và hai nút đóng khách CỐ Ý khác nhau:
  🚫 **Từ chối** — đóng đợt này, KHÔNG hỏi xác nhận (bấm mấy chục lần/ngày).
  ⛔ **Ngừng chăm sóc** — dừng hẳn, CÓ hỏi + bắt buộc lý do.
"""

from html import escape
from urllib.parse import quote

from app.services import sale_service as svc
from app.web.shell import _icon, render_shell


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _so(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".")


def _truoc(dt) -> str:
    """'3 giờ trước' — nhân viên đọc khoảng cách nhanh hơn đọc mốc tuyệt đối."""
    if not dt:
        return "—"
    from app.core.ngay import bay_gio

    giay = (bay_gio() - dt).total_seconds()
    if giay < 3600:
        return f"{int(giay // 60)} phút trước"
    if giay < 86400:
        return f"{int(giay // 3600)} giờ trước"
    return f"{int(giay // 86400)} ngày trước"


def _url(hien_tai: dict, **doi) -> str:
    """Đường dẫn màn này với bộ lọc hiện tại, ghi đè vài tham số.

    Tham số đầu CỐ Ý không tên `loc`: bộ lọc có một khoá TÊN LÀ `loc` (ô đếm
    đang chọn), gọi `_url(loc, loc=...)` sẽ đụng tên ngay."""
    tham = dict(hien_tai)
    tham.update(doi)
    cai = [(k, v) for k, v in tham.items() if v not in ("", None, 0)]
    duoi = "&".join(f"{k}={quote(str(v))}" for k, v in cai)
    return "/crm/bang-viec" + (f"?{duoi}" if duoi else "")


def _o_dem(dem: dict, loc: dict) -> str:
    """4 ô đếm đầu bảng — bấm là lọc, bấm lại là bỏ lọc."""
    o = [("hom_nay", "Cần làm hôm nay", "#2EAD6E"),
         ("qua_han", "Quá hạn", "#B0413E"),
         ("vua_phan_hoi", "Vừa phản hồi — chờ đáp", "#E0A417"),
         ("yeu_cau_chia", "Chưa có người phụ trách", "#4E7FE8")]
    ra = ""
    for ma, nhan, mau in o:
        bat = (loc.get("loc") or "") == ma
        href = _url(loc, loc="" if bat else ma)
        ra += (f'<a class="vc-tile{" on" if bat else ""}" style="--c:{mau}" '
               f'href="{escape(href)}">'
               f'<span class="vc-vach" style="background:{mau}"></span>'
               f'<div class="vc-num" style="color:{mau}">'
               f'{_so(dem.get(ma))}</div>'
               f'<div class="vc-lbl">{escape(nhan)}</div>'
               '<div class="vc-sub">&nbsp;</div></a>')
    return f'<div class="vc-tiles">{ra}</div>'


def _nut_dong(l: dict) -> str:
    """Hai nút đóng khách — khác nhau CỐ Ý, đừng gộp."""
    return (
        f'<form method="post" action="/crm/bang-viec/{l["id"]}/tu-choi" '
        'class="vc-inline"><button class="kh-btn" type="submit" '
        'title="Đóng ĐỢT NÀY — đợt sau vẫn chăm. Khách nhắn lại là thẻ tự '
        'quay về bảng">🚫 Từ chối</button></form>'
        f'<form method="post" action="/crm/bang-viec/{l["id"]}/ngung" '
        'class="vc-inline" onsubmit="return confirm(\'NGỪNG CHĂM SÓC hẳn khách '
        "này?\\n\\nKhác với Từ chối: thẻ KHÔNG tự quay lại, phải chờ khách nhắn "
        "trước.')\">"
        '<input name="ly_do" required placeholder="Lý do (bắt buộc)" '
        'style="width:150px">'
        '<button class="kh-btn" type="submit" title="Dừng HẲN tới khi khách '
        'nhắn lại trước">⛔ Ngừng</button></form>')


def _the(l: dict, cot_ds: list[dict]) -> str:
    """Một thẻ khách trên pipeline."""
    ke = l.get("buoc_ke")
    if l["cho_dap"]:
        viec = ('<div class="bv-viec urgent">💬 Khách vừa nhắn — ĐÁP KHÁCH '
                "trước, con trỏ đứng yên</div>")
    elif ke:
        chip = "".join(f'<span class="bv-chip">{escape(g)}</span>'
                       for g in (l.get("goi_y") or []))
        tre = ("" if ke["san_sang"] else
               f'<span class="bv-cho">⏳ {escape(l["ly_do_cho"])}</span>')
        viec = (f'<div class="bv-viec">📌 <b>Bước {ke["step_no"]}</b> · '
                f'{escape(ke["work"] or ke["name"])} {tre}</div>'
                + (f'<div class="bv-chips">{chip}</div>' if chip else ""))
    else:
        viec = '<div class="bv-viec">✅ Hết thang bám đuổi</div>'

    keo = "".join(
        f'<option value="{c["ma"]}"{" selected" if c["ma"] == l["cot"] else ""}>'
        f'{escape(c["ten"])}</option>' for c in cot_ds if c["keo"])
    link = ""
    if l.get("external_page_id") and l.get("external_conversation_id"):
        from app.integrations.pancake.links import link_hoi_thoai

        u = link_hoi_thoai(l["external_page_id"], l["external_conversation_id"])
        link = (f'<a class="kh-ic" href="{escape(u)}" target="_blank" '
                f'rel="noopener" title="Mở Pancake">{_icon("external-link")}</a>')
    return (
        f'<div class="bv-the{" nong" if ke and ke.get("nong") else ""}">'
        f'<div class="bv-h"><a class="kh-name" '
        f'href="/crm/khach-hang/{l["customer_id"]}">{_e(l["full_name"])}</a>'
        + (f'<span class="bv-nong">🔥 nóng</span>' if ke and ke.get("nong")
           else "")
        + f'<span class="kh-sp"></span>'
          f'<span class="kh-nho">{_truoc(l.get("khach_cuoi"))}</span></div>'
        f'<div class="kh-sub">{_e(l.get("primary_phone"))} · '
        f'{_e(l.get("owner_name"))}</div>'
        + (f'<div class="bv-qh">⚠️ {escape(l["qua_han"])}</div>'
           if l.get("qua_han") else "")
        + viec
        + '<div class="bv-f">'
          f'<a class="kh-ic go" href="/crm/khach-hang/{l["customer_id"]}'
          f'?tab=hoi-thoai" title="Mở hội thoại trong CRM">'
          f'{_icon("message-circle")}</a>{link}'
          f'<form method="post" action="/crm/bang-viec/{l["id"]}/keo" '
          'class="vc-inline">'
          f'<select name="cot" onchange="this.form.requestSubmit()">{keo}'
          "</select></form></div>"
        + f'<details class="bv-nut"><summary>Đóng khách</summary>'
          f'<div class="ds-acts">{_nut_dong(l)}</div></details>'
        "</div>"
    )


def _pipeline(data: dict) -> str:
    cot = ""
    for c in data["cot"]:
        ds = data["theo_cot"].get(c["ma"], [])
        the = "".join(_the(l, data["cot"]) for l in ds) or (
            '<div class="bv-rong">—</div>')
        cot += (f'<div class="bv-cot"><div class="bv-cot-h" '
                f'style="border-color:{c["mau"]}">'
                f'<b>{escape(c["ten"])}</b>'
                f'<span class="bv-dem">{len(ds)}</span></div>'
                f'<div class="bv-cot-h2">📌 {escape(c["viec"])}</div>'
                + ("" if c["keo"] else
                   '<div class="bv-khoa">🔒 máy suy ra — không kéo tay</div>')
                + f"{the}</div>")
    return f'<div class="bv-board">{cot}</div>'


def _bang(data: dict) -> str:
    than = ""
    for l in data["the"]:
        ke = l.get("buoc_ke")
        viec = ("💬 Đáp khách" if l["cho_dap"] else
                (f'Bước {ke["step_no"]} · {ke["work"] or ke["name"]}'
                 + ("" if ke["san_sang"] else f' ({l["ly_do_cho"]})')
                 if ke else "✅ hết thang"))
        cot = next((c for c in data["cot"] if c["ma"] == l["cot"]), None)
        than += (
            "<tr>"
            f'<td><a class="kh-name" href="/crm/khach-hang/{l["customer_id"]}">'
            f'{_e(l["full_name"])}</a>'
            f'<div class="kh-sub">{_e(l.get("primary_phone"))}</div></td>'
            f'<td><span class="kh-st chua" style="background:'
            f'{cot["mau"] if cot else "var(--soft)"}22;color:'
            f'{cot["mau"] if cot else "var(--sub)"}">'
            f'{escape(cot["ten"] if cot else l["cot"])}</span>'
            f'<div class="kh-nho">{escape(l["cot_vi_sao"])}</div></td>'
            f'<td class="num">{int(l.get("sale_step") or 0)}</td>'
            f"<td>{escape(viec)}</td>"
            f'<td>{_e(l.get("owner_name"))}</td>'
            f'<td class="kh-nho">{_truoc(l.get("khach_cuoi"))}</td>'
            f'<td><div class="ds-acts">{_nut_dong(l)}</div></td>'
            "</tr>")
    than = than or ('<tr><td colspan="7" class="rong">Không có việc nào — '
                    "hoặc đã chăm hết khách hôm nay 🎉</td></tr>")
    return ('<div class="kh-card"><div class="kh-tblwrap">'
            '<table class="kh-tbl"><thead><tr>'
            "<th>Khách</th><th>Cột</th><th class=\"num\">Bước</th>"
            "<th>Việc cần làm</th><th>Phụ trách</th><th>Khách nhắn</th>"
            "<th>Đóng khách</th></tr></thead>"
            f"<tbody>{than}</tbody></table></div></div>")


def _rong(data: dict, loc: dict, ca_doi: bool, quan_ly: bool) -> str:
    """Bảng trống thì phải nói RÕ vì sao trống + cách xem tiếp.

    Màn trống không giải thích là nguồn gốc câu "sao không có dữ liệu" — người
    dùng không có cách nào biết là do bộ lọc hay do hệ thống hỏng."""
    if data["the"]:
        return ""
    if loc.get("loc"):
        return ('<div class="flash warn">Không có thẻ nào trong ô đếm vừa bấm. '
                f'<a href="{escape(_url(loc, loc=""))}">Bỏ lọc</a> để xem lại '
                "toàn bộ.</div>")
    if not ca_doi:
        them = ('<a href="' + escape(_url(loc, tatca=1)) + '">Xem cả đội</a>'
                if quan_ly else
                "Nếu bạn chắc là mình có khách, báo quản lý kiểm tra phần chia "
                "khách")
        return ('<div class="flash warn">Bạn <b>chưa được giao lead nào</b> '
                f"đang mở, nên bảng trống. {them}.</div>")
    return ('<div class="flash warn">Chưa có lead nào đang mở trong hệ thống — '
            "hoặc mọi khách đều đã được chăm hôm nay. Bỏ tick "
            "<b>“Hiện cả khách đã chăm hôm nay”</b> ở trên để kiểm.</div>")


def render_bang_viec(data: dict, *, loc: dict, che_do: str = "bang",
                     ca_doi: bool = False, quan_ly: bool = False,
                     flash: str = "", loi: str = "") -> str:
    tab = "".join(
        f'<a class="tab{" on" if che_do == ma else ""}" '
        f'href="{escape(_url(loc, cd=ma))}">{escape(nhan)}</a>'
        for ma, nhan in [("bang", "▤ Chế độ Bảng"),
                         ("pipeline", "▥ Chế độ Pipeline")])
    khung = ""
    if not svc.bat():
        khung = ('<div class="flash warn">Thang bám đuổi <b>chưa có bước nào</b>'
                 " — bảng đang xếp mọi khách vào Mới/Tiềm năng. Chạy "
                 "<code>python scripts/seed_thang_sale.py</code> để nạp thang "
                 "8 bước mẫu.</div>")
    body = (
        (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + (f'<div class="flash err">{escape(loi)}</div>' if loi else "")
        + khung
        + '<div class="flash warn" style="background:var(--soft);color:'
          'var(--text)">🤖 Cột trên bảng do <b>máy đọc tin nhắn thật</b> suy ra '
          f'(thang tính từ <b>{svc.ngay_bat_thang():%d/%m/%Y}</b>), khác với '
          '<a href="/crm/pipeline">Pipeline giai đoạn</a> do người tự kéo. Hai '
          "thứ chạy song song: giai đoạn = <i>khách ở đâu trong quy trình</i>, "
          "bước = <i>câu tiếp theo cần nói</i>.</div>"
        + _o_dem(data["dem"], loc)
        + '<form class="kh-filters" method="get" action="/crm/bang-viec">'
          f'<input type="hidden" name="cd" value="{escape(che_do)}">'
          f'<label class="kh-find">{_icon("search")}'
          f'<input name="q" value="{escape(loc.get("q") or "")}" '
          'placeholder="Tìm tên khách · số điện thoại…"></label>'
          # Ô "Xem cả đội": quản lý mặc định BẬT sẵn (họ không ôm lead nên
          # "chỉ của tôi" luôn trống); nhân viên thường thì khoá lại.
          '<label class="kh-btn" style="cursor:pointer"'
          + ("" if quan_ly else
             ' title="Chỉ quản lý mới xem được khách của người khác"')
          + '><input type="checkbox" name="tatca" value="1"'
          + (" checked" if ca_doi else "")
          + ("" if quan_ly else " disabled")
          + ' onchange="this.form.requestSubmit()"> Xem cả đội</label>'
          '<label class="kh-btn" style="cursor:pointer">'
          '<input type="checkbox" name="hien_da_cham" value="1"'
          + (" checked" if loc.get("hien_da_cham") else "")
          + ' onchange="this.form.requestSubmit()"> Hiện cả khách đã chăm hôm '
            "nay</label>"
          '<span class="kh-sp"></span>'
          f'<span class="cnt">{_so(len(data["the"]))} thẻ'
          + (" · cả đội" if ca_doi else " · của tôi") + "</span>"
          "</form>"
        + _rong(data, loc, ca_doi, quan_ly)
        + f'<div class="tabs" style="margin-bottom:12px">{tab}</div>'
        + (_pipeline(data) if che_do == "pipeline" else _bang(data))
        + '<p class="note" style="margin-top:10px">🚫 <b>Từ chối</b> = đóng đợt '
          "này, khách nhắn lại là thẻ <b>tự quay về</b> bảng (không hỏi xác "
          "nhận vì bấm nhiều lần trong ngày). ⛔ <b>Ngừng chăm sóc</b> = dừng "
          "hẳn, có hỏi + bắt buộc lý do, thẻ <b>không tự quay lại</b>.</p>"
    )
    return render_shell(
        "Bảng việc Sale", "crm-board", body,
        heading="Bảng việc Sale",
        sub="Thang bám đuổi · máy đọc tin nhắn thật để biết cần nói gì tiếp",
    )


# ------------------------------------------------------------ cấu hình thang
def render_thang(buoc: list[dict], *, flash: str = "", loi: str = "") -> str:
    dong = "".join(
        "<tr>"
        f'<td class="num">{r["step_no"]}</td>'
        f'<td><b>{_e(r["name"])}</b><div class="kh-sub">{_e(r["work"])}</div></td>'
        f'<td class="kh-nho">{_e(r["keywords_agent"])}</td>'
        f'<td class="kh-nho">{_e(r["keywords_customer"])}</td>'
        "</tr>" for r in buoc) or (
        '<tr><td colspan="4" class="rong">Thang chưa có bước nào.</td></tr>')
    body = (
        (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + (f'<div class="flash err">{escape(loi)}</div>' if loi else "")
        + '<div class="flash warn">⚠️ <b>Từ khoá phải là CỤM NHIỀU CHỮ.</b> Máy '
          "bỏ dấu trước khi so, nên từ đơn hay đụng nhau: "
          "<code>đắt</code> → <code>dat</code> đụng luôn <code>đặt hàng</code>. "
          'Dùng <code>"đắt quá", "sao đắt"</code> thay vì <code>"đắt"</code>.'
          "</div>"
        + '<div class="kh-card"><div class="kh-tblwrap"><table class="kh-tbl">'
          '<thead><tr><th class="num">Bước</th><th>Tên / việc cần làm</th>'
          "<th>Từ khoá NHÂN VIÊN nói (đã làm bước)</th>"
          "<th>Từ khoá KHÁCH nói (nhảy cóc tới)</th></tr></thead>"
          f"<tbody>{dong}</tbody></table></div></div>"
        + '<div class="kh-card" style="padding:16px 18px;margin-top:14px">'
          '<div class="ht-h">Thêm / sửa bước</div>'
          '<form method="post" action="/crm/thang-sale" class="vc-form-r">'
          '<label style="flex:0 1 90px">Số bước'
          '<input type="number" name="step_no" min="1" max="20" required></label>'
          '<label style="flex:1 1 180px">Tên bước'
          '<input name="name" required placeholder="vd Báo giá"></label>'
          '<label style="flex:2 1 220px">Việc cần làm (câu 📌 trên thẻ)'
          '<input name="work" placeholder="Gửi bảng giá cho khách"></label>'
          '<label style="flex:3 1 100%">Từ khoá NHÂN VIÊN nói'
          '<input name="kw_nv" placeholder="#gia, bảng giá, giá bên em, chi phí '
          'liệu trình"></label>'
          '<label style="flex:3 1 100%">Từ khoá KHÁCH nói → nhảy cóc tới bước này'
          '<input name="kw_kh" placeholder="bao nhiêu tiền, giá thế nào"></label>'
          '<button class="kh-btn go" type="submit">Lưu bước</button>'
          "</form>"
          '<p class="note">Ba từ máy tự hiểu: <code>#anh</code> (tin có ảnh) · '
          "<code>#gia</code> (tin có số tiền) · <code>#ma</code> (tin có mã "
          "giảm). Bước 1 và bước cuối cố ý để trống ô nhảy cóc.</p></div>"
    )
    return render_shell(
        "Thang bám đuổi Sale", "crm-board", body,
        heading="Thang bám đuổi Sale",
        sub="Máy dò từ khoá trong tin để biết đã đi tới bước nào",
    )
