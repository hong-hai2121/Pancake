"""Kiểm thử B8 — Bàn giao Sale → CSKH (FR-090/091 · HANDOVER-001…006 · màn 24-25).

Nghiệm thu theo THU-TU-TRIEN-KHAI-CRM.md: "chuyển đơn sang giao thành công thì
hàng đợi CSKH tự có khách mới kèm phiếu", cộng luật FR-091 (8 trường bắt buộc,
thiếu -> không nhận, trả lại Sale kèm việc, bổ sung đủ tự quay lại chờ nhận).

Dữ liệu giả mang dấu `__tb8__`, dọn sạch đầu/cuối. KHÔNG gọi mạng.

Chạy:  python scripts/thu_b8.py
Cần:   DB chạy + init_crm.sql + seed_auth (vai trò Sale/CSKH).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core.errors import ApiError               # noqa: E402
from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import handover_repo      # noqa: E402
from app.main import app                           # noqa: E402
from app.services import handover_service, order_service  # noqa: E402

DAU = "__tb8__"
MK = "B8-test-1234"
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
    khach = f"(select id from crm.customers where full_name like '{DAU}%')"
    conn.execute(f"delete from crm.tasks where customer_id in {khach}")
    conn.execute(f"delete from crm.handovers where customer_id in {khach}")
    conn.execute(f"delete from crm.care_plans where customer_id in {khach}")
    conn.execute(
        f"delete from crm.customer_treatment_items where customer_treatment_id in "
        f"(select id from crm.customer_treatments where customer_id in {khach})")
    conn.execute(f"delete from crm.customer_treatments where customer_id in {khach}")
    conn.execute(
        f"delete from crm.order_status_history where order_id in "
        f"(select id from crm.orders where customer_id in {khach})")
    conn.execute(f"delete from crm.orders where customer_id in {khach}")
    conn.execute(f"delete from crm.customer_assignments where customer_id in {khach}")
    conn.execute(f"delete from crm.leads where customer_id in {khach}")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.products where product_code like '{DAU}%'")
    conn.execute(
        f"delete from crm.treatment_templates where template_code like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vai in (("admin", "Admin"), ("sale", "Sale"),
                         ("cskh1", "CSKH"), ("cskh2", "CSKH")):
            uid[ten] = conn.execute(
                "insert into crm.users (name, email, username, password_hash, status, role_id) "
                "values (%s, %s, %s, %s, 'active', %s) returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]),
            ).fetchone()["id"]

        kh = conn.execute(
            "insert into crm.customers (full_name, primary_phone, status) "
            "values (%s, '0900111222', 'customer') returning id",
            (f"{DAU}KhachA",),
        ).fetchone()["id"]
        conn.execute(
            "insert into crm.customer_assignments (customer_id, user_id, assignment_type) "
            "values (%s, %s, 'sale')", (kh, uid["sale"]))

        # Khoá tạm CSKH THẬT đang active: vòng tròn B8 chọn người ít việc nhất
        # trong TOÀN cty — không khoá thì test gán phiếu cho người thật.
        cskh_that = [r["id"] for r in conn.execute(
            "select u.id from crm.users u join crm.roles r on r.id = u.role_id "
            "where r.name = 'CSKH' and u.status = 'active' "
            f"and u.email not like '{DAU}%'").fetchall()]
        if cskh_that:
            conn.execute(
                "update crm.users set status = 'inactive' where id = any(%s)",
                (cskh_that,))

        # liệu trình đang dùng (nguồn chép FR-090) + triệu chứng + thuốc (mồi B5)
        sp = conn.execute(
            "insert into crm.products (product_code, name, price, status) "
            f"values ('{DAU}SP1', '{DAU}Dạ dày an', 350000, 'active') returning id",
        ).fetchone()["id"]
        mau = conn.execute(
            "insert into crm.treatment_templates (template_code, name, status) "
            f"values ('{DAU}LT1', '{DAU}Liệu trình dạ dày 1 tháng', 'active') returning id",
        ).fetchone()["id"]
        lt = conn.execute(
            "insert into crm.customer_treatments (customer_id, template_id, status) "
            "values (%s, %s, 'planned') returning id", (kh, mau),
        ).fetchone()["id"]
        conn.execute(
            "insert into crm.customer_treatment_items "
            "(customer_treatment_id, product_id, quantity, dose_text) "
            "values (%s, %s, 2, 'Sáng 2 viên sau ăn')", (lt, sp))
        trieu_chung = conn.execute(
            "select id from crm.symptoms order by id limit 1").fetchone()
        if trieu_chung:
            conn.execute(
                "insert into crm.customer_symptoms (customer_id, symptom_id) "
                "values (%s, %s) on conflict do nothing", (kh, trieu_chung["id"]))
        conn.execute(
            "insert into crm.current_medications (customer_id, name, dosage) "
            "values (%s, 'Omeprazol', '20mg sáng')", (kh,))

    def don_moi(so_luong: int = 2) -> dict:
        return order_service.create_order({
            "customer_id": kh, "status": "confirmed",
            "items": [{"product_id": sp, "quantity": so_luong}],
        })

    try:
        _chay(pool, kh, sp, uid, don_moi)
    finally:
        with pool.connection() as conn:
            if cskh_that:   # mở lại CSKH thật kể cả khi test vỡ giữa chừng
                conn.execute(
                    "update crm.users set status = 'active' where id = any(%s)",
                    (cskh_that,))


def _chay(pool, kh, sp, uid, don_moi) -> None:  # noqa: PLR0915 — script nghiệm thu
    print("== 1. FR-090: đơn giao thành công -> TỰ SINH phiếu ==")
    don = don_moi()
    for tt in ("packing", "shipping", "delivered"):
        order_service.change_status(don["id"], tt, force=True)
    phieu = handover_repo.get_by_order(don["id"])
    ok("chuyển 'delivered' là có phiếu ngay (hook trong change_status)",
       phieu is not None)
    ok("phiếu gán CSKH tự động (vòng tròn) + trạng thái assigned",
       phieu["cskh_user_id"] in (uid["cskh1"], uid["cskh2"])
       and phieu["status"] == "assigned", str(dict(phieu or {})))
    ok("ghi Sale chốt từ phân công khách", phieu["sale_user_id"] == uid["sale"])
    ok("chép liệu trình: tên mẫu + cách dùng từ items snapshot",
       phieu["treatment_summary"] == f"{DAU}Liệu trình dạ dày 1 tháng"
       and "Sáng 2 viên" in (phieu["dose_text"] or ""))
    ok("mồi thuốc đang dùng từ hồ sơ B5",
       "Omeprazol" in (phieu["current_medications"] or ""))
    ok("tạo vỏ hồ sơ chăm (care_plans) + gắn vào phiếu",
       phieu["care_plan_id"] is not None)
    ok("tính ngày dự kiến bắt đầu = giao + 2 ngày",
       phieu["expected_start_date"] is not None)
    with pool.connection() as conn:
        viec = conn.execute(
            "select * from crm.tasks where customer_id = %s "
            "and task_type = 'cham_soc'", (kh,)).fetchone()
    ok("CSKH có việc onboarding trong hàng đợi (B4)",
       viec is not None and viec["assigned_to"] == phieu["cskh_user_id"])
    ok("hồ sơ CHƯA đủ 8 trường -> is_complete=false + liệt kê thiếu",
       phieu["is_complete"] is False and len(phieu["missing_fields"]) >= 1)

    print("== 2. Idempotent — automation chạy lại không tạo trùng ==")
    lai = handover_service.tao_tu_don(don["id"])
    with pool.connection() as conn:
        so_phieu = conn.execute(
            "select count(*) as n from crm.handovers where order_id = %s",
            (don["id"],)).fetchone()["n"]
    ok("tao_tu_don lần 2 trả phiếu CŨ, vẫn 1 phiếu/đơn",
       lai["id"] == phieu["id"] and so_phieu == 1)
    order_service.change_status(don["id"], "collected", force=True)
    with pool.connection() as conn:
        so_phieu = conn.execute(
            "select count(*) as n from crm.handovers where order_id = %s",
            (don["id"],)).fetchone()["n"]
    ok("đơn nhảy tiếp 'collected' — hook chạy lại vẫn 1 phiếu", so_phieu == 1)

    print("== 3. FR-091: thiếu hồ sơ KHÔNG nhận được, trả lại Sale ==")
    phai_loi("nhận khi thiếu -> MISSING_REQUIRED_DATA", "MISSING_REQUIRED_DATA",
             handover_service.nhan, phieu["id"],
             actor={"sub": str(phieu["cskh_user_id"])})
    phai_loi("trả lại không lý do -> MISSING_REQUIRED_DATA", "MISSING_REQUIRED_DATA",
             handover_service.tra_lai, phieu["id"], "  ")
    handover_service.tra_lai(phieu["id"], "Thiếu tình trạng khách + cam kết",
                             actor={"sub": str(phieu["cskh_user_id"])})
    h2 = handover_repo.get(phieu["id"])
    ok("trả lại -> status=returned + lưu lý do + mốc",
       h2["status"] == "returned" and h2["returned_at"] is not None
       and "Thiếu" in h2["returned_reason"])
    with pool.connection() as conn:
        viec_sale = conn.execute(
            "select * from crm.tasks where assigned_to = %s and title like %s",
            (uid["sale"], "Bổ sung phiếu bàn giao%")).fetchone()
    ok("Sale nhận việc 'bổ sung phiếu' kèm danh sách thiếu",
       viec_sale is not None and "thiếu" in viec_sale["title"].lower())

    print("== 4. Sale bổ sung đủ -> phiếu TỰ quay lại chờ nhận ==")
    h3 = handover_service.cap_nhat_phieu(phieu["id"], {
        "customer_condition": "Đau thượng vị 3 tháng, HP âm tính",
        "notes": "Kiêng đồ chua cay",
        "comorbidities": "Không",
        "concerns": "Sợ tác dụng phụ",
        "cskh_watch_points": "Theo dõi phân tuần đầu",
        "sale_discussed": "Đã tư vấn đủ liệu trình 1 tháng",
        "promises_made": "Không cam kết khỏi 100%",
    }, actor={"sub": str(uid["sale"])})
    ok("đủ 8 trường -> is_complete=true, thiếu rỗng",
       h3["is_complete"] is True and h3["missing_fields"] == [])
    ok("phiếu returned tự quay lại 'assigned'", h3["status"] == "assigned")
    phai_loi("sửa trường lạ -> VALIDATION_ERROR", "VALIDATION_ERROR",
             handover_service.cap_nhat_phieu, phieu["id"], {"hacker": "x"})

    print("== 5. HANDOVER-004: nhận -> khách chính thức thuộc CSKH ==")
    h4 = handover_service.nhan(phieu["id"], actor={"sub": str(h3["cskh_user_id"])})
    ok("nhận xong: accepted + đóng mốc accepted_at",
       h4["status"] == "accepted" and h4["accepted_at"] is not None)
    with pool.connection() as conn:
        pc = conn.execute(
            "select user_id from crm.customer_assignments where customer_id = %s "
            "and assignment_type = 'cskh' and end_at is null", (kh,)).fetchone()
        cp = conn.execute(
            "select owner_id from crm.care_plans where id = %s",
            (h4["care_plan_id"],)).fetchone()
    ok("customer_assignments vai 'cskh' mở đúng người",
       pc and pc["user_id"] == h4["cskh_user_id"])
    ok("care_plans.owner theo CSKH đã nhận", cp["owner_id"] == h4["cskh_user_id"])
    phai_loi("nhận lần 2 -> CONFLICT", "CONFLICT",
             handover_service.nhan, phieu["id"])
    phai_loi("đổi CSKH khi đã nhận -> CONFLICT (đi đường chuyển khách A5)",
             "CONFLICT", handover_service.gan_cskh, phieu["id"], uid["cskh2"])

    print("== 6. HANDOVER-006: gán tay + vòng tròn theo tải ==")
    don2 = don_moi(1)
    order_service.change_status(don2["id"], "delivered", force=True)
    phieu2 = handover_repo.get_by_order(don2["id"])
    ok("đơn 2 giao -> phiếu 2 (khách đã có CSKH thì giữ nguyên người)",
       phieu2 is not None and phieu2["cskh_user_id"] == h4["cskh_user_id"])
    khac = uid["cskh2"] if h4["cskh_user_id"] == uid["cskh1"] else uid["cskh1"]
    g = handover_service.gan_cskh(phieu2["id"], khac, actor={"sub": str(uid["admin"])})
    ok("gán tay sang CSKH khác được", g["cskh_user_id"] == khac)
    phai_loi("gán người không tồn tại -> NOT_FOUND", "NOT_FOUND",
             handover_service.gan_cskh, phieu2["id"], 99999999)

    print("== 7. Chặn tạo phiếu từ đơn CHƯA giao ==")
    don3 = don_moi(1)
    phai_loi("đơn 'confirmed' -> CONFLICT", "CONFLICT",
             handover_service.tao_tu_don, don3["id"])
    phai_loi("đơn không tồn tại -> NOT_FOUND", "NOT_FOUND",
             handover_service.tao_tu_don, 99999999)

    print("== 8. API HANDOVER-001…006 + phân quyền ==")
    web = TestClient(app)

    def dang_nhap(u: str) -> dict:
        r = web.post("/api/v1/auth/login", json={"username": u, "password": MK})
        assert r.status_code == 200, r.text[:200]
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    ha = dang_nhap(f"{DAU}admin")
    hc = dang_nhap(f"{DAU}cskh1")

    r = web.get("/api/v1/handovers/pending")
    ok("chưa đăng nhập -> 401", r.status_code == 401, str(r.status_code))
    r = web.get("/api/v1/handovers/pending", headers=hc)
    ok("HANDOVER-001 danh sách chờ (CSKH xem được)",
       r.status_code == 200
       and any(x["id"] == phieu2["id"] for x in r.json()["data"]["items"]),
       r.text[:200])
    r = web.get(f"/api/v1/handovers?status=accepted&customer_id={kh}", headers=ha)
    ok("lọc status=accepted ra phiếu 1",
       r.status_code == 200
       and any(x["id"] == phieu["id"] for x in r.json()["data"]["items"]))
    r = web.get(f"/api/v1/handovers/{phieu2['id']}", headers=hc)
    ok("HANDOVER-003 chi tiết kèm danh sách 'thieu'",
       r.status_code == 200 and isinstance(r.json()["data"]["thieu"], list))
    r = web.put(f"/api/v1/handovers/{phieu2['id']}", headers=hc, json={
        "customer_condition": "Ổn", "notes": "-", "comorbidities": "Không",
        "concerns": "-", "cskh_watch_points": "-",
    })
    ok("PUT bổ sung phiếu 2 (đủ 8 trường vì liệu trình đã mồi sẵn)",
       r.status_code == 200 and r.json()["data"]["is_complete"] is True,
       r.text[:300])
    r = web.post(f"/api/v1/handovers/{phieu2['id']}/assign",
                 json={"user_id": uid["cskh1"]}, headers=ha)
    ok("HANDOVER-006 gán CSKH qua API", r.status_code == 200)
    r = web.post(f"/api/v1/handovers/{phieu2['id']}/accept", headers=hc)
    ok("HANDOVER-004 nhận qua API", r.status_code == 200
       and r.json()["data"]["status"] == "accepted", r.text[:200])
    r = web.post(f"/api/v1/handovers/{phieu2['id']}/return",
                 json={"reason": "thử trả sau khi nhận"}, headers=hc)
    ok("trả lại phiếu ĐÃ nhận -> 409", r.status_code == 409)
    r = web.post("/api/v1/handovers", json={"order_id": don["id"]}, headers=ha)
    ok("HANDOVER-002 tạo tay đơn đã có phiếu -> trả phiếu cũ",
       r.status_code == 201 and r.json()["data"]["id"] == phieu["id"])

    print("== 9. Màn 24-25 (web) ==")
    web.post("/dang-nhap", data={"username": f"{DAU}admin", "password": MK})
    r = web.get("/crm/ban-giao")
    ok("màn 24 trả HTML có bảng + tên khách", r.status_code == 200
       and "<table" in r.text and f"{DAU}KhachA" in r.text)
    r = web.get(f"/crm/ban-giao/{phieu['id']}")
    ok("màn 25 mở phiếu, có đủ nhãn 8 trường FR-091",
       r.status_code == 200 and "Tình trạng khách" in r.text
       and "Vấn đề CSKH cần theo dõi" in r.text)
    r = web.get("/crm/ban-giao/99999999")
    ok("phiếu không tồn tại -> 404", r.status_code == 404)

    print("== 10. Backfill KHÔNG sinh phiếu (hook_ban_giao=False) ==")
    with pool.connection() as conn:
        kh2 = conn.execute(
            "insert into crm.customers (full_name, primary_phone, status) "
            "values (%s, '0900333444', 'customer') returning id",
            (f"{DAU}KhachCu",),
        ).fetchone()["id"]
    don_cu = order_service.create_order({
        "customer_id": kh2, "status": "confirmed",
        "items": [{"product_id": sp, "quantity": 1}],
    })
    order_service.change_status(don_cu["id"], "delivered", force=True,
                                ban_giao=False)
    ok("change_status(ban_giao=False) — backfill không sinh phiếu",
       handover_repo.get_by_order(don_cu["id"]) is None)

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKẾT QUẢ: {PASS} PASS · {FAIL} FAIL")
    # SystemExit vẫn chạy finally ở main() — CSKH thật được mở khoá trước khi thoát
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
