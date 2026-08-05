"""Mục **Mốc thời gian** của màn Cài đặt (Đợt 1 — port mẫu Kallet `?sec=time`).

Bốn khối, gộp về MỘT chỗ những thứ trước đây nằm rải rác:

  **1A · Thang bám đuổi Sale** — tên bước · câu việc 📌 · từ khoá (thẻ bấm gỡ)
        · bật/tắt từng bước · **11 con số nhịp đẩy bước** (gộp từ nhóm `sale`
        của màn Cài đặt — T2) · ô 🧪 **Thử một câu**.
  **1D · Thang mua lại** — mốc chăm: bật/tắt · số ngày · nhãn 📌 · 🤖/👤.
  **1G · Câu việc cột — Bảng Sale** (7 cột ngoài thang bước).
  **1H · Câu việc cột — Bảng CSKH** (11 cột).

## Ba điều giao diện phải làm đúng, nếu không cấu hình sai mà không ai biết

1. **Thẻ trùng phải TỰ LỘ ra.** Máy bỏ dấu cả hai phía trước khi so, nên
   `"số đo"` và `"so do"` là MỘT. Bộ seed của mẫu để cả cặp; nhìn danh sách dài
   người ta tưởng đang phủ rộng hơn thực tế. Thẻ thừa hiện MỜ + có nút gỡ hàng
   loạt.
2. **Từ khoá quá ngắn phải bị chặn ngay lúc lưu**, kèm ví dụ. `"đắt"` bỏ dấu
   thành `"dat"`, đụng luôn `"đặt hàng"` — mẫu đo trên 53.000 tin thật.
3. **Ô Thử một câu chấm trên từ khoá ĐANG GÕ**, chưa lưu cũng thử được, và gọi
   thẳng hàm bộ dò thật dùng — kết quả ô thử không bao giờ lệch với lúc chạy.
"""

from html import escape

from app.services import sale_service as sv

# 1G — 7 cột Bảng Sale NGOÀI thang bước (8 cột "Bước N" sửa ở 1A, khỏi hai nơi)
COT_SALE = [(m, t, c) for m, t, c, _ in sv.COT_DAU + sv.COT_CUOI]

# 1H — cột Bảng CSKH. Mốc nào có nhãn riêng (1D) thì nhãn đó THẮNG câu cột.
#
# 🔑 Lấy THẲNG từ `cskh_service.cac_cot()` chứ không chép tay: danh sách cột đổi
#    theo công tắc quy trình (tên cột "Chăm hàng tháng" ↔ "Chăm định kỳ"), chép
#    ra đây là hai nguồn đá nhau — màn Cài đặt bày chữ mờ một đằng, bảng việc
#    hiện một nẻo. `goc=True` để chữ mờ trong ô đúng là TÊN GỐC trong mã, tức
#    thứ sẽ hiện lại nếu người dùng xoá trắng ô.
#
# Không gọi ở mức module: `cac_cot()` đọc cấu hình dưới DB, mà module này được
# nạp lúc khởi động — hỏi DB ở đó là app chết trước khi kịp báo lỗi tử tế.
def cot_cskh() -> list[tuple[str, str, str]]:
    from app.services import cskh_service

    return [(c["ma"], c["ten"], c["mau"]) for c in cskh_service.cac_cot(goc=True)]

# Cột CSKH do MỐC sinh ra — nhãn mốc (1D) đè lên câu cột. Cột "việc gấp"
# (Nóng · Quá hạn · Nhắc gọi…) KHÔNG theo mốc: thay bằng "Tới kỳ mua lại" là
# sai việc.
COT_THEO_MOC = {"cham_dinh_ky", "den_ky_mua_lai", "sap_roi_bo"}

# 11 con số nhịp đẩy bước — gộp về 1A (T2), chia hai cụm cho dễ đọc.
SO_1A: list[tuple[str, list[str]]] = [
    ("Nhịp đẩy bước", ["sale_step_rest_hours", "sale_step_max_per_day",
                       "sale_step_hour_from", "sale_step_hour_to"]),
    ("Giai đoạn nóng · trần nhảy · ngày bật thang",
     ["sale_hot_hours", "sale_hot_max_steps", "sale_step_window",
      "sale_step_skip_max", "sale_stuck_days", "sale_ladder_start",
      "sale_scan_enabled"]),
]


def _khoi(ma: str, tieu_de: str, phu: str, dem: str, ruot: str,
          mo: bool = False) -> str:
    return (f'<details class="mocg" id="{ma}"{" open" if mo else ""}>'
            f'<summary><span class="chev">▾</span>'
            f'<span class="gttl">{escape(tieu_de)}'
            f'<span class="gsub"> · {escape(phu)}</span></span>'
            f'<span class="gcnt">{escape(dem)}</span></summary>'
            f'<div class="gbody">{ruot}</div></details>')


def _the_tu_khoa(ten_o: str, chuoi: str, nhan: str, goi_y: str,
                 xanh: bool = False) -> str:
    """Một hàng từ khoá kiểu THẺ. Ô ẩn giữ nguyên chuỗi "a, b, c" như cũ nên
    phần lưu ở server không phải đổi gì."""
    cum = sv.cum_the(chuoi)
    thua = sum(1 for c in cum if c["trung_voi"])
    the = ""
    for c in cum:
        lop = "kwtag" + (" sp" if c["dac_biet"] else "") + (
            " dup" if c["trung_voi"] else "")
        title = (f'Cụm đặc biệt — máy tự hiểu: {c["dac_biet"]}' if c["dac_biet"]
                 else (f'Thừa: máy bỏ dấu rồi nên cụm này y hệt “{c["trung_voi"]}”'
                       if c["trung_voi"] else
                       "Máy thấy cụm này trong tin là tính đã đi bước"))
        chu = (f'{c["cum"]} · {c["dac_biet"]}' if c["dac_biet"] else c["cum"])
        the += (f'<span class="{lop}" title="{escape(title)}">'
                f'<b>{escape(chu)}</b>'
                f'<button type="button" class="kwx" data-i="{c["i"]}" '
                'title="Gỡ cụm này">×</button></span>')
    ben = f'{len(cum)} cụm'
    if thua:
        ben += ('<button type="button" class="kwdup" title="Gỡ các cụm chỉ '
                f'khác nhau ở dấu — máy coi chúng là một">gỡ {thua} thẻ thừa'
                "</button>")
    return (
        f'<div class="kwrow{" kh" if xanh else ""}">'
        f'<span class="kwlb">{escape(nhan)}</span>'
        '<div class="kwbox" data-kw>'
        f'<input type="hidden" name="{escape(ten_o)}" value="{escape(chuoi)}">'
        f'{the}<input type="text" class="kwadd" placeholder="{escape(goi_y)}">'
        "</div>"
        f'<div class="kwside">{ben}</div></div>'
    )


def _1a(buoc: list[dict], o_so: str) -> str:
    """1A — mỗi bước một khối: bật/tắt · tên · việc 📌 · 2 hàng từ khoá."""
    ruot = ""
    for b in buoc:
        so = int(b["step_no"])
        bat = b["status"] == "active"
        ruot += (
            f'<div class="mitem{"" if bat else " off"}">'
            '<div class="mrow">'
            f'<input type="checkbox" class="msw" id="bw{so}" '
            f'name="b[{so}][active]" value="1"{" checked" if bat else ""}>'
            f'<label class="swui" for="bw{so}" title="'
            + ("Đang bật — gạt để bỏ bước này khỏi thang"
               if bat else "Đang tắt — gạt để bật lại") + '"><span></span></label>'
            f'<span class="mname">Bước {so}<small>thứ {so}/{len(buoc)}</small></span>'
            f'<input class="nhanin" style="flex:0 0 190px" name="b[{so}][ten]" '
            f'value="{escape(b["name"] or "")}" maxlength="60" '
            'placeholder="Tên bước" title="Tên bước — cũng là TÊN CỘT trên bảng việc">'
            f'<input class="nhanin" name="b[{so}][viec]" '
            f'value="{escape(b["work"] or "")}" maxlength="160" '
            'placeholder="Việc cần làm ở bước này" '
            'title="📌 Câu hiện trên thẻ khách khi khách tới bước này">'
            '<span class="offlbl">Đang tắt</span>'
            "</div>"
            + _the_tu_khoa(f"b[{so}][tu_khoa]", b["keywords_agent"] or "",
                           "máy nhận ra bước này khi tin có",
                           "gõ cụm rồi Enter")
            + _the_tu_khoa(f"b[{so}][tu_khoa_kh]", b["keywords_customer"] or "",
                           "khách nói câu này thì nhảy tới đây",
                           "để trống = bước này không nhảy cóc", xanh=True)
            + "</div>")

    ghi_chu = (
        '<div class="gnote">Máy <b>đọc tin nhân viên gửi</b> để biết khách đã '
        "đi tới bước nào — chat một lúc xong 3 bước thì con trỏ nhảy thẳng 3. "
        "Máy <b>bỏ dấu cả hai phía</b> nên gõ “băn khoăn” hay “ban khoan” đều "
        "ăn — <b>khỏi phải nhập hai dạng</b>. Ba cụm đặc biệt: <code>#anh</code> "
        "tin có ảnh · <code>#gia</code> tin có số tiền · <code>#ma</code> tin có "
        "mã giảm. Không nhận ra cụm nào thì mỗi <b>lượt nhắn</b> tính 1 bước."
        "</div>"
        '<div class="gnote">Khách <b>trả lời giữa chừng</b> thì con trỏ '
        "<b>đứng yên</b> — việc lúc đó là trả lời khách.</div>"
        '<div class="gnote">🐸 <b>Nhảy cóc</b> (hàng xanh): khách nói toạc điều '
        "đang vướng thì khỏi bò tuần tự. Chỉ <b>tiến</b>, không bao giờ lùi.</div>")
    return ruot + ghi_chu + _thu_cau() + o_so


def _thu_cau() -> str:
    """Ô 🧪 Thử một câu — chấm trên từ khoá ĐANG GÕ, không ghi gì."""
    return (
        '<div class="kwtry">'
        '<div class="kwtt">🧪 Thử một câu · <span>dán câu nhân viên hay gõ, xem '
        "máy hiểu là bước mấy — chấm trên từ khoá <b>đang gõ trên màn</b>, chưa "
        "lưu cũng thử được</span></div>"
        '<div class="kwtrow"><span class="kwtai">'
        '<label title="Tin nhân viên gửi — chấm trên bộ từ khoá hàng TÍM">'
        '<input type="radio" name="kwtAi" value="nv" checked> nhân viên gõ</label>'
        '<label title="Tin khách nhắn — chấm trên bộ từ khoá hàng XANH (nhảy cóc)">'
        '<input type="radio" name="kwtAi" value="kh"> khách nhắn</label>'
        "</span></div>"
        '<div class="kwtrow">'
        '<input type="text" id="kwtCau" placeholder="vd: dạ bên em gửi chị bảng giá ạ">'
        '<label class="kwtck" id="kwtAnhWrap" title="Đánh dấu nếu tin đó có kèm '
        'ảnh — để thử cụm #anh"><input type="checkbox" id="kwtAnh"> có kèm ảnh</label>'
        '<button type="button" class="kwtgo" id="kwtGo">Thử xem</button>'
        "</div>"
        '<div class="kwtkq" id="kwtKq" hidden></div></div>'
    )


def _1d(moc: list[dict]) -> str:
    """1D — thang mua lại: bật/tắt · số ngày · nhãn 📌 · 🤖 máy / 👤 người."""
    ruot = ""
    for m in moc:
        mid = int(m["id"])
        bat = bool(m["active"])
        gat = m["board_column"] == "moc_out"      # mốc BUÔNG — tắt là nguy
        ruot += (
            f'<div class="mitem{"" if bat else " off"}{" crit" if gat else ""}">'
            '<div class="mrow">'
            f'<input type="checkbox" class="msw" id="mc{mid}" '
            f'name="m[{mid}][active]" value="1"{" checked" if bat else ""}>'
            f'<label class="swui" for="mc{mid}"><span></span></label>'
            f'<span class="mname">'
            + ("Buông" if gat else f'Mốc {m["offset_days"]}')
            + f'<small>{escape(m["code"])}</small></span>'
            f'<input class="mnum num" name="m[{mid}][offset_days]" '
            f'value="{int(m["offset_days"])}"><span class="munit">ngày</span>'
            f'<input class="nhanin" name="m[{mid}][nhan]" '
            f'value="{escape(m.get("label") or "")}" maxlength="80" '
            'placeholder="Nhãn 📌 riêng của mốc (trống = dùng câu cột)" '
            'title="📌 Câu hiện trên thẻ khách khi khách đứng ở mốc này">'
            '<span class="aigui">'
            + "".join(
                f'<button type="button" class="aib'
                + (" on" if m["sender"] == v else "")
                + f'" data-v="{v}" title="{t}">{ic}</button>'
                for v, ic, t in (("may", "🤖", "Máy tự gửi mốc này"),
                                 ("nguoi", "👤", "Để người nhắn — máy KHÔNG gửi")))
            + f'<input type="hidden" class="aiv" name="m[{mid}][ai_gui]" '
              f'value="{escape(m["sender"])}"></span>'
            '<span class="offlbl">Đang tắt</span>'
            "</div>"
            + ('<div class="critw" hidden>⚠️'
               '<span class="msg">Tắt mốc BUÔNG thì cả nhóm khách ngủ quay lại '
               "sinh việc — đội không kham nổi.</span>"
               '<button type="button" class="keep">Giữ mốc</button>'
               '<button type="button" class="force">Vẫn tắt</button></div>'
               if gat else "")
            + "</div>")
    return ruot + (
        '<div class="gnote">Mốc để TRỐNG nhãn thì rơi về câu chung của cột '
        "(khai ở <b>1H</b> bên dưới). Ba cột <i>Chăm định kỳ · Đến kỳ mua lại · "
        "Sắp rời bỏ</i> gom nhiều mốc — không đặt nhãn riêng thì mấy mốc đó đọc "
        "y hệt nhau, nhân viên không biết khách ở nấc nào.</div>")


def _cot(bp: str, cot: list[tuple[str, str, str]], dat: dict[str, str],
         theo_moc: set[str] | None = None) -> str:
    """1G/1H — mỗi cột một hàng: tên cột + câu việc 📌. Trống = về mặc định."""
    ruot = ('<div class="nrow chead"><span class="cdot" '
            'style="visibility:hidden"></span><span class="clab">Cột</span>'
            '<span class="cin">Tên cột hiện trên bảng</span>'
            '<span class="cin">Câu việc cần làm 📌</span>'
            '<span class="ctag"></span></div>')
    for ma, ten_goc, mau in cot:
        kn, kw = f"bn_{bp}_{ma}", f"bw_{bp}_{ma}"
        da_dat = bool(dat.get(kn) or dat.get(kw))
        moc_tag = ('<span class="ctm" title="Khách đứng ở mốc có nhãn thì lấy '
                   'nhãn mốc; câu này chỉ dùng khi mốc để trống">theo mốc</span>'
                   if theo_moc and ma in theo_moc else "")
        ruot += (
            f'<div class="nrow"><span class="cdot" style="background:{mau}">'
            f'</span><span class="clab"><span class="cma">{escape(ma)}</span>'
            f"{moc_tag}</span>"
            f'<input class="cin" name="{kn}" value="{escape(dat.get(kn, ""))}" '
            f'maxlength="40" placeholder="{escape(ten_goc)}" '
            'title="Tên cột — đổi ở đây là đổi mọi nơi: bảng, pipeline, bộ lọc">'
            f'<input class="cin" name="{kw}" value="{escape(dat.get(kw, ""))}" '
            'maxlength="120" placeholder="(dùng câu mặc định)" '
            'title="📌 Câu trên thẻ khách">'
            f'<span class="ctag{" on" if da_dat else ""}">'
            + ("đã sửa" if da_dat else "mặc định") + "</span></div>")
    return ruot + (
        '<div class="gnote">Xoá trắng ô rồi Lưu là trả về mặc định — chữ mờ '
        "trong ô chính là chữ gốc.</div>")


def render(buoc: list[dict], moc: list[dict], dat_cot: dict[str, str],
           o_so_1a: str) -> str:
    """Thân mục Mốc thời gian. `o_so_1a` do views/cai_dat dựng (11 ô số của T2)."""
    _cskh = cot_cskh()
    return (
        '<form class="card" method="post" action="/quan-tri/cai-dat?sec=moc" '
        'id="mocForm"><input type="hidden" name="nhom" value="moc">'
        '<h3>⏱️ Mốc thời gian</h3>'
        '<p class="note">Mọi con số và câu chữ điều khiển <b>nhịp chăm khách</b> '
        "gom về đây — trước kia nằm rải ở màn Cài đặt, màn Thang bám đuổi và "
        "màn Chăm sóc, sửa một thứ phải nhớ ba chỗ.</p>"
        + _khoi("k1a", "1A · Thang bám đuổi Sale",
                "nội dung theo BƯỚC, không theo ngày", f"{len(buoc)} bước",
                _1a(buoc, o_so_1a), mo=True)
        + _khoi("k1d", "1D · Thang mua lại", "xương sống bảng CSKH",
                f"{len(moc)} mốc", _1d(moc))
        + _khoi("k1g", "1G · Câu việc cột — Bảng Sale",
                "các cột NGOÀI thang bước", f"{len(COT_SALE)} cột",
                _cot("sale", COT_SALE, dat_cot))
        + _khoi("k1h", "1H · Câu việc cột — Bảng CSKH",
                "dùng khi mốc chưa đặt nhãn", f"{len(_cskh)} cột",
                _cot("cskh", _cskh, dat_cot, COT_THEO_MOC))
        + '<div class="savebar">'
          '<button class="btn primary" type="submit">💾 Lưu thay đổi</button>'
          '<span class="dirty">Chưa có thay đổi.</span></div>'
        "</form>"
    )
