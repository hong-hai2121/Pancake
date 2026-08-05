"""Màn LUỒNG TỰ ĐỘNG (Đợt 3) — port `luong-tu-dong.php` của mẫu Kallet.

Lớp áo cho `services/auto_flow.py`. Mọi luật nằm bên engine, file này chỉ vẽ.

Khác mẫu ở một điểm quan trọng: mẫu có nút **Test bắn** gửi thật một tin ra
ngoài (và tự nhận là "vượt mọi lớp chặn lẫn công tắc"). Bên ta KHÔNG có nút đó
— Đợt 3 chỉ dựng khung, chưa mở đường gửi. Thay vào đó là nút **Chạy thử**:
chạy khô trên dữ liệu thật, trả lời "luật này hôm nay trúng ai, vì sao", không
tin nào rời hệ thống.
"""

from html import escape

from app.services import auto_flow as af


def _bang_an_toan(ly_do: str) -> str:
    """Dải cảnh báo ĐẦU MÀN. Không giấu ở cuối trang: người mở màn này lần đầu
    phải biết ngay là nó chưa gửi được gì, trước khi hí hoáy khai luật."""
    return (
        '<div class="card afcanh"><h3>🔒 Màn này CHƯA gửi tin cho ai</h3>'
        '<p class="note">Đợt 3 mới dựng <b>khung</b>: khai luật và <b>soi</b> '
        "xem luật trúng ai. Engine cố ý <b>không có một dòng mã gửi tin nào</b> "
        "— muốn bật gửi thật phải viết thêm mã, không phải gạt một công tắc.</p>"
        f'<p class="afwhy">{escape(ly_do)}</p>'
        '<p class="note">Vì sao vẫn nên khai luật từ bây giờ: một luật sai thì '
        "sai với <b>hàng chục nghìn khách trong một đêm</b>. Chạy thử trên dữ "
        "liệu thật là cách duy nhất kiểm chứng nó trước khi nó có quyền bắn "
        "tin.</p></div>")


def _sua(f: dict) -> str:
    """Form sửa MỘT luồng, xổ ra trong `<details>` ngay dưới thẻ. Trước đây chỉ
    thêm/xoá được: gõ sai một con số là phải xoá đi khai lại từ đầu, và mất luôn
    lịch sử chạy thử của luồng đó."""
    dk = f.get("dieu_kien") or []
    gt = str((dk[0] or {}).get("gia_tri") or "") if dk else ""
    ma_dang = {d.get("ma") for d in dk}
    dk_o = "".join(
        f'<option value="{escape(k)}"'
        f'{" selected" if k in ma_dang else ""}>{escape(v["ten"])}</option>'
        for k, v in af.DIEU_KIEN.items())
    return (
        f'<details class="afsua"><summary>✏️ Sửa luồng</summary>'
        f'<input type="hidden" name="id" value="{f["id"]}">'
        '<div class="afgrid">'
        f'<label class="afl">Tên luồng<input name="s_name" '
        f'value="{escape(f["name"] or "")}"></label>'
        + _chon("s_moc_neo", [(k, v[0]) for k, v in af.MOC_NEO.items()],
                f.get("moc_neo"), "Mốc neo (kiểu lệch ngày)")
        + f'<label class="afl">Sau bao nhiêu ngày<input type="number" '
          f'name="s_so_ngay" min="0" max="3650" '
          f'value="{int(f.get("so_ngay") or 0)}"></label>'
        + "</div><div class=\"afgrid\">"
        + _chon("s_khop", [("all", "Thoả TẤT CẢ"), ("any", "Thoả BẤT KỲ")],
                f.get("khop"), "Cách ghép điều kiện")
        + '<label class="afl">Điều kiện lọc'
          f'<select name="s_dk_ma" multiple size="4">{dk_o}</select></label>'
        + f'<label class="afl">Giá trị so sánh<input name="s_dk_gia_tri" '
          f'value="{escape(gt)}"></label>'
        + '</div><div class="afgrid">'
        + f'<label class="afl afck"><input type="checkbox" name="s_tao_viec" '
          f'value="1"{" checked" if f["tao_viec"] else ""}> Sinh việc cho nhân '
          "viên</label>"
        + '<div class="afl"><button class="btn primary" name="viec" '
          f'value="sua:{f["id"]}">Lưu sửa đổi</button></div>'
        + "</div></details>")


def _lich_su(runs: list[dict], viec: list[dict]) -> str:
    """Lịch sử: các lượt CHẠY THỬ + các VIỆC luồng đã sinh. Có nó thì câu hỏi
    "việc này ở đâu ra" trả lời được bằng dữ liệu."""
    if not (runs or viec):
        return ""
    dr = "".join(
        f'<div class="afls"><span class="note">'
        f'{r["created_at"]:%d/%m %H:%M}</span> chạy thử → '
        f'<b>{r["so_trung"]}</b> khách trúng · 0 tin gửi</div>' for r in runs)
    dv = "".join(
        f'<div class="afls"><span class="note">{v["ngay"]:%d/%m}</span> '
        f'{escape(str(v["full_name"] or "—"))} → việc '
        f'<b>#{v["task_id"] or "?"}</b> '
        f'({escape(str(v["status"] or "đã xoá"))}'
        + (f' · {escape(str(v["nguoi"]))}' if v.get("nguoi") else "")
        + ")</div>" for v in viec)
    return ('<div class="afhist">'
            + (f'<div class="mnhom">Lượt chạy thử gần đây</div>{dr}' if dr else "")
            + (f'<div class="mnhom">Việc đã sinh</div>{dv}' if dv else "")
            + "</div>")


def _the_luong(f: dict, lich_su: str = "") -> str:
    tat = f["status"] != "active"
    kieu = af.kieu_flow().get(f["kind"], f["kind"])
    canh_su_kien = ""
    if f["kind"] == "lech_ngay" and f.get("moc_neo") in af.MOC_NEO:
        mo = (f'{f.get("so_ngay") or 0} ngày sau '
              f'{af.MOC_NEO[f["moc_neo"]][0].lower()}')
    elif f["kind"] == "truong_doi" and f.get("truong") in af.TRUONG_DOI:
        mo = (f'{af.TRUONG_DOI[f["truong"]][0]} → '
              f'«{f.get("truong_gia_tri") or ""}»')
    elif f["kind"] == "su_kien" and f.get("su_kien") in af.SU_KIEN:
        mo = af.SU_KIEN[f["su_kien"]][0]
        canh_su_kien = (
            '<div class="afwhy">⚠️ Kiểu SỰ KIỆN <b>chưa chạy thật</b>: hàng đợi '
            "sự kiện chưa dựng, nên máy chỉ lọc theo <b>điều kiện</b> chứ không "
            "biết sự kiện có vừa xảy ra hay không. Chạy thử vẫn xem được điều "
            "kiện trúng ai, nhưng <b>không đặt việc được</b> — dùng kiểu «sau N "
            "ngày» hoặc «trường đổi» nếu cần máy nhắc.</div>")
    else:
        mo = "— chưa khai đủ —"
    n_dk = len(f.get("dieu_kien") or [])
    viec = ('<span class="pill ok">sinh VIỆC cho nhân viên</span>'
            if f["tao_viec"] else
            '<span class="pill warn">định gửi tin (chưa mở)</span>')
    chay = (f'<span class="note">đã chạy thử {f["so_lan_chay"]} lượt</span>'
            if f.get("so_lan_chay") else
            '<span class="note">chưa chạy thử lần nào</span>')
    return (
        f'<div class="afrow{" tat" if tat else ""}">'
        f'<div class="afh"><b>{escape(f["name"] or "(chưa đặt tên)")}</b>'
        f'<span class="pill">{escape(kieu)}</span>{viec}</div>'
        f'<div class="afmo">{escape(mo)}'
        + (f' · {n_dk} điều kiện lọc' if n_dk else " · không lọc thêm")
        + f"</div><div class='afmo'>{chay}</div>"
        '<div class="afnut">'
        f'<button class="btn" name="viec" value="thu:{f["id"]}">▶ Chạy thử</button>'
        + (f'<button class="btn primary" name="viec" value="viec:{f["id"]}" '
           "onclick=\"return confirm('Đặt việc THẬT vào bảng việc của nhân "
           "viên phụ trách?\\n\\nKhông tin nào được gửi — máy chỉ nhắc "
           "người.')\">📋 Sinh việc ngay</button>"
           if f["tao_viec"] and f["kind"] != "su_kien" else "")
        + f'<button class="btn" name="viec" value="doi:{f["id"]}">'
          f'{"Bật" if tat else "Tắt"}</button>'
        + f'<button class="btn" name="viec" value="xoa:{f["id"]}" '
          "onclick=\"return confirm('Xoá luồng này?')\">Xoá</button>"
        + f"</div>{canh_su_kien}{_sua(f)}{lich_su}</div>")


def _chon(ten: str, muc, dang, phu: str = "") -> str:
    o = "".join(f'<option value="{escape(str(k))}"'
                f'{" selected" if str(dang or "") == str(k) else ""}>'
                f"{escape(v)}</option>" for k, v in muc)
    return f'<label class="afl">{escape(phu)}<select name="{ten}">{o}</select></label>'


def _form_them() -> str:
    """Form khai luồng mới. Ba kiểu chung một form, JS ẩn/hiện phần không dùng —
    ba form riêng thì cùng một danh sách điều kiện phải viết ba lần."""
    dk_o = "".join(
        f'<option value="{escape(k)}">{escape(v["ten"])}</option>'
        for k, v in af.DIEU_KIEN.items())
    return (
        '<div class="card"><h3>➕ Khai một luồng mới</h3>'
        '<div class="afgrid">'
        '<label class="afl">Tên luồng<input name="name" required '
        'placeholder="vd: Nhắc mua lại 45 ngày sau khi nhận hàng"></label>'
        + _chon("kind", af.kieu_flow().items(), "lech_ngay", "Kiểu kích hoạt")
        + "</div>"
        '<div class="afgrid" data-kieu="su_kien">'
        + _chon("su_kien", [(k, f"{v[0]} ({v[1]})")
                            for k, v in af.SU_KIEN.items()], "", "Sự kiện")
        + "</div>"
        '<div class="afgrid" data-kieu="lech_ngay">'
        + _chon("moc_neo", [(k, f"{v[0]} ({v[2]})")
                            for k, v in af.MOC_NEO.items()], "nhan_cuoi",
                "Mốc neo")
        + '<label class="afl">Sau bao nhiêu ngày'
          '<input type="number" name="so_ngay" min="0" max="3650" value="45">'
          "</label>"
        + "</div>"
        '<div class="afgrid" data-kieu="truong_doi">'
        + _chon("truong", [(k, v[0]) for k, v in af.TRUONG_DOI.items()],
                "card_rank", "Trường theo dõi")
        + '<label class="afl">Đổi sang giá trị'
          '<input name="truong_gia_tri" placeholder="vd: gold"></label>'
        + "</div>"
        '<div class="afgrid">'
        + _chon("khop", [("all", "Phải thoả TẤT CẢ điều kiện"),
                         ("any", "Thoả BẤT KỲ điều kiện nào")], "all",
                "Cách ghép điều kiện")
        + '<label class="afl">Điều kiện lọc (chọn nhiều bằng Ctrl)'
          f'<select name="dk_ma" multiple size="5">{dk_o}</select></label>'
        + "</div>"
        '<p class="note">Điều kiện chọn ở đây dùng phép <b>≥</b> với giá trị gõ '
        "bên dưới; muốn phép khác thì sửa sau khi lưu. Danh sách CHỈ khai những "
        "trường <b>có thật</b> trong dữ liệu — điều kiện lúc nào cũng không khớp "
        "là cái bẫy im lặng.</p>"
        '<div class="afgrid">'
        '<label class="afl">Giá trị so sánh (áp cho mọi điều kiện đã chọn)'
        '<input name="dk_gia_tri" placeholder="vd: 500000"></label>'
        '<label class="afl afck"><input type="checkbox" name="tao_viec" '
        'value="1" checked> Sinh <b>việc cho nhân viên</b> thay vì gửi tin'
        "</label></div>"
        '<p class="note">Ô trên nên để BẬT: người vẫn là người bấm gửi, máy chỉ '
        "nhắc. <b>Đây là đường tự động duy nhất đang mở</b> — máy đặt một việc "
        'vào <a href="/crm/cong-viec">bảng việc</a> của người phụ trách, không '
        "tin nào rời hệ thống.</p>"
        '<div style="margin-top:12px">'
        '<button class="btn primary" name="viec" value="them">Lưu luồng</button>'
        "</div></div>")


def _kq(kq: dict | None) -> str:
    if not kq:
        return ""
    vi_du = "".join(
        f'<div class="afkh"><b>{escape(str(v.get("ten") or "(không tên)"))}</b>'
        f'<span class="note">{escape(str(v.get("sdt") or "—"))}</span>'
        f'<span class="note">{escape(str(v.get("hang") or ""))}</span></div>'
        for v in kq["vi_du"])
    return (
        '<div class="card afkq"><h3>▶ Kết quả chạy thử</h3>'
        f'<div class="afso"><b>{kq["so_trung"]:,}</b>'.replace(",", ".")
        + " khách trúng luật hôm nay</div>"
        f'<p class="note">Vì sao trúng: {escape(kq["ly_do"])}.</p>'
        + (f'<p class="note">Đã loại <b>{kq["so_bo_qua"]}</b> khách xin ngừng '
           "nhận tin — luật này luôn chạy, không phụ thuộc ô tick nào.</p>"
           if kq["so_bo_qua"] else
           '<p class="note">Không có khách nào đã xin ngừng nhận tin.</p>')
        + f'<p class="afwhy">Đã gửi: <b>{kq["da_gui"]}</b> tin. '
        + escape(kq["ghi_chu_an_toan"]) + "</p>"
        + (f'<div class="afkhs">{vi_du}</div>' if vi_du else
           '<p class="note">Không khách nào trúng — thử nới điều kiện.</p>')
        + "</div>")


def _kq_viec(kq: dict | None) -> str:
    """Kết quả một lượt SINH VIỆC. Bày cả lý do BỎ QUA: "trúng 500 mà sinh 12
    việc" mà không giải thích được thì không ai dám bật công tắc."""
    if not kq:
        return ""
    b = kq["bo_qua"]
    ly = [(b["chua_co_nguoi"], "chưa có người phụ trách — không biết đặt việc "
                               "cho ai"),
          (b["viec_cu_con_mo"], "việc cũ của luồng này còn chưa làm xong"),
          (b["da_sinh_hom_nay"], "hôm nay luồng đã sinh việc cho họ rồi")]
    dong = "".join(f'<div class="afls"><b>{n}</b> khách — {escape(t)}</div>'
                   for n, t in ly if n)
    return (
        '<div class="card afkq"><h3>📋 Đã đặt việc cho nhân viên</h3>'
        f'<div class="afso"><b>{kq["da_sinh"]}</b> việc mới</div>'
        f'<p class="note">Xét {kq["xet"]} khách trúng luật. Việc nằm ở '
        '<a href="/crm/cong-viec">màn Công việc</a> của người phụ trách, hạn '
        "cuối ngày hôm nay.</p>"
        + (f'<div class="mnhom">Vì sao {kq["xet"] - kq["da_sinh"]} khách còn '
           f"lại không được đặt việc</div>{dong}" if dong else "")
        + f'<p class="afwhy">Đã gửi: <b>{kq["da_gui"]}</b> tin. '
        + escape(kq["ghi_chu_an_toan"]) + "</p></div>")


def render(flows: list[dict], kq: dict | None, ly_do_khoa: str,
           kq_viec: dict | None = None,
           lich_su: dict[int, str] | None = None) -> str:
    lich_su = lich_su or {}
    ds = "".join(_the_luong(dict(f), lich_su.get(int(f["id"]), ""))
                 for f in flows) or (
        '<p class="note">Chưa khai luồng nào. Dựng thử một cái bên dưới rồi bấm '
        "<b>Chạy thử</b> — không tin nào bị gửi đi.</p>")
    return (
        _bang_an_toan(ly_do_khoa)
        + _kq(kq) + _kq_viec(kq_viec)
        + '<form method="post" action="/quan-tri/luong-tu-dong">'
        f'<div class="card"><h3>⚡ Luồng đã khai</h3>{ds}</div>'
        + _form_them()
        + "</form>")
