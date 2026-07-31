"""Seed TÀI KHOẢN cho đủ 9 cấp bậc (mục 3 BRD) + 2 đội có trưởng nhóm.

seed_auth.py đã tạo vai trò + quyền + admin; script này tạo phần NGƯỜI:

    chudn      Chủ doanh nghiệp          marketing  Marketing
    tnsale     Trưởng nhóm Sale (đội Sale)   ketoan     Kế toán
    sale01/02  Sale (đội Sale)               chuyenmon  Người chuyên môn
    tncskh     Trưởng nhóm CSKH (đội CSKH)
    cskh01/02  CSKH (đội CSKH)

Sale/CSKH tạo 2 người để luật CHIA VÒNG TRÒN của B3 có người mà chia.
Đội: "Đội Sale" (manager = tnsale) · "Đội CSKH" (manager = tncskh).

Mật khẩu sinh ngẫu nhiên, IN RA ĐÚNG MỘT LẦN lúc tạo — chép lại ngay, chạy
lại script sẽ KHÔNG in lại (tài khoản đã có thì giữ nguyên, muốn cấp lại:
--reset-passwords, hoặc admin dùng POST /api/v1/users/{id}/reset-password).

Chạy:  python scripts/seed_tai_khoan_mau.py
"""

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password    # noqa: E402
from app.db.client import get_pg_pool          # noqa: E402

# (username, tên hiển thị, vai trò, đội hoặc None)
TAI_KHOAN: list[tuple[str, str, str, str | None]] = [
    ("chudn",     "Chủ doanh nghiệp",   "Chủ doanh nghiệp",  None),
    ("tnsale",    "Trưởng nhóm Sale",   "Trưởng nhóm Sale",  "Đội Sale"),
    ("sale01",    "Sale 01",            "Sale",              "Đội Sale"),
    ("sale02",    "Sale 02",            "Sale",              "Đội Sale"),
    ("tncskh",    "Trưởng nhóm CSKH",   "Trưởng nhóm CSKH",  "Đội CSKH"),
    ("cskh01",    "CSKH 01",            "CSKH",              "Đội CSKH"),
    ("cskh02",    "CSKH 02",            "CSKH",              "Đội CSKH"),
    ("marketing", "Marketing",          "Marketing",         None),
    ("ketoan",    "Kế toán",            "Kế toán",           None),
    ("chuyenmon", "Người chuyên môn",   "Người chuyên môn",  None),
]

# (tên đội, department, username trưởng nhóm)
DOI: list[tuple[str, str, str]] = [
    ("Đội Sale", "sale", "tnsale"),
    ("Đội CSKH", "cskh", "tncskh"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reset-passwords", action="store_true",
                    help="Cấp lại mật khẩu MỚI cho các tài khoản mẫu đã có (trừ admin)")
    args = ap.parse_args()

    pool = get_pg_pool()
    bang_mk: list[tuple[str, str, str]] = []   # (username, vai trò, mật khẩu) — chỉ cái mới cấp
    with pool.connection() as conn:
        thieu_vai = conn.execute(
            "select count(*) as n from crm.roles"
        ).fetchone()["n"]
        if thieu_vai == 0:
            sys.exit("LOI: chua co vai tro nao — chay scripts/seed_auth.py truoc.")

        # --- đội (tạo trước, manager gắn sau vì phụ thuộc vòng teams<->users) ---
        doi_id: dict[str, int] = {}
        for ten, dept, _ in DOI:
            row = conn.execute(
                """
                insert into crm.teams (name, department) values (%s, %s)
                on conflict (name) do update set department = excluded.department
                returning id
                """,
                (ten, dept),
            ).fetchone()
            doi_id[ten] = row["id"]

        # --- tài khoản ---
        for username, ten, vai, doi in TAI_KHOAN:
            co = conn.execute(
                "select id from crm.users where username = %s", (username,)
            ).fetchone()
            if co and not args.reset_passwords:
                continue
            mk = secrets.token_urlsafe(9)
            if co:
                conn.execute(
                    "update crm.users set password_hash = %s, failed_login_count = 0, "
                    "locked_until = null, status = 'active' where id = %s",
                    (hash_password(mk), co["id"]),
                )
            else:
                conn.execute(
                    """
                    insert into crm.users (name, email, username, password_hash,
                                           status, role_id, team_id)
                    select %s, %s, %s, %s, 'active', r.id, %s
                      from crm.roles r where r.name = %s
                    """,
                    (ten, f"{username}@pancakebot.local", username,
                     hash_password(mk), doi_id.get(doi) if doi else None, vai),
                )
            bang_mk.append((username, vai, mk))

        # --- trưởng nhóm làm manager của đội ---
        for ten, _, sep in DOI:
            conn.execute(
                """
                update crm.teams t set manager_id = u.id
                  from crm.users u
                 where t.name = %s and u.username = %s
                """,
                (ten, sep),
            )

        so = conn.execute(
            "select count(*) as n from crm.users where status = 'active'"
        ).fetchone()["n"]

    if bang_mk:
        print("=" * 62)
        print("MAT KHAU CHI IN MOT LAN NAY — chep lai ngay:")
        print(f"  {'username':<12} {'vai tro':<20} mat khau")
        for u, v, mk in bang_mk:
            print(f"  {u:<12} {v:<20} {mk}")
        print("=" * 62)
        print("Dang nhap xong nen doi mat khau: POST /api/v1/auth/change-password")
    else:
        print("[seed] Tat ca tai khoan mau da co — khong cap lai mat khau "
              "(muon cap: --reset-passwords).")
    print(f"[seed] Tong tai khoan active: {so}")


if __name__ == "__main__":
    main()
