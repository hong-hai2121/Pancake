"""Kiểm thử màn 2 — Trang chủ theo vai trò (/crm/trang-chu).

Luật kiểm:
  * "/" chuyển hướng về /crm/trang-chu (FR-001 — đăng nhập xong vào dashboard
    theo vai trò).
  * Mỗi vai trò trong 9 vai trò thấy ĐÚNG khối của mình (marker riêng từng bản).
  * Vai trò lạ (tự tạo) rơi về bản "khac" — không vỡ trang.
  * Phạm vi số liệu: Sale chỉ thấy lead CỦA MÌNH; trưởng nhóm thấy CẢ ĐỘI
    (tra teams.manager_id trong DB) + hàng đợi lead chưa ai nhận.
  * Chưa đăng nhập thì bị đá về /dang-nhap.

Chạy:  python scripts/thu_trang_chu.py
Cần:   DB đang chạy + đã seed (seed_auth.py). KHÔNG cần server — TestClient.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Console Windows mặc định cp1252 — in tiếng Việt là vỡ; ép UTF-8 cho chắc
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient      # noqa: E402

from app.core.security import hash_password    # noqa: E402
from app.db.client import get_pg_pool          # noqa: E402
from app.main import app                       # noqa: E402

DAU = "__tc2__"
MK = "TrangChu-test-1234"
PASS = 0
FAIL = 0

# vai trò -> (marker PHẢI có trên trang của vai trò đó)
MARKER = {
    "Chủ doanh nghiệp": ["Chi phí QC 30 ngày", "Tổng quan chi tiết"],
    "Admin": ["Lỗi đồng bộ chờ thử lại", "Hoạt động gần đây"],
    "Trưởng nhóm Sale": ["Hàng đợi chưa nhận", "Tải theo nhân viên trong đội"],
    "Sale": ["Lead cần hành động sớm nhất", "Doanh thu giao TC tháng"],
    "Trưởng nhóm CSKH": ["Việc theo nhân viên trong đội", "Mốc chăm chờ làm"],
    "CSKH": ["Đơn chờ xác nhận (CS01)", "Mốc chăm chờ làm"],
    "Marketing": ["ROAS 30 ngày", "Chi phí QC 7 ngày"],
    "Kế toán": ["Đơn mới nhất", "Doanh thu giao TC hôm nay"],
    "Người chuyên môn": ["Ca chuyển chuyên môn chờ", "Khách cờ đỏ"],
}


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    conn.execute(
        "delete from crm.leads where customer_id in "
        f"(select id from crm.customers where full_name like '{DAU}%')"
    )
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.users where username like '{DAU}%'")
    conn.execute(f"delete from crm.teams where name like '{DAU}%'")
    conn.execute(f"delete from crm.roles where name like '{DAU}%'")


def tao_user(conn, username: str, ten: str, role_id, team_id=None) -> int:
    return conn.execute(
        """
        insert into crm.users (name, email, username, password_hash, role_id,
                               team_id, status)
        values (%s, %s, %s, %s, %s, %s, 'active') returning id
        """,
        (ten, f"{username}@test.local", username, hash_password(MK),
         role_id, team_id),
    ).fetchone()["id"]


def dang_nhap_web(client: TestClient, username: str) -> bool:
    """Đăng nhập kiểu form web (cookie HttpOnly) — đúng đường người dùng đi."""
    client.cookies.clear()
    r = client.post(
        "/dang-nhap",
        data={"username": username, "password": MK, "next": "/"},
        follow_redirects=False,
    )
    return r.status_code == 303


def main() -> None:
    client = TestClient(app)
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)
        vai = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        stage = conn.execute(
            "select id, pipeline_id from crm.pipeline_stages "
            "order by pipeline_id, sort_order limit 1"
        ).fetchone()

        # --- dựng: 1 đội Sale (trưởng nhóm + 2 sale), mỗi vai còn lại 1 người ---
        doi = conn.execute(
            f"insert into crm.teams (name, department) values ('{DAU}DoiSale', "
            "'sale') returning id"
        ).fetchone()["id"]
        uid: dict[str, int] = {}
        uid["Trưởng nhóm Sale"] = tao_user(
            conn, f"{DAU}tnsale", f"{DAU}TN Sale", vai["Trưởng nhóm Sale"], doi)
        conn.execute("update crm.teams set manager_id = %s where id = %s",
                     (uid["Trưởng nhóm Sale"], doi))
        uid["Sale"] = tao_user(conn, f"{DAU}saleA", f"{DAU}Sale A", vai["Sale"], doi)
        sale_b = tao_user(conn, f"{DAU}saleB", f"{DAU}Sale B", vai["Sale"], doi)
        for ten_vai, tk in [("Chủ doanh nghiệp", "chudn"), ("Admin", "admin2"),
                            ("Trưởng nhóm CSKH", "tncskh"), ("CSKH", "cskh"),
                            ("Marketing", "mkt"), ("Kế toán", "ketoan"),
                            ("Người chuyên môn", "chmon")]:
            uid[ten_vai] = tao_user(conn, DAU + tk, DAU + ten_vai, vai[ten_vai])

        # vai trò LẠ — không có trong ánh xạ, phải rơi về bản "khac"
        vai_la = conn.execute(
            f"insert into crm.roles (name) values ('{DAU}VaiLa') returning id"
        ).fetchone()["id"]
        uid_la = tao_user(conn, f"{DAU}vaila", f"{DAU}Vai La", vai_la)

        # dữ liệu phạm vi: 1 lead của saleB + 1 lead chưa ai nhận
        kh1 = conn.execute(
            f"insert into crm.customers (full_name) values ('{DAU}Khach B') "
            "returning id").fetchone()["id"]
        kh2 = conn.execute(
            f"insert into crm.customers (full_name) values ('{DAU}Khach doi') "
            "returning id").fetchone()["id"]
        conn.execute(
            "insert into crm.leads (customer_id, pipeline_id, stage_id, owner_id)"
            " values (%s, %s, %s, %s)",
            (kh1, stage["pipeline_id"], stage["id"], sale_b),
        )
        conn.execute(
            "insert into crm.leads (customer_id, pipeline_id, stage_id, owner_id)"
            " values (%s, %s, %s, null)",
            (kh2, stage["pipeline_id"], stage["id"]),
        )

    print("== Màn 2 — Trang chủ theo vai trò ==")

    # 1. chưa đăng nhập -> bị đá về /dang-nhap
    client.cookies.clear()
    r = client.get("/crm/trang-chu", follow_redirects=False)
    ok("chưa đăng nhập bị đá về /dang-nhap",
       r.status_code in (302, 303, 307) and "/dang-nhap" in r.headers.get("location", ""),
       f"status={r.status_code}")

    # 2. "/" trỏ về trang chủ theo vai trò
    ok("đăng nhập web (saleA)", dang_nhap_web(client, f"{DAU}saleA"))
    r = client.get("/", follow_redirects=False)
    ok('"/" chuyển hướng về /crm/trang-chu',
       r.headers.get("location", "") == "/crm/trang-chu",
       f"location={r.headers.get('location')}")

    # 3. từng vai trò thấy đúng bản của mình
    tk_theo_vai = {
        "Chủ doanh nghiệp": "chudn", "Admin": "admin2",
        "Trưởng nhóm Sale": "tnsale", "Sale": "saleA",
        "Trưởng nhóm CSKH": "tncskh", "CSKH": "cskh", "Marketing": "mkt",
        "Kế toán": "ketoan", "Người chuyên môn": "chmon",
    }
    for ten_vai, tk in tk_theo_vai.items():
        if not dang_nhap_web(client, DAU + tk):
            ok(f"[{ten_vai}] đăng nhập", False, "login hỏng")
            continue
        r = client.get("/crm/trang-chu")
        thieu = [m for m in MARKER[ten_vai] if m not in r.text]
        ok(f"[{ten_vai}] thấy đúng bản của mình",
           r.status_code == 200 and not thieu,
           f"status={r.status_code} thiếu={thieu}")

    # 4. vai trò lạ không vỡ trang, rơi về bản "khac"
    ok("đăng nhập vai trò lạ", dang_nhap_web(client, f"{DAU}vaila"))
    r = client.get("/crm/trang-chu")
    ok("vai trò lạ rơi về bản 'khac'",
       r.status_code == 200 and "Chưa nhận diện vai trò" in r.text,
       f"status={r.status_code}")

    # 5. phạm vi số liệu (gọi thẳng repo — số trên trang là số này)
    from app.db.repositories import crm_screens_repo as repo

    d_a = repo.trang_chu("sale", uid["Sale"])
    ok("Sale A không thấy lead của Sale B", d_a["lead"]["mo"] == 0,
       f"mo={d_a['lead']['mo']}")
    d_b = repo.trang_chu("sale", sale_b)
    ok("Sale B thấy lead của mình", d_b["lead"]["mo"] == 1,
       f"mo={d_b['lead']['mo']}")
    d_tn = repo.trang_chu("sale_tn", uid["Trưởng nhóm Sale"])
    ok("Trưởng nhóm thấy lead cả đội", d_tn["lead"]["mo"] == 1,
       f"mo={d_tn['lead']['mo']}")
    ok("Trưởng nhóm thấy hàng đợi chưa nhận", d_tn["hang_doi"] >= 1,
       f"hang_doi={d_tn['hang_doi']}")
    ok("Bảng tải theo nhân viên đủ 3 người đội Sale",
       len(d_tn["theo_nv"]) == 3, f"n={len(d_tn['theo_nv'])}")

    with pool.connection() as conn:
        don_dep(conn)

    print(f"\nKết quả: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
