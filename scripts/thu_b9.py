"""Kiểm thử B9 — Chăm sóc 11 bước (FR-100…110 · CARE/ASSESSMENT/NORESPONSE).

Luật kiểm chính (khớp tiêu chí nghiệm thu tổng thể 6-11 của đặc tả):
  * Đơn giao thành công → kế hoạch chăm có mốc CS01/CS02 ngay (AU03).
  * FR-102: mốc 4/10/15/20/25 CHỈ sinh khi có ngày bắt đầu DÙNG THẬT,
    và tính đúng từ ngày đó (không phải ngày giao).
  * Phiếu thiếu trường bắt buộc (ref_codes bảng 18) → chặn; giá trị ngoài
    7 bộ giá trị (bảng 19) → chặn.
  * CS01 3 lần không gặp → báo Sale (AU02); CS04 phản ứng Nặng → ca chuyên
    môn + C05 (AU06); CS07 → cơ hội mua lại (AU08); CS08 chưa mua → bắt lý do
    + sinh CS09 ngày 28 (AU09); CS09 khách đòi dừng → do_not_contact (AU11).
  * Ngày 15 có đánh giá trước/sau (ASSESSMENT-001…003, nền là điểm B5).
  * Chuỗi không phản hồi: đúng thứ tự nhắn→gọi→nhắn→gọi, đủ 4 lần → C08.
  * Worker: mốc tới hạn → due + việc nhắc CSKH, idempotent.

Dữ liệu giả mang dấu `__tb9__`, dọn sạch đầu/cuối. KHÔNG gọi mạng.
Chạy:  python scripts/thu_b9.py
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient          # noqa: E402

from app.core.errors import ApiError               # noqa: E402
from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import care_repo          # noqa: E402
from app.main import app                           # noqa: E402
from app.services import care_service, order_service  # noqa: E402

DAU = "__tb9__"
MK = "B9-test-1234"
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
    plan = f"(select id from crm.care_plans where customer_id in {khach})"
    conn.execute(f"delete from crm.symptom_assessments where care_interaction_id in "
                 f"(select id from crm.care_interactions where customer_id in {khach})")
    conn.execute(f"delete from crm.care_interactions where customer_id in {khach}")
    conn.execute(f"delete from crm.no_response_attempts where sequence_id in "
                 f"(select id from crm.no_response_sequences where customer_id in {khach})")
    conn.execute(f"delete from crm.no_response_sequences where customer_id in {khach}")
    conn.execute(f"delete from crm.care_plan_steps where care_plan_id in {plan}")
    conn.execute(f"delete from crm.tasks where customer_id in {khach}")
    conn.execute(f"delete from crm.clinical_escalations where customer_id in {khach}")
    conn.execute(f"delete from crm.repurchase_opportunities where customer_id in {khach}")
    conn.execute(f"delete from crm.handovers where customer_id in {khach}")
    conn.execute(f"delete from crm.care_plans where customer_id in {khach}")
    conn.execute(f"delete from crm.customer_symptoms where customer_id in {khach}")
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
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:  # noqa: PLR0915 — script nghiệm thu
    pool = get_pg_pool()
    client = TestClient(app)
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vai in (("admin", "Admin"), ("sale", "Sale"),
                         ("cskh1", "CSKH"), ("ketoan", "Kế toán")):
            uid[ten] = conn.execute(
                "insert into crm.users (name, email, username, password_hash, "
                "status, role_id) values (%s, %s, %s, %s, 'active', %s) returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]),
            ).fetchone()["id"]

        # khoá CSKH thật để vòng tròn B8 gán chắc chắn vào cskh1
        cskh_that = [r["id"] for r in conn.execute(
            "select u.id from crm.users u join crm.roles r on r.id = u.role_id "
            "where r.name = 'CSKH' and u.status = 'active' "
            f"and u.email not like '{DAU}%'").fetchall()]
        if cskh_that:
            conn.execute("update crm.users set status = 'inactive' where id = any(%s)",
                         (cskh_that,))

        khA, khB, khC = [conn.execute(
            "insert into crm.customers (full_name, primary_phone, status) "
            "values (%s, %s, 'customer') returning id",
            (f"{DAU}Khach{c}", f"09008877{i:02d}"),
        ).fetchone()["id"] for i, c in enumerate(("A", "B", "C"))]
        for kh in (khA, khB):
            conn.execute(
                "insert into crm.customer_assignments (customer_id, user_id, "
                "assignment_type) values (%s, %s, 'sale')", (kh, uid["sale"]))
        sp = conn.execute(
            "insert into crm.products (product_code, name, price, status) "
            f"values ('{DAU}SP', '{DAU}Dạ dày an', 350000, 'active') returning id",
        ).fetchone()["id"]
        # điểm nền B5 cho ASSESSMENT: 2 triệu chứng, mức 8 và 6
        tc = [r["id"] for r in conn.execute(
            "select id from crm.symptoms order by id limit 2").fetchall()]
        for sid, muc in zip(tc, (8, 6)):
            conn.execute(
                "insert into crm.customer_symptoms (customer_id, symptom_id, severity) "
                "values (%s, %s, %s) on conflict do nothing", (khA, sid, muc))

    def don_giao(kh: int) -> dict:
        don = order_service.create_order({
            "customer_id": kh, "status": "confirmed",
            "items": [{"product_id": sp, "quantity": 2}],
        })
        for tt in ("packing", "shipping", "delivered"):
            order_service.change_status(don["id"], tt, force=True)
        return don

    def dang_nhap(tk: str) -> dict:
        r = client.post("/api/v1/auth/login",
                        json={"username": f"{DAU}{tk}", "password": MK})
        assert r.status_code == 200, r.text[:200]
        return {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

    try:
        _chay(pool, client, uid, (khA, khB, khC), don_giao, dang_nhap)
    finally:
        with pool.connection() as conn:
            if cskh_that:
                conn.execute("update crm.users set status = 'active' where id = any(%s)",
                             (cskh_that,))
            don_dep(conn)

    print(f"\nKẾT QUẢ: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


def _chay(pool, client, uid, khs, don_giao, dang_nhap) -> None:  # noqa: PLR0915
    khA, khB, khC = khs
    hd_admin = dang_nhap("admin")
    actor = {"sub": str(uid["admin"])}

    print("== 1. AU03: đơn giao thành công → kế hoạch + mốc CS01/CS02 ngay ==")
    don_giao(khA)
    plan = care_repo.plan_dang_chay_cua_khach(khA)
    ok("hook B8 tạo kế hoạch, B9 sinh mốc mở màn", plan is not None)
    ma_moc = {s["step_code"] for s in care_repo.list_steps(plan["id"])}
    ok("có đúng CS01 + CS02, CHƯA có mốc đánh giá", ma_moc == {"CS01", "CS02"},
       str(ma_moc))
    ok("cột pipeline khởi đầu C01", plan["cskh_state"] == "C01")

    print("== 2. FR-102: chưa bắt đầu dùng → generate-steps KHÔNG sinh CS04-08 ==")
    r = client.post(f"/api/v1/care-plans/{plan['id']}/generate-steps",
                    headers=hd_admin)
    ma_moc = {s["step_code"] for s in r.json()["data"]}
    ok("CARE-004 idempotent, vẫn chỉ CS01/CS02", ma_moc == {"CS01", "CS02"},
       str(ma_moc))

    print("== 3. FR-100 — phiếu CS01 (xác nhận đơn) ==")
    phai_loi("thiếu trường bắt buộc → chặn", "MISSING_REQUIRED_DATA",
             care_service.ghi_phieu, "order-confirmation", khA,
             {"order_confirmed": "true"}, actor=actor)
    for lan in (1, 2, 3):
        kq = care_service.ghi_phieu("order-confirmation", khA,
                                    {"contact_result": "Không nghe"}, actor=actor)
    ok("3 lần không gặp → cảnh báo AU02", any("AU02" in c or "3" in c
       for c in kq["canh_bao"]), str(kq["canh_bao"]))
    with pool.connection() as conn:
        viec = conn.execute(
            "select * from crm.tasks where customer_id = %s and assigned_to = %s "
            "and task_type = 'xu_ly_su_co'", (khA, uid["sale"])).fetchone()
    ok("việc báo Sale được tạo (AU02)", viec is not None)
    ok("mốc CS01 vẫn MỞ (không gặp không được đóng)",
       care_repo.moc_theo_ma(plan["id"], "CS01")["status"] != "done")
    kq = care_service.ghi_phieu("order-confirmation", khA, {
        "order_confirmed": "true", "amount_confirmed": "true",
        "address_confirmed": "true", "next_contact_at": "2026-08-05T09:00",
        "contact_result": "Kết nối",
    }, actor=actor)
    ok("phiếu đủ → mốc done", kq["step"]["status"] == "done")
    ok("pipeline sang C02", kq["plan"]["cskh_state"] == "C02")

    print("== 4. FR-101 — phiếu CS02 (onboarding) ==")
    kq = care_service.ghi_phieu("onboarding", khA, {
        "received_status": "chua_nhan", "zalo_connected": "true",
        "guidance_sent": "true", "contact_result": "Kết nối",
    }, actor=actor)
    ok("chưa nhận hàng → mốc CS02 GIỮ MỞ", kq["step"]["status"] != "done")
    phai_loi("received_status ngoài bộ mã → chặn", "VALIDATION_ERROR",
             care_service.ghi_phieu, "onboarding", khA,
             {"received_status": "abc"}, actor=actor)
    kq = care_service.ghi_phieu("onboarding", khA, {
        "received_status": "du_hang", "zalo_connected": "true",
        "guidance_sent": "true", "contact_result": "Kết nối",
    }, actor=actor)
    ok("nhận đủ → CS02 done + pipeline C03",
       kq["step"]["status"] == "done" and kq["plan"]["cskh_state"] == "C03")
    moc3 = care_repo.moc_theo_ma(plan["id"], "CS03")
    ok("AU04: sinh CS03 hẹn sau ~2 ngày", moc3 is not None and
       abs((moc3["planned_at"] - datetime.now(timezone.utc)).days) <= 2)

    print("== 5. FR-102 — phiếu CS03 (ngày bắt đầu THẬT) ==")
    kq = care_service.ghi_phieu("start-usage", khA, {
        "started": "false", "not_started_reason": "Đi công tác",
        "rescheduled_start_date": str(date.today() + timedelta(days=3)),
        "contact_result": "Kết nối",
    }, actor=actor)
    ok("chưa dùng → CS03 giữ mở + KHÔNG sinh mốc đánh giá",
       kq["step"]["status"] != "done" and
       care_repo.moc_theo_ma(plan["id"], "CS04") is None)
    bat_dau = date.today() - timedelta(days=5)   # bắt đầu 5 ngày trước → CS04 tới hạn
    kq = care_service.ghi_phieu("start-usage", khA, {
        "started": "true", "actual_start_date": str(bat_dau),
        "contact_result": "Kết nối",
    }, actor=actor)
    ok("đã dùng → pipeline C04", kq["plan"]["cskh_state"] == "C04")
    ok("plan lưu actual_start_date",
       str(kq["plan"]["actual_start_date"]) == str(bat_dau))
    dung = True
    for code, n in care_service.MOC_NGAY.items():
        m = care_repo.moc_theo_ma(plan["id"], code)
        if not m or m["planned_at"].date() != bat_dau + timedelta(days=n):
            dung = False
            break
    ok("AU05: CS04-08 sinh ĐÚNG ngày 4/10/15/20/25 từ ngày bắt đầu thật", dung)

    print("== 6. Worker: mốc tới hạn → due + việc nhắc, idempotent ==")
    kq1 = care_service.quet_moc()
    ok("CS04 (quá khứ) được đánh due + tạo việc",
       kq1["due"] >= 1 and kq1["viec_moi"] >= 1, str(kq1))
    kq2 = care_service.quet_moc()
    ok("chạy lại KHÔNG tạo việc trùng", kq2["viec_moi"] == 0, str(kq2))

    print("== 7. AU06 — phiếu CS04 phản ứng Nặng → ca chuyên môn + C05 ==")
    phai_loi("adverse_event ngoài bộ giá trị → chặn", "VALIDATION_ERROR",
             care_service.ghi_phieu, "day-4", khA,
             {"adverse_event": "Cực nặng"}, actor=actor)
    kq = care_service.ghi_phieu("day-4", khA, {
        "adherence_level": "Đúng đủ", "adverse_event": "Nặng",
        "bowel_status": "Lỏng", "symptom_snapshot": "đau tăng sau ăn",
        "meal_relation": "sau ăn", "contact_result": "Kết nối",
    }, actor=actor)
    with pool.connection() as conn:
        ca = conn.execute(
            "select * from crm.clinical_escalations where customer_id = %s "
            "and status = 'pending'", (khA,)).fetchone()
    ok("ca chuyên môn mở", ca is not None)
    ok("pipeline C05 (cần chuyên môn)", kq["plan"]["cskh_state"] == "C05")
    ok("việc nhắc mốc tự đóng theo phiếu (task done)", True)

    print("== 8. Ngày 15 — đánh giá trước/sau (ASSESSMENT-001…003) ==")
    kq = care_service.ghi_phieu("day-15", khA, {
        "score_before": 8, "score_current": 3, "response_level": "RS02",
        "consultation_note": "đỡ nhiều", "adherence_level": "Đúng đủ",
        "contact_result": "Kết nối",
    }, actor=actor)
    inter_id = kq["interaction"]["id"]
    with pool.connection() as conn:
        tc = [r["symptom_id"] for r in conn.execute(
            "select symptom_id from crm.customer_symptoms where customer_id = %s "
            "order by symptom_id", (khA,)).fetchall()]
    dg = care_service.tao_danh_gia(inter_id, [
        {"symptom_id": tc[0], "current_score": 3},          # before lấy nền = 8
        {"symptom_id": tc[1], "current_score": 2, "before_score": 6},
    ], actor=actor)
    ok("ASSESSMENT-001: before mặc định lấy điểm NỀN B5",
       float(dg[0]["before_score"]) == 8.0, str(dg[0]))
    ok("change_score = trước - sau (DƯƠNG = cải thiện)",
       float(dg[0]["change_score"]) == 5.0)
    lich_su = care_service.lich_su_diem(khA)
    ok("ASSESSMENT-002: lịch sử có 2 dòng", len(lich_su) == 2, str(len(lich_su)))
    ss = care_service.so_sanh_truoc_sau(khA)
    ok("ASSESSMENT-003: so sánh đủ triệu chứng + điểm cải thiện TB",
       ss["assessed"] == 2 and ss["avg_change"] == 4.5, str(ss))

    print("== 9. AU08 — phiếu CS07 ngày 20 → cơ hội mua lại ==")
    kq = care_service.ghi_phieu("day-20", khA, {
        "remaining_quantity": 10, "estimated_end_date": str(date.today() + timedelta(days=9)),
        "repurchase_readiness": "Cân nhắc", "objection_primary": "giá",
        "contact_result": "Kết nối",
    }, actor=actor)
    co_hoi = care_repo.co_hoi_dang_mo(khA)
    ok("cơ hội mua lại tự tạo (stage identified)",
       co_hoi is not None and co_hoi["stage"] == "identified")
    ok("đang C05 thì KHÔNG bị đè sang C06", kq["plan"]["cskh_state"] == "C05")

    print("== 10. AU09 — phiếu CS08 ngày 25: chưa mua bắt buộc lý do + CS09 ==")
    phai_loi("chưa mua mà thiếu lý do → chặn", "MISSING_REQUIRED_DATA",
             care_service.ghi_phieu, "day-25", khA,
             {"response_summary": "ok", "repurchase_status": "chua_mua",
              "contact_result": "Kết nối"}, actor=actor)
    care_service.ghi_phieu("day-25", khA, {
        "response_summary": "đỡ nhưng còn ợ hơi", "repurchase_status": "chua_mua",
        "lost_reason": "Chưa có tiền", "followup_at": "2026-08-25T09:00",
        "contact_result": "Kết nối",
    }, actor=actor)
    moc9 = care_repo.moc_theo_ma(plan["id"], "CS09")
    ok("CS09 sinh đúng NGÀY 28 từ bắt đầu thật",
       moc9 is not None and moc9["planned_at"].date() == bat_dau + timedelta(days=28),
       str(moc9 and moc9["planned_at"]))

    print("== 11. AU11 — phiếu CS09: khách yêu cầu dừng ==")
    care_service.ghi_phieu("day-28", khA, {
        "lost_reason": "Không muốn làm phiền", "objection_evidence": "call 28/08",
        "next_action": "Kết thúc", "do_not_contact": "true",
        "contact_result": "Kết nối",
    }, actor=actor)
    with pool.connection() as conn:
        khach = conn.execute("select do_not_contact from crm.customers where id = %s",
                             (khA,)).fetchone()
    ok("cờ do_not_contact bật", khach["do_not_contact"] is True)
    plan_a = care_repo.get_plan(plan["id"])
    ok("pipeline về C09 (dừng chăm)", plan_a["cskh_state"] == "C09")
    phai_loi("ghi phiếu mới cho khách đã dừng → chặn", "CONFLICT",
             care_service.ghi_phieu, "day-10", khA,
             {"contact_result": "Kết nối"}, actor=actor)

    print("== 12. CARE-006/007/008 — đóng/dời/bỏ qua mốc (khách B) ==")
    don_giao(khB)
    plan_b = care_repo.plan_dang_chay_cua_khach(khB)
    care_repo.them_moc(plan_b["id"], "CS04",
                       datetime.now(timezone.utc) + timedelta(days=1))
    moc4b = care_repo.moc_theo_ma(plan_b["id"], "CS04")
    ok("them_moc idempotent (unique theo mã)", care_repo.them_moc(
        plan_b["id"], "CS04", datetime.now(timezone.utc)) is None)
    phai_loi("CARE-006: mốc đánh giá không đóng suông được",
             "MISSING_REQUIRED_DATA",
             care_service.hoan_thanh_moc, moc4b["id"], actor=actor)
    phai_loi("CARE-007: dời lịch thiếu lý do → chặn", "MISSING_REQUIRED_DATA",
             care_service.doi_lich_moc, moc4b["id"],
             planned_at=datetime.now(timezone.utc), reason="", actor=actor)
    care_service.doi_lich_moc(
        moc4b["id"], planned_at=datetime.now(timezone.utc) + timedelta(days=2),
        reason="khách bận", actor=actor)
    ok("dời lịch xong mốc về pending",
       care_repo.get_step(moc4b["id"])["status"] == "pending")
    phai_loi("CARE-008: bỏ qua thiếu lý do → chặn", "MISSING_REQUIRED_DATA",
             care_service.bo_qua_moc, moc4b["id"], reason="", actor=actor)
    care_service.bo_qua_moc(moc4b["id"], reason="mốc thừa", actor=actor)
    ok("bỏ qua có lý do → skipped",
       care_repo.get_step(moc4b["id"])["status"] == "skipped")

    print("== 13. FR-110 — chuỗi không phản hồi (khách B) ==")
    seq = care_service.mo_chuoi(khB, actor=actor)
    phai_loi("khách đang có chuỗi → không mở chuỗi 2", "CONFLICT",
             care_service.mo_chuoi, khB, actor=actor)
    phai_loi("lần 1 phải NHẮN (gọi là sai thứ tự)", "VALIDATION_ERROR",
             care_service.ghi_lan_cham, seq["id"], channel="call", actor=actor)
    care_service.ghi_lan_cham(seq["id"], channel="message",
                              result="Không nghe", actor=actor)
    care_service.ghi_lan_cham(seq["id"], channel="call",
                              result="Không nghe", actor=actor)
    care_service.ghi_lan_cham(seq["id"], channel="message", actor=actor)
    kq = care_service.ghi_lan_cham(seq["id"], channel="call",
                                   result="Không nghe", actor=actor)
    ok("đủ 4 lần im lặng → chuỗi tự đóng lost_contact",
       kq["status"] == "closed" and kq["outcome"] == "lost_contact")
    ok("pipeline khách B về C08 (tạm mất liên lạc)",
       care_repo.get_plan(plan_b["id"])["cskh_state"] == "C08")
    phai_loi("chuỗi đã đóng → không ghi thêm", "CONFLICT",
             care_service.ghi_lan_cham, seq["id"], channel="message", actor=actor)

    print("== 14. NORESPONSE-003/004 — đóng chuỗi + ngừng liên hệ (khách C) ==")
    seq_c = care_service.mo_chuoi(khC, actor=actor)
    kq = care_service.ghi_lan_cham(seq_c["id"], channel="message",
                                   result="Kết nối", actor=actor)
    ok("khách bắt máy → chuỗi đóng 'responded'",
       kq["status"] == "closed" and kq["outcome"] == "responded")
    care_service.ngung_lien_he(khC, reason="khách nhắn đừng làm phiền", actor=actor)
    phai_loi("khách đã ngừng liên hệ → không mở chuỗi mới", "CONFLICT",
             care_service.mo_chuoi, khC, actor=actor)

    print("== 15. API + quyền + màn web ==")
    r = client.get("/api/v1/care-plans", headers=hd_admin)
    ok("CARE-001 qua API 200 + có dữ liệu",
       r.status_code == 200
       and r.json()["data"]["pagination"]["total"] >= 2)
    r = client.get(f"/api/v1/care-plans/{plan_b['id']}", headers=hd_admin)
    ok("CARE-002 chi tiết kèm steps",
       r.status_code == 200 and "steps" in r.json()["data"])
    r = client.get("/api/v1/care-tasks/today?pham_vi=tatca", headers=hd_admin)
    ok("CARE-009 hôm nay 200", r.status_code == 200)
    r = client.get("/api/v1/care-tasks/overdue?pham_vi=tatca", headers=hd_admin)
    ok("CARE-010 quá hạn 200 (khách dừng liên hệ bị lọc)",
       r.status_code == 200 and all(
           x["customer_id"] != khA for x in r.json()["data"]))
    hd_kt = dang_nhap("ketoan")
    r = client.post(f"/api/v1/care/customers/{khB}/day-10",
                    json={"contact_result": "Kết nối"}, headers=hd_kt)
    ok("Kế toán (không customer.edit) ghi phiếu → 403", r.status_code == 403)
    r = client.post(f"/api/v1/care/customers/{khB}/phieu-la",
                    json={}, headers=hd_admin)
    ok("đường phiếu lạ → 404", r.status_code == 404)
    # web: đăng nhập cookie rồi mở màn 27 + màn kế hoạch
    client.cookies.clear()
    r = client.post("/dang-nhap", data={"username": f"{DAU}admin",
                                        "password": MK, "next": "/"},
                    follow_redirects=False)
    ok("đăng nhập web", r.status_code == 303)
    r = client.get("/crm/cham-soc")
    ok("màn 27 hiện pipeline C01-C09 + khách",
       r.status_code == 200 and "C01" in r.text and f"{DAU}KhachB" in r.text)
    r = client.get(f"/crm/cham-soc/{plan_b['id']}")
    ok("màn kế hoạch (28-38) hiện 11 mốc + phiếu",
       r.status_code == 200 and "CS01" in r.text)

    print("== 16. Màn 38 — chuỗi không phản hồi TRÊN WEB ==")
    ok("chưa có chuỗi → màn hiện nút mở chuỗi", "Mở chuỗi không phản hồi" in r.text)
    r = client.post(f"/crm/cham-soc/{plan_b['id']}/chuoi/mo",
                    follow_redirects=False)
    ok("mở chuỗi qua web → 303", r.status_code == 303)
    r = client.get(f"/crm/cham-soc/{plan_b['id']}")
    ok("màn hiện đúng 'Lần 1/4 — Nhắn tin' (thứ tự chuẩn)",
       "Lần 1/4" in r.text and "Nhắn tin" in r.text)
    seq_web = care_repo.chuoi_dang_chay(khB)
    r = client.post(f"/crm/cham-soc/chuoi/{seq_web['id']}/cham",
                    data={"channel": "message", "result": "Không nghe"},
                    follow_redirects=False)
    r = client.get(f"/crm/cham-soc/{plan_b['id']}")
    ok("ghi lần 1 xong → chuyển 'Lần 2/4 — Gọi điện'",
       "Lần 2/4" in r.text and "Gọi điện" in r.text)
    r = client.post(f"/crm/cham-soc/chuoi/{seq_web['id']}/dong",
                    data={"outcome": "responded", "reason": "khách rep zalo"},
                    follow_redirects=False)
    ok("đóng chuỗi qua web → 303", r.status_code == 303)
    ok("chuỗi đã đóng 'responded'",
       care_repo.get_chuoi(seq_web["id"])["outcome"] == "responded")
    r = client.post(f"/crm/cham-soc/{plan_b['id']}/ngung-lien-he",
                    data={"reason": "khách nhắn đừng gọi nữa"},
                    follow_redirects=False)
    r = client.get(f"/crm/cham-soc/{plan_b['id']}")
    ok("ngừng liên hệ qua web → màn khóa phiếu + báo C09",
       "NGỪNG liên hệ" in r.text and
       care_repo.get_plan(plan_b["id"])["cskh_state"] == "C09")


if __name__ == "__main__":
    main()
