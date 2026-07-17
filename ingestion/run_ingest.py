"""Cron: lấy chat đã chốt -> distill -> lưu + tạo embedding.

Chạy định kỳ: python -m ingestion.run_ingest
"""

import asyncio

from app.db.client import get_supabase
from app.rag.embedding import embed
from ingestion.distill import distill


async def run() -> None:
    """Pipeline ingestion đầy đủ.

    TODO:
      1. Lấy các đoạn chat đã chốt đơn (chưa xử lý).
      2. distill() từng đoạn -> cặp hỏi–đáp.
      3. embed() nội dung -> ghi vào bảng hoi_thoai_mau.
      4. Đánh dấu đoạn chat đã xử lý.
    """
    _ = get_supabase()
    _ = (embed, distill)
    raise NotImplementedError("Ghép pipeline: lấy chat -> distill -> embed -> lưu")


if __name__ == "__main__":
    asyncio.run(run())
