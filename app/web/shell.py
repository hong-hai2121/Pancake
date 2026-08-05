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

import hashlib
import time
from functools import lru_cache
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
    # --- bộ icon riêng của màn Hội thoại (rail lọc · hàng danh sách · đầu khung
    # chat · ô soạn tin). Chép ĐÚNG path lucide mà mẫu crmv2.kallet.vn dùng để
    # hình vẽ khớp bản gốc; chỉ nét là theo _icon (1.8) cho đồng bộ menu.
    "messages-square": '<path d="M16 10a2 2 0 0 1-2 2H6.83a2 2 0 0 0-1.42.59l-2.2 2.2'
                       'A.71.71 0 0 1 2 14.29V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>'
                       '<path d="M20 9a2 2 0 0 1 2 2v10.29a.71.71 0 0 1-1.21.5l-2.2-2.2'
                       'A2 2 0 0 0 17.17 19H10a2 2 0 0 1-2-2v-1"/>',
    "mail-warning": '<path d="M22 10.5V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v12c0 1.1.9 2 2 2h12.5"/>'
                    '<path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>'
                    '<path d="M20 14v4"/><path d="M20 22v.01"/>',
    "list-checks": '<path d="M13 5h8"/><path d="M13 12h8"/><path d="M13 19h8"/>'
                   '<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/>',
    "flame": '<path d="M12 3q1 4 4 6.5t3 5.5a1 1 0 0 1-14 0 5 5 0 0 1 1-3 1 1 0 0 0 5 0'
             'c0-2-1.5-3-1.5-5q0-2 2.5-4"/>',
    "heart-handshake": '<path d="M19.41 14.41C21 12.83 22 11.5 22 9.5a5.5 5.5 0 0 0-9.59-3.68'
                       '.6.6 0 0 1-.82 0A5.5 5.5 0 0 0 2 9.5c0 2.3 1.5 4 3 5.5l5.54 5.36'
                       'a2 2 0 0 0 2.88.05 2.12 2.12 0 0 0 0-3 2.12 2.12 0 1 0 3-3'
                       ' 2.12 2.12 0 0 0 3 0 2 2 0 0 0 0-2.83l-1.88-1.88a2.41 2.41 0 0 0-3.41 0'
                       'l-1.71 1.71a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l2.82-2.76"/>',
    "user-round": '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
    "radio": '<path d="M16.25 7.76a6 6 0 0 1 0 8.48"/>'
             '<path d="M19.08 4.93a10 10 0 0 1 0 14.14"/>'
             '<path d="M4.93 19.07a10 10 0 0 1 0-14.14"/>'
             '<path d="M7.75 16.24a6 6 0 0 1 0-8.48"/><circle cx="12" cy="12" r="2"/>',
    "calendar": '<path d="M8 2v3"/><path d="M16 2v3"/>'
                '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/>',
    "timer": '<path d="M10 2h4"/><path d="m12 14 3-3"/><circle cx="12" cy="14" r="8"/>',
    "panel-left-close": '<rect x="3" y="3" width="18" height="18" rx="2"/>'
                        '<path d="M9 3v18"/><path d="m16 15-3-3 3-3"/>',
    # đáy menu trái: nút Đăng xuất trong khối tài khoản (_side_foot)
    "log-out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>'
               '<path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    "search": '<path d="m21 21-4.34-4.34"/><circle cx="11" cy="11" r="8"/>',
    "sliders": '<path d="M10 5H3"/><path d="M12 19H3"/><path d="M14 3v4"/>'
               '<path d="M16 17v4"/><path d="M21 12h-9"/><path d="M21 19h-5"/>'
               '<path d="M21 5h-7"/><path d="M8 10v4"/><path d="M8 12H3"/>',
    "eye": '<path d="M2.06 12.35a1 1 0 0 1 0-.7 10.75 10.75 0 0 1 19.88 0 1 1 0 0 1 0 .7'
           ' 10.75 10.75 0 0 1-19.88 0"/><circle cx="12" cy="12" r="3"/>',
    "eye-off": '<path d="M10.73 5.08a10.74 10.74 0 0 1 11.21 6.57 1 1 0 0 1 0 .7'
               ' 10.75 10.75 0 0 1-1.45 2.49"/>'
               '<path d="M14.08 14.16a3 3 0 0 1-4.24-4.24"/>'
               '<path d="M17.48 17.5a10.75 10.75 0 0 1-15.42-5.15 1 1 0 0 1 0-.7'
               ' 10.75 10.75 0 0 1 4.45-5.14"/><path d="m2 2 20 20"/>',
    "message-circle": '<path d="M2.99 16.34a2 2 0 0 1 .1 1.17l-1.07 3.29a1 1 0 0 0 1.24 1.17'
                      'l3.41-1a2 2 0 0 1 1.1.09 10 10 0 1 0-4.78-4.72"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>'
            '<circle cx="12" cy="7" r="4"/>',
    "phone": '<path d="M13.83 16.57a1 1 0 0 0 1.21-.3l.36-.47A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3'
             'a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6'
             'l-.47.35a1 1 0 0 0-.29 1.23 14 14 0 0 0 6.39 6.39"/>',
    "phone-call": '<path d="M13 2a9 9 0 0 1 9 9"/><path d="M13 6a5 5 0 0 1 5 5"/>'
                  '<path d="M13.83 16.57a1 1 0 0 0 1.21-.3l.36-.47A2 2 0 0 1 17 15h3'
                  'a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3'
                  'a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.47.35a1 1 0 0 0-.29 1.23'
                  ' 14 14 0 0 0 6.39 6.39"/>',
    "copy": '<rect x="8" y="8" width="14" height="14" rx="2"/>'
            '<path d="M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    # Hai dấu tích chồng = "đã xong rồi, xác nhận rồi" — mẫu dùng cho số việc
    # đã chăm xong hôm nay, phân biệt với `check` (một việc lẻ).
    "check-check": '<path d="M18 6 7 17l-5-5"/><path d="m22 10-7.5 7.5L13 16"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "dots-h": '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>'
              '<circle cx="5" cy="12" r="1"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "mail": '<path d="m22 7-8.99 5.73a2 2 0 0 1-2.01 0L2 7"/>'
            '<rect x="2" y="4" width="20" height="16" rx="2"/>',
    "external-link": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/>'
                     '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "lock": '<rect x="4" y="10" width="16" height="11" rx="2"/>'
            '<path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    "lightbulb": '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8'
                 'c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/>'
                 '<path d="M9 18h6"/><path d="M10 22h4"/>',
    "book-open": '<path d="M12 5v16"/>'
                 '<path d="M20 19a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2l-4 0A5 5 0 0 0 12 5'
                 'a5 5 0 0 0-4-2H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4a5 5 0 0 1 4 2 5 5 0 0 1 4-2z"/>',
    "send": '<path d="M14.54 21.69a.5.5 0 0 0 .93-.03l6.5-19a.5.5 0 0 0-.63-.63l-19 6.5'
            'a.5.5 0 0 0-.03.94l7.93 3.18a2 2 0 0 1 1.11 1.11z"/>'
            '<path d="m21.85 2.15-10.94 10.94"/>',
    # --- bộ icon riêng của màn Khách hàng (bảng theo mẫu Kallet): huy hiệu hạng
    # thẻ · phân trang · thanh công cụ bảng. Chép đúng path lucide mà mẫu dùng.
    "medal": '<path d="M7.21 15 2.66 7.14a2 2 0 0 1 .13-2.2L4.4 2.8A2 2 0 0 1 6 2h12'
             'a2 2 0 0 1 1.6.8l1.6 2.14a2 2 0 0 1 .14 2.2L16.79 15"/>'
             '<path d="M11 12 5.12 2.2"/><path d="m13 12 5.88-9.8"/><path d="M8 7h8"/>'
             '<circle cx="12" cy="17" r="5"/><path d="M12 18v-2h-.5"/>',
    "gem": '<path d="M10.5 3 8 9l4 13 4-13-2.5-6"/>'
           '<path d="M17 3a2 2 0 0 1 1.6.8l3 4a2 2 0 0 1 .013 2.382l-7.99 10.986'
           'a2 2 0 0 1-3.247 0l-7.99-10.986A2 2 0 0 1 2.4 7.8l2.998-3.997A2 2 0 0 1 7 3z"/>'
           '<path d="M2 9h20"/>',
    "ticket": '<path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2'
              'a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/>'
              '<path d="M13 5v2"/><path d="M13 17v2"/><path d="M13 11v2"/>',
    "sparkles": '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558'
                'a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051'
                'a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558'
                'a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051'
                'a2 2 0 0 0 1.594-1.594z"/><path d="M20 2v4"/><path d="M22 4h-4"/>'
                '<circle cx="4" cy="20" r="2"/>',
    "circle": '<circle cx="12" cy="12" r="10"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "filter-x": '<path d="M12.531 3H3a1 1 0 0 0-.742 1.67l7.225 7.989A2 2 0 0 1 10 14v6'
                'a1 1 0 0 0 .553.895l2 1A1 1 0 0 0 14 21v-7a2 2 0 0 1 .517-1.341l.427-.473"/>'
                '<path d="m16.5 3.5 5 5"/><path d="m21.5 3.5-5 5"/>',
    "file-spreadsheet": '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706'
                        'l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/>'
                        '<path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M8 13h2"/>'
                        '<path d="M14 13h2"/><path d="M8 17h2"/><path d="M14 17h2"/>',
    "columns-3": '<rect x="3" y="3" width="18" height="18" rx="2"/>'
                 '<path d="M9 3v18"/><path d="M15 3v18"/>',
    "check-square": '<path d="M21 10.656V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12.344"/>'
                    '<path d="m9 11 3 3L22 4"/>',
    # C1 — nhóm Ưu đãi
    "gift": '<rect x="3" y="8" width="18" height="4" rx="1"/>'
            '<path d="M12 8v13"/><path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"/>'
            '<path d="M7.5 8a2.5 2.5 0 0 1 0-5C11 3 12 8 12 8s1-5 4.5-5a2.5 2.5 0 0 1 0 5"/>',
    "award": '<circle cx="12" cy="8" r="6"/>'
             '<path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/>',
    # C2 — nhóm Tiền
    "wallet": '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4"/>'
              '<path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>'
              '<path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>',
}

# Menu bên trái, chia NHÓM. Mỗi mục: (đường dẫn, nhãn, khoá `active`, icon,
# quyền cần có). Quyền "" = ai đăng nhập cũng thấy; có mã -> chỉ hiện khi token
# mang quyền đó; nhiều mã cách nhau "|" = có MỘT trong số đó là hiện (vd mục
# Quản trị mở cho cả trưởng nhóm). Đây chỉ là ẨN MỤC MENU cho gọn — chặn thật
# nằm ở route.
# Nhóm CRM là các màn khung (xem app/web/views/crm.py) — lát cắt B1…B11 làm đầy.
#
# THỨ TỰ NHÓM bám mẫu giao diện Kallet (web-da-noi/, bản crmv2.kallet.vn):
#   Chung → Bộ phận → Ưu đãi → Tiền → (Bot Pancake) → Quản trị.
# Mẫu có mục nào ta chưa dựng màn thì BỎ TRỐNG, không thêm link chết; ngược lại
# màn của ta không có trong mẫu thì xếp vào nhóm gần nghĩa nhất (ghi chú tại chỗ).
MENU_GROUPS: list[tuple[str, list[tuple[str, str, str, str, str]]]] = [
    # Việc hằng ngày, ai cũng mở — đứng đầu menu.
    ("Chung", [
        # Hộp thư hội thoại (giao diện port từ mẫu crmv2.kallet.vn) — xếp ĐẦU
        # menu vì đây là màn nhân viên mở suốt ngày. Muốn theo đúng thứ tự mẫu
        # (Trang chủ trước) thì đổi chỗ hai dòng này là xong.
        ("/crm/hoi-thoai", "Hội thoại", "crm-chat", "messages", ""),
        # Màn 2 — trang chủ theo vai trò (đăng nhập xong vào đây, "/" trỏ về đây)
        ("/crm/trang-chu", "Trang chủ", "crm-home", "home", ""),
        ("/crm/tong-quan", "Tổng quan", "crm-overview", "dashboard", ""),
        ("/crm/khach-hang", "Khách hàng", "crm-customers", "customers", ""),
        ("/crm/don-hang", "Đơn hàng", "crm-orders", "orders", ""),
    ]),
    # Mẫu Kallet: Sale → CSKH → Quảng cáo. Công việc/Bàn giao là màn của CSKH nên
    # kẹp ngay sau khối CSKH, trước Quảng cáo.
    ("Bộ phận", [
        # Mục này được NÂNG thành 2 khối bộ phận xổ/thu ĐỨNG LIỀN NHAU (xem
        # _sidebar): "Sale" (_sale_dept) rồi ngay dưới là "Chăm sóc khách hàng"
        # (_dept_cskh) — hai bộ phận nối tiếp nhau đúng luồng bàn giao Sale→CSKH.
        ("/crm/pipeline", "Pipeline Sale", "crm-pipeline", "pipeline", ""),
        ("/crm/cong-viec", "Công việc", "crm-tasks", "tasks", ""),
        # B8 — màn 24-25: đơn giao thành công tự sinh phiếu, CSKH nhận/trả lại
        ("/crm/ban-giao", "Bàn giao", "crm-handover", "care", ""),
        # BRD mục 4 (nguồn quảng cáo) — màn 7 + 53-55: chi phí · ROAS · LTV
        ("/crm/quang-cao", "Nguồn quảng cáo", "crm-ads", "sentiment", "ads.view"),
    ]),
    # Mẫu Kallet: Voucher · Chiến dịch · Hạng thẻ · Sản phẩm · Mẫu tin.
    # C1 đã port Voucher + Hạng thẻ; Chiến dịch/Mẫu tin chờ lát cắt sau.
    ("Ưu đãi", [
        # C1 — voucher.php của mẫu. Quyền riêng: tặng voucher là phát tiền.
        ("/crm/voucher", "Voucher", "crm-voucher", "gift", "voucher.grant"),
        # C4 — kich-ban.php: THƯ VIỆN chép tay, KHÔNG gửi gì (khác Chiến dịch)
        ("/crm/kich-ban", "Thư viện kịch bản", "crm-scripts", "products", ""),
        # C1 — hang-the.php: 5 bậc + "Chưa xếp hạng", tính theo tổng chi tiêu
        ("/crm/hang-the", "Hạng thẻ", "crm-rank", "award", ""),
        # C3 — chien-dich.php: 2 tầng, máy gửi tầng 1 · người chăm tầng 2
        ("/crm/chien-dich", "Chiến dịch", "crm-campaign", "messages",
         "campaign.manage"),
        # C3 — mau-tin.php: nội dung dùng cho chiến dịch & gửi hàng loạt
        ("/crm/mau-tin", "Mẫu tin", "crm-template", "data", "campaign.manage"),
        # Màn 69 + 71 — bảng theo dõi automation đang chạy (không phải builder)
        ("/crm/automation", "Automation", "crm-automation", "tasks", ""),
        ("/crm/san-pham", "Sản phẩm", "crm-products", "products", ""),
    ]),
    # Mẫu Kallet: Thu nhập của tôi · Báo cáo · Lương thưởng · Đối soát & duyệt
    # thưởng — C2 đã port đủ cả 4.
    ("Tiền", [
        # C2 — luong.php: CHỈ xem của chính mình, không lộ lương người khác
        ("/crm/thu-nhap", "Thu nhập của tôi", "crm-income", "wallet",
         "payroll.view_own"),
        # B11 — màn 60-64 + drill-down FR-173 (màn 5-6 vào từ đây/trang chủ)
        ("/crm/bao-cao", "Báo cáo", "crm-reports", "sentiment", ""),
        # C2 — luong-thuong.php: bảng lương cả đội + chốt kỳ
        ("/crm/luong", "Lương thưởng", "crm-payroll", "wallet", "payroll.manage"),
        # C2 — doi-soat.php: duyệt/bác thưởng chăm sóc theo 3 rổ
        ("/crm/doi-soat", "Đối soát thưởng", "crm-recon", "check-square",
         "payroll.approve"),
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
    # Khu Quản trị đứng CUỐI menu, dưới cả nhóm Bot Pancake — việc thiết lập chứ
    # không phải việc hằng ngày. Là NHÓM xổ/thu y hệt Bot Pancake (trước đây chỉ
    # là MỘT nút, các màn con giấu trong dải tab của views/admin.py:_TABS): mở
    # thẳng đúng màn cần từ menu, khỏi vào Nhân viên rồi mới bấm tab.
    # Quyền từng mục bám đúng route (app/web/routes/admin.py) nên trưởng nhóm chỉ
    # thấy Nhân viên, người có audit.view chỉ thấy Nhật ký...
    # Thông báo · Giám sát · Kho data GỘP VÀO ĐÂY (trước là nhóm KHÔNG TÊN ngăn
    # bằng vạch nav-sep): cũng là màn theo dõi/dữ liệu chứ không phải việc hằng
    # ngày, để riêng thì menu có một cụm 3 mục trôi nổi không tiêu đề, gập nhóm
    # Quản trị lại vẫn còn nguyên đó.
    # Thứ tự trong nhóm: Người → Thiết lập → Theo dõi → Dữ liệu.
    ("Quản trị", [
        ("/quan-tri/nhan-vien", "Nhân viên", "admin-nhan-vien", "customers",
         "user.manage|user.manage_team"),
        ("/quan-tri/phan-quyen", "Vai trò & quyền", "admin-phan-quyen", "lock",
         "user.manage"),
        ("/quan-tri/the-pancake", "Thẻ Pancake", "admin-the-pancake", "ticket",
         "user.manage"),
        ("/quan-tri/cai-dat", "Cài đặt", "admin-cai-dat", "admin", "user.manage"),
        # BRD mục 4 — khu Tích hợp Pancake (kết nối, nhật ký/lỗi đồng bộ, ánh xạ)
        ("/quan-tri/tich-hop", "Tích hợp", "tich-hop", "data", "integration.manage"),
        # Màn 3 — trung tâm thông báo (chuông ở góc phải cũng trỏ về đây). Mục
        # DUY NHẤT trong nhóm không đòi quyền: ai cũng có thông báo của mình.
        ("/crm/thong-bao", "Thông báo", "crm-notify", "bell", ""),
        ("/quan-tri/nhat-ky", "Nhật ký", "admin-nhat-ky", "clock", "audit.view"),
        # C4 — lich-su.php: vòng xác minh công (soi tin nhắn thật)
        ("/crm/giam-sat", "Giám sát", "crm-audit-work", "search",
         "audit.view"),
        # C4 — kho-data.php: khách chưa chia · khách kẹt · nhật ký
        ("/crm/kho-data", "Kho data", "crm-data", "data", "data.export"),
    ]),
]


# Nhóm menu XỔ/THU được: tiêu đề nhóm thành <summary> bấm gập cả cụm mục bên
# dưới, trạng thái nhớ trong localStorage (xem `_NAV_JS`). MỌI nhóm CÓ TÊN đều
# gập được: 6 nhóm là hơn 30 mục, không ai dùng cả 6 cùng lúc — Sale gập Tiền,
# kế toán gập Bộ phận, còn Bot Pancake/Quản trị là khu phụ ngày thường không
# đụng tới. Muốn thêm nhóm mới thì bỏ đúng tên nhóm vào đây, khỏi sửa gì thêm.
# Nay MENU_GROUPS không còn nhóm KHÔNG TÊN nào (3 mục cũ đã gộp vào Quản trị)
# nên cả 6 nhóm đều gập được. Nhánh vạch ngăn trong `_sidebar` vẫn giữ để thêm
# nhóm không tên về sau khỏi vỡ menu — nhưng nhóm KHÔNG TÊN thì đừng bỏ vào đây:
# không có tiêu đề là không có chỗ bấm để mở lại.
_NHOM_THU_GON: frozenset[str] = frozenset({
    "Chung", "Bộ phận", "Ưu đãi", "Tiền", "Bot Pancake", "Quản trị",
})

# Nhóm GHIM ở đáy menu: không nằm trong <nav> cuộn mà xuống khối `.side-bottom`
# cố định cùng khối tài khoản.
#
# HIỆN TRỐNG — Quản trị đã ĐƯA VỀ trong <nav>, đứng cuối cùng chung với 5 nhóm
# kia (mẫu Kallet cũng để nhóm Quản trị trong vùng cuộn, chỉ ghim nút Thu gọn +
# khối tài khoản). Ghim riêng làm nó trông như một khu tách rời khỏi menu.
# Giữ lại cơ chế để sau này muốn ghim nhóm nào thì bỏ tên vào đây là xong; tên
# phải có trong MENU_GROUPS và nên gập được (_NHOM_THU_GON) kẻo nhóm dài chiếm
# mất phần cuộn phía trên.
_NHOM_GHIM: frozenset[str] = frozenset()


# MÀU RIÊNG CỦA TỪNG NHÓM — in ra biến CSS `--gc` trên thẻ <details> của nhóm,
# các mục con thừa hưởng: icon, tiêu đề nhóm, nền lúc rê chuột, quầng sáng của
# mục đang chọn, sọc trái khối bộ phận. Icon mỗi nhóm một màu thì quét mắt
# nhanh hơn hẳn một dải icon trắng như nhau (nhớ theo màu, không phải đọc chữ).
#
# Bảng màu bám nền tím→hồng của sidebar: 4 nhóm nghiệp vụ lấy màu tươi và tách
# bạch, còn Bot Pancake/Quản trị là khu phụ nên để tông trầm — đỡ thành cầu vồng
# mà vẫn nói được "hai cái này không phải việc hằng ngày".
# Sáng cỡ 300 (pastel) chứ đừng đậm hơn: nền tím vốn tối, màu đậm là chìm mất.
_MAU_NHOM: dict[str, str] = {
    "Chung": "#8ecdff",         # xanh trời — việc mở suốt ngày
    "Bộ phận": "#ffd27a",       # hổ phách, khớp chữ CRM ở logo
    "Ưu đãi": "#ffb0c8",        # hồng — quà, voucher
    "Tiền": "#93e6b8",          # bạc hà — tiền nong
    "Bot Pancake": "#bcb3e8",   # tím nhạt trầm — khu phụ
    "Quản trị": "#cfc6d8",      # xám tím trầm — thiết lập, không phải nghiệp vụ
}


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
    on_bv = " on" if active == "crm-board" else ""
    try:
        from app.db.repositories.crm_screens_repo import sale_menu

        stages = sale_menu()
    except Exception:  # noqa: BLE001 — DB chưa lên vẫn phải có menu dùng được
        return (f'<a class="nav-item{on_bv}" href="/crm/bang-viec">'
                f'{_icon("pipeline")}<span>Bảng việc Sale</span></a>'
                f'<a class="nav-item{on}" href="/crm/pipeline">'
                f'{_icon("pipeline")}<span>Pipeline Sale</span></a>')

    cot = "".join(
        f'<a class="nd-link" href="/crm/pipeline?st={s["id"]}">'
        f'<span class="nd-dot" style="background:{mau_giai_doan(i)}"></span>'
        f'<span>{escape(s["name"])}</span>'
        f'<span class="nd-count">{s["so_lead"]}</span></a>'
        for i, s in enumerate(stages)
    )
    # C4 — thư viện câu mẫu để CHÉP TAY (khác hẳn /data/kich-ban của bot)
    cong_cu = ('<a class="nd-link" href="/crm/kich-ban">'
               "<span>📖 Thư viện kịch bản</span></a>")
    cong_cu += ('<a class="nd-link" href="/crm/san-pham">'
                "<span>🏷️ Bảng giá &amp; liệu trình</span></a>")
    # C5 — cấu hình thang bám đuổi (chỉ người quản lý mới cần)
    if "user.manage" in perms:
        cong_cu += ('<a class="nd-link" href="/quan-tri/cai-dat?sec=moc#k1a">'
                    "<span>⚙️ Thang bám đuổi</span></a>")

    return (
        f'<details class="nav-dept"{" open" if on else ""}>'
        f'<summary>{_icon("pipeline")}<span>Sale</span>'
        '<span class="nd-chev">▾</span></summary>'
        '<div class="nd-group">Nhiệm vụ</div>'
        # C5 — bảng việc theo THANG BÁM ĐUỔI (máy đọc tin nhắn thật). Đứng
        # TRƯỚC Pipeline vì đây mới là màn nhân viên mở suốt ngày; Pipeline
        # giai đoạn là bản do người tự kéo, xem để đối chiếu.
        f'<a class="nd-link{on_bv}" href="/crm/bang-viec">'
        "<span>📋 Bảng việc (thang bám đuổi)</span></a>"
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
    on = " on" if active in ("crm-care", "crm-repurchase", "crm-cskh-board") else ""
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
        # C6 — vòng đời khách SAU khi nhận hàng (cảm ơn → voucher → thang mua
        # lại), khác hẳn "Chăm sóc C01-C09" (liệu trình của MỘT đơn) ở trên.
        f'<a class="sm-link{" on" if active == "crm-cskh-board" else ""}" '
        'href="/crm/bang-viec-cskh">🎯 Bảng việc CSKH</a>'
        f'<a class="sm-link" href="/crm/mua-lai">🔄 Cơ hội mua lại{n("mua_lai")}</a>'
        '<a class="sm-link" href="/crm/khach-ngu">😴 Khách ngủ (màn 41)</a>'
        "</div></details>"
    )


def _sidebar(active: str) -> str:
    """Menu trái: logo + các nhóm mục; mục đang xem được tô đậm. Mục gắn quyền
    chỉ hiện khi người đăng nhập có quyền đó (đọc từ contextvar middleware đặt)."""
    user = current_user.get()
    perms = (user or {}).get("perms") or []
    # "items" = phần menu CUỘN được; "ghim" = nhóm dán ở đáy (xem _NHOM_GHIM)
    phan = {"items": "", "ghim": ""}
    for ten_nhom, muc in MENU_GROUPS:
        muc_hien = ""
        so_muc = 0          # số mục THẬT SỰ hiện (đã lọc quyền) — hiện trên
        for href, label, key, icon, quyen in muc:   # huy hiệu lúc nhóm thu gọn
            if quyen and not any(m in perms for m in quyen.split("|")):
                continue
            if key == "crm-pipeline":
                # Mục Pipeline được nâng thành HAI khối bộ phận xổ/thu đứng liền
                # nhau (kiểu Pancake): Sale → Chăm sóc khách hàng, đúng thứ tự
                # khách chạy qua (Sale chốt đơn → bàn giao sang CSKH).
                muc_hien += _sale_dept(active, perms) + _dept_cskh(active)
                so_muc += 2
                continue
            cls = "nav-item on" if key == active else "nav-item"
            # escape nhãn: nhóm Quản trị có mục "Vai trò & quyền" — dấu & trần
            # là HTML hỏng (tabs_bar cũng escape y vậy).
            # `title` để lúc menu thu về rail icon (.side.mini) rê chuột còn
            # biết mục nào là mục nào — chữ bị giấu hết.
            muc_hien += (
                f'<a class="{cls}" href="{href}" title="{escape(label)}">'
                f"{_icon(icon)}<span>{escape(label)}</span></a>"
            )
            so_muc += 1
        # cả nhóm bị ẩn theo quyền -> khỏi in tên nhóm trơ trọi; nhóm không tên
        # (khu quản trị ở cuối menu) thì chỉ in mục, không in tiêu đề nhóm
        if not muc_hien:
            continue
        # Nhóm GHIM không nằm trong <nav> cuộn mà xuống khối đáy cố định.
        khoi = "ghim" if ten_nhom in _NHOM_GHIM else "items"
        # Màu nhóm truyền xuống bằng biến CSS, mọi mục con thừa hưởng (_MAU_NHOM)
        mau = _MAU_NHOM.get(ten_nhom, "")
        style = f' style="--gc:{mau}"' if mau else ""
        if ten_nhom in _NHOM_THU_GON:
            # LUÔN in `open`: không có JS (hoặc màn hẹp — menu nằm ngang) thì
            # nhóm trải phẳng như cũ, chứ không kẹt ở trạng thái đóng. Người
            # dùng thu gọn thì _NAV_JS đóng lại ngay lúc dựng trang (thẻ script
            # nằm cuối <body> nên đóng xong mới vẽ, không thấy nhấp nháy).
            phan[khoi] += (
                f'<details class="nav-grp" data-nhom="{escape(ten_nhom)}"'
                f"{style} open>"
                f'<summary class="nav-group">{escape(ten_nhom)}'
                # huy hiệu số: CSS chỉ cho hiện khi nhóm đang thu gọn — lúc đó
                # tiêu đề là thứ duy nhất còn thấy nên phải nói được bên trong
                # còn bao nhiêu mục.
                f'<span class="grp-so">{so_muc}</span>'
                '<span class="grp-chev">▸</span></summary>'
                f'<div class="nav-grp-kids">{muc_hien}</div></details>'
            )
        else:
            # Nhóm không gập được: gói trong <div> mang màu để mục con vẫn thừa
            # hưởng --gc (nhánh này hiện không dùng — mọi nhóm đều gập được).
            phan[khoi] += (
                f"<div{style}>"
                + (f'<div class="nav-group">{escape(ten_nhom)}</div>'
                   if ten_nhom else '<div class="nav-sep"></div>')
                + muc_hien + "</div>"
            )
    items, ghim = phan["items"], phan["ghim"]
    return (
        '<aside class="side">'
        # Logo dựng theo mẫu Kallet: huy hiệu vuông trắng (dấu) + viên thuốc
        # trắng (tên) + chữ CRM hổ phách. Mẫu dùng ảnh kallet-logo.png; dự án
        # chưa có thư mục static nên dấu là chữ lồng, đổi sang <img> lúc nào
        # cũng được mà không phải sửa CSS. Trỏ về TRANG CHỦ (mẫu ghi "Về trang
        # chủ") chứ không phải /bang-dieu-khien — màn đó đòi quyền bot.view nên
        # cấp dưới bấm logo là ăn 403.
        '<a class="brand" href="/crm/trang-chu" title="Về trang chủ">'
        '<span class="logo">FB</span>'
        '<span class="bname">Sales Bot</span>'
        '<span class="btag">CRM</span></a>'
        f'<nav class="nav">{items}</nav>'
        + f'<div class="side-bottom">{ghim}{_side_foot()}</div>'
        + "</aside>"
    )


def _side_foot() -> str:
    """Đáy menu trái (port từ mẫu Kallet): nút thu/phóng menu + khối tài khoản
    đang đăng nhập.

    Khối user ở topbar (`_user_box`) VẪN GIỮ — mẫu có cả hai chỗ, và khi menu
    thu về rail icon thì chuông/tên trên topbar là thứ duy nhất còn đọc được,
    còn ở đây chỉ còn avatar. Đăng xuất phải là form POST y như topbar:
    /dang-xuat không nhận GET.
    """
    user = current_user.get()
    if not user:
        return ""
    ten = (user.get("name") or user.get("username") or "?").strip()
    # Chữ trên avatar lấy TỪ CUỐI của tên: người Việt gọi nhau bằng tên, chứ
    # "Nguyễn Thị Nga" mà hiện "N" (họ Nguyễn) thì ai cũng giống ai.
    chu = (ten.split()[-1][:1] if ten.split() else "?").upper()
    vai = user.get("role") or ""
    return (
        '<button class="foot-btn" type="button" id="navToggle" '
        'title="Thu gọn menu" aria-label="Thu gọn menu">'
        f'{_icon("panel-left-close")}<span>Thu gọn</span></button>'
        '<div class="side-foot">'
        f'<span class="sf-ava" aria-hidden="true">{escape(chu)}</span>'
        f'<span class="sf-who"><b title="{escape(ten)}">{escape(ten)}</b>'
        f'<small>{escape(vai)}</small></span>'
        '<form method="post" action="/dang-xuat" class="sf-form" data-native>'
        f'<button class="sf-out" title="Đăng xuất">{_icon("log-out")}</button>'
        "</form></div>"
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


@lru_cache(maxsize=1)
def _ui_ver() -> str:
    """Vân tay của CSS+JS khung, in vào <meta name=ui-ver>.

    PJAX chỉ thay ruột .side/.main nên <head> (chứa toàn bộ <style>) KHÔNG bao
    giờ được cập nhật: một tab đang mở mà server đổi giao diện thì nó nhận
    markup mới nhưng vẫn dùng CSS cũ — layout vỡ mà không hiểu vì sao, cứ tưởng
    code sai. `applyDoc` so vân tay này, lệch thì nạp lại cả trang.

    Tính LƯỜI (lru_cache) chứ không phải hằng số module: `_NAV_JS` khai báo tận
    cuối file, sau hàm này. Uvicorn --reload nạp lại module là hash tự đổi theo.
    """
    return hashlib.blake2s(
        (_CSS + _NAV_JS).encode("utf-8"), digest_size=6
    ).hexdigest()


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
        f'<meta name="ui-ver" content="{_ui_ver()}">'
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
  /* hổ phách của chữ "CRM" cạnh logo (mẫu Kallet dùng --amber-400) — đủ sáng
     để nổi trên dải tím mà không chói như vàng nguyên bản */
  --brand-tag:#f7c65b;
  --in:#efe9f1; --out:#6f5a9c;
  /* Bong bóng tin MÌNH gửi ở màn Hội thoại — mẫu Kallet đổ dốc tím→hồng chứ
     không tô phẳng như --out. Dựng lại từ 3 màu nhấn sẵn có để dark mode chỉ
     phải khai lại đúng dòng này. */
  --grad-brand:linear-gradient(100deg,var(--accent) 0%,var(--accent2) 55%,var(--hot) 100%);
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
    --brand-tag:#e9b855;
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
  /* overflow:hidden chứ KHÔNG auto: nay chỉ <nav> cuộn, còn khối đáy
     (.side-bottom: nhóm Quản trị + tài khoản) phải đứng yên. Cả cột cùng cuộn
     thì cuộn xuống mục cuối là mất luôn avatar lẫn nút thu gọn. */
  position:sticky; top:0; align-self:flex-start; height:100vh; overflow:hidden;
  display:flex; flex-direction:column;
  padding:16px 12px; box-shadow:2px 0 12px rgba(111,90,156,.18);
}
/* ---------- logo (dựng theo mẫu Kallet) ----------
   Dải cao 56px kéo hết bề ngang cột (margin âm bù `padding:16px 12px` của
   .side) rồi tự đệm lại 16px — nhờ vậy vạch ngăn dưới chạm được mép menu.
   Ba mảnh: .logo (huy hiệu vuông) · .bname (viên thuốc trắng) · .btag (CRM). */
.brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:#fff;
  flex:0 0 auto;height:56px;margin:-16px -12px 10px;padding:0 16px;
  border-bottom:1px solid rgba(255,255,255,.10)}
.logo{width:28px;height:28px;border-radius:9px;background:#fff;color:var(--accent);
  display:grid;place-items:center;flex:0 0 auto;overflow:hidden;
  font-weight:800;font-size:12px;letter-spacing:-.02em;
  box-shadow:0 2px 6px rgba(43,34,48,.18)}
.logo img{width:100%;height:100%;object-fit:contain;display:block}
.bname{display:flex;align-items:center;background:#fff;color:var(--accent);
  border-radius:10px;padding:5px 11px;font-weight:800;font-size:14px;
  letter-spacing:-.01em;white-space:nowrap;
  box-shadow:0 2px 6px rgba(43,34,48,.18)}
.btag{font-weight:800;font-size:17px;letter-spacing:.2px;color:var(--brand-tag)}
/* min-height:0 là BẮT BUỘC cạnh flex:1 — mặc định min-height:auto không cho
   flex item co nhỏ hơn nội dung, nav sẽ đội khối đáy tụt khỏi màn thay vì cuộn */
/* scrollbar-gutter:stable — luôn chừa sẵn rãnh 6px kể cả lúc chưa cần cuộn, để
   mục trong <nav> và mục ở khối ghim (không có thanh cuộn) thẳng hàng mép phải.
   Lệch 6px giữa hai cụm là đủ làm khối ghim trông như một khu khác. */
.nav{display:flex;flex-direction:column;gap:2px;
  flex:1 1 auto;min-height:0;overflow-y:auto;scrollbar-gutter:stable;
  scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.25) transparent}
.nav::-webkit-scrollbar{width:6px}
.nav::-webkit-scrollbar-track{background:transparent}
.nav::-webkit-scrollbar-thumb{background:rgba(255,255,255,.22);border-radius:99px}
.nav::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,.35)}
/* Mép dưới mờ dần khi CÒN nội dung phía dưới (mẫu Kallet: .nav.more, class do
   _NAV_JS gắn). Không có nó thì mục cuối bị cắt ngang trông như hỏng, mà cũng
   chẳng ai biết là còn cuộn được — nhất là khi khối ghim che ngay bên dưới. */
.nav.more{-webkit-mask-image:linear-gradient(to bottom,#000 calc(100% - 24px),transparent);
  mask-image:linear-gradient(to bottom,#000 calc(100% - 24px),transparent)}
/* --gc = màu của nhóm đang chứa mục này (_MAU_NHOM in vào thẻ <details>).
   Đây là giá trị lùi cho mục không nằm trong nhóm nào. */
.nav,.side-bottom{--gc:rgba(255,255,255,.85)}
.nav-item{
  display:flex;align-items:center;gap:11px;padding:9px 10px;border-radius:9px;
  color:var(--side-tx);text-decoration:none;font-size:14px;font-weight:500;
}
/* Icon mang màu nhóm — đây mới là thứ làm menu dễ quét: 30 icon trắng như nhau
   thì phải đọc chữ mới biết mục nào, có màu thì nhớ được bằng mắt. */
.nav-item .ico,.nav-dept>summary .ico{color:var(--gc)}
.nav-item:hover{background:color-mix(in srgb,var(--gc) 22%,transparent);color:#fff}
/* Mục ĐANG CHỌN giữ nền trắng chữ tím (tương phản cao nhất), chỉ mượn màu nhóm
   làm quầng sáng. Icon phải về màu tím: pastel trên nền trắng là chìm nghỉm. */
.nav-item.on{background:#fff;color:var(--accent);font-weight:650;
  box-shadow:0 3px 12px color-mix(in srgb,var(--gc) 45%,transparent)}
.nav-item.on .ico{color:var(--accent)}
.ico{width:19px;height:19px;flex:0 0 auto}
/* tên nhóm menu (CRM / Bot Pancake) — mang luôn màu nhóm */
.nav-group{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--gc);opacity:.75;padding:12px 10px 4px}
/* vạch ngăn thay tên nhóm KHÔNG TÊN — hiện MENU_GROUPS không còn nhóm nào như
   vậy (Thông báo/Giám sát/Kho data đã gộp vào Quản trị), giữ cho lần sau */
.nav-sep{height:1px;background:rgba(255,255,255,.16);margin:12px 10px 8px}
/* nhóm menu XỔ/THU được (_NHOM_THU_GON — mọi nhóm có tên): tiêu đề nhóm
   thành <summary> bấm gập.
   ĐỘ NỔI ĐỔI THEO TRẠNG THÁI — mắt luôn bắt đúng thứ đang bấm được:
     · THU GỌN: cả cụm chỉ còn đúng dòng tiêu đề này -> chữ TRẮNG, ĐẬM, to hơn
       một chút. KHÔNG nền, KHÔNG viền: một khối trắng nằm giữa menu tối trông
       như mục đang chọn (.nav-item.on cũng nền trắng), gây nhầm.
     · XỔ RA: tiêu đề lùi về nhãn mờ như cũ, nhường sáng cho các bộ phận/mục
       con bên dưới (xem .nav-grp[open] ... ở dưới).
   GHIM ĐẦU KHUNG: summary position:sticky, thanh cuộn là <nav> còn khung chặn
   là chính <details> của nhóm -> cuộn tới đâu tiêu đề nhóm đó dán ở mép trên,
   khi <details> trôi hết thì nhóm sau tự đẩy nó lên thay chỗ. Nền frost chỉ
   bật lúc ĐANG DÍNH (class .stuck do _NAV_JS gắn) — không có nền thì mục cuộn
   qua đâm xuyên chữ, mà để nền sẵn thì lại thành cái khối màu như vừa bỏ. */
.nav-grp>summary{list-style:none;cursor:pointer;user-select:none;
  display:flex;align-items:center;gap:6px;
  padding:7px 10px;margin-top:11px;border-radius:9px;
  position:sticky;top:0;z-index:2;
  transition:background .15s,color .15s,opacity .15s}
.nav-grp>summary::-webkit-details-marker{display:none}
.nav-grp>summary.stuck{background:rgba(28,18,40,.55);
  -webkit-backdrop-filter:blur(9px);backdrop-filter:blur(9px);
  border-radius:0;margin-left:-12px;margin-right:-12px;padding-left:22px;
  padding-right:16px;box-shadow:0 7px 12px -9px rgba(0,0,0,.65)}
.grp-chev{margin-left:auto;font-size:10px;transition:transform .15s}
.nav-grp[open]>summary .grp-chev{transform:rotate(90deg)}
/* --- XỔ RA: tiêu đề nhạt đi --- */
.nav-grp[open]>summary{opacity:.55}
.nav-grp[open]>summary:hover{opacity:.85}
.nav-grp[open]>summary.stuck{opacity:1;color:color-mix(in srgb,var(--gc) 80%,#fff)}
/* --- THU GỌN: chỉ to + đậm lên, không vẽ nền --- */
.nav-grp:not([open])>summary{opacity:1;color:var(--gc);font-weight:800;
  font-size:12px;letter-spacing:.07em}
.nav-grp:not([open])>summary:hover{opacity:.8}
.nav-grp:not([open])>summary .grp-chev{margin-left:6px;opacity:1}
/* số mục đang bị gập bên trong — chỉ hiện lúc THU GỌN, để biết cụm này còn gì */
.grp-so{display:none}
.nav-grp:not([open])>summary .grp-so{display:inline-flex;margin-left:auto;
  align-items:center;justify-content:center;min-width:18px;height:16px;
  padding:0 5px;border-radius:8px;color:var(--gc);
  background:color-mix(in srgb,var(--gc) 26%,transparent);
  font-size:10px;font-weight:700;letter-spacing:0}
.nav-grp-kids{display:flex;flex-direction:column;gap:2px}
/* XỔ RA: mục con chỉ SÁNG hơn tiêu đề nhóm, KHÔNG thụt vào và không vạch dọc —
   menu chỉ rộng 236px, thụt 18px là mấy nhãn dài ("Đối soát thưởng", "Vai trò
   & quyền") cụt mất; tiêu đề nhóm mờ + mục sáng đã đủ phân cấp. */
.nav-grp[open]>.nav-grp-kids{margin:2px 0}
/* `:not(.on)` là BẮT BUỘC: mục đang xem có nền TRẮNG (.nav-item.on), bộ chọn
   này lại nặng ký hơn (.nav-grp+[open]+.nav-grp-kids+.nav-item) nên bỏ quên là
   nó đè cả chữ lẫn icon (stroke=currentColor) thành trắng -> trắng trên trắng,
   mục đang chọn biến thành vệt trắng trơn. Hover khai lại cho khỏi bị hụt. */
.nav-grp[open]>.nav-grp-kids>.nav-item:not(.on){color:rgba(255,255,255,.93)}
.nav-grp[open]>.nav-grp-kids>.nav-item:not(.on):hover{color:#fff}
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
.sm-link:hover,.sm-child:hover{color:#fff;
  background:color-mix(in srgb,var(--gc) 20%,transparent)}
/* chấm màu trong khối menu: đè .dot toàn cục (chấm live có animation) */
.sm-link .dot,.sm-child .dot{width:8px;height:8px;border-radius:50%;
  flex:0 0 auto;box-shadow:none;animation:none}
.sm-link.star{color:#ffd54f}
/* mục XỔ XUỐNG trong menu (Sale · Chăm sóc khách hàng — kiểu Kallet):
   summary trông như nav-item, con thụt vào có chấm màu + số đếm */
.nav-dept>summary{display:flex;align-items:center;gap:10px;padding:9px 10px;
  border-radius:10px;color:var(--side-tx);font-size:14px;font-weight:600;
  cursor:pointer;list-style:none;user-select:none}
.nav-dept>summary::-webkit-details-marker{display:none}
.nav-dept>summary:hover{background:color-mix(in srgb,var(--gc) 22%,transparent);
  color:#fff}
/* Bộ phận nặng hơn mục thường (600 vs 500) kể cả lúc thu: trong một nhóm đã xổ
   ra thì ĐÂY là cấp mắt phải bắt trước, mục phẳng chỉ là hàng ngang cấp dưới. */
.dept>summary.nav-item{font-weight:600}
/* đang XỔ: cả khối nhận nền tối mờ + viền nhẹ + SỌC HỔ PHÁCH bên trái để nổi
   hẳn khỏi phần menu còn lại — nhóm đã phóng ra thì bộ phận phải rõ hơn cả
   tiêu đề nhóm (tiêu đề lúc này chỉ còn là nhãn mờ .nav-grp[open]>summary).
   (phủ cả 2 khối: Sale = .nav-dept, CSKH = .dept; :not(.on) để summary đang
   active giữ nền trắng chữ tím của .nav-item.on, không bị chữ trắng đè) */
.nav-dept[open],.dept[open]{background:rgba(0,0,0,.22);
  border:1px solid rgba(255,255,255,.14);
  border-left:3px solid var(--gc);border-radius:12px;
  padding:2px 4px 8px;margin:4px 0;box-shadow:0 2px 10px rgba(0,0,0,.14)}
.nav-dept[open]>summary:not(.on),.dept[open]>summary:not(.on){
  color:#fff;font-weight:700}
.nav-dept[open]>summary:hover,.dept[open]>summary:hover{background:var(--side-on)}
.nd-chev{margin-left:auto;font-size:10px;opacity:.7;transition:transform .18s}
.nav-dept:not([open]) .nd-chev{transform:rotate(-90deg)}
.nd-group{font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--side-tx);opacity:.5;padding:8px 10px 3px 24px}
.nd-link{display:flex;align-items:center;gap:8px;padding:6px 10px 6px 24px;
  border-radius:8px;color:var(--side-tx);text-decoration:none;font-size:13px}
.nd-link:hover{color:#fff;background:color-mix(in srgb,var(--gc) 20%,transparent)}
.nd-link.on{background:#fff;color:var(--accent);font-weight:650}
.nd-link>span:not(.nd-dot):not(.nd-count){overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.nd-dot{width:8px;height:8px;border-radius:50%;flex:none}
.nd-count{margin-left:auto;font-size:11px;background:var(--side-on);
  border-radius:12px;padding:1px 8px;min-width:22px;text-align:center;flex:none}
.nd-link.on .nd-count{background:color-mix(in srgb,var(--accent) 14%,transparent)}
/* ---------- khối GHIM ở đáy menu: nút thu/phóng + tài khoản ----------
   Nằm NGOÀI <nav> nên không cuộn theo menu. Đây là "chân trang" của cột menu
   chứ KHÔNG chứa mục nghiệp vụ nào — mọi nhóm (kể cả Quản trị) đều ở trong
   vùng cuộn, đúng nếp mẫu Kallet.
   `flex:0 0 auto` + KHÔNG overflow: cả cột menu chỉ được có ĐÚNG MỘT thanh
   cuộn (ở <nav>) — cho khối này cuộn riêng là ra thanh thứ hai dính nhau.
   Viền + bóng đổ ngược lên (mẫu: .foot-btn) cho thấy danh sách trôi xuống dưới
   nó chứ không phải hết menu. */
.side-bottom{flex:0 0 auto;display:flex;flex-direction:column;padding-right:6px;
  border-top:1px solid rgba(255,255,255,.12);
  box-shadow:0 -10px 16px -10px rgba(0,0,0,.45)}
.foot-btn{margin:8px 0;display:flex;align-items:center;gap:11px;
  padding:9px 10px;border:1px solid rgba(255,255,255,.14);border-radius:9px;
  background:none;color:var(--side-tx);font:inherit;font-size:13px;
  font-weight:500;cursor:pointer;flex:0 0 auto}
.foot-btn:hover{background:var(--side-on);color:#fff}
.side-foot{display:flex;align-items:center;gap:9px;flex:0 0 auto;
  padding-top:10px;border-top:1px solid rgba(255,255,255,.10)}
.sf-ava{width:32px;height:32px;border-radius:50%;flex:0 0 auto;
  display:grid;place-items:center;background:#fff;color:var(--accent);
  font-weight:800;font-size:14px;box-shadow:0 2px 6px rgba(43,34,48,.18)}
.sf-who{min-width:0;flex:1 1 auto;display:flex;flex-direction:column;line-height:1.25}
.sf-who b{font-size:13px;font-weight:650;color:#fff;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sf-who small{font-size:10.5px;opacity:.7;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sf-form{flex:0 0 auto;display:flex}
.sf-out{display:grid;place-items:center;width:30px;height:30px;padding:0;
  border:none;border-radius:8px;background:none;color:var(--side-tx);
  cursor:pointer}
.sf-out:hover{background:var(--side-on);color:#fff}
/* ---------- menu THU về rail icon (bấm #navToggle, nhớ trong localStorage) ----
   Chỉ giấu CHỮ và co bề ngang — không đụng cấu trúc, nên bung ra là y như cũ.
   Con của khối bộ phận (nd-link/sm-link) không có icon nên trong rail phải ẩn
   hẳn; bấm vào tiêu đề bộ phận lúc đó thì _NAV_JS bung menu ra lại. */
.side.mini{flex-basis:66px;width:66px;padding:16px 8px}
.side.mini .brand{justify-content:center;margin:-16px -8px 10px;padding:0;gap:0}
.side.mini .bname,.side.mini .btag{display:none}
.side.mini .nav-item,.side.mini .nav-dept>summary{justify-content:center;
  gap:0;padding:9px 0}
.side.mini .nav-item>span,.side.mini .nav-dept>summary>span{display:none}
/* tiêu đề nhóm co thành vạch ngăn — vẫn thấy được ranh giới giữa các nhóm */
.side.mini .nav-grp>summary{height:1px;padding:0;margin:11px 8px 7px;
  font-size:0;background:rgba(255,255,255,.18);border-radius:0;box-shadow:none;
  position:static;backdrop-filter:none;-webkit-backdrop-filter:none}
.side.mini .grp-chev,.side.mini .grp-so{display:none}
.side.mini .nd-group,.side.mini .nd-link,.side.mini .nav-kids{display:none}
.side.mini .nav-dept[open],.side.mini .dept[open]{background:none;border:0;
  box-shadow:none;padding:0;margin:0}
.side.mini .foot-btn{justify-content:center;gap:0;padding:9px 0}
.side.mini .foot-btn>span{display:none}
.side.mini .foot-btn .ico{transform:rotate(180deg)}   /* thành "mở rộng" */
.side.mini .side-foot{flex-direction:column;gap:6px}
.side.mini .sf-who{display:none}
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

/* ---------- màn Hội thoại (port giao diện mẫu crmv2.kallet.vn) ----------
   BA cột nằm ngang, mỗi cột tự cuộn riêng, cả màn không bao giờ cuộn dọc:
     rail lọc 52px · danh sách 320px · khung chat (co giãn).
   KHÔNG có panel khách riêng — mẫu nhét hồ sơ khách vào ĐẦU KHUNG CHAT
   (hạng thẻ · điện thoại · mua cuối · tổng chi · fanpage) cho đỡ chật.
   Số đo giữ đúng bản mẫu; màu đổi hết sang biến gốc của dự án — mẫu dùng
   --surface-card/--surface-sunken/--brand-600/--pink-50, ở đây là
   --card/--in/--accent/--soft. */
/* `.content.full` là flex HÀNG và chỉ chờ đúng MỘT con (xem màn Tin nhắn).
   Màn này có thêm dải ghi chú phía trên nên phải bọc lại thành cột, không thì
   dải ghi chú với khung 3 cột đứng cạnh nhau. */
.ht-wrap{flex:1;min-width:0;display:flex;flex-direction:column}
.ht{display:flex;flex:1;min-height:0;width:100%}

/* CHƯA LÀM ĐƯỢC — nút/ô mẫu có nhưng dữ liệu hiện tại chưa dựng nổi. Viền đứt
   + mờ + con trỏ cấm để nhìn phát biết ngay, lý do nằm ở tooltip. Dùng chung
   một lớp cho mọi loại phần tử nên gỡ đánh dấu sau này chỉ là xoá 1 class. */
.ht-todo{opacity:.55;cursor:not-allowed !important;
  outline:1px dashed var(--border-strong,var(--sub));outline-offset:-2px}
.ht-todo:hover{background:transparent !important;color:var(--sub) !important;
  border-color:var(--border) !important}
/* Khối xổ liệt kê phần chưa làm, đứng ngay trên khung 3 cột */
.ht-note{flex:0 0 auto;background:var(--warn-bg);color:var(--text);
  border-bottom:1px solid var(--border);padding:9px 16px;font-size:12.5px}
.ht-note summary{cursor:pointer;color:var(--warn)}
.ht-note ul{margin:9px 0 4px;padding-left:20px}
.ht-note li{margin:3px 0;line-height:1.5}
.ht-note .note{margin:6px 0 0}

/* --- cột 1: rail lọc (chỉ icon, nhãn nằm ở tooltip) --- */
.ht-rail{flex:0 0 52px;display:flex;flex-direction:column;align-items:center;
  gap:4px;padding:12px 0;background:var(--soft);
  border-right:1px solid var(--border);overflow-y:auto}
.ht-rb{width:38px;height:38px;border:0;border-radius:11px;cursor:pointer;
  display:grid;place-items:center;position:relative;flex:0 0 auto;
  background:transparent;color:var(--sub)}
.ht-rb:hover{background:var(--card);color:var(--text)}
.ht-rb.on{background:var(--card);color:var(--accent);box-shadow:var(--shadow)}
.ht-rb .ico{width:19px;height:19px}
/* Huy hiệu SỐ chưa đọc đậu trên nút (mẫu để số, không phải chấm trơn) */
.ht-rb .rnum{position:absolute;top:1px;right:1px;min-width:15px;height:15px;
  line-height:15px;padding:0 3px;border-radius:999px;background:var(--err);
  color:#fff;font-size:9px;font-weight:700;text-align:center}
.ht-rsep{width:24px;height:1px;background:var(--border);margin:5px 0;flex:0 0 auto}

/* --- cột 2: danh sách hội thoại --- */
.ht-list{flex:0 0 320px;max-width:40%;min-width:0;background:var(--card);
  border-right:1px solid var(--border);display:flex;flex-direction:column;
  min-height:0}
/* Đầu cột: ô tìm + nút "Lọc theo". Hai tab Tất cả/Chưa đọc KHÔNG ở đây —
   mẫu đẩy chúng sang rail bên trái. */
.ht-lhead{flex:0 0 auto;padding:14px 14px 10px;display:flex;align-items:center;
  gap:8px}
.ht-lfind{position:relative;flex:1 1 auto;min-width:0}
.ht-lfind .ico{width:15px;height:15px;position:absolute;left:11px;top:50%;
  transform:translateY(-50%);color:var(--sub);pointer-events:none}
.ht-lfind input{width:100%;height:36px;border:1px solid var(--border);
  background:var(--soft);border-radius:10px;padding:0 12px 0 32px;font:inherit;
  font-size:13px;color:var(--text);outline:none}
.ht-lfind input:focus{border-color:var(--accent)}
.ht-lfilter{display:inline-flex;align-items:center;gap:6px;height:36px;
  padding:0 12px;border:1px solid var(--border);background:var(--card);
  color:var(--text);border-radius:10px;font:inherit;font-size:12.5px;
  font-weight:600;cursor:pointer;white-space:nowrap;flex:0 0 auto}
.ht-lfilter:hover{border-color:var(--accent);color:var(--accent)}
.ht-lfilter .ico{width:15px;height:15px}
.ht-lbody{flex:1 1 auto;min-height:0;overflow-y:auto}

/* Hàng hội thoại: avatar + khối 4 dòng (tên/giờ · tin/chưa đọc · fanpage/giai
   đoạn · cửa gửi tin) */
.ht-row{display:flex;align-items:center;gap:11px;padding:11px 16px;
  border-bottom:1px solid var(--border);border-left:3px solid transparent;
  cursor:pointer;text-decoration:none;color:inherit}
.ht-row:hover{background:var(--bg)}
/* Chưa đọc VÀ đang mở đều tô nền nhạt; khác nhau ở vạch trái + độ đậm chữ. */
.ht-row.unread{border-left-color:var(--accent);background:var(--soft)}
.ht-row.on{background:var(--soft);border-left-color:var(--hot)}
.ht-av{width:38px;height:38px;border-radius:50%;flex:0 0 auto;display:grid;
  place-items:center;font-weight:700;font-size:13px;background:var(--soft);
  color:var(--accent)}
.ht-row.unread .ht-av{background:var(--accent);color:#fff}
.ht-rmain{flex:1 1 auto;min-width:0}
.ht-r1{display:flex;align-items:flex-start;gap:7px}
.ht-name{font-weight:600;font-size:13.5px;color:var(--text);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;max-width:150px}
.ht-row.unread .ht-name{font-weight:700}
/* Mắt/bong bóng: đã xem · chưa xem · đã phản hồi */
.ht-seen{display:inline-flex;flex:0 0 auto;margin-top:1px;color:var(--sub)}
.ht-seen .ico{width:13px;height:13px}
.ht-seen.rep{color:var(--ok)}
.ht-seen.unseen{opacity:.65}
.ht-time{margin-left:auto;flex:0 0 auto;font-size:11px;color:var(--sub)}
.ht-r2{display:flex;align-items:center;gap:6px;margin-top:2px}
/* display:block là BẮT BUỘC — thẻ này là <span>, mà text-overflow chỉ ăn trên
   hộp block. Để inline là câu tin dài tràn hàng. */
.ht-msg{display:block;flex:1 1 auto;min-width:0;font-size:12px;color:var(--sub);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ht-row.unread .ht-msg{color:var(--text);font-weight:600}
.ht-unread{background:var(--err);color:#fff;font-size:10px;font-weight:700;
  min-width:18px;height:18px;line-height:18px;text-align:center;
  border-radius:999px;padding:0 5px;flex:0 0 auto}
.ht-r3{display:flex;align-items:center;gap:6px;margin-top:4px}
/* Cắt bằng ba chấm chứ không để tràn: fanpage tên dài ("Nha khoa … Cơ sở 2")
   mà không cắt thì chữ đè lên chip thẻ bên phải khi cột danh sách hẹp lại. */
.ht-fp{font-size:10.5px;color:var(--sub);min-width:0;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
/* Chip giai đoạn: nền lấy từ biến --c đặt inline (mỗi giai đoạn một màu) nên
   CSS khỏi liệt kê 12 lớp con. */
.ht-stage{margin-left:auto;flex:0 0 auto;font-size:9.5px;font-weight:700;
  padding:1px 8px;border-radius:999px;color:#fff;white-space:nowrap;
  background:var(--c,var(--accent))}
/* display:block bắt buộc — thẻ này là <span>, để inline thì margin-top không
   ăn và chip cửa dính sát dòng fanpage phía trên. */
.ht-r4{display:block;margin-top:5px}
/* "Cửa gửi tin" của Meta — mở (gõ tay tự do) hay khoá (chỉ mẫu đã duyệt).
   Mẫu dùng CHẤM tròn cùng màu chữ, không phải icon. */
.ht-door{display:inline-flex;align-items:center;gap:5px;font-size:10.5px;
  font-weight:700;border-radius:999px;padding:2px 9px;white-space:nowrap}
.ht-door i{width:6px;height:6px;border-radius:999px;background:currentcolor;
  flex:0 0 auto;display:block}
.ht-door.open{background:var(--ok-bg);color:var(--ok)}
.ht-door.tpl{background:var(--warn-bg);color:var(--warn)}
/* "unk" = kho thiếu mốc tin cuối của khách nên CHƯA tính được cửa. Phải xám —
   tô vàng như hết cửa là khẳng định một điều mình không biết. */
.ht-door.unk{background:var(--in);color:var(--sub)}

/* --- cột 3: khung chat --- */
.ht-chat{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;
  min-height:0;background:var(--bg)}
/* Đầu khung KIÊM hồ sơ khách: tên + hạng thẻ, rồi dải meta điện thoại · mua
   cuối · tổng chi · fanpage, rồi cụm nút thao tác. */
.ht-chead{flex:0 0 auto;display:flex;align-items:center;gap:12px;
  padding:11px 20px;background:var(--card);
  border-bottom:1px solid var(--border);flex-wrap:wrap}
.ht-chead .ht-av{width:40px;height:40px;font-size:14px}
.ht-cwho{flex:1 1 auto;min-width:0}
.ht-cline{display:flex;align-items:center;gap:8px}
/* Cắt ba chấm: khung chat hẹp lại thì tên khách dài đẩy chip hạng thẻ tràn
   ra ngoài đầu khung. */
.ht-cname{font-weight:600;font-size:15px;color:var(--text);min-width:0;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ht-tier{display:inline-flex;align-items:center;gap:4px;font-size:10.5px;
  font-weight:700;border-radius:999px;padding:2px 9px;background:var(--soft);
  color:var(--accent);flex:0 0 auto}
.ht-tier .ico{width:12px;height:12px}
.ht-cmeta{display:flex;align-items:center;gap:6px 14px;margin-top:3px;
  font-size:11.5px;color:var(--sub);flex-wrap:wrap}
.ht-cmeta b{color:var(--text);font-weight:600}
.ht-ctel{display:inline-flex;align-items:center;gap:4px;cursor:pointer;
  background:none;border:0;font:inherit;font-size:11.5px;color:var(--sub);
  padding:0}
.ht-ctel .num{color:var(--accent);font-weight:600}
.ht-ctel .ico{width:12px;height:12px}
.ht-ctel .ico.cp{width:11px;height:11px;opacity:.7}
.ht-cact{margin-left:auto;display:flex;align-items:center;gap:6px;flex:0 0 auto}
.ht-ic{width:34px;height:34px;border:1px solid var(--border);border-radius:9px;
  background:var(--card);color:var(--sub);cursor:pointer;display:grid;
  place-items:center;flex:0 0 auto}
.ht-ic:hover{border-color:var(--accent);color:var(--accent)}
.ht-ic .ico{width:16px;height:16px}
/* Nút "← Danh sách" — CHỈ có nghĩa ở bố cục một cột (<900px), nơi danh sách bị
   khung chat che mất. Màn rộng hai thứ đứng cạnh nhau nên giấu đi. */
.ht-back{display:none;text-decoration:none}
/* Nút chữ ở đầu khung (người phụ trách · Chưa đọc) — cùng chiều cao 34px */
.ht-cbtn{display:inline-flex;align-items:center;gap:6px;height:34px;
  padding:0 11px;border:1px solid var(--border);border-radius:9px;
  background:var(--card);color:var(--text);font:inherit;font-size:12.5px;
  font-weight:600;cursor:pointer;flex:0 0 auto;white-space:nowrap}
.ht-cbtn:hover{border-color:var(--accent)}
.ht-cbtn .ico{width:15px;height:15px;color:var(--sub)}
.ht-cbtn .mini{width:20px;height:20px;border-radius:50%;background:var(--soft);
  color:var(--accent);display:grid;place-items:center;font-size:10px;
  font-weight:700;flex:0 0 auto}

.ht-thread{flex:1 1 auto;min-height:0;overflow-y:auto;padding:20px 24px}
.ht-m{display:flex;margin-bottom:10px}
.ht-m.out{justify-content:flex-end}
.ht-bub{max-width:70%;padding:9px 12px;border-radius:14px;font-size:13px;
  line-height:1.4;white-space:pre-wrap;word-wrap:break-word;
  overflow-wrap:anywhere}
.ht-m.in .ht-bub{background:var(--in);color:var(--text);
  border-bottom-left-radius:4px}
.ht-m.out .ht-bub{background:var(--grad-brand);color:#fff;
  border-bottom-right-radius:4px}
.ht-mt{font-size:10px;margin-top:3px;color:var(--sub)}
.ht-m.out .ht-mt{text-align:right}
/* Dải ngày chen giữa luồng tin */
.ht-day{display:flex;align-items:center;gap:10px;margin:14px 0 12px;
  color:var(--sub);font-size:11px}
.ht-day::before,.ht-day::after{content:"";flex:1;height:1px;
  background:var(--border)}

/* Dải nhắc cửa gửi tin — KIÊM chỗ đứng của hai nút trợ lý.
   Trước đây hai nút nằm chung hàng ô soạn tin, chỉ có icon vuông 42px nên lẫn
   vào nút Gửi, nhìn không ra là làm gì. Đưa lên đây thì có chỗ hiện CHỮ, và
   hàng này vốn đã là hàng "trạng thái" nên đọc liền mạch: còn bao lâu gõ tự
   do → có thể nhờ máy soạn hộ. `flex-wrap` cho màn hẹp tự xuống dòng. */
.ht-win{flex:0 0 auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap;
  padding:9px 20px 0;background:var(--card);
  border-top:1px solid var(--border)}
.ht-wpill{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;
  font-weight:600;border-radius:999px;padding:4px 11px;flex:0 0 auto}
.ht-wpill .ico{width:13px;height:13px}
.ht-wpill.open{background:var(--ok-bg);color:var(--ok)}
.ht-wpill.tpl{background:var(--warn-bg);color:var(--warn)}
.ht-wpill.unk{background:var(--in);color:var(--sub)}
/* Đẩy cụm nút trợ lý sang phải, tách khỏi chip cửa và dòng kết quả */
.ht-wgap{flex:1 1 auto;min-width:8px}
.ht-tool{display:inline-flex;align-items:center;gap:6px;height:30px;
  padding:0 11px;border:1px solid var(--border);border-radius:9px;
  background:var(--card);color:var(--text);font:inherit;font-size:12px;
  font-weight:600;cursor:pointer;flex:0 0 auto;white-space:nowrap}
.ht-tool:hover{border-color:var(--accent);color:var(--accent)}
.ht-tool .ico{width:15px;height:15px;flex:0 0 auto}
.ht-tool.hint .ico{color:var(--warn)}
.ht-tool.lib .ico{color:var(--accent)}
.ht-tool:disabled{cursor:not-allowed}

.ht-composer{flex:0 0 auto;display:flex;gap:8px;align-items:center;
  padding:10px 20px 14px;background:var(--card)}
.ht-composer input{flex:1 1 auto;min-width:0;height:42px;
  border:1px solid var(--border);background:var(--soft);border-radius:10px;
  padding:0 14px;font:inherit;font-size:13.5px;color:var(--text);outline:none}
.ht-composer input:focus{border-color:var(--accent)}
.ht-cico{width:42px;height:42px;border:1px solid var(--border);
  border-radius:10px;background:var(--card);cursor:pointer;display:grid;
  place-items:center;flex:0 0 auto;color:var(--sub)}
.ht-cico:hover{border-color:var(--accent)}
.ht-cico .ico{width:18px;height:18px}
.ht-cico.hint{color:var(--warn)}
.ht-cico.lib{color:var(--accent)}
.ht-send{width:46px;height:42px;border:0;border-radius:10px;
  background:var(--grad-brand);color:#fff;cursor:pointer;display:grid;
  place-items:center;flex:0 0 auto;box-shadow:var(--shadow-lg)}
.ht-send .ico{width:17px;height:17px}
/* Ngoài cửa 24 giờ: Meta khoá tin tự do -> giấu ô gõ tay, chỉ chừa nút mẫu */
.ht-locked{flex:0 0 auto;margin:0 20px 14px;padding:11px 14px;border-radius:12px;
  background:var(--warn-bg);color:var(--warn);font-size:12.5px;display:flex;
  align-items:center;gap:9px}
.ht-locked .ico{width:16px;height:16px;flex:0 0 auto}

/* Chưa chọn hội thoại nào: khung chat nhường chỗ cho một lời nhắc */
.ht-empty{flex:1 1 auto;display:grid;place-items:center;text-align:center;
  color:var(--sub);padding:40px}

/* --- màn Hội thoại, khổ VỪA (900–1200px) ---
   Ba cột vẫn đứng cạnh nhau nhưng cột chat chỉ còn 236 (menu) + 52 (rail) +
   320 (danh sách) trừ đi -> ~450px. Không rút bớt thì đầu khung và dải công cụ
   xuống dòng lung tung. Ngưỡng 900px bên dưới mới đổi hẳn bố cục. */
@media (max-width:1200px){
  .ht-list{flex:0 0 272px}
  /* Nút đầu khung bỏ NHÃN CHỮ, chừa icon — nghĩa đầy đủ vẫn nằm ở tooltip.
     `font-size:0` là cách duy nhất giấu được chữ TRẦN (không có thẻ bọc để
     mà display:none); con nào vẫn cần chữ thì tự đặt lại cỡ. */
  .ht-cact .ht-cbtn{font-size:0;gap:0;padding:0 8px}
  .ht-cact .ht-cbtn .mini{font-size:10px}
  /* Thanh đẩy phải biến mất: nó là `flex:1 1 auto` nên khi cụm nút trợ lý
     xuống dòng, nó vẫn chiếm hết dòng trên -> chip cửa dính mép trái rồi chừa
     một khoảng trắng to đúng bằng nửa dải. Bỏ nó thì các mục chảy liền nhau. */
  .ht-wgap{display:none}
  .ht-win{row-gap:8px;padding-bottom:2px}
  .ht-tool{padding:0 9px}
}

/* ---------- co theo màn hình nhỏ ---------- */
@media (max-width:900px){
  body{flex-direction:column}
  .side{width:100%;flex:none;height:auto;position:static;padding:10px 12px;
    flex-direction:row;align-items:center;gap:12px}
  /* màn hẹp: menu nằm ngang -> logo bỏ dải 56px + vạch ngăn + margin âm,
     viên thuốc tên co lại nhường chỗ cho hàng icon */
  .brand{height:auto;margin:0;padding:0;border-bottom:0;gap:8px}
  .bname{padding:4px 9px;font-size:13px}
  .btag{font-size:15px}
  /* màn hẹp: giấu tên trong topbar, giữ nút Đăng xuất */
  .su-info{display:none}
  .nav{flex-direction:row;overflow-x:auto;gap:4px;margin-left:auto}
  .nav-item span{display:none}
  .nav-item{padding:9px 12px}
  .nav-item.on{box-shadow:inset 0 -3px 0 var(--accent)}
  /* màn hẹp menu nằm ngang: khối xổ không hợp — ẩn, hiện link phẳng dự phòng */
  .dept{display:none}
  .mobile-only{display:flex}
  /* nhóm xổ/thu: trải phẳng vào hàng ngang (display:contents bỏ hộp bọc, các
     mục thành con trực tiếp của .nav). _NAV_JS bỏ qua màn hẹp nên nhóm luôn ở
     trạng thái `open` server in ra -> không lo con bị <details> giấu mất. */
  .nav-grp,.nav-grp-kids{display:contents}
  .grp-chev,.grp-so{display:none}
  /* menu nằm ngang: bỏ khoảng cách trên + nền của tiêu đề nhóm (dựng cho cột
     dọc), kẻo mỗi nhãn nhóm bị đẩy lệch khỏi hàng icon */
  .nav-grp>summary{margin-top:0;padding:9px 4px;background:none;box-shadow:none}
  /* menu đã nằm ngang thì rail icon vô nghĩa: giấu nút thu gọn, và nếu class
     `mini` còn sót lại từ lúc màn rộng (đổi cỡ cửa sổ giữa chừng) thì vô hiệu
     hoá nó ở đây — _NAV_JS cũng bỏ qua mini trên màn hẹp. */
  .foot-btn{display:none}
  .side.mini{flex-basis:auto;width:100%;padding:10px 12px}
  .side.mini .brand{margin:0;justify-content:flex-start}
  .side.mini .bname{display:flex}
  .side.mini .btag{display:inline}
  /* menu nằm ngang: khối ghim nối tiếp hàng icon chứ không phải cột dưới đáy
     (nhóm Quản trị trong đó đã display:contents nên trải thẳng vào hàng) */
  .side-bottom{flex-direction:row;align-items:center;gap:4px;
    border-top:0;box-shadow:none;padding:0;margin:0}
  .side-foot{flex:0 0 auto;border-top:0;padding-top:0;margin-left:6px}
  .sf-who{display:none}
  .topbar,.tabs{padding-left:16px;padding-right:16px}
  .content{padding:16px}
  .inbox{flex-direction:column}
  .inbox-list{flex:0 0 auto;max-height:38vh;border-right:0;
    border-bottom:1px solid var(--border)}
  /* Màn Hội thoại hẹp: MỘT cột kiểu Messenger/Zalo, không phải hai khung chồng
     nhau. Xếp chồng thì danh sách 34vh và chat phần còn lại đều bẹp, không cái
     nào dùng được. Ở đây: chưa chọn -> cả màn là danh sách; chọn rồi -> cả màn
     là khung chat, quay lại bằng nút ← ở đầu khung.
     Trạng thái do server đánh dấu bằng lớp `.chon` trên `.ht` (views/crm.py),
     không cần JS: mỗi lần chọn/quay lại là một lượt điều hướng thật. */
  .ht{flex-direction:column}
  .ht-rail{flex:0 0 auto;flex-direction:row;justify-content:flex-start;
    gap:4px;padding:8px 10px;border-right:0;
    border-bottom:1px solid var(--border);overflow-x:auto}
  .ht-rsep{width:1px;height:24px;margin:0 4px}
  .ht-list{flex:1 1 auto;max-width:none;min-height:0;border-right:0;
    border-bottom:0}
  /* Chưa chọn: giấu khung chat — lời nhắc "chọn một hội thoại BÊN TRÁI" vô
     nghĩa khi danh sách đang nằm ngay trên chỗ nó. */
  .ht-chat{display:none}
  /* Đã chọn: rail + danh sách nhường cả màn cho khung chat */
  .ht.chon .ht-rail,.ht.chon .ht-list{display:none}
  .ht.chon .ht-chat{display:flex}
  .ht-back{display:grid}
  .ht-chead{padding:11px 14px}
  .ht-thread{padding:16px 14px}
  .ht-win,.ht-composer{padding-left:14px;padding-right:14px}
}

/* --- điện thoại (<560px): đầu khung chat còn ~330px, không đủ cho 5 nút.
   Giấu những nút CHƯA LÀM ĐƯỢC (viền đứt, bấm không ra gì) và chừa lại nút
   thật: người phụ trách + mở bên Pancake. --- */
@media (max-width:560px){
  .ht-cact button.ht-todo{display:none}
  .ht-tier{display:none}
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

/* ---------- màn Khách hàng (port giao diện mẫu crmv2.kallet.vn) ----------
   Bố cục dọc: 5 ô đếm bấm được · dải bộ lọc · thẻ bảng (đầu bảng + bảng +
   chân phân trang). Số đo giữ đúng bản mẫu; màu đổi hết sang biến gốc —
   mẫu dùng --surface-card/--surface-sunken/--brand-600, ở đây là
   --card/--soft/--accent.
   Dùng LẠI của màn Hội thoại: `.ht-todo` (đánh dấu chưa làm được), `.ht-note`
   (khối liệt kê), `.ht-door` (chip cửa gửi tin) — cùng một ngôn ngữ hình. */
.kh-tiles{display:flex;gap:12px;margin-bottom:14px;flex-wrap:wrap}
.kh-tile{flex:1 1 150px;min-width:0;text-align:left;text-decoration:none;
  background:var(--card);border-radius:14px;padding:14px 16px 14px 18px;
  position:relative;overflow:hidden;box-shadow:var(--shadow);
  border:1px solid transparent}
.kh-tile:hover{border-color:var(--border)}
.kh-tile.on{outline:2px solid var(--c,var(--accent));outline-offset:-1px}
.kh-tile b{position:absolute;left:0;top:0;bottom:0;width:5px;
  background:var(--c,var(--accent))}
.kh-tile .n{font-weight:800;font-size:24px;line-height:1.1;color:var(--c,var(--accent))}
.kh-tile .l{font-size:12px;color:var(--sub);margin-top:3px}

/* --- dải bộ lọc: mọi ô cùng cao 34px, tự xuống hàng khi hẹp --- */
.kh-filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center;
  margin-bottom:14px}
.kh-filters select,.kh-filters .kh-find,.kh-filters .kh-spend,
.kh-filters .kh-btn{height:34px;border:1px solid var(--border);
  background:var(--card);border-radius:9px;font-size:12.5px;color:var(--text);
  font-family:inherit}
.kh-filters select{padding:0 8px;max-width:200px}
.kh-find{display:flex;align-items:center;gap:6px;padding:0 10px;min-width:240px;
  flex:1 1 240px;max-width:340px}
.kh-find .ico{width:15px;height:15px;color:var(--sub);flex:0 0 auto}
.kh-find input{flex:1;min-width:0;border:0;background:transparent;outline:none;
  font:inherit;font-size:12.5px;color:var(--text)}
.kh-spend{display:flex;align-items:center;gap:5px;padding:0 10px;
  color:var(--sub);font-size:12px}
.kh-spend input{width:52px;height:24px;border:1px solid var(--border);
  background:var(--bg);border-radius:6px;padding:0 6px;font:inherit;
  font-size:12px;color:var(--text)}
.kh-btn{display:inline-flex;align-items:center;gap:6px;padding:0 12px;
  font-weight:600;cursor:pointer}
.kh-btn:hover{border-color:var(--accent)}
.kh-btn .ico{width:15px;height:15px}
.kh-btn.go{background:var(--grad-brand);color:#fff;border-color:transparent}
.kh-clear{display:inline-flex;align-items:center;gap:5px;height:34px;
  padding:0 8px;font-size:12.5px;font-weight:600;text-decoration:none;
  color:var(--accent)}
.kh-clear.off{color:var(--sub);opacity:.5;pointer-events:none}
.kh-clear .ico{width:14px;height:14px}
.kh-sp{flex:1 1 auto}

/* --- thẻ bảng --- */
.kh-card{background:var(--card);border:1px solid var(--border);
  border-radius:14px;overflow:hidden}
.kh-head{display:flex;align-items:center;justify-content:space-between;gap:10px;
  padding:10px 16px;border-bottom:1px solid var(--border);flex-wrap:wrap}
.kh-head .cnt{font-size:12px;color:var(--sub)}
.kh-head .acts{display:flex;align-items:center;gap:8px}
.kh-hbtn{display:inline-flex;align-items:center;gap:5px;height:30px;padding:0 10px;
  border:1px solid var(--border);background:var(--card);color:var(--text);
  border-radius:8px;font:inherit;font-size:12px;font-weight:600;cursor:pointer}
.kh-hbtn .ico{width:14px;height:14px}
.kh-tblwrap{overflow-x:auto}
.kh-tbl{width:100%;border-collapse:collapse;font-size:13px}
.kh-tbl th{padding:10px 12px;font-weight:600;font-size:11.5px;text-align:left;
  color:var(--sub);border-bottom:1px solid var(--border);white-space:nowrap}
.kh-tbl td{padding:10px 12px;vertical-align:top}
.kh-tbl tbody tr{border-bottom:1px solid var(--border)}
.kh-tbl tbody tr:hover{background:var(--soft)}
/* cột số căn phải: `td.num,th.num` toàn cục lo phần căn lề, ở đây chỉ thêm nét */
.kh-tbl .money{text-align:right;font-weight:600;color:var(--text);white-space:nowrap}
.kh-tbl .rong{padding:26px 12px;text-align:center;color:var(--sub)}
/* ô "Khách": tên đậm · dòng phụ SĐT · fanpage · chip cửa gửi tin */
.kh-name{font-weight:600;color:var(--text);text-decoration:none}
.kh-name:hover{text-decoration:underline}
.kh-sub{font-size:11px;color:var(--sub);margin-top:1px}
.kh-tel{color:var(--accent);font-weight:600;cursor:pointer;border:0;
  background:none;font:inherit;font-size:11px;padding:0}
.kh-tel:hover{text-decoration:underline}
.kh-r4{display:block;margin-top:5px}
/* dòng phụ nhạt dưới ô ngày (vd "549 ngày trước", tên người chăm) */
.kh-nho{font-size:10.5px;color:var(--sub);opacity:.85}
.kh-none{font-style:italic;color:var(--sub);font-size:12px}
/* pill tình trạng chăm sóc */
.kh-st{display:inline-flex;align-items:center;font-size:11px;font-weight:600;
  border-radius:999px;padding:3px 10px;white-space:nowrap}
.kh-st.active{background:var(--ok-bg);color:var(--ok)}
.kh-st.fading{background:var(--warn-bg);color:var(--warn)}
.kh-st.sleep{background:var(--in);color:var(--sub)}
.kh-st.chua{background:var(--soft);color:var(--accent)}
/* pill hạng thẻ (C1) — nền/chữ do voucher_service.mat_hang() gắn inline vì mỗi
   hạng một cặp màu; ở đây chỉ lo hình khối cho đồng bộ với .kh-st */
.kh-tier{display:inline-flex;align-items:center;gap:4px;font-size:11px;
  font-weight:700;border-radius:999px;padding:2px 9px;white-space:nowrap}
/* cụm 3 nút thao tác cuối hàng */
.kh-acts{display:flex;align-items:center;gap:6px;justify-content:flex-end}
.kh-ic{width:30px;height:30px;border:1px solid var(--border);border-radius:8px;
  background:var(--card);color:var(--sub);display:grid;place-items:center;
  flex:0 0 auto;cursor:pointer}
.kh-ic:hover{border-color:var(--accent);color:var(--accent)}
.kh-ic .ico{width:14px;height:14px}
.kh-ic.go{background:var(--grad-brand);color:#fff;border-color:transparent;
  box-shadow:var(--shadow)}
.kh-ic.go:hover{color:#fff;filter:brightness(1.05)}
/* --- chân bảng: số dòng / trang + nút lùi-tiến --- */
.kh-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;
  padding:11px 16px;border-top:1px solid var(--border);flex-wrap:wrap;
  font-size:12.5px;color:var(--sub)}
.kh-foot select{height:30px;border:1px solid var(--border);background:var(--card);
  border-radius:8px;padding:0 8px;font:inherit;font-size:12.5px;color:var(--text)}
.kh-pager{display:flex;align-items:center;gap:6px}
.kh-pg{width:32px;height:32px;border:1px solid var(--border);border-radius:8px;
  background:var(--card);color:var(--text);display:grid;place-items:center;
  text-decoration:none}
.kh-pg:hover{border-color:var(--accent)}
.kh-pg.off{color:var(--sub);opacity:.5;pointer-events:none}
.kh-pg .ico{width:16px;height:16px}
/* Toast "đã chép số" — hiện giữa đáy màn 1,6 giây rồi tự tắt (xem _KH_JS) */
.kh-toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);
  z-index:200;background:var(--text);color:var(--card);font-size:12.5px;
  font-weight:600;padding:9px 16px;border-radius:999px;box-shadow:var(--shadow-lg);
  opacity:0;pointer-events:none;transition:opacity .18s}
.kh-toast.on{opacity:1}
@media (max-width:900px){
  .kh-find{max-width:none}
  .kh-filters select{max-width:none;flex:1 1 150px}
}

/* ---------- C7 · Đơn hàng (app/web/views/don_hang.py) ----------
   Màn này mượn nguyên bộ .kh-* ở trên (thẻ chỉ số · dải lọc · bảng · chân
   trang) — dưới đây CHỈ là phần mẫu có riêng ở màn Đơn hàng. */
/* khoảng thời gian: nhãn kỳ + select phủ trong suốt lên trên (giữ menu gốc của
   trình duyệt, khỏi tự dựng lịch — bấm đâu cũng ra danh sách kỳ) */
.dh-range{position:relative;display:inline-flex;align-items:center;gap:6px;
  height:34px;padding:0 10px;border:1px solid var(--border);border-radius:9px;
  background:var(--card);font-size:12.5px;color:var(--text)}
.dh-range .ico{width:14px;height:14px;color:var(--sub)}
.dh-range b{font-weight:600;white-space:nowrap}
.dh-range select{position:absolute;inset:0;width:100%;height:100%;opacity:0;
  border:0;cursor:pointer}
.dh-day{display:inline-flex;align-items:center;gap:5px;height:34px;padding:0 10px;
  border:1px solid var(--border);border-radius:9px;background:var(--card);
  font-size:11.5px;color:var(--sub)}
.dh-day input{border:0;background:transparent;font:inherit;font-size:12px;
  color:var(--text);outline:none;width:120px}
/* mã đơn + tiêu đề cột bấm được để đổi sắp xếp */
.dh-ma{font-weight:700;color:var(--accent);text-decoration:none;white-space:nowrap}
.dh-ma[href]{text-decoration:underline dotted;text-underline-offset:3px}
.dh-sort{color:inherit;text-decoration:none}
.dh-sort:hover{color:var(--accent)}
.dh-tbl td{vertical-align:middle}
.dh-tbl .money{text-align:right}
.dh-0{color:var(--sub);font-weight:600}
/* viên trạng thái/phân loại — mỗi trục một họ màu, đọc lướt là phân biệt được */
.dh-pill{display:inline-flex;align-items:center;font-size:10.5px;font-weight:600;
  border-radius:999px;padding:3px 9px;white-space:nowrap}
.dh-pill.mo{background:var(--in);color:var(--sub)}
.dh-pill.tin{background:var(--in);color:var(--out)}
.dh-pill.cho{background:var(--warn-bg);color:var(--warn)}
.dh-pill.xong{background:var(--ok-bg);color:var(--ok)}
.dh-pill.hong{background:var(--err-bg);color:var(--err)}
.dh-pill.no{background:var(--soft);color:var(--sub)}
.dh-pill.ads{background:var(--in);color:var(--out)}
.dh-pill.lm-new{background:var(--soft);color:var(--accent)}
.dh-pill.lm-repurchase{background:var(--ok-bg);color:var(--ok)}
.dh-pill.lm-upsell{background:var(--hot-bg);color:var(--hot)}
.dh-pill.lm-exchange{background:var(--warn-bg);color:var(--warn)}
.dh-pill.cs-cham_soc{background:var(--soft);color:var(--accent)}
.dh-pill.cs-tu_nhien{background:var(--in);color:var(--sub)}
/* thanh tổng nằm cùng hàng với "đang xem x–y / n" */
.dh-sum{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}
.dh-sum span{display:flex;align-items:baseline;gap:5px;font-size:11.5px;
  color:var(--sub)}
.dh-sum b{font-size:15px;font-weight:800;color:var(--text)}
.dh-sum b.ok{color:var(--ok)}
.dh-scope{background:var(--warn-bg);border-radius:10px;padding:9px 12px;
  margin-top:10px}
/* popover chọn cột xuất — hai bản (dải lọc mở xuống, thanh nổi mở lên) */
.dh-wrap{position:relative;display:inline-flex}
.dh-pop{display:none;position:absolute;top:calc(100% + 8px);right:0;width:360px;
  max-width:calc(100vw - 48px);background:var(--card);color:var(--text);
  border:1px solid var(--border);border-radius:12px;padding:12px;
  box-shadow:var(--shadow-lg);z-index:80;text-align:left}
.dh-pop.up{top:auto;bottom:calc(100% + 10px)}
.dh-pop.on{display:block}
.dh-pop-h{display:flex;align-items:center;justify-content:space-between;gap:8px;
  margin-bottom:8px;font-size:11.5px;font-weight:700;color:var(--sub)}
.dh-pop-h a{color:var(--accent);text-decoration:none;font-weight:600}
.dh-cols{max-height:258px;overflow-y:auto;display:grid;
  grid-template-columns:1fr 1fr;gap:1px 10px}
.dh-cols label{display:flex;align-items:center;gap:7px;min-width:0;
  font-size:12px;padding:4px 3px;border-radius:6px;cursor:pointer}
.dh-cols span{min-width:0;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.dh-go{width:100%;border:0;background:var(--grad-brand);color:#fff;font:inherit;
  font-size:12.5px;font-weight:700;padding:9px 12px;border-radius:9px;
  cursor:pointer;margin-top:8px}
/* thanh nổi khi tích chọn đơn — 3 luật của mẫu: không tràn ngang, không đè
   menu trái (--dhL = bề rộng sidebar), không che chân phân trang */
.dh-bar{position:fixed;left:var(--dhL,12px);right:12px;bottom:18px;margin:0 auto;
  width:max-content;max-width:var(--dhMax,calc(100vw - 24px));display:none;
  align-items:center;justify-content:center;gap:8px 12px;flex-wrap:wrap;
  background:var(--text);color:var(--card);border-radius:14px;padding:10px 14px;
  box-shadow:var(--shadow-lg);z-index:90}
.dh-bar-n{font-size:13px;font-weight:700;white-space:nowrap}
.dh-bar-o{display:none;align-items:center;font-size:11.5px;font-weight:700;
  border-radius:999px;padding:3px 9px;background:rgba(255,255,255,.16)}
.dh-bar-all{border:1px solid rgba(255,255,255,.28);background:rgba(255,255,255,.08);
  color:inherit;font:inherit;font-size:12px;font-weight:600;padding:6px 11px;
  border-radius:8px;cursor:pointer;white-space:nowrap}
.dh-bar-vach{width:1px;height:20px;background:rgba(255,255,255,.2)}
.dh-bar-btn{display:inline-flex;align-items:center;gap:6px;border:0;
  background:transparent;color:inherit;font:inherit;font-size:12.5px;
  font-weight:600;padding:7px 12px;border-radius:9px;cursor:pointer;
  white-space:nowrap}
.dh-bar-btn.off{opacity:.45;cursor:not-allowed}
.dh-bar-btn .ico{width:15px;height:15px}
.dh-bar-x{border:0;background:transparent;color:inherit;opacity:.7;font-size:18px;
  line-height:1;cursor:pointer;padding:0 4px}
/* popover trong thanh nổi nằm trên nền tối — trả lại nền sáng cho dễ đọc */
.dh-bar .dh-pop{background:var(--card);color:var(--text)}

/* ---------- C1 · Voucher (app/web/views/uu_dai.py) ---------- */
.vc-tiles{display:flex;gap:12px;margin-bottom:14px;flex-wrap:wrap}
.vc-tile{flex:1 1 160px;min-width:0;position:relative;overflow:hidden;
  border-radius:14px;padding:14px 16px 13px 18px;text-decoration:none;
  background:var(--card);box-shadow:var(--shadow);display:block}
.vc-tile.warn{background:var(--warn-bg);box-shadow:none}
.vc-tile.on{outline:2px solid var(--c,var(--accent));outline-offset:-1px}
.vc-vach{position:absolute;left:0;top:0;bottom:0;width:5px}
.vc-num{font-weight:800;font-size:24px;line-height:1.1}
.vc-lbl{font-size:11.5px;color:var(--sub);margin-top:3px}
.vc-sub{font-size:10.5px;color:var(--sub);opacity:.8;margin-top:2px}
.vc-form{background:var(--card);border:1px solid var(--accent);border-radius:12px;
  padding:14px 16px;margin-bottom:16px;box-shadow:var(--shadow)}
.vc-form-t{font-size:13px;font-weight:700;margin-bottom:10px}
.vc-form-r{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
.vc-form-r label{display:flex;flex-direction:column;gap:4px;font-size:11.5px;
  color:var(--sub);flex:1 1 150px}
.vc-form-r input{height:34px;border:1px solid var(--border);background:var(--bg);
  border-radius:9px;padding:0 10px;font:inherit;font-size:13px;color:var(--text)}
/* mã voucher: bấm là chép — trông như chữ nhưng phải rõ là bấm được */
.vc-ma{display:inline-flex;align-items:center;gap:5px;border:0;background:none;
  font:inherit;font-weight:700;color:var(--accent);cursor:pointer;padding:0}
.vc-ma .ico{width:12px;height:12px;opacity:.6}
.vc-lech{margin-left:5px;cursor:help;color:var(--warn);font-weight:700}
.vc-inline{display:flex;gap:6px;justify-content:flex-end}
.vc-inline input{height:30px;width:130px;border:1px solid var(--border);
  border-radius:8px;padding:0 8px;font:inherit;font-size:12px;background:var(--card)}
.vc-inline .kh-btn{height:30px}

/* ---------- C1 · Hạng thẻ ---------- */
.ht-cots{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap}
.ht-cot{flex:1 1 120px;min-width:0;text-align:center;border-radius:14px;
  padding:16px 10px;text-decoration:none}
.ht-cot .ic{font-size:24px;line-height:1}
.ht-cot .n{font-weight:800;font-size:24px;margin-top:6px}
.ht-cot .l{font-size:11.5px;font-weight:600;margin-top:2px}
.ht-cot.chua{background:var(--soft);border:1.5px dashed var(--border)}
.ht-cot.chua .n,.ht-cot.chua .l{color:var(--sub)}
.ht-cot.chua .l{font-style:italic}
.ht-warn{background:var(--warn-bg);border-radius:16px;padding:16px 18px;
  margin-bottom:16px}
.ht-warn-h{display:flex;align-items:center;gap:12px;flex-wrap:wrap;
  font-size:15px;font-weight:700;color:var(--warn)}
.ht-warn-h .kh-btn{margin-left:auto;background:var(--card)}
.ht-warn p{font-size:12.5px;line-height:1.55;margin:10px 0 0;max-width:640px}
.ht-warn .ht-cam{font-weight:700;color:var(--err)}
.ht-chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.ht-chip{display:inline-flex;align-items:center;gap:6px;background:var(--card);
  border-radius:10px;padding:7px 12px;font-size:12px;color:var(--sub)}
.ht-chip.off{background:var(--soft);border:1px dashed var(--border);
  font-style:italic}
.ht-h{display:flex;align-items:center;justify-content:space-between;gap:12px;
  font-size:15px;font-weight:700;margin-bottom:14px}
/* `hz-` chứ KHÔNG phải `ht-` như cả khối này: `.ht-row` đã là hàng hội thoại
   của màn Hội thoại (xem mục "cột 2"), mà khối này nằm sau nên từng đè lên nó
   — hàng hội thoại bị bọc viền kín, bo tròn, vạch nhấn "chưa đọc" teo còn 1px.
   Hai màn không liên quan gì nhau thì không được dùng chung tên lớp. */
.hz-rows{display:flex;flex-direction:column;gap:8px}
.hz-row{display:flex;align-items:center;gap:12px;border:1px solid var(--border);
  border-radius:11px;padding:9px 14px;flex-wrap:wrap}
.hz-row .ic{font-size:18px}
.hz-row .ten{font-weight:600;font-size:13px;width:110px;flex:0 0 auto}
.hz-row .tu{font-size:11.5px;color:var(--sub)}
.hz-row .mo{font-size:12px;color:var(--sub);flex:1 1 auto}
/* T3 — ngưỡng chỉ đọc ở đây, nên đầu khối chỉ còn cặp nút "Sửa" + "Tính lại". */
.ht-hnut{display:flex;align-items:center;gap:8px;flex:0 0 auto}
.ht-hnut form{margin:0}
.ht-in{width:140px;height:32px;display:inline-flex;align-items:center;
  justify-content:flex-end;border:1px solid var(--border);background:var(--soft);
  border-radius:8px;padding:0 10px;font:inherit;font-size:13px;color:var(--text)}
/* "chưa điền" phải là CHỮ màu cam, không phải số 0 — xem luật B3.3 của mẫu */
.ht-chua{color:var(--warn);font-style:normal;font-weight:600;font-size:12px}
.ht-qlrow{display:flex;gap:12px;align-items:flex-start;border:1px solid
  var(--border);border-radius:12px;padding:11px 14px;margin-bottom:9px}
.ht-qlrow .ten{flex:0 0 140px;font-weight:700;font-size:13px}
.ht-qlrow .ds{flex:1 1 auto;min-width:0;display:flex;flex-wrap:wrap;gap:7px}
.ht-ql{display:inline-flex;align-items:center;gap:6px;border-radius:9px;
  padding:5px 11px;font-size:12px}

/* ---------- C2 · Lương · Thưởng · Đối soát (app/web/views/luong.py) ---------- */
.lg-top{display:flex;gap:14px;flex-wrap:wrap;align-items:stretch;margin-bottom:12px}
.lg-net{flex:1 1 260px;background:var(--grad-brand);color:#fff;border-radius:16px;
  padding:18px 20px;box-shadow:var(--shadow-lg)}
.lg-net-l{font-size:12.5px;opacity:.85}
.lg-net-v{font-weight:800;font-size:30px;line-height:1.15;margin-top:4px}
.lg-net-s{font-size:11.5px;opacity:.8;margin-top:4px}
.lg-goal{flex:2 1 320px;background:var(--card);border:1px solid var(--border);
  border-radius:16px;padding:16px 18px}
.lg-goal-h{display:flex;align-items:baseline;justify-content:space-between;
  gap:10px;font-size:13px}
.lg-bar{height:10px;border-radius:999px;background:var(--soft);overflow:hidden;
  margin-top:9px}
.lg-bar i{display:block;height:100%;background:var(--grad-brand)}
.lg-goal .note{margin-top:8px}
.lg-goal .note.ok{color:var(--ok)}
.lg-goal-f{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;
  margin-bottom:14px}
.lg-goal-f label{display:flex;flex-direction:column;gap:4px;font-size:11.5px;
  color:var(--sub)}
.lg-goal-f input{height:34px;width:120px;border:1px solid var(--border);
  border-radius:9px;padding:0 10px;font:inherit;font-size:13px;
  background:var(--card);color:var(--text)}
.lg-h4{font-size:12.5px;font-weight:700;margin:14px 0 7px;color:var(--sub)}
.lg-act{display:inline-block;margin:0}
/* dấu ✎ = người đã sửa phân loại đơn, máy thôi tự đổi */
.lg-sua{color:var(--warn);font-weight:700;cursor:help}
.ds-chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.ds-chip{display:inline-flex;align-items:center;gap:6px;padding:6px 13px;
  border:1px solid var(--border);border-radius:999px;background:var(--card);
  font-size:12.5px;color:var(--text);text-decoration:none}
.ds-chip b{color:var(--sub);font-size:11.5px}
.ds-chip.on{background:var(--grad-brand);color:#fff;border-color:transparent}
.ds-chip.on b{color:rgba(255,255,255,.85)}
.ds-acts{display:flex;flex-direction:column;gap:6px;align-items:flex-end}

/* ---------- C3 · Chiến dịch & Mẫu tin (app/web/views/chien_dich.py) ---------- */
/* Dải "hai tầng" — vẽ ra để không ai gộp 2 tầng lại làm một */
.cd-tang{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  margin-bottom:14px;font-size:12.5px}
.cd-t1,.cd-t2{flex:1 1 240px;border-radius:12px;padding:11px 14px}
.cd-t1{background:var(--soft);color:var(--accent)}
.cd-t2{background:var(--ok-bg);color:var(--ok)}
.cd-mui{color:var(--sub);font-weight:600;white-space:nowrap}
.cd-preview{margin-top:12px;background:var(--soft);border-radius:11px;
  padding:11px 14px;font-size:13px}
.cd-preview.warn{background:var(--warn-bg);color:var(--warn)}
.vc-form-r textarea{border:1px solid var(--border);background:var(--bg);
  border-radius:9px;padding:8px 10px;font:inherit;font-size:13px;
  color:var(--text);resize:vertical}
.mt-body{font-size:11.5px;color:var(--sub);white-space:pre-wrap;
  word-break:break-word;display:block;max-width:340px}

/* ---------- C4 · Thư viện kịch bản (app/web/views/giam_sat.py) ---------- */
.kb-list{display:flex;flex-direction:column;gap:10px}
.kb-card{background:var(--card);border:1px solid var(--border);
  border-radius:12px;padding:12px 14px}
.kb-h{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:13px}
.kb-loai{font-size:11px;font-weight:700;background:var(--soft);
  color:var(--accent);border-radius:999px;padding:2px 9px}
.kb-th{font-size:11.5px;color:var(--sub)}
.kb-body{margin-top:7px;font-size:13px;line-height:1.55;white-space:pre-wrap;
  background:var(--soft);border-radius:9px;padding:9px 11px}
.kb-f{display:flex;align-items:center;gap:8px;margin-top:9px}
.gy-item{border-left:3px solid var(--accent);padding-left:10px;margin-bottom:10px}

/* ---------- C5 · Bảng việc Sale (app/web/views/sale.py) ----------
   Bố cục 3 tầng port từ mẫu (templatemaux/index.php?bp=sale):
     tầng 1 `.bv-bar1` — đổi bộ phận · đã xong hôm nay · ô tìm · chọn chế độ
     tầng 2 `.bv-bar2` — dải bộ lọc
     tầng 3 `.bv-tabs` — tab đếm việc (bấm = đặt bộ lọc)
   Ba tầng dính nhau trên nền THẺ (`.bv-head`), khu nội dung nền CHÌM — mẫu tách
   hai vùng bằng nền chứ không bằng đường kẻ. Màn chạy `full=True` nên bề ngang
   không bị bó 1280px: bảng kanban 15 cột cần hết chỗ có thể. */
.bv-wrap{flex:1;min-width:0;display:flex;flex-direction:column}
.bv-head{flex:0 0 auto;background:var(--card);
  border-bottom:1px solid var(--border)}
.bv-than{flex:1 1 auto;min-height:0;overflow-y:auto;padding:14px 24px 40px}
.bv-bar1{display:flex;align-items:center;gap:12px;flex-wrap:wrap;
  padding:14px 24px 10px}
.bv-gap{flex:1 1 auto;min-width:8px}
/* Cặp nút "một trong hai" — dùng cho cả Sale/CSKH lẫn Bảng/Pipeline */
.bv-seg2{display:flex;gap:3px;background:var(--soft);border-radius:10px;
  padding:3px;flex:0 0 auto}
.bv-seg2 a{padding:5px 13px;border-radius:7px;text-decoration:none;
  font-size:12.5px;font-weight:600;color:var(--sub);white-space:nowrap}
.bv-seg2 a.on{background:var(--card);color:var(--accent);box-shadow:var(--shadow)}
.bv-seg2 a:hover{color:var(--text)}
.bv-done{display:inline-flex;align-items:center;gap:7px;flex:0 0 auto;
  background:var(--ok-bg);color:var(--ok);border-radius:999px;padding:6px 13px;
  font-size:12.5px;font-weight:600}
.bv-done .ico{width:15px;height:15px}
.bv-find{position:relative;flex:0 0 auto;margin:0}
.bv-find .ico{width:15px;height:15px;position:absolute;left:11px;top:50%;
  transform:translateY(-50%);color:var(--sub);pointer-events:none}
.bv-find input{width:210px;max-width:100%;height:36px;
  border:1px solid var(--border);background:var(--soft);border-radius:10px;
  padding:0 12px 0 32px;font:inherit;font-size:13px;color:var(--text);
  outline:none}
.bv-find input:focus{border-color:var(--accent)}
.bv-bar2{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  padding:0 24px 12px;margin:0}
.bv-ck{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 12px;
  border:1px solid var(--border);background:var(--card);border-radius:9px;
  font-size:12.5px;color:var(--text);cursor:pointer;flex:0 0 auto}
.bv-ck:hover{border-color:var(--accent)}
.bv-xoa{display:inline-flex;align-items:center;gap:5px;height:34px;
  color:var(--accent);font-size:12.5px;font-weight:600;text-decoration:none;
  flex:0 0 auto}
.bv-xoa .ico{width:14px;height:14px}
/* Ô xổ trong dải lọc — cùng cỡ 34px với ô tích để dải không lởm chởm */
.bv-sel{height:34px;max-width:230px;border:1px solid var(--border);
  background:var(--card);border-radius:9px;padding:0 10px;font:inherit;
  font-size:12.5px;color:var(--text);cursor:pointer;flex:0 0 auto}
.bv-sel:hover{border-color:var(--accent)}
/* Ô "Của tôi" — chỗ đáng lẽ là ô chọn nhân viên, nhưng người này không có
   quyền xem của người khác. In ra chữ chứ không bỏ trống: phải nói rõ phạm vi
   đang bó, kẻo tưởng đang xem hết. */
.bv-ro{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 12px;
  border:1px solid var(--border);background:var(--card);border-radius:9px;
  font-size:12.5px;color:var(--sub);flex:0 0 auto}
.bv-ro .ico{width:14px;height:14px}
.bv-ngay{display:flex;align-items:center;gap:5px;height:34px;
  border:1px solid var(--border);background:var(--card);border-radius:9px;
  padding:0 10px;font-size:12px;color:var(--sub);flex:0 0 auto}
.bv-ngay .ico{width:14px;height:14px;flex:0 0 auto}
.bv-ngay input{height:24px;border:1px solid var(--border);background:var(--soft);
  border-radius:6px;padding:0 5px;font:inherit;font-size:12px;
  color:var(--text);outline:none}
.bv-ngay input:focus{border-color:var(--accent)}
.bv-cnt{font-size:12.5px;color:var(--sub);flex:0 0 auto}
/* Tab đếm: gạch chân chứ không phải viên thuốc — mẫu để chúng như tab thật để
   phân biệt với dải lọc ngay trên. */
.bv-tabs{display:flex;align-items:center;gap:22px;padding:0 24px;
  flex-wrap:wrap}
.bv-tab{text-decoration:none;font-size:13px;padding:2px 0 7px;
  color:var(--sub);font-weight:500;border-bottom:2px solid transparent}
.bv-tab:hover{color:var(--text)}
.bv-tab.on{color:var(--accent);font-weight:700;border-bottom-color:var(--accent)}
.bv-tab b{font-weight:800}
.bv-tab b.err{color:var(--err)}
/* Dải ghi chú trong khu nội dung (đã ẩn N khách · máy đọc tin thật) */
.bv-note{display:flex;align-items:center;gap:9px;background:var(--soft);
  border:1px dashed var(--border);border-radius:11px;padding:8px 13px;
  margin-bottom:12px;font-size:12px;color:var(--sub);line-height:1.5}
.bv-note .ico{width:15px;height:15px;color:var(--ok);flex:0 0 auto}
.bv-note span{flex:1 1 auto;min-width:0}
.bv-note a{color:var(--accent);font-weight:600;flex:0 0 auto}

.bv-board{display:flex;gap:10px;overflow-x:auto;padding-bottom:8px;
  align-items:flex-start}
.bv-cot{flex:0 0 260px;background:var(--soft);border-radius:12px;padding:8px}
.bv-cot-h{display:flex;align-items:center;gap:8px;font-size:12.5px;
  padding:6px 8px;border-left:3px solid var(--accent);background:var(--card);
  border-radius:8px}
.bv-dem{margin-left:auto;font-size:11px;color:var(--sub);font-weight:700}
.bv-cot-h2{font-size:10.5px;color:var(--sub);padding:5px 8px 7px}
.bv-khoa{font-size:10.5px;color:var(--sub);font-style:italic;padding:0 8px 6px}
.bv-rong{text-align:center;color:var(--sub);font-size:12px;padding:14px 0}
.bv-the{background:var(--card);border:1px solid var(--border);border-radius:10px;
  padding:9px 11px;margin-bottom:8px}
.bv-the.nong{border-color:var(--hot)}
/* Hẹn mua TRƯỢT ngày — tài liệu mẫu (C1) bắt "ở lại cột Hẹn mua, viền đỏ".
   Viền dày hơn thẻ thường 1px để phân biệt được cả khi in đen trắng; và LUÔN
   đi kèm dòng chữ `.bv-qh` do view in ra (luật vàng B3.5: màu không bao giờ
   đứng một mình). Đừng bỏ dòng chữ đó đi mà chỉ giữ viền. */
.bv-the.tre{border-color:var(--err);border-width:2px;padding:10px 11px}
.kh-tbl tr.tre>td:first-child{box-shadow:inset 3px 0 0 var(--err)}
.bv-h{display:flex;align-items:center;gap:6px;font-size:13px}
/* --- Hàng meta của thẻ: hạng thẻ + tổng chi · nguồn · SĐT bấm-chép --- */
.bv-meta{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-top:4px}
.bv-hang{font-size:10.5px;font-weight:700;border-radius:999px;padding:2px 8px;
  white-space:nowrap}
.bv-nguon{font-size:10px;font-weight:600;color:var(--sub);background:var(--soft);
  border-radius:999px;padding:2px 8px;white-space:nowrap}
.bv-tel{font-size:10.5px;padding:2px 8px;border-radius:999px;
  background:var(--ok-bg);color:var(--ok);border:0;cursor:pointer;
  display:inline-flex;align-items:center;gap:4px;font-family:inherit}
.bv-tel .ico{width:11px;height:11px}
/* Dấu đã xem / chưa đọc — chỉ vẽ khi kho hội thoại của watcher có dữ liệu */
.bv-xem{display:inline-flex;flex:0 0 auto}
.bv-xem .ico{width:13px;height:13px}
.bv-xem.da{color:var(--ok)}
.bv-xem.chua{color:var(--err)}
.bv-xem.chua-xem{color:var(--sub);opacity:.65}
/* Cửa gửi tin 24 giờ — cùng bộ 3 trạng thái với màn Hội thoại */
.bv-cua-r{margin-top:7px}
.bv-cua{display:inline-flex;align-items:center;gap:5px;font-size:10.5px;
  font-weight:700;border-radius:999px;padding:2px 9px;white-space:nowrap}
.bv-cua i{width:6px;height:6px;border-radius:999px;background:currentcolor;
  flex:0 0 auto;display:block}
.bv-cua.open{background:var(--ok-bg);color:var(--ok)}
.bv-cua.tpl{background:var(--warn-bg);color:var(--warn)}
.bv-cua.unk{background:var(--in);color:var(--sub)}
/* Thanh tiến trình thang bước.
   🔴 Thanh này ĐẦY DẦN VỀ PHÍA XẤU (đi hết thang = sắp buông khách) trong khi
   mắt đọc "đầy = tốt" — bẫy B4 của mẫu. Nên màu do Python đặt inline theo tỉ lệ
   (xanh→vàng→đỏ) và LUÔN có dòng chữ mốc bên dưới. Đừng bao giờ bỏ dòng chữ. */
.bv-tien{margin-top:7px}
.bv-tien-r{height:5px;border-radius:999px;background:var(--in);overflow:hidden}
.bv-tien-f{height:100%;border-radius:999px}
.bv-tien-c{font-size:10.5px;color:var(--sub);margin-top:3px;line-height:1.4}
.bv-tdo{min-width:150px}
.bv-nong{font-size:10px;font-weight:700;color:var(--hot);background:var(--hot-bg);
  border-radius:999px;padding:1px 7px}
/* câu 📌 "việc cần làm" — thứ nhân viên đọc đầu tiên, đừng làm mờ đi */
.bv-viec{margin-top:7px;font-size:12px;line-height:1.5;background:var(--soft);
  border-radius:8px;padding:6px 9px}
.bv-viec.urgent{background:var(--warn-bg);color:var(--warn);font-weight:600}
.bv-cho{color:var(--sub);font-size:11px;font-style:italic;margin-left:4px}
.bv-qh{margin-top:6px;font-size:11.5px;color:var(--err);font-weight:600}
.bv-chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.bv-chip{font-size:10.5px;background:var(--card);border:1px solid var(--border);
  border-radius:999px;padding:2px 8px;color:var(--sub)}
/* --- Thanh hàng loạt (port includes/bulkbar.php) ---
   Dính đáy màn, MỜ đi khi chưa tích thẻ nào chứ không giấu hẳn: giấu thì người
   dùng không biết là có thao tác hàng loạt, mà bày sáng thì bấm vào báo lỗi. */
.bv-hl{position:sticky;bottom:0;z-index:30;display:flex;align-items:center;
  gap:8px;flex-wrap:wrap;margin:0 0 12px;padding:10px 14px;background:var(--card);
  border:1px solid var(--border);border-radius:12px;box-shadow:var(--shadow-lg);
  opacity:.45;pointer-events:none;transition:opacity .12s}
.bv-hl.on{opacity:1;pointer-events:auto;border-color:var(--accent)}
.bv-hl-n{font-size:12.5px;color:var(--sub);flex:0 0 auto}
.bv-hl-n b{color:var(--accent);font-size:14px}
.bv-hl-g{position:relative;flex:0 0 auto}
.bv-hl-g>summary{list-style:none;cursor:pointer}
.bv-hl-g>summary::-webkit-details-marker{display:none}
.bv-hl-p{position:absolute;z-index:40;bottom:38px;left:0;min-width:230px;
  max-height:280px;overflow-y:auto;background:var(--card);
  border:1px solid var(--border);border-radius:11px;box-shadow:var(--shadow-lg);
  padding:9px;display:flex;flex-direction:column;gap:5px}
.bv-hl-nv{display:flex;align-items:center;gap:7px;font-size:12.5px;
  padding:3px 4px;cursor:pointer;border-radius:7px}
.bv-hl-nv:hover{background:var(--soft)}
.bv-tick{width:15px;height:15px;flex:0 0 auto;cursor:pointer;accent-color:var(--accent)}
.bv-tdc{width:34px;text-align:center}

/* --- Hàng nút trên thẻ (port render_actions của mẫu) --- */
.bv-nutr{display:flex;align-items:center;flex-wrap:wrap;gap:5px;margin-top:9px}
.bv-nutr form{margin:0}
.bv-nut-ic{width:29px;height:29px;border:1px solid var(--border);
  border-radius:8px;background:var(--card);color:var(--sub);cursor:pointer;
  display:inline-grid;place-items:center;flex:0 0 auto;text-decoration:none;
  padding:0}
.bv-nut-ic:hover{border-color:var(--accent);color:var(--accent)}
.bv-nut-ic .ico{width:15px;height:15px}
.bv-nut-ic.ok{color:var(--ok)}
.bv-nut-ic.go{color:var(--accent)}
/* Menu ⋯ — mọi thứ không dùng hằng ngày. `position:relative` trên <details> để
   khay bung ra bám đúng nút, không nhảy về góc thẻ. */
.bv-menu{position:relative;flex:0 0 auto}
.bv-menu>summary{list-style:none}
.bv-menu>summary::-webkit-details-marker{display:none}
.bv-menu-p{position:absolute;z-index:40;right:0;top:33px;min-width:225px;
  background:var(--card);border:1px solid var(--border);border-radius:11px;
  box-shadow:var(--shadow-lg);padding:9px;display:flex;flex-direction:column;
  gap:8px}
.bv-menu-p form{display:flex;flex-wrap:wrap;align-items:center;gap:5px}
.bv-menu-p label{width:100%;font-size:11px;font-weight:700;color:var(--sub)}
.bv-menu-p input[type=datetime-local],.bv-menu-p select{flex:1 1 120px;
  min-width:0;height:30px;border:1px solid var(--border);background:var(--soft);
  border-radius:8px;padding:0 8px;font:inherit;font-size:12px;
  color:var(--text)}
.bv-menu-p .kh-btn{height:30px;font-size:12px}
.bv-menu-sep{height:1px;background:var(--border);margin:2px 0}
.bv-f{display:flex;align-items:center;gap:6px;margin-top:8px}
.bv-f select{height:28px;flex:1;min-width:0;border:1px solid var(--border);
  border-radius:8px;background:var(--card);font:inherit;font-size:11.5px;
  color:var(--text)}
.bv-nut{margin-top:6px}
.bv-nut summary{font-size:11px;color:var(--sub);cursor:pointer}
.bv-nut .ds-acts{margin-top:6px}

/* ---------- C8 · Màn Cài đặt (app/web/views/cai_dat.py) ---------- */
.cd-wrap{display:flex;gap:18px;align-items:flex-start}
/* Menu mục con DÍNH — cuộn nội dung bên phải mà menu vẫn nằm trong tầm mắt */
.cd-menu{flex:0 0 232px;background:var(--card);border:1px solid var(--border);
  border-radius:14px;padding:7px;position:sticky;top:8px;box-shadow:var(--shadow)}
.cd-nav{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:9px;
  font-size:12.5px;font-weight:600;color:var(--text);text-decoration:none;margin:1px 0}
.cd-nav:hover{background:var(--soft)}
.cd-nav.on{background:var(--soft);color:var(--accent)}
.cd-nav .cd-ic{flex:0 0 auto}
.cd-nav .cd-lb{flex:1 1 auto;min-width:0}
.cd-nav b{font-size:10.5px;color:var(--sub);font-weight:700;flex:0 0 auto}
/* chuông cam = số ô CHƯA ĐIỀN của mục — thấy ngay chỗ nào còn thiếu cấu hình */
.cd-cam{font-style:normal;font-size:10px;font-weight:800;color:#fff;
  background:var(--warn);border-radius:999px;padding:1px 6px;flex:0 0 auto}
.cd-nav.ngoai{color:var(--sub)}
.cd-nav-g{font-size:10.5px;font-weight:700;text-transform:uppercase;
  color:var(--sub);opacity:.75;padding:10px 10px 4px;letter-spacing:.4px}
.cd-than{flex:1 1 auto;min-width:0}
.cd-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
  gap:11px}
.cd-o{display:flex;flex-direction:column;gap:4px;border:1px solid var(--border);
  border-radius:12px;padding:11px 13px}
/* Ô chưa điền: viền + chữ CAM. Màu không đứng một mình — luôn kèm chữ
   "chưa điền" ở pill bên cạnh (luật A3/B3.5 của mẫu). */
.cd-o.trong{border-color:#f0d3c4;background:var(--warn-bg)}
.cd-h{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.cd-h code{font-size:10.5px;color:var(--accent);font-weight:700}
.cd-ten{font-size:12.5px;font-weight:700;color:var(--text)}
.cd-mo{font-size:11px;color:var(--sub);line-height:1.45}
.cd-dk{display:flex;align-items:center;gap:7px;margin-top:3px}
.cd-in{height:34px;border:1px solid var(--border);background:var(--bg);
  border-radius:9px;padding:0 10px;font:inherit;font-size:12.5px;
  color:var(--text);width:100%;min-width:0;box-sizing:border-box}
.cd-in.num{text-align:right;font-variant-numeric:tabular-nums}
.cd-in.trong{border-color:#f0d3c4;color:var(--warn)}
.cd-in.trong::placeholder{color:var(--warn);opacity:.8}
.cd-dv{font-size:11.5px;color:var(--sub);flex:0 0 auto}
.cd-md{font-size:10.5px;color:var(--sub);opacity:.85}
.pill.cam{background:var(--warn-bg);color:var(--warn)}
@media (max-width:900px){
  .cd-wrap{flex-direction:column}
  .cd-menu{position:static;flex:1 1 auto;width:100%;
    display:flex;flex-wrap:wrap;gap:4px}
  .cd-nav{flex:0 1 auto}
  .cd-nav-g{width:100%}
}

/* ---------- Đợt 2 · Cài đặt → công tắc gửi tin (3 trạng thái, 2 lớp khoá) --- */
.ctcard{border:1.5px solid #f0d3c4}
.ctkhoa{display:flex;align-items:center;gap:9px;flex-wrap:wrap;
  background:var(--soft);border-radius:11px;padding:10px 14px;font-size:12.5px;
  margin:12px 0}
.ctkhoa .chan{color:var(--border)}
.ctkhoa .het{flex:1 1 auto;text-align:right;font-size:11.5px;color:var(--sub)}
.ctkhoa b.tot{color:var(--ok)}
.ctkhoa b.xau{color:var(--danger)}
.ctnuts{display:flex;gap:10px;flex-wrap:wrap}
.ctnut{flex:1 1 170px;text-align:left;border:1.5px solid var(--border);
  border-radius:12px;padding:11px 14px;background:var(--card);color:var(--sub);
  font:inherit;cursor:pointer}
.ctnut b{display:block;font-size:13.5px}
.ctnut i{display:block;font-size:11.5px;font-style:normal;margin-top:3px;
  opacity:.85}
.ctnut.on{border-color:var(--brand);background:var(--soft);color:var(--text)}
.ctnut:disabled{opacity:.55;cursor:not-allowed}
.ctwhy{margin-top:12px;background:var(--danger-bg,#fdecec);color:var(--danger);
  border-radius:10px;padding:10px 12px;font-size:11.5px;font-weight:600}

/* ---------- Đợt 3 · Luồng tự động (KHUNG — chưa gửi tin) ------------------- */
.afcanh{border:1.5px solid #f0d3c4}
.afwhy{margin-top:10px;background:var(--soft);border-left:3px solid var(--danger);
  border-radius:8px;padding:10px 12px;font-size:12px;color:var(--text)}
.afrow{border:1px solid var(--border);border-radius:12px;padding:12px 14px;
  margin-top:10px}
.afrow.tat{opacity:.55}
.afh{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:13.5px}
.afmo{font-size:12px;color:var(--sub);margin-top:4px}
.afnut{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}
.afgrid{display:flex;gap:12px;flex-wrap:wrap;margin-top:11px}
.afl{flex:1 1 220px;display:flex;flex-direction:column;gap:4px;font-size:12px;
  color:var(--sub)}
.afl input,.afl select{height:36px;border:1px solid var(--border);
  background:var(--soft);border-radius:9px;padding:0 11px;font:inherit;
  font-size:12.5px;color:var(--text)}
.afl select[multiple]{height:auto;padding:6px 8px}
.afck{flex-direction:row;align-items:center;gap:8px;color:var(--text)}
.afck input{height:auto;flex:0 0 auto}
.afkq{border:1.5px solid var(--brand)}
.afso{font-size:22px;font-weight:800;margin:6px 0}
.afkhs{display:flex;flex-wrap:wrap;gap:7px;margin-top:11px}
.afkh{display:flex;gap:7px;align-items:baseline;border:1px solid var(--border);
  border-radius:999px;padding:4px 12px;font-size:12px}
.afsua{margin-top:10px;border-top:1px dashed var(--border);padding-top:8px}
.afsua>summary{cursor:pointer;font-size:12px;color:var(--sub);list-style:none}
.afsua>summary::-webkit-details-marker{display:none}
.afhist{margin-top:10px;border-top:1px dashed var(--border);padding-top:8px}
.afls{font-size:11.5px;color:var(--sub);padding:2px 0}

/* ---------- Đợt 2 · Kịch bản nhận diện + Gợi ý kịch bản -------------------- */
.ndthes{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
.ndthe{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);
  border-radius:999px;padding:4px 6px 4px 11px;font-size:12px;background:var(--card)}
.ndthe .mo{opacity:.6}
.ndthe.tat{opacity:.5;background:var(--soft)}
/* Mẫu NỀN: viền đứt + không có nút — nhìn là biết ngay cái này không xoá được */
.ndthe.nen{border-style:dashed;background:var(--soft);color:var(--sub);
  padding:4px 11px}
.ndthe .x{border:none;background:none;cursor:pointer;color:var(--ok);
  font:inherit;line-height:1;padding:0 2px}
.ndthe .x.xoa{color:var(--danger)}
.ndadd{display:flex;gap:7px;flex-wrap:wrap;margin-top:11px}
.ndadd input,.ndadd select{flex:1 1 160px;height:34px;border:1px solid var(--border);
  background:var(--soft);border-radius:8px;padding:0 11px;font:inherit;
  font-size:12.5px;color:var(--text)}
.ndadd .btn{flex:0 0 auto}
.ndkq{display:flex;align-items:center;gap:10px;margin-top:11px;flex-wrap:wrap}
.ndtag{font-size:12.5px;font-weight:700;border:1px solid var(--sub);
  border-radius:999px;padding:3px 12px;color:var(--sub)}
.ndtag.goi{color:var(--ok);border-color:var(--ok)}
.ndtag.vc{color:var(--brand);border-color:var(--brand)}
.ndtag.chan{color:var(--danger);border-color:var(--danger)}
.ndwhy{font-size:12px;color:var(--sub);flex:1 1 220px}
.gytbl{border:1px solid var(--border);border-radius:12px;overflow:hidden;
  margin-top:10px}
.gyrow{display:flex;align-items:center;gap:12px;padding:10px 14px;
  border-top:1px solid var(--border);flex-wrap:wrap}
.gyrow:first-child{border-top:none}
.gyrow.tat{opacity:.5}
.gyrow .kw{flex:1 1 200px;font-size:12.5px}
.gyrow .mui{color:var(--sub)}
.gyrow .sc{flex:0 1 260px;font-size:12px;color:var(--sub)}
.gyn{display:flex;gap:6px;flex:0 0 auto}
.gyn .x{border:none;background:none;cursor:pointer;color:var(--ok);font:inherit;
  line-height:1;padding:0 2px}
.gyn .x.xoa{color:var(--danger)}

/* ---------- Đợt 1 · Cài đặt → Mốc thời gian (views/cai_dat_moc.py) ---------- */
.mocg{border:1px solid var(--border);border-radius:13px;overflow:hidden;
  background:var(--card);margin-top:10px}
.mocg>summary{display:flex;align-items:center;gap:9px;padding:12px 15px;
  cursor:pointer;background:var(--soft);list-style:none}
.mocg>summary::-webkit-details-marker{display:none}
.mocg .chev{color:var(--sub);transform:rotate(-90deg);transition:transform .15s}
.mocg[open] .chev{transform:rotate(0)}
.mocg .gttl{flex:1 1 auto;min-width:0;font-size:13.5px;font-weight:700}
.mocg .gsub{font-weight:400;color:var(--sub);font-size:11.5px}
.mocg .gcnt{flex:0 0 auto;font-size:11.5px;color:var(--sub)}
.gbody{padding:12px 15px;display:flex;flex-direction:column;gap:9px}
.mnhom{font-size:10.5px;font-weight:700;letter-spacing:.04em;
  text-transform:uppercase;color:var(--sub);margin:10px 0 2px}
.mitem{border:1px solid var(--border);border-radius:11px;padding:9px 12px}
.mitem.off{opacity:.55}
.mrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
/* nút gạt: input ẩn + label vẽ — bấm nhãn là đổi, không cần JS */
.msw{position:absolute;width:0;height:0;opacity:0}
.swui{width:42px;height:24px;border-radius:999px;background:var(--border);
  padding:3px;flex:0 0 auto;cursor:pointer;display:block;transition:background .15s}
.swui>span{width:18px;height:18px;border-radius:999px;background:#fff;
  box-shadow:var(--shadow);display:block;transition:margin-left .15s}
.msw:checked+.swui{background:var(--accent)}
.msw:checked+.swui>span{margin-left:18px}
.mitem.crit .msw:checked+.swui{background:#0E9488}
.mname{flex:0 0 118px;min-width:0;font-size:12.5px;font-weight:600;line-height:1.25}
.mname small{display:block;font-size:10px;font-weight:400;color:var(--sub);
  font-family:ui-monospace,monospace}
.mnum{flex:0 0 56px;width:56px;height:32px;border:1px solid var(--border);
  background:var(--bg);border-radius:8px;padding:0 8px;font:inherit;
  font-size:12.5px;text-align:center;color:var(--text)}
.munit{flex:0 0 auto;font-size:11.5px;color:var(--sub)}
.nhanin{flex:1 1 180px;min-width:90px;height:32px;border:1px solid var(--border);
  background:var(--card);border-radius:8px;padding:0 10px;font:inherit;
  font-size:12.5px;font-weight:600;color:var(--accent)}
.nhanin::placeholder{font-weight:400;color:var(--sub)}
.offlbl{display:none;flex:0 0 auto;font-size:10.5px;font-weight:600;
  color:var(--sub);background:var(--soft);border-radius:999px;padding:2px 8px}
.mitem.off .offlbl{display:block}
.aigui{flex:0 0 auto;display:flex;gap:3px;background:var(--soft);
  border-radius:9px;padding:3px}
.aib{width:30px;height:25px;border:1px solid transparent;background:none;
  font:inherit;font-size:13px;border-radius:7px;cursor:pointer;opacity:.45;
  filter:grayscale(1)}
.aib.on{border-color:var(--accent);background:var(--card);opacity:1;
  filter:none;box-shadow:var(--shadow)}
/* cảnh báo mốc GẮT — hỏi lại tại chỗ, không dùng confirm() dễ bấm nhầm */
.critw{display:flex;align-items:center;gap:10px;background:var(--warn-bg);
  border-radius:10px;padding:9px 12px;margin-top:7px;font-size:12px}
.critw .msg{flex:1 1 auto;color:var(--warn);line-height:1.45}
.critw button{font:inherit;font-size:12px;font-weight:600;padding:5px 11px;
  border-radius:8px;cursor:pointer;flex:0 0 auto}
.critw .keep{border:1px solid var(--border);background:var(--card);color:var(--text)}
.critw .force{border:none;background:var(--warn);color:#fff}
/* hàng từ khoá kiểu THẺ */
.kwrow{display:flex;align-items:flex-start;gap:9px;margin:6px 0 0 50px;
  padding-left:10px;border-left:2px solid var(--border)}
.kwrow.kh{border-left-color:#4E7FE8}
.kwrow.kh .kwlb{color:#4E7FE8}
.kwrow.kh .kwtag{border-color:#BBD3F5;background:#E2EAFB;color:#1B4C8F}
.kwlb{flex:0 0 auto;font-size:11px;color:var(--sub);padding-top:8px;
  white-space:nowrap;cursor:help}
.kwbox{flex:1 1 auto;min-width:0;display:flex;flex-wrap:wrap;align-items:center;
  gap:5px;min-height:32px;border:1px solid var(--border);background:var(--bg);
  border-radius:9px;padding:5px 6px;cursor:text}
.kwbox:focus-within{border-color:var(--accent)}
.kwtag{display:inline-flex;align-items:center;gap:3px;max-width:100%;
  font-size:11.5px;line-height:1;background:var(--card);
  border:1px solid var(--border);border-radius:999px;padding:4px 4px 4px 9px}
.kwtag b{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kwtag.sp{color:var(--accent);background:var(--soft);border-color:var(--accent)}
/* thẻ THỪA (chỉ khác dấu) — mờ đi để lộ ra ngay, không phải soi bằng mắt */
.kwtag.dup{opacity:.45}
.kwx{width:16px;height:16px;padding:0;border:none;background:none;
  border-radius:999px;color:var(--sub);font:inherit;font-size:13px;line-height:1;
  cursor:pointer;display:flex;align-items:center;justify-content:center}
.kwx:hover{background:var(--err-bg);color:var(--err)}
.kwadd{flex:1 1 110px;min-width:110px;height:22px;border:none;background:none;
  outline:none;padding:0 3px;font:inherit;font-size:11.5px;color:var(--text)}
.kwside{flex:0 0 96px;padding-top:8px;font-size:10.5px;color:var(--sub);
  text-align:right;line-height:1.5}
.kwdup{display:block;margin-left:auto;border:none;background:none;padding:0;
  font:inherit;font-size:10.5px;color:var(--accent);text-decoration:underline;
  cursor:pointer}
/* ô 🧪 Thử một câu */
.kwtry{margin-top:10px;border:1px dashed var(--accent);border-radius:11px;
  background:var(--soft);padding:11px 13px}
.kwtt{font-size:12px;font-weight:700;color:var(--accent)}
.kwtt span{font-weight:400;font-size:11.5px}
.kwtrow{display:flex;align-items:center;gap:9px;margin-top:8px;flex-wrap:wrap}
.kwtrow input[type=text]{flex:1 1 260px;min-width:0;height:34px;
  border:1px solid var(--border);background:var(--card);border-radius:9px;
  padding:0 11px;font:inherit;font-size:12.5px;color:var(--text)}
.kwtck,.kwtai{flex:0 0 auto;font-size:11.5px;color:var(--accent);cursor:pointer}
.kwtai{display:inline-flex;gap:14px}
.kwtai label{display:inline-flex;align-items:center;gap:5px;cursor:pointer}
.kwtgo{flex:0 0 auto;height:34px;padding:0 15px;border:none;border-radius:9px;
  background:var(--accent);color:#fff;font:inherit;font-size:12.5px;
  font-weight:600;cursor:pointer}
.kwtgo:disabled{opacity:.5;cursor:default}
.kwtkq{margin-top:9px;font-size:12px;line-height:1.6;background:var(--card);
  border-radius:9px;padding:9px 12px}
.kwtkq .hit{display:inline-block;font-size:11px;color:var(--accent);
  background:var(--soft);border-radius:999px;padding:1px 8px;margin:2px 3px 0 0}
.kwtkq .no{color:var(--warn)}
/* 1G/1H — hàng cột */
.nrow{display:flex;align-items:center;gap:11px;padding:9px 2px}
.nrow+.nrow{border-top:1px solid var(--border)}
.nrow.chead{padding-bottom:3px;border:none}
.nrow.chead .clab,.nrow.chead .cin{border:none;background:none;height:auto;
  padding:0;font-size:10.5px;font-weight:700;letter-spacing:.04em;
  text-transform:uppercase;color:var(--sub)}
.cdot{flex:0 0 auto;width:9px;height:9px;border-radius:999px}
.clab{flex:0 0 150px;min-width:0;font-size:12.5px;font-weight:700;
  display:flex;align-items:center;gap:6px}
.cma{font-family:ui-monospace,monospace;font-size:11px;font-weight:400;
  color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ctm{flex:0 0 auto;font-size:9.5px;font-weight:700;color:var(--accent);
  background:var(--soft);border-radius:999px;padding:1px 6px;cursor:help}
.cin{flex:1 1 auto;min-width:0;height:34px;border:1px solid var(--border);
  background:var(--bg);border-radius:9px;padding:0 10px;font:inherit;
  font-size:12.5px;color:var(--text)}
.ctag{flex:0 0 62px;text-align:center;font-size:10px;font-weight:700;
  color:var(--sub);background:var(--soft);border-radius:999px;padding:2px 8px}
.ctag.on{color:var(--accent);background:var(--soft)}
.gnote{font-size:11.5px;line-height:1.5;border-radius:10px;padding:9px 12px;
  margin-top:6px;background:var(--soft);color:var(--text)}
.savebar{display:flex;align-items:center;gap:12px;margin-top:16px;
  padding-top:14px;border-top:1px solid var(--border)}
.dirty{font-size:12px;color:var(--sub)}
.dirty.on{color:var(--warn);font-weight:600}

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

  // --- nhóm menu xổ/thu (Bot Pancake) -------------------------------------
  // Server LUÔN in `open` (không JS / màn hẹp thì nhóm trải phẳng như cũ), chỗ
  // này mới gập lại theo lựa chọn đã lưu. Phải lưu ngoài DOM vì PJAX vẽ lại cả
  // .side sau mỗi lần chuyển trang — không nhớ thì bung ra lại liên tục.
  var KHOA_THU_GON = 'nav-thu-gon';

  function nhomDaThuGon(){
    try { return JSON.parse(localStorage.getItem(KHOA_THU_GON)) || []; }
    catch (e) { return []; }        // chế độ riêng tư / localStorage bị chặn
  }

  function apDungThuGon(){
    // Màn hẹp menu nằm ngang (.nav-grp display:contents) — gập lại là mất mục,
    // nên bỏ qua, để nguyên `open`.
    if (window.matchMedia('(max-width:900px)').matches) return;
    var thuGon = nhomDaThuGon();
    var nhom = document.querySelectorAll('.side details[data-nhom]');
    for (var i = 0; i < nhom.length; i++) {
      var d = nhom[i];
      // Đang đứng trong nhóm nào thì nhóm đó luôn mở, kẻo mục đang xem bị giấu.
      // Dò '.on' trơ chứ không '.nav-item.on': mục đang xem có thể nằm trong
      // khối bộ phận xổ/thu ở nhóm Bộ phận, ở đó link mang class nd-link/sm-link.
      d.open = d.querySelector('.on') !== null ||
               thuGon.indexOf(d.getAttribute('data-nhom')) < 0;
    }
  }

  // `toggle` KHÔNG nổi bọt -> bắt ở pha capture (vẫn tới được đúng thẻ đích).
  document.addEventListener('toggle', function(e){
    var d = e.target;
    if (!d.matches || !d.matches('.side details[data-nhom]')) return;
    // Rail (.side.mini) bung hết nhóm bằng JS — mấy lượt `toggle` đó là của
    // máy, ghi vào localStorage là xoá sạch lựa chọn gập của người dùng.
    if (document.querySelector('.side.mini')) return;
    var ten = d.getAttribute('data-nhom');
    var thuGon = nhomDaThuGon();
    var i = thuGon.indexOf(ten);
    if (d.open) { if (i >= 0) thuGon.splice(i, 1); }
    else if (i < 0) { thuGon.push(ten); }
    try { localStorage.setItem(KHOA_THU_GON, JSON.stringify(thuGon)); }
    catch (e2) {}                   // không lưu được thì thôi, đừng vỡ menu
    veLaiMenu();  // gập/xổ đổi chiều cao menu -> tính lại mép mờ + ghim
  }, true);

  apDungThuGon();

  // --- thu/phóng cả menu thành rail icon (nút #navToggle ở đáy) -------------
  // Cùng nếp với nhóm thu gọn: nhớ ngoài DOM vì PJAX chép luôn className của
  // .side từ trang mới (server không bao giờ in `mini`) -> mất class.
  var KHOA_MINI = 'nav-mini';

  function hep(){ return window.matchMedia('(max-width:900px)').matches; }

  function apDungMini(){
    var s = document.querySelector('.side');
    if (!s) return;
    var mini = false;
    // Màn hẹp menu nằm ngang -> rail vô nghĩa, bỏ qua (nhưng KHÔNG xoá lựa
    // chọn đã lưu: về màn rộng vẫn thu lại như cũ).
    if (!hep()) { try { mini = localStorage.getItem(KHOA_MINI) === '1'; } catch (e) {} }
    if (mini) s.classList.add('mini'); else s.classList.remove('mini');
    var b = document.getElementById('navToggle');
    if (b) b.title = mini ? 'Mở rộng menu' : 'Thu gọn menu';
    if (mini) {
      // Trong rail, tiêu đề nhóm co còn vạch 1px -> nhóm nào đang gập là icon
      // của nó mất tăm mà chẳng còn chỗ bấm mở. Nên rail thì BUNG HẾT; lựa chọn
      // gập vẫn nằm nguyên trong localStorage (handler `toggle` bên trên đã bỏ
      // qua lúc mini) nên phóng menu ra là gập lại đúng như cũ.
      var ds = document.querySelectorAll('.side details[data-nhom]');
      for (var i = 0; i < ds.length; i++) ds[i].open = true;
    } else {
      apDungThuGon();
    }
  }

  function datMini(mini){
    try { localStorage.setItem(KHOA_MINI, mini ? '1' : '0'); } catch (e) {}
    apDungMini();
    veLaiMenu();  // rail đổi bề rộng -> menu cao khác đi
  }

  document.addEventListener('click', function(e){
    var t = e.target;
    if (!t || !t.closest) return;
    if (t.closest('#navToggle')) {
      datMini(!document.querySelector('.side').classList.contains('mini'));
      return;
    }
    // Trong rail, con của khối bộ phận bị ẩn (chúng không có icon) nên bấm
    // tiêu đề bộ phận mà xổ ra thì chẳng thấy gì — bung cả menu ra thay vì xổ.
    if (t.closest('.side.mini .nav-dept>summary,.side.mini .dept>summary')) {
      e.preventDefault();
      datMini(false);
    }
  });

  apDungMini();

  // --- mép dưới menu mờ dần khi còn nội dung cuộn (mẫu Kallet: .nav.more) ---
  function moMep(){
    var n = document.querySelector('.side .nav');
    if (!n) return;
    // -2px cho sai số làm tròn khi phóng to/thu nhỏ trang
    var con = n.scrollTop + n.clientHeight < n.scrollHeight - 2;
    if (con) n.classList.add('more'); else n.classList.remove('more');
  }

  // --- tiêu đề nhóm ĐANG DÍNH mép trên -> gắn .stuck (CSS mới cho nền frost) --
  // Việc dán là của position:sticky, JS chỉ để biết CÁI NÀO đang dán: chưa có
  // bộ chọn :stuck nào chạy được rộng rãi. So mép trên của summary với mép trên
  // vùng cuộn — bằng nhau (trong 1px) nghĩa là nó đang bị giữ lại.
  var choVe = false;
  function tinhGhim(){
    choVe = false;
    var n = document.querySelector('.side .nav');
    if (!n) return;
    var moc = n.getBoundingClientRect().top;
    var ss = n.querySelectorAll('.nav-grp>summary');
    for (var i = 0; i < ss.length; i++) {
      var dinh = ss[i].getBoundingClientRect().top <= moc + 1;
      if (dinh) ss[i].classList.add('stuck'); else ss[i].classList.remove('stuck');
    }
  }
  // Gộp vào 1 khung hình: scroll bắn liên tục, đo getBoundingClientRect mỗi lượt
  // là bắt trình duyệt tính lại bố cục giữa chừng -> cuộn giật.
  function xepGhim(){
    if (!choVe) { choVe = true; requestAnimationFrame(tinhGhim); }
  }
  function veLaiMenu(){ moMep(); xepGhim(); }

  // `scroll` KHÔNG nổi bọt -> bắt ở pha capture như handler `toggle` bên trên.
  document.addEventListener('scroll', function(e){
    var t = e.target;
    if (t && t.classList && t.classList.contains('nav')) veLaiMenu();
  }, true);
  window.addEventListener('resize', veLaiMenu);
  veLaiMenu();

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
    // CSS + JS của khung nằm trong <head>, mà PJAX chỉ thay ruột .side/.main ->
    // tab mở từ TRƯỚC lần sửa giao diện sẽ ôm bản CSS cũ mãi mãi: markup mới +
    // style cũ = layout vỡ (mục mới không có luật nào cho nó). Vân tay ở
    // <meta name=ui-ver> đổi thì nạp lại cả trang cho ăn khớp.
    var vCu = document.querySelector('meta[name="ui-ver"]');
    var vMoi = doc.querySelector('meta[name="ui-ver"]');
    if (vCu && vMoi && vCu.getAttribute('content') !== vMoi.getAttribute('content')) {
      location.href = url;
      return;
    }
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
      // <nav> nay tự cuộn (khối đáy ghim cố định) mà innerHTML thay cả nó ->
      // đang xem mục cuối menu, bấm phát nào menu giật về đầu phát ấy. Nhớ lại
      // chỗ cuộn rồi đặt về sau khi vẽ.
      var navCu = curSide.querySelector('.nav');
      var navTop = navCu ? navCu.scrollTop : 0;
      curSide.className = newSide.className;
      curSide.innerHTML = newSide.innerHTML;
      apDungThuGon();   // .side vừa bị vẽ lại -> nhóm thu gọn bung ra, gập lại
      apDungMini();     // ... và className vừa bị chép đè -> đắp lại `mini`
      var navMoi = curSide.querySelector('.nav');
      if (navMoi) navMoi.scrollTop = navTop;
      veLaiMenu();      // menu vừa vẽ lại -> tính lại mép mờ + ghim
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
