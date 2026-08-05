"""Kiểm thử phân cấp tạo tài khoản (mở rộng A5 — quyền `user.manage_team`).

Luật kiểm: Chủ DN/Admin (`user.manage`) tạo mọi cấp như cũ; trưởng nhóm
Sale/CSKH (`user.manage_team`) chỉ THẤY đội mình, chỉ TẠO + reset mật khẩu
cho vai trò thành viên đội mình; sửa/khoá/chuyển khách vẫn cấm.

Chạy:  python scripts/thu_quan_tri_doi.py
Cần:   DB đang chạy + đã seed (seed_auth đã có quyền user.manage_team).
KHÔNG cần server — TestClient gọi thẳng vào app.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient      # noqa: E402

from app.core.config import settings           # noqa: E402
from app.core.security import hash_password    # noqa: E402
from app.db.client import get_pg_pool          # noqa: E402
from app.main import app                       # noqa: E402

DAU = "__qtd__"
MK = "Qtd-test-1234"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    conn.execute(f"delete from crm.users where username like '{DAU}%'")
    conn.execute(f"delete from crm.teams where name like '{DAU}%'")


def dang_nhap(client: TestClient, username: str, password: str) -> dict:
    r = client.post("/api/v1/auth/login",
                    json={"username": username, "password": password})
    assert r.status_code == 200, f"login {username} loi: {r.text[:200]}"
    return r.json()["data"]


def main() -> None:
    client = TestClient(app)
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)
        vai = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles"
        ).fetchall()}
        doi = conn.execute(
            "insert into crm.teams (name, department) values (%s, 'sale') returning id",
            (f"{DAU}DoiSale",),
        ).fetchone()["id"]

        def tao(username: str, role: str, team_id=None) -> int:
            return conn.execute(
                "insert into crm.users (name, email, username, password_hash, "
                "status, role_id, team_id) values (%s, %s, %s, %s, 'active', %s, %s) "
                "returning id",
                (username, f"{username}@x.com", username, hash_password(MK),
                 vai[role], team_id),
            ).fetchone()["id"]

        tns = tao(f"{DAU}tns", "Trưởng nhóm Sale", doi)      # trưởng nhóm chuẩn
        sale1 = tao(f"{DAU}sale1", "Sale", doi)              # sale con trong đội
        tns2 = tao(f"{DAU}tns2", "Trưởng nhóm Sale", None)   # trưởng nhóm CHƯA có đội
        conn.execute("update crm.teams set manager_id = %s where id = %s", (tns, doi))

    print("== 0. Đăng nhập ==")
    admin = dang_nhap(client, "admin", settings.admin_bootstrap_password)
    ha = {"Authorization": f"Bearer {admin['access_token']}"}
    tn = dang_nhap(client, f"{DAU}tns", MK)
    ht = {"Authorization": f"Bearer {tn['access_token']}"}
    perms = tn["user"]["permissions"]
    ok("token trưởng nhóm mang user.manage_team, KHÔNG mang user.manage",
       "user.manage_team" in perms and "user.manage" not in perms, str(perms))

    print("== 1. Trưởng nhóm chỉ thấy đội mình ==")
    r = client.get("/api/v1/users", headers=ht)
    items = r.json()["data"]["items"]
    ok("GET /users 200", r.status_code == 200, r.text[:200])
    ok("chỉ thấy 2 người trong đội (tns + sale1)",
       {u["username"] for u in items} == {f"{DAU}tns", f"{DAU}sale1"},
       str([u["username"] for u in items]))

    print("== 2. Trưởng nhóm tạo sale con ==")
    r = client.post("/api/v1/users", headers=ht, json={
        "name": f"{DAU}Sale moi", "email": f"{DAU}moi@x.com",
        "username": f"{DAU}salemoi",
    })
    ok("POST /users 201 (không cần chọn vai trò)", r.status_code == 201, r.text[:200])
    moi = r.json()["data"]
    ok("vai trò bị ÉP = Sale, đội = đội mình",
       moi["role_id"] == vai["Sale"] and moi["team_id"] == doi)
    ok("có initial_password trả một lần", bool(moi.get("initial_password")))
    r = client.post("/api/v1/auth/login", json={
        "username": f"{DAU}salemoi", "password": moi["initial_password"],
    })
    ok("sale con mới đăng nhập được ngay", r.status_code == 200, r.text[:200])

    print("== 3. Trưởng nhóm KHÔNG leo thang được ==")
    r = client.post("/api/v1/users", headers=ht, json={
        "name": f"{DAU}Leo", "email": f"{DAU}leo@x.com",
        "username": f"{DAU}leo", "role_id": vai["Trưởng nhóm Sale"],
    })
    ok("xin tạo Trưởng nhóm -> 403", r.status_code == 403, r.text[:200])
    r = client.post("/api/v1/users", headers=ht, json={
        "name": f"{DAU}Leo", "email": f"{DAU}leo@x.com",
        "username": f"{DAU}leo", "role_id": vai["Admin"],
    })
    ok("xin tạo Admin -> 403", r.status_code == 403)

    print("== 4. Reset mật khẩu trong/ngoài phạm vi ==")
    r = client.post(f"/api/v1/users/{sale1}/reset-password", headers=ht)
    mk_sale1 = (r.json().get("data") or {}).get("new_password") or MK
    ok("reset MK sale con trong đội -> 200 + new_password",
       r.status_code == 200 and bool(r.json()["data"].get("new_password")),
       r.text[:200])
    admin_id = int(admin["user"]["id"])
    r = client.post(f"/api/v1/users/{admin_id}/reset-password", headers=ht)
    ok("reset MK người ngoài đội (admin) -> 403", r.status_code == 403, r.text[:200])

    print("== 5. Sửa/khoá/chuyển khách vẫn là việc của Admin ==")
    r = client.put(f"/api/v1/users/{sale1}", headers=ht, json={"name": "Doi ten"})
    ok("PUT /users -> 403", r.status_code == 403)
    r = client.patch(f"/api/v1/users/{sale1}/status", headers=ht,
                     json={"status": "suspended"})
    ok("PATCH status -> 403", r.status_code == 403)
    r = client.post(f"/api/v1/users/{sale1}/transfer-customers", headers=ht,
                    json={"new_owner_id": tns})
    ok("POST transfer -> 403", r.status_code == 403)

    print("== 6. Sale thường + trưởng nhóm chưa gán đội ==")
    s1 = dang_nhap(client, f"{DAU}sale1", mk_sale1)  # MK vừa được cấp lại ở mục 4
    r = client.get("/api/v1/users",
                   headers={"Authorization": f"Bearer {s1['access_token']}"})
    ok("sale thường GET /users -> 403", r.status_code == 403)
    t2 = dang_nhap(client, f"{DAU}tns2", MK)
    r = client.get("/api/v1/users",
                   headers={"Authorization": f"Bearer {t2['access_token']}"})
    ok("trưởng nhóm CHƯA có đội -> 403 kèm lời nhắn",
       r.status_code == 403 and "trưởng nhóm" in r.json()["message"], r.text[:200])

    print("== 7. Admin vẫn toàn quyền như cũ ==")
    r = client.post("/api/v1/users", headers=ha, json={
        "name": f"{DAU}CSKH x", "email": f"{DAU}ck@x.com",
        "username": f"{DAU}cskhx", "role_id": vai["CSKH"],
    })
    ok("admin tạo CSKH (vai trò tự chọn) -> 201",
       r.status_code == 201 and r.json()["data"]["role_id"] == vai["CSKH"],
       r.text[:200])

    print("== 8. Màn web /quan-tri/nhan-vien ==")
    web_tn = TestClient(app)
    web_tn.cookies.set("access_token", tn["access_token"])
    r = web_tn.get("/quan-tri/nhan-vien")
    ok("trưởng nhóm mở màn -> 200 bản thu gọn",
       r.status_code == 200 and "trưởng nhóm tạo tài khoản" in r.text)
    ok("bản thu gọn KHÔNG có nút Khoá / link hồ sơ",
       ">Khoá<" not in r.text and f"/quan-tri/nhan-vien/{sale1}\"><b>" not in r.text)
    r = web_tn.post("/quan-tri/nhan-vien", data={
        "name": f"{DAU}Tu form", "email": f"{DAU}form@x.com",
        "username": f"{DAU}tuform",
    })
    ok("tạo từ form web chạy (thấy mật khẩu một lần)",
       r.status_code == 200 and "hiện MỘT lần" in r.text, r.text[:200])
    with pool.connection() as conn:
        u = conn.execute(
            f"select role_id, team_id from crm.users where username = '{DAU}tuform'"
        ).fetchone()
    ok("tài khoản từ form đúng vai trò Sale + đúng đội",
       u and u["role_id"] == vai["Sale"] and u["team_id"] == doi)

    web_s1 = TestClient(app)
    web_s1.cookies.set("access_token", s1["access_token"])
    r = web_s1.get("/quan-tri/nhan-vien")
    ok("sale thường mở màn -> 403", r.status_code == 403)

    print("== 9. Khu Bot Pancake chỉ cấp toàn hệ thống (bot.view) ==")
    web_ad = TestClient(app)
    web_ad.cookies.set("access_token", admin["access_token"])
    r = web_ad.get("/bang-dieu-khien")
    ok("admin vào /bang-dieu-khien -> 200", r.status_code == 200, str(r.status_code))
    for duong in ("/bang-dieu-khien", "/tin-nhan", "/khach-hang",
                  "/cam-xuc", "/data/kich-ban", "/pancake/pages"):
        r = web_tn.get(duong)
        ok(f"trưởng nhóm vào {duong} -> 403", r.status_code == 403, str(r.status_code))
    r = web_tn.get("/quan-tri/nhan-vien")
    # "Chung" là nhóm đầu menu CRM (trước 04/08/2026 tên là "CRM" — đổi khi sắp
    # lại menu theo mẫu Kallet). Mọi mục trong nhóm này không đòi quyền nên
    # trưởng nhóm chắc chắn thấy -> dùng làm mốc "menu CRM vẫn còn".
    # Dò '>Bot Pancake<' / '>Chung<' chứ KHÔNG kèm thẻ đóng: MỌI nhóm có tên nay
    # là <summary> xổ/thu (_NHOM_THU_GON) chứ không còn <div class="nav-group">.
    ok("menu trưởng nhóm KHÔNG còn nhóm Bot Pancake",
       ">Bot Pancake<" not in r.text and ">Chung<" in r.text)
    r = web_ad.get("/quan-tri/nhan-vien")
    ok("menu admin vẫn có nhóm Bot Pancake", ">Bot Pancake<" in r.text)

    with pool.connection() as conn:
        don_dep(conn)

    print(f"\n== KẾT QUẢ: {PASS} PASS · {FAIL} FAIL ==")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
