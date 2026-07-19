"""Ingestion: đoạn chat đã chốt -> distill (LLM) -> embed -> lưu hoi_thoai_mau.

Nguồn mặc định: data/chats.json — JSON array các đoạn chat (mỗi phần tử là 1
chuỗi hội thoại, hoặc {"conversation": "...", "nguon": "..."}).

Chạy: python -m ingestion.run_ingest [đường_dẫn.json]
"""

import asyncio
import json
import sys
from pathlib import Path

from app.db.queries import insert_qa
from ingestion.distill import distill


async def ingest_conversation(conversation: str, nguon: str | None = None) -> int:
    """Distill 1 đoạn chat -> lưu từng cặp hỏi–đáp (kèm embedding). Trả số cặp."""
    pairs = await distill(conversation)
    for p in pairs:
        await insert_qa(p["cau_hoi"], p["cau_tra_loi"], nguon=nguon)
    return len(pairs)


async def run(path: str = "data/chats.json") -> int:
    """Chạy pipeline cho toàn bộ đoạn chat trong file. Trả về tổng số cặp đã lưu."""
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(
            f"Không thấy file chat: {file}. Tạo JSON array các đoạn chat trước."
        )
    items = json.loads(file.read_text(encoding="utf-8"))
    total = 0
    for it in items:
        if isinstance(it, str):
            conv, nguon = it, None
        else:
            conv, nguon = it.get("conversation", ""), it.get("nguon")
        if conv.strip():
            total += await ingest_conversation(conv, nguon)
    print(f"Đã chưng cất & lưu {total} cặp hỏi–đáp từ {file}")
    return total


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "data/chats.json"
    asyncio.run(run(p))
