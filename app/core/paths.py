"""Mốc đường dẫn dùng chung.

Trước đây mỗi file tự đếm `Path(__file__).resolve().parents[N]` để lần về thư
mục gốc — hễ chuyển file sang thư mục khác là N sai, mà sai kiểu này không nổ
ngay lúc import, chỉ lặng lẽ đọc/ghi nhầm chỗ. Nay khai báo một lần ở đây.
"""

from pathlib import Path

# app/core/paths.py -> app/core -> app -> gốc dự án
PROJECT_ROOT = Path(__file__).resolve().parents[2]

ENV_FILE = PROJECT_ROOT / ".env"
