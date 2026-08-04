"""Khung (shell) dùng chung cho toàn bộ giao diện web.

Mọi trang đều gọi `render_shell(...)` để có cùng một bố cục:

    ┌──────────┬────────────────────────────────┐
    │ sidebar  │ topbar (tiêu đề + tab + nút)   │
    │ (menu    ├────────────────────────────────┤
    │  trái)   │ content (nội dung từng trang)  │
    └──────────┴────────────────────────────────┘

Toàn bộ CSS của dự án nằm ở `_CSS` trong file này (một stylesheet duy nhất),
gồm cả các class dùng riêng cho từng màn hình: form/danh sách dữ liệu bot,
thẻ hội thoại, bong bóng chat... Nhờ vậy các module webview khác chỉ cần dựng
phần thân HTML rồi bọc lại bằng `render_shell`.

Bố cục tự co theo bề rộng: dưới 900px sidebar chuyển thành thanh ngang trên đầu.
"""

import time
from html import escape

from app.core.request_context import current_user

# --- Icon dạng SVG inline (dùng currentColor nên tự đổi màu theo trạng thái) ---
_ICONS = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/>'
            '<path d="M5 9.5V21h5v-6h4v6h5V9.5"/>',
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1"/>'
                 '<rect x="14" y="3" width="7" height="5" rx="1"/>'
                 '<rect x="14" y="12" width="7" height="9" rx="1"/>'
                 '<rect x="3" y="16" width="7" height="5" rx="1"/>',
    "messages": '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.5 8.5 0 0 1-3.9-.9L3 21'
                'l1.9-5A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5z"/>',
    "customers": '<path d="M17 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
                 '<circle cx="9.5" cy="7" r="4"/>'
                 '<path d="M22 21v-2a4 4 0 0 0-3-3.9"/>'
                 '<path d="M16 3.1a4 4 0 0 1 0 7.8"/>',
    "sentiment": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9'
                 'a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "pipeline": '<rect x="3" y="3" width="5" height="18" rx="1"/>'
                '<rect x="10" y="3" width="5" height="12" rx="1"/>'
                '<rect x="17" y="3" width="5" height="8" rx="1"/>',
    "tasks": '<rect x="3" y="3" width="18" height="18" rx="2"/>'
             '<path d="m8 12 3 3 5-6"/>',
    "orders": '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/>'
              '<path d="M2 3h3l2.6 12.6a1.5 1.5 0 0 0 1.5 1.2h8.6a1.5 1.5 0 0 0 1.5-1.2L21 8H6"/>',
    "care": '<path d="M12 21C7 16.5 3 13 3 8.8A4.8 4.8 0 0 1 7.8 4c1.7 0 3.2.8 4.2 2.1'
            'A5.3 5.3 0 0 1 16.2 4 4.8 4.8 0 0 1 21 8.8c0 4.2-4 7.7-9 12.2z"/>',
    "repurchase": '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>',
    "products": '<path d="M21 8.5 12 3 3 8.5v7L12 21l9-5.5v-7z"/>'
                '<path d="M3 8.5 12 14l9-5.5"/><path d="M12 21V14"/>',
    "admin": '<circle cx="12" cy="12" r="3"/>'
             '<path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83'
             'l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0'
             'v-.09a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06'
             'a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3'
             'a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.65 8.9a1.7 1.7 0 0 0-.34-1.87l-.06-.06'
             'a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h0A1.7 1.7 0 0 0 10.04 3V3'
             'a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.03 1.56h0a1.7 1.7 0 0 0 1.87-.34l.06-.06'
             'a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v0'
             'a1.7 1.7 0 0 0 1.56 1.03H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1z"/>',
    "bell": '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>'
            '<path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    "data": '<path d="M12 2a3 3 0 0 0-3 3v.4A3.2 3.2 0 0 0 7 11a3 3 0 0 0 2 5.6V18'
            'a3 3 0 0 0 6 0v-1.4A3 3 0 0 0 17 11a3.2 3.2 0 0 0-2-5.6V5a3 3 0 0 0-3-3z"/>'
            '<path d="M12 2v20"/>',
}

# Menu bên trái, chia NHÓM. Mỗi mục: (đường dẫn, nhãn, khoá `active`, icon,
# quyền cần có). Quyền "" = ai đăng nhập cũng thấy; có mã -> chỉ hiện khi token
# mang quyền đó; nhiều mã cách nhau "|" = có MỘT trong số đó là hiện (vd mục
# Quản trị mở cho cả trưởng nhóm). Đây chỉ là ẨN MỤC MENU cho gọn — chặn thật
# nằm ở route.
# Nhóm CRM là các màn khung (xem app/web/views/crm.py) — lát cắt B1…B11 làm đầy.
MENU_GROUPS: list[tuple[str, list[tuple[str, str, str, str, str]]]] = [
    ("CRM", [
        # Màn 2 — trang chủ theo vai trò (đăng nhập xong vào đây, "/" trỏ về đây)
        ("/crm/trang-chu", "Trang chủ", "crm-home", "home", ""),
        # Màn 3 — trung tâm thông báo (chuông ở góc phải cũng trỏ về đây)
        ("/crm/thong-bao", "Thông báo", "crm-notify", "bell", ""),
        ("/crm/tong-quan", "Tổng quan", "crm-overview", "dashboard", ""),
        # B11 — màn 60-64 + drill-down FR-173 (màn 5-6 vào từ đây/trang chủ)
        ("/crm/bao-cao", "Báo cáo", "crm-reports", "sentiment", ""),
        ("/crm/khach-hang", "Khách hàng", "crm-customers", "customers", ""),
        # Mục này được NÂNG thành 2 khối bộ phận xổ/thu ĐỨNG LIỀN NHAU (xem
        # _sidebar): "Sale" (_sale_dept) rồi ngay dưới là "Chăm sóc khách hàng"
        # (_dept_cskh) — hai bộ phận nối tiếp nhau đúng luồng bàn giao Sale→CSKH.
        ("/crm/pipeline", "Pipeline Sale", "crm-pipeline", "pipeline", ""),
        ("/crm/cong-viec", "Công việc", "crm-tasks", "tasks", ""),
        ("/crm/don-hang", "Đơn hàng", "crm-orders", "orders", ""),
        # B8 — màn 24-25: đơn giao thành công tự sinh phiếu, CSKH nhận/trả lại
        ("/crm/ban-giao", "Bàn giao", "crm-handover", "care", ""),
        ("/crm/san-pham", "Sản phẩm", "crm-products", "products", ""),
        # Màn 69 + 71 — bảng theo dõi automation đang chạy (không phải builder)
        ("/crm/automation", "Automation", "crm-automation", "tasks", ""),
        # BRD mục 4 (nguồn quảng cáo) — màn 7 + 53-55: chi phí · ROAS · LTV
        ("/crm/quang-cao", "Nguồn quảng cáo", "crm-ads", "sentiment", "ads.view"),
        # BRD mục 4 — khu Tích hợp Pancake (kết nối, nhật ký/lỗi đồng bộ, ánh xạ)
        ("/quan-tri/tich-hop", "Tích hợp", "tich-hop", "data", "integration.manage"),
    ]),
    # Cả nhóm đòi bot.view (chỉ Chủ DN/Admin có) — middleware trong app/main.py
    # chặn thật theo tiền tố _KHU_BOT, đây chỉ ẩn menu.
    ("Bot Pancake", [
        ("/bang-dieu-khien", "Bảng điều khiển", "dashboard", "dashboard", "bot.view"),
        ("/tin-nhan", "Tin nhắn", "messages", "messages", "bot.view"),
        ("/khach-hang", "KH Pancake", "customers", "customers", "bot.view"),
        ("/cam-xuc", "Cảm xúc", "sentiment", "sentiment", "bot.view"),
        ("/data/kich-ban", "Dữ liệu bot", "data", "data", "bot.view"),
    ]),
    # Quản trị đứng CUỐI menu, dưới cả nhóm Bot Pancake — việc thiết lập chứ
    # không phải việc hằng ngày. Nhóm không tên nên _sidebar khỏi in tiêu đề.
    ("", [
        ("/quan-tri/nhan-vien", "Quản trị", "admin", "admin",
         "user.manage|user.manage_team"),
    ]),
]


def _icon(name: str) -> str:
    """Bọc path SVG thành thẻ <svg> 20px, nét theo màu chữ hiện tại."""
    return (
        '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        f'{_ICONS.get(name, "")}</svg>'
    )


# Chấm màu 13 giai đoạn pipeline ở khối Sale (bảng `pipeline_stages` không có
# cột màu — tô cố định theo thứ tự sort_order, đủ phân biệt bằng mắt).
_STAGE_MAU = ["#7a4f9c", "#3b62d9", "#e0a417", "#78909c", "#00897b", "#e5484d",
              "#2e7d32", "#b0413e", "#5c6bc0", "#8d6e63", "#26a69a", "#ec407a",
              "#7cb342"]


def mau_giai_doan(i: int) -> str:
    """Màu của giai đoạn thứ `i` (theo sort_order) — menu trái và bảng chăm sóc
    ở màn 11 dùng CHUNG hàm này nên chấm menu luôn khớp màu cột."""
    return _STAGE_MAU[i % len(_STAGE_MAU)]


def _sale_dept(active: str, perms: list) -> str:
    """Mục XỔ XUỐNG 'Sale' (kiểu Kallet — thế chỗ mục Pipeline Sale phẳng):
    Nhiệm vụ (Bảng chăm sóc) → Cột trên bảng (13 giai đoạn, chấm màu + số lead
    đang mở — bấm là mở Kanban tô sáng đúng cột) → Công cụ.

    Cùng bộ class nd-* với _dept_cskh cho đồng bộ. <details> thuần nên không
    cần JS (PJAX chỉ bắt thẻ <a>, bấm tiêu đề xổ/thu không bị chặn); DB lỗi
    thì lùi về link phẳng như cũ."""
    on = " on" if active == "crm-pipeline" else ""
    try:
        from app.db.repositories.crm_screens_repo import sale_menu

        stages = sale_menu()
    except Exception:  # noqa: BLE001 — DB chưa lên vẫn phải có menu dùng được
        return (f'<a class="nav-item{on}" href="/crm/pipeline">'
                f'{_icon("pipeline")}<span>Pipeline Sale</span></a>')

    cot = "".join(
        f'<a class="nd-link" href="/crm/pipeline?st={s["id"]}">'
        f'<span class="nd-dot" style="background:{mau_giai_doan(i)}"></span>'
        f'<span>{escape(s["name"])}</span>'
        f'<span class="nd-count">{s["so_lead"]}</span></a>'
        for i, s in enumerate(stages)
    )
    cong_cu = ""
    if "bot.view" in perms:
        cong_cu += ('<a class="nd-link" href="/data/kich-ban">'
                    "<span>📖 Thư viện kịch bản</span></a>")
    cong_cu += ('<a class="nd-link" href="/crm/san-pham">'
                "<span>🏷️ Bảng giá &amp; liệu trình</span></a>")

    return (
        f'<details class="nav-dept"{" open" if on else ""}>'
        f'<summary>{_icon("pipeline")}<span>Sale</span>'
        '<span class="nd-chev">▾</span></summary>'
        '<div class="nd-group">Nhiệm vụ</div>'
        f'<a class="nd-link{on}" href="/crm/pipeline"><span>🎯 Bảng chăm sóc</span></a>'
        '<div class="nd-group">Cột trên bảng</div>'
        f"{cot}"
        '<div class="nd-group">Công cụ</div>'
        f"{cong_cu}"
        "</details>"
    )


def _dept_cskh(active: str) -> str:
    """Khối 'Chăm sóc khách hàng' xổ/thu trong menu trái — CÙNG NẾP `_sale_dept`
    (class dept/sm-group/sm-link/sm-child/chev, kiểu Kallet): Nhiệm vụ chăm sóc
    (số đếm thật từ tasks B4, theo người đăng nhập) → Chăm & mua lại.

    DB lỗi thì vẫn hiện khối, chỉ thiếu số. Màn hẹp (<900px) khối xổ bị ẩn —
    hiện 2 link phẳng mobile-only thay (Chăm sóc/Mua lại không còn mục phẳng)."""
    on = " on" if active in ("crm-care", "crm-repurchase") else ""
    flat = (
        f'<a class="nav-item{" on" if active == "crm-care" else ""} mobile-only" '
        f'href="/crm/cham-soc">{_icon("care")}<span>Chăm sóc</span></a>'
        f'<a class="nav-item{" on" if active == "crm-repurchase" else ""} mobile-only" '
        f'href="/crm/mua-lai">{_icon("repurchase")}<span>Mua lại</span></a>'
    )
    try:
        from app.db.repositories.crm_screens_repo import menu_cskh_counts

        user = current_user.get() or {}
        so = menu_cskh_counts(int(user.get("sub", 0)) or None)
    except Exception:  # noqa: BLE001 — menu không được chết vì số đếm
        so = None

    def n(khoa: str) -> str:
        return f" ({so[khoa]})" if so is not None else ""

    return flat + (
        f'<details class="dept"{" open" if on else ""}>'
        f'<summary class="nav-item{on}">{_icon("care")}'
        '<span>Chăm sóc khách hàng</span><span class="chev">▸</span></summary>'
        '<div class="nav-kids">'
        '<div class="sm-group">Nhiệm vụ chăm sóc</div>'
        f'<a class="sm-link" href="/crm/cong-viec">🗓️ Cần làm hôm nay{n("hom_nay")}</a>'
        f'<a class="sm-child" href="/crm/cong-viec">'
        f'<span class="dot" style="background:#c62828"></span>Quá hạn{n("qua_han")}</a>'
        f'<a class="sm-child" href="/crm/cong-viec">'
        f'<span class="dot" style="background:#1565c0"></span>Sắp tới{n("sap_toi")}</a>'
        '<div class="sm-group">Chăm &amp; mua lại</div>'
        f'<a class="sm-link" href="/crm/cham-soc">💚 Chăm sóc C01-C09{n("cham_soc")}</a>'
        f'<a class="sm-link" href="/crm/mua-lai">🔄 Cơ hội mua lại{n("mua_lai")}</a>'
        '<a class="sm-link" href="/crm/khach-ngu">😴 Khách ngủ (màn 41)</a>'
        "</div></details>"
    )


def _sidebar(active: str) -> str:
    """Menu trái: logo + các nhóm mục; mục đang xem được tô đậm. Mục gắn quyền
    chỉ hiện khi người đăng nhập có quyền đó (đọc từ contextvar middleware đặt)."""
    user = current_user.get()
    perms = (user or {}).get("perms") or []
    items = ""
    for ten_nhom, muc in MENU_GROUPS:
        muc_hien = ""
        for href, label, key, icon, quyen in muc:
            if quyen and not any(m in perms for m in quyen.split("|")):
                continue
            if key == "crm-pipeline":
                # Mục Pipeline được nâng thành HAI khối bộ phận xổ/thu đứng liền
                # nhau (kiểu Pancake): Sale → Chăm sóc khách hàng, đúng thứ tự
                # khách chạy qua (Sale chốt đơn → bàn giao sang CSKH).
                muc_hien += _sale_dept(active, perms) + _dept_cskh(active)
                continue
            cls = "nav-item on" if key == active else "nav-item"
            muc_hien += (
                f'<a class="{cls}" href="{href}">{_icon(icon)}<span>{label}</span></a>'
            )
        # cả nhóm bị ẩn theo quyền -> khỏi in tên nhóm trơ trọi; nhóm không tên
        # (khu quản trị ở cuối menu) thì chỉ in mục, không in tiêu đề nhóm
        if muc_hien:
            items += (f'<div class="nav-group">{escape(ten_nhom)}</div>'
                      if ten_nhom else '<div class="nav-sep"></div>') + muc_hien
    return (
        '<aside class="side">'
        '<a class="brand" href="/bang-dieu-khien">'
        '<span class="logo">FB</span><span class="bname">Sales Bot</span></a>'
        f'<nav class="nav">{items}</nav>'
        "</aside>"
    )


def _user_box() -> str:
    """Góc phải topbar: tên + vai trò người đăng nhập và nút Đăng xuất (A2).

    Đọc từ contextvar do middleware auth trong app/main.py đặt — không phải sửa
    chữ ký render_shell của 37 route. Không có user (lý thuyết không xảy ra vì
    web đã khoá) thì khỏi hiện gì.
    """
    user = current_user.get()
    if not user:
        return ""
    ten = escape(user.get("name") or user.get("username") or "?")
    vai_tro = escape(user.get("role") or "")
    return (
        '<div class="top-user">'
        + _chuong(user)
        + f'<div class="su-info"><div class="su-name" title="{ten}">{ten}</div>'
        f'<div class="su-role">{vai_tro}</div></div>'
        '<form method="post" action="/dang-xuat" class="su-form" data-native>'
        '<button class="su-out" title="Đăng xuất">Đăng xuất</button></form>'
        "</div>"
    )


# Số thông báo chưa đọc bày trên MỌI trang -> cache ngắn theo từng người,
# khỏi bắn một câu đếm mỗi lần vẽ trang (cùng cách làm với _sale_dept).
_chuong_cache: dict[int, tuple[float, int]] = {}
_CHUONG_TTL = 20.0


def _chuong(user: dict) -> str:
    """Chuông thông báo (màn 3) + huy hiệu số chưa đọc."""
    try:
        uid = int(user.get("sub") or 0)
    except (TypeError, ValueError):
        return ""
    if not uid:
        return ""
    luc, so = _chuong_cache.get(uid, (0.0, 0))
    if time.monotonic() - luc > _CHUONG_TTL:
        try:
            from app.db.repositories import notification_repo

            so = notification_repo.dem_chua_doc(uid)["tong"]
        except Exception:  # noqa: BLE001 — DB lỗi thì chuông im, không vỡ trang
            so = 0
        _chuong_cache[uid] = (time.monotonic(), so)
    huy_hieu = (f'<span class="bell-dot">{so if so < 100 else "99+"}</span>'
                if so else "")
    return (
        f'<a class="bell" href="/crm/thong-bao" title="Thông báo ({so} chưa đọc)">'
        f'{_icon("bell")}{huy_hieu}</a>'
    )


def tabs_bar(items: list[tuple[str, str, str]], active: str) -> str:
    """Dải tab con trong 1 mục menu. `items` = [(href, nhãn, khoá)]."""
    html = ""
    for href, label, key in items:
        cls = "tab on" if key == active else "tab"
        html += f'<a class="{cls}" href="{href}">{escape(label)}</a>'
    return f'<nav class="tabs">{html}</nav>'


def flash(ok: str = "", error: str = "") -> str:
    """Dải thông báo kết quả (xanh = thành công, đỏ = lỗi)."""
    if ok:
        return f'<div class="flash ok">✓ {escape(ok)}</div>'
    if error:
        return f'<div class="flash err">✕ {escape(error)}</div>'
    return ""


def stat(
    label: str, value: str, hint: str = "", tone: str = "", href: str = ""
) -> str:
    """Ô số liệu cho Bảng điều khiển. `tone` = '' | 'ok' | 'err' | 'warn'.

    href — nếu có, cả ô trở thành liên kết bấm được (hiện chevron ở góc phải).
    """
    hint_html = f'<div class="s-hint">{hint}</div>' if hint else ""
    tone_cls = f" {tone}" if tone else ""
    inner = (
        f'<div class="s-label">{escape(label)}</div>'
        f'<div class="s-value">{value}</div>{hint_html}'
    )
    if href:
        return f'<a class="stat link{tone_cls}" href="{escape(href)}">{inner}</a>'
    return f'<div class="stat{tone_cls}">{inner}</div>'


def render_shell(
    title: str,
    active: str,
    body: str,
    heading: str = "",
    sub: str = "",
    tabs: str = "",
    actions: str = "",
    script: str = "",
    full: bool = False,
) -> str:
    """Ghép 1 trang HTML hoàn chỉnh.

    title   — tên trên tab trình duyệt
    active  — khoá mục menu đang chọn (xem MENU)
    body    — HTML phần nội dung
    heading — tiêu đề lớn trên topbar (mặc định = title)
    sub     — dòng mô tả nhỏ dưới tiêu đề (đã là HTML)
    tabs    — dải tab con (dùng `tabs_bar`)
    actions — HTML nút/điều khiển đặt bên phải topbar
    script  — JS riêng của trang, thêm vào cuối (vd polling ở màn Tin nhắn).
              Được đánh dấu `data-page-script` để `_NAV_JS` tìm và chạy lại
              sau mỗi lần điều hướng bằng AJAX (xem _NAV_JS).
    full    — True: nội dung chiếm hết chiều cao, tự cuộn (dùng cho màn chat)
    """
    heading = heading or title
    sub_html = f'<div class="page-sub">{sub}</div>' if sub else ""
    actions_html = f'<div class="page-actions">{actions}</div>' if actions else ""
    page_script_html = f"<script data-page-script>{script}</script>" if script else ""
    script_html = f"<script>{_NAV_JS}</script>{page_script_html}"
    content_cls = "content full" if full else "content"
    main_cls = "main full" if full else "main"

    return (
        "<!doctype html><html lang=\"vi\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)} — FB Sales Bot</title>"
        f"<style>{_CSS}</style></head><body>"
        + _sidebar(active)
        + f'<main class="{main_cls}"><header class="topbar">'
        '<div class="page-head">'
        f'<h1>{escape(heading)}</h1>{sub_html}</div>{actions_html}'
        + _user_box()
        + f"</header>{tabs}"
        f'<div class="{content_cls}">{body}</div>'
        "</main>"
        + script_html
        + "</body></html>"
    )


# ---------------------------------------------------------------------------
# Stylesheet dùng chung. Để nguyên dạng chuỗi thường (không f-string) nên không
# phải nhân đôi dấu ngoặc nhọn của CSS.
# ---------------------------------------------------------------------------
_CSS = """
/* Chuyển trang mượt: trình duyệt crossfade giữa 2 lần tải thay vì chớp trắng.
   Đặt tên ổn định cho các khối lặp lại y hệt ở mọi trang (sidebar/topbar/tab)
   để chúng được giữ nguyên vị trí, chỉ phần nội dung bên dưới mới crossfade. */
@view-transition{navigation:auto}
.side{view-transition-name:side}
.topbar{view-transition-name:topbar}
.tabs{view-transition-name:tabs}
/* Bảng màu tím–hồng (lấy theo giao diện Kallet CRM): nền tím rất nhạt, chữ mực
   tím đậm, nhấn bằng tím #6f5a9c + hồng #e91e8c, đổ bóng ám tím thay vì xám. */
:root{
  --bg:#f5eff6; --card:#fff; --text:#2b2230; --sub:#8a7f98; --border:#eee3f0;
  --accent:#6f5a9c; --accent2:#a8718f; --hot:#e91e8c; --soft:#f7f1fa;
  --ok:#16a34a; --err:#e5484d; --warn:#e0900a;
  --ok-bg:#e9f7ee; --err-bg:#fdecec; --warn-bg:#fff5e2; --hot-bg:#fdeef5;
  --side:linear-gradient(185deg,#6f5a9c 0%,#8c6a9b 48%,#c4868f 100%);
  --side-tx:rgba(255,255,255,.78); --side-on:rgba(255,255,255,.16);
  --in:#efe9f1; --out:#6f5a9c;
  --shadow:0 2px 10px rgba(111,90,156,.08);
  --shadow-lg:0 6px 16px rgba(142,94,156,.18);
  --r:12px;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#15111a; --card:#1d1824; --text:#ece6f2; --sub:#9d92ab; --border:#2f2739;
    --accent:#b39ddb; --accent2:#c4868f; --hot:#f472b6; --soft:#241d2d;
    --ok:#3fb950; --err:#f85149; --warn:#d29922;
    --ok-bg:#152a1c; --err-bg:#2c1719; --warn-bg:#2c2313; --hot-bg:#2d1a26;
    --side:linear-gradient(185deg,#3a2f4a 0%,#4a3a55 48%,#5d4550 100%);
    --side-tx:rgba(255,255,255,.72); --side-on:rgba(255,255,255,.12);
    --in:#241d2d; --out:#7e63b3;
    --shadow:0 2px 10px rgba(0,0,0,.35); --shadow-lg:0 6px 16px rgba(0,0,0,.45);
  }
}
*{box-sizing:border-box}
/* min-height chứ KHÔNG phải height: `height:100%` giới hạn khung chứa của
   position:sticky đúng 1 màn hình, cuộn quá đó là menu trái hết chỗ bám và trôi
   theo. min-height cho body cao bằng nội dung -> sidebar bám được suốt trang. */
html,body{min-height:100%}
body{
  margin:0; display:flex; background:var(--bg); color:var(--text); line-height:1.45;
  font-family:-apple-system,"Segoe UI",Roboto,system-ui,sans-serif; font-size:14px;
}
a{color:var(--accent)}

/* ---------- sidebar ---------- */
.side{
  flex:0 0 236px; width:236px; background:var(--side); color:var(--side-tx);
  /* align-self:flex-start là BẮT BUỘC: mặc định flex item bị kéo giãn (stretch)
     cao bằng cả body, mà đã cao bằng khung chứa thì sticky không còn khoảng nào
     để bám -> vẫn trôi. Cố định 100vh rồi tự cuộn bên trong nếu menu dài. */
  position:sticky; top:0; align-self:flex-start; height:100vh; overflow-y:auto;
  display:flex; flex-direction:column;
  padding:16px 12px; box-shadow:2px 0 12px rgba(111,90,156,.18);
}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:#fff;
  padding:6px 8px 16px}
.logo{width:32px;height:32px;border-radius:10px;background:#fff;color:var(--accent);
  display:grid;place-items:center;font-weight:800;font-size:13px;
  box-shadow:0 3px 10px rgba(80,50,100,.18)}
.bname{font-weight:700;font-size:15px}
.nav{display:flex;flex-direction:column;gap:2px}
.nav-item{
  display:flex;align-items:center;gap:11px;padding:9px 10px;border-radius:9px;
  color:var(--side-tx);text-decoration:none;font-size:14px;font-weight:500;
}
.nav-item:hover{background:var(--side-on);color:#fff}
.nav-item.on{background:#fff;color:var(--accent);font-weight:650;
  box-shadow:0 3px 10px rgba(80,50,100,.18)}
.ico{width:19px;height:19px;flex:0 0 auto}
/* tên nhóm menu (CRM / Bot Pancake) */
.nav-group{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--side-tx);opacity:.55;padding:12px 10px 4px}
/* vạch ngăn thay tên nhóm — dùng cho nhóm KHÔNG TÊN ở cuối menu (Quản trị) */
.nav-sep{height:1px;background:rgba(255,255,255,.16);margin:12px 10px 8px}
/* ---------- khối bộ phận xổ/thu trong menu trái (Sale, CSKH — kiểu Kallet) ---------- */
.mobile-only{display:none}          /* link phẳng dự phòng — chỉ hiện màn hẹp */
.dept>summary{list-style:none;cursor:pointer;user-select:none}
.dept>summary::-webkit-details-marker{display:none}
.dept>summary .chev{margin-left:auto;font-size:11px;opacity:.75;
  transition:transform .15s}
.dept[open]>summary .chev{transform:rotate(90deg)}
.nav-kids{padding:2px 0 6px;display:flex;flex-direction:column;gap:1px}
.sm-group{font-size:10px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--side-tx);opacity:.5;padding:8px 10px 3px 40px}
.sm-link,.sm-child{display:flex;align-items:center;gap:8px;
  padding:6px 10px 6px 40px;border-radius:8px;color:var(--side-tx);
  text-decoration:none;font-size:13px}
.sm-child{padding-left:52px}
.sm-link:hover,.sm-child:hover{background:var(--side-on);color:#fff}
/* chấm màu trong khối menu: đè .dot toàn cục (chấm live có animation) */
.sm-link .dot,.sm-child .dot{width:8px;height:8px;border-radius:50%;
  flex:0 0 auto;box-shadow:none;animation:none}
.sm-link.star{color:#ffd54f}
/* mục XỔ XUỐNG trong menu (Sale · Chăm sóc khách hàng — kiểu Kallet):
   summary trông như nav-item, con thụt vào có chấm màu + số đếm */
.nav-dept>summary{display:flex;align-items:center;gap:10px;padding:9px 10px;
  border-radius:10px;color:var(--side-tx);font-size:14px;font-weight:500;
  cursor:pointer;list-style:none;user-select:none}
.nav-dept>summary::-webkit-details-marker{display:none}
.nav-dept>summary:hover{background:var(--side-on);color:#fff}
/* đang XỔ: cả khối nhận nền tối mờ + viền nhẹ để nổi khỏi phần menu còn lại
   (phủ cả 2 khối: Sale = .nav-dept, CSKH = .dept; :not(.on) để summary đang
   active giữ nền trắng chữ tím của .nav-item.on, không bị chữ trắng đè) */
.nav-dept[open],.dept[open]{background:rgba(0,0,0,.16);
  border:1px solid rgba(255,255,255,.08);border-radius:12px;
  padding:2px 4px 8px;margin:2px 0}
.nav-dept[open]>summary:not(.on),.dept[open]>summary:not(.on){
  color:#fff;font-weight:650}
.nav-dept[open]>summary:hover,.dept[open]>summary:hover{background:var(--side-on)}
.nd-chev{margin-left:auto;font-size:10px;opacity:.7;transition:transform .18s}
.nav-dept:not([open]) .nd-chev{transform:rotate(-90deg)}
.nd-group{font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--side-tx);opacity:.5;padding:8px 10px 3px 24px}
.nd-link{display:flex;align-items:center;gap:8px;padding:6px 10px 6px 24px;
  border-radius:8px;color:var(--side-tx);text-decoration:none;font-size:13px}
.nd-link:hover{background:var(--side-on);color:#fff}
.nd-link.on{background:#fff;color:var(--accent);font-weight:650}
.nd-link>span:not(.nd-dot):not(.nd-count){overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.nd-dot{width:8px;height:8px;border-radius:50%;flex:none}
.nd-count{margin-left:auto;font-size:11px;background:var(--side-on);
  border-radius:12px;padding:1px 8px;min-width:22px;text-align:center;flex:none}
.nd-link.on .nd-count{background:color-mix(in srgb,var(--accent) 14%,transparent)}
/* Kanban khung (màn CRM tạm): cột giai đoạn + thẻ lead */
.kanban{display:flex;gap:10px;overflow-x:auto;padding:4px 0}
.kcol{min-width:150px;flex:1;background:var(--soft);border:1px solid var(--border);
  border-radius:10px;padding:9px}
.kcol.closed{opacity:.65}
.kcol h4{font-size:12px;color:var(--sub);display:flex;justify-content:space-between;
  gap:6px;margin-bottom:6px}
.kcount{background:var(--card);border:1px solid var(--border);border-radius:99px;
  padding:0 7px;font-size:11px;color:var(--text)}
.kcard{background:var(--card);border:1px solid var(--border);border-radius:8px;
  padding:6px 8px;font-size:12.5px;margin-top:6px;box-shadow:var(--shadow)}
/* ---------- Trang chủ (màn 2 — /crm/trang-chu) ----------
   Bố cục theo giao diện Kallet: tiêu đề + lời chào → thanh chọn kỳ → 3 ô lớn
   → 2 thẻ đội (Sale / CSKH) → doanh thu → biểu đồ cột → xếp hạng. */
.hm-h1{font-size:21px;font-weight:900;color:var(--accent);margin:0 0 4px;
  display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.hm-h1 .dt{font-size:13px;font-weight:600;color:var(--sub)}
.hm-sub{color:var(--sub);font-size:12.5px;margin-bottom:16px}
.panel{background:var(--card);border:1px solid var(--border);border-radius:14px;
  padding:14px 16px;margin-bottom:14px;box-shadow:var(--shadow)}
.panel-t{font-size:14px;font-weight:800;color:var(--text);margin-bottom:11px;
  display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.panel-t small{font-weight:400;color:var(--sub);font-size:12px}
/* thanh chọn kỳ */
.rf-quick{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.rf-lb{display:inline-flex;align-items:center;gap:6px;font-size:13px;
  font-weight:600;color:var(--sub)}
.rf-seg{display:flex;gap:6px;background:var(--soft);padding:4px;border-radius:12px;
  flex-wrap:wrap}
.rf-seg a{padding:6px 13px;border-radius:9px;font-size:13px;font-weight:600;
  text-decoration:none;color:var(--sub);white-space:nowrap}
.rf-seg a.on{background:var(--card);color:var(--accent);box-shadow:var(--shadow)}
.rf-seg a:hover:not(.on){color:var(--accent)}
.rf-row{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin:0}
.rf-field{display:flex;flex-direction:column;gap:5px}
.rf-ov{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  color:var(--sub)}
.rf-field input,.rf-field select{height:40px;border:1.5px solid var(--border);
  border-radius:11px;background:var(--card);color:var(--text);font-size:13px;
  padding:0 11px;font-family:inherit}
.rf-go{height:40px;border:none;border-radius:11px;padding:0 18px;font-size:13px;
  font-weight:700;cursor:pointer;color:#fff;font-family:inherit;
  background:linear-gradient(135deg,var(--accent),var(--hot))}
/* 3 ô lớn */
.kpi3{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));
  gap:13px;margin-bottom:16px}
.bigkpi{display:flex;align-items:center;gap:13px;background:var(--card);
  border:1px solid var(--border);border-radius:16px;padding:15px 17px;
  text-decoration:none;color:inherit;box-shadow:var(--shadow)}
.bigkpi:hover{box-shadow:var(--shadow-lg)}
.bk-ic{width:50px;height:50px;border-radius:14px;display:flex;align-items:center;
  justify-content:center;font-size:23px;flex:0 0 50px;background:var(--soft)}
.bk-n{font-size:29px;font-weight:900;line-height:1;color:var(--text)}
.bk-l{font-size:12.5px;color:var(--sub);margin-top:4px}
.bigkpi.warn .bk-ic{background:var(--warn-bg)} .bigkpi.warn .bk-n{color:var(--warn)}
.bigkpi.err  .bk-ic{background:var(--err-bg)}  .bigkpi.err  .bk-n{color:var(--err)}
.bigkpi.info .bk-ic{background:var(--hot-bg)}  .bigkpi.info .bk-n{color:var(--accent)}
.bigkpi.ok   .bk-ic{background:var(--ok-bg)}   .bigkpi.ok   .bk-n{color:var(--ok)}
/* thẻ đội — KHÔNG dùng lại tên .grid2 (đã là lưới 2 cột của form ở cuối file) */
.hm-2col{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));
  gap:16px;margin-bottom:14px}
.teamcard{background:var(--card);border:1px solid var(--border);border-radius:18px;
  padding:17px;box-shadow:var(--shadow)}
.tc-head{display:flex;align-items:center;gap:11px;margin-bottom:13px}
.tc-ic{width:39px;height:39px;border-radius:12px;display:flex;align-items:center;
  justify-content:center;font-size:19px;color:#fff;flex:0 0 39px}
.tc-ic.sale{background:linear-gradient(135deg,var(--hot),var(--accent2))}
.tc-ic.cskh{background:linear-gradient(135deg,#3b82f6,#60a5fa)}
.tc-head b{font-size:16px;font-weight:900;color:var(--text)}
.tc-link{margin-left:auto;font-size:12.5px;font-weight:700;text-decoration:none}
.kpis2{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}
.kpi2{background:var(--soft);border:1px solid var(--border);border-radius:12px;
  padding:13px 14px;text-decoration:none;color:inherit;display:block}
.kpi2:hover{border-color:var(--hot)}
.kpi2 .n{font-size:24px;font-weight:900;line-height:1;color:var(--text)}
.kpi2 .l{font-size:11.5px;color:var(--sub);margin-top:5px}
.kpi2 .n.pink{color:var(--hot)} .kpi2 .n.blue{color:#2563eb}
.kpi2 .n.green{color:var(--ok)} .kpi2 .n.red{color:var(--err)}
.kpi2 .n.warn{color:var(--warn)}
.revbar{display:flex;align-items:center;justify-content:space-between;gap:10px;
  margin-top:11px;padding:13px 15px;border-radius:12px;text-decoration:none;
  flex-wrap:wrap}
.revbar span{font-size:13px;font-weight:600}
.revbar b{font-size:18px;font-weight:900;display:flex;align-items:center;gap:7px}
.revbar b small{font-size:11.5px;font-weight:600;opacity:.75}
.revbar.sale{background:var(--hot-bg)}
.revbar.sale span{color:var(--accent)} .revbar.sale b{color:var(--hot)}
.revbar.cskh{background:color-mix(in srgb,#3b82f6 12%,transparent)}
.revbar.cskh span{color:#2563eb} .revbar.cskh b{color:#2563eb}
/* biểu đồ cột doanh thu — SVG dựng thẳng, không thư viện ngoài */
/* co theo bề ngang nhưng GIỮ tỉ lệ (viewBox 900x190) — kéo giãn một chiều là
   chữ ngày tháng méo hết */
.hm-chart{width:100%;height:auto;aspect-ratio:900/190;display:block}
.hm-chart .gl{stroke:var(--border)}
.hm-chart .bs{fill:var(--hot)} .hm-chart .bc{fill:#3b82f6}
.hm-chart text{fill:var(--sub);font-size:10px}
.hm-legend{display:flex;gap:18px;flex-wrap:wrap;margin-top:10px;font-size:12px;
  color:var(--sub)}
.hm-legend span{display:flex;align-items:center;gap:6px}
.hm-legend i{width:12px;height:12px;border-radius:3px;display:inline-block}
/* xếp hạng */
.rankwrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
  gap:16px}
.rtbl{width:100%;border-collapse:collapse;font-size:12.5px}
.rtbl th{text-align:left;color:var(--accent);border-bottom:2px solid var(--border);
  padding:7px 8px;font-size:11px;text-transform:uppercase;letter-spacing:.03em}
.rtbl td{border-bottom:1px solid var(--border);padding:7px 8px;color:var(--text)}
.rtbl tr:hover td{background:var(--soft)}
.rtbl a{font-weight:800;text-decoration:none}
.rtbl .num{text-align:right;font-variant-numeric:tabular-nums}
/* ---------- Bảng chăm sóc theo mốc (màn 11 — /crm/pipeline) ----------
   Bố cục theo giao diện Kallet: dải chỉ số → thanh lọc → quy tắc → bảng cột
   + khung làm việc bên phải. Màu lấy hết từ biến gốc nên tự theo sáng/tối;
   màu riêng của TỪNG CỘT truyền vào bằng biến --c (xem mau_giai_doan). */
.lp-kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));
  gap:10px;margin-bottom:12px}
.lp-kpi a,.lp-kpi-flat{background:var(--card);border-radius:14px;padding:12px 16px;
  border:1.5px solid transparent;box-shadow:var(--shadow);text-decoration:none;
  display:block}
.lp-kpi a:hover{border-color:color-mix(in srgb,var(--hot) 40%,transparent)}
.lp-kpi a.on{border-color:var(--hot);background:var(--hot-bg)}
.lp-kpi b{font-size:22px;display:block;color:var(--text);line-height:1.2}
.lp-kpi span{font-size:12.5px;color:var(--sub)}
.lp-fbar{background:var(--card);border-radius:14px;padding:11px 13px;
  margin-bottom:12px;box-shadow:var(--shadow)}
.lp-frow{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0}
.lp-flbl{font-size:12px;color:var(--sub);font-weight:700}
.lp-sel{height:34px;border:1.5px solid var(--border);border-radius:9px;
  background:var(--soft);color:var(--text);font-size:12.5px;padding:0 8px;
  max-width:190px}
.lp-search{display:flex;align-items:center;gap:6px;border:1.5px solid var(--border);
  border-radius:9px;background:var(--soft);padding:0 10px;height:34px;color:var(--sub)}
.lp-search input{border:none;background:none;outline:none;font-size:12.5px;
  width:184px;color:var(--text)}
.lp-chip{border:1.5px solid var(--border);background:var(--soft);color:var(--text);
  border-radius:999px;padding:5px 13px;font-size:12.5px;font-weight:600;
  cursor:pointer;white-space:nowrap;text-decoration:none;display:inline-flex;
  align-items:center;gap:5px}
.lp-chip:hover{border-color:var(--hot)}
.lp-chip.on{background:var(--hot);border-color:var(--hot);color:#fff}
.lp-toggle{display:flex;border:1.5px solid var(--border);border-radius:10px;
  overflow:hidden}
.lp-toggle a{display:flex;align-items:center;gap:5px;padding:7px 13px;
  font-size:12.5px;font-weight:600;color:var(--sub);text-decoration:none;
  background:var(--soft)}
.lp-toggle a.on{background:linear-gradient(135deg,var(--accent),var(--hot));color:#fff}
/* Lọc theo thời điểm tạo — <details> nên không cần JS */
.lp-ct{position:relative}
.lp-ct>summary{display:flex;align-items:center;gap:6px;height:34px;
  border:1.5px solid var(--border);border-radius:9px;background:var(--soft);
  color:var(--text);font-size:12.5px;padding:0 11px;cursor:pointer;
  list-style:none;user-select:none}
.lp-ct>summary::-webkit-details-marker{display:none}
.lp-ct[open]>summary{border-color:var(--accent)}
.lp-ctpop{position:absolute;z-index:60;top:40px;left:0;width:min(420px,86vw);
  background:var(--card);border:1px solid var(--border);border-radius:14px;
  box-shadow:var(--shadow-lg);padding:13px}
.lp-ctpop-h{font-size:13px;font-weight:700;color:var(--text);margin-bottom:9px}
.lp-ctpop-h span{font-weight:400;color:var(--sub)}
.lp-ctpre{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.lp-ctrange{display:flex;gap:10px}
.lp-ctrange label{flex:1;font-size:12px;color:var(--sub);display:flex;
  flex-direction:column;gap:4px}
.lp-ctrange input{border:1.5px solid var(--border);border-radius:8px;padding:6px 8px;
  font-size:12.5px;background:var(--card);color:var(--text)}
.lp-ctpop-f{display:flex;align-items:center;gap:8px;margin-top:11px;
  border-top:1px solid var(--border);padding-top:10px}
.lp-btn{display:inline-flex;align-items:center;gap:6px;border:none;border-radius:9px;
  padding:7px 13px;font-size:12.5px;font-weight:600;cursor:pointer;
  background:linear-gradient(135deg,var(--accent),var(--hot));color:#fff;
  text-decoration:none}
.lp-btn.ghost{background:var(--soft);color:var(--text);
  border:1.5px solid var(--border)}
.lp-btn.danger{background:var(--err-bg);color:var(--err);
  border:1.5px solid color-mix(in srgb,var(--err) 30%,transparent)}
/* Quy tắc tự động */
.lp-rules{background:var(--card);border-radius:14px;margin-bottom:12px;
  box-shadow:var(--shadow);overflow:hidden}
.lp-rules>summary{display:flex;align-items:center;gap:8px;padding:11px 14px;
  font-size:13px;color:var(--text);cursor:pointer;list-style:none;user-select:none}
.lp-rules>summary::-webkit-details-marker{display:none}
.lp-rules-b{padding:0 16px 14px;font-size:12.5px;color:var(--text)}
.lp-rules-b ul{margin:0 0 10px;padding-left:18px;line-height:1.9}
.lp-rules-n{background:var(--soft);border-radius:10px;padding:9px 12px}
/* Bảng cột */
.lp-board{display:flex;gap:11px;overflow-x:auto;padding-bottom:12px;
  align-items:flex-start}
.lp-col{flex:0 0 268px;background:var(--soft);border:1px solid var(--border);
  border-radius:14px;display:flex;flex-direction:column;
  max-height:calc(100vh - 250px)}
/* Xem 1 cột: VẪN là bảng cột, chỉ rộng hơn cho dễ đọc + chừa chỗ khung làm việc */
.lp-board.one{overflow-x:visible}
.lp-board.one .lp-col{flex:0 0 340px;max-width:340px}
.lp-col.closed{opacity:.8}
.lp-col-h{display:flex;align-items:center;gap:7px;padding:10px 12px;
  border-bottom:1px solid var(--border);color:var(--c,var(--accent))}
.lp-col-t{font-size:13px;font-weight:700;color:var(--text);text-decoration:none;flex:1}
.lp-col-t:hover{color:var(--c,var(--accent))}
.lp-col-n{background:var(--c,var(--accent));color:#fff;border-radius:999px;
  min-width:22px;text-align:center;font-size:11.5px;font-weight:700;padding:2px 7px}
.lp-col-b{padding:8px;overflow-y:auto;flex:1;min-height:80px}
.lp-col-e{font-size:12px;color:var(--sub);text-align:center;padding:18px 8px;
  border:1.5px dashed var(--border);border-radius:10px}
.lp-band{display:flex;align-items:center;gap:6px;font-size:11px;font-weight:700;
  color:var(--sub);text-transform:uppercase;letter-spacing:.03em;margin:8px 2px 5px}
.lp-band span{background:var(--soft);color:var(--accent);border-radius:999px;
  padding:1px 7px;font-size:10.5px;border:1px solid var(--border)}
/* Thẻ khách: cả thẻ là 1 liên kết, nút Pancake nổi lên góc phải */
.lp-card{position:relative;background:var(--card);border:1px solid var(--border);
  border-radius:11px;margin-bottom:7px;box-shadow:var(--shadow)}
.lp-card:hover{border-color:var(--hot)}
.lp-card.od{border-left:3px solid var(--err)}
.lp-card.won{border-left:3px solid var(--ok)}
.lp-card.on{border-color:var(--hot);background:var(--hot-bg);
  box-shadow:0 0 0 2px color-mix(in srgb,var(--hot) 20%,transparent)}
.lp-card-lk{display:block;padding:9px 30px 9px 10px;text-decoration:none;
  color:inherit}
.lp-c-top{display:flex;align-items:center;gap:5px}
.lp-c-name{font-size:13px;font-weight:600;color:var(--text);flex:1;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.lp-c-chat{position:absolute;top:7px;right:7px;color:var(--sub);padding:2px;
  line-height:1;text-decoration:none;font-size:13px}
.lp-c-chat:hover{color:var(--hot)}
.lp-c-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:5px;font-size:11.5px;
  color:var(--sub)}
.lp-c-meta span{display:inline-flex;align-items:center;gap:3px}
.lp-c-meta .od{color:var(--err);font-weight:600}
/* Nhãn nhiệt độ + trạng thái */
.lp-pill{display:inline-flex;align-items:center;gap:4px;border-radius:999px;
  padding:2px 8px;font-size:11px;font-weight:700}
.lp-hot{background:var(--hot-bg);color:var(--hot)}
.lp-warm{background:var(--warn-bg);color:var(--warn)}
.lp-cold{background:var(--soft);color:var(--sub)}
.lp-ok{background:var(--ok-bg);color:var(--ok)}
/* Khung làm việc bên phải — chi tiết khách đang chọn */
.lp-pane{flex:1 1 auto;min-width:0;background:var(--card);
  border:1px solid var(--border);border-radius:14px;
  max-height:calc(100vh - 250px);overflow-y:auto;box-shadow:var(--shadow)}
.lp-pane-empty{padding:56px 28px;text-align:center;color:var(--sub)}
.lp-pane-empty h3{margin:12px 0 6px;font-size:15px;color:var(--text)}
.lp-pane-empty p{margin:0 auto;font-size:13px;max-width:380px;line-height:1.75}
.lp-dw-h{position:sticky;top:0;background:var(--card);
  border-bottom:1px solid var(--border);padding:15px 20px;z-index:2;
  border-radius:14px 14px 0 0}
.lp-dw-h1{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.lp-dw-h1 h2{margin:0;font-size:17px;color:var(--text)}
.lp-dw-h2{display:flex;flex-wrap:wrap;gap:14px;margin-top:8px;font-size:12.5px;
  color:var(--sub)}
.lp-dw-s{padding:15px 20px;border-bottom:1px solid var(--border)}
.lp-dw-lbl{font-size:11.5px;font-weight:700;color:var(--sub);text-transform:uppercase;
  letter-spacing:.04em;margin-bottom:9px}
.lp-steps{display:flex;flex-wrap:wrap;gap:6px}
.lp-step{display:inline-flex;align-items:center;gap:5px;
  border:1.5px solid var(--border);background:var(--card);color:var(--text);
  border-radius:999px;padding:6px 12px;font-size:12px;font-weight:600;cursor:pointer}
.lp-step:hover{border-color:var(--hot)}
.lp-step.on{background:linear-gradient(135deg,var(--accent),var(--hot));
  border-color:transparent;color:#fff;cursor:default}
.lp-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:9px}
.lp-facts div{background:var(--soft);border:1px solid var(--border);
  border-radius:10px;padding:8px 11px}
.lp-facts span{display:block;font-size:11px;color:var(--sub);margin-bottom:2px}
.lp-facts b{font-size:13px;color:var(--text)}
.lp-inl{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:0}
.lp-inl input,.lp-inl select,.lp-dw-s textarea{border:1.5px solid var(--border);
  border-radius:9px;padding:7px 9px;font-size:12.5px;font-family:inherit;
  background:var(--card);color:var(--text)}
.lp-dw-s textarea{width:100%;box-sizing:border-box;resize:vertical}
.lp-mut{color:var(--sub);font-size:12px}
.lp-log{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
.lp-log li{display:flex;gap:11px;font-size:12.5px;color:var(--text);position:relative;
  padding-left:14px}
.lp-log li:before{content:'';position:absolute;left:0;top:6px;width:7px;height:7px;
  border-radius:50%;background:var(--hot)}
.lp-log time{color:var(--sub);flex:0 0 96px;font-size:12px}
/* Chế độ Bảng (xem=bang) — mỗi giai đoạn một khối xổ/thu */
.lp-tbl{display:flex;flex-direction:column;gap:9px}
.lp-acc{background:var(--card);border-radius:14px;box-shadow:var(--shadow);
  overflow:hidden}
.lp-acc>summary{display:flex;align-items:center;gap:9px;padding:12px 15px;
  cursor:pointer;list-style:none;color:var(--c,var(--accent));user-select:none}
.lp-acc>summary::-webkit-details-marker{display:none}
.lp-acc-t{font-size:13.5px;font-weight:700;color:var(--text);flex:1}
.lp-acc-n{font-size:12px;color:var(--sub)}
.lp-th,.lp-tr{display:grid;grid-template-columns:2.1fr 1.2fr 1.4fr 1.5fr 1fr;
  gap:10px;padding:9px 15px;align-items:center}
.lp-th{font-size:11.5px;font-weight:700;color:var(--sub);text-transform:uppercase;
  letter-spacing:.03em;background:var(--soft);border-top:1px solid var(--border)}
.lp-tr{border-top:1px solid var(--border);font-size:12.5px}
.lp-tr:hover{background:var(--soft)}
.lp-empty{background:var(--card);border-radius:14px;padding:44px 24px;
  text-align:center;color:var(--sub);box-shadow:var(--shadow)}
@media(max-width:1180px){
  .lp-board.one{flex-wrap:wrap}
  .lp-board.one .lp-col{flex:1 1 100%;max-width:none}
  .lp-pane{flex:1 1 100%;max-height:none}
  .lp-th,.lp-tr{grid-template-columns:1.6fr 1fr 1.4fr}
  .lp-th span:nth-child(n+4),.lp-tr>*:nth-child(n+4){display:none}
}
/* khối người đăng nhập + nút đăng xuất (A2) — góc phải topbar.
   .page-actions đã mang margin-left:auto (đẩy cả cụm về mép phải); trang nào
   không có actions thì .top-user tự đẩy mình bằng auto margin của chính nó. */
.top-user{margin-left:auto;display:flex;align-items:center;gap:10px;min-width:0}
.page-actions+.top-user{margin-left:0}
.su-info{min-width:0;max-width:200px;text-align:right}
.su-name{color:var(--text);font-size:12.5px;font-weight:600;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.su-role{color:var(--sub);font-size:11px}
.su-form{margin:0}
.su-out{border:1px solid var(--border);background:transparent;color:var(--sub);
  font-size:11px;padding:4px 8px;border-radius:8px;cursor:pointer;white-space:nowrap}
.su-out:hover{border-color:var(--err);color:var(--err);background:var(--err-bg)}
/* chuông thông báo (màn 3) — huy hiệu số chưa đọc đè góc trên phải */
.bell{position:relative;display:inline-flex;align-items:center;justify-content:center;
  width:32px;height:32px;border-radius:9px;color:var(--sub);border:1px solid transparent}
.bell:hover{color:var(--text);border-color:var(--border);background:var(--card)}
.bell svg{width:17px;height:17px}
.bell-dot{position:absolute;top:-1px;right:-1px;min-width:16px;height:16px;padding:0 4px;
  border-radius:9px;background:var(--err);color:#fff;font-size:10px;font-weight:700;
  line-height:16px;text-align:center}

/* ---------- khung phải ---------- */
.main{flex:1;min-width:0;display:flex;flex-direction:column;min-height:100vh}
/* Màn "full" (Tin nhắn): main phải bị KHOÁ đúng 100vh (không phải min-height)
   để .inbox/.pane/.thread bên trong có khung chiều cao cố định mà co/cuộn theo
   — nếu không thì main tự giãn cao theo tổng số tin nhắn, kéo cả trang cuộn
   theo kiểu thường (danh sách hội thoại trôi mất, ô soạn tin bị đẩy khuất). */
.main.full{height:100vh;overflow:hidden}
/* Thanh trên + tab + nội dung: nền chạy hết bề ngang, còn CHỮ thì căn giữa theo
   cùng một khung 1280px — trước đây chỉ .content bị giới hạn bề rộng mà không
   có margin auto nên cả trang dồn về mép trái khi màn hình rộng. */
.topbar{
  position:sticky;top:0;z-index:6;background:var(--card);
  border-bottom:1px solid var(--border);
  padding:14px max(26px, calc((100% - 1280px) / 2));
  display:flex;align-items:center;gap:16px;flex-wrap:wrap;
}
.page-head{min-width:0}
.topbar h1{font-size:18px;margin:0;font-weight:650}
.page-sub{color:var(--sub);font-size:12.5px;margin-top:2px}
.page-actions{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.content{padding:22px 26px 40px;width:100%;max-width:1280px;margin-inline:auto}
.content.full{padding:0;max-width:none;margin-inline:0;flex:1;min-height:0;display:flex}

/* ---------- tab con ---------- */
.tabs{display:flex;gap:6px;background:var(--card);
  padding:10px max(26px, calc((100% - 1280px) / 2)) 0;
  border-bottom:1px solid var(--border);flex-wrap:wrap}
.tab{padding:8px 14px;border-radius:8px 8px 0 0;text-decoration:none;
  color:var(--sub);font-size:13.5px;font-weight:500;border-bottom:2px solid transparent;
  margin-bottom:-1px}
.tab:hover{color:var(--text)}
.tab.on{color:var(--accent);border-bottom-color:var(--accent);font-weight:650}

/* ---------- thành phần chung ---------- */
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);
  padding:16px;box-shadow:var(--shadow)}
.intro{color:var(--sub);font-size:13px;margin:0 0 14px}
.grp{font-size:12px;margin:22px 0 8px;color:var(--sub);text-transform:uppercase;
  letter-spacing:.04em;font-weight:650}
.count{background:var(--border);color:var(--text);border-radius:10px;padding:1px 8px;
  font-size:11.5px;margin-left:4px;text-transform:none;letter-spacing:0}
.empty{background:var(--card);border:1px dashed var(--border);border-radius:12px;
  padding:24px;color:var(--sub);text-align:center}
.flash{padding:9px 12px;border-radius:9px;font-size:13px;margin-bottom:14px}
.flash.ok{background:var(--ok-bg);color:var(--ok);
  border:1px solid color-mix(in srgb,var(--ok) 25%,transparent)}
.flash.err{background:var(--err-bg);color:var(--err);
  border:1px solid color-mix(in srgb,var(--err) 25%,transparent)}
.flash.warn{background:var(--warn-bg);color:var(--warn);
  border:1px solid color-mix(in srgb,var(--warn) 25%,transparent)}
.note{color:var(--sub);font-size:12px;margin:10px 0 0}
/* Công tắc gạt ở màn Cài đặt: ô checkbox thật (form gửi được) + phần nhìn là
   hai khối span, nên không cần JS nào cả. */
.sw{display:inline-flex;align-items:center;gap:8px;cursor:pointer;user-select:none}
.sw input{position:absolute;opacity:0;width:0;height:0}
.sw>span{width:38px;height:21px;border-radius:20px;background:var(--border);
  position:relative;transition:background .15s}
.sw>span::after{content:"";position:absolute;top:2px;left:2px;width:17px;height:17px;
  border-radius:50%;background:#fff;transition:transform .15s}
.sw input:checked+span{background:var(--ok)}
.sw input:checked+span::after{transform:translateX(17px)}
.sw input:focus-visible+span{outline:2px solid var(--accent);outline-offset:2px}
.sw b{font-size:12px;color:var(--sub);font-weight:600}
/* Bảng số liệu (màn Nguồn quảng cáo): cột số canh phải cho dễ so hàng dọc */
td.num,th.num{text-align:right;white-space:nowrap}
/* Thanh tỷ lệ trong phễu quảng cáo */
.bar{background:var(--bg);border-radius:6px;height:8px;min-width:80px;overflow:hidden}
.bar>span{display:block;height:100%;background:var(--accent);border-radius:6px}
code{font-family:ui-monospace,Consolas,monospace;font-size:12px;background:var(--bg);
  padding:1px 5px;border-radius:5px}
.btn{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);
  background:var(--card);color:var(--text);border-radius:8px;padding:7px 13px;
  text-decoration:none;font-size:13px;font-weight:550;cursor:pointer}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.primary{background:linear-gradient(135deg,var(--accent),var(--accent2));
  border-color:transparent;color:#fff;box-shadow:0 3px 10px rgba(80,50,100,.18)}
.btn.primary:hover{filter:brightness(1.06);color:#fff}
.btn:hover{border-color:var(--accent);color:var(--accent);background:var(--soft)}
select,.inp{border:1px solid var(--border);background:var(--card);color:var(--text);
  border-radius:8px;padding:7px 10px;font:inherit;font-size:13px}
.live{display:inline-flex;align-items:center;gap:5px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok);
  box-shadow:0 0 0 0 rgba(22,163,74,.6);animation:pulse 1.8s infinite}
@keyframes pulse{
  0%{box-shadow:0 0 0 0 rgba(22,163,74,.5)}
  70%{box-shadow:0 0 0 6px rgba(22,163,74,0)}
  100%{box-shadow:0 0 0 0 rgba(22,163,74,0)}
}

/* ---------- form ---------- */
.form label{display:block;font-size:12.5px;color:var(--sub);margin-bottom:10px}
.form input,.form textarea,.form select{display:block;width:100%;margin-top:4px;
  padding:8px 10px;border:1px solid var(--border);border-radius:8px;font:inherit;
  font-size:14px;background:var(--bg);color:var(--text);resize:vertical}
.form input:focus,.form textarea:focus{outline:2px solid var(--soft);
  border-color:var(--accent)}
.grid2{display:flex;gap:12px;flex-wrap:wrap}
.grid2>label{flex:1 1 200px}
.form button{border:0;background:var(--accent);color:#fff;border-radius:8px;
  padding:9px 18px;font:inherit;font-weight:600;cursor:pointer}
.check{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--sub);
  margin-bottom:12px}
.check input{width:auto;margin:0}

/* ---------- danh sách dòng dữ liệu ---------- */
.list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.row{display:flex;gap:12px;align-items:flex-start;background:var(--card);
  border:1px solid var(--border);border-radius:12px;padding:12px 14px}
.step{flex:0 0 auto;min-width:28px;height:28px;border-radius:8px;background:var(--accent);
  color:#fff;font-weight:700;font-size:13px;display:grid;place-items:center}
.rbody{flex:1;min-width:0}
.rtext{font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}
.qa .q{font-weight:600;font-size:14px;overflow-wrap:anywhere}
.qa .a{font-size:14px;margin-top:2px;overflow-wrap:anywhere}
.rmeta{color:var(--sub);font-size:12px;margin-top:4px}
.del button{border:1px solid var(--border);background:transparent;color:var(--err);
  border-radius:8px;width:30px;height:30px;cursor:pointer;font-size:14px;line-height:1}
.del button:hover{border-color:var(--err)}

/* ---------- màn "Thử tin nhắn" ---------- */
.mono{font-size:13px}
.mono .lbl{color:var(--sub);font-size:12px;margin-top:8px}
.qline{font-family:ui-monospace,Consolas,monospace;font-size:12px;background:var(--bg);
  border:1px solid var(--border);border-radius:8px;padding:6px 9px;margin-bottom:6px;
  overflow-x:auto;white-space:nowrap}
.score{flex:0 0 auto;width:92px;text-align:right}
.snum{font-size:12px;color:var(--sub);font-family:ui-monospace,Consolas,monospace}
.sbar{display:block;height:5px;border-radius:3px;background:var(--border);
  margin-top:4px;overflow:hidden}
.sbar i{display:block;height:100%;border-radius:3px}
.answer{background:color-mix(in srgb,var(--accent) 10%,transparent);
  border-left:3px solid var(--accent);border-radius:8px;padding:12px 14px;
  font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}
details{margin-top:10px;font-size:13px;color:var(--sub)}
summary{cursor:pointer}
.prompt{background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:10px;margin-top:8px;font-size:12px;white-space:pre-wrap;overflow-x:auto;
  font-family:ui-monospace,Consolas,monospace;color:var(--text)}

/* ---------- bảng điều khiển ---------- */
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:var(--r);
  padding:14px 16px;box-shadow:var(--shadow)}
.stat.link:hover{border-color:var(--accent);box-shadow:var(--shadow-lg)}
.s-label{color:var(--sub);font-size:12px;font-weight:550}
/* Số to tô màu nhấn cho bảng điều khiển đỡ đơn điệu (tone ok/err/warn ghi đè) */
.s-value{font-size:24px;font-weight:700;margin-top:4px;letter-spacing:-.02em;
  color:var(--accent)}
.s-hint{color:var(--sub);font-size:11.5px;margin-top:3px}
.stat.ok .s-value{color:var(--ok)}
.stat.err .s-value{color:var(--err)}
.stat.warn .s-value{color:var(--warn)}
a.stat.link{position:relative;display:block;text-decoration:none;color:inherit;
  transition:border-color .15s}
a.stat.link:hover{border-color:var(--accent)}
a.stat.link::after{content:"›";position:absolute;top:12px;right:14px;
  color:var(--sub);font-size:18px;line-height:1}
a.stat.link:hover::after{color:var(--accent)}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.kv{display:flex;justify-content:space-between;gap:12px;padding:7px 0;
  border-bottom:1px solid var(--border);font-size:13px}
.kv:last-child{border-bottom:0}
.kv .k{color:var(--sub)}
.kv .v{text-align:right;overflow-wrap:anywhere}
.pill{font-size:11px;padding:2px 9px;border-radius:20px;border:1px solid var(--border);
  color:var(--sub)}
.pill.ok{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 40%,transparent)}
.pill.err{color:var(--err);border-color:color-mix(in srgb,var(--err) 40%,transparent)}
.pill.warn{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 40%,transparent)}
/* Form gọn nằm ngay trong ô bảng (khu Tích hợp: chọn rồi bấm Lưu từng dòng) */
.inline{display:flex;gap:6px;align-items:center}
.inline select{min-width:150px}
.err-txt{color:var(--err)}
.links{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}
/* Danh sách page hiện ngay trên bảng điều khiển: ẩn, bấm ô stat (#ds-page) mới mở */
.ds-page{display:none;margin-top:12px}
.ds-page:target{display:block}
.ds-page-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}
/* Dòng page trong danh sách: nhìn phát biết page nào đang chạy.
   BẬT = vạch xanh bên trái, chữ rõ. TẮT = xám mờ, avatar mất màu. */
.pgrow{border-left:3px solid transparent;transition:opacity .15s linear}
.pgrow.on{border-left-color:var(--ok)}
.pgrow.off{background:var(--bg);border-left-color:var(--border)}
.pgrow.off .avatar{filter:grayscale(1);opacity:.5}
.pgrow.off .name{color:var(--sub);font-weight:500}
.pgrow.off .rmeta{opacity:.7}
.pgrow.off .btn{opacity:.6}
/* Page ĐANG BẬT nhưng poller gọi lỗi (Pancake vô hiệu hoá, hết hạn gói, mất
   quyền...): vạch vàng + nền vàng nhạt để nổi hẳn giữa danh sách, kèm dòng
   .pgwarn ghi nguyên văn lời Pancake báo. */
.pgrow.warn{background:var(--warn-bg);border-left-color:var(--warn)}
.pgwarn{color:var(--warn);font-size:12px;font-weight:600;margin-top:4px;
  overflow-wrap:anywhere}
.pgstate{font-size:11px;font-weight:700;margin-left:6px;letter-spacing:.02em}
/* Nhãn quyền của token trên từng page (suy từ role_in_page Pancake trả về) */
.pgquyen{display:inline-block;font-size:11px;font-weight:650;line-height:1.7;
  padding:0 8px;border-radius:20px;white-space:nowrap}
.pgquyen.du{color:var(--ok);background:var(--ok-bg);
  border:1px solid color-mix(in srgb,var(--ok) 32%,transparent)}
.pgquyen.thieu{color:var(--warn);background:var(--warn-bg);
  border:1px solid color-mix(in srgb,var(--warn) 32%,transparent)}
.pgquyen.vo_hieu{color:var(--err);background:var(--err-bg);
  border:1px solid color-mix(in srgb,var(--err) 32%,transparent)}
/* Dòng tổng kết quyền ở đầu panel danh sách page */
.pgquyen-sum{display:flex;align-items:center;gap:8px;flex-wrap:wrap;
  font-size:12px;color:var(--sub);padding:10px 12px;margin-bottom:10px;
  background:var(--bg);border:1px solid var(--border);border-radius:10px}
.pgquyen-sum .btn{flex:0 0 auto;padding:4px 11px;font-size:12px}
.pgquyen-sum .btn:disabled{opacity:.6;cursor:default}
/* Mốc cập nhật + nút: luôn dính nhau, đẩy về mép phải khi còn chỗ */
.pgquyen-act{display:flex;align-items:center;gap:8px;margin-left:auto}
.pgquyen-luc{font-size:11.5px;color:var(--sub);white-space:nowrap}
.pgrow.on .pgstate{color:var(--ok)}
.pgrow.off .pgstate{color:var(--sub)}
.pgrow.warn .pgstate{color:var(--warn)}
/* Công tắc BẬT/TẮT page: BẬT = xanh đặc, TẮT = xám nhạt, LỖI = vàng cảnh báo */
.pgsw{border:1px solid var(--border);background:var(--card);color:var(--sub);
  border-radius:20px;padding:5px 12px;font-size:12px;font-weight:700;cursor:pointer;
  white-space:nowrap}
.pgsw.on{background:var(--ok);border-color:var(--ok);color:#fff}
.pgsw.off{background:var(--bg);border-color:var(--border);color:var(--sub)}
.pgsw.warn{background:var(--warn);border-color:var(--warn);color:#fff}
.pgsw:hover{opacity:.9}

/* ---------- thẻ page / hội thoại / khách ---------- */
.avatar{flex:0 0 auto;width:40px;height:40px;border-radius:50%;display:grid;
  place-items:center;color:#fff;font-weight:700;font-size:17px}
.avatar.sm{width:30px;height:30px;font-size:13px}
.info{min-width:0;flex:1}
.name{font-weight:600;color:var(--text);text-decoration:none;display:block;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
a.name:hover{color:var(--accent)}
.sub{color:var(--sub);font-size:12px;margin-top:1px}
.badges{margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;border:1px solid var(--border);
  color:var(--sub)}
.badge.platform{text-transform:capitalize;color:var(--accent)}
.unread{background:var(--err);color:#fff;border-radius:20px;font-size:11px;
  font-weight:700;padding:2px 8px;min-width:20px;text-align:center}
/* Nhãn cảm xúc tiêu cực do worker nền quét (app/workers/sentiment.py) */
.neg{background:var(--err-bg);color:var(--err);border-radius:20px;
  border:1px solid color-mix(in srgb,var(--err) 35%,transparent);
  font-size:11px;font-weight:700;padding:2px 8px}
/* Khung quản lý từ khoá tiêu cực (màn Cảm xúc) */
.kwadd{display:flex;gap:8px;padding:14px 14px 0}
.kwadd .inp{flex:1}
.kwlist{display:flex;flex-wrap:wrap;gap:6px;padding:12px 14px}
.kwchip{display:inline-flex;align-items:center;gap:6px;background:var(--soft);
  border:1px solid var(--border);border-radius:20px;padding:3px 6px 3px 11px;
  font-size:12.5px}
.kwchip button{border:0;background:transparent;color:var(--sub);cursor:pointer;
  font-size:15px;line-height:1;padding:0 4px;border-radius:50%}
.kwchip button:hover{background:var(--err);color:#fff}
/* Thu gọn danh sách từ khoá về ĐÚNG 1 hàng; bấm mới bung ra đầy đủ */
.kwbox{border-top:1px solid var(--border);margin-top:12px}
.kwbox summary{display:flex;align-items:center;gap:10px;cursor:pointer;
  padding:10px 14px;list-style:none}
.kwbox summary::-webkit-details-marker{display:none}
.kwbox summary:hover{background:var(--soft)}
.kwsum-n{flex:none;font-weight:600;font-size:13px}
/* Phần dư của dòng xem trước bị cắt bằng "…" thay vì xuống dòng */
.kwsum-preview{flex:1;min-width:0;color:var(--sub);font-size:12.5px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kwsum-more{flex:none;color:var(--accent);font-size:12.5px;font-weight:600}
.kwbox[open] .kwsum-preview{visibility:hidden}   /* mở ra rồi thì khỏi lặp lại */
.kwbox[open] .kwsum-more::after{content:" ▲"}
.kwbox:not([open]) .kwsum-more::after{content:" ▼"}
.kwbulk{border-top:1px solid var(--border);padding:12px 14px 14px}
.kwbulk-lbl{font-size:12.5px;color:var(--sub)}
.kwbulk textarea{width:100%;margin-top:6px;font-family:inherit;resize:vertical}
/* Dòng danh sách ở màn Cảm xúc: nội dung bên trái, nút mở hội thoại bên phải */
.link-row{display:flex;align-items:center;gap:12px}
.link-row .info{flex:1;min-width:0}
.link-row .btn{flex:none}
.tblwrap{overflow-x:auto}
.tbl td.nowrap{white-space:nowrap}
.tbl td.snip{color:var(--sub);max-width:420px;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
/* Ô nội dung ở Sổ cảnh báo: cho xuống dòng để <mark> không bị cắt mất */
.tbl td.snip-kw{color:var(--sub);max-width:460px;min-width:260px}
/* Cụm từ khoá làm bung cảnh báo, tô ngay trong câu */
mark.kw{background:var(--warn-bg);color:var(--text);font-weight:650;
  border-radius:4px;padding:0 3px;
  box-shadow:inset 0 -2px 0 color-mix(in srgb,var(--warn) 55%,transparent)}
/* Chip liệt kê từ khoá đã khớp ở cột riêng */
.kwhit{display:inline-block;font-size:11.5px;font-weight:650;line-height:1.8;
  padding:0 8px;margin:1px 3px 1px 0;border-radius:20px;color:var(--warn);
  background:var(--warn-bg);
  border:1px solid color-mix(in srgb,var(--warn) 35%,transparent)}
.snippet{color:var(--sub);font-size:13px;margin-top:2px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
/* Tên page trên thẻ hội thoại — CHỈ hiện ở hộp thư gộp (page_id=ALL) */
.cpage{color:var(--accent);font-size:11px;font-weight:600;margin-top:1px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:.9}
.time{color:var(--sub);font-size:12px;margin-left:auto;flex:0 0 auto;white-space:nowrap}
.card.link,.card.link-wrap{display:flex;gap:12px;align-items:center;
  transition:border-color .15s}
.card.link{text-decoration:none;color:inherit;align-items:flex-start}
.card.link:hover,.card.link-wrap:hover{border-color:var(--accent)}
.crow{display:flex;align-items:baseline;gap:8px}
/* thẻ (tag) của hội thoại, hiện ngay dưới tên để dễ so sánh */
.ctags{display:flex;flex-wrap:wrap;gap:4px;margin-top:3px}
/* Pill mang TÊN thẻ (không còn là "#175") -> phải chặn tên dài làm vỡ cột:
   cắt bằng ellipsis, tên đầy đủ vẫn xem được ở tooltip. */
.ctag{font-size:10px;font-weight:700;line-height:1.7;padding:0 6px;border-radius:9px;
  color:var(--tc);border:1px solid var(--tc);
  background:color-mix(in srgb,var(--tc) 13%,transparent);
  max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ---------- lưới danh sách page (tối đa 4 cột, giảm dần theo màn hình) ---------- */
.pages-grid{list-style:none;margin:0;padding:0;display:grid;gap:12px;
  grid-template-columns:repeat(4,minmax(0,1fr))}
.page-card{display:flex;flex-direction:column;gap:10px;padding:14px;
  transition:border-color .15s}
.page-card:hover{border-color:var(--accent)}
.pc-head{display:flex;gap:11px;align-items:center;min-width:0}
.page-card .info{min-width:0;flex:1}
.page-card .sub{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.page-card .badges{margin-top:0}
.page-card .btn{margin-top:auto;justify-content:center}
@media (max-width:1080px){.pages-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:800px){.pages-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:520px){.pages-grid{grid-template-columns:1fr}}

/* ---------- bảng ---------- */
.tbl{width:100%;border-collapse:collapse;background:var(--card);
  border:1px solid var(--border);border-radius:12px;overflow:hidden}
.tbl th,.tbl td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--border);
  font-size:13.5px;vertical-align:middle}
.tbl th{color:var(--sub);font-size:11.5px;text-transform:uppercase;letter-spacing:.03em;
  background:var(--bg);font-weight:650}
.tbl tr:last-child td{border-bottom:0}
.tbl tr:hover td{background:var(--soft)}
/* dải tiêu đề nhóm trong bảng nhân viên (màn Quản trị, xếp theo đội) */
.tbl tr.tgrp td{background:var(--soft);color:var(--accent);font-weight:700;
  font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;padding:6px 14px}
.twrap{overflow-x:auto;border-radius:12px}

/* ---------- màn tin nhắn 2 cột ---------- */
.inbox{display:flex;flex:1;min-height:0;width:100%}
.inbox-list{flex:0 0 330px;border-right:1px solid var(--border);background:var(--card);
  display:flex;flex-direction:column;min-height:0}
.inbox-list .lhead{padding:12px 16px;border-bottom:1px solid var(--border);
  color:var(--sub);font-size:12px;display:flex;align-items:center;gap:8px}
.lhint{color:var(--sub);font-size:11px;border:1px solid var(--border);
  border-radius:20px;padding:1px 8px}
.inbox-list .lbody{overflow-y:auto;padding:8px;flex:1;min-height:0}
/* Dòng trạng thái ở đáy cột trái khi "kéo xuống nạp thêm" (đang tải / hết kho) */
.feed-more{padding:12px 8px;text-align:center;color:var(--sub);font-size:12px}
.feed-more.done{opacity:.75}
/* Đã nạp thêm -> auto-refresh tạm dừng: chấm hết nhấp nháy để khỏi hiểu nhầm */
.live.paused .dot{background:var(--sub);box-shadow:none;animation:none}
.inbox-list .list{gap:4px}
.inbox-list .card{border-color:transparent;box-shadow:none;padding:9px 10px;
  border-radius:10px}
.inbox-list .card:hover{background:var(--bg)}
.inbox-list .card.on{background:var(--soft);border-color:var(--accent)}
/* ---------- thanh lọc theo thẻ (giống Pancake) ---------- */
.tagbar{display:flex;gap:6px;flex-wrap:wrap;padding:8px 12px;
  border-bottom:1px solid var(--border);background:var(--card);
  max-height:108px;overflow-y:auto}
.tchip{display:inline-flex;align-items:center;gap:6px;text-decoration:none;
  font-size:12px;font-weight:550;color:var(--text);border:1px solid var(--border);
  background:var(--card);border-radius:20px;padding:3px 10px;line-height:1.7}
.tchip:hover{border-color:var(--tc,var(--accent))}
.tchip .tdot{width:8px;height:8px;border-radius:50%;flex:0 0 auto;
  background:var(--tc,var(--sub))}
.tchip .tnum{color:var(--sub);font-size:11px;font-weight:600}
.tchip.on{border-color:var(--tc,var(--accent));
  background:color-mix(in srgb,var(--tc,var(--accent)) 15%,transparent)}
.tchip.on .tnum{color:var(--text)}
.tchip.all{color:var(--sub)}
.tchip.all.on{color:var(--accent);border-color:var(--accent);background:var(--soft)}
.pane{flex:1;min-width:0;display:flex;flex-direction:column;min-height:0}
.thread{flex:1;padding:18px 22px;display:flex;flex-direction:column;gap:4px;
  overflow-y:auto;min-height:0}
.msg{display:flex;flex-direction:column;max-width:min(72%,560px);margin-top:8px}
.msg.in{align-self:flex-start;align-items:flex-start}
.msg.out{align-self:flex-end;align-items:flex-end}
.bubble{padding:8px 12px;border-radius:16px;font-size:14px;white-space:pre-wrap;
  word-wrap:break-word;overflow-wrap:anywhere}
.msg.in .bubble{background:var(--in);color:var(--text);border-bottom-left-radius:4px}
.msg.out .bubble{background:var(--out);color:#fff;border-bottom-right-radius:4px}
.att{display:block;max-width:220px;max-height:220px;border-radius:10px;margin-top:6px}
.att-link{display:inline-block;margin-top:6px;font-size:13px}
.mtime{color:var(--sub);font-size:11px;margin:2px 4px 0}
.chead{padding:12px 22px;border-bottom:1px solid var(--border);background:var(--card);
  display:flex;align-items:center;gap:10px}
.suggest-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  padding:10px 16px 0;background:var(--card)}
.suggest-bar .btn:disabled{opacity:.6;cursor:default}
.shint{color:var(--sub);font-size:12.5px;min-width:0;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.shint.warn{color:var(--warn)}
/* Bảng "Trích tri thức": thanh đầu có nút ✕ đóng (panel chen giữa khung chat và
   ô soạn tin nên phải luôn đóng được, dù đã lưu hay chưa) */
.ext-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.ext-head .ext-close{margin-left:auto;flex:0 0 auto;padding:4px 10px;font-size:12px}
.composer{border-top:1px solid var(--border);background:var(--card);padding:12px 16px;
  display:flex;gap:10px;align-items:flex-end}
.composer textarea{flex:1;resize:none;border:1px solid var(--border);border-radius:20px;
  padding:10px 15px;font:inherit;font-size:14px;background:var(--bg);color:var(--text);
  max-height:130px}
.composer button{flex:0 0 auto;border:0;background:var(--accent);color:#fff;
  border-radius:20px;padding:10px 20px;font:inherit;font-weight:600;cursor:pointer}
.placeholder{flex:1;display:grid;place-items:center;color:var(--sub);padding:40px;
  text-align:center}

/* ---------- co theo màn hình nhỏ ---------- */
@media (max-width:900px){
  body{flex-direction:column}
  .side{width:100%;flex:none;height:auto;position:static;padding:10px 12px;
    flex-direction:row;align-items:center;gap:12px}
  .brand{padding:0}
  /* màn hẹp: giấu tên trong topbar, giữ nút Đăng xuất */
  .su-info{display:none}
  .nav{flex-direction:row;overflow-x:auto;gap:4px;margin-left:auto}
  .nav-item span{display:none}
  .nav-item{padding:9px 12px}
  .nav-item.on{box-shadow:inset 0 -3px 0 var(--accent)}
  /* màn hẹp menu nằm ngang: khối xổ không hợp — ẩn, hiện link phẳng dự phòng */
  .dept{display:none}
  .mobile-only{display:flex}
  .topbar,.tabs{padding-left:16px;padding-right:16px}
  .content{padding:16px}
  .inbox{flex-direction:column}
  .inbox-list{flex:0 0 auto;max-height:38vh;border-right:0;
    border-bottom:1px solid var(--border)}
}

/* ---------- tab "Thử API" (bố cục kiểu Postman) ---------- */
.pm{gap:12px}
.pm-bar{display:flex;gap:0;align-items:stretch;flex-wrap:wrap}
.pm-method{flex:0 0 auto;width:96px;font-weight:700;border-radius:10px 0 0 10px;
  border-right:none}
.pm-base{display:flex;align-items:center;padding:0 10px;font-size:12.5px;
  font-family:ui-monospace,Menlo,Consolas,monospace;color:var(--sub);
  background:var(--bg);border:1px solid var(--border);border-left:none;
  border-right:none;white-space:nowrap}
.pm-path{flex:1 1 260px;min-width:0;border-radius:0;
  font-family:ui-monospace,Menlo,Consolas,monospace}
.pm-send{flex:0 0 auto;border-radius:0 10px 10px 0;padding:0 22px}
.pm-opts{display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.pm-inline{display:flex;align-items:center;gap:6px;font-size:13px;margin:0}
.pm-inline .inp{width:auto;min-width:130px}
.pm-kv-head{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.pm-kv-head .btn{margin-left:auto;padding:3px 10px;font-size:12px}
.pm-row{display:flex;gap:6px;margin-bottom:6px}
.pm-row .inp{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px}
.pm-row .inp:first-child{flex:0 0 34%}
.pm-row .inp:nth-child(2){flex:1;min-width:0}
.pm-del{flex:0 0 auto;width:34px;border:1px solid var(--border);background:transparent;
  color:var(--err);border-radius:8px;cursor:pointer;font-size:13px;line-height:1}
.pm-del:hover{background:var(--bg)}
.pm-status{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.pm-url{font-size:12.5px;overflow-wrap:anywhere;margin-bottom:10px}
.pm-url code{font-size:12.5px}
.pm-params{display:flex;flex-direction:column;gap:4px}
.pm-prow{display:flex;gap:10px;align-items:baseline;font-size:12.5px;
  padding:4px 0;border-bottom:1px dashed var(--border)}
.pm-prow:last-child{border-bottom:none}
.pm-prow code{flex:0 0 34%;color:var(--accent)}
.pm-prow span{flex:1;min-width:0;overflow-wrap:anywhere;
  font-family:ui-monospace,Menlo,Consolas,monospace}
.pm-prow code.pm-secret{color:var(--warn)}
/* Bảng tra cứu của trang test: token đầy đủ + page ID bấm được */
.pm-ref>summary{cursor:pointer;font-weight:600;font-size:14px;list-style:none;
  display:flex;align-items:center;gap:8px}
.pm-ref>summary::-webkit-details-marker{display:none}
.pm-ref>summary::before{content:"▸";color:var(--sub);font-size:12px}
.pm-ref[open]>summary::before{content:"▾"}
.pm-ref .lbl{margin-top:0}
.pm-ref .tblwrap{max-height:280px;overflow:auto}
.pm-copy{display:flex;gap:8px;align-items:flex-start}
.pm-copy code{flex:1;min-width:0;overflow-wrap:anywhere;font-size:12px;
  background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px 10px}
.pm-copy .btn{flex:0 0 auto;padding:4px 12px;font-size:12px}
code.pm-pid{cursor:pointer;color:var(--accent);border-bottom:1px dashed var(--accent)}
code.pm-pid:hover{background:var(--soft)}
.pm-json{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:14px 16px;margin:0;max-height:60vh;overflow:auto;font-size:12.5px;
  line-height:1.55;font-family:ui-monospace,Menlo,Consolas,monospace;
  white-space:pre;tab-size:2}
@media (max-width:700px){
  .pm-base{display:none}
  .pm-method,.pm-path,.pm-send{border-radius:10px}
  .pm-method{border-right:1px solid var(--border);width:100%}
  .pm-path{border:1px solid var(--border);margin:6px 0}
  .pm-send{width:100%}
}

/* ---------- tab "Thử API dự án" (danh mục 205 endpoint, bấm là chạy) ---------- */
.ac-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.ac-find{flex:1 1 260px;min-width:0}
.ac-chips{display:flex;gap:6px;flex-wrap:wrap}
.ac-chip{border:1px solid var(--border);background:var(--card);color:var(--sub);
  border-radius:20px;padding:5px 13px;font-size:12.5px;cursor:pointer;font-weight:600}
.ac-chip:hover{border-color:var(--accent);color:var(--accent)}
.ac-chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.ac-grp{background:var(--card);border:1px solid var(--border);border-radius:var(--r);
  margin-bottom:10px;box-shadow:var(--shadow);overflow:hidden}
.ac-grp>summary{cursor:pointer;list-style:none;display:flex;align-items:center;
  gap:9px;padding:12px 16px;font-weight:650}
.ac-grp>summary::-webkit-details-marker{display:none}
.ac-grp>summary::before{content:"▸";color:var(--sub);font-size:12px}
.ac-grp[open]>summary::before{content:"▾"}
.ac-grp>summary:hover{background:var(--soft)}
.ac-ep{border-top:1px solid var(--border)}
.ac-head{display:flex;align-items:center;gap:10px;width:100%;text-align:left;
  padding:9px 16px;background:transparent;border:0;cursor:pointer;color:inherit;
  font:inherit}
.ac-head:hover{background:var(--soft)}
.ac-ep.open>.ac-head{background:var(--soft)}
.ac-m{flex:0 0 62px;text-align:center;font-size:10.5px;font-weight:800;
  letter-spacing:.04em;padding:3px 0;border-radius:6px;color:#fff}
.ac-m.get{background:#16a34a}.ac-m.post{background:#6f5a9c}
.ac-m.put{background:#e0900a}.ac-m.patch{background:#e0900a}
.ac-m.delete{background:#e5484d}
.ac-path{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;
  flex:0 0 auto;overflow-wrap:anywhere}
.ac-desc{flex:1;min-width:0;color:var(--sub);font-size:12.5px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.ac-perm{flex:0 0 auto;font-size:10.5px;color:var(--accent2)}
.ac-go{flex:0 0 auto;border:1px solid var(--border);background:var(--card);
  color:var(--accent);border-radius:8px;padding:3px 11px;font-size:12px;
  font-weight:700;cursor:pointer}
.ac-go:hover{background:var(--accent);border-color:var(--accent);color:#fff}
.ac-body{padding:4px 16px 16px;border-top:1px dashed var(--border);
  background:var(--soft)}
.ac-fields{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));
  gap:10px;margin:12px 0}
.ac-fields label{display:flex;flex-direction:column;gap:4px;font-size:12px;
  color:var(--sub)}
.ac-fields .inp{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px}
.ac-req{color:var(--err)}
.ac-body textarea{width:100%;font-family:ui-monospace,Menlo,Consolas,monospace;
  font-size:12.5px;border:1px solid var(--border);border-radius:10px;padding:10px 12px;
  background:var(--card);color:var(--text)}
.ac-acts{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}
.ac-res{margin-top:12px}
.ac-res .pm-json{max-height:46vh}
.ac-empty{color:var(--sub);padding:14px 2px}

/* ---------- điều hướng kiểu AJAX (_NAV_JS) ---------- */
html.pjax-loading{cursor:progress}
html.pjax-loading .main{opacity:.55;transition:opacity .15s linear}
"""


# ---------------------------------------------------------------------------
# Điều hướng kiểu SPA (PJAX): chặn click link nội bộ + submit form, gọi fetch
# tới CHÍNH route đó (server vẫn trả nguyên trang HTML như cũ, không cần thêm
# route/endpoint riêng cho từng màn), rồi chỉ thay <title>, .side (menu trái)
# và .main (topbar + tab + nội dung) của trang HIỆN TẠI thay vì để trình duyệt
# điều hướng thật — nhờ vậy sidebar/topbar không bị trình duyệt huỷ và vẽ lại
# (đó chính là nguồn gốc hiện tượng nhấp nháy khi chuyển trang/tab).
#
# Một số trang có thêm JS riêng (script[data-page-script], vd polling ở màn
# Tin nhắn) — đoạn này KHÔNG tự chạy lại khi ta gán innerHTML nên phải tự tạo
# lại thẻ <script> để trình duyệt thực thi sau mỗi lần thay nội dung; các
# setInterval của lần trước cũng phải tự huỷ (qua window.__pjaxTimers) kẻo
# rò rỉ khi người dùng ra vào lại cùng 1 trang nhiều lần.
_NAV_JS = """
(function(){
  // Đường dẫn hiện tại KHÔNG tính #fragment — dùng để phân biệt "đổi trang
  // thật" với "chỉ nhảy tới neo trong trang" ở handler popstate bên dưới.
  var here = location.pathname + location.search;

  function sameOrigin(url){
    try { return new URL(url, location.href).origin === location.origin; }
    catch (e) { return false; }
  }

  function runPageScript(doc){
    (window.__pjaxTimers || []).forEach(clearInterval);
    window.__pjaxTimers = [];
    var old = document.querySelector('script[data-page-script]');
    if (old) old.remove();
    var fresh = doc.querySelector('script[data-page-script]');
    if (fresh && fresh.textContent.trim()) {
      var s = document.createElement('script');
      s.setAttribute('data-page-script', '');
      s.textContent = fresh.textContent;
      document.body.appendChild(s);
    }
  }

  function applyDoc(doc, url){
    document.title = doc.title;
    var newSide = doc.querySelector('.side');
    var newMain = doc.querySelector('.main');
    var curSide = document.querySelector('.side');
    var curMain = document.querySelector('.main');
    // Phải chép cả class chứ không chỉ innerHTML: <main> có thể mang class
    // "full" (màn Tin nhắn khoá 100vh, overflow:hidden). Nếu chỉ thay ruột thì
    // đi từ Tin nhắn sang trang thường, <main> vẫn còn "full" -> trang bị khoá
    // đúng 1 màn hình, cuộn không được và phần dưới (vd nhật ký quét ở màn
    // Cảm xúc) bị cắt mất.
    if (newSide && curSide) {
      curSide.className = newSide.className;
      curSide.innerHTML = newSide.innerHTML;
    }
    if (newMain && curMain) {
      curMain.className = newMain.className;
      curMain.innerHTML = newMain.innerHTML;
    }
    runPageScript(doc);
    window.scrollTo({top: 0});
    var hash = (url.split('#')[1]) || '';
    var target = hash && document.getElementById(hash);
    if (target) target.scrollIntoView();
  }

  function swap(doc, url){
    if (document.startViewTransition) {
      document.startViewTransition(function(){ applyDoc(doc, url); });
    } else {
      applyDoc(doc, url);
    }
  }

  function go(url, opts, push){
    document.documentElement.classList.add('pjax-loading');
    fetch(url, opts || {})
      .then(function(r){
        return r.text().then(function(html){ return {html: html, url: r.url}; });
      })
      .then(function(res){
        var doc = new DOMParser().parseFromString(res.html, 'text/html');
        // Trang NGOÀI shell (màn đăng nhập sau khi bấm Đăng xuất, hoặc bị đá
        // về /dang-nhap vì phiên hết hạn) không có .side/.main để swap —
        // trước đây applyDoc lặng lẽ không đổi gì, người dùng tưởng nút hỏng
        // và phải tự F5. Gặp trang như vậy thì điều hướng THẬT (replace để
        // không nhét thêm mục history rác).
        if (!doc.querySelector('.side') || !doc.querySelector('.main')) {
          location.replace(res.url);
          return;
        }
        swap(doc, res.url);
        if (push) history.pushState({pjax: true}, '', res.url);
        here = location.pathname + location.search;
      })
      .catch(function(){ location.href = url; })
      .then(function(){ document.documentElement.classList.remove('pjax-loading'); });
  }

  // Click link nội bộ -> AJAX thay vì điều hướng thật. Bỏ qua: mở tab mới
  // (Ctrl/Cmd/Shift/giữa chuột), target khác _self, link tải file, neo cùng
  // trang (#...), mailto/tel, hoặc khác origin.
  document.addEventListener('click', function(e){
    if (e.defaultPrevented || e.button !== 0 ||
        e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest('a[href]');
    if (!a || a.target || a.hasAttribute('download')) return;
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || /^(mailto|tel):/i.test(href)) return;
    if (!sameOrigin(href)) return;
    e.preventDefault();
    go(href, {cache: 'no-store'}, true);
  });

  // Submit form (GET hoặc POST) -> AJAX. e.defaultPrevented tôn trọng các
  // handler khác chạy trước (vd confirm() huỷ ở nút Xoá, hoặc trang đã tự xử
  // lý AJAX riêng như công tắc BẬT/TẮT page ở Bảng điều khiển).
  document.addEventListener('submit', function(e){
    if (e.defaultPrevented) return;
    var f = e.target;
    // Form gắn data-native (vd Đăng xuất) đi đường trình duyệt THẬT, không
    // AJAX: submit -> 303 -> nhảy thẳng sang trang đích ngay lập tức.
    if (f.hasAttribute('data-native')) return;
    // ĐỌC QUA getAttribute, KHÔNG dùng f.method / f.action trực tiếp: form có
    // [LegacyOverrideBuiltIns] nên một ô <input name="method"> (hay "action",
    // "target"...) sẽ CHE property gốc — f.method trả về thẻ <select> chứ không
    // phải chuỗi, gọi .toLowerCase() là ném lỗi ngay sau preventDefault() và
    // form không bao giờ được gửi đi.
    var action = f.getAttribute('action') || location.pathname;
    var verb = (f.getAttribute('method') || 'get').toLowerCase();
    if (f.getAttribute('target') || !sameOrigin(action)) return;
    e.preventDefault();
    // FormData(form) KHÔNG chứa nút bấm đã gửi form. Trình duyệt thật thì có,
    // nên form nào phân biệt hành động bằng <button name=… value=…> (vd chọn
    // giai đoạn ở Bảng chăm sóc) sẽ mất tham số nếu không tự thêm vào đây.
    var fd = new FormData(f);
    var sb = e.submitter;
    if (sb && sb.name && !fd.has(sb.name)) fd.append(sb.name, sb.value);
    var qs = new URLSearchParams(fd).toString();
    if (verb === 'post') {
      go(action, {
        method: 'POST', body: qs,
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      }, true);
    } else {
      var base = action.split('?')[0];
      go(base + (qs ? '?' + qs : ''), {cache: 'no-store'}, true);
    }
  });

  // <select data-nav-tpl="/tin-nhan?page_id="> đổi lựa chọn -> AJAX (thay vì
  // gán thẳng location.href khiến trình duyệt điều hướng thật).
  document.addEventListener('change', function(e){
    var tpl = e.target.getAttribute && e.target.getAttribute('data-nav-tpl');
    if (tpl == null) return;
    go(tpl + encodeURIComponent(e.target.value), {cache: 'no-store'}, true);
  });

  // Back/Forward: trang đã đổi qua AJAX nên không có bfcache riêng -> tải lại
  // nội dung cho khớp URL, vẫn không đụng sidebar/topbar (không push state mới).
  //
  // ⚠ Bấm link neo trong trang (href="#...") CŨNG phát 'popstate' trên
  // Chrome/Safari (fragment navigation là một mục lịch sử mới của cùng tài
  // liệu). Nếu không lọc, mỗi lần bấm neo là tải lại + gán innerHTML cho .main
  // -> phần tử đích bị dựng mới nên `:target` hết khớp: panel "Danh sách page"
  // ở Bảng điều khiển vừa hiện ra đã tự đóng lại ngay.
  // => Chỉ đổi mỗi #fragment thì để trình duyệt tự xử lý, không tải lại gì cả.
  window.addEventListener('popstate', function(){
    var now = location.pathname + location.search;
    if (now === here) return;
    here = now;
    go(location.href, {cache: 'no-store'}, false);
  });
})();
"""
