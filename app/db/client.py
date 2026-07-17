"""Kết nối Supabase / Postgres."""

from functools import lru_cache

from app.config import settings


@lru_cache
def get_supabase():
    """Client Supabase (dùng cho thao tác bảng qua REST)."""
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_key)


@lru_cache
def get_pg_pool():
    """Connection pool psycopg (dùng khi cần chạy SQL/pgvector trực tiếp).

    TODO: khởi tạo psycopg_pool.ConnectionPool(settings.database_url)
    nếu muốn truy vấn vector bằng SQL thuần thay vì RPC của Supabase.
    """
    raise NotImplementedError("Khởi tạo pool nếu cần truy vấn SQL trực tiếp")
