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
# Dùng LẠI bộ chép SĐT của màn Khách hàng (nút `.kh-tel` + `.kh-toast`) thay vì
# viết bộ thứ hai — hai bộ thì sớm muộn cũng lệch hành vi.
from app.web.views.crm import _KH_JS
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


def _thanh_cong_cu(loc: dict, che_do: str, xong: int) -> str:
    """Tầng 1 của mẫu — đổi bộ phận · số đã xong · ô tìm · chọn chế độ.

    Mẫu gộp cả tiêu đề vào đây; bên này tiêu đề đã nằm ở topbar của `render_shell`
    nên chỗ đó bỏ, giữ nguyên phần còn lại và thứ tự trái→phải của mẫu.
    """
    bp = (
        '<div class="bv-seg2">'
        '<a class="on" href="/crm/bang-viec">🎯 Sale</a>'
        '<a href="/crm/bang-viec-cskh">💗 CSKH</a></div>'
    )
    mode = "".join(
        f'<a class="{"on" if che_do == ma else ""}" '
        f'href="{escape(_url(loc, cd=ma))}">{escape(nhan)}</a>'
        for ma, nhan in [("bang", "Bảng"), ("pipeline", "Pipeline")])
    return (
        '<div class="bv-bar1">' + bp
        + '<span class="bv-gap"></span>'
        + f'<span class="bv-done">{_icon("check")}Hôm nay đã xong: '
          f'<b>{_so(xong)}</b></span>'
        # Ô tìm là form RIÊNG (mẫu cũng vậy): gõ xong Enter là đi luôn, không
        # phải chờ dải lọc bên dưới.
        + '<form class="bv-find" method="get" action="/crm/bang-viec">'
          f'<input type="hidden" name="cd" value="{escape(che_do)}">'
          + _giu_an(loc, bo=("q", "cd"))
          + _icon("search")
          + f'<input name="q" value="{escape(loc.get("q") or "")}" '
            'placeholder="Tìm khách, SĐT…"></form>'
        + f'<div class="bv-seg2 bv-mode">{mode}</div>'
        "</div>"
    )


def _giu_an(loc: dict, bo: tuple = ()) -> str:
    """Các tham số lọc hiện tại dưới dạng input ẩn — để form này không XOÁ bộ
    lọc của form kia. Hai form GET rời nhau trên cùng một màn thì mỗi form chỉ
    gửi đúng ô của nó, thiếu chỗ này là bấm tìm xong mất sạch bộ lọc."""
    return "".join(
        f'<input type="hidden" name="{escape(k)}" value="{escape(str(v))}">'
        for k, v in loc.items() if k not in bo and v not in ("", None, 0))


def _xo(ten: str, dang_chon: str, muc: list[tuple[str, str]],
        nhan_de: str = "") -> str:
    """Một ô xổ trong dải lọc — tự gửi form khi đổi."""
    o = "".join(
        f'<option value="{escape(g)}"'
        f'{" selected" if str(g) == str(dang_chon) else ""}>{escape(n)}</option>'
        for g, n in muc)
    tip = f' title="{escape(nhan_de)}"' if nhan_de else ""
    return (f'<select class="bv-sel" name="{escape(ten)}"{tip} '
            f'onchange="this.form.requestSubmit()">{o}</select>')


def _pham_vi(loc: dict, che_do: str, hd_ngay: int) -> str:
    """Cặp nút "🔥 Còn động N ngày / Tất cả lead" — mẫu để ngay đầu dải lọc.

    Bảng mặc định chỉ bày lead còn động cho gọn; kho lead cũ vẫn xem được nhưng
    phải bấm — để không ai vô tình làm việc trên 30.000 thẻ chết.
    """
    hien = loc.get("pv") or ""
    return (
        '<div class="bv-seg2"'
        ' title="Bảng chỉ hiện lead còn động cho gọn; bấm «Tất cả lead» để xem'
        ' cả kho">'
        f'<a class="{"" if hien == "all" else "on"}" '
        f'href="{escape(_url(loc, cd=che_do, pv="hd"))}">🔥 Còn động '
        f'{hd_ngay} ngày</a>'
        f'<a class="{"on" if hien == "all" else ""}" '
        f'href="{escape(_url(loc, cd=che_do, pv="all"))}">Tất cả lead</a></div>'
    )


def _dai_loc(loc: dict, che_do: str, ca_doi: bool, quan_ly: bool,
             so_the: int, *, cot: list[dict], dem_cot: dict,
             ds_nv: list[dict], ds_page: list[dict], hd_ngay: int,
             cham_tran: bool) -> str:
    """Tầng 2 của mẫu — dải bộ lọc, 7 ô, nối thật xuống DB.

    Thứ tự trái→phải giữ đúng mẫu: phạm vi · ngày nhắn lần đầu · nhân viên ·
    fanpage · trạng thái · xoá lọc. Hai ô tích của bản cũ (xem cả đội · hiện
    khách đã chăm) giữ lại — mẫu không có nhưng chúng đang chạy và trả lời hai
    câu hỏi khác hẳn phần còn lại.

    Ô "nhân viên" chỉ in cho quản lý. Nhân viên thường thấy một ô chữ "Của tôi"
    y như mẫu — nói rõ phạm vi đang bó, chứ không để trống làm người ta tưởng
    đang xem hết.
    """
    co_loc = any(loc.get(k) for k in
                 ("q", "loc", "hien_da_cham", "nv", "page", "tt", "tu", "den",
                  "pv"))
    xoa = (f'<a class="bv-xoa" href="{escape(_url({"cd": che_do}))}">'
           f'{_icon("x")}Xoá lọc</a>' if co_loc else "")
    # Ô trạng thái: kèm số THẬT trong phạm vi lọc hiện tại. Chạm trần quét thì
    # gắn "≥" — nói "42" khi mình chỉ đếm được tới 3000 dòng là nói quá chắc.
    dau = "≥" if cham_tran else ""
    o_tt = _xo("tt", loc.get("tt") or "",
               [("", "Tất cả trạng thái")]
               + [(c["ma"], f'{c["ten"]} ({dau}{dem_cot.get(c["ma"], 0)})')
                  for c in cot],
               "Lọc theo cột trên bảng — số trong ngoặc đếm trong phạm vi lọc "
               "hiện tại")
    o_nv = (_xo("nv", loc.get("nv") or "",
                [("", "Mọi nhân viên"), ("none", "— Chưa gán —")]
                + [(str(n["id"]), f'{n["name"]} ({n["so_lead"]})')
                   for n in ds_nv])
            if quan_ly else
            f'<span class="bv-ro">{_icon("user")}Của tôi</span>')
    o_page = _xo("page", str(loc.get("page") or 0),
                 [("0", "Tất cả fanpage")]
                 + [(str(p["id"]), f'{p["name"]} ({p["so_lead"]})')
                    for p in ds_page])
    ngay = (
        '<div class="bv-ngay" title="Lọc theo ngày khách nhắn đến lần đầu '
        '(ngày tạo lead)">'
        + _icon("calendar")
        + "<span>Nhắn lần đầu:</span>"
          f'<input type="date" name="tu" value="{escape(loc.get("tu") or "")}" '
          'onchange="this.form.requestSubmit()"><span>–</span>'
          f'<input type="date" name="den" '
          f'value="{escape(loc.get("den") or "")}" '
          'onchange="this.form.requestSubmit()"></div>'
    )
    return (
        '<form class="bv-bar2" method="get" action="/crm/bang-viec">'
        f'<input type="hidden" name="cd" value="{escape(che_do)}">'
        # `pv` do CẶP NÚT bên ngoài form đặt (chúng là link, không phải input) —
        # phải mang theo dạng ẩn, không thì đổi ô xổ là mất phạm vi đang chọn.
        + _giu_an(loc, bo=("tatca", "hien_da_cham", "cd", "nv", "page", "tt",
                           "tu", "den"))
        + _pham_vi(loc, che_do, hd_ngay) + ngay + o_nv + o_page + o_tt
        + '<label class="bv-ck"'
        + ("" if quan_ly else
           ' title="Chỉ quản lý mới xem được khách của người khác"')
        + '><input type="checkbox" name="tatca" value="1"'
        + (" checked" if ca_doi else "")
        + ("" if quan_ly else " disabled")
        + ' onchange="this.form.requestSubmit()"> Xem cả đội</label>'
          '<label class="bv-ck"><input type="checkbox" name="hien_da_cham" '
          'value="1"'
        + (" checked" if loc.get("hien_da_cham") else "")
        + ' onchange="this.form.requestSubmit()"> Hiện cả khách đã chăm hôm '
          "nay</label>"
        + xoa
        + '<span class="bv-gap"></span>'
          f'<span class="bv-cnt">{_so(so_the)} thẻ'
        + (" · cả đội" if ca_doi else " · của tôi") + "</span></form>"
    )


def _tab_dem(dem: dict, loc: dict) -> str:
    """Tầng 3 của mẫu — tab đếm việc, bấm là đặt bộ lọc.

    Mẫu có ĐÚNG 3 tab (Việc hôm nay · Quá hạn · Tiềm năng). Giữ thêm tab thứ tư
    "Chưa có người phụ trách" vì nó đang chạy thật và trả lời câu hỏi hằng ngày
    của quản lý — bỏ đi chỉ để giống ảnh thì mất chức năng mà chẳng được gì.
    """
    tab = [("hom_nay", "Việc hôm nay", ""),
           ("qua_han", "Quá hạn", "err"),
           ("vua_phan_hoi", "Vừa phản hồi", ""),
           ("yeu_cau_chia", "Chưa có người phụ trách", "")]
    ra = ""
    for ma, nhan, lop in tab:
        bat = (loc.get("loc") or "") == ma
        # Bấm lại tab đang bật = bỏ lọc. Mẫu không có, nhưng thiếu nó thì không
        # có đường nào quay về "xem tất cả" ngoài việc bấm Xoá lọc.
        href = _url(loc, loc="" if bat else ma)
        ra += (f'<a class="bv-tab{" on" if bat else ""}" '
               f'href="{escape(href)}">{escape(nhan)} '
               f'<b class="{lop}">{_so(dem.get(ma))}</b></a>')
    return f'<div class="bv-tabs">{ra}</div>'


def _dai_da_an(data: dict, loc: dict) -> str:
    """Dải "đã ẩn N khách đã chăm hôm nay" — mẫu có, và nó cần thiết: bảng ngắn
    hơn mình tưởng mà không nói lý do là người dùng tưởng mất khách."""
    if loc.get("hien_da_cham"):
        return ('<div class="bv-note">'
                + _icon("check-check")
                + "<span>Đang hiện <b>cả</b> khách đã chăm hôm nay.</span>"
                f'<a href="{escape(_url(loc, hien_da_cham=0))}">Ẩn lại</a>'
                "</div>")
    if not data.get("da_an"):
        return ""
    return ('<div class="bv-note">'
            + _icon("check-check")
            + f'<span>Đã ẩn <b>{_so(data["da_an"])}</b> khách <b>đã chăm hôm '
              "nay</b> — khách nhắn lại sẽ tự hiện lại.</span>"
            f'<a href="{escape(_url(loc, hien_da_cham=1))}">Xem lại</a></div>')


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


def _tien(v) -> str:
    try:
        return f"{float(v or 0):,.0f}đ".replace(",", ".")
    except (TypeError, ValueError):
        return "0đ"


def _hang(l: dict, hang_ten: dict) -> str:
    """Chip hạng thẻ + tổng chi. Dùng chung bộ mặt với màn Ưu đãi/Hạng thẻ để
    một khách nhìn ở màn nào cũng cùng icon, cùng màu."""
    from app.services.voucher_service import mat_hang

    ma = l.get("card_rank")
    mat = mat_hang(ma)
    ten = hang_ten.get(ma) or ("Chưa xếp hạng" if not ma else str(ma))
    return (f'<span class="bv-hang" style="background:{mat["nen"]};'
            f'color:{mat["mau"]}" title="Hạng thẻ · tổng chi tiêu">'
            f'{mat["icon"]} {escape(ten)} · {_tien(l.get("total_spent"))}</span>')


def _chip_nguon(l: dict) -> str:
    ng = (l.get("source") or "").strip()
    return (f'<span class="bv-nguon" title="Nguồn khách">{escape(ng)}</span>'
            if ng else "")


def _sdt(l: dict) -> str:
    """SĐT bấm-là-chép. Dùng LẠI `.kh-tel` + `.kh-toast` + `_KH_JS` của màn Khách
    hàng, không viết bộ chép thứ hai — hai bộ thì sớm muộn cũng lệch nhau."""
    so = (l.get("primary_phone") or "").strip()
    if not so:
        return ""
    return (f'<button type="button" class="kh-tel bv-tel" data-so="{escape(so)}"'
            f' title="Bấm để chép số">{_icon("phone")}{escape(so)}</button>')


def _dau_xem(l: dict) -> str:
    """Dấu đã xem / chưa đọc — lấy từ kho hội thoại của watcher.

    Kho chưa có (watcher chưa chạy) thì hai cột này vắng mặt: KHÔNG vẽ gì cả,
    chứ không vẽ dấu "đã xem" xám rồi để người ta tin nhầm.
    """
    if "seen" not in l and "unread_count" not in l:
        return ""
    chua = int(l.get("unread_count") or 0)
    if chua:
        return (f'<span class="bv-xem chua" title="{chua} tin chưa đọc">'
                f'{_icon("mail-warning")}</span>')
    if l.get("seen"):
        return f'<span class="bv-xem da" title="Đã xem">{_icon("check")}</span>'
    return (f'<span class="bv-xem chua-xem" title="Chưa xem">'
            f'{_icon("mail")}</span>')


def _cua_24h(l: dict) -> str:
    """Chip cửa gửi tin của Meta — BA trạng thái, y như màn Hội thoại.

    Thiếu mốc tin cuối của khách thì trả "chưa rõ" (xám), KHÔNG kết luận hết
    cửa: nói thế là khẳng định một điều mình không biết.
    """
    from app.core.ngay import bay_gio

    moc = l.get("khach_cuoi")
    if not moc:
        return ('<span class="bv-cua unk" title="Kho chưa có mốc tin cuối của '
                'khách — chưa tính được cửa"><i></i>Chưa rõ cửa</span>')
    con = 24 - (bay_gio() - moc).total_seconds() / 3600
    if con <= 0:
        return ('<span class="bv-cua tpl" title="Ngoài cửa 24 giờ — chỉ gửi '
                'được mẫu Meta đã duyệt"><i></i>Cửa mẫu Meta</span>')
    return (f'<span class="bv-cua open" title="Còn {max(1, int(con))} giờ nhắn '
            f'tự do"><i></i>Cửa tự do · còn {max(1, int(con))} giờ</span>')


def _tien_do(l: dict, tong_buoc: int) -> str:
    """Thanh tiến trình theo thang bước.

    🔴 BẪY của mẫu (mục B4): thanh ĐẦY DẦN VỀ PHÍA XẤU — khách đi hết thang bám
    đuổi là sắp buông, trong khi mắt đọc "thanh đầy = tốt". Nên BẮT BUỘC đổi màu
    xanh→vàng→đỏ VÀ luôn kèm chữ mốc. Bỏ chữ đi là hiểu ngược.
    """
    if tong_buoc <= 0:
        return ""
    cur = min(int(l.get("sale_step") or 0), tong_buoc)
    ti = cur / tong_buoc
    mau = "#2EAD6E" if ti <= 0.4 else ("#E0A417" if ti <= 0.75 else "#E5484D")
    if l.get("cot") == "da_chot":
        ti, mau = 1.0, "#2E7D32"
    ke = l.get("buoc_ke")
    if l.get("cho_dap"):
        chu = f"Đã gửi {cur}/{tong_buoc} bước · khách đang chờ mình đáp"
    elif ke and not ke["san_sang"]:
        chu = (f'Đã gửi {cur}/{tong_buoc} bước · bước {ke["step_no"]} chờ '
               f'({l.get("ly_do_cho") or "chưa tới nhịp"})')
    elif ke:
        chu = f'Đã gửi {cur}/{tong_buoc} bước · tới lượt bước {ke["step_no"]}'
    elif cur >= tong_buoc:
        chu = f"Đã đi hết {tong_buoc} bước — hết bám đuổi"
    else:
        chu = f"Đã gửi {cur}/{tong_buoc} bước"
    return (f'<div class="bv-tien" title="{escape(chu)}">'
            f'<div class="bv-tien-r"><div class="bv-tien-f" '
            f'style="width:{round(ti * 100)}%;background:{mau}"></div></div>'
            f'<div class="bv-tien-c">{escape(chu)}</div></div>')


def _todo(vi_sao: str) -> str:
    """Đánh dấu "chưa làm được" — viền đứt + mờ + con trỏ cấm, lý do ở tooltip.
    `.ht-todo` là lớp DÙNG CHUNG cho mọi màn (xem shell.py), không phải của
    riêng màn Hội thoại: gỡ đánh dấu sau này chỉ là xoá một class."""
    return f'title="CHƯA LÀM ĐƯỢC — {escape(vi_sao)}"'


def _hang_nut(l: dict, cot_ds: list[dict]) -> str:
    """Hàng nút trên thẻ + menu ⋯, port từ `render_actions()` của mẫu.

    Thứ tự giữ đúng mẫu: chat · Pancake · thư viện kịch bản · Botcake · tự khai
    · ⋯. Nút nào chưa nối được thì để viền đứt kèm lý do, KHÔNG giấu đi — giấu
    thì người quen mẫu tưởng mình làm thiếu, mà bày nút chết thì tệ hơn nữa.
    """
    cid, lid = l["customer_id"], l["id"]
    pc = ""
    if l.get("external_page_id") and l.get("external_conversation_id"):
        from app.integrations.pancake.links import link_hoi_thoai

        u = link_hoi_thoai(l["external_page_id"], l["external_conversation_id"])
        pc = (f'<a class="bv-nut-ic" href="{escape(u)}" target="_blank" '
              f'rel="noopener" title="Mở hội thoại bên Pancake">'
              f'{_icon("external-link")}</a>')
    else:
        pc = (f'<span class="bv-nut-ic ht-todo" '
              f'{_todo("hội thoại này chưa có link Pancake")}>'
              f'{_icon("external-link")}</span>')

    # Cột kéo tay: giữ <select> ở đây, kéo-thả thật là việc của bước 5.
    keo = "".join(
        f'<option value="{c["ma"]}"{" selected" if c["ma"] == l["cot"] else ""}>'
        f'{escape(c["ten"])}</option>' for c in cot_ds if c["keo"])

    hen = (l.get("next_action_at").strftime("%Y-%m-%dT%H:%M")
           if l.get("next_action_at") else "")
    return (
        '<div class="bv-nutr">'
        f'<a class="bv-nut-ic go" href="/crm/khach-hang/{cid}?tab=hoi-thoai" '
        f'title="Mở hội thoại trong CRM">{_icon("message-circle")}</a>'
        + pc
        + f'<a class="bv-nut-ic" href="/crm/kich-ban" '
          f'title="Thư viện kịch bản — chép tay, KHÔNG gửi gì">'
          f'{_icon("book-open")}</a>'
        # Botcake = MÁY BẮN TIN, khác hẳn thư viện kịch bản ở trên. Mẫu dặn
        # riêng: đừng gộp hai thứ này.
        + f'<span class="bv-nut-ic ht-todo" '
          f'{_todo("gửi kịch bản Botcake chưa nối — thao tác ở màn Hội thoại")}>'
          f'{_icon("send")}</span>'
        + f'<form method="post" action="/crm/bang-viec/{lid}/tu-khai" '
          'class="vc-inline"><input type="hidden" name="viec" value="nhan">'
          '<button class="bv-nut-ic ok" type="submit" '
          'title="Tự khai ĐÃ NHẮN khách này — ghi công, chờ máy soi tin">'
          f'{_icon("check")}</button></form>'
        + f'<form method="post" action="/crm/bang-viec/{lid}/tu-khai" '
          'class="vc-inline"><input type="hidden" name="viec" value="goi">'
          '<button class="bv-nut-ic" type="submit" '
          f'title="Tự khai ĐÃ GỌI khách này">{_icon("phone-call")}</button>'
          "</form>"
        + '<span class="bv-gap"></span>'
        # ⋯ — mọi thứ không dùng hằng ngày gom vào đây cho hàng nút khỏi vỡ
        + '<details class="bv-menu"><summary class="bv-nut-ic" '
          f'title="Thao tác khác">{_icon("dots-h")}</summary>'
          '<div class="bv-menu-p">'
          f'<form method="post" action="/crm/bang-viec/{lid}/hen">'
          '<label>📌 Hẹn mua</label>'
          f'<input type="datetime-local" name="khi" value="{escape(hen)}">'
          '<button class="kh-btn" type="submit">Lưu hẹn</button></form>'
        # Xoá hẹn phải là FORM RIÊNG: nút submit mang `name="khi"` nằm chung
        # form sẽ gửi KÈM giá trị của ô nhập (`khi=<ngày>&khi=`), server đọc cái
        # đầu nên bấm Xoá lại hoá ra Lưu.
        + (f'<form method="post" action="/crm/bang-viec/{lid}/hen">'
           '<input type="hidden" name="khi" value="">'
           '<button class="kh-btn" type="submit" title="Bỏ hẹn, thẻ rời cột '
           'Hẹn mua">🗑 Xoá hẹn</button></form>' if hen else "")
        # Đổi ô xổ là gửi luôn, đúng như mẫu (`onchange="this.form.submit()"`).
        # Mẫu KHÔNG có kéo thả — ô xổ này chính là đường chuyển cột của nó.
        + f'<form method="post" action="/crm/bang-viec/{lid}/keo">'
          '<label>↔ Chuyển cột</label>'
          f'<select name="cot" onchange="this.form.requestSubmit()">{keo}'
          "</select>"
          '<button class="kh-btn" type="submit">Chuyển</button></form>'
          f'<form method="post" action="/crm/bang-viec/{lid}/mo-lai">'
          '<button class="kh-btn" type="submit" title="Nhả cột đặt tay, để máy '
          'tự xếp lại theo tin nhắn">🤖 Trả thẻ về cho máy xếp</button></form>'
          '<div class="bv-menu-sep"></div>'
          f"{_nut_dong(l)}"
          "</div></details>"
        "</div>"
    )


def _the(l: dict, cot_ds: list[dict], hang_ten: dict | None = None,
         tong_buoc: int = 0) -> str:
    """Một thẻ khách trên pipeline."""
    hang_ten = hang_ten or {}
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

    # Hẹn TRƯỢT ngày: tài liệu mẫu (mục C1) bắt "ở lại cột Hẹn mua, VIỀN ĐỎ".
    # Viền suông là chưa đủ — luật vàng B3.5 của chính tài liệu: màu không bao
    # giờ đứng một mình, luôn kèm chữ/icon. Nên viền + dòng cảnh báo đi đôi.
    lop = " nong" if ke and ke.get("nong") else ""
    if l.get("hen_tre"):
        lop += " tre"
    return (
        f'<div class="bv-the{lop}">'
        # Hàng 1: ô tích · dấu đã xem · tên · nóng · giờ khách nhắn cuối
        f'<div class="bv-h">{_tick(l)}{_dau_xem(l)}<a class="kh-name" '
        f'href="/crm/khach-hang/{l["customer_id"]}">{_e(l["full_name"])}</a>'
        + (f'<span class="bv-nong">🔥 nóng</span>' if ke and ke.get("nong")
           else "")
        + f'<span class="kh-sp"></span>'
          f'<span class="kh-nho">{_truoc(l.get("khach_cuoi"))}</span></div>'
        # Hàng 2: hạng thẻ + tổng chi · nguồn · SĐT bấm-chép
        + f'<div class="bv-meta">{_hang(l, hang_ten)}{_chip_nguon(l)}'
        + _sdt(l) + "</div>"
        + f'<div class="kh-sub">{_e(l.get("owner_name"))}'
        + (f' · {escape(l["page_name"])}' if l.get("page_name") else "")
        + "</div>"
        + ('<div class="bv-qh">⚠️ Hẹn đã trượt ngày — chốt lại hẹn với '
           "khách</div>" if l.get("hen_tre") else "")
        + (f'<div class="bv-qh">⚠️ {escape(l["qua_han"])}</div>'
           if l.get("qua_han") else "")
        + viec
        + _tien_do(l, tong_buoc)
        + f'<div class="bv-cua-r">{_cua_24h(l)}</div>'
        + _hang_nut(l, cot_ds)
        + "</div>"
    )


def _pipeline(data: dict, hang_ten: dict, tong_buoc: int) -> str:
    cot = ""
    for c in data["cot"]:
        ds = data["theo_cot"].get(c["ma"], [])
        the = "".join(_the(l, data["cot"], hang_ten, tong_buoc)
                      for l in ds) or ('<div class="bv-rong">—</div>')
        cot += (f'<div class="bv-cot"><div class="bv-cot-h" '
                f'style="border-color:{c["mau"]}">'
                f'<b>{escape(c["ten"])}</b>'
                f'<span class="bv-dem">{len(ds)}</span></div>'
                f'<div class="bv-cot-h2">📌 {escape(c["viec"])}</div>'
                + ("" if c["keo"] else
                   '<div class="bv-khoa">🔒 máy suy ra — không kéo tay</div>')
                + f"{the}</div>")
    return f'<div class="bv-board">{cot}</div>'


def _bang(data: dict, hang_ten: dict, tong_buoc: int) -> str:
    than = ""
    for l in data["the"]:
        ke = l.get("buoc_ke")
        viec = ("💬 Đáp khách" if l["cho_dap"] else
                (f'Bước {ke["step_no"]} · {ke["work"] or ke["name"]}'
                 + ("" if ke["san_sang"] else f' ({l["ly_do_cho"]})')
                 if ke else "✅ hết thang"))
        cot = next((c for c in data["cot"] if c["ma"] == l["cot"]), None)
        than += (
            # Hàng cũng nhuộm như thẻ pipeline — đổi chế độ mà mất cảnh báo thì
            # hai chế độ không còn "chỉ khác cách bày" nữa.
            f'<tr class="{"tre" if l.get("hen_tre") else ""}">'
            f'<td class="bv-tdc">{_tick(l)}</td>'
            f'<td>{_dau_xem(l)}<a class="kh-name" '
            f'href="/crm/khach-hang/{l["customer_id"]}">{_e(l["full_name"])}</a>'
            f'<div class="bv-meta">{_sdt(l)}{_chip_nguon(l)}</div></td>'
            f'<td>{_hang(l, hang_ten)}</td>'
            f'<td><span class="kh-st chua" style="background:'
            f'{cot["mau"] if cot else "var(--soft)"}22;color:'
            f'{cot["mau"] if cot else "var(--sub)"}">'
            f'{escape(cot["ten"] if cot else l["cot"])}</span>'
            f'<div class="kh-nho">{escape(l["cot_vi_sao"])}</div></td>'
            # Cột "Bước" trần không nói được gì — thay bằng thanh tiến trình,
            # cùng luật màu + luôn kèm chữ như trên thẻ pipeline.
            f'<td class="bv-tdo">{_tien_do(l, tong_buoc)}</td>'
            f"<td>{escape(viec)}</td>"
            f'<td>{_e(l.get("owner_name"))}</td>'
            f'<td>{_cua_24h(l)}'
            f'<div class="kh-nho">{_truoc(l.get("khach_cuoi"))}</div></td>'
            # Cùng MỘT hàng nút với thẻ pipeline — hai chế độ chỉ khác cách bày,
            # không được khác việc làm được.
            f'<td>{_hang_nut(l, data["cot"])}</td>'
            "</tr>")
    than = than or ('<tr><td colspan="9" class="rong">Không có việc nào — '
                    "hoặc đã chăm hết khách hôm nay 🎉</td></tr>")
    return ('<div class="kh-card"><div class="kh-tblwrap">'
            '<table class="kh-tbl"><thead><tr>'
            '<th class="bv-tdc"><input type="checkbox" id="bv-tick-all" '
            'aria-label="Chọn tất cả thẻ đang hiện"></th>'
            "<th>Khách</th><th>Hạng thẻ</th><th>Cột</th><th>Tiến trình</th>"
            "<th>Việc cần làm</th><th>Phụ trách</th><th>Cửa gửi tin</th>"
            "<th>Thao tác</th></tr></thead>"
            f"<tbody>{than}</tbody></table></div></div>")


def _rong(data: dict, loc: dict, ca_doi: bool, quan_ly: bool,
          che_do: str = "bang") -> str:
    """Bảng trống thì phải nói RÕ vì sao trống + cách xem tiếp.

    Màn trống không giải thích là nguồn gốc câu "sao không có dữ liệu" — người
    dùng không có cách nào biết là do bộ lọc hay do hệ thống hỏng."""
    if data["the"]:
        return ""
    if loc.get("loc"):
        return ('<div class="flash warn">Không có thẻ nào trong tab vừa bấm. '
                f'<a href="{escape(_url(loc, loc=""))}">Bỏ lọc</a> để xem lại '
                "toàn bộ.</div>")
    # Bộ lọc đang bật thì PHẢI đổ tại bộ lọc. Nói "chưa có lead nào trong hệ
    # thống" trong khi người ta vừa chọn một fanpage là chỉ sai chỗ, và họ sẽ đi
    # tìm lỗi ở kho dữ liệu chứ không nghĩ tới cái ô mình vừa bấm.
    dang_loc = [ten for khoa, ten in (
        ("nv", "nhân viên"), ("page", "fanpage"), ("tt", "trạng thái"),
        ("tu", "ngày nhắn lần đầu"), ("den", "ngày nhắn lần đầu"),
        ("q", "từ khoá tìm")) if loc.get(khoa)]
    if dang_loc:
        # dict.fromkeys thay set(): giữ đúng thứ tự đọc được, khỏi mỗi lần tải
        # lại đổi chỗ. ("pv=all" không kể — đó là nới ra, không phải bó lại.)
        ten = " · ".join(dict.fromkeys(dang_loc))
        return ('<div class="flash warn">Không có thẻ nào khớp bộ lọc đang bật '
                f"(<b>{escape(ten)}</b>). "
                f'<a href="{escape(_url({"cd": che_do}))}">'
                "Xoá lọc</a> để xem lại toàn bộ.</div>")
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


def _tick(l: dict) -> str:
    """Ô tích chọn thẻ. Tên `ids` khớp `f.getlist("ids")` bên route."""
    return (f'<input class="bv-tick" type="checkbox" name="ids" '
            f'value="{l["id"]}" form="bv-hl" aria-label="Chọn thẻ này">')


def _thanh_hang_loat(ds_nv: list[dict]) -> str:
    """Thanh thao tác hàng loạt — ẩn tới khi tích ít nhất một thẻ.

    KHÔNG có "tặng voucher" và "✅ tự khai": tài liệu mẫu (C1) cấm hai việc này
    làm hàng loạt. Phát tiền nhầm cả lô, và khai công 200 khách một nhịp thì con
    số công hết nghĩa mà bộ soi tin không bác lại kịp. Đừng thêm vào.
    """
    nv = "".join(
        f'<label class="bv-hl-nv"><input type="checkbox" name="bb_nv" '
        f'value="{n["id"]}"> {escape(n["name"])}</label>' for n in ds_nv)
    chia = (f'<details class="bv-hl-g"><summary class="kh-btn">👤 Giao / chia '
            f'nhân viên</summary><div class="bv-hl-p">'
            f'<div class="note">Tích 1 người = giao hết · nhiều người = '
            f"chia đều.</div>{nv}"
            '<button class="kh-btn" type="submit" name="act" value="giao">'
            "Giao thẻ đã chọn</button></div></details>"
            if nv else
            f'<span class="kh-btn ht-todo" {_todo("chưa có nhân viên nào đang ôm lead")}>'
            "👤 Giao / chia nhân viên</span>")
    return (
        '<form class="bv-hl" id="bv-hl" method="post" '
        'action="/crm/bang-viec/hang-loat">'
        '<span class="bv-hl-n"><b id="bv-hl-so">0</b> thẻ đã chọn</span>'
        + chia
        + '<button class="kh-btn" type="submit" name="act" value="xuat">'
          "⬇ Xuất CSV</button>"
        + f'<span class="kh-btn ht-todo" '
          f'{_todo("chiến dịch dựng theo BỘ LỌC, chưa có đường nhận danh sách chọn tay")}>'
          "🚩 Đưa vào chiến dịch</span>"
        + f'<span class="kh-btn ht-todo" '
          f'{_todo("gửi kịch bản Botcake chưa nối")}>🅑 Gửi Botcake</span>'
        + '<span class="bv-gap"></span>'
          '<button type="button" class="kh-btn" id="bv-hl-bo">Bỏ chọn</button>'
          "</form>"
    )


# Bật/tắt thanh hàng loạt theo số ô đã tích. Chạy lại được nhiều lần: shell nạp
# lại script sau mỗi lượt điều hướng.
_HL_JS = """
(function(){
  var bar = document.querySelector('.bv-hl');
  if (!bar) return;
  var so = document.getElementById('bv-hl-so');
  var tat = document.getElementById('bv-tick-all');
  function o(){ return Array.prototype.slice.call(
      document.querySelectorAll('.bv-tick')); }
  function dem(){
    var n = o().filter(function(x){ return x.checked; }).length;
    so.textContent = n;
    bar.classList.toggle('on', n > 0);
    if (tat) tat.checked = n > 0 && n === o().length;
  }
  o().forEach(function(x){ x.addEventListener('change', dem); });
  if (tat) tat.addEventListener('change', function(){
    o().forEach(function(x){ x.checked = tat.checked; }); dem();
  });
  var bo = document.getElementById('bv-hl-bo');
  if (bo) bo.addEventListener('click', function(){
    o().forEach(function(x){ x.checked = false; }); dem();
  });
  dem();
})();
"""


def _dai_cat(data: dict) -> str:
    """Mẫu có dải này và nó cần thiết: số ở tab đếm cả phạm vi lọc, còn danh
    sách dưới chỉ bày tối đa `HIEN_TOI_DA` thẻ gấp nhất. Không nói ra thì hai
    con số đá nhau và người dùng tưởng mất thẻ."""
    tong, hien = data.get("tong") or 0, len(data["the"])
    if tong <= hien:
        return ""
    return ('<div class="bv-note"><span>Đang bày <b>' + _so(hien)
            + "</b> thẻ gấp nhất trong <b>" + _so(tong)
            + "</b> thẻ khớp bộ lọc. Lọc theo cột hoặc nhân viên để xem hết."
              "</span></div>")


def render_bang_viec(data: dict, *, loc: dict, che_do: str = "bang",
                     ca_doi: bool = False, quan_ly: bool = False,
                     flash: str = "", loi: str = "",
                     ds_nv: list[dict] | None = None,
                     ds_page: list[dict] | None = None,
                     hd_ngay: int = 14,
                     hang_ten: dict | None = None) -> str:
    hang_ten = hang_ten or {}
    tong_buoc = len(svc.thang())
    khung = ""
    if not svc.bat():
        khung = ('<div class="flash warn">Thang bám đuổi <b>chưa có bước nào</b>'
                 " — bảng đang xếp mọi khách vào Mới/Tiềm năng. Chạy "
                 "<code>python scripts/seed_thang_sale.py</code> để nạp thang "
                 "8 bước mẫu.</div>")
    # Bố cục 3 tầng của mẫu: thanh công cụ · dải lọc · tab đếm — rồi mới tới
    # khu nội dung. Cả ba tầng DÍNH nhau trên nền thẻ, khu nội dung nền chìm.
    dau = (
        '<div class="bv-head">'
        + _thanh_cong_cu(loc, che_do, data.get("xong_hom_nay") or 0)
        + _dai_loc(loc, che_do, ca_doi, quan_ly,
                   data.get("tong") or len(data["the"]),
                   cot=data["cot"], dem_cot=data.get("dem_cot") or {},
                   ds_nv=ds_nv or [], ds_page=ds_page or [],
                   hd_ngay=hd_ngay, cham_tran=bool(data.get("cham_tran")))
        + _tab_dem(data["dem"], loc)
        + "</div>"
    )
    # `.content.full` là flex HÀNG và chỉ chờ ĐÚNG MỘT con (xem shell.py) — hai
    # tầng đầu/thân để trần sẽ đứng cạnh nhau. Bọc lại thành cột.
    body = (
        '<div class="bv-wrap">'
        + dau
        + '<div class="bv-than">'
        + (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + (f'<div class="flash err">{escape(loi)}</div>' if loi else "")
        + khung
        + _dai_da_an(data, loc)
        + _dai_cat(data)
        + '<div class="bv-note"><span>🤖 Cột trên bảng do <b>máy đọc tin nhắn '
          "thật</b> suy ra (thang tính từ "
          f'<b>{svc.ngay_bat_thang():%d/%m/%Y}</b>), khác với '
          '<a href="/crm/pipeline">Pipeline giai đoạn</a> do người tự kéo. '
          "Giai đoạn = <i>khách ở đâu trong quy trình</i>, bước = <i>câu tiếp "
          "theo cần nói</i>.</span></div>"
        + _rong(data, loc, ca_doi, quan_ly, che_do)
        # Thanh hàng loạt CHỈ cho quản lý — giao lead của người khác là việc của
        # họ. Nhân viên thường thấy thanh này chỉ tổ bấm rồi ăn 403.
        + (_thanh_hang_loat(ds_nv or []) if quan_ly else "")
        + (_pipeline(data, hang_ten, tong_buoc) if che_do == "pipeline"
           else _bang(data, hang_ten, tong_buoc))
        + '<p class="note" style="margin-top:10px">🚫 <b>Từ chối</b> = đóng đợt '
          "này, khách nhắn lại là thẻ <b>tự quay về</b> bảng (không hỏi xác "
          "nhận vì bấm nhiều lần trong ngày). ⛔ <b>Ngừng chăm sóc</b> = dừng "
          "hẳn, có hỏi + bắt buộc lý do, thẻ <b>không tự quay lại</b>.</p>"
        # Toast của nút chép SĐT — `_KH_JS` tìm đúng phần tử này.
        + '<div class="kh-toast"></div>'
        + "</div></div>"
    )
    return render_shell(
        "Bảng việc Sale", "crm-board", body,
        heading="Bảng việc Sale",
        sub="Thang bám đuổi · máy đọc tin nhắn thật để biết cần nói gì tiếp",
        script=_KH_JS + (_HL_JS if quan_ly else ""),
        full=True,
    )
