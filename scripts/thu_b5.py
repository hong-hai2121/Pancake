"""Kiểm thử B5 — hồ sơ tư vấn + sàng lọc an toàn (FR-050…053), tự dọn sạch.

Nửa đầu kiểm TẦNG LUẬT (consult_service), nửa sau kiểm TẦNG API + phân quyền
(health.view cho hồ sơ, content.approve cho kết luận ca).

Cốt lõi nghiệm thu B5 (THU-TU-TRIEN-KHAI-CRM.md): nhập "phân đen" -> hồ sơ
gắn cảnh báo ĐỎ và KHÔNG cho đề xuất liệu trình.

Chạy:  python scripts/thu_b5.py
Cần:   DB chạy + seed_auth + seed_danh_muc (symptoms) + có user Người chuyên môn.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient      # noqa: E402

from app.core.config import settings           # noqa: E402
from app.core.errors import ApiError           # noqa: E402
from app.core.security import hash_password    # noqa: E402
from app.db.client import get_pg_pool          # noqa: E402
from app.main import app                       # noqa: E402
from app.services import consult_service       # noqa: E402

DAU = "__b5test__"
MK = "B5-test-1234"
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
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
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

        kh_a, kh_b, kh_c = tao_khach("A do"), tao_khach("B vang"), tao_khach("C sach")
        trieu_chung = {r["code"]: r["id"] for r in conn.execute(
            "select id, code from crm.symptoms"
        ).fetchall()}
        assert trieu_chung, "Chưa seed symptoms — chạy scripts/seed_danh_muc.py"

        vai = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles"
        ).fetchall()}

        def tao_user(ten: str, role: str) -> int:
            return conn.execute(
                "insert into crm.users (name, email, username, password_hash, "
                "status, role_id) values (%s, %s, %s, %s, 'active', %s) returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), vai[role]),
            ).fetchone()["id"]

        tao_user("sale", "Sale")            # có health.view, KHÔNG content.approve
        tao_user("mkt", "Marketing")        # KHÔNG có health.view

    print("== 1. FR-050 — phiếu triệu chứng: cấu trúc trước, ghi chú sau ==")
    phai_loi("chỉ ghi chú tự do -> chặn", "MISSING_REQUIRED_DATA",
             consult_service.save_symptom, kh_a,
             symptom_id=trieu_chung["o_chua"], data={"note": "khách kể dài dòng"})
    ts1 = consult_service.save_symptom(
        kh_a, symptom_id=trieu_chung["o_chua"],
        data={"severity": 7, "frequency": "daily", "meal_relation": "sau_an",
              "is_primary": True, "note": "ợ nhiều sau ăn no"})
    ok("khai đủ cấu trúc -> lưu", ts1["severity"] == 7 and ts1["is_primary"])
    ts1b = consult_service.save_symptom(
        kh_a, symptom_id=trieu_chung["o_chua"],
        data={"severity": 4, "frequency": "often"})
    ok("khai lại cùng triệu chứng -> CẬP NHẬT không nhân dòng",
       ts1b["id"] == ts1["id"] and ts1b["severity"] == 4)
    ok("danh mục triệu chứng đã seed >= 19", len(trieu_chung) >= 19)

    print("== 2. FR-051/052 — khám + thuốc ==")
    kham = consult_service.add_examination(
        kh_a, {"exam_type": "noi_soi", "conclusion": "viêm hang vị"})
    ok("lưu kết quả khám nội soi", kham["exam_type"] == "noi_soi")
    thuoc = consult_service.add_medication(
        kh_b, {"name": "PPI phối hợp", "dosage": "1 viên/ngày"})
    ok("thuốc không phản ứng -> KHÔNG mở ca", thuoc["escalation_id"] is None)
    thuoc2 = consult_service.add_medication(
        kh_b, {"name": "Thuốc nam không rõ nguồn", "reaction": "đau bụng dữ dội"})
    ok("thuốc CÓ phản ứng -> tự mở ca chuyên môn (FR-052)",
       thuoc2["escalation_id"] is not None)
    dt = consult_service.add_previous_treatment(
        kh_b, {"name": "kháng sinh diệt HP", "result": "không đỡ"})
    ok("lưu điều trị trước đây", dt["id"] is not None)

    print("== 3. FR-053 — RED FLAG: phân đen -> cờ đỏ + chặn đề xuất + tạo việc ==")
    phai_loi("mục sàng lọc lạ -> chặn", "VALIDATION_ERROR",
             consult_service.add_screening, kh_a, screening_type="boi_toan")
    p1 = consult_service.add_screening(
        kh_a, screening_type="phan_den", value="3 ngày nay phân đen như bã cà phê")
    ok("nhập 'phân đen' -> hồ sơ gắn cảnh báo ĐỎ",
       p1["safety_check"]["safety_flag"] == "red")
    ok("ca chuyển chuyên môn tự mở", p1["safety_check"]["escalation_id"] is not None)
    ca_id = p1["safety_check"]["escalation_id"]
    phai_loi("cờ đỏ -> KHÔNG cho đề xuất liệu trình (chốt B6)", "FORBIDDEN",
             consult_service.kiem_duoc_de_xuat, kh_a)
    with pool.connection() as conn:
        ca = conn.execute(
            "select e.*, t.task_type, t.priority, t.status as task_status "
            "from crm.clinical_escalations e "
            "left join crm.tasks t on t.id = e.task_id where e.id = %s",
            (ca_id,),
        ).fetchone()
    ok("việc duyet_chuyen_mon khẩn được tạo, có người nhận",
       ca["task_type"] == "duyet_chuyen_mon" and ca["priority"] == "urgent"
       and ca["assigned_to"] is not None)
    p2 = consult_service.add_screening(kh_a, screening_type="non_mau")
    ok("red flag thứ 2 -> KHÔNG mở ca trùng (đã có ca chờ)",
       p2["safety_check"]["escalation_id"] is None)

    p3 = consult_service.add_screening(kh_b, screening_type="thai_ky")
    ok("thai kỳ (yellow) -> cờ VÀNG, không chặn đề xuất",
       p3["safety_check"]["safety_flag"] == "yellow")
    try:
        consult_service.kiem_duoc_de_xuat(kh_b)
        ok("cờ vàng vẫn đề xuất được", True)
    except ApiError as e:
        ok("cờ vàng vẫn đề xuất được", False, e.code)

    print("== 4. SAFETY-005 — chuyên môn kết luận, gỡ cờ có dấu vết ==")
    phai_loi("kết luận rỗng -> chặn", "MISSING_REQUIRED_DATA",
             consult_service.resolve_escalation, ca_id, resolution="  ")
    kq = consult_service.resolve_escalation(
        ca_id, resolution="Đã hỏi kỹ: khách uống sắt, phân đen do thuốc — an toàn",
        go_canh_bao=True)
    ok("resolve -> ca đóng + cờ được gỡ",
       kq["status"] == "resolved" and kq["safety_check"]["safety_flag"] is None)
    with pool.connection() as conn:
        task = conn.execute(
            "select status, result from crm.tasks where id = %s", (ca["task_id"],)
        ).fetchone()
        con_phieu = conn.execute(
            "select count(*) as n from crm.safety_screenings "
            "where customer_id = %s and cleared_at is null", (kh_a,),
        ).fetchone()["n"]
        giu_vet = conn.execute(
            "select count(*) as n from crm.safety_screenings where customer_id = %s",
            (kh_a,),
        ).fetchone()["n"]
    ok("task đi kèm được đóng bằng kết luận",
       task["status"] == "done" and "an toàn" in task["result"])
    ok("phiếu sàng lọc GỠ nhưng GIỮ VẾT (không delete)",
       con_phieu == 0 and giu_vet == 2)
    try:
        consult_service.kiem_duoc_de_xuat(kh_a)
        ok("gỡ cờ xong lại đề xuất được", True)
    except ApiError as e:
        ok("gỡ cờ xong lại đề xuất được", False, e.code)
    phai_loi("resolve lần 2 -> CONFLICT", "CONFLICT",
             consult_service.resolve_escalation, ca_id, resolution="lại nữa")

    print("== 5. CONSULT — phiên tư vấn + câu bắt buộc ==")
    phai_loi("mở phiên cho khách ma -> NOT_FOUND", "NOT_FOUND",
             consult_service.create_session, customer_id=999999999)
    phien = consult_service.create_session(customer_id=kh_c, channel="chat")
    ok("mở phiên -> có started_at", phien["started_at"] is not None)
    kq = consult_service.save_answers(phien["id"], [
        {"question_code": "trieu_chung_chinh", "answer_text": "ợ chua, nóng rát"},
        {"question_code": "muc_do", "answer_value": 7},
    ])
    ok("lưu 2 câu -> còn thiếu 5 câu bắt buộc", len(kq["missing_fields"]) == 5)
    phai_loi("hoàn tất khi còn thiếu -> chặn", "MISSING_REQUIRED_DATA",
             consult_service.complete_session, phien["id"])
    consult_service.save_answers(phien["id"], [
        {"question_code": "tan_suat", "answer_text": "hằng ngày"},
        {"question_code": "thoi_gian_mac", "answer_text": "6 tháng"},
        {"question_code": "lien_quan_bua_an", "answer_text": "sau ăn no"},
        {"question_code": "benh_nen", "answer_text": "không"},
        {"question_code": "thuoc_dang_dung", "answer_text": "không"},
    ])
    ok("khai đủ -> hết thiếu", consult_service.missing_fields(phien["id"]) == [])
    xong = consult_service.complete_session(phien["id"])
    ok("hoàn tất -> risk thấp (khách sạch)",
       xong["completed_at"] is not None and xong["risk_level"] == "low")
    phai_loi("khai thêm vào phiên đã đóng -> CONFLICT", "CONFLICT",
             consult_service.save_answers, phien["id"],
             [{"question_code": "muc_do", "answer_value": 5}])

    print("== 6. Tầng API + phân quyền ==")
    client = TestClient(app)

    def dang_nhap(u: str, p: str) -> dict:
        r = client.post("/api/v1/auth/login", json={"username": u, "password": p})
        assert r.status_code == 200, r.text[:200]
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    ha = dang_nhap("admin", settings.admin_bootstrap_password)
    hs = dang_nhap(f"{DAU}sale", MK)
    hm = dang_nhap(f"{DAU}mkt", MK)

    r = client.get("/api/v1/symptoms", headers=hm)
    ok("Marketing không có health.view -> 403", r.status_code == 403)
    r = client.get("/api/v1/symptoms", headers=hs)
    ok("Sale xem danh mục triệu chứng -> 200",
       r.status_code == 200 and len(r.json()["data"]["items"]) >= 19)

    r = client.post(f"/api/v1/customers/{kh_c}/safety-screenings", headers=hs,
                    json={"screening_type": "sut_can", "value": "sút 4kg/1 tháng"})
    ok("Sale nhập red flag qua API -> 201 + cờ đỏ", r.status_code == 201
       and r.json()["data"]["safety_check"]["safety_flag"] == "red", r.text[:200])
    r = client.get("/api/v1/clinical-escalations", headers=hs)
    ca_api = [x for x in r.json()["data"]["items"] if x["customer_id"] == kh_c]
    ok("SAFETY-004 danh sách ca chờ có ca vừa mở", len(ca_api) == 1)
    r = client.post(f"/api/v1/clinical-escalations/{ca_api[0]['id']}/resolve",
                    headers=hs, json={"resolution": "toi tu xu"})
    ok("Sale thiếu content.approve -> KHÔNG kết luận được ca (403)",
       r.status_code == 403)
    r = client.post(f"/api/v1/clinical-escalations/{ca_api[0]['id']}/resolve",
                    headers=ha, json={"resolution": "sút cân do ăn kiêng chủ ý",
                                      "go_canh_bao": True})
    ok("admin (content.approve) kết luận -> 200 + gỡ cờ",
       r.status_code == 200
       and r.json()["data"]["safety_check"]["safety_flag"] is None, r.text[:200])

    r = client.post("/api/v1/consultation-sessions", headers=hs,
                    json={"customer_id": kh_c, "channel": "call"})
    sid = r.json()["data"]["id"]
    r = client.get(f"/api/v1/consultation-sessions/{sid}/missing-fields", headers=hs)
    ok("CONSULT-005 route missing-fields chạy",
       r.status_code == 200 and len(r.json()["data"]["items"]) == 7)

    with pool.connection() as conn:
        don_dep(conn)
        con = conn.execute(
            f"select count(*) as n from crm.customers where full_name like '{DAU}%'"
        ).fetchone()["n"]
    ok("dọn sạch dữ liệu test", con == 0)

    print(f"\nKẾT QUẢ: {PASS} PASS / {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
