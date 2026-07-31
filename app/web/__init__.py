"""Giao diện web server-rendered — toàn bộ phần HTML của app.

    shell.py   — khung dùng chung (sidebar, topbar, CSS) cho mọi trang
    routes/    — nhận request, gọi tầng dữ liệu, trả HTML
    views/     — dựng chuỗi HTML, không chạm DB

Tách bạch với `app/api` (REST JSON `/api/v1` theo đặc tả CRM): route ở đây chỉ
phục vụ trình duyệt. Bước sau sẽ thay các file trong `views/` bằng template
Jinja2 trong `web/templates/` — xem docs/KE-HOACH-TAI-CAU-TRUC.md.
"""
