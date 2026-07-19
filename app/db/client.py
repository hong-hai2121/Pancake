"""Tạo kết nối tới Supabase / Postgres (dùng chung toàn app).

Có 2 cách nói chuyện với DB:
  - `get_supabase()`  : client REST của Supabase (thao tác bảng, gọi RPC). ĐANG DÙNG.
  - `get_pg_pool()`   : pool psycopg nối thẳng Postgres (chạy SQL/pgvector thô). CHƯA DÙNG.
"""

from functools import lru_cache

from app.config import settings


@lru_cache
def get_supabase():
    """Trả về client Supabase (tạo 1 lần rồi tái sử dụng nhờ lru_cache).

    Dùng cho mọi thao tác bảng qua REST: select/insert/upsert/delete và rpc().
    Đọc URL + SECRET key từ settings (nạp từ .env).
    """
    from supabase import create_client   # import trong hàm để tránh nạp nếu không dùng

    return create_client(settings.supabase_url, settings.supabase_key)


@lru_cache
def get_pg_pool():
    """Connection pool psycopg — dùng khi cần chạy SQL / pgvector trực tiếp.

    Hiện CHƯA cài đặt (app đang dùng Supabase REST + tính cosine phía Python).
    Nếu sau này muốn truy vấn vector bằng SQL thuần, khởi tạo:
        psycopg_pool.ConnectionPool(settings.database_url)
    """
    raise NotImplementedError("Khởi tạo pool nếu cần truy vấn SQL trực tiếp")
