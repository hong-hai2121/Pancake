"""Đồng bộ DB theo file mới nhất trong repo — CHẠY SAU MỖI LẦN `git pull`.

Vì sao cần: database KHÔNG nằm trong git (dữ liệu ở volume Docker `pgdata`,
xem .gitignore), và app lúc khởi động cũng không tự chạy migration. Nên kéo
code mới về mà không đồng bộ thì DB lệch so với code — và lệch KHÔNG báo lỗi
gì cho tới khi có câu truy vấn chạm đúng chỗ thiếu rồi nổ 500 giữa chừng.

Gói 4 bước vào 1 lệnh, tất cả đều idempotent (chạy lại bao nhiêu lần cũng được,
không mất dữ liệu, không cấp lại mật khẩu đã có):

    1. scripts/init_crm.sql        bảng · cột · index · khoá ngoại · trigger
    2. scripts/seed_auth.py        vai trò · quyền · ma trận quyền · admin
    3. scripts/seed_danh_muc.py    giai đoạn Sale · lý do · mã ref · triệu chứng
    4. scripts/seed_tai_khoan_mau.py  tài khoản 9 cấp bậc · 2 đội có trưởng nhóm

Chạy:  python scripts/dong_bo_db.py
       python scripts/dong_bo_db.py --chi-schema   (chỉ bước 1, bỏ seed)

Xong nên chạy tiếp test suite để chắc chắn: python scripts/thu_b1.py ...
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GOC))

from app.core.config import settings          # noqa: E402

SEED = ["seed_auth.py", "seed_danh_muc.py", "seed_tai_khoan_mau.py"]


def nap_schema() -> None:
    """Chạy init_crm.sql qua psycopg — không phụ thuộc docker hay psql trên PATH.

    autocommit=True để chính `begin; ... commit;` bên trong file cầm trịch
    giao dịch; `set local search_path` nhờ vậy vẫn có tác dụng.
    """
    import psycopg

    sql = (GOC / "scripts" / "init_crm.sql").read_text(encoding="utf-8")
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute(sql)


def chay_seed(ten: str) -> None:
    r = subprocess.run([sys.executable, str(GOC / "scripts" / ten)],
                       cwd=GOC, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    for dong in (r.stdout or "").splitlines():
        print(f"      {dong}")
    if r.returncode != 0:
        print((r.stderr or "").strip()[-800:])
        raise RuntimeError(f"{ten} thoat voi ma {r.returncode}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chi-schema", action="store_true",
                    help="Chỉ nạp init_crm.sql, bỏ qua 3 script seed")
    args = ap.parse_args()

    if settings.db_backend != "postgres":
        sys.exit(f"LOI: DB_BACKEND={settings.db_backend} — script nay chi dong bo "
                 "Postgres. Doi DB_BACKEND=postgres trong .env.")

    viec: list[tuple[str, callable]] = [("init_crm.sql", nap_schema)]
    if not args.chi_schema:
        viec += [(ten, lambda t=ten: chay_seed(t)) for ten in SEED]

    for i, (ten, ham) in enumerate(viec, 1):
        print(f"[{i}/{len(viec)}] {ten}")
        t0 = time.monotonic()
        try:
            ham()
        except Exception as e:                       # noqa: BLE001
            print(f"      THAT BAI: {e}")
            sys.exit(f"\nDung o buoc {i} ({ten}) — DB CHUA dong bo xong.")
        print(f"      xong ({time.monotonic() - t0:.1f}s)")

    print("\n[dong_bo_db] DB da khop voi code trong repo.")
    print("[dong_bo_db] Doi/them QUYEN thi phai DANG XUAT rồi DANG NHAP LAI — "
          "token JWT mang san danh sach quyen, khong tu cap nhat.")


if __name__ == "__main__":
    main()
