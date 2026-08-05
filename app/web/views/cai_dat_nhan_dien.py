"""Hai mục Cài đặt của Đợt 2 — Kịch bản nhận diện + Gợi ý kịch bản.

Nguồn mẫu: `cai-dat.php?sec=script` và `?sec=suggest` của Kallet.

Điểm khác mẫu, cố ý:

  * Mẫu chỉ có MỘT danh sách sửa được. Bên ta chia rõ **NỀN** (hằng trong
    `services/tieng_viet.py`, luôn chạy, không xoá được) và **THÊM** (bảng
    `crm.phrase_patterns`, admin tự khai). Trộn chung thì một buổi chiều nghịch
    tay có thể xoá sạch bộ dò mà không ai biết; tách ra thì admin thấy ngay cái
    gì là móng, cái gì là của mình.
  * Ô 🧪 "Thử một câu" của mẫu gửi bằng GET rồi tải lại cả trang. Bên ta gọi
    JSON tại chỗ — thử liên tiếp mười câu là chuyện thường khi đang chỉnh mẫu.
"""

from html import escape

# (mã loại, tiêu đề, câu dẫn, gợi ý ô nhập, có ô "chữ đầy đủ" không)
KHOI: tuple[tuple[str, str, str, str, bool], ...] = (
    ("goi", "① Mẫu câu tính là ĐÃ GỌI",
     "Gọi xong nhân viên để lại tin cho khách. Máy đọc tin, thấy mẫu câu báo đã "
     "gọi thì ghi nhận công — cuộc gọi không đi qua hệ thống nên đây là bằng "
     "chứng duy nhất.",
     "vd: em vừa gọi cho chị", False),
    ("chan", "② Mẫu câu KHÔNG tính (chặn)",
     "Chạy TRƯỚC danh sách trên. «lát em gọi», «chị gọi lại cho em»… có chữ gọi "
     "nhưng là HẸN gọi, chưa gọi — tính là đã gọi thì công được chấm oan.",
     "vd: lát em gọi", False),
    ("voucher", "③ Từ báo VOUCHER",
     "Chỉ dùng cho kênh B (voucher cũ không có mã): cần ĐÚNG con số mệnh giá VÀ "
     "một từ trong danh sách này, trong cùng một tin. Kênh A dò thẳng mã đã "
     "phát nên không phải khai gì.",
     "vd: mã giảm, ưu đãi", False),
    ("viet_tat", "④ Bảng viết tắt",
     "Bung viết tắt thành chữ đầy đủ trước khi so. Chỉ đổi khi đứng RIÊNG một "
     "từ — bung trong lòng từ khác là «ca» thành «chia» và loạn hết.",
     "viết tắt (vd: k)", True),
)


def _the(p: dict, sua: bool) -> str:
    """Một thẻ mẫu của admin — bấm ✓ bật/tắt, ✕ xoá."""
    tat = p["status"] != "active"
    chu = escape(p["pattern"])
    if p.get("replacement"):
        chu += f' <span class="mo">→ {escape(p["replacement"])}</span>'
    nut = ""
    if sua:
        nut = (
            f'<button class="x" name="viec" value="doi:{p["id"]}" '
            f'title="{"Bật lại" if tat else "Tắt tạm"}">'
            f'{"○" if tat else "✓"}</button>'
            f'<button class="x xoa" name="viec" value="xoa:{p["id"]}" '
            'title="Xoá hẳn" onclick="return confirm(\'Xoá mẫu này?\')">✕'
            "</button>")
    return f'<span class="ndthe{" tat" if tat else ""}">{chu}{nut}</span>'


def _nen(ds: list[str]) -> str:
    return "".join(f'<span class="ndthe nen" title="Mẫu nền — luôn chạy, '
                   f'không xoá được">{escape(m)}</span>' for m in ds)


def _khoi(ma: str, tieu_de: str, dan: str, goi_y: str, co_the_hai: bool,
          nen: list[str], them: list[dict], sua: bool) -> str:
    o_hai = (f'<input name="thay_the" maxlength="120" placeholder="→ chữ đầy đủ" '
             "required>" if co_the_hai else "")
    form = ""
    if sua:
        form = (
            f'<div class="ndadd"><input type="hidden" name="loai" value="{ma}">'
            f'<input name="mau" maxlength="120" placeholder="{escape(goi_y)}" '
            f'required>{o_hai}'
            '<button class="btn primary" name="viec" value="them">+ Thêm</button>'
            "</div>")
    ds_them = "".join(_the(p, sua) for p in them)
    if not (nen or ds_them):
        ds_them = '<i class="note">Chưa có mẫu nào.</i>'
    return (
        f'<div class="mocg nd-{ma}"><div class="gbody">'
        f'<div class="mnhom">{escape(tieu_de)}</div>'
        f'<div class="gnote">{dan}</div>'
        f'<div class="ndthes">{_nen(nen)}{ds_them}</div>{form}'
        "</div></div>")


def render_nhan_dien(nen: dict[str, list[str]], them: dict[str, list[dict]],
                     o_gap: str, sua: bool) -> str:
    """Mục «Kịch bản nhận diện». `o_gap` là ô số `nhandien_goi_gap` đã dựng sẵn
    bằng bộ ô chung của màn Cài đặt."""
    khoi = "".join(
        _khoi(ma, td, dan, gy, hai, nen.get(ma, []), them.get(ma, []), sua)
        for ma, td, dan, gy, hai in KHOI)
    thu = (
        '<div class="mocg" id="thu-cau"><div class="gbody">'
        '<div class="mnhom">🧪 Thử một câu thật</div>'
        '<div class="gnote">Dán một câu nhân viên đã gõ, xem máy hiểu thế nào '
        "(thứ tự chốt: chặn → đã gọi → voucher). Chấm ngay trên mẫu <b>đã "
        "lưu</b>.</div>"
        '<div class="kwtry"><input id="ndCau" placeholder="vd: lát em gọi lại '
        'cho chị nhé"><input id="ndMa" placeholder="mã đã phát (không bắt buộc)"'
        ' style="flex:0 1 190px"><input id="ndGia" type="number" '
        'placeholder="mệnh giá" style="flex:0 1 130px">'
        '<button type="button" class="btn" id="ndThu">Thử</button></div>'
        '<div id="ndKq" class="ndkq"></div></div></div>')
    return (
        '<form class="card" method="post" action="/quan-tri/cai-dat/nhan-dien">'
        "<h3>📞 Kịch bản nhận diện</h3>"
        '<p class="note">Máy đọc tin nhân viên gõ để chấm công «đã gọi» và «đã '
        "báo mã». Thẻ <b>xám viền đứt</b> là mẫu <b>nền</b> — luôn chạy, không "
        "xoá được; thẻ còn lại là mẫu bạn khai thêm.</p>"
        f"{khoi}"
        '<div class="mocg"><div class="gbody">'
        '<div class="mnhom">Độ rộng khi dò</div>'
        f'<div class="cd-grid">{o_gap}</div>'
        '<div class="gnote">Lưu ô này bằng nút Lưu ở mục '
        '<a href="/quan-tri/cai-dat?sec=giam_sat">Giám sát</a> — nó là một cài '
        "đặt của bộ soi tin, để đây cho tiện nhìn khi đang chỉnh mẫu.</div>"
        "</div></div>"
        f"{thu}</form>")


# ------------------------------------------------------------ gợi ý kịch bản
def render_goi_y(luat: list[dict], kich_ban: list[dict], sua: bool) -> str:
    """Mục «Gợi ý kịch bản» — mỗi dòng: từ khoá khách nói → kịch bản gợi ý."""
    dong = ""
    for r in luat:
        tat = r["status"] != "active"
        ten = r.get("title") or "— kịch bản đã xoá / chưa chọn —"
        nut = ""
        if sua:
            nut = (f'<span class="gyn">'
                   f'<button class="x" name="viec" value="doi:{r["id"]}" '
                   f'title="{"Bật lại" if tat else "Tắt tạm"}">'
                   f'{"○" if tat else "✓"}</button>'
                   f'<button class="x xoa" name="viec" value="xoa:{r["id"]}" '
                   'onclick="return confirm(\'Xoá dòng này?\')" title="Xoá">✕'
                   "</button></span>")
        dong += (f'<div class="gyrow{" tat" if tat else ""}">'
                 f'<span class="kw">{escape(r["keywords"])}</span>'
                 f'<span class="mui">→</span>'
                 f'<span class="sc">{escape(ten)}</span>{nut}</div>')
    if not dong:
        dong = '<div class="gyrow"><i class="note">Chưa có dòng nào.</i></div>'

    chon = '<option value="0">— chọn kịch bản —</option>' + "".join(
        f'<option value="{k["id"]}">{escape((k["title"] or "")[:60])}</option>'
        for k in kich_ban)
    them = ""
    if sua:
        them = (
            '<div class="ndadd"><input name="tu_khoa" required '
            'placeholder="vd: giá, ship, còn hàng (ngăn bằng dấu phẩy)">'
            f'<select name="script_id">{chon}</select>'
            '<button class="btn primary" name="viec" value="them">+ Thêm dòng'
            "</button></div>")
    return (
        '<form class="card" method="post" action="/quan-tri/cai-dat/goi-y">'
        "<h3>💡 Gợi ý kịch bản</h3>"
        '<p class="note">Khách nhắn trúng từ khoá thì nút 💡 trên thẻ khách gợi '
        "ý sẵn kịch bản hợp cảnh. <b>Dò từ khoá, không phải AI</b> — gợi ý phải "
        'giải thích được "vì sao ra câu này". Không phân biệt hoa/thường; trúng '
        "bất kỳ từ khoá nào là gợi ý."
        f' Có {len(kich_ban)} kịch bản để chọn — soạn ở '
        '<a href="/crm/kich-ban">Thư viện kịch bản</a>.</p>'
        f'<div class="gytbl">{dong}</div>{them}</form>')
