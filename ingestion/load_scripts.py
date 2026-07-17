"""Nạp kịch bản sẵn (Bảng 1) vào bảng kich_ban.

Chạy: python -m ingestion.load_scripts
"""

import asyncio

from app.db.client import get_supabase
from app.rag.embedding import embed


async def load(path: str = "data/kich_ban.json") -> None:
    """Đọc file kịch bản, tạo embedding cho mỗi bước, ghi vào DB.

    TODO:
      1. Đọc file nguồn (json/csv) chứa các bước kịch bản.
      2. Với mỗi bước: tạo embedding cho `noi_dung`.
      3. Upsert vào bảng `kich_ban`.
    """
    _ = get_supabase()
    _ = embed
    raise NotImplementedError("Cài đặt đọc file + upsert kich_ban")


if __name__ == "__main__":
    asyncio.run(load())
