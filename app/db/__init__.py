"""Tầng dữ liệu, tách 3 lớp để đổi nơi lưu trữ mà không sửa phần còn lại của app.

    queries.py   — API dùng chung (mọi nơi khác chỉ import từ đây)
    backends/    — cài đặt cụ thể cho từng nơi lưu: postgres, supabase
    client.py    — tạo kết nối (pool psycopg / client Supabase)

Chọn backend bằng `DB_BACKEND` trong .env.
"""
