"""Màn BẢNG VIỆC CSKH + đợt khuyến mãi (C6, port từ mẫu Kallet).

Nguồn mẫu: `index.php?bp=cskh` (bảng việc CSKH) và phần "Khuyến mãi CSKH" của
`cai-dat.php`. Bố cục giữ đúng mẫu:

    dải ô đếm → thanh lọc → kanban cột (thẻ khách + câu việc 📌)

Ba luật giao diện của mẫu, giữ nguyên:

  * **Câu việc 📌 không bao giờ chung chung.** Cột gấp phải nói rõ khách đang ở
    nhịp nào / vì lý do gì — hai nhịp khác nhau thì độ gấp khác hẳn.
  * **Màu không đứng một mình**, luôn kèm chữ.
  * **Cột máy suy ra hoàn toàn thì KHÔNG cho kéo tay** — kéo vào đó là nói dối
    dữ liệu; ô chọn cột tự ẩn những cột này.

CSS riêng của màn để ngay trong file (không nhét vào `shell._CSS`): đây là màn
mới của lát C6, gom một chỗ thì gỡ ra cũng gọn.
"""

from html import escape

from app.services import cskh_service as svc
from app.web.shell import _icon, render_shell

_CSS = """
<style>
.cs-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:10px;margin-bottom:14px}
.cs-tile{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:11px 13px;position:relative;overflow:hidden;text-decoration:none;
  display:block;box-shadow:var(--shadow)}
.cs-tile .num{font-size:23px;font-weight:900;line-height:1.1}
.cs-tile .lbl{font-size:11.5px;color:var(--sub);margin-top:3px;font-weight:600}
.cs-tile .vach{position:absolute;left:0;top:0;bottom:0;width:4px}
.cs-warn{border-color:#F1C48B;background:#FFF8EE}
.cs-banner{border-radius:12px;padding:11px 14px;margin-bottom:13px;font-size:13px;
  line-height:1.6;border:1px solid}
.cs-off{background:#FFF6E5;border-color:#F1C48B;color:#8A5A00}
.cs-on{background:#E8F5EC;border-color:#A9D9BC;color:#1E6B3E}
.cs-kan{display:flex;gap:11px;overflow-x:auto;padding:4px 2px 12px;
  align-items:flex-start}
.cs-col{min-width:262px;max-width:262px;background:var(--soft);
  border:1px solid var(--border);border-radius:12px;padding:9px}
.cs-col h4{font-size:12px;font-weight:800;display:flex;align-items:center;gap:7px;
  margin:0 0 4px}
.cs-col .cham{width:9px;height:9px;border-radius:50%;flex:none}
.cs-col .dem{margin-left:auto;background:var(--card);border:1px solid var(--border);
  border-radius:99px;padding:0 8px;font-size:11px;font-weight:700}
.cs-col .goi-y{font-size:11px;color:var(--sub);margin-bottom:7px;line-height:1.45}
.cs-card{background:var(--card);border:1px solid var(--border);border-radius:10px;
  padding:9px 10px;margin-bottom:8px;box-shadow:var(--shadow)}
.cs-card .ten{font-size:13px;font-weight:700;display:flex;gap:6px;
  align-items:center;flex-wrap:wrap}
.cs-card .ten a{color:var(--text);text-decoration:none}
.cs-card .ten a:hover{color:var(--accent)}
.cs-meta{font-size:11.5px;color:var(--sub);margin-top:3px;display:flex;gap:7px;
  flex-wrap:wrap;align-items:center}
.cs-viec{margin-top:7px;font-size:12.5px;line-height:1.5;background:var(--soft);
  border-radius:8px;padding:6px 8px}
.cs-chip{font-size:10.5px;font-weight:700;border-radius:99px;padding:1px 7px;
  border:1px solid transparent;white-space:nowrap}
.cs-act{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;align-items:center}
.cs-act form{display:inline}
.cs-act button,.cs-act select{font-size:11.5px;padding:3px 8px;border-radius:7px;
  border:1px solid var(--border);background:var(--card);cursor:pointer;
  color:var(--text)}
.cs-act button:hover{border-color:var(--accent);color:var(--accent)}
.cs-rong{font-size:12px;color:var(--sub);padding:8px 2px}
.cs-tbl{width:100%;border-collapse:collapse;font-size:13px}
.cs-tbl th,.cs-tbl td{padding:8px 10px;border-bottom:1px solid var(--border);
  text-align:left;vertical-align:top}
.cs-tbl th{font-size:11.5px;color:var(--sub);text-transform:uppercase;
  letter-spacing:.04em}
</style>
"""


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _d(v) -> str:
    return v.strftime("%d/%m/%Y") if v else "—"


def _so(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".")


def _tien(n) -> str:
    try:
        return f"{float(n or 0):,.0f}đ".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


# ------------------------------------------------------------------ ô đếm
def _o_dem(dem: dict, loc: dict) -> str:
    o = [
        ("viec_hom_nay", "Việc hôm nay", "#3B62D9", False),
        ("qua_han", "Quá hạn", "#B0413E", True),
        ("vua_phan_hoi", "Khách vừa nhắn", "#E5484D", False),
        ("cho_tang_voucher", "Cần tặng voucher", "#8E5E9C", False),
        ("nhac_han", "Nhắc hạn voucher", "#B87514", False),
        ("tong", "Đang trong vòng chăm", "#6E6177", False),
    ]
    ra = ""
    for ma, nhan, mau, canh in o:
        lop = "cs-tile" + (" cs-warn" if canh and dem.get(ma) else "")
        ra += (f'<div class="{lop}">'
               f'<span class="vach" style="background:{mau}"></span>'
               f'<div class="num" style="color:{mau}">{_so(dem.get(ma))}</div>'
               f'<div class="lbl">{escape(nhan)}</div></div>')
    return f'<div class="cs-tiles">{ra}</div>'


def _bang_bao(bat: bool, ctkm: dict | None) -> str:
    """Nói thẳng quy trình đang chạy luật nào — người dùng phải biết vì sao
    thẻ xếp như đang thấy."""
    if not bat:
        return (
            '<div class="cs-banner cs-off">⚙️ <b>Quy trình CSKH 3 giai đoạn '
            'đang TẮT</b> — bảng đang xếp cột theo dải ngày cũ (30 · 60 · 150). '
            'Bật ở <a href="/quan-tri/cai-dat">Cài đặt → Quy trình CSKH</a> sau '
            'khi đã dựng thang mốc và điền mệnh giá voucher máy tặng.</div>')
    dau, cach = svc.moc_dau(), svc.moc_cach()
    nhip = " · ".join(str(n) for n in svc.nhip_voucher())
    mg = svc.menh_gia_voucher()
    canh = ("" if mg > 0 else
            ' <b style="color:#B0413E">Mệnh giá máy tặng đang là 0 ⇒ máy KHÔNG '
            "tự tặng voucher</b> (nhân viên tặng tay ở màn Voucher).")
    ct = (f' · 🎁 Đợt khuyến mãi đang chạy: <b>{escape(ctkm["name"])}</b>'
          if ctkm else
          ' · <span style="opacity:.75">chưa có đợt khuyến mãi nào đang chạy — '
          "mốc khuyến mãi tạm chăm như mốc thường</span>")
    return (
        f'<div class="cs-banner cs-on">✅ <b>Quy trình CSKH đang BẬT</b> — '
        f"mốc đầu D{dau}, cách nhau {cach} ngày, buông ở D{svc.ngay_buong()}. "
        f"Nhắc hạn voucher trước {nhip} ngày.{canh}{ct}</div>")


def _dai_loc(loc: dict, tong: int) -> str:
    chon_viec = " checked" if loc.get("viec") else ""
    chon_toi = " checked" if loc.get("toi") else ""
    return (
        '<form class="kh-filters" method="get" action="/crm/bang-viec-cskh">'
        f'<label class="kh-find">{_icon("search")}'
        f'<input name="q" value="{escape(loc.get("q") or "")}" '
        'placeholder="Tên khách · số điện thoại…"></label>'
        f'<label style="display:inline-flex;gap:6px;align-items:center;'
        f'font-size:12.5px"><input type="checkbox" name="viec" value="1"'
        f'{chon_viec} onchange="this.form.requestSubmit()"> Chỉ việc hôm nay'
        "</label>"
        f'<label style="display:inline-flex;gap:6px;align-items:center;'
        f'font-size:12.5px"><input type="checkbox" name="toi" value="1"'
        f'{chon_toi} onchange="this.form.requestSubmit()"> Khách của tôi</label>'
        '<button class="btn" type="submit">Lọc</button>'
        f'<span style="margin-left:auto;font-size:12px;color:var(--sub)">'
        f"{_so(tong)} thẻ</span></form>")


# ------------------------------------------------------------------ thẻ khách
def _chip(chu: str, mau: str, nen: str) -> str:
    return (f'<span class="cs-chip" style="color:{mau};background:{nen};'
            f'border-color:{mau}33">{escape(chu)}</span>')


def _the(kh: dict, cot_keo: list[dict], sua: bool) -> str:
    ten = escape(kh.get("full_name") or f'#{kh["id"]}')
    sdt = escape(kh.get("primary_phone") or "")
    d = kh.get("ngay")
    chips = ""
    if d is not None:
        chips += _chip(f"D+{d}", "#3B62D9", "#E7EDFB")
    if kh.get("moc"):
        chips += _chip(f'mốc D{kh["moc"]["offset_days"]}', "#2E7D32", "#E3F1E7")
    if kh.get("moc_lo"):
        chips += _chip(f'lỡ {kh["moc_lo"]} mốc', "#B0413E", "#FBE6E6")
    if (v := kh.get("voucher")):
        ma = (v.get("code") or "").strip() or "chưa báo mã"
        chips += _chip(f'🎟️ {ma} · {_tien(v.get("amount"))}', "#B87514", "#FDF1DC")
    if kh.get("goi"):
        kq = {"nghe": "đã gọi · nghe máy", "khong_nghe": "đã gọi · không nghe",
              "hen_goi_lai": "đã gọi · hẹn gọi lại"}
        chips += _chip(kq.get(kh["goi"].get("call_result") or "", "đã gọi"),
                       "#5A5A5A", "#EDEDF0")
    if int(kh.get("dang_chay") or 0) > 0:
        chips += _chip("đang có đơn chạy", "#8E5E9C", "#F1E7F5")
    if kh.get("card_rank"):
        chips += _chip(kh["card_rank"], "#6E6177", "#F1EFF3")

    ho_so = f'/crm/khach-hang/{kh["id"]}'
    thao = ""
    if sua:
        chon = "".join(f'<option value="{c["ma"]}">{escape(c["ten"])}</option>'
                       for c in cot_keo if c["ma"] != kh["cot"])
        thao = (
            '<div class="cs-act">'
            f'<form method="post" action="/crm/bang-viec-cskh/{kh["id"]}/cham">'
            '<button type="submit" title="Ghi một lượt chăm — đóng mốc đang mở">'
            "✔️ Đã chăm</button></form>"
            f'<form method="post" action="/crm/bang-viec-cskh/{kh["id"]}/goi">'
            '<select name="ket_qua"><option value="nghe">gọi · nghe máy</option>'
            '<option value="khong_nghe">gọi · không nghe</option>'
            '<option value="hen_goi_lai">gọi · hẹn gọi lại</option></select>'
            "<button type=\"submit\">📞 Ghi</button></form>"
            f'<form method="post" action="/crm/bang-viec-cskh/{kh["id"]}/cot">'
            f'<select name="cot" onchange="this.form.requestSubmit()">'
            f"<option value=\"\">↔ chuyển cột…</option>{chon}</select></form>"
        )
        if kh.get("cskh_column"):
            thao += (f'<form method="post" action="/crm/bang-viec-cskh/'
                     f'{kh["id"]}/mo-lai"><button type="submit" '
                     'title="Nhả cột đặt tay, trả thẻ về cho máy xếp">'
                     "↺ Máy xếp</button></form>")
        thao += "</div>"

    o_sdt = f"📞 {sdt}" if sdt else ""
    nguoi = kh.get("owner_name")
    o_nguoi = f"<span>· {escape(str(nguoi))}</span>" if nguoi else ""
    cau = escape(kh.get("cau_viec") or "")
    return (
        f'<div class="cs-card">'
        f'<div class="ten"><a href="{ho_so}">{ten}</a></div>'
        f'<div class="cs-meta">{o_sdt}'
        f'<span>nhận hàng {_d(kh.get("last_delivered_at"))}</span>{o_nguoi}</div>'
        f'<div class="cs-meta">{chips}</div>'
        f'<div class="cs-viec">📌 {cau}</div>'
        f"{thao}</div>")


def render_bang_viec(data: dict, user: dict, loc: dict, *, sua: bool = False,
                     flash: str = "", loi: str = "") -> str:
    """Bảng việc CSKH — kanban theo cột do `cskh_service` suy ra."""
    cot_keo = [c for c in data["cot"] if c["keo"]]
    kan = ""
    for c in data["cot"]:
        ds = data["theo_cot"].get(c["ma"]) or []
        if not ds and c["ma"] in ("da_mua_lai", "tu_choi", "ngung"):
            continue                      # cột đóng mà rỗng thì khỏi chiếm chỗ
        the = "".join(_the(k, cot_keo, sua) for k in ds) or \
            '<div class="cs-rong">— không có khách nào —</div>'
        kan += (
            f'<div class="cs-col">'
            f'<h4><span class="cham" style="background:{c["mau"]}"></span>'
            f'{escape(c["ten"])}<span class="dem">{len(ds)}</span></h4>'
            f'<div class="goi-y">{escape(c["viec"])}</div>{the}</div>')

    bao = ""
    if flash:
        bao += f'<div class="flash ok">{escape(flash)}</div>'
    if loi:
        bao += f'<div class="flash err">{escape(loi)}</div>'

    body = (_CSS + bao + _bang_bao(data["bat"], data.get("ctkm"))
            + _o_dem(data["dem"], loc)
            + _dai_loc(loc, len(data["the"]))
            + f'<div class="cs-kan">{kan}</div>')
    return render_shell(
        "Bảng việc CSKH", "crm-cskh-board", body,
        heading="Bảng việc CSKH",
        sub="Vòng đời khách sau khi nhận hàng: cảm ơn → voucher → thang mua lại. "
            "<b>Khác</b> màn Chăm sóc C01-C09 (liệu trình của một đơn).",
        actions='<a class="btn" href="/crm/cskh/khuyen-mai">🎁 Đợt khuyến mãi</a>'
                '<a class="btn" href="/crm/cham-soc">💚 Chăm sóc C01-C09</a>',
    )


# ------------------------------------------------------------------ khuyến mãi
def render_khuyen_mai(ds: list[dict], user: dict, *, sua: bool = False,
                      flash: str = "", loi: str = "") -> str:
    """Đợt khuyến mãi CSKH — nhập tay từng đợt.

    Cố ý KHÔNG lấy tự động từ Chiến dịch / Flash sale: mốc khuyến mãi gửi thẳng
    nội dung này cho khách, đoán mò là gửi sai ưu đãi.
    """
    hang = ""
    for r in ds:
        tt = ("✅ đang bật" if r["active"] else "⏸️ tắt")
        han = f'{_d(r.get("start_on"))} → {_d(r.get("end_on"))}'
        nut = ""
        if sua:
            nut = (
                f'<form method="post" action="/crm/cskh/khuyen-mai/{r["id"]}/bat" '
                'style="display:inline"><button class="btn" type="submit">'
                f'{"Tắt" if r["active"] else "Bật"}</button></form> '
                f'<form method="post" action="/crm/cskh/khuyen-mai/{r["id"]}/xoa" '
                'style="display:inline" onsubmit="return confirm(\'Xoá đợt này?\')">'
                '<button class="btn" type="submit">Xoá</button></form>')
        hang += (f"<tr><td><b>{_e(r.get('name'))}</b><br>"
                 f'<span style="color:var(--sub);font-size:12px">'
                 f"{_e(r.get('content'))}</span></td>"
                 f"<td>{han}</td><td>{tt}</td><td>{nut}</td></tr>")
    if not hang:
        hang = ('<tr><td colspan="4" style="color:var(--sub)">Chưa có đợt nào. '
                "Mốc khuyến mãi sẽ tạm chăm như mốc thường — máy KHÔNG bịa nội "
                "dung ưu đãi để gửi khách.</td></tr>")

    form = ""
    if sua:
        form = (
            '<div class="panel"><div class="panel-t">Thêm đợt khuyến mãi</div>'
            '<form method="post" action="/crm/cskh/khuyen-mai" '
            'class="kh-filters" style="flex-wrap:wrap">'
            '<input name="ten" placeholder="Tên đợt (VD: Ưu đãi tháng 8)" '
            'required style="min-width:220px">'
            '<input name="noi_dung" placeholder="Nội dung gửi khách" '
            'style="min-width:320px">'
            '<label style="font-size:12.5px">Từ <input type="date" name="tu_ngay">'
            "</label>"
            '<label style="font-size:12.5px">Đến <input type="date" name="den_ngay">'
            "</label>"
            '<label style="font-size:12.5px;display:inline-flex;gap:6px;'
            'align-items:center"><input type="checkbox" name="bat" value="1"> '
            "Bật ngay</label>"
            '<button class="btn primary" type="submit">Lưu đợt</button>'
            "</form></div>")

    bao = ""
    if flash:
        bao += f'<div class="flash ok">{escape(flash)}</div>'
    if loi:
        bao += f'<div class="flash err">{escape(loi)}</div>'

    body = (_CSS + bao + form
            + '<div class="panel"><div class="panel-t">Các đợt đã khai</div>'
            '<table class="cs-tbl"><thead><tr><th>Đợt</th><th>Thời gian</th>'
            "<th>Tình trạng</th><th></th></tr></thead>"
            f"<tbody>{hang}</tbody></table></div>")
    return render_shell(
        "Đợt khuyến mãi CSKH", "crm-cskh-board", body,
        heading="Đợt khuyến mãi CSKH",
        sub="Mốc chăm có cờ khuyến mãi (D45 · D75 · D105 …) lấy nội dung từ đợt "
            "ĐANG CHẠY hôm nay. Không có đợt nào thì mốc đó chăm như mốc thường.",
        actions='<a class="btn" href="/crm/bang-viec-cskh">← Bảng việc CSKH</a>',
    )
