"""Chép dữ liệu từ file SQLite CŨ (data/pancakebot.db) sang Postgres local.

Dự án đã bỏ backend SQLite; script này chỉ để CỨU dữ liệu còn sót trong file .db
cũ, chạy một lần rồi có thể xoá cả script lẫn file .db:

    python -m scripts.migrate_sqlite_to_postgres                       # xem trước
    python -m scripts.migrate_sqlite_to_postgres --apply               # ghi thật
    python -m scripts.migrate_sqlite_to_postgres --db data/khac.db --apply

Đích lấy từ DATABASE_URL trong .env (Postgres phải đang chạy). Nguồn đọc bằng
module `sqlite3` có sẵn của Python — KHÔNG cần backend sqlite (đã xoá) và không
gọi lại OpenAI: embedding trong file .db là BLOB float32, đọc thẳng ra list số.

An toàn: mặc định chạy khô; bảng đích đã có dữ liệu thì DỪNG (thêm --force để
xoá sạch bảng đích rồi chép lại).
"""

import argparse
import array
import json
import sqlite3
import sys
from pathlib import Path

from app.db.backends.postgres_be import PostgresBackend

TABLES = ("kich_ban", "hoi_thoai_mau", "trang_thai_khach")

# Cột để Postgres tự sinh — không chép sang.
SKIP_COLS = ("id", "created_at", "updated_at")

# Cột TEXT chứa JSON ở SQLite -> jsonb ở Postgres.
JSON_COLS = {"meta", "ngu_canh"}


def _from_blob(blob: bytes | None) -> list[float] | None:
    """BLOB float32 (cách backend sqlite cũ lưu) -> list[float]."""
    if blob is None:
        return None
    vec = array.array("f")
    vec.frombytes(blob)
    return list(vec)


def _rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    """Đọc cả bảng, đổi BLOB -> list số và TEXT JSON -> dict."""
    try:
        cur = conn.execute(f"select * from {table}")
    except sqlite3.OperationalError:
        return []                      # file .db cũ có thể thiếu bảng
    out = []
    for row in cur.fetchall():
        item = {}
        for key in row.keys():
            if key in SKIP_COLS:
                continue
            val = row[key]
            if key == "embedding":
                val = _from_blob(val)
            elif key in JSON_COLS:
                try:
                    val = json.loads(val) if val else {}
                except (TypeError, ValueError):
                    val = {}
            item[key] = val
        out.append(item)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/pancakebot.db", help="file .db nguồn")
    ap.add_argument("--apply", action="store_true", help="ghi thật (mặc định chạy khô)")
    ap.add_argument("--force", action="store_true", help="xoá sạch bảng đích rồi chép")
    args = ap.parse_args()

    path = Path(args.db)
    if not path.exists():
        print(f"Không thấy file nguồn: {path}")
        return 1

    src = sqlite3.connect(path)
    src.row_factory = sqlite3.Row
    dst = PostgresBackend()

    data = {t: _rows(src, t) for t in TABLES}
    for table, rows in data.items():
        have = dst.count(table)
        print(f"{table:<18} nguồn {len(rows):>5} dòng  ->  đích đang có {have} dòng")
        if have and rows and not args.force:
            print(
                f"\nDỪNG: bảng '{table}' ở Postgres đã có {have} dòng. Thêm --force "
                f"để xoá sạch rồi chép lại."
            )
            return 1

    if not args.apply:
        print("\n(chạy khô — thêm --apply để ghi thật)")
        return 0

    for table, rows in data.items():
        if not rows:
            continue
        if args.force:
            dst._exec(f"truncate {table} restart identity")   # noqa: SLF001
        for row in rows:
            dst._insert(table, row)                           # noqa: SLF001
        print(f"{table:<18} đã chép {len(rows)} dòng")

    print("\nXong. Kiểm tra ở trang /data rồi có thể xoá file .db cũ.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
