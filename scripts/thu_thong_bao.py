"""Kiểm thử MÀN 3 — Trung tâm thông báo (NOTIFY-001…004).

Nghiệm thu đúng 11 loại trong "Danh sách màn hình CRM" mục 3, cộng các luật:
  * quét lại KHÔNG sinh trùng (dedupe_key)
  * đã đọc rồi thì không réo lại
  * chỉ xem/đánh dấu được thông báo CỦA MÌNH
  * tắt loại nào (NOTIFY-004) là nguồn bỏ qua ngay
  * nguồn nào hỏng không kéo sập 10 nguồn còn lại

Dữ liệu giả mang dấu `__tn3__`, dọn sạch đầu/cuối. KHÔNG gọi mạng.

Chạy:  python scripts/thu_thong_bao.py
Cần:   DB chạy + init_crm.sql bản có notifications + seed_auth.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core.errors import ApiError               # noqa: E402
from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import notification_repo as repo  # noqa: E402
from app.main import app                           # noqa: E402
from app.services import notification_service as tb  # noqa: E402

DAU = "__tn3__"
MK = "Tn3-test-1234"
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
    nguoi = f"(select id from crm.users where email like '{DAU}%')"
    khach = f"(select id from crm.customers where full_name like '{DAU}%')"
    conn.execute(f"delete from crm.notifications where user_id in {nguoi}")
    conn.execute(f"delete from crm.notification_settings where user_id in {nguoi}")
    conn.execute(f"delete from crm.tasks where customer_id in {khach}")
    conn.execute(f"delete from crm.clinical_escalations where customer_id in {khach}")
    conn.execute(
        f"delete from crm.order_status_history where order_id in "
        f"(select id from crm.orders where customer_id in {khach})")
    conn.execute(f"delete from crm.orders where customer_id in {khach}")
    conn.execute(f"delete from crm.customer_assignments where customer_id in {khach}")
    conn.execute(f"delete from crm.leads where customer_id in {khach}")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:  # noqa: PLR0915 — script nghiệm thu
    pool = get_pg_pool()
    gio = datetime.now(timezone.utc)
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vai in (("sale", "Sale"), ("cskh", "CSKH"), ("admin", "Admin")):
            uid[ten] = conn.execute(
                "insert into crm.users (name, email, username, password_hash, status, role_id) "
                "values (%s, %s, %s, %s, 'active', %s) returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]),
            ).fetchone()["id"]

        kh = conn.execute(
            "insert into crm.customers (full_name, primary_phone, status) "
            "values (%s, '0977111222', 'customer') returning id",
            (f"{DAU}KhachA",),
        ).fetchone()["id"]

        # --- nguồn 1: lead mới chưa liên hệ (của sale) ---
        pipe = conn.execute(
            "select p.id as pid, s.id as sid from crm.pipelines p "
            "join crm.pipeline_stages s on s.pipeline_id = p.id "
            "order by s.sort_order limit 1").fetchone()
        lead_id = conn.execute(
            "insert into crm.leads (customer_id, pipeline_id, stage_id, owner_id, "
            "next_action_at) values (%s, %s, %s, %s, %s) returning id",
            (kh, pipe["pid"], pipe["sid"], uid["sale"], gio - timedelta(hours=2)),
        ).fetchone()["id"]

        # --- nguồn 2+3: việc sắp đến hạn + việc quá hạn (của sale) ---
        viec_qh = conn.execute(
            "insert into crm.tasks (customer_id, assigned_to, task_type, title, "
            "due_at, status) values (%s, %s, 'goi', %s, %s, 'open') returning id",
            (kh, uid["sale"], f"{DAU}Gọi lại khách", gio - timedelta(hours=3)),
        ).fetchone()["id"]
        viec_sap = conn.execute(
            "insert into crm.tasks (customer_id, assigned_to, task_type, title, "
            "due_at, status) values (%s, %s, 'cham_soc', %s, %s, 'open') returning id",
            (kh, uid["sale"], f"{DAU}Chăm ngày 4", gio + timedelta(hours=3)),
        ).fetchone()["id"]

        # --- nguồn 5+6: ca lâm sàng (phản ứng thuốc / chuyển chuyên môn) ---
        ca_pu = conn.execute(
            "insert into crm.clinical_escalations (customer_id, source, reason, "
            "risk_level, status, assigned_to) values (%s, 'medication_risk', %s, "
            "'high', 'pending', %s) returning id",
            (kh, f"{DAU}Khách báo buồn nôn sau uống", uid["cskh"]),
        ).fetchone()["id"]
        ca_cm = conn.execute(
            "insert into crm.clinical_escalations (customer_id, source, reason, "
            "risk_level, status, assigned_to) values (%s, 'safety_check', %s, "
            "'critical', 'pending', %s) returning id",
            (kh, f"{DAU}Cờ đỏ: đi ngoài phân đen", uid["cskh"]),
        ).fetchone()["id"]

        # --- nguồn 7+8: đơn giao thành công + đơn hoàn ---
        conn.execute(
            "insert into crm.customer_assignments (customer_id, user_id, assignment_type) "
            "values (%s, %s, 'sale')", (kh, uid["sale"]))
        don_giao = conn.execute(
            "insert into crm.orders (customer_id, status, total_amount, delivered_at, "
            "sale_owner_id) values (%s, 'delivered', 750000, now(), %s) returning id",
            (kh, uid["sale"]),
        ).fetchone()["id"]
        don_hoan = conn.execute(
            "insert into crm.orders (customer_id, status, total_amount, sale_owner_id) "
            "values (%s, 'returned', 500000, %s) returning id",
            (kh, uid["sale"]),
        ).fetchone()["id"]

    print("== 1. Quét 11 nguồn — sinh thông báo đúng người ==")
    kq = tb.quet_tat_ca()
    ok("quét chạy đủ 11 loại, không nguồn nào ném lỗi",
       set(kq) == set(tb.LOAI), f"thiếu/thừa: {set(tb.LOAI) ^ set(kq)}")

    def cua(user_key: str, loai: str) -> list[dict]:
        rows, _ = repo.list_notifications(user_id=uid[user_key], type_=loai, limit=50)
        return rows

    ok("lead mới -> báo Sale đang giữ lead",
       any(r["related_id"] == lead_id for r in cua("sale", "lead_moi")))
    ok("việc quá hạn -> báo người phụ trách, ưu tiên cao",
       any(r["related_id"] == viec_qh and r["priority"] == "high"
           for r in cua("sale", "viec_qua_han")))
    ok("việc sắp đến hạn (trong 24h) -> báo riêng loại khác",
       any(r["related_id"] == viec_sap for r in cua("sale", "viec_sap_den_han")))
    ok("khách cần gọi lại (lead quá hẹn) -> báo Sale",
       any(r["related_id"] == lead_id for r in cua("sale", "khach_can_goi_lai")))
    ok("khách có phản ứng -> báo người xử lý ca, mức urgent",
       any(r["related_id"] == ca_pu and r["priority"] == "urgent"
           for r in cua("cskh", "khach_co_phan_ung")))
    ok("khách cần chuyển chuyên môn -> loại riêng",
       any(r["related_id"] == ca_cm
           for r in cua("cskh", "khach_can_chuyen_chuyen_mon")))
    ok("đơn giao thành công -> báo Sale",
       any(r["related_id"] == don_giao for r in cua("sale", "don_giao_thanh_cong")))
    ok("đơn hoàn -> báo Sale",
       any(r["related_id"] == don_hoan for r in cua("sale", "don_hoan")))
    ok("mọi thông báo đều có link mở màn liên quan",
       all(r["link"] for r in repo.list_notifications(user_id=uid["sale"], limit=99)[0]))

    print("== 2. Dedupe: quét lại KHÔNG sinh trùng ==")
    truoc = repo.list_notifications(user_id=uid["sale"], limit=99)[1]
    tb.quet_tat_ca()
    sau = repo.list_notifications(user_id=uid["sale"], limit=99)[1]
    ok("quét lượt 2 không đẻ thêm dòng nào", truoc == sau, f"{truoc} -> {sau}")

    print("== 3. Đã đọc rồi thì không réo lại ==")
    tin = cua("sale", "viec_qua_han")[0]
    repo.danh_dau_doc(tin["id"], uid["sale"])
    tb.quet_tat_ca()
    lai = repo.get(tin["id"], uid["sale"])
    ok("thông báo đã đọc vẫn ở trạng thái đã đọc sau khi quét lại",
       lai["read_at"] is not None)
    ok("không sinh bản sao chưa đọc cho cùng sự việc",
       len([r for r in cua("sale", "viec_qua_han")
            if r["related_id"] == viec_qh]) == 1)

    print("== 4. NOTIFY-004: tắt loại nào là ngừng nhận loại đó ==")
    with pool.connection() as conn:
        conn.execute(f"delete from crm.notifications where user_id = {uid['sale']} "
                     "and type = 'lead_moi'")
    tb.dat_cai_dat({"lead_moi": False}, {"sub": str(uid["sale"])})
    tb.quet_tat_ca()
    ok("đã TẮT lead_moi -> quét không sinh lại loại đó", not cua("sale", "lead_moi"))
    ok("các loại khác vẫn nhận bình thường", bool(cua("sale", "khach_can_goi_lai")))
    cd = tb.lay_cai_dat({"sub": str(uid["sale"])})
    ok("cài đặt trả đủ 11 loại kèm nhãn", len(cd["items"]) == 11
       and any(c["type"] == "lead_moi" and c["enabled"] is False for c in cd["items"]))
    phai_loi("đặt loại lạ -> VALIDATION_ERROR", "VALIDATION_ERROR",
             tb.dat_cai_dat, {"loai_bia_dat": True}, {"sub": str(uid["sale"])})
    tb.dat_cai_dat({"lead_moi": True}, {"sub": str(uid["sale"])})

    print("== 5. Một nguồn hỏng KHÔNG kéo sập cả lượt quét ==")
    goc = tb._quet_loi_dong_bo

    def no_loi(_tat):
        raise RuntimeError("giả lập nguồn hỏng")

    tb._quet_loi_dong_bo = no_loi
    try:
        kq2 = tb.quet_tat_ca()
        ok("nguồn lỗi trả 0, các nguồn khác vẫn chạy",
           kq2["loi_dong_bo"] == 0 and set(kq2) == set(tb.LOAI))
    finally:
        tb._quet_loi_dong_bo = goc

    print("== 6. API NOTIFY-001…004 ==")
    web = TestClient(app)

    def dang_nhap(u: str) -> dict:
        r = web.post("/api/v1/auth/login", json={"username": u, "password": MK})
        assert r.status_code == 200, r.text[:200]
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    hs = dang_nhap(f"{DAU}sale")
    hc = dang_nhap(f"{DAU}cskh")

    r = web.get("/api/v1/notifications")
    ok("chưa đăng nhập -> 401", r.status_code == 401, str(r.status_code))
    r = web.get("/api/v1/notifications", headers=hs)
    d = r.json()["data"]
    ok("NOTIFY-001 trả danh sách + số chưa đọc", r.status_code == 200
       and d["pagination"]["total"] >= 5 and d["chua_doc"]["tong"] >= 1, r.text[:200])
    ok("NOTIFY-001 chỉ trả thông báo CỦA MÌNH",
       all(x["user_id"] == uid["sale"] for x in d["items"]))
    r = web.get("/api/v1/notifications?chua_doc=true", headers=hs)
    ok("lọc chưa đọc",
       all(x["read_at"] is None for x in r.json()["data"]["items"]))
    r = web.get("/api/v1/notifications?type=don_hoan", headers=hs)
    ok("lọc theo loại",
       all(x["type"] == "don_hoan" for x in r.json()["data"]["items"]))

    tin_cskh = cua("cskh", "khach_co_phan_ung")[0]
    r = web.post(f"/api/v1/notifications/{tin_cskh['id']}/read", headers=hs)
    ok("NOTIFY-002 đọc thông báo của NGƯỜI KHÁC -> 404", r.status_code == 404)
    r = web.post(f"/api/v1/notifications/{tin_cskh['id']}/read", headers=hc)
    ok("NOTIFY-002 chủ nhân đánh dấu được", r.status_code == 200
       and r.json()["data"]["read_at"] is not None, r.text[:200])

    r = web.post("/api/v1/notifications/read-all", headers=hs)
    ok("NOTIFY-003 đánh dấu tất cả đã đọc", r.status_code == 200
       and r.json()["data"]["da_danh_dau"] >= 1, r.text[:200])
    ok("sau read-all thì số chưa đọc về 0",
       repo.dem_chua_doc(uid["sale"])["tong"] == 0)

    r = web.get("/api/v1/notification-settings", headers=hs)
    ok("lấy cài đặt qua API đủ 11 loại",
       r.status_code == 200 and len(r.json()["data"]["items"]) == 11)
    r = web.put("/api/v1/notification-settings", headers=hs,
                json={"settings": {"don_hoan": False}})
    ok("NOTIFY-004 lưu qua API", r.status_code == 200
       and any(c["type"] == "don_hoan" and not c["enabled"]
               for c in r.json()["data"]["items"]), r.text[:200])
    r = web.put("/api/v1/notification-settings", headers=hs,
                json={"settings": {"khong_co_that": True}})
    ok("NOTIFY-004 mã lạ -> 422", r.status_code == 422)

    print("== 7. Màn 3 (web) + chuông ==")
    web.post("/dang-nhap", data={"username": f"{DAU}cskh", "password": MK})
    r = web.get("/crm/thong-bao")
    ok("màn 3 trả HTML + có tên loại", r.status_code == 200
       and "Trung tâm thông báo" in r.text and "Khách có phản ứng" in r.text)
    ok("màn 3 có khối cài đặt NOTIFY-004", "Cài đặt thông báo của tôi" in r.text)
    ok("chuông hiện trên thanh trên", 'class="bell"' in r.text)
    r = web.post("/crm/thong-bao/doc-het", follow_redirects=False)
    ok("web: đánh dấu tất cả đã đọc -> 303 về màn 3", r.status_code == 303)
    ok("CSKH sau doc-het còn 0 chưa đọc",
       repo.dem_chua_doc(uid["cskh"])["tong"] == 0)
    r = web.post("/crm/thong-bao/cai-dat", data={"lead_moi": "on"},
                 follow_redirects=False)
    ok("web: lưu cài đặt (ô không tick = TẮT)", r.status_code == 303)
    cd = {c["type"]: c["enabled"]
          for c in tb.lay_cai_dat({"sub": str(uid["cskh"])})["items"]}
    ok("ô tick -> bật, 10 ô còn lại -> tắt",
       cd["lead_moi"] is True and cd["don_hoan"] is False)

    print("== 8. Dọn thông báo cũ đã đọc ==")
    with pool.connection() as conn:
        conn.execute(
            "update crm.notifications set read_at = now() - interval '90 days' "
            "where user_id = %s", (uid["sale"],))
        conn.execute(
            "insert into crm.notifications (user_id, type, title, dedupe_key) "
            "values (%s, 'lead_moi', %s, 'giu-lai-chua-doc')",
            (uid["sale"], f"{DAU}Chưa đọc nhưng cũ"))
        conn.execute(
            "update crm.notifications set created_at = now() - interval '200 days' "
            "where dedupe_key = 'giu-lai-chua-doc'")
    repo.don_rac(60)
    con = repo.list_notifications(user_id=uid["sale"], limit=99)[0]
    ok("xoá thông báo ĐÃ ĐỌC quá 60 ngày",
       not any(r["read_at"] is not None for r in con))
    ok("CHƯA đọc thì không xoá dù cũ 200 ngày",
       any(r["dedupe_key"] == "giu-lai-chua-doc" for r in con))

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKẾT QUẢ: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
