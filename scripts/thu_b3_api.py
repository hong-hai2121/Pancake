"""Kiểm thử tầng API của B3 (LEAD-001…011, PIPELINE-001…004) qua TestClient.

Tầng luật đã kiểm riêng ở scripts/thu_b3.py (25/25) — file này chỉ kiểm phần
API: khuôn phản hồi A3, phân quyền, mã lỗi, route matching (overdue/hot vs {id}).

Chạy:  python scripts/thu_b3_api.py
Cần:   DB đang chạy + đã seed (seed_auth, seed_danh_muc). KHÔNG cần server —
TestClient gọi thẳng vào app (không bật lifespan nên không kéo worker nền).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient      # noqa: E402

from app.core.config import settings           # noqa: E402
from app.db.client import get_pg_pool          # noqa: E402
from app.main import app                       # noqa: E402

DAU = "__b3api__"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    conn.execute(f"delete from crm.leads where source like '{DAU}%'")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:
    client = TestClient(app)
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)
        kh = conn.execute(
            "insert into crm.customers (full_name) values (%s) returning id",
            (f"{DAU}Khach",),
        ).fetchone()["id"]
        role_sale = conn.execute(
            "select id from crm.roles where name = 'Sale'"
        ).fetchone()["id"]
        sale = conn.execute(
            "insert into crm.users (name, email, status, role_id) "
            "values (%s, %s, 'active', %s) returning id",
            (f"{DAU}Sale", f"{DAU}s@x.com", role_sale),
        ).fetchone()["id"]
        ly_do = conn.execute(
            "select id from crm.lead_reasons where code = 'gia_cao'"
        ).fetchone()["id"]

    print("== 0. Đăng nhập ==")
    r = client.post("/api/v1/auth/login", json={
        "username": "admin", "password": settings.admin_bootstrap_password,
    })
    ok("login admin 200 + đúng khuôn", r.status_code == 200 and r.json()["success"])
    token = r.json()["data"]["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    print("== 1. Chặn khi thiếu quyền/token ==")
    r = client.get("/api/v1/leads")
    ok("không token -> 401", r.status_code == 401)
    r = client.get("/api/v1/pipelines", headers=h)
    ok("GET /pipelines 200, thấy 'Bán mới'",
       r.status_code == 200 and any(p["name"] == "Bán mới" for p in r.json()["data"]["items"]))

    print("== 2. Vòng đời lead qua API ==")
    r = client.post("/api/v1/leads", headers=h, json={
        "customer_id": kh, "source": f"{DAU}fb", "temperature": "nong",
    })
    ok("POST /leads 201", r.status_code == 201, r.text[:200])
    lead = r.json()["data"]
    lid = lead["id"]
    ok("chia tự động có owner", lead["owner_id"] is not None)

    r = client.get(f"/api/v1/pipelines/{lead['pipeline_id']}/stages", headers=h)
    stages = {s["code"]: s["id"] for s in r.json()["data"]["items"]}
    ok("PIPELINE-003 trả 13 giai đoạn", len(stages) == 13, f"được {len(stages)}")

    r = client.post(f"/api/v1/leads/{lid}/move-stage", headers=h,
                    json={"stage_id": stages["dang_can_nhac"]})
    ok("luật chặn trả đúng mã MISSING_REQUIRED_DATA (422)",
       r.status_code == 422 and r.json()["error_code"] == "MISSING_REQUIRED_DATA")

    r = client.post(f"/api/v1/leads/{lid}/move-stage", headers=h, json={
        "stage_id": stages["da_ket_noi"], "reason": "khách rep tin nhắn",
    })
    ok("move sang 'Đã kết nối' 200", r.status_code == 200)
    ok("first_contact_at được ghi", r.json()["data"]["first_contact_at"] is not None)

    r = client.get("/api/v1/leads/hot", headers=h)
    ok("route /leads/hot không bị /leads/{id} nuốt",
       r.status_code == 200 and lid in [x["id"] for x in r.json()["data"]["items"]])

    r = client.put(f"/api/v1/leads/{lid}", headers=h, json={"temperature": "am"})
    ok("LEAD-004 đổi nhiệt độ", r.json()["data"]["temperature"] == "am")

    r = client.post(f"/api/v1/leads/{lid}/assign", headers=h,
                    json={"user_id": sale, "reason": "giao chuyên trách"})
    ok("LEAD-007 gán sale", r.json()["data"]["owner_id"] == sale)

    r = client.post(f"/api/v1/leads/{lid}/close", headers=h, json={
        "stage_code": "tu_choi", "lost_reason_id": ly_do, "note": "chê đắt",
    })
    ok("LEAD-011 đóng kèm lý do chuẩn", r.status_code == 200
       and r.json()["data"]["closed_at"] is not None)

    r = client.get(f"/api/v1/leads/{lid}/stage-history", headers=h)
    ok("LEAD-006 lịch sử 3 dòng", len(r.json()["data"]["items"]) == 3)

    r = client.get("/api/v1/leads", headers=h,
                   params={"trang_thai": "closed", "customer_id": kh})
    d = r.json()["data"]
    ok("LEAD-001 lọc closed + phân trang chuẩn A3",
       d["pagination"]["total"] >= 1 and lid in [x["id"] for x in d["items"]])

    print("== 3. Quyền pipeline ==")
    # Admin có user.manage nên tạo được; kiểm khuôn lỗi trùng tên
    r = client.post("/api/v1/pipelines", headers=h, json={"name": "Bán mới"})
    ok("trùng tên pipeline -> VALIDATION_ERROR",
       r.status_code == 422 and r.json()["error_code"] == "VALIDATION_ERROR")

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKẾT QUẢ: {PASS} PASS / {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
