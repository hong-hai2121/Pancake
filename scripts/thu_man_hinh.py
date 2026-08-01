"""Kiểm thử MÀN 9 (hồ sơ 360°) · MÀN 10 (gộp trùng) · MÀN 22 (chi tiết đơn).

Đây là đợt "trả nợ giao diện" cho các lát đã xong backend: dựng một khách giả
có đủ dữ liệu của B1…B9 (hội thoại + tin nhắn, triệu chứng, thuốc, sàng lọc,
liệu trình, đơn, bàn giao, kế hoạch chăm, quy nguồn ad, audit) rồi mở từng tab
kiểm tra dữ liệu CÓ LÊN MÀN, chứ không chỉ trả 200.

Dữ liệu giả mang dấu `__tmh__`, dọn sạch đầu/cuối. KHÔNG gọi mạng.

Chạy:  python scripts/thu_man_hinh.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.main import app                           # noqa: E402
from app.web.views.profile import TABS             # noqa: E402

DAU = "__tmh__"
MK = "Tmh-test-1234"
PAGE_GIA = "777000111000222"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    kh = f"(select id from crm.customers where full_name like '{DAU}%')"
    conn.execute(f"delete from crm.messages where conversation_id in "
                 f"(select id from crm.conversations where customer_id in {kh})")
    conn.execute(f"delete from crm.conversations where customer_id in {kh}")
    conn.execute(f"delete from crm.conversations where page_id in "
                 f"(select id from crm.pages where external_page_id = '{PAGE_GIA}')")
    conn.execute(f"delete from crm.care_plan_steps where care_plan_id in "
                 f"(select id from crm.care_plans where customer_id in {kh})")
    conn.execute(f"delete from crm.care_plans where customer_id in {kh}")
    conn.execute(f"delete from crm.handovers where customer_id in {kh}")
    conn.execute(f"delete from crm.tasks where customer_id in {kh}")
    conn.execute(f"delete from crm.clinical_escalations where customer_id in {kh}")
    conn.execute(f"delete from crm.safety_screenings where customer_id in {kh}")
    conn.execute(f"delete from crm.current_medications where customer_id in {kh}")
    conn.execute(f"delete from crm.examinations where customer_id in {kh}")
    conn.execute(f"delete from crm.customer_symptoms where customer_id in {kh}")
    conn.execute(f"delete from crm.customer_treatment_items where customer_treatment_id in "
                 f"(select id from crm.customer_treatments where customer_id in {kh})")
    conn.execute(f"delete from crm.customer_treatments where customer_id in {kh}")
    conn.execute(f"delete from crm.repurchase_opportunities where customer_id in {kh}")
    conn.execute(f"delete from crm.lead_attributions where customer_id in {kh}")
    conn.execute(f"delete from crm.order_items where order_id in "
                 f"(select id from crm.orders where customer_id in {kh})")
    conn.execute(f"delete from crm.order_status_history where order_id in "
                 f"(select id from crm.orders where customer_id in {kh})")
    conn.execute(f"delete from crm.orders where customer_id in {kh}")
    conn.execute(f"delete from crm.customer_assignments where customer_id in {kh}")
    conn.execute(f"delete from crm.customer_identities where customer_id in {kh}")
    conn.execute(f"delete from crm.leads where customer_id in {kh}")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.pages where external_page_id = '{PAGE_GIA}'")
    conn.execute(f"delete from crm.products where product_code like '{DAU}%'")
    conn.execute(f"delete from crm.treatment_templates where template_code like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:  # noqa: PLR0915 — script nghiệm thu
    pool = get_pg_pool()
    gio = datetime.now(timezone.utc)
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vai in (("admin", "Admin"), ("sale", "Sale"), ("cskh", "CSKH")):
            uid[ten] = conn.execute(
                "insert into crm.users (name, email, username, password_hash, status, role_id) "
                "values (%s, %s, %s, %s, 'active', %s) returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]),
            ).fetchone()["id"]

        # --- khách chính, có đủ mọi thứ ---
        kh = conn.execute(
            "insert into crm.customers (full_name, primary_phone, status, safety_flag) "
            "values (%s, '0966111222', 'treating', 'yellow') returning id",
            (f"{DAU}KhachDu",),
        ).fetchone()["id"]
        for vai, u in (("sale", uid["sale"]), ("cskh", uid["cskh"])):
            conn.execute(
                "insert into crm.customer_assignments (customer_id, user_id, assignment_type) "
                "values (%s, %s, %s)", (kh, u, vai))

        # lead
        pipe = conn.execute(
            "select p.id as pid, s.id as sid from crm.pipelines p "
            "join crm.pipeline_stages s on s.pipeline_id = p.id "
            "order by s.sort_order limit 1").fetchone()
        conn.execute(
            "insert into crm.leads (customer_id, pipeline_id, stage_id, owner_id, "
            "temperature, next_action_at) values (%s, %s, %s, %s, 'nong', %s)",
            (kh, pipe["pid"], pipe["sid"], uid["sale"], gio + timedelta(days=1)))

        # hội thoại + tin nhắn (FR-012)
        page = conn.execute(
            "insert into crm.pages (platform, external_page_id, name) "
            f"values ('facebook', '{PAGE_GIA}', '{DAU}Page') returning id"
        ).fetchone()["id"]
        conv = conn.execute(
            "insert into crm.conversations (customer_id, page_id, "
            "external_conversation_id, last_message_at, snippet, message_count) "
            "values (%s, %s, %s, %s, %s, 2) returning id",
            (kh, page, f"{PAGE_GIA}_tmh1", gio, f"{DAU}xin chao shop"),
        ).fetchone()["id"]
        for i, (ai, noi) in enumerate([
                ("customer", f"{DAU}em bi dau da day"),
                ("agent", f"{DAU}chao anh, em tu van nhe")]):
            conn.execute(
                "insert into crm.messages (conversation_id, external_message_id, "
                "sender_type, sender_name, content, msg_type, sent_at) "
                "values (%s, %s, %s, %s, %s, 'text', %s)",
                (conv, f"tmh-m{i}", ai, f"{DAU}nguoi{i}", noi,
                 gio - timedelta(minutes=10 - i)))

        # hồ sơ tư vấn B5
        tc = conn.execute("select id from crm.symptoms order by id limit 1").fetchone()
        if tc:
            conn.execute(
                "insert into crm.customer_symptoms (customer_id, symptom_id, severity, "
                "frequency) values (%s, %s, 7, 'often')", (kh, tc["id"]))
        conn.execute(
            "insert into crm.examinations (customer_id, exam_type, exam_date, "
            "facility, conclusion) values (%s, 'noi_soi', current_date, %s, %s)",
            (kh, f"{DAU}BV Bach Mai", f"{DAU}Viem hang vi HP duong tinh"))
        conn.execute(
            "insert into crm.current_medications (customer_id, name, dosage) "
            "values (%s, %s, '20mg sang')", (kh, f"{DAU}Omeprazol"))
        conn.execute(
            "insert into crm.safety_screenings (customer_id, screening_type, value, "
            "risk_level) values (%s, 'sut_can', %s, 'high')",
            (kh, f"{DAU}sut 5kg/2 thang"))
        conn.execute(
            "insert into crm.clinical_escalations (customer_id, source, reason, "
            "risk_level, status) values (%s, 'safety_check', %s, 'high', 'pending')",
            (kh, f"{DAU}Co dau hieu canh bao"))

        # liệu trình B6
        sp = conn.execute(
            "insert into crm.products (product_code, name, price, status) "
            f"values ('{DAU}SP', '{DAU}Da day an', 350000, 'active') returning id"
        ).fetchone()["id"]
        mau = conn.execute(
            "insert into crm.treatment_templates (template_code, name, status) "
            f"values ('{DAU}LT', '{DAU}Lieu trinh 1 thang', 'active') returning id"
        ).fetchone()["id"]
        lt = conn.execute(
            "insert into crm.customer_treatments (customer_id, template_id, status, "
            "start_date) values (%s, %s, 'active', current_date) returning id",
            (kh, mau),
        ).fetchone()["id"]
        conn.execute(
            "insert into crm.customer_treatment_items (customer_treatment_id, "
            "product_id, quantity, dose_text) values (%s, %s, 2, %s)",
            (lt, sp, f"{DAU}Sang 2 vien sau an"))

        # đơn B7 + dòng hàng + lịch sử
        don = conn.execute(
            "insert into crm.orders (customer_id, status, order_type, total_amount, "
            "sale_owner_id, delivered_at, external_order_id) "
            "values (%s, 'delivered', 'new', 700000, %s, %s, %s) returning id",
            (kh, uid["sale"], gio, f"{DAU}DH01"),
        ).fetchone()["id"]
        conn.execute(
            "insert into crm.order_items (order_id, product_id, quantity, unit_price, "
            "line_total) values (%s, %s, 2, 350000, 700000)", (don, sp))
        conn.execute(
            "insert into crm.order_status_history (order_id, from_status, to_status, "
            "changed_by, reason) values (%s, 'confirmed', 'delivered', %s, %s)",
            (don, uid["sale"], f"{DAU}giao xong"))
        conn.execute("update crm.customer_treatments set order_id = %s where id = %s",
                     (don, lt))

        # bàn giao B8 + kế hoạch chăm B9
        cp = conn.execute(
            "insert into crm.care_plans (customer_id, customer_treatment_id, owner_id) "
            "values (%s, %s, %s) returning id", (kh, lt, uid["cskh"]),
        ).fetchone()["id"]
        conn.execute(
            "insert into crm.care_plan_steps (care_plan_id, step_code, planned_at, "
            "status) values (%s, 'CS01', %s, 'pending')", (cp, gio))
        conn.execute(
            "insert into crm.handovers (customer_id, order_id, care_plan_id, "
            "sale_user_id, cskh_user_id, status, is_complete) "
            "values (%s, %s, %s, %s, %s, 'accepted', true)",
            (kh, don, cp, uid["sale"], uid["cskh"]))

        # cơ hội mua lại + quy nguồn
        conn.execute(
            "insert into crm.repurchase_opportunities (customer_id, next_template_id, "
            "owner_id, expected_close_date, expected_value, stage) "
            "values (%s, %s, %s, current_date, 700000, 'identified')",
            (kh, mau, uid["cskh"]))
        conn.execute(
            "insert into crm.lead_attributions (customer_id, touch_type, "
            "external_ad_id, source, utm, attributed_at) "
            "values (%s, 'first', %s, 'pancake_pos', %s::jsonb, now())",
            (kh, f"{DAU}AD01", '{"campaign": "' + DAU + 'chien-dich"}'))
        conn.execute(
            "insert into crm.audit_logs (user_id, action, object_type, object_id, "
            "old_value, new_value) values (%s, 'customer_update', 'customers', %s, "
            "'{\"status\": \"new\"}'::jsonb, '{\"status\": \"treating\"}'::jsonb)",
            (uid["admin"], kh))
        conn.execute(
            "insert into crm.tasks (customer_id, assigned_to, task_type, title, "
            "due_at, status, related_type, related_id) "
            "values (%s, %s, 'cham_soc', %s, %s, 'open', 'order', %s)",
            (kh, uid["cskh"], f"{DAU}Goi xac nhan don", gio + timedelta(days=1), don))

        # --- 2 khách TRÙNG số điện thoại (cho màn 10) ---
        trung = []
        for i in (1, 2):
            trung.append(conn.execute(
                "insert into crm.customers (full_name, primary_phone, status) "
                "values (%s, '0955000111', 'new') returning id",
                (f"{DAU}KhachTrung{i}",),
            ).fetchone()["id"])

    web = TestClient(app)

    def dang_nhap(u: str) -> None:
        r = web.post("/dang-nhap", data={"username": u, "password": MK},
                     follow_redirects=False)
        assert r.status_code == 303, r.status_code

    dang_nhap(f"{DAU}admin")

    print("== 1. Màn 9 — mở đủ 9 tab ==")
    for ma, nhan in TABS:
        r = web.get(f"/crm/khach-hang/{kh}?tab={ma}")
        ok(f"tab {ma} ({nhan}) trả 200", r.status_code == 200, str(r.status_code))

    print("== 2. Màn 9 — dữ liệu THẬT lên đúng tab ==")
    r = web.get(f"/crm/khach-hang/{kh}")
    ok("đầu hồ sơ có tên + cờ vàng + người phụ trách",
       f"{DAU}KhachDu" in r.text and "Cờ vàng" in r.text
       and f"{DAU}sale" in r.text, r.text[:0])
    ok("tổng quan: cảnh báo an toàn hiện đỏ", "Cảnh báo an toàn" in r.text)
    ok("tổng quan: việc tiếp theo lên bảng", f"{DAU}Goi xac nhan don" in r.text)

    r = web.get(f"/crm/khach-hang/{kh}?tab=hoi-thoai")
    ok("tab hội thoại: có dòng hội thoại + số tin đã lưu",
       f"{DAU}xin chao shop" in r.text and "2/2" in r.text)
    r = web.get(f"/crm/khach-hang/{kh}?tab=hoi-thoai&conv={conv}")
    ok("khung chat hiện NỘI DUNG tin nhắn (FR-012)",
       f"{DAU}em bi dau da day" in r.text and "Nội dung hội thoại" in r.text)

    r = web.get(f"/crm/khach-hang/{kh}?tab=tu-van")
    ok("tab tư vấn: kết quả nội soi + thuốc + sàng lọc + ca chuyên môn",
       f"{DAU}Viem hang vi" in r.text and f"{DAU}Omeprazol" in r.text
       and f"{DAU}sut 5kg" in r.text and f"{DAU}Co dau hieu" in r.text)

    r = web.get(f"/crm/khach-hang/{kh}?tab=lieu-trinh")
    ok("tab liệu trình: tên mẫu + sản phẩm + cách dùng",
       f"{DAU}Lieu trinh 1 thang" in r.text and f"{DAU}Da day an" in r.text
       and f"{DAU}Sang 2 vien" in r.text)

    r = web.get(f"/crm/khach-hang/{kh}?tab=don-hang")
    ok("tab đơn hàng: có đơn + link sang chi tiết",
       f'href="/crm/don-hang/{don}"' in r.text and "700.000" in r.text)

    r = web.get(f"/crm/khach-hang/{kh}?tab=cham-soc")
    ok("tab chăm sóc: phiếu bàn giao + kế hoạch chăm + mốc CS01",
       "Phiếu bàn giao" in r.text and "CS01" in r.text)
    ok("tab chăm sóc: cơ hội mua lại", f"{DAU}Lieu trinh 1 thang" in r.text)

    r = web.get(f"/crm/khach-hang/{kh}?tab=marketing")
    ok("tab marketing: quy nguồn first touch + UTM",
       f"{DAU}AD01" in r.text and f"{DAU}chien-dich" in r.text)

    r = web.get(f"/crm/khach-hang/{kh}?tab=lich-su")
    ok("tab lịch sử: audit cũ→mới của khách",
       "customer_update" in r.text and "treating" in r.text)

    r = web.get(f"/crm/khach-hang/{kh}?tab=cuoc-goi")
    ok("tab cuộc gọi: báo rõ thuộc C-MVP3 chứ không để trống",
       "C-MVP3" in r.text)

    r = web.get("/crm/khach-hang/99999999")
    ok("khách không tồn tại -> 404", r.status_code == 404)

    print("== 3. Màn 8 nối sang hồ sơ 360° ==")
    r = web.get(f"/crm/khach-hang?q={DAU}KhachDu")
    ok("danh sách khách có link mở hồ sơ",
       f'href="/crm/khach-hang/{kh}"' in r.text)
    ok("có lối vào màn 10 gộp trùng", "/crm/khach-hang/gop-trung" in r.text)

    print("== 4. Màn 22 — chi tiết đơn ==")
    r = web.get(f"/crm/don-hang/{don}")
    ok("mở đơn 200 + tên khách + link về hồ sơ",
       r.status_code == 200 and f"{DAU}KhachDu" in r.text
       and f'href="/crm/khach-hang/{kh}"' in r.text, str(r.status_code))
    ok("dòng hàng lên bảng", f"{DAU}Da day an" in r.text and "700.000" in r.text)
    ok("lịch sử trạng thái confirmed → delivered",
       "confirmed" in r.text and f"{DAU}giao xong" in r.text)
    ok("liệu trình liên quan", f"{DAU}Lieu trinh 1 thang" in r.text)
    ok("công việc liên quan", f"{DAU}Goi xac nhan don" in r.text)
    ok("nguồn quảng cáo", f"{DAU}AD01" in r.text)
    ok("nút mở phiếu bàn giao", "/crm/ban-giao/" in r.text)
    r = web.get("/crm/don-hang/99999999")
    ok("đơn không tồn tại -> 404", r.status_code == 404)
    r = web.get("/crm/don-hang")
    ok("màn 21 có link Chi tiết", "Chi tiết</a>" in r.text)

    print("== 5. Màn 10 — dò trùng + gộp ==")
    r = web.get("/crm/khach-hang/gop-trung")
    ok("màn 10 mở 200 và bắt được cặp trùng SĐT",
       r.status_code == 200 and f"{DAU}KhachTrung1" in r.text
       and "0955000111" in r.text, str(r.status_code))
    ok("có nút chọn hồ sơ chính", 'name="chinh"' in r.text)

    dang_nhap(f"{DAU}cskh")   # CSKH có customer.edit -> gộp được
    r = web.post("/crm/gop-trung",
                 data={"chinh": str(trung[0]), "ids": [str(x) for x in trung]},
                 follow_redirects=False)
    ok("gộp trả 303 về màn 10", r.status_code == 303, str(r.status_code))
    with pool.connection() as conn:
        tt = {x["id"]: x["status"] for x in conn.execute(
            "select id, status from crm.customers where id = any(%s)",
            (trung,)).fetchall()}
    ok("hồ sơ phụ chuyển 'merged', KHÔNG xoá",
       tt.get(trung[1]) == "merged" and trung[1] in tt, str(tt))
    ok("hồ sơ chính giữ nguyên trạng thái", tt.get(trung[0]) != "merged")
    r = web.get("/crm/khach-hang/gop-trung")
    ok("gộp xong thì cặp đó không còn trong danh sách nghi trùng",
       f"{DAU}KhachTrung1" not in r.text)

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKẾT QUẢ: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
