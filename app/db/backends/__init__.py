"""Chọn backend lưu trữ theo cấu hình `DB_BACKEND` trong .env.

    DB_BACKEND=postgres   -> Postgres + pgvector cài trên máy này (mặc định)
    DB_BACKEND=supabase   -> Postgres cloud của Supabase, nói chuyện qua REST

Thêm backend mới = thêm 1 file trong thư mục này, cài đủ các phương thức của
`base.Backend`, rồi khai báo 1 dòng ở `_REGISTRY`. Không phải sửa queries.py hay
bất kỳ chỗ nào khác trong app.
"""

from functools import lru_cache

from app.core.config import settings

# Backend mặc định khi .env không có DB_BACKEND.
DEFAULT_BACKEND = "postgres"

# Tên backend -> hàm dựng. Import nằm TRONG lambda để chỉ nạp thư viện của
# backend đang dùng (chạy postgres thì không cần cài gói `supabase`, và ngược lại
# chạy supabase thì không cần psycopg).
_REGISTRY = {
    "postgres": lambda: _load("postgres_be", "PostgresBackend"),
    "supabase": lambda: _load("supabase_be", "SupabaseBackend"),
}


def _load(module: str, cls: str):
    """Nạp lớp backend theo tên module trong chính gói này."""
    from importlib import import_module

    return getattr(import_module(f"app.db.backends.{module}"), cls)()


@lru_cache
def get_backend():
    """Trả về backend đang cấu hình (tạo 1 lần rồi tái sử dụng cả tiến trình)."""
    name = backend_name()
    if name not in _REGISTRY:
        raise ValueError(
            f"DB_BACKEND={name!r} không hợp lệ. Chọn một trong: "
            f"{', '.join(sorted(_REGISTRY))}."
        )
    return _REGISTRY[name]()


def backend_name() -> str:
    """Tên backend đang dùng — cho trang cấu hình / thông báo lỗi."""
    return (settings.db_backend or DEFAULT_BACKEND).strip().lower()
