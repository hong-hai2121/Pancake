"""Kiểm thử B7 — đơn hàng: 11 trạng thái, ánh xạ Pancake POS→CRM, đơn đầu/mua lại.

Cốt lõi nghiệm thu (THU-TU-TRIEN-KHAI-CRM.md): đơn Pancake đồng bộ về ĐÚNG
trạng thái CRM; đơn thứ 2 của khách tự gắn nhãn "mua lại".

Đồng bộ POS kiểm bằng DICT GIẢ (shop 999888777) — không gọi mạng, không đụng
dữ liệu POS thật; endpoint kéo tay (ORDER-011) chỉ kiểm phân quyền.

Chạy:  python scripts/thu_b7.py
Cần:   DB chạy + đã áp init_crm.sql bản B7 + seed_auth (có order.view/edit).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient      # noqa: E402

from app.core.config import settings           # noqa: E402
from app.core.errors import ApiError           # noqa: E402
from app.core.security import hash_password    # noqa: E402
from app.db.client import get_pg_pool          # noqa: E402
from app.db.repositories import order_repo     # noqa: E402
from app.integrations.pancake_pos import pos_sync  # noqa: E402
from app.main import app                       # noqa: E402
from app.services import order_service, product_service  # noqa: E402

DAU = "__b7test__"
MK = "B7-test-1234"
SHOP_GIA = 999888777          # shop POS giả — không bao giờ trùng shop thật
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
    # orders KHÔNG cascade từ customers -> phải xoá đơn trước, khách sau
    conn.execute(f"delete from crm.orders where pos_shop_id = {SHOP_GIA}")
    conn.execute(
        "delete from crm.orders where customer_id in "
        f"(select id from crm.customers where full_name like '{DAU}%')"
    )
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.products where name like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")
    # trả bảng ánh xạ về mặc định (lần chạy trước fail giữa chừng có thể để lại)
    conn.execute("update crm.order_status_mappings set crm_status='draft', note=null "
                 "where pancake_status=0")
    conn.execute("update crm.order_status_mappings set crm_status='pending', note=null "
                 "where pancake_status=17")


def don_pos(pos_id: int, *, status: int = 0, phone: str, name: str,
            total: float = 500000, inserted: str = "2026-07-30T10:00:00",
            updated: str | None = None, conv: str | None = None,
            page: str | None = None, fbid: str | None = None,
            history: list | None = None) -> dict:
    """Dựng 1 đơn POS giả đúng các trường mà pos_sync đọc."""
    return {
        "id": pos_id, "shop_id": SHOP_GIA, "status": status,
        "bill_full_name": name, "bill_phone_number": phone,
        "total_price": total,
        "inserted_at": inserted, "updated_at": updated or inserted,
        "conversation_id": conv, "page_id": page,
        "customer": {"fb_id": fbid} if fbid else {},
        "status_history": history or [],
    }


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)

        def tao_khach(ten: str) -> int:
            return conn.execute(
                "insert into crm.customers (full_name) values (%s) returning id",
                (f"{DAU}{ten}",),
            ).fetchone()["id"]

        kh1, kh2 = tao_khach("Khach1"), tao_khach("Khach2")
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles"
        ).fetchall()}
        for ten, vai in (("sale", "Sale"), ("ketoan", "Kế toán"), ("mkt", "Marketing")):
            conn.execute(
                "insert into crm.users (name, email, username, password_hash, status, role_id) "
                "values (%s, %s, %s, %s, 'active', %s)",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]),
            )

    sp1 = product_service.create_product(
        {"name": f"{DAU}Men tieu hoa", "product_code": f"{DAU}SP1", "price": 200000})
    sp_khong_gia = product_service.create_product({"name": f"{DAU}Chua co gia"})

    print("== 1. FR-080 — 11 trạng thái + luật chuyển, lịch sử không xoá ==")
    d1 = order_service.create_order(
        {"customer_id": kh1, "items": [{"product_id": sp1["id"], "quantity": 2}]})
    ok("tạo đơn -> draft, tự phân loại 'new', tổng = 2 x giá SP",
       d1["status"] == "draft" and d1["order_type"] == "new"
       and float(d1["total_amount"]) == 400000)
    ok("tạo đơn ghi luôn dòng lịch sử đầu (null -> draft)",
       len(d1["status_history"]) == 1
       and d1["status_history"][0]["from_status"] is None
       and d1["status_history"][0]["to_status"] == "draft")

    phai_loi("trạng thái lạ -> chặn", "VALIDATION_ERROR",
             order_service.change_status, d1["id"], "giao_xong")
    phai_loi("draft -> delivered (nhảy cóc) -> chặn", "INVALID_STAGE_TRANSITION",
             order_service.change_status, d1["id"], "delivered")
    order_service.change_status(d1["id"], "confirmed")
    phai_loi("đổi sang chính trạng thái đang đứng -> CONFLICT", "CONFLICT",
             order_service.change_status, d1["id"], "confirmed")
    order_service.change_status(d1["id"], "shipping")
    d1b = order_service.change_status(d1["id"], "delivered")
    ok("sang delivered -> tự đóng dấu delivered_at (mốc khởi tính CSKH)",
       d1b["delivered_at"] is not None)
    d1c = order_service.change_status(d1["id"], "collected")
    ok("delivered -> collected (đã thu tiền)", d1c["status"] == "collected")
    su = order_repo.list_history(d1["id"])
    ok("lịch sử đủ 5 bước, nối đúng chuỗi cũ->mới",
       len(su) == 5 and [h["to_status"] for h in su]
       == ["draft", "confirmed", "shipping", "delivered", "collected"])

    d2 = order_service.create_order(
        {"customer_id": kh2, "items": [{"product_id": sp1["id"], "quantity": 1}]})
    order_service.change_status(d2["id"], "cancelled")
    phai_loi("cancelled là trạng thái chót -> không đi tiếp",
             "INVALID_STAGE_TRANSITION",
             order_service.change_status, d2["id"], "confirmed")

    print("== 2. FR-082 — đơn đầu / mua lại ==")
    d3 = order_service.create_order(
        {"customer_id": kh1, "items": [{"product_id": sp1["id"], "quantity": 1}]})
    ok("đơn thứ 2 của khách -> tự gắn 'repurchase'", d3["order_type"] == "repurchase")
    d4 = order_service.create_order(
        {"customer_id": kh2, "items": [{"product_id": sp1["id"], "quantity": 1}]})
    ok("đơn trước đó bị HỦY không tính là đã mua -> đơn mới vẫn 'new'",
       d4["order_type"] == "new")
    d5 = order_service.create_order(
        {"customer_id": kh1, "order_type": "upsell",
         "items": [{"product_id": sp1["id"], "quantity": 1}]})
    ok("order_type gửi tay (upsell) được tôn trọng", d5["order_type"] == "upsell")

    print("== 3. FR-080 — giá chốt tại thời điểm bán ==")
    product_service.update_product(sp1["id"], {"price": 250000})
    it = order_repo.list_items(d1["id"])[0]
    ok("đổi giá SP xong, dòng hàng đơn cũ GIỮ giá lúc bán",
       float(it["unit_price"]) == 200000 and float(it["line_total"]) == 400000)
    d6 = order_service.create_order(
        {"customer_id": kh1,
         "items": [{"product_id": sp1["id"], "quantity": 1, "unit_price": 180000}]})
    ok("unit_price gửi tay được giữ nguyên (không tra lại giá SP)",
       float(order_repo.list_items(d6["id"])[0]["unit_price"]) == 180000)
    phai_loi("SP chưa có giá + không gửi unit_price -> chặn",
             "MISSING_REQUIRED_DATA", order_service.create_order,
             {"customer_id": kh1,
              "items": [{"product_id": sp_khong_gia["id"], "quantity": 1}]})
    phai_loi("đơn không có dòng hàng -> chặn", "MISSING_REQUIRED_DATA",
             order_service.create_order, {"customer_id": kh1, "items": []})

    print("== 4. FR-081 — bảng ánh xạ POS -> CRM (màn 23) ==")
    anh_xa = order_service.list_mappings()
    ok("seed đủ 17 mã trạng thái POS",
       len(anh_xa) == 17 and {m["pancake_status"] for m in anh_xa}
       == {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 15, 16, 17, 20})
    ok("mã 3 (Đã nhận) -> delivered theo mặc định",
       next(m["crm_status"] for m in anh_xa if m["pancake_status"] == 3) == "delivered")
    m17 = order_service.update_mapping(17, {"crm_status": "confirmed"})
    ok("admin sửa được ánh xạ (17 -> confirmed)", m17["crm_status"] == "confirmed")
    order_service.update_mapping(17, {"crm_status": "pending"})   # trả về mặc định
    phai_loi("ánh xạ sang trạng thái lạ -> chặn", "VALIDATION_ERROR",
             order_service.update_mapping, 17, {"crm_status": "xong_roi"})
    phai_loi("mã POS chưa có trong bảng -> NOT_FOUND", "NOT_FOUND",
             order_service.update_mapping, 99, {"crm_status": "draft"})

    print("== 5. Đồng bộ đơn POS (dict giả — không gọi mạng) ==")
    p1 = don_pos(1, phone="0911222001", name=f"{DAU}Pos Mot",
                 conv=f"{SHOP_GIA}_111", page=str(SHOP_GIA), fbid="111")
    kq = pos_sync.sync_batch([p1])
    ok("đơn POS mới -> tao_moi", kq == {"tao_moi": 1, "cap_nhat": 0, "bo_qua": 0, "loi": 0})
    dpos = order_repo.find_by_pos(SHOP_GIA, 1)
    ok("đơn nhận diện đúng: source/external_order_id/pos_status/trạng thái ánh xạ",
       dpos is not None and dpos["source"] == "pancake_pos"
       and dpos["external_order_id"] == f"pos:{SHOP_GIA}:1"
       and dpos["pos_status"] == 0 and dpos["status"] == "draft"
       and float(dpos["total_amount"]) == 500000)

    kq = pos_sync.sync_batch([p1])
    ok("chạy lại y hệt -> bo_qua (idempotent, không tạo trùng)",
       kq["bo_qua"] == 1 and kq["tao_moi"] == 0)

    p1_moi = dict(p1, status=1, updated_at="2026-07-30T12:00:00")
    kq = pos_sync.sync_batch([p1_moi])
    dpos = order_repo.find_by_pos(SHOP_GIA, 1)
    ok("POS đổi trạng thái (0->1) -> cap_nhat, CRM thành confirmed",
       kq["cap_nhat"] == 1 and dpos["status"] == "confirmed")
    su = order_repo.list_history(dpos["id"])
    ok("bước đổi do đồng bộ ghi lịch sử reason='pos_sync'",
       su[-1]["reason"] == "pos_sync" and su[-1]["changed_by"] is None)

    p1_giao = dict(p1, status=3, updated_at="2026-07-31T09:00:00",
                   status_history=[{"status": 3, "updated_at": "2026-07-31T08:30:00"}])
    pos_sync.sync_batch([p1_giao])
    dpos = order_repo.find_by_pos(SHOP_GIA, 1)
    ok("POS sang 3 (Đã nhận) -> delivered + delivered_at lấy mốc THẬT từ POS",
       dpos["status"] == "delivered" and dpos["delivered_at"] is not None
       and dpos["delivered_at"].strftime("%H:%M") == "08:30")

    p2 = don_pos(2, phone="0911222001", name=f"{DAU}Pos Mot",
                 inserted="2026-07-31T10:00:00")
    pos_sync.sync_batch([p2])
    d2pos = order_repo.find_by_pos(SHOP_GIA, 2)
    ok("đơn POS thứ 2 cùng SĐT -> khớp CÙNG khách, gắn 'repurchase'",
       d2pos["customer_id"] == dpos["customer_id"]
       and d2pos["order_type"] == "repurchase")
    with pool.connection() as conn:
        so_khach = conn.execute(
            f"select count(*) as n from crm.customers where full_name like '{DAU}Pos%'"
        ).fetchone()["n"]
    ok("không đẻ khách trùng khi khớp qua SĐT", so_khach == 1)

    p3 = don_pos(3, status=99, phone="0911222003", name=f"{DAU}Pos La")
    kq = pos_sync.sync_batch([p3])
    d3pos = order_repo.find_by_pos(SHOP_GIA, 3)
    su3 = order_repo.list_history(d3pos["id"])
    ok("mã POS lạ (99) -> KHÔNG bỏ rơi đơn: nhận 'draft' + reason đánh dấu",
       kq["tao_moi"] == 1 and d3pos["status"] == "draft"
       and "chưa có ánh xạ" in (su3[0]["reason"] or ""))

    p4 = don_pos(4, status=6, phone="0911222004", name=f"{DAU}Pos Huy",
                 inserted="2026-07-29T08:00:00")
    p5 = don_pos(5, status=0, phone="0911222004", name=f"{DAU}Pos Huy",
                 inserted="2026-07-30T08:00:00")
    pos_sync.sync_batch([p4, p5])
    ok("đơn POS bị hủy không tính 'đã mua' -> đơn sau vẫn 'new'",
       order_repo.find_by_pos(SHOP_GIA, 4)["status"] == "cancelled"
       and order_repo.find_by_pos(SHOP_GIA, 5)["order_type"] == "new")

    # backfill cũ->mới: đơn CŨ vào trước, đơn MỚI của cùng khách thành mua lại
    p6 = don_pos(6, phone="0911222006", name=f"{DAU}Pos Backfill",
                 inserted="2026-07-20T08:00:00")
    p7 = don_pos(7, phone="0911222006", name=f"{DAU}Pos Backfill",
                 inserted="2026-07-25T08:00:00")
    pos_sync.sync_batch([p6, p7])
    ok("backfill cũ->mới: đơn 20/07 là 'new', đơn 25/07 là 'repurchase' "
       "(so theo THỜI ĐIỂM TẠO bên POS)",
       order_repo.find_by_pos(SHOP_GIA, 6)["order_type"] == "new"
       and order_repo.find_by_pos(SHOP_GIA, 7)["order_type"] == "repurchase")

    order_service.update_mapping(0, {"crm_status": "pending"})
    p8 = don_pos(8, phone="0911222008", name=f"{DAU}Pos AnhXaMoi")
    pos_sync.sync_batch([p8])
    ok("admin đổi ánh xạ (0 -> pending) -> lượt đồng bộ SAU ăn ngay",
       order_repo.find_by_pos(SHOP_GIA, 8)["status"] == "pending")
    order_service.update_mapping(0, {"crm_status": "draft"})   # trả về mặc định

    print("== 6. Tầng API + phân quyền (ORDER-001…011) ==")
    client = TestClient(app)

    def dang_nhap(u: str, p: str) -> dict:
        r = client.post("/api/v1/auth/login", json={"username": u, "password": p})
        assert r.status_code == 200, r.text[:200]
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    ha = dang_nhap("admin", settings.admin_bootstrap_password)
    hs = dang_nhap(f"{DAU}sale", MK)
    hk = dang_nhap(f"{DAU}ketoan", MK)
    hm = dang_nhap(f"{DAU}mkt", MK)

    r = client.get(f"/api/v1/orders?q={DAU}Khach1", headers=hs)
    ok("ORDER-001 Sale xem danh sách + lọc theo tên khách",
       r.status_code == 200
       and r.json()["data"]["pagination"]["total"] >= 4, r.text[:200])
    r = client.get("/api/v1/orders?status=delivered&source=pancake_pos", headers=hs)
    ok("ORDER-001 lọc trạng thái + nguồn", r.status_code == 200 and all(
        x["status"] == "delivered" and x["source"] == "pancake_pos"
        for x in r.json()["data"]["items"]))
    r = client.post("/api/v1/orders", headers=hs, json={
        "customer_id": kh2,
        "items": [{"product_id": sp1["id"], "quantity": 3}]})
    ok("ORDER-003 Sale tạo đơn qua API -> 201", r.status_code == 201, r.text[:200])
    don_api = r.json()["data"]
    r = client.post(f"/api/v1/orders/{don_api['id']}/status", headers=hs,
                    json={"to_status": "confirmed", "reason": "gọi chốt xong"})
    ok("ORDER-005 chuyển trạng thái qua API", r.status_code == 200)
    r = client.post(f"/api/v1/orders/{don_api['id']}/status", headers=hs,
                    json={"to_status": "collected"})
    ok("ORDER-005 chuyển sai luật -> 409 INVALID_STAGE_TRANSITION",
       r.status_code == 409 and r.json()["error_code"] == "INVALID_STAGE_TRANSITION")
    r = client.put(f"/api/v1/orders/{don_api['id']}", headers=hs,
                   json={"note": "khách hẹn nhận cuối tuần"})
    ok("ORDER-004 sửa ghi chú", r.status_code == 200
       and r.json()["data"]["note"] == "khách hẹn nhận cuối tuần")
    r = client.get(f"/api/v1/orders/{don_api['id']}", headers=hs)
    ok("ORDER-002 chi tiết kèm items + lịch sử",
       len(r.json()["data"]["items"]) == 1
       and len(r.json()["data"]["status_history"]) == 2)
    r = client.get(f"/api/v1/orders/{don_api['id']}/history", headers=hk)
    ok("ORDER-006 Kế toán xem được lịch sử (order.view)",
       r.status_code == 200 and len(r.json()["data"]["items"]) == 2)
    r = client.get(f"/api/v1/customers/{kh1}/orders", headers=hs)
    ok("ORDER-007 đơn theo khách (hồ sơ 360°)",
       r.status_code == 200 and r.json()["data"]["pagination"]["total"] == 4)
    r = client.get("/api/v1/orders/tong-quan", headers=hk)
    ok("ORDER-008 tổng quan đếm theo trạng thái",
       r.status_code == 200 and "theo_trang_thai" in r.json()["data"])
    r = client.get("/api/v1/order-status-mappings", headers=hs)
    ok("ORDER-009 xem bảng ánh xạ", r.status_code == 200
       and len(r.json()["data"]["items"]) == 17)

    r = client.post("/api/v1/orders", headers=hk, json={
        "customer_id": kh2, "items": [{"product_id": sp1["id"], "quantity": 1}]})
    ok("Kế toán chỉ XEM — tạo đơn bị 403", r.status_code == 403)
    r = client.get("/api/v1/orders", headers=hm)
    ok("Marketing không có order.view -> 403", r.status_code == 403)
    r = client.put("/api/v1/order-status-mappings/17", headers=hs,
                   json={"crm_status": "confirmed"})
    ok("ORDER-010 Sale KHÔNG sửa được ánh xạ (403)", r.status_code == 403)
    r = client.put("/api/v1/order-status-mappings/17", headers=ha,
                   json={"crm_status": "pending", "note": "giữ mặc định"})
    ok("ORDER-010 admin sửa ánh xạ qua API", r.status_code == 200)
    r = client.post("/api/v1/orders/sync-pos", headers=hs, json={})
    ok("ORDER-011 kéo tay chỉ dành quản trị -> Sale 403", r.status_code == 403)

    with pool.connection() as conn:
        don_dep(conn)
        con = conn.execute(
            "select count(*) as n from crm.orders where customer_id in "
            f"(select id from crm.customers where full_name like '{DAU}%')"
        ).fetchone()["n"]
    ok("dọn sạch dữ liệu test", con == 0)

    print(f"\nKẾT QUẢ: {PASS} PASS / {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
