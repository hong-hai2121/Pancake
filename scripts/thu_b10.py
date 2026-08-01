"""Kiểm thử B10 — Mua lại & khách ngủ (FR-120…123 · REPURCHASE-001…010 · màn 39-41).

Luật kiểm chính:
  * FR-121: 1 khách 1 cơ hội mở; khách ngừng liên hệ không mở; readiness theo bộ.
  * FR-122: 9 nhãn suy từ stage + ngày (chưa/sắp/đến hạn/quá hạn/khách ngủ…);
    chuyển bước theo TRANSITIONS, 'Chưa mua' bắt buộc lý do (9 mã chuẩn BRD).
  * FR-120: ngày hết = bắt đầu THẬT + số ngày mẫu × hệ số tuân thủ + tạm dừng
    + hàng cũ; lưu vào liệu trình + đồng bộ cơ hội mở; 'Chưa dùng' → chặn.
  * FR-123: khách ngủ 30/60/90/180, lọc giá trị, loại do_not_contact; gán
    chiến dịch + việc mua lại; doanh thu tái kích hoạt đo TỰ ĐỘNG khi có đơn.
  * Đơn giao thành công → cơ hội mở tự 'won' (Đã mua = có đơn mới).

Dữ liệu giả mang dấu `__tb10__`, dọn sạch đầu/cuối. KHÔNG gọi mạng.
Chạy:  python scripts/thu_b10.py
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient          # noqa: E402

from app.core.errors import ApiError               # noqa: E402
from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import repurchase_repo    # noqa: E402
from app.main import app                           # noqa: E402
from app.services import order_service, repurchase_service  # noqa: E402

DAU = "__tb10__"
MK = "B10-test-1234"
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
    conn.execute(f"delete from crm.reactivation_members where customer_id in {khach}")
    conn.execute(
        f"delete from crm.reactivation_campaigns where name like '{DAU}%'")
    conn.execute(f"delete from crm.repurchase_opportunities where customer_id in {khach}")
    conn.execute(f"delete from crm.symptom_assessments where care_interaction_id in "
                 f"(select id from crm.care_interactions where customer_id in {khach})")
    conn.execute(f"delete from crm.care_interactions where customer_id in {khach}")
    conn.execute(f"delete from crm.care_plan_steps where care_plan_id in "
                 f"(select id from crm.care_plans where customer_id in {khach})")
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


def main() -> None:  # noqa: PLR0915
    pool = get_pg_pool()
    client = TestClient(app)
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vai in (("admin", "Admin"), ("cskh1", "CSKH"),
                         ("ketoan", "Kế toán")):
            uid[ten] = conn.execute(
                "insert into crm.users (name, email, username, password_hash, "
                "status, role_id) values (%s, %s, %s, %s, 'active', %s) returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]),
            ).fetchone()["id"]
        cskh_that = [r["id"] for r in conn.execute(
            "select u.id from crm.users u join crm.roles r on r.id = u.role_id "
            "where r.name = 'CSKH' and u.status = 'active' "
            f"and u.email not like '{DAU}%'").fetchall()]
        if cskh_that:
            conn.execute("update crm.users set status = 'inactive' where id = any(%s)",
                         (cskh_that,))

        kh = {}
        for i, ten in enumerate(("D", "E", "F", "G", "H")):
            kh[ten] = conn.execute(
                "insert into crm.customers (full_name, primary_phone, status) "
                "values (%s, %s, 'customer') returning id",
                (f"{DAU}Khach{ten}", f"09007766{i:02d}"),
            ).fetchone()["id"]
        # G: đã yêu cầu ngừng liên hệ — phải bị loại khỏi mọi danh sách
        conn.execute("update crm.customers set do_not_contact = true where id = %s",
                     (kh["G"],))

        sp = conn.execute(
            "insert into crm.products (product_code, name, price, status) "
            f"values ('{DAU}SP', '{DAU}Dạ dày an', 500000, 'active') returning id",
        ).fetchone()["id"]
        mau = conn.execute(
            "insert into crm.treatment_templates (template_code, name, status, "
            f"duration_days) values ('{DAU}LT', '{DAU}LT 1 tháng', 'active', 30) "
            "returning id").fetchone()["id"]
        # liệu trình + kế hoạch chăm có NGÀY BẮT ĐẦU THẬT (nguồn FR-120)
        bat_dau = date.today() - timedelta(days=10)
        lt_d = conn.execute(
            "insert into crm.customer_treatments (customer_id, template_id, "
            "status, start_date) values (%s, %s, 'active', %s) returning id",
            (kh["D"], mau, bat_dau - timedelta(days=3)),
        ).fetchone()["id"]
        conn.execute(
            "insert into crm.care_plans (customer_id, customer_treatment_id, "
            "owner_id, actual_start_date) values (%s, %s, %s, %s)",
            (kh["D"], lt_d, uid["cskh1"], bat_dau))
        # khách ngủ: E ngủ 100 ngày (1tr) · F ngủ 40 ngày (200k) · G ngủ 50 ngày
        for ten, ngay, tien in (("E", 100, 1000000), ("F", 40, 200000),
                                ("G", 50, 300000)):
            conn.execute(
                "insert into crm.orders (customer_id, status, total_amount, "
                "delivered_at, created_at) values (%s, 'delivered', %s, "
                "now() - make_interval(days => %s), now() - make_interval(days => %s))",
                (kh[ten], tien, ngay, ngay + 3))

    def dang_nhap(tk: str) -> dict:
        r = client.post("/api/v1/auth/login",
                        json={"username": f"{DAU}{tk}", "password": MK})
        assert r.status_code == 200, r.text[:200]
        return {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

    try:
        _chay(pool, client, uid, kh, sp, lt_d, bat_dau, dang_nhap)
    finally:
        with pool.connection() as conn:
            if cskh_that:
                conn.execute("update crm.users set status = 'active' where id = any(%s)",
                             (cskh_that,))
            don_dep(conn)

    print(f"\nKẾT QUẢ: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


def _chay(pool, client, uid, kh, sp, lt_d, bat_dau, dang_nhap) -> None:  # noqa: PLR0915
    svc = repurchase_service
    actor = {"sub": str(uid["admin"])}
    hd_admin = dang_nhap("admin")

    print("== 1. FR-121 — tạo cơ hội (REPURCHASE-003/004) ==")
    phai_loi("khách không tồn tại → chặn", "NOT_FOUND",
             svc.tao, {"customer_id": 999999999}, actor=actor)
    phai_loi("khách ngừng liên hệ → không mở cơ hội", "CONFLICT",
             svc.tao, {"customer_id": kh["G"]}, actor=actor)
    phai_loi("readiness ngoài bộ giá trị → chặn", "VALIDATION_ERROR",
             svc.tao, {"customer_id": kh["D"], "readiness": "Rất máu"},
             actor=actor)
    opp_d = svc.tao({"customer_id": kh["D"], "current_treatment_id": lt_d,
                     "readiness": "Cân nhắc", "expected_value": 900000},
                    actor=actor)
    ok("tạo được cơ hội, bước đầu 'identified'", opp_d["stage"] == "identified")
    phai_loi("1 khách 1 cơ hội mở — tạo trùng bị chặn", "CONFLICT",
             svc.tao, {"customer_id": kh["D"]}, actor=actor)
    svc.cap_nhat(opp_d["id"], {"next_template_id": None,
                               "expected_value": 1200000}, actor=actor)
    ok("REPURCHASE-004 sửa được giá trị dự kiến",
       float(svc.chi_tiet(opp_d["id"])["expected_value"]) == 1200000)

    print("== 2. FR-122 — 9 nhãn suy từ ngày (không lưu cột) ==")
    cach_nhan = [(20, "chua_den_han"), (5, "sap_den_han"), (0, "den_han"),
                 (-5, "qua_han"), (-40, "khach_ngu")]
    dung = True
    for lech, nhan in cach_nhan:
        repurchase_repo.update(opp_d["id"],
                               expected_close_date=date.today() + timedelta(days=lech))
        thay = svc.chi_tiet(opp_d["id"])["display_state"]
        if thay != nhan:
            dung = False
            ok(f"nhãn lệch {lech} ngày", False, f"ra {thay} thay vì {nhan}")
            break
    ok("nhãn thời gian đúng cả 5 mốc (chưa/sắp/đến/quá hạn/ngủ)", dung)

    print("== 3. REPURCHASE-005/006 — chuyển bước + lý do chuẩn ==")
    kq = svc.chuyen_stage(opp_d["id"], "contacted", actor=actor)
    ok("identified → contacted (nhãn 'Đang tư vấn')",
       kq["display_state"] == "dang_tu_van")
    phai_loi("contacted → identified (đi lùi) → chặn", "CONFLICT",
             svc.chuyen_stage, opp_d["id"], "identified", actor=actor)
    phai_loi("→ lost thiếu lý do → chặn", "MISSING_REQUIRED_DATA",
             svc.chuyen_stage, opp_d["id"], "lost", actor=actor)
    with pool.connection() as conn:
        ma_ly_do = conn.execute(
            "select code from crm.lead_reasons order by id limit 1"
        ).fetchone()["code"]
    kq = svc.ghi_ly_do(opp_d["id"], ma_ly_do=ma_ly_do,
                       note="hẹn sang tháng", actor=actor)
    ok("REPURCHASE-006: lý do CHUẨN (lead_reasons) + tự chuyển lost",
       kq["stage"] == "lost" and kq["lost_reason_id"] is not None)
    phai_loi("mã lý do lạ → chặn", "VALIDATION_ERROR",
             svc.ghi_ly_do, opp_d["id"], ma_ly_do="XYZ", actor=actor)
    phai_loi("cơ hội đã đóng — không sửa nữa", "CONFLICT",
             svc.cap_nhat, opp_d["id"], {"expected_value": 1}, actor=actor)

    print("== 4. FR-120 — tính ngày dự kiến hết (REPURCHASE-007) ==")
    kq = svc.tinh_ngay_het(lt_d, {}, actor=actor)
    ok("mặc định: bắt đầu THẬT (care plan) + 30 ngày mẫu",
       kq["start_date"] == str(bat_dau)
       and kq["expected_end_date"] == str(bat_dau + timedelta(days=30)),
       str(kq))
    kq = svc.tinh_ngay_het(lt_d, {"adherence_level": "Thiếu liều",
                                  "tam_dung_ngay": 2}, actor=actor)
    ok("thiếu liều ×1.25 + tạm dừng 2 ngày (minh bạch từng khoản)",
       kq["factor"] == 1.25
       and kq["expected_end_date"] == str(bat_dau + timedelta(
           days=round(30 * 1.25) + 2)), str(kq))
    with pool.connection() as conn:
        luu = conn.execute(
            "select expected_end_date from crm.customer_treatments where id = %s",
            (lt_d,)).fetchone()
    ok("kết quả LƯU vào liệu trình", str(luu["expected_end_date"]) ==
       kq["expected_end_date"])
    phai_loi("khách 'Chưa dùng' → chặn tính", "CONFLICT",
             svc.tinh_ngay_het, lt_d, {"adherence_level": "Chưa dùng"},
             actor=actor)

    print("== 5. REPURCHASE-008/009 — sắp đến hạn / quá hạn ==")
    opp_e = svc.tao({"customer_id": kh["E"],
                     "expected_close_date": date.today() + timedelta(days=3)},
                    actor=actor)
    opp_f = svc.tao({"customer_id": kh["F"],
                     "expected_close_date": date.today() - timedelta(days=4)},
                    actor=actor)
    sap = {r["id"] for r in svc.sap_den_han(7)}
    tre = {r["id"] for r in svc.qua_han()}
    ok("due-soon (7 ngày) bắt đúng cơ hội +3 ngày",
       opp_e["id"] in sap and opp_f["id"] not in sap)
    ok("overdue bắt đúng cơ hội -4 ngày",
       opp_f["id"] in tre and opp_e["id"] not in tre)

    print("== 6. FR-123 — khách ngủ (REPURCHASE-010) ==")
    ngu = svc.khach_ngu(30)
    ids = {r["id"] for r in ngu["items"]}
    ok("E (100 ngày) + F (40 ngày) nằm trong danh sách ≥30",
       kh["E"] in ids and kh["F"] in ids)
    ok("G (do_not_contact) bị LOẠI dù ngủ 50 ngày", kh["G"] not in ids)
    ok("H (chưa từng mua) không tính là khách ngủ", kh["H"] not in ids)
    ok("chia rổ đúng: E vào 90+, F vào 30-59",
       ngu["buckets"]["90"] == 1 and ngu["buckets"]["30"] == 1, str(ngu["buckets"]))
    ngu_gia_tri = svc.khach_ngu(30, gia_tri_tu=500000)
    ok("lọc theo tổng giá trị mua ≥ 500k → chỉ còn E",
       {r["id"] for r in ngu_gia_tri["items"]} == {kh["E"]})
    phai_loi("tu_ngay = 0 → chặn", "VALIDATION_ERROR", svc.khach_ngu, 0)

    print("== 7. FR-123 — gán chiến dịch + việc + đo doanh thu tự động ==")
    phai_loi("không chọn khách → chặn", "MISSING_REQUIRED_DATA",
             svc.gan_chien_dich, customer_ids=[], ten_moi="x", actor=actor)
    phai_loi("không chọn/đặt tên chiến dịch → chặn", "MISSING_REQUIRED_DATA",
             svc.gan_chien_dich, customer_ids=[kh["E"]], actor=actor)
    kq = svc.gan_chien_dich(ten_moi=f"{DAU}Đánh thức T8",
                            customer_ids=[kh["E"], kh["F"], kh["G"]],
                            assigned_to=uid["cskh1"], tao_viec=True, actor=actor)
    ok("gán 2 khách, G (ngừng liên hệ) bị bỏ qua",
       kq["them"] == 2 and kq["bo_qua"] == 1, str(kq))
    with pool.connection() as conn:
        viec = conn.execute(
            "select count(*) as n from crm.tasks where task_type = 'mua_lai' "
            "and assigned_to = %s and customer_id in (%s, %s)",
            (uid["cskh1"], kh["E"], kh["F"])).fetchone()["n"]
    ok("mỗi khách 1 việc 'mua_lai' cho người được giao", viec == 2, str(viec))
    kq2 = svc.gan_chien_dich(campaign_id=kq["campaign"]["id"],
                             customer_ids=[kh["E"]], actor=actor)
    ok("gán lại khách đã trong chiến dịch → bỏ qua (unique)",
       kq2["them"] == 0 and kq2["bo_qua"] == 1)

    # đơn mới của F giao thành công → cơ hội mở tự WON + member converted
    don = order_service.create_order({
        "customer_id": kh["F"], "status": "confirmed",
        "items": [{"product_id": sp, "quantity": 1}]})
    for tt in ("packing", "shipping", "delivered"):
        order_service.change_status(don["id"], tt, force=True)
    ok("đơn giao TC → cơ hội mở của F tự 'won' (Đã mua = có đơn mới)",
       svc.chi_tiet(opp_f["id"])["stage"] == "won")
    bc = [c for c in svc.bao_cao_chien_dich()
          if c["id"] == kq["campaign"]["id"]][0]
    ok("doanh thu tái kích hoạt đo TỰ ĐỘNG (500k từ đơn mới của F)",
       bc["chuyen_doi"] == 1 and float(bc["doanh_thu"]) == 500000, str(dict(bc)))

    print("== 8. API + quyền + màn web ==")
    r = client.get("/api/v1/customers/sleeping?tu_ngay=30", headers=hd_admin)
    ok("REPURCHASE-010 literal route thắng /customers/{id}",
       r.status_code == 200 and r.json()["data"]["buckets"]["90"] >= 1,
       f"status={r.status_code}")
    r = client.get("/api/v1/repurchase-opportunities?nhan=sap_den_han",
                   headers=hd_admin)
    ok("REPURCHASE-001 lọc theo nhãn suy ra", r.status_code == 200)
    r = client.get("/api/v1/repurchase-opportunities/due-soon?pham_vi=tatca",
                   headers=hd_admin)
    ok("REPURCHASE-008 qua API 200", r.status_code == 200)
    hd_kt = dang_nhap("ketoan")
    r = client.post(f"/api/v1/repurchase-opportunities/{opp_e['id']}/move-stage",
                    json={"stage": "contacted"}, headers=hd_kt)
    ok("Kế toán (không customer.edit) chuyển bước → 403", r.status_code == 403)
    client.cookies.clear()
    r = client.post("/dang-nhap", data={"username": f"{DAU}admin",
                                        "password": MK, "next": "/"},
                    follow_redirects=False)
    ok("đăng nhập web", r.status_code == 303)
    r = client.get("/crm/mua-lai")
    ok("màn 39-40 hiện cơ hội + nhãn FR-122",
       r.status_code == 200 and "Sắp đến hạn" in r.text
       and f"{DAU}KhachE" in r.text)
    r = client.get("/crm/khach-ngu")
    ok("màn 41 hiện khách ngủ + chiến dịch",
       r.status_code == 200 and f"{DAU}KhachE" in r.text
       and f"{DAU}Đánh thức T8" in r.text)
    r = client.post(f"/crm/mua-lai/{opp_e['id']}/chuyen",
                    data={"stage": "contacted", "reason": ""},
                    follow_redirects=False)
    ok("chuyển bước từ web → 303",
       r.status_code == 303
       and svc.chi_tiet(opp_e["id"])["stage"] == "contacted")


if __name__ == "__main__":
    main()
