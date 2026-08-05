"""Màn Cài đặt hệ thống — bố cục port từ mẫu Kallet `cai-dat.php` (C8).

Vì sao tách khỏi `views/admin.py`: mẫu để cả màn Cài đặt trong MỘT file 3.671
dòng và đó chính là thứ khiến nó khó sửa. Bên ta tách riêng ngay từ đầu.

## Hai thứ đáng chép từ mẫu

1. **Menu mục con DÍNH bên trái, hiện MỘT mục mỗi lần.** Người dùng vào Cài đặt
   là để sửa một thứ họ đang nghĩ tới; bắt họ cuộn qua 7 nhóm không liên quan
   để tìm nó là thiết kế sai. Bản cũ bên ta đổ cả 56 cài đặt của 8 nhóm vào một
   trang dài dằng dặc.

2. **Mục nào đã có MÀN RIÊNG thì menu trỏ thẳng sang đó** (phần tử thứ 4 trong
   `navDefs` của mẫu) chứ KHÔNG dựng lại ô nhập thứ hai cho cùng một dữ liệu.
   Hai nơi sửa cùng một thứ là hai nơi lệch nhau.

## Luật hiển thị B3.3 của mẫu — đừng sửa

**Ô trống hiện chữ "chưa điền" MÀU CAM, không phải số 0.** `0` là một giá trị
đã đặt (vd "0 = máy không tự tặng voucher"); trống nghĩa là *chưa ai đặt* và
module ăn theo nó đang tự tắt. Hiện `0` cho ô trống làm người dùng tưởng đã cấu
hình xong rồi ngồi chờ một thứ không bao giờ chạy.
"""

from html import escape

_ICON = {
    "moc": "⏱️",
    "dong_bo": "🔄", "quang_cao": "📣", "uu_dai": "🎁", "gui_tin": "📨",
    "giam_sat": "🔍", "cskh": "💚", "bot": "🤖", "vong_doi": "🌱",
}

# Mục ĐẶC BIỆT — không phải một nhóm cài đặt dạng ô số mà là màn cấu hình
# riêng (thang bước · mốc · câu việc cột). Đứng ĐẦU menu vì đây là thứ người
# vận hành đụng tới nhiều nhất.
MUC_MOC = ("moc", "Mốc thời gian")

# Mục ĐẶC BIỆT — dựng tay, không phải một nhóm cài đặt. Thứ tự ở đây là thứ tự
# trên menu; "moc" đứng đầu vì đó là thứ người vận hành đụng tới nhiều nhất.
MUC_DAC_BIET: tuple[tuple[str, str, str], ...] = (
    ("moc", "Mốc thời gian", "⏱️"),
    ("nhan_dien", "Kịch bản nhận diện", "📞"),
    ("goi_y", "Gợi ý kịch bản", "💡"),
)
MA_DAC_BIET = frozenset(m[0] for m in MUC_DAC_BIET)

# T2 — 11 con số của thang bám đuổi Sale đã GỘP vào mục "Mốc thời gian" (khối
# 1A), nên nhóm `sale` không còn xuất hiện thành một mục menu riêng. Bỏ dòng
# này đi là màn Cài đặt hiện HAI chỗ sửa cùng một thứ.
NHOM_AN = frozenset({"sale"})

# Khoá có ĐIỀU KHIỂN RIÊNG (khối dựng tay ở dưới), nên phải rút khỏi lưới ô
# chung — bày cả hai là lại có hai chỗ sửa cùng một giá trị, đúng cái bệnh Đợt 1
# vừa chữa xong ở thang Sale và ngưỡng hạng thẻ.
KHOA_RIENG = frozenset({"outbound_messaging_mode"})

# Mục có MÀN RIÊNG — menu trỏ thẳng sang, không đẻ ô nhập thứ hai.
MAN_RIENG: list[tuple[str, str, str]] = [
    ("🔌 Kết nối Pancake", "/quan-tri/tich-hop",
     "Token, page, nhật ký & lỗi đồng bộ"),
    ("🧾 Trạng thái đơn", "/quan-tri/tich-hop/anh-xa",
     "Ánh xạ 17 mã POS → 11 trạng thái CRM"),
    ("⚡ Luồng tự động", "/quan-tri/luong-tu-dong",
     "Khai + soi luật máy tự chạy — Đợt 3 mới dựng khung, CHƯA gửi tin"),
    ("💎 Hạng thẻ & ngưỡng", "/crm/hang-the",
     "Bậc thang + quyền lợi từng hạng"),
    ("💰 Bậc lương & thưởng", "/crm/bac-luong",
     "Hoa hồng · thưởng chăm · thưởng nóng"),
    ("📖 Thư viện kịch bản", "/crm/kich-ban",
     "Câu mẫu + luật gợi ý theo từ khoá"),
]


def chua_dien(m: dict) -> bool:
    """Ô này CHƯA ĐIỀN hay không — xem luật B3.3 ở đầu file."""
    if m["kieu"] == "bool":
        return False
    gt = m["gia_tri"]
    return gt is None or (isinstance(gt, str) and gt.strip() == "")


def _o(m: dict) -> str:
    """Một ô cấu hình kiểu "field box" của mẫu: mã · nhãn · mô tả · điều khiển."""
    ma = escape(m["code"])
    gt = m["gia_tri"]
    trong = chua_dien(m)
    val = escape("" if gt is None else str(gt))

    if m["kieu"] == "bool":
        dieu_khien = (f'<label class="sw"><input type="checkbox" name="{ma}"'
                      f'{" checked" if gt else ""}><span></span>'
                      f'<b>{"Bật" if gt else "Tắt"}</b></label>')
    elif m["chon"]:
        chon = "".join(
            f'<option value="{escape(c)}"'
            f'{" selected" if str(gt) == c else ""}>{escape(c)}</option>'
            for c in m["chon"])
        dieu_khien = f'<select name="{ma}">{chon}</select>'
    elif m["kieu"] == "str":
        dieu_khien = (f'<input class="cd-in{" trong" if trong else ""}" '
                      f'name="{ma}" value="{val}" placeholder="chưa điền" '
                      'autocomplete="off">')
    else:
        buoc = "1" if m["kieu"] == "int" else "any"
        gh = ""
        if m["nho_nhat"] is not None:
            gh += f' min="{m["nho_nhat"]:g}"'
        if m["lon_nhat"] is not None:
            gh += f' max="{m["lon_nhat"]:g}"'
        dieu_khien = (f'<input class="cd-in num{" trong" if trong else ""}" '
                      f'type="number" step="{buoc}"{gh} name="{ma}" '
                      f'value="{val}" placeholder="chưa điền">'
                      + (f'<span class="cd-dv">{escape(m["don_vi"])}</span>'
                         if m["don_vi"] else ""))

    dau = ""
    if m["rieng"]:
        dau = '<span class="pill">công tắc riêng</span>'
    elif m["da_doi"]:
        dau = (f'<span class="pill warn" title="Mặc định trong .env: '
               f'{escape(str(m["mac_dinh"]))}">đã đổi</span>')
    if trong:
        dau += '<span class="pill cam">chưa điền</span>'

    mac_dinh = ""
    if m["mac_dinh"] not in (None, ""):
        mac_dinh = ('<span class="cd-md">mặc định .env: '
                    f'<code>{escape(str(m["mac_dinh"]))}</code></span>')
    return (
        f'<label class="cd-o{" trong" if trong else ""}">'
        f'<span class="cd-h"><code>{escape(m["code"].upper())}</code>{dau}</span>'
        f'<span class="cd-ten">{escape(m["ten"])}</span>'
        + (f'<span class="cd-mo">{escape(m["mo_ta"])}</span>'
           if m["mo_ta"] else "")
        + f'<span class="cd-dk">{dieu_khien}</span>{mac_dinh}</label>'
    )


def bang_nguong_hang(bac: list[dict], quyen_loi: dict,
                     la_khung: bool = False) -> str:
    """T3 — bảng NGƯỠNG hạng thẻ, gộp vào ngay mục Ưu đãi.

    Trước đây ngưỡng sửa ở `/crm/hang-the` còn mốc giảm quyền lợi lại ở màn Cài
    đặt: cùng một chính sách, hai nơi. Nay cả hai ở đây; `/crm/hang-the` giữ vai
    trò TOÀN CẢNH chỉ đọc (đúng cách mẫu làm với `hang-the.php`).
    """
    if la_khung:
        return (
            '<div class="mocg" style="margin-top:14px" open><div class="gbody">'
            '<div class="mnhom">Ngưỡng từng hạng</div>'
            '<div class="gnote">Bảng <code>crm.card_ranks</code> đang RỖNG nên '
            "5 hạng dưới kia chỉ là khung mặc định, chưa có dòng nào để ghi "
            "ngưỡng vào. Chạy <code>python scripts/seed_uu_dai.py</code> để nạp "
            "bộ hạng chuẩn, rồi quay lại đây điền ngưỡng.</div>"
            "</div></div>")
    dong = ""
    for h in bac:
        icon = (h.get("emoji") or "").strip() or h["mat"]["icon"]
        gia = "" if h["min_spent"] is None else f'{float(h["min_spent"]):.0f}'
        ql = quyen_loi.get(h["code"]) or []
        chip = "".join(
            f'<span class="ht-ql" style="background:{h["mat"]["nen"]}">'
            f'<b style="color:{h["mat"]["mau"]}">{escape(b["benefit_key"])}</b>'
            + (f' · {escape(b["benefit_value"])}' if b["benefit_value"] else "")
            + "</span>" for b in ql)
        dong += (
            f'<div class="nrow"><span class="cdot" '
            f'style="background:{h["mat"]["mau"]}"></span>'
            f'<span class="clab">{escape(icon)} {escape(h["name"])}'
            f'<span class="cma">{escape(h["code"])}</span></span>'
            '<span class="munit">từ</span>'
            f'<input class="cd-in num{" trong" if not gia else ""}" '
            f'type="number" min="0" step="1000" name="nguong_{escape(h["code"])}" '
            f'value="{gia}" placeholder="chưa điền" style="flex:0 0 140px">'
            '<span class="munit">đ</span>'
            f'<span class="cd-mo" style="flex:1 1 auto">{chip or "— chưa khai quyền lợi —"}</span>'
            "</div>")
    return (
        '<div class="mocg" id="nguong" style="margin-top:14px" open>'
        '<div class="gbody">'
        '<div class="mnhom">Ngưỡng từng hạng · tính theo tổng tiền đơn đã giao</div>'
        f"{dong}"
        '<div class="gnote">Ngưỡng để <b>trống</b> = hạng đó ngừng nhận khách '
        "mới cho tới khi điền lại — KHÔNG phải ngưỡng 0đ. Sửa xong nhớ bấm "
        '<b>Tính lại hạng</b> ở <a href="/crm/hang-the">màn Hạng thẻ</a> để áp '
        "cho khách cũ; khách mới thì tính lúc đơn giao xong.</div>"
        "</div></div>")


def khoi_nguon_lead(dem: dict, chi_inbox: bool) -> str:
    """Đ2 — nói rõ công tắc «chỉ nhận lead inbox» đang ảnh hưởng bao nhiêu khách
    THẬT. Một công tắc mà không cho thấy hậu quả thì không ai dám gạt."""
    bl = int(dem.get("comment") or 0)
    if bl:
        hq = (f"Đang có <b>{bl:,}</b>".replace(",", ".")
              + " khách chỉ có hội thoại bình luận — "
              + ("hiện KHÔNG lên bảng việc Sale."
                 if chi_inbox else "hiện ĐANG tính là việc.")
              + " Họ vẫn còn nguyên trong hệ thống, chỉ là không nhắc việc.")
    else:
        hq = ("Chưa có khách nào thuộc diện chỉ-bình-luận. Poller mặc định chỉ "
              "kéo hội thoại <b>inbox</b> về; tắt công tắc này thì mỗi vòng "
              "poller kéo thêm một lượt <b>COMMENT</b> nữa cho từng page.")
    return (
        '<div class="mocg" id="nguon-lead" style="margin-top:14px">'
        '<div class="gbody">'
        '<div class="mnhom">Nguồn lead vào bảng việc · ảnh hưởng thật</div>'
        f'<div class="gnote">{hq}</div>'
        '<div class="gnote">Đếm theo hội thoại đã đồng bộ: '
        + " · ".join(f'<b>{int(v):,}</b> {escape(k)}'.replace(",", ".")
                     for k, v in sorted(dem.items())) + " — xem ở "
        '<a href="/crm/khach-hang">Khách hàng</a>.</div>'
        "</div></div>")


def khoi_ban_giao() -> str:
    """Đ2 — luật LUÔN CHẠY, không có công tắc. Nói thẳng ra để người vào mục
    Vòng đời khỏi đi tìm cái nút tắt không tồn tại."""
    return (
        '<div class="mocg" style="margin-top:14px"><div class="gbody">'
        '<div class="mnhom">Bàn giao Sale → Chăm sóc · luôn chạy</div>'
        '<div class="gnote">Khách chuyển từ Sale sang CSKH khi <b>đơn ĐẦU TIÊN '
        "giao thành công</b> — cố định, không tắt được. Lịch chăm đếm từ "
        "<b>ngày khách NHẬN HÀNG</b>, không phải ngày chốt đơn: đó là ngày khách "
        "thật sự bắt đầu dùng, và cũng là mốc duy nhất cả hai đội nhìn giống "
        'nhau. Các mốc chăm khai ở <a href="/quan-tri/cai-dat?sec=moc#k1d">Mốc '
        "thời gian → Thang mua lại</a>.</div></div></div>")


def khoi_cong_tac_gui_tin(tt: dict, che_do: dict, co_gat: bool) -> str:
    """Đ2 — công tắc gửi tin: BA nút chế độ + hàng trạng thái hai lớp khoá.

    `tt` là gói của `cong_tac_gui_tin.dien_giai()`; `che_do` là bảng nhãn.
    `co_gat` = người xem có quyền `gui_tin.bat_cong_tac` không — KHÔNG có thì
    nút vẫn HIỆN nhưng khoá, để người ta biết chỗ này tồn tại và đi xin quyền,
    thay vì tưởng hệ thống không làm được.
    """
    nut = ""
    for ma, (nhan, icon, mo) in che_do.items():
        on = " on" if ma == tt["ma"] else ""
        khoa = "" if co_gat else " disabled"
        nut += (f'<button class="ctnut{on}"{khoa} name="che_do" value="{ma}"'
                f'{"" if co_gat else " title=Cần quyền gui_tin.bat_cong_tac"}>'
                f'<b>{icon} {escape(nhan)}</b><i>{escape(mo)}</i></button>')

    khoa_cung = tt["khoa_cung"]
    hang = (
        '<div class="ctkhoa">'
        f'<span>🔒 Khoá cứng hệ thống: <b class="{"xau" if khoa_cung else "tot"}">'
        f'{"ĐÓNG" if khoa_cung else "MỞ"}</b></span><span class="chan">·</span>'
        f'<span>Chế độ đang đặt: <b>{tt["icon"]} {escape(tt["nhan"])}</b></span>'
        '<span class="chan">·</span>'
        f'<span>Thực tế đang gửi thật: <b class="{"tot" if tt["gui_that"] else "xau"}">'
        f'{"CÓ" if tt["gui_that"] else "KHÔNG"}</b></span>'
        '<span class="het">Phải mở CẢ HAI lớp máy mới bắn tin ra ngoài.</span>'
        "</div>")
    vi_sao = (f'<p class="ctwhy">{escape(tt["vi_sao"])}</p>'
              if tt["vi_sao"] else "")
    canh = "" if co_gat else (
        '<p class="ctwhy">Bạn đang xem ở chế độ chỉ đọc — gạt công tắc này cần '
        "quyền <code>gui_tin.bat_cong_tac</code>, tách riêng khỏi quyền sửa cài "
        "đặt thường vì tin đã gửi thì không thu hồi được.</p>")
    return (
        '<form class="card ctcard" method="post" '
        'action="/quan-tri/cai-dat/che-do-gui-tin">'
        '<h3>🛡️ Công tắc gửi tin tự động</h3>'
        '<p class="note">Máy chỉ bắn tin ra ngoài khi chế độ là <b>THẬT</b> '
        '<i>và</i> khoá cứng đã mở. Mặc định TẮT cho an toàn lúc còn đang đồng '
        "bộ dữ liệu.</p>"
        f'{hang}<div class="ctnuts">{nut}</div>{vi_sao}{canh}'
        '<p class="note" style="margin-top:12px">Bấm một chế độ là lưu ngay — '
        "mỗi lần đổi đều vào Nhật ký cấu hình kèm giá trị cũ → mới.</p></form>")


def _menu(nhom: list[dict], sec: str) -> str:
    muc = "".join(
        f'<a class="cd-nav{" on" if sec == ma else ""}" '
        f'href="/quan-tri/cai-dat?sec={ma}">'
        f'<span class="cd-ic">{icon}</span>'
        f'<span class="cd-lb">{escape(ten)}</span></a>'
        for ma, ten, icon in MUC_DAC_BIET)
    for g in nhom:
        if g["ma"] in NHOM_AN:
            continue
        on = " on" if g["ma"] == sec else ""
        n_trong = sum(1 for m in g["muc"] if chua_dien(m))
        # Đếm ô chưa điền ngay trên menu — không có nó thì phải mở từng mục ra
        # mới biết chỗ nào còn thiếu cấu hình.
        chuong = (f'<i class="cd-cam" title="{n_trong} ô chưa điền">'
                  f"{n_trong}</i>" if n_trong else "")
        muc += (f'<a class="cd-nav{on}" href="/quan-tri/cai-dat?sec={escape(g["ma"])}">'
                f'<span class="cd-ic">{_ICON.get(g["ma"], "⚙️")}</span>'
                f'<span class="cd-lb">{escape(g["ten"])}</span>'
                f'{chuong}<b>{len(g["muc"])}</b></a>')
    on_log = " on" if sec == "log" else ""
    muc += (f'<a class="cd-nav{on_log}" href="/quan-tri/cai-dat?sec=log">'
            '<span class="cd-ic">📜</span>'
            '<span class="cd-lb">Nhật ký cấu hình</span></a>')
    ngoai = "".join(
        f'<a class="cd-nav ngoai" href="{escape(u)}" title="{escape(mo)}">'
        f'<span class="cd-lb">{escape(ten)}</span><b>↗</b></a>'
        for ten, u, mo in MAN_RIENG)
    return (f'<nav class="cd-menu">{muc}'
            '<div class="cd-nav-g">Có màn riêng</div>'
            f"{ngoai}</nav>")


# Việc đọc được từ mã `action`. Không có trong bảng này = "trả về mặc định"
# (chỉ còn `setting_reset` rơi vào đó).
_VIEC = {
    "setting_update": "đổi",
    "sua_nguong_hang_the": "đổi ngưỡng hạng thẻ",
}


def _nhat_ky(rows: list[dict]) -> str:
    """Mục "Nhật ký cấu hình" — ai đổi cài đặt nào, từ giá trị nào sang gì.

    Đọc thẳng `crm.audit_logs` (mọi lượt sửa đã ghi sẵn từ A4) thay vì đẻ bảng
    `config_log` riêng như mẫu — một nguồn sự thật, khỏi có ngày hai bảng lệch.
    """
    than = ""
    for r in rows:
        cu = r.get("old_value") or {}
        moi = r.get("new_value") or {}
        khoa = sorted(set(cu) | set(moi))
        doi = " · ".join(
            f'<code>{escape(k)}</code>: {escape(str(cu.get(k, "—")))} → '
            f'<b>{escape(str(moi.get(k, "—")))}</b>' for k in khoa) or "—"
        luc = r.get("created_at")
        than += (
            "<tr>"
            f'<td class="note">{luc:%d/%m/%Y %H:%M}</td>'
            f'<td>{escape(str(r.get("user_name") or "—"))}</td>'
            f'<td>{_VIEC.get(str(r.get("action")), "trả về mặc định")}</td>'
            f"<td>{doi}</td></tr>")
    than = than or ('<tr><td colspan="4" class="rong">Chưa ai đổi cài đặt nào '
                    "— mọi thứ đang chạy đúng giá trị trong <code>.env</code>."
                    "</td></tr>")
    return (
        '<div class="card"><h3>📜 Nhật ký cấu hình</h3>'
        '<p class="note">Mọi lượt sửa cài đặt đều vào đây kèm giá trị CŨ → MỚI. '
        'Xem đầy đủ mọi loại thao tác ở <a href="/quan-tri/nhat-ky">Nhật ký '
        "hoạt động</a>.</p>"
        '<div class="tblwrap"><table class="tbl"><thead><tr>'
        "<th>Lúc</th><th>Người đổi</th><th>Việc</th><th>Thay đổi</th>"
        f"</tr></thead><tbody>{than}</tbody></table></div></div>"
    )


def render(nhom: list[dict], *, sec: str = "", nhat_ky: list[dict] | None = None,
           co_sua: bool = True, dac_biet: dict[str, str] | None = None,
           truoc: dict[str, str] | None = None,
           sau: dict[str, str] | None = None) -> str:
    """Thân màn Cài đặt (chưa bọc shell — `views/admin.render_cai_dat` bọc nốt).

    Mỗi mục là một form riêng: bấm Lưu ở mục nào chỉ gửi các ô của mục đó, nên
    sửa một chỗ không kéo theo rủi ro ghi đè chỗ khác đang mở ở tab kia.

    `dac_biet` — thân các mục dựng tay (Mốc thời gian · Kịch bản nhận diện ·
    Gợi ý kịch bản), khoá theo mã mục. Chúng cần dữ liệu từ nhiều bảng nên route
    dựng sẵn rồi truyền vào; để view này tự đi lấy là trộn tầng.

    `truoc` / `sau` — khối HTML dựng sẵn chèn TRƯỚC hoặc SAU lưới ô của một
    nhóm, khoá theo mã nhóm. Khối "trước" nằm NGOÀI form của nhóm (dành cho thứ
    có form riêng, như công tắc gửi tin — nó cần quyền khác và lưu ngay khi
    bấm); khối "sau" nằm TRONG form, đi chung nút Lưu (bảng ngưỡng hạng thẻ).
    """
    truoc, sau, dac_biet = truoc or {}, sau or {}, dac_biet or {}
    hop_le = [g["ma"] for g in nhom if g["ma"] not in NHOM_AN]
    if sec not in hop_le and sec != "log" and sec not in MA_DAC_BIET:
        sec = "moc" if dac_biet.get("moc") else (hop_le[0] if hop_le else "log")

    if sec in MA_DAC_BIET:
        than = dac_biet.get(sec) or (
            f'<p class="note">Chưa dựng được mục «{escape(sec)}».</p>')
    elif sec == "log":
        than = _nhat_ky(nhat_ky or [])
    else:
        g = next(g for g in nhom if g["ma"] == sec)
        o = "".join(_o(m) for m in g["muc"] if m["code"] not in KHOA_RIENG)
        nut = ""
        if co_sua:
            nut = (
                '<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">'
                '<button class="btn primary">Lưu mục này</button>'
                '<button class="btn" name="mac_dinh" value="1" '
                "onclick=\"return confirm('Bỏ mọi thay đổi của mục này, quay "
                "về đúng giá trị trong .env?')\" "
                'title="Bỏ mọi thay đổi của mục, quay về giá trị trong .env">'
                "Trả về mặc định</button></div>")
        than = (
            truoc.get(g["ma"], "")
            + '<form class="card" method="post" action="/quan-tri/cai-dat">'
            f'<input type="hidden" name="nhom" value="{escape(g["ma"])}">'
            f'<h3>{_ICON.get(g["ma"], "⚙️")} {escape(g["ten"])}</h3>'
            f'<div class="cd-grid">{o}</div>'
            f'{sau.get(g["ma"], "")}{nut}</form>')

    return (
        '<div class="card" style="margin-bottom:14px"><p class="note" '
        'style="margin:0">Đổi ở đây có tác dụng <b>ngay ở lượt chạy kế tiếp</b> '
        "của worker (chậm nhất khoảng 10 giây) — không phải khởi động lại "
        "server. Ô để <b>trống</b> hiện chữ <b>“chưa điền”</b> màu cam: đó là "
        "<i>chưa ai đặt</i>, khác hẳn số <b>0</b> (đã đặt bằng 0). Mọi thay đổi "
        'đều vào <a href="/quan-tri/cai-dat?sec=log">Nhật ký cấu hình</a>.</p>'
        '<p class="note">Token, mật khẩu và chuỗi kết nối <b>cố ý không</b> nằm '
        "ở đây — chúng chỉ có trong <code>.env</code> trên máy chủ và ở màn "
        '<a href="/quan-tri/tich-hop">Kết nối</a>.</p></div>'
        + '<div class="cd-wrap">' + _menu(nhom, sec)
        + f'<div class="cd-than">{than}</div></div>'
    )
