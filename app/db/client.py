"""Tạo kết nối tới nơi lưu dữ liệu (dùng chung toàn app).

Mỗi hàm ở đây chỉ lo phần KẾT NỐI; phần đọc/ghi bảng nằm ở `app/db/backends/`.
Backend nào được dùng là do `DB_BACKEND` trong .env quyết định:

  - `get_pg_pool()`  : pool psycopg nối thẳng Postgres  (DB_BACKEND=postgres)
  - `get_supabase()` : client REST của Supabase         (DB_BACKEND=supabase)
"""

from functools import lru_cache

from app.core.config import settings


@lru_cache
def get_supabase():
    """Trả về client Supabase (tạo 1 lần rồi tái sử dụng nhờ lru_cache).

    Dùng cho mọi thao tác bảng qua REST: select/insert/upsert/delete và rpc().
    Đọc URL + SECRET key từ settings (nạp từ .env).
    """
    from supabase import create_client   # import trong hàm để tránh nạp nếu không dùng

    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError(
            "Thiếu SUPABASE_URL / SUPABASE_KEY trong .env (đang chạy "
            "DB_BACKEND=supabase). Đặt DB_BACKEND=postgres nếu muốn dùng "
            "Postgres cài trên máy."
        )
    return create_client(settings.supabase_url, settings.supabase_key)


@lru_cache
def get_pg_pool():
    """Trả về connection pool psycopg tới Postgres local (tạo 1 lần).

    Vì sao là POOL: uvicorn chạy handler trong threadpool, mà một connection
    psycopg không dùng chéo thread được. Pool phát cho mỗi lượt `with
    pool.connection()` một connection riêng rồi thu lại — vừa an toàn theo
    thread, vừa khỏi bắt tay TCP+TLS lại từ đầu mỗi truy vấn.

      * `row_factory=dict_row` : mọi câu SELECT trả về dict (cùng hình dạng dữ
        liệu với backend Supabase, nên tầng trên không phải phân biệt).
      * `autocommit=True`      : mỗi câu lệnh tự commit — hợp với kiểu dùng của
        app (từng thao tác ngắn, độc lập), không phải nhớ commit tay.
      * `connect_timeout`      : BẮT BUỘC có. Không đặt thì libpq chờ vô hạn, và
        worker của pool sẽ treo im lặng thay vì báo lỗi — đúng cái bẫy gặp khi
        DATABASE_URL trỏ `localhost` mà Docker chỉ nghe trên 127.0.0.1
        (Windows phân giải localhost ra ::1 trước). Dùng 127.0.0.1 cho chắc.
    """
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    if not settings.database_url:
        raise RuntimeError(
            "Thiếu DATABASE_URL trong .env (đang chạy DB_BACKEND=postgres). "
            "Ví dụ: postgresql://postgres:postgres@localhost:5432/pancakebot"
        )

    pool = ConnectionPool(
        settings.database_url,
        min_size=settings.pg_pool_min,
        max_size=settings.pg_pool_max,
        kwargs={
            "row_factory": dict_row,
            "autocommit": True,
            # libpq nhận giây (số nguyên, tối thiểu 2).
            "connect_timeout": max(int(settings.pg_connect_timeout), 2),
        },
        # Không mở trong hàm dựng (psycopg_pool khuyến nghị), mở ngay bên dưới.
        open=False,
        timeout=settings.pg_connect_timeout,
    )
    pool.open()
    return pool
