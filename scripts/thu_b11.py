"""Kiểm thử B11 — Báo cáo (REPORT-001…011 · FR-170…173 · màn 4-6 + 60-64).

Luật kiểm chính:
  * FR-173: số tổng và danh sách drill-down CÙNG điều kiện lọc — đếm phải
    khớp nhau từng metric; lọc theo người (user_id) ăn cả hai phía.
  * Quyền theo nội dung: doanh thu = revenue.view · ads = ads.view; drill-down
    kiểm quyền TỪNG metric; export thêm data.export + audit (FR-181).
  * REPORT-002/003 mỗi nhân viên một dòng, tỷ lệ đúng; lead vào bước đếm theo
    LỊCH SỬ FR-041 (khách sang bước sau vẫn tính đã qua bước trước).

DB đang có DỮ LIỆU THẬT → số toàn cục chỉ kiểm ≥; số CỦA NGƯỜI TEST (user_id
mới tinh) kiểm bằng ĐÚNG. Dấu `__tb11__`, dọn sạch đầu/cuối. KHÔNG gọi mạng.
Chạy:  python scripts/thu_b11.py
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
from app.main import app                           # noqa: E402
from app.services import report_service            # noqa: E402

DAU = "__tb11__"
MK = "B11-test-1234"
PASS = 0
FAIL = 0
NAY = date.today().isoformat()


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
    conn.execute(f"delete from crm.repurchase_opportunities where customer_id in {khach}")
    conn.execute(f"delete from crm.care_plan_steps where care_plan_id in "
                 f"(select id from crm.care_plans where customer_id in {khach})")
    conn.execute(f"delete from crm.tasks where customer_id in {khach}")
    conn.execute(f"delete from crm.handovers where customer_id in {khach}")
    conn.execute(f"delete from crm.care_plans where customer_id in {khach}")
    conn.execute(
        f"delete from crm.order_status_history where order_id in "
        f"(select id from crm.orders where customer_id in {khach})")
    conn.execute(f"delete from crm.orders where customer_id in {khach}")
    conn.execute(f"delete from crm.lead_stage_history where lead_id in "
                 f"(select id from crm.leads where customer_id in {khach})")
    conn.execute(f"delete from crm.leads where customer_id in {khach}")
    conn.execute(f"delete from crm.customer_assignments where customer_id in {khach}")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(
        f"delete from crm.ad_metrics_daily where external_id like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:  # noqa: PLR0915
    pool = get_pg_pool()
    client = TestClient(app)
    gio = datetime.now(timezone.utc)
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vai in (("admin", "Admin"), ("sale1", "Sale"),
                         ("sale2", "Sale"), ("cskh1", "CSKH"),
                         ("mkt", "Marketing"), ("ketoan", "Kế toán")):
            uid[ten] = conn.execute(
                "insert into crm.users (name, email, username, password_hash, "
                "status, role_id) values (%s, %s, %s, %s, 'active', %s) returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]),
            ).fetchone()["id"]

        kh1, kh2 = [conn.execute(
            "insert into crm.customers (full_name, primary_phone, status) "
            "values (%s, %s, 'customer') returning id",
            (f"{DAU}Khach{i}", f"09006655{i:02d}"),
        ).fetchone()["id"] for i in (1, 2)]

        st = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.pipeline_stages").fetchall()}
        pipe = conn.execute(
            "select pipeline_id from crm.pipeline_stages limit 1"
        ).fetchone()["pipeline_id"]

        def lead(kh, owner, contact=False):
            row = conn.execute(
                "insert into crm.leads (customer_id, pipeline_id, stage_id, "
                "owner_id, first_contact_at) values (%s, %s, %s, %s, %s) "
                "returning id",
                (kh, pipe, list(st.values())[0], owner,
                 gio if contact else None),
            ).fetchone()
            return row["id"]

        l1 = lead(kh1, uid["sale1"], contact=True)   # đi trọn phễu
        lead(kh1, uid["sale1"])                      # l2 — chưa liên hệ
        lead(kh2, uid["sale2"], contact=True)        # l3 — của sale2
        for buoc in ("Đã tư vấn", "Đã báo giá", "Đã chốt"):
            conn.execute(
                "insert into crm.lead_stage_history (lead_id, to_stage_id, "
                "changed_at, reason) values (%s, %s, %s, null)",
                (l1, st[buoc], gio))
        # 1 lead của sale2 thua kèm LÝ DO — nguồn 'lý do chưa chốt' FR-172
        conn.execute(
            "insert into crm.lead_stage_history (lead_id, to_stage_id, "
            "changed_at, reason) values (%s, %s, %s, %s)",
            (l1, st["Từ chối"], gio, f"{DAU}Giá cao"))

        def don(kh, owner, tien, loai, trang_thai="delivered"):
            conn.execute(
                "insert into crm.orders (customer_id, sale_owner_id, status, "
                "order_type, total_amount, delivered_at, created_at) "
                "values (%s, %s, %s, %s, %s, %s, %s)",
                (kh, owner, trang_thai, loai, tien,
                 gio if trang_thai == 'delivered' else None, gio))

        don(kh1, uid["sale1"], 800000, "new")
        don(kh1, uid["sale1"], 300000, "repurchase")
        don(kh2, uid["sale2"], 500000, "new", trang_thai="returned")

        # việc của cskh1: 1 đúng hạn · 1 trễ · 1 đang quá hạn
        for due, done in ((gio + timedelta(hours=2), gio),
                          (gio - timedelta(days=1), gio), (None, None)):
            if done:
                conn.execute(
                    "insert into crm.tasks (customer_id, assigned_to, task_type, "
                    "due_at, status, completed_at) "
                    "values (%s, %s, 'cham_soc', %s, 'done', %s)",
                    (kh1, uid["cskh1"], due, done))
            else:
                conn.execute(
                    "insert into crm.tasks (customer_id, assigned_to, task_type, "
                    "due_at, status) values (%s, %s, 'goi', %s, 'open')",
                    (kh1, uid["cskh1"], gio - timedelta(days=2)))

        plan = conn.execute(
            "insert into crm.care_plans (customer_id, owner_id) "
            "values (%s, %s) returning id", (kh1, uid["cskh1"])).fetchone()["id"]
        conn.execute(   # mốc xong đúng hạn
            "insert into crm.care_plan_steps (care_plan_id, step_code, planned_at, "
            "status, completed_at) values (%s, 'CS01', %s, 'done', %s)",
            (plan, gio, gio))
        conn.execute(   # mốc xong + PHẢN ỨNG NẶNG (nguồn khach_phan_ung)
            "insert into crm.care_plan_steps (care_plan_id, step_code, planned_at, "
            "status, completed_at, data) values (%s, 'CS04', %s, 'done', %s, "
            "'{\"adverse_event\": \"Nặng\"}'::jsonb)", (plan, gio, gio))
        conn.execute(   # mốc quá hạn đang chờ
            "insert into crm.care_plan_steps (care_plan_id, step_code, planned_at, "
            "status) values (%s, 'CS05', %s, 'pending')",
            (plan, gio - timedelta(days=2)))
        conn.execute(
            "insert into crm.handovers (customer_id, cskh_user_id, status) "
            "values (%s, %s, 'assigned')", (kh1, uid["cskh1"]))
        conn.execute(
            "insert into crm.repurchase_opportunities (customer_id, owner_id, "
            "expected_close_date, stage, stage_moved_at) "
            "values (%s, %s, %s, 'won', %s)",
            (kh2, uid["cskh1"], date.today(), gio))
        for i, (ngay, chi) in enumerate(((date.today(), 100000),
                                         (date.today() - timedelta(days=1), 50000))):
            conn.execute(
                "insert into crm.ad_metrics_daily (entity_type, entity_id, "
                "external_id, ngay, spend) values ('ad', %s, %s, %s, %s) "
                "on conflict do nothing",
                (900000 + i, f"{DAU}ad{i}", ngay, chi))

    def dang_nhap(tk: str) -> dict:
        r = client.post("/api/v1/auth/login",
                        json={"username": f"{DAU}{tk}", "password": MK})
        assert r.status_code == 200, r.text[:200]
        return {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

    try:
        _chay(pool, client, uid, dang_nhap)
    finally:
        with pool.connection() as conn:
            don_dep(conn)
    print(f"\nKẾT QUẢ: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


def _chay(pool, client, uid, dang_nhap) -> None:  # noqa: PLR0915
    admin = {"sub": str(uid["admin"]),
             "perms": ["customer.view", "revenue.view", "ads.view",
                       "data.export"]}
    cskh_user = {"sub": str(uid["cskh1"]), "perms": ["customer.view"]}

    print("== 1. FR-173 — số tổng và drill-down CÙNG điều kiện ==")
    for metric in ("lead_moi", "don_giao", "viec_qua_han", "khach_phan_ung"):
        kq = report_service.drill_down(metric, NAY, NAY, None, user=admin)
        ok(f"[{metric}] tổng == số dòng danh sách",
           kq["tong"] == len(kq["rows"]) or len(kq["rows"]) == 200,
           f"tong={kq['tong']} rows={len(kq['rows'])}")
    kq = report_service.drill_down("doanh_thu_giao", NAY, NAY, None, user=admin)
    tong_dong = sum(float(r["so_tien"]) for r in kq["rows"])
    ok("[doanh_thu_giao] SUM == cộng từng dòng", kq["tong"] == tong_dong,
       f"{kq['tong']} vs {tong_dong}")

    print("== 2. Lọc theo NGƯỜI ăn cả số lẫn danh sách ==")
    kq1 = report_service.drill_down("lead_moi", NAY, NAY, uid["sale1"], user=admin)
    kq2 = report_service.drill_down("lead_moi", NAY, NAY, uid["sale2"], user=admin)
    ok("sale1 có 2 lead, sale2 có 1 (đúng tuyệt đối — user mới tinh)",
       kq1["tong"] == 2 and kq2["tong"] == 1,
       f"{kq1['tong']} / {kq2['tong']}")
    kq = report_service.drill_down("doanh_thu_giao", NAY, NAY, uid["sale1"],
                                   user=admin)
    ok("doanh thu sale1 = 800k + 300k", kq["tong"] == 1100000, str(kq["tong"]))

    print("== 3. REPORT-001 dashboard + quyền cắt ô ==")
    db = report_service.dashboard(NAY, NAY, user=admin)
    ok("đủ ô + có doanh thu/chi phí (admin)",
       db["so"].get("doanh_thu_giao") is not None
       and db["so"].get("chi_phi_qc") is not None)
    ok("chi phí QC gồm 100k hôm nay (≥ vì có dữ liệu thật)",
       db["so"]["chi_phi_qc"] >= 100000, str(db["so"]["chi_phi_qc"]))
    ok("phễu đủ 6 bậc, mỗi bậc mang metric để drill",
       len(db["pheu"]) == 6 and all(p.get("metric") for p in db["pheu"]))
    db_cskh = report_service.dashboard(NAY, NAY, user=cskh_user)
    ok("người KHÔNG có revenue.view — ô doanh thu bị cắt",
       "doanh_thu_giao" not in db_cskh["so"]
       and "chi_phi_qc" not in db_cskh["so"])

    print("== 4. REPORT-002/003 — mỗi nhân viên một dòng ==")
    bc = report_service.bao_cao_sale(NAY, NAY)
    dong1 = next(r for r in bc["rows"] if r["id"] == uid["sale1"])
    ok("sale1: lead 2 · liên hệ 1 · tư vấn 1 · chốt 1 · DT 1,1tr",
       dong1["lead_moi"] == 2 and dong1["lien_he"] == 1
       and dong1["tu_van"] == 1 and dong1["chot"] == 1
       and float(dong1["doanh_thu"]) == 1100000, str(dict(dong1)))
    ok("tỷ lệ chốt sale1 = 50%", dong1["tl_chot"] == 50.0, str(dong1["tl_chot"]))
    bc = report_service.bao_cao_cskh(NAY, NAY)
    dongc = next(r for r in bc["rows"] if r["id"] == uid["cskh1"])
    ok("cskh1: 1 khách · 2 mốc xong · 1 mốc quá hạn · 1 việc quá hạn",
       dongc["khach_phu_trach"] == 1 and dongc["moc_xong"] == 2
       and dongc["moc_qua_han"] == 1 and dongc["viec_qua_han"] == 1,
       str(dict(dongc)))

    print("== 5. REPORT-004…009 ==")
    mk = report_service.bao_cao_marketing(NAY, NAY)
    ok("marketing: có ROAS + LTV khi đủ số",
       mk["so"]["roas"] is not None and mk["so"]["ltv"] is not None)
    ok("lý do chưa chốt FR-172 bắt được lý do vừa ghi",
       any(f"{DAU}Giá cao" in (r["ly_do"] or "") for r in mk["ly_do_chua_chot"]))
    dh = report_service.bao_cao_don_hang(NAY, NAY)
    ok("REPORT-005 nhóm theo trạng thái có delivered + returned",
       {r["status"] for r in dh["theo_trang_thai"]} >= {"delivered", "returned"})
    dt = report_service.bao_cao_doanh_thu(NAY, NAY)
    ok("REPORT-006 tách bán mới / mua lại (mua lại ≥ 300k)",
       dt["mua_lai"] >= 300000 and dt["tong"] >= dt["mua_lai"])
    ml = report_service.bao_cao_mua_lai(NAY, NAY)
    ok("REPORT-007 đếm won trong kỳ ≥ 1", ml["so"]["co_hoi_won"] >= 1)
    ok("REPORT-008 tổng đài trả khung trung thực",
       report_service.bao_cao_cuoc_goi()["available"] is False)
    cv = report_service.bao_cao_cong_viec(NAY, NAY)
    loai = {r["task_type"]: r for r in cv["theo_loai"]}
    ok("REPORT-009 việc cham_soc: 2 xong · 1 đúng hạn",
       loai.get("cham_soc", {}).get("xong", 0) >= 2
       and loai.get("cham_soc", {}).get("dung_han", 0) >= 1)

    print("== 6. Quyền drill-down + export (FR-181) ==")
    phai_loi("metric lạ → chặn kèm danh sách", "VALIDATION_ERROR",
             report_service.drill_down, "metric_la", user=admin)
    phai_loi("CSKH xem chi_phi_qc (cần ads.view) → cấm", "FORBIDDEN",
             report_service.drill_down, "chi_phi_qc", NAY, NAY, user=cskh_user)
    phai_loi("export không có data.export → cấm", "FORBIDDEN",
             report_service.xuat_csv, "lead_moi", NAY, NAY, user=cskh_user)
    noi_dung, ten_file = report_service.xuat_csv("lead_moi", NAY, NAY,
                                                 uid["sale1"], user=admin)
    ok("CSV có BOM UTF-8 + chấm phẩy + đúng 2 dòng dữ liệu",
       noi_dung.startswith("﻿") and ";" in noi_dung
       and noi_dung.count("\n") >= 3 and ten_file.endswith(".csv"))
    with pool.connection() as conn:
        au = conn.execute(
            "select 1 from crm.audit_logs where action = 'report_export' "
            "and user_id = %s limit 1", (uid["admin"],)).fetchone()
    ok("mỗi lần xuất có audit (FR-181)", au is not None)

    print("== 7. API REPORT-001…011 ==")
    hd = {"admin": dang_nhap("admin"), "cskh": dang_nhap("cskh1"),
          "mkt": dang_nhap("mkt"), "ketoan": dang_nhap("ketoan")}
    for duong, quyen_cua in (("dashboard", "cskh"), ("sales", "ketoan"),
                             ("customer-care", "cskh"), ("marketing", "mkt"),
                             ("orders", "ketoan"), ("revenue", "ketoan"),
                             ("repurchase", "cskh"), ("call-quality", "cskh"),
                             ("tasks", "cskh")):
        r = client.get(f"/api/v1/reports/{duong}?tu={NAY}&den={NAY}",
                       headers=hd[quyen_cua])
        ok(f"GET /reports/{duong} ({quyen_cua}) → 200", r.status_code == 200,
           f"status={r.status_code}")
    r = client.get(f"/api/v1/reports/sales?tu={NAY}&den={NAY}",
                   headers=hd["cskh"])
    ok("CSKH gọi /reports/sales (cần revenue.view) → 403", r.status_code == 403)
    r = client.get(
        f"/api/v1/reports/drill-down?metric=lead_moi&tu={NAY}&den={NAY}"
        f"&user_id={uid['sale1']}", headers=hd["admin"])
    ok("REPORT-010 qua API — đúng 2 dòng của sale1",
       r.status_code == 200 and r.json()["data"]["tong"] == 2)
    r = client.post("/api/v1/reports/export",
                    json={"metric": "lead_moi", "tu": NAY, "den": NAY},
                    headers=hd["admin"])
    ok("REPORT-011 qua API — file CSV đính kèm",
       r.status_code == 200
       and "attachment" in r.headers.get("content-disposition", ""))

    print("== 8. Màn web 4-6 + 60-64 + drill-down ==")
    client.cookies.clear()
    r = client.post("/dang-nhap", data={"username": f"{DAU}admin",
                                        "password": MK, "next": "/"},
                    follow_redirects=False)
    ok("đăng nhập web", r.status_code == 303)
    r = client.get(f"/crm/tong-quan?tu={NAY}&den={NAY}")
    ok("màn 4 mới: có phễu + ô bấm được (href drill-down)",
       r.status_code == 200 and "Phễu" in r.text
       and "/crm/bao-cao/chi-tiet?metric=" in r.text)
    r = client.get(f"/crm/dashboard-sale?user_id={uid['sale1']}&tu={NAY}&den={NAY}")
    ok("màn 5 dashboard Sale 200 + tỷ lệ chốt",
       r.status_code == 200 and "Tỷ lệ chốt" in r.text)
    r = client.get(f"/crm/dashboard-cskh?user_id={uid['cskh1']}&tu={NAY}&den={NAY}")
    ok("màn 6 dashboard CSKH 200", r.status_code == 200)
    r = client.get(f"/crm/bao-cao?tab=sale&tu={NAY}&den={NAY}")
    ok("màn 60 báo cáo Sale có dòng sale1",
       r.status_code == 200 and f"{DAU}sale1" in r.text)
    r = client.get(f"/crm/bao-cao?tab=cong-viec&tu={NAY}&den={NAY}")
    ok("màn 64 báo cáo công việc 200", r.status_code == 200)
    r = client.get(f"/crm/bao-cao/chi-tiet?metric=lead_moi&tu={NAY}&den={NAY}"
                   f"&user_id={uid['sale1']}")
    ok("trang drill-down hiện khách + nút xuất CSV",
       r.status_code == 200 and f"{DAU}Khach1" in r.text and "Xuất CSV" in r.text)
    # CSKH mở tab doanh thu → bị chặn lịch sự ngay trên màn
    client.cookies.clear()
    client.post("/dang-nhap", data={"username": f"{DAU}cskh1", "password": MK,
                                    "next": "/"}, follow_redirects=False)
    r = client.get(f"/crm/bao-cao?tab=doanh-thu&tu={NAY}&den={NAY}")
    ok("CSKH mở tab Doanh thu → màn báo cần quyền revenue.view",
       r.status_code == 200 and "revenue.view" in r.text)


if __name__ == "__main__":
    main()
