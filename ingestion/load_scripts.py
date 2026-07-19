"""Nạp kịch bản sẵn (Bảng 1) vào bảng kich_ban.

File nguồn: data/kich_ban.json — một JSON array, mỗi phần tử:
    {"buoc": "...", "noi_dung": "...", "trang_thai": "...", "dieu_kien": "..."}
(chỉ `noi_dung` là bắt buộc). Mỗi bước được tạo embedding rồi ghi vào DB.

Chạy: python -m ingestion.load_scripts [đường_dẫn.json]
"""

import asyncio
import json
import sys
from pathlib import Path

from app.db.queries import insert_script


async def load(path: str = "data/kich_ban.json") -> int:
    """Đọc file kịch bản, tạo embedding cho mỗi bước, ghi vào DB. Trả về số dòng."""
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(
            f"Không thấy file kịch bản: {file}. Tạo JSON array các bước trước."
        )
    items = json.loads(file.read_text(encoding="utf-8"))
    count = 0
    for it in items:
        noi_dung = (it.get("noi_dung") or "").strip()
        if not noi_dung:
            continue
        await insert_script(
            buoc=it.get("buoc") or "",
            noi_dung=noi_dung,
            trang_thai=it.get("trang_thai"),
            dieu_kien=it.get("dieu_kien"),
        )
        count += 1
    print(f"Đã nạp {count} bước kịch bản từ {file}")
    return count


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "data/kich_ban.json"
    asyncio.run(load(p))
