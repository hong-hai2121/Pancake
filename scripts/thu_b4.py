"""Kiểm thử B4 — task engine (mục 19 BRD + TASK-001…009), tự dọn sạch.

Nửa đầu kiểm TẦNG LUẬT (gọi thẳng task_service), nửa sau kiểm TẦNG API qua
TestClient (khuôn A3, phân quyền, route matching today/overdue vs {id}) và
màn /crm/cong-viec.

Chạy:  python scripts/thu_b4.py
Cần:   DB đang chạy + đã seed (seed_auth.py). Dữ liệu test mang dấu __b4test__.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient      # noqa: E402

from app.core.config import settings           # noqa: E402
from app.core.errors import ApiError           # noqa: E402
from app.db.client import get_pg_pool          # noqa: E402
from app.main import app                       # noqa: E402
from app.services import task_service          # noqa: E402

DAU = "__b4test__"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def phai_loi(ten: str, ma: str, fn, *a, **kw) -> None:
    try:
        fn(*a, **kw)
        ok(ten, False, "không raise gì cả")
    except ApiError as e:
        ok(ten, e.code == ma, f"raise {e.code} thay vì {ma}")


def don_dep(conn) -> None:
    conn.execute(f"delete from crm.tasks where title like '{DAU}%'")
    conn.execute(f"delete from crm.orders where external_order_id like '{DAU}%'")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def mai() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=1)


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)
        role_sale = conn.execute(
            "select id from crm.roles where name = 'Sale'"
        ).fetchone()["id"]

        def tao_user(ten: str, status: str = "active") -> int:
            return conn.execute(
                "insert into crm.users (name, email, status, role_id) "
                "values (%s, %s, %s, %s) returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", status, role_sale),
            ).fetchone()["id"]

        s1, s2 = tao_user("Sale 1"), tao_user("Sale 2")
        khoa = tao_user("Da khoa", status="suspended")
        kh = conn.execute(
            "insert into crm.customers (full_name) values (%s) returning id",
            (f"{DAU}Khach",),
        ).fetchone()["id"]
        don = conn.execute(
            "insert into crm.orders (customer_id, external_order_id, status) "
            "values (%s, %s, 'confirmed') returning id",
            (kh, f"{DAU}don1"),
        ).fetchone()["id"]

    chuan = {"title": f"{DAU}goi kh", "task_type": "goi",
             "assigned_to": s1, "due_at": mai(), "customer_id": kh}

    print("== 1. Luật tạo việc (owner + hạn bắt buộc — mục 19) ==")
    phai_loi("thiếu người phụ trách -> chặn", "MISSING_REQUIRED_DATA",
             task_service.create_task, {**chuan, "assigned_to": None})
    phai_loi("thiếu hạn due_at -> chặn", "MISSING_REQUIRED_DATA",
             task_service.create_task, {**chuan, "due_at": None})
    phai_loi("loại việc lạ -> chặn", "VALIDATION_ERROR",
             task_service.create_task, {**chuan, "task_type": "bay_nhay"})
    phai_loi("giao người bị khoá -> chặn", "CONFLICT",
             task_service.create_task, {**chuan, "assigned_to": khoa})
    t1 = task_service.create_task(dict(chuan))
    ok("tạo hợp lệ -> open", t1["status"] == "open" and t1["assignee_name"] is not None)
    with pool.connection() as conn:
        n = conn.execute(
            "select count(*) as n from crm.audit_logs "
            "where action = 'task_create' and object_id = %s", (t1["id"],),
        ).fetchone()["n"]
    ok("tạo việc có vết audit", n == 1)

    print("== 2. Liên kết đa hình tự kiểm ==")
    phai_loi("related_type không kèm related_id -> chặn", "VALIDATION_ERROR",
             task_service.create_task, {**chuan, "related_type": "order"})
    phai_loi("related trỏ bản ghi ma -> NOT_FOUND", "NOT_FOUND",
             task_service.create_task,
             {**chuan, "related_type": "order", "related_id": 999999999})
    t2 = task_service.create_task(
        {**chuan, "task_type": "xac_nhan_don",
         "related_type": "order", "related_id": don})
    ok("gắn đơn có thật -> tạo được", t2["related_id"] == don)

    print("== 3. Không đóng việc nếu thiếu kết quả (mục 19) ==")
    phai_loi("complete không result -> chặn", "MISSING_REQUIRED_DATA",
             task_service.complete_task, t1["id"], "")
    phai_loi("complete result toàn khoảng trắng -> chặn", "MISSING_REQUIRED_DATA",
             task_service.complete_task, t1["id"], "   ")
    t1b = task_service.complete_task(t1["id"], "đã gọi, khách hẹn mai chốt")
    ok("complete kèm kết quả -> done + completed_at",
       t1b["status"] == "done" and t1b["completed_at"] is not None
       and t1b["result"].startswith("đã gọi"))
    phai_loi("complete lần 2 -> CONFLICT", "CONFLICT",
             task_service.complete_task, t1["id"], "lại nữa")
    phai_loi("sửa việc đã done -> CONFLICT", "CONFLICT",
             task_service.update_task, t1["id"], {"priority": "high"})
    phai_loi("lách luật: update status=done -> chặn", "CONFLICT",
             task_service.update_task, t2["id"], {"status": "done"})

    print("== 4. Huỷ / dời lịch / chuyển người — đều phải có lý do ==")
    phai_loi("huỷ thiếu lý do -> chặn", "MISSING_REQUIRED_DATA",
             task_service.update_task, t2["id"], {"status": "cancelled"})
    t3 = task_service.create_task({**chuan, "title": f"{DAU}viec 3"})
    phai_loi("dời lịch thiếu lý do -> chặn", "MISSING_REQUIRED_DATA",
             task_service.reschedule_task, t3["id"], mai())
    phai_loi("dời lịch về quá khứ -> chặn", "VALIDATION_ERROR",
             task_service.reschedule_task, t3["id"],
             datetime.now(timezone.utc) - timedelta(hours=1), reason="lùi")
    han_moi = mai() + timedelta(days=1)
    t3b = task_service.reschedule_task(t3["id"], han_moi, reason="khách hẹn lại")
    ok("dời lịch hợp lệ -> hạn mới", abs((t3b["due_at"] - han_moi).total_seconds()) < 2)
    phai_loi("chuyển người thiếu lý do -> chặn", "MISSING_REQUIRED_DATA",
             task_service.reassign_task, t3["id"], s2)
    phai_loi("chuyển sang người bị khoá -> chặn", "CONFLICT",
             task_service.reassign_task, t3["id"], khoa, reason="thử")
    t3c = task_service.reassign_task(t3["id"], s2, reason="Sale 1 nghỉ phép")
    ok("chuyển hợp lệ -> đổi người", t3c["assigned_to"] == s2)
    t3d = task_service.update_task(t3["id"], {"status": "cancelled",
                                              "reason": "khách bom"})
    ok("huỷ kèm lý do -> cancelled", t3d["status"] == "cancelled")

    print("== 5. Việc hôm nay + quá hạn + leo thang ==")
    sap = task_service.create_task(
        {**chuan, "title": f"{DAU}hom nay",
         "due_at": datetime.now(timezone.utc) + timedelta(minutes=5)})
    tre = task_service.create_task(
        {**chuan, "title": f"{DAU}tre han",
         "due_at": datetime.now(timezone.utc) - timedelta(hours=3)})
    hom_nay_s1 = [t["id"] for t in task_service.list_today(s1)]
    ok("việc hôm nay CỦA s1 có cả việc sắp đến hạn lẫn việc trễ",
       sap["id"] in hom_nay_s1 and tre["id"] in hom_nay_s1)
    ok("s2 không thấy việc của s1",
       sap["id"] not in [t["id"] for t in task_service.list_today(s2)])
    qua_han = [t["id"] for t in task_service.list_overdue()]
    ok("việc trễ nằm trong danh sách quá hạn",
       tre["id"] in qua_han and sap["id"] not in qua_han)
    so_moi = task_service.quet_qua_han()
    ok("quét quá hạn đánh dấu >= 1 việc", so_moi >= 1, f"được {so_moi}")
    with pool.connection() as conn:
        row = conn.execute(
            "select escalated_at from crm.tasks where id = %s", (tre["id"],)
        ).fetchone()
        n_audit = conn.execute(
            "select count(*) as n from crm.audit_logs "
            "where action = 'task_escalated' and object_id = %s", (tre["id"],),
        ).fetchone()["n"]
    ok("escalated_at được ghi + audit báo quản lý",
       row["escalated_at"] is not None and n_audit == 1)
    ok("quét lần 2 không đánh dấu lại", task_service.quet_qua_han() == 0)
    tre_b = task_service.reschedule_task(tre["id"], mai(), reason="cho làm lại")
    ok("dời lịch xoá dấu leo thang", tre_b["escalated_at"] is None)

    print("== 6. Tầng API (TASK-001…009) ==")
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={
        "username": "admin", "password": settings.admin_bootstrap_password,
    })
    token = r.json()["data"]["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    admin_id = int(r.json()["data"]["user"]["id"])

    r = client.get("/api/v1/tasks")
    ok("không token -> 401", r.status_code == 401)
    r = client.post("/api/v1/tasks", headers=h, json={
        "title": f"{DAU}api", "task_type": "cham_soc", "assigned_to": admin_id,
        "due_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        "customer_id": kh,
    })
    ok("POST /tasks 201", r.status_code == 201, r.text[:200])
    t_api = r.json()["data"]
    ok("created_by = người gọi API", t_api["created_by"] == admin_id)

    r = client.get("/api/v1/tasks/today", headers=h)
    ok("GET /tasks/today không bị /{id} nuốt",
       r.status_code == 200
       and t_api["id"] in [x["id"] for x in r.json()["data"]["items"]])
    r = client.get("/api/v1/tasks/overdue", headers=h)
    ok("GET /tasks/overdue 200", r.status_code == 200)
    r = client.post(f"/api/v1/tasks/{t_api['id']}/complete", headers=h,
                    json={"result": ""})
    ok("API complete thiếu kết quả -> 422 MISSING_REQUIRED_DATA",
       r.status_code == 422
       and r.json()["error_code"] == "MISSING_REQUIRED_DATA", r.text[:200])
    r = client.post(f"/api/v1/tasks/{t_api['id']}/complete", headers=h,
                    json={"result": "đã chăm, khách ổn"})
    ok("API complete đủ kết quả -> done", r.json()["data"]["status"] == "done")
    r = client.get("/api/v1/tasks", headers=h,
                   params={"assigned_to": s1, "status": "open"})
    ten_thay = [x["id"] for x in r.json()["data"]["items"]]
    ok("TASK-001 lọc assigned_to + status", sap["id"] in ten_thay
       and t_api["id"] not in ten_thay)

    print("== 7. Màn /crm/cong-viec ==")
    web = TestClient(app)
    web.cookies.set("access_token", token)
    r = web.get("/crm/cong-viec")
    ok("màn công việc 200, mặc định 'Việc của tôi'",
       r.status_code == 200 and "Việc của tôi" in r.text)
    r = web.get("/crm/cong-viec", params={"pham_vi": "tatca"})
    ok("?pham_vi=tatca -> 'Cả đội', thấy việc của s1",
       r.status_code == 200 and "Cả đội" in r.text and f"{DAU}hom nay" in r.text)

    with pool.connection() as conn:
        don_dep(conn)
        con = conn.execute(
            f"select count(*) as n from crm.tasks where title like '{DAU}%'"
        ).fetchone()["n"]
    ok("dọn sạch dữ liệu test", con == 0)

    print(f"\nKẾT QUẢ: {PASS} PASS / {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
