"""Kiểm thử B6 — sản phẩm & liệu trình + rule engine (FR-060…062), tự dọn sạch.

Cốt lõi nghiệm thu (THU-TU-TRIEN-KHAI-CRM.md): khách có BỆNH NỀN nằm trong
điều kiện loại trừ thì liệu trình đó KHÔNG hiện ra.

Chạy:  python scripts/thu_b6.py
Cần:   DB chạy + seed_auth + seed_danh_muc (symptoms).
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient      # noqa: E402

from app.core.config import settings           # noqa: E402
from app.core.errors import ApiError           # noqa: E402
from app.core.security import hash_password    # noqa: E402
from app.db.client import get_pg_pool          # noqa: E402
from app.main import app                       # noqa: E402
from app.services import (                     # noqa: E402
    consult_service, product_service, treatment_service,
)

DAU = "__b6test__"
MK = "B6-test-1234"
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
    # thứ tự: khách (kéo theo đề xuất/liệu trình) -> mẫu (kéo items/rules) -> SP -> user
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.treatment_templates where template_code like '{DAU}%'")
    conn.execute(f"delete from crm.products where name like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)

        def tao_khach(ten: str) -> int:
            return conn.execute(
                "insert into crm.customers (full_name) values (%s) returning id",
                (f"{DAU}{ten}",),
            ).fetchone()["id"]

        kh_sach, kh_nen, kh_do = tao_khach("Sach"), tao_khach("BenhNen"), tao_khach("Do")
        trieu_chung = {r["code"]: r["id"] for r in conn.execute(
            "select id, code from crm.symptoms"
        ).fetchall()}
        role_sale = conn.execute(
            "select id from crm.roles where name = 'Sale'"
        ).fetchone()["id"]
        admin_id = conn.execute(
            "select id from crm.users where username = 'admin'"
        ).fetchone()["id"]
        conn.execute(
            "insert into crm.users (name, email, username, password_hash, status, role_id) "
            "values (%s, %s, %s, %s, 'active', %s)",
            (f"{DAU}sale", f"{DAU}sale@x.com", f"{DAU}sale",
             hash_password(MK), role_sale),
        )

    print("== 1. FR-060 — sản phẩm: versioning giá + duyệt nội dung ==")
    sp1 = product_service.create_product(
        {"name": f"{DAU}Men vi sinh", "product_code": f"{DAU}SP1",
         "price": 350000, "usage_text": "ngày 2 gói"})
    ok("tạo SP -> approval draft + có phiên bản 1",
       sp1["approval_status"] == "draft")
    phai_loi("trùng mã SP -> chặn", "VALIDATION_ERROR",
             product_service.create_product,
             {"name": f"{DAU}Khac", "product_code": f"{DAU}SP1"})
    sp1b = product_service.update_product(sp1["id"], {"price": 390000})
    from app.db.repositories import catalog_repo
    pb = catalog_repo.list_product_versions(sp1["id"])
    ok("đổi giá -> phiên bản MỚI, bản cũ đóng hiệu lực",
       float(sp1b["price"]) == 390000 and len(pb) == 2
       and float(pb[0]["price"]) == 390000 and pb[1]["effective_to"] is not None)
    product_service.add_version(sp1["id"], {"usage_text": "ngày 3 gói sau ăn"})
    ok("phiên bản nội dung mới -> approval về pending",
       catalog_repo.get_product(sp1["id"])["approval_status"] == "pending")
    sp1c = product_service.approve(sp1["id"])
    ok("duyệt nội dung -> approved", sp1c["approval_status"] == "approved")
    sp2 = product_service.create_product({"name": f"{DAU}Thao duoc X", "price": 250000})
    product_service.set_status(sp2["id"], "inactive")
    ok("khoá SP -> inactive (không có delete)",
       catalog_repo.get_product(sp2["id"])["status"] == "inactive")

    print("== 2. FR-061 — mẫu liệu trình + luật trong DB ==")
    t1 = treatment_service.create_template(
        {"template_code": f"{DAU}LT-DAY", "name": f"{DAU}Da day co ban",
         "problem_group": "da_day", "base_price": 1200000,
         "duration_days": 30, "status": "active"})
    t2 = treatment_service.create_template(
        {"template_code": f"{DAU}LT-RUOT", "name": f"{DAU}Dai trang",
         "problem_group": "dai_trang", "base_price": 990000,
         "duration_days": 25, "status": "active"})
    t3 = treatment_service.create_template(
        {"template_code": f"{DAU}LT-NHAP", "name": f"{DAU}Ban nhap",
         "status": "draft"})
    treatment_service.add_item(t1["id"], {"product_id": sp1["id"], "quantity": 2})
    phai_loi("thêm SP đang khoá vào mẫu -> chặn", "CONFLICT",
             treatment_service.add_item, t1["id"],
             {"product_id": sp2["id"], "quantity": 1})
    phai_loi("rule_type lạ -> chặn", "VALIDATION_ERROR",
             treatment_service.add_rule, t1["id"],
             {"rule_type": "bay", "condition": {"type": "screening", "code": "x"},
              "action": {"message": "m"}})
    phai_loi("condition thiếu type -> chặn", "VALIDATION_ERROR",
             treatment_service.add_rule, t1["id"],
             {"rule_type": "exclusion", "condition": {"code": "benh_nen"},
              "action": {"message": "m"}})
    phai_loi("action thiếu message -> chặn", "VALIDATION_ERROR",
             treatment_service.add_rule, t1["id"],
             {"rule_type": "exclusion",
              "condition": {"type": "screening", "code": "benh_nen"},
              "action": {}})
    treatment_service.add_rule(t1["id"], {
        "rule_type": "exclusion",
        "condition": {"type": "screening", "code": "benh_nen"},
        "action": {"message": "Không dùng cho khách có bệnh nền"}})
    treatment_service.add_rule(t1["id"], {
        "rule_type": "suitable",
        "condition": {"type": "symptom_group", "group": "dạ dày"},
        "action": {"message": "Phù hợp triệu chứng dạ dày"}})
    treatment_service.add_rule(t2["id"], {
        "rule_type": "suitable",
        "condition": {"type": "symptom", "code": "tieu_chay", "min_severity": 3},
        "action": {"message": "Tiêu chảy mức >=3"}})
    treatment_service.add_rule(t2["id"], {
        "rule_type": "warning",
        "condition": {"type": "safety_flag", "flag": "yellow"},
        "action": {"message": "Khách thận trọng — cần chuyên môn xem"}})
    ok("nạp 4 luật vào DB", len(catalog_repo.list_rules(t1["id"])) == 2)

    print("== 3. FR-062 — rule engine đề xuất ==")
    phai_loi("khách CHƯA khai triệu chứng -> chặn đề xuất", "MISSING_REQUIRED_DATA",
             treatment_service.recommend, kh_sach)
    consult_service.save_symptom(kh_sach, symptom_id=trieu_chung["o_chua"],
                                 data={"severity": 7, "frequency": "daily"})
    kq = treatment_service.recommend(kh_sach)
    hien = {x["template_id"] for x in kq["items"]}
    loai = {x["template_id"]: x["loai_vi"] for x in kq["loai_tru"]}
    ok("khách dạ dày: mẫu Dạ dày HIỆN kèm lý do",
       t1["id"] in hien and any("Phù hợp" in r for x in kq["items"]
                                if x["template_id"] == t1["id"] for r in x["ly_do"]))
    ok("mẫu Đại tràng KHÔNG hiện (không khớp suitable)",
       t2["id"] in loai and "không khớp" in loai[t2["id"]])
    ok("mẫu draft không xuất hiện đâu cả",
       t3["id"] not in hien and t3["id"] not in loai)
    ok("nhắc thiếu: chưa có phiếu sàng lọc", len(kq["missing_info"]) == 1)

    # --- tiêu chí "Xong khi": bệnh nền nằm trong loại trừ -> mẫu biến mất ---
    consult_service.save_symptom(kh_nen, symptom_id=trieu_chung["dau_thuong_vi"],
                                 data={"severity": 6, "frequency": "often"})
    consult_service.save_symptom(kh_nen, symptom_id=trieu_chung["tieu_chay"],
                                 data={"severity": 5, "frequency": "daily"})
    consult_service.add_screening(kh_nen, screening_type="benh_nen",
                                  value="tiểu đường type 2")
    kq2 = treatment_service.recommend(kh_nen)
    loai2 = {x["template_id"]: x["loai_vi"] for x in kq2["loai_tru"]}
    ok("XONG KHI: khách BỆNH NỀN -> mẫu Dạ dày (loại trừ bệnh nền) KHÔNG hiện",
       t1["id"] in loai2 and loai2[t1["id"]] == "Không dùng cho khách có bệnh nền")
    t2_hien = next((x for x in kq2["items"] if x["template_id"] == t2["id"]), None)
    ok("mẫu Đại tràng hiện KÈM cảnh báo (khách cờ vàng)",
       t2_hien is not None and len(t2_hien["canh_bao"]) == 1
       and len(kq2["canh_bao_chung"]) == 1)

    elig = treatment_service.eligibility_check(t1["id"], kh_nen)
    ok("TREATMENT-009: eligibility mẫu Dạ dày với khách bệnh nền = False",
       elig["eligible"] is False and "bệnh nền" in (elig["loai_vi"] or ""))

    consult_service.add_screening(kh_do, screening_type="non_mau")
    phai_loi("khách CỜ ĐỎ -> đề xuất bị chặn (nối B5)", "FORBIDDEN",
             treatment_service.recommend, kh_do)

    print("== 4. Lưu đề xuất + duyệt + tạo liệu trình ==")
    phai_loi("chọn mẫu ngoài danh sách cho phép -> chặn", "CONFLICT",
             treatment_service.recommend, kh_sach, template_id=t2["id"])
    rec1 = treatment_service.recommend(kh_sach, template_id=t1["id"])
    ok("khách sạch -> đề xuất 'proposed', không cần duyệt",
       rec1["status"] == "proposed" and rec1["needs_approval"] is False)
    ct1 = treatment_service.create_customer_treatment(
        kh_sach, recommendation_id=rec1["id"], start_date=date.today())
    ok("tạo liệu trình từ đề xuất -> planned + items SNAPSHOT + ngày hết dự kiến",
       ct1["status"] == "planned" and len(ct1["items"]) == 1
       and ct1["expected_end_date"] is not None)

    rec2 = treatment_service.recommend(kh_nen, template_id=t2["id"])
    ok("khách cờ vàng -> đề xuất PHẢI chờ chuyên môn duyệt",
       rec2["status"] == "pending_approval" and rec2["needs_approval"] is True)
    phai_loi("tạo liệu trình khi đề xuất CHƯA duyệt -> chặn", "CONFLICT",
             treatment_service.create_customer_treatment, kh_nen,
             recommendation_id=rec2["id"])
    rec2b = treatment_service.approve_recommendation(
        rec2["id"], approve=True, note="đã xem bệnh nền, dùng được",
        actor={"sub": str(admin_id)})
    ok("chuyên môn duyệt -> approved", rec2b["status"] == "approved")
    phai_loi("duyệt lần 2 -> CONFLICT", "CONFLICT",
             treatment_service.approve_recommendation, rec2["id"])
    ct2 = treatment_service.create_customer_treatment(
        kh_nen, recommendation_id=rec2["id"])
    ok("duyệt xong tạo được liệu trình, approved_by lưu lại",
       ct2["approved_by"] is not None)
    phai_loi("tạo liệu trình từ mẫu draft -> chặn", "CONFLICT",
             treatment_service.create_customer_treatment, kh_sach,
             template_id=t3["id"])
    phai_loi("tạo liệu trình cho khách CỜ ĐỎ -> chặn", "FORBIDDEN",
             treatment_service.create_customer_treatment, kh_do,
             template_id=t1["id"])

    print("== 5. Điều chỉnh liệu trình ==")
    phai_loi("điều chỉnh thiếu lý do -> chặn", "MISSING_REQUIRED_DATA",
             treatment_service.adjust_customer_treatment, ct1["id"],
             {"status": "paused"})
    ct1b = treatment_service.adjust_customer_treatment(
        ct1["id"], {"status": "active"}, reason="khách bắt đầu dùng")
    ok("điều chỉnh kèm lý do -> đổi trạng thái", ct1b["status"] == "active")
    treatment_service.adjust_customer_treatment(
        ct1["id"], {"status": "completed"}, reason="xong liệu trình")
    phai_loi("liệu trình đã kết thúc -> không điều chỉnh nữa", "CONFLICT",
             treatment_service.adjust_customer_treatment, ct1["id"],
             {"status": "active"}, reason="thử lại")

    print("== 6. Tầng API + phân quyền ==")
    client = TestClient(app)

    def dang_nhap(u: str, p: str) -> dict:
        r = client.post("/api/v1/auth/login", json={"username": u, "password": p})
        assert r.status_code == 200, r.text[:200]
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    ha = dang_nhap("admin", settings.admin_bootstrap_password)
    hs = dang_nhap(f"{DAU}sale", MK)

    r = client.post("/api/v1/products", headers=hs,
                    json={"name": f"{DAU}Sale tu tao"})
    ok("Sale KHÔNG sửa được danh mục SP (403)", r.status_code == 403)
    r = client.post("/api/v1/products", headers=ha,
                    json={"name": f"{DAU}SP qua API", "price": 100000})
    ok("admin tạo SP qua API -> 201", r.status_code == 201, r.text[:200])
    sp_api = r.json()["data"]
    r = client.put(f"/api/v1/products/{sp_api['id']}", headers=ha,
                   json={"price": 120000})
    r = client.get(f"/api/v1/products/{sp_api['id']}", headers=hs)
    ok("PRODUCT-002 kèm versions (đổi giá ra 2 bản)",
       len(r.json()["data"]["versions"]) == 2)
    r = client.get(f"/api/v1/products/{sp_api['id']}/history", headers=hs)
    ok("PRODUCT-008 history có vết audit",
       r.status_code == 200 and len(r.json()["data"]["audit"]) >= 2)

    r = client.post(f"/api/v1/customers/{kh_sach}/treatment-recommendations",
                    headers=hs, json={})
    ok("Sale chạy engine xem danh sách -> 201 + có mẫu Dạ dày",
       r.status_code == 201
       and t1["id"] in [x["template_id"] for x in r.json()["data"]["items"]],
       r.text[:200])
    r = client.post(f"/api/v1/treatment-recommendations/{rec1['id']}/approve",
                    headers=hs, json={})
    ok("Sale KHÔNG duyệt được đề xuất (403)", r.status_code == 403)
    r = client.post(f"/api/v1/treatment-templates/{t1['id']}/eligibility-check",
                    headers=hs, json={"customer_id": kh_sach})
    ok("TREATMENT-009 qua API", r.status_code == 200
       and r.json()["data"]["eligible"] is True)
    r = client.get(f"/api/v1/customer-treatments/{ct2['id']}", headers=hs)
    ok("TREATMENT-013 chi tiết liệu trình khách",
       r.status_code == 200 and r.json()["data"]["customer_id"] == kh_nen)
    r = client.get(f"/api/v1/treatment-templates/{t1['id']}", headers=hs)
    ok("TREATMENT-002 kèm items + rules",
       len(r.json()["data"]["items"]) == 1 and len(r.json()["data"]["rules"]) == 2)

    with pool.connection() as conn:
        don_dep(conn)
        con = conn.execute(
            f"select count(*) as n from crm.products where name like '{DAU}%'"
        ).fetchone()["n"]
    ok("dọn sạch dữ liệu test", con == 0)

    print(f"\nKẾT QUẢ: {PASS} PASS / {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
