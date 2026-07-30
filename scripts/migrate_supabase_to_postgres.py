"""Sao dữ liệu từ Supabase (cloud) xuống Postgres cài ở máy.

Chạy từ thư mục gốc dự án:

    python -m scripts.migrate_supabase_to_postgres            # xem trước, KHÔNG ghi
    python -m scripts.migrate_supabase_to_postgres --apply    # ghi thật

Cần .env có đủ SUPABASE_URL + SUPABASE_KEY (đọc nguồn) và DATABASE_URL (đích).
Script KHÔNG phụ thuộc DB_BACKEND đang đặt là gì — nó dựng thẳng 2 backend nên
chạy được ở cả hai chiều cấu hình.

An toàn:
  * Mặc định chạy khô (dry-run), phải thêm --apply mới ghi.
  * Nếu bảng đích đã có dữ liệu, script DỪNG và báo — tránh nhân đôi khi lỡ
    chạy hai lần. Thêm --force để ghi đè (XOÁ sạch bảng đích rồi chép lại).
  * Embedding được chép NGUYÊN VẸN, không gọi lại OpenAI (không tốn tiền, không
    lệch vector).
  * `id` KHÔNG được chép: cột id ở Postgres là `generated always as identity`
    nên để DB tự cấp. Ba bảng này không tham chiếu id lẫn nhau nên vô hại.
"""

import argparse
import sys

from app.db.backends.postgres_be import PostgresBackend
from app.db.backends.supabase_be import SupabaseBackend

# Thứ tự chép không quan trọng (3 bảng độc lập, không có khoá ngoại).
TABLES = ("kich_ban", "hoi_thoai_mau", "trang_thai_khach")

# Cột do DB đích tự sinh — bỏ đi khi chép.
SKIP_COLS = ("id", "created_at", "updated_at")


def _read_all(table: str) -> list[dict]:
    """Đọc toàn bộ 1 bảng từ Supabase, kèm cả cột embedding.

    Dùng thẳng client REST vì giao diện Backend cố tình không có hàm "dump cả
    bảng kèm vector" (không route nào của app cần tới).
    """
    from app.db.client import get_supabase

    res = get_supabase().table(table).select("*").execute()
    return res.data or []


def _to_vector(raw) -> list[float] | None:
    """pgvector về qua REST có thể là list, hoặc chuỗi '[0.1,0.2,...]'."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return [float(x) for x in raw.strip("[]").split(",") if x.strip()]
    return [float(x) for x in raw]


def _target_columns(dst: PostgresBackend, table: str) -> set[str]:
    """Tên các cột thật sự có ở bảng đích (Supabase có thể thừa cột)."""
    rows = dst._all(  # noqa: SLF001 — script bảo trì, dùng thẳng backend
        "select column_name from information_schema.columns"
        " where table_schema = 'public' and table_name = %s",
        (table,),
    )
    return {r["column_name"] for r in rows}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="ghi thật (mặc định chạy khô)")
    ap.add_argument("--force", action="store_true", help="xoá sạch bảng đích rồi chép")
    args = ap.parse_args()

    dst = PostgresBackend()

    data = {t: _read_all(t) for t in TABLES}
    for table, rows in data.items():
        have = dst.count(table)
        print(f"{table:<18} nguồn {len(rows):>5} dòng  ->  đích đang có {have} dòng")
        if have and not args.force:
            print(
                f"\nDỪNG: bảng '{table}' ở Postgres đã có {have} dòng. Thêm --force "
                f"để xoá sạch rồi chép lại."
            )
            return 1

    if not args.apply:
        print("\n(chạy khô — thêm --apply để ghi thật)")
        return 0

    for table, rows in data.items():
        cols = _target_columns(dst, table)
        if args.force:
            dst._exec(f"truncate {table} restart identity")  # noqa: SLF001
        for row in rows:
            payload = {
                k: v for k, v in row.items() if k in cols and k not in SKIP_COLS
            }
            if "embedding" in payload:
                payload["embedding"] = _to_vector(payload["embedding"])
            dst._insert(table, payload)   # noqa: SLF001
        print(f"{table:<18} đã chép {len(rows)} dòng")

    print("\nXong. Đặt DB_BACKEND=postgres trong .env rồi khởi động lại app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
