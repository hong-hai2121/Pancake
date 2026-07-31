"""Kiểm thử B1 — khách hàng 360°: chuẩn hoá SĐT, chống trùng 4 bậc (FR-011),
tạo thủ công (FR-020), gộp (FR-022), tag (FR-023), phân công, API.

Chạy:  python scripts/thu_b1.py
Dữ liệu test mang dấu __b1__, tự dọn trước + sau.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core.config import settings               # noqa: E402
from app.core.errors import ApiError               # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.main import app                           # noqa: E402
from app.services import customer_service          # noqa: E402
from app.services.phone import normalize_phone     # noqa: E402

DAU = "__b1__"
PASS = FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def phai_loi(ten: str, ma: str, fn, *a, **kw) -> None:
    try:
        fn(*a, **kw)
        ok(ten, False, "không raise")
    except ApiError as e:
        ok(ten, e.code == ma, f"raise {e.code} thay vì {ma}")


def don_dep(conn) -> None:
    conn.execute(f"delete from crm.orders where external_order_id like '{DAU}%'")
    conn.execute(f"delete from crm.leads where source like '{DAU}%'")
    conn.execute(
        f"""delete from crm.customer_identities where customer_id in
            (select id from crm.customers where full_name like '{DAU}%' or source like '{DAU}%')"""
    )
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%' or source like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")
    conn.execute(f"delete from crm.tags where name like '{DAU}%'")
    conn.execute(f"delete from crm.pages where name like '{DAU}%'")


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)
        role_sale = conn.execute("select id from crm.roles where name='Sale'").fetchone()["id"]
        sale1 = conn.execute(
            "insert into crm.users (name,email,status,role_id) values (%s,%s,'active',%s) returning id",
            (f"{DAU}Sale1", f"{DAU}s1@x.com", role_sale),
        ).fetchone()["id"]
        sale2 = conn.execute(
            "insert into crm.users (name,email,status,role_id) values (%s,%s,'active',%s) returning id",
            (f"{DAU}Sale2", f"{DAU}s2@x.com", role_sale),
        ).fetchone()["id"]
        page = conn.execute(
            "insert into crm.pages (external_page_id,name,platform) values (%s,%s,'facebook') returning id",
            (f"{DAU}pg", f"{DAU}Page"),
        ).fetchone()["id"]

    print("== 1. Chuẩn hoá SĐT ==")
    for vao, mong in [
        ("+84 90 123 4567", "0901234567"), ("84901234567", "0901234567"),
        ("090.123.4567", "0901234567"), ("0901234567", "0901234567"),
        ("901234567", "0901234567"), ("abc", None), ("", None), (None, None),
        ("02439999999", "02439999999"),
    ]:
        ok(f"normalize({vao!r}) = {mong!r}", normalize_phone(vao) == mong,
           f"được {normalize_phone(vao)!r}")

    print("== 2. Tạo thủ công (FR-020) ==")
    phai_loi("thiếu tên -> chặn", "MISSING_REQUIRED_DATA",
             customer_service.create_customer, {"source": f"{DAU}fb"})
    phai_loi("thiếu SĐT lẫn định danh -> chặn", "MISSING_REQUIRED_DATA",
             customer_service.create_customer,
             {"full_name": f"{DAU}A", "source": f"{DAU}fb"})
    phai_loi("SĐT rác -> VALIDATION", "VALIDATION_ERROR",
             customer_service.create_customer,
             {"full_name": f"{DAU}A", "primary_phone": "xyz", "source": f"{DAU}fb"})
    kh1 = customer_service.create_customer({
        "full_name": f"{DAU}Anh Ba", "primary_phone": "+84 90 111 2233",
        "source": f"{DAU}fb", "owner_id": sale1,
    })
    ok("tạo OK, SĐT đã chuẩn hoá", kh1["primary_phone"] == "0901112233")
    ok("có người phụ trách sale", (kh1["nguoi_phu_trach"] or [{}])[0].get("user_id") == sale1)
    phai_loi("trùng SĐT không force -> DUPLICATE_CUSTOMER", "DUPLICATE_CUSTOMER",
             customer_service.create_customer,
             {"full_name": f"{DAU}Chi Tu", "primary_phone": "0901112233",
              "source": f"{DAU}fb"})
    kh2 = customer_service.create_customer(
        {"full_name": f"{DAU}Chi Tu", "primary_phone": "0901112233",
         "source": f"{DAU}fb"},
        force=True,
    )
    ok("force=true tạo được (nhà chung số)", kh2["id"] != kh1["id"])

    print("== 3. Chống trùng 4 bậc (FR-011) ==")
    kh3, tao = customer_service.upsert_from_source(
        platform="facebook", name=f"{DAU}Khach FB", phone="0905556677",
        external_customer_id=f"{DAU}ext1", psid=f"{DAU}psid1", page_id=page,
        external_conversation_id=f"{DAU}conv1", source=f"{DAU}pancake",
    )
    ok("lần đầu: tạo mới + có lead tự động", tao)
    kh3b, tao2 = customer_service.upsert_from_source(
        platform="facebook", external_customer_id=f"{DAU}ext1",
        source=f"{DAU}pancake",
    )
    ok("bậc 1 external_id: nhận ra, không tạo trùng",
       not tao2 and kh3b["id"] == kh3["id"])
    kh3c, tao3 = customer_service.upsert_from_source(
        platform="facebook", psid=f"{DAU}psid1", page_id=page, source=f"{DAU}pancake",
    )
    ok("bậc 2 PSID: nhận ra", not tao3 and kh3c["id"] == kh3["id"])
    kh3d, tao4 = customer_service.upsert_from_source(
        platform="facebook", phone="0905556677", source=f"{DAU}pancake",
    )
    ok("bậc 3 SĐT (1 khách): nhận ra", not tao4 and kh3d["id"] == kh3["id"])
    khX, taoX = customer_service.upsert_from_source(
        platform="facebook", phone="0901112233", source=f"{DAU}pancake",
    )
    ok("SĐT 2 khách chung -> KHÔNG tự nhận, tạo mới", taoX)
    with get_pg_pool().connection() as conn:
        n_lead = conn.execute(
            "select count(*) as n from crm.leads where customer_id = %s and closed_at is null",
            (kh3["id"],),
        ).fetchone()["n"]
    ok("đồng bộ lại 3 lần vẫn 1 lead mở", n_lead == 1, f"được {n_lead}")

    print("== 4. Gộp khách (FR-022) ==")
    with get_pg_pool().connection() as conn:
        don1 = conn.execute(
            "insert into crm.orders (customer_id, external_order_id, status) "
            "values (%s, %s, 'confirmed') returning id",
            (kh2["id"], f"{DAU}don1"),
        ).fetchone()["id"]
    phai_loi("gộp chính vào chính -> chặn", "VALIDATION_ERROR",
             customer_service.merge_customers,
             primary_id=kh1["id"], duplicate_ids=[kh1["id"]])
    out = customer_service.merge_customers(
        primary_id=kh1["id"], duplicate_ids=[kh2["id"]], actor_id=sale1,
    )
    ok("gộp xong: đơn dồn về hồ sơ chính", out["da_don"].get("orders", 0) == 1)
    with get_pg_pool().connection() as conn:
        dup = conn.execute(
            "select status, merged_into_id from crm.customers where id = %s",
            (kh2["id"],),
        ).fetchone()
        don_moi = conn.execute(
            "select customer_id from crm.orders where id = %s", (don1,)
        ).fetchone()["customer_id"]
    ok("hồ sơ phụ status=merged trỏ về chính",
       dup["status"] == "merged" and dup["merged_into_id"] == kh1["id"])
    ok("đơn nay thuộc hồ sơ chính", don_moi == kh1["id"])
    phai_loi("gộp lại hồ sơ đã merged -> chặn", "VALIDATION_ERROR",
             customer_service.merge_customers,
             primary_id=kh1["id"], duplicate_ids=[kh2["id"]])

    print("== 5. Tag + phân công ==")
    t = customer_service.add_tag(customer_id=kh1["id"], name=f"{DAU}VIP")
    ok("tạo tag mới + gắn", t["tag_id"] > 0)
    t2 = customer_service.add_tag(customer_id=kh3["id"], name=f"{DAU}VIP")
    ok("tag trùng tên dùng lại, không tạo mới", t2["tag_id"] == t["tag_id"])
    phai_loi("thay người đang giữ thiếu lý do -> chặn", "MISSING_REQUIRED_DATA",
             customer_service.assign,
             customer_id=kh1["id"], user_id=sale2, assignment_type="sale")
    customer_service.assign(customer_id=kh1["id"], user_id=sale2,
                            assignment_type="sale", reason="chia lại tệp")
    hist = customer_service.assignment_history(kh1["id"])
    ok("lịch sử phân công giữ cả người cũ", len(hist) == 2)
    customer_service.assign(customer_id=kh1["id"], user_id=sale1,
                            assignment_type="cskh")
    ok("sale và cskh là 2 ownership riêng",
       len([a for a in customer_service.get_customer(kh1["id"])["nguoi_phu_trach"]
            if a["assignment_type"] in ("sale", "cskh")]) == 2)

    print("== 6. API (khuôn A3 + route) ==")
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={
        "username": "admin", "password": settings.admin_bootstrap_password,
    })
    h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    r = client.get("/api/v1/customers", headers=h,
                   params={"keyword": f"{DAU}Anh"})
    ok("CUSTOMER-001 tìm theo keyword", r.status_code == 200
       and r.json()["data"]["pagination"]["total"] >= 1)
    r = client.get("/api/v1/customers/duplicates", headers=h)
    ok("CUSTOMER-006 không bị /{id} nuốt", r.status_code == 200)
    r = client.get(f"/api/v1/customers/{kh1['id']}/timeline", headers=h)
    loai1 = {x["loai"] for x in r.json()["data"]["items"]}
    r = client.get(f"/api/v1/customers/{kh3['id']}/timeline", headers=h)
    loai3 = {x["loai"] for x in r.json()["data"]["items"]}
    ok("CUSTOMER-008 timeline: đơn (kh1, dồn từ gộp) + lead (kh3)",
       "order" in loai1 and "lead_stage" in loai3, f"kh1={loai1} kh3={loai3}")
    r = client.post("/api/v1/customers", headers=h, json={
        "full_name": f"{DAU}API Tao", "primary_phone": "0908887766",
        "source": f"{DAU}api",
    })
    ok("CUSTOMER-003 tạo 201", r.status_code == 201, r.text[:150])
    r = client.delete(f"/api/v1/customers/{r.json()['data']['id']}", headers=h)
    ok("CUSTOMER-005 xoá mềm", r.status_code == 200)
    r = client.get(f"/api/v1/customers/{kh2['id']}", headers=h)
    ok("hồ sơ merged vẫn xem được (không mất lịch sử)", r.status_code == 200)

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKẾT QUẢ: {PASS} PASS / {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
