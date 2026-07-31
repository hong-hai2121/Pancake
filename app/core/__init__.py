"""Hạ tầng dùng chung, không dính nghiệp vụ.

    config.py — đọc .env thành `settings`
    paths.py  — mốc thư mục gốc dự án, để không phải đếm `parents[N]`

Sẽ thêm khi làm API theo đặc tả: security.py (JWT), permissions.py, deps.py,
errors.py (12 mã lỗi chuẩn), response.py (bao {success, data, message}),
pagination.py, idempotency.py, audit.py.
"""
