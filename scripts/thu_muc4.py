"""Kiểm thử BRD MỤC 4 — Tích hợp Pancake & nguồn quảng cáo.

Nghiệm thu đúng 6 chức năng + 4 luật trọng yếu + 4 màn + 3 dữ liệu đầu ra của
mục 4:

  Chức năng  nhiều page/tài khoản · đồng bộ khách-hội thoại-thẻ-nhân viên-đơn ·
             lưu external_id/source/page_id/updated_at_external/synced_at ·
             sync log + retry queue · campaign/ad/creative + first/last touch ·
             nút mở đúng hội thoại Pancake
  Luật       không tạo khách trùng · không gọi API mỗi lần mở màn ·
             token lỗi phải cảnh báo · không sửa ngược nguồn
  Màn        Kết nối · Nhật ký đồng bộ · Danh sách lỗi · Ánh xạ

Dữ liệu GIẢ hết (page/hội thoại/đơn mang dấu `__m4test__`, shop POS 999888666)
— KHÔNG gọi mạng, không đụng dữ liệu Pancake thật.

Chạy:  python scripts/thu_muc4.py
Cần:   DB chạy + đã áp init_crm.sql bản mục 4 + seed_auth (có integration.manage).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core.config import settings               # noqa: E402
from app.core.errors import ApiError               # noqa: E402
from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import (                  # noqa: E402
    attribution_repo,
    customer_repo,
    integration_repo,
    order_repo,
    tag_store,
)
from app.integrations.pancake import crm_sync      # noqa: E402
from app.integrations.pancake.links import link_hoi_thoai  # noqa: E402
from app.integrations.pancake_pos import pos_sync  # noqa: E402
from app.main import app                           # noqa: E402
from app.services import integration_service       # noqa: E402

DAU = "__m4test__"
MK = "M4-test-1234"
PAGE_GIA = "999000111222333"          # page Facebook giả
PAGE_GIA2 = "999000111222444"         # page thứ 2 — kiểm "nhiều page"
SHOP_GIA = 999888666
NV_PANCAKE = "m4-staff-uuid-0001"
AD_GIA = "120000000000000999"
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
    conn.execute(f"delete from crm.orders where pos_shop_id = {SHOP_GIA}")
    conn.execute(
        "delete from crm.lead_attributions where customer_id in "
        f"(select id from crm.customers where full_name like '{DAU}%')")
    conn.execute(
        "delete from crm.orders where customer_id in "
        f"(select id from crm.customers where full_name like '{DAU}%')")
    conn.execute(
        "delete from crm.leads where customer_id in "
        f"(select id from crm.customers where full_name like '{DAU}%')")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.ads where external_ad_id = '{AD_GIA}'")
    conn.execute(
        "delete from crm.conversations where page_id in "
        f"(select id from crm.pages where external_page_id in ('{PAGE_GIA}','{PAGE_GIA2}'))")
    conn.execute(
        f"delete from crm.pages where external_page_id in ('{PAGE_GIA}','{PAGE_GIA2}')")
    conn.execute("delete from crm.sync_errors where external_id like 'm4c%'")
    conn.execute("delete from crm.pages where external_page_id = ''")
    conn.execute(f"delete from crm.sync_logs where scope in ('{PAGE_GIA}','{PAGE_GIA2}',"
                 f"'{SHOP_GIA}')")
    conn.execute(f"delete from crm.staff_mappings where external_staff_id like 'm4-%'")
    conn.execute(f"delete from crm.tags where name like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")
    # xoá cache page của crm_sync (lần chạy trước giữ id đã bị xoá)
    crm_sync._page_cache.clear()
    crm_sync._tat_cache.update({"luc": 0.0, "ids": set()})
    crm_sync._the_cache.update({"luc": 0.0, "data": {}})


def conv(conv_id: str, *, name: str, phone: str = "", fb: str = "",
         updated: str = "2026-08-01T09:00:00", tags: list | None = None,
         assignee: list | None = None, snippet: str = "xin chao") -> dict:
    """Hội thoại giả đúng shape mà crm_sync đọc (bản đã chuẩn hoá của poller)."""
    return {
        "conv_id": conv_id, "name": f"{DAU}{name}",
        "customer_id": f"uuid-{conv_id}", "fb_id": fb,
        "phones": [phone] if phone else [],
        "updated_at": updated, "snippet": snippet,
        "message_count": 5, "unread_count": 1,
        "tags": tags or [], "assignee_ids": assignee or [],
    }


def don_pos(pos_id: int, *, phone: str, name: str, status: int = 3,
            ad_id: str = "", post_id: str = "", conv_id: str = "",
            page: str = "", inserted: str = "2026-07-20T10:00:00") -> dict:
    return {
        "id": pos_id, "shop_id": SHOP_GIA, "status": status,
        "bill_full_name": f"{DAU}{name}", "bill_phone_number": phone,
        "total_price": 750000,
        "inserted_at": inserted, "updated_at": inserted,
        "conversation_id": conv_id or None, "page_id": page or None,
        "customer": {},
        "ad_id": ad_id or None, "post_id": post_id or None,
        "ads_source": "Facebook",
        "p_utm_campaign": "chien-dich-thu", "p_utm_source": "fb",
        "assigning_seller_id": NV_PANCAKE,
        "status_history": [{"status": 3, "updated_at": "2026-07-22T08:00:00"}],
    }


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        for ten, vai in (("admin", "Admin"), ("sale", "Sale")):
            conn.execute(
                "insert into crm.users (name, email, username, password_hash, status, role_id) "
                "values (%s, %s, %s, %s, 'active', %s)",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]),
            )
        uid_sale = conn.execute(
            "select id from crm.users where username = %s", (f"{DAU}sale",)
        ).fetchone()["id"]
    # tên thẻ Pancake giả cho 2 page (kho watcher.the_pancake) — crm_sync dịch ID -> tên
    tag_store.upsert_tags(PAGE_GIA, {501: {"text": f"{DAU}Da chot", "color": "#0f0"}})
    tag_store.upsert_tags(PAGE_GIA2, {501: {"text": f"{DAU}Da chot", "color": "#0f0"}})

    print("== 1. Kết nối nhiều page/tài khoản Pancake ==")
    ket_noi = integration_service.danh_sach_ket_noi()
    ok("dam_bao_ket_noi tạo dòng kết nối theo .env (chạy lại không trùng)",
       len(ket_noi) >= 1 and len(integration_service.danh_sach_ket_noi()) == len(ket_noi))
    ok("token KHÔNG bị lưu vào DB (chỉ giữ bản che)",
       all(not (k.get("token_hint") or "").startswith("ey") for k in ket_noi))

    kq1 = crm_sync.sync_batch(PAGE_GIA, "Page Thu 1", [
        conv("m4c1", name="KhachA", phone="0912345678", fb="fb-a",
             tags=[501], assignee=[NV_PANCAKE]),
        conv("m4c2", name="KhachB", fb="fb-b"),
    ])
    kq2 = crm_sync.sync_batch(PAGE_GIA2, "Page Thu 2", [
        conv("m4c3", name="KhachC", fb="fb-c"),
    ])
    ok("2 page khác nhau cùng đổ về CRM được",
       kq1["tao_moi"] == 2 and kq2["tao_moi"] == 1, f"{kq1} {kq2}")

    print("== 2. Đồng bộ customer · conversation · tag · nhân viên xử lý ==")
    with pool.connection() as conn:
        hc = conn.execute(
            "select c.*, p.external_page_id from crm.conversations c "
            "join crm.pages p on p.id = c.page_id "
            "where c.external_conversation_id = 'm4c1'").fetchone()
    ok("hội thoại về CRM đúng page + external_conversation_id",
       hc and hc["external_page_id"] == PAGE_GIA, str(hc))
    ok("lưu source + updated_at_external + synced_at (đúng câu chữ mục 4)",
       hc["source"] == "pancake" and hc["external_updated_at"] is not None
       and hc["synced_at"] is not None)
    ok("lưu thêm snippet + số tin + chưa đọc", hc["message_count"] == 5
       and hc["unread_count"] == 1 and hc["snippet"] == "xin chao")

    with pool.connection() as conn:
        the = conn.execute(
            "select t.name from crm.customer_tags ct join crm.tags t on t.id = ct.tag_id "
            f"where ct.customer_id = %s", (hc["customer_id"],)).fetchall()
    ok("thẻ Pancake dịch ra TÊN và gắn vào khách",
       any(r["name"] == f"{DAU}Da chot" for r in the), str(the))

    ok("nhân viên xử lý lưu id gốc bên Pancake",
       hc["assignee_external_id"] == NV_PANCAKE)
    ok("chưa ánh xạ -> assignee_user_id rỗng, KHÔNG chặn đồng bộ",
       hc["assignee_user_id"] is None)
    nv = integration_repo.list_staff("pancake_pages")
    ok("id nhân viên tự vào bảng ánh xạ để Admin gán sau",
       any(s["external_staff_id"] == NV_PANCAKE for s in nv))

    integration_service.gan_nhan_vien("pancake_pages", NV_PANCAKE, uid_sale)
    crm_sync.sync_batch(PAGE_GIA, "Page Thu 1", [
        conv("m4c1", name="KhachA", phone="0912345678", fb="fb-a",
             updated="2026-08-01T10:30:00", tags=[501], assignee=[NV_PANCAKE])])
    with pool.connection() as conn:
        hc2 = conn.execute("select * from crm.conversations where "
                           "external_conversation_id = 'm4c1'").fetchone()
    ok("gán ánh xạ xong -> lượt sau hội thoại mang đúng nhân viên CRM",
       hc2["assignee_user_id"] == uid_sale)
    ok("updated_at_external tiến theo Pancake, không lùi",
       hc2["external_updated_at"] > hc["external_updated_at"])

    print("== 3. LUẬT — không tạo khách mới khi đã tồn tại định danh chuẩn ==")
    with pool.connection() as conn:
        truoc = conn.execute(
            f"select count(*) n from crm.customers where full_name like '{DAU}%'"
        ).fetchone()["n"]
    lai = crm_sync.sync_batch(PAGE_GIA, "Page Thu 1", [
        conv("m4c1", name="KhachA", phone="0912345678", fb="fb-a", tags=[501]),
        conv("m4c2", name="KhachB", fb="fb-b"),
    ])
    with pool.connection() as conn:
        sau = conn.execute(
            f"select count(*) n from crm.customers where full_name like '{DAU}%'"
        ).fetchone()["n"]
    ok("đồng bộ lại y hệt -> KHÔNG sinh khách mới (idempotent)",
       truoc == sau and lai["tao_moi"] == 0, f"{truoc} -> {sau}")

    print("== 4. Nhật ký đồng bộ (sync_logs) ==")
    logs, tong = integration_repo.list_logs(provider="pancake_pages", limit=10)
    log1 = next((x for x in logs if x["scope"] == PAGE_GIA), None)
    ok("mỗi mẻ đồng bộ ghi 1 dòng nhật ký", log1 is not None and tong >= 3)
    ok("nhật ký đếm đủ tạo/sửa/bỏ qua/lỗi + thời lượng",
       log1["created_count"] + log1["updated_count"] >= 0
       and log1["duration_ms"] is not None and log1["status"] in
       ("success", "partial", "failed"))

    print("== 5. Hàng đợi lỗi + thử lại (retry queue) ==")
    # Ép lỗi THẬT ở tầng ghi: mốc thời gian rác -> Postgres từ chối ::timestamptz
    hong = conv("m4c9", name="KhachHong", phone="0912345679",
                updated="khong-phai-thoi-gian")
    kq_hong = crm_sync.sync_batch(PAGE_GIA, "Page Thu 1", [hong])
    rows, _ = integration_repo.list_loi(provider="pancake_pages", status="pending")
    dong_loi = next((r for r in rows if r["external_id"] == "m4c9"), None)
    ok("row hỏng -> đếm vào 'loi' và KHÔNG ném lên poller", kq_hong["loi"] == 1)
    ok("row hỏng vào hàng đợi kèm loại lỗi", dong_loi is not None, str(rows[:1]))

    integration_repo.ghi_loi(
        provider="pancake_pages", entity="conversation", external_id="m4c9",
        error_type="X", error_message="lan 2")
    rows2, _ = integration_repo.list_loi(provider="pancake_pages", status="pending")
    dong2 = next((r for r in rows2 if r["external_id"] == "m4c9"), None)
    ok("lỗi lặp lại -> CỘNG số lần thử vào cùng 1 dòng, không nhân bản",
       dong2 is not None and dong2["retry_count"] == 1
       and len([r for r in rows2 if r["external_id"] == "m4c9"]) == 1)
    ok("backoff: lần thử kế hẹn về tương lai",
       dong2["next_retry_at"] > dong2["created_at"])

    # payload đã lưu -> chạy lại được mà không gọi Pancake
    integration_repo.ghi_loi(
        provider="pancake_pages", entity="conversation", external_id="m4c9",
        payload=conv("m4c9", name="KhachHong", phone="0912345679",
                     **{"assignee": []}) | {"_page_name": "Page Thu 1"},
        error_type="X", error_message="lan 3")
    integration_repo.hen_lai(dong2["id"], 0)
    kq_retry = integration_service.chay_hang_doi()
    rows3, _ = integration_repo.list_loi(provider="pancake_pages", status="pending")
    ok("chạy hàng đợi -> sửa từ payload đã lưu, KHÔNG gọi lại Pancake",
       kq_retry["xong"] >= 1, str(kq_retry))
    ok("chạy xong dòng lỗi rời khỏi hàng đợi",
       not any(r["external_id"] == "m4c9" for r in rows3))

    # Hội thoại "mồ côi" (không biết page): tuyệt đối KHÔNG được tạo page rỗng
    # rồi dồn hết vào đó — hỏng cả ánh xạ page lẫn link mở Pancake.
    kq_mo_coi = crm_sync.sync_batch("", "Khong ro page", [
        conv("m4c11", name="KhachMoCoi", fb="fb-z")])
    with pool.connection() as conn:
        page_rong = conn.execute(
            "select count(*) n from crm.pages where external_page_id = ''"
        ).fetchone()["n"]
    ok("hội thoại thiếu page -> vào hàng đợi lỗi, KHÔNG tạo page rỗng",
       kq_mo_coi["loi"] == 1 and page_rong == 0, f"page rỗng: {page_rong}")

    print("== 6. Đơn POS + quy nguồn quảng cáo (campaign/ad/creative, first/last) ==")
    kq_don = pos_sync.sync_batch([
        don_pos(9001, phone="0912345678", name="KhachA", ad_id=AD_GIA,
                post_id="post-1", conv_id="m4c1", page=PAGE_GIA,
                inserted="2026-07-10T10:00:00"),
        don_pos(9002, phone="0912345678", name="KhachA", ad_id=AD_GIA,
                post_id="post-2", conv_id="m4c1", page=PAGE_GIA,
                inserted="2026-07-25T10:00:00"),
    ])
    ok("đơn POS về CRM (2 đơn cùng khách)", kq_don["tao_moi"] == 2, str(kq_don))
    with pool.connection() as conn:
        kh_a = conn.execute(
            "select id from crm.customers where full_name = %s", (f"{DAU}KhachA",)
        ).fetchone()
        don_ktra = conn.execute(
            "select * from crm.orders where pos_shop_id = %s and pos_order_id = 9001",
            (SHOP_GIA,)).fetchone()
    ok("đơn lưu synced_at + pos_updated_at (dấu vết đồng bộ)",
       don_ktra["synced_at"] is not None and don_ktra["pos_updated_at"] is not None)
    ok("đơn POS KHÔNG tạo khách mới cho người đã có (khớp qua SĐT/hội thoại)",
       don_ktra["customer_id"] == kh_a["id"])

    cham = {c["touch_type"]: c for c in attribution_repo.cham_cua_khach(kh_a["id"])}
    ok("ghi chạm ĐẦU và chạm CUỐI cho khách", set(cham) == {"first", "last"}, str(cham))
    ok("chạm đầu = đơn cũ nhất, chạm cuối = đơn mới nhất",
       cham["first"]["attributed_at"] < cham["last"]["attributed_at"])
    ok("lưu ad_id + post_id + utm (campaign/source) theo mục 4",
       cham["last"]["external_ad_id"] == AD_GIA
       and cham["last"]["post_id"] == "post-2"
       and (cham["last"]["utm"] or {}).get("campaign") == "chien-dich-thu")
    with pool.connection() as conn:
        ad = conn.execute("select * from crm.ads where external_ad_id = %s",
                          (AD_GIA,)).fetchone()
    ok("ad_id lẻ vẫn lưu được vào crm.ads (chưa có cây campaign — MVP5 lấp sau)",
       ad is not None and ad["ad_set_id"] is None)
    ok("nhân viên POS (người bán) tự vào bảng ánh xạ",
       any(s["external_staff_id"] == NV_PANCAKE
           for s in integration_repo.list_staff("pancake_pos")))
    # limit lớn: DB thật (POS_SYNC bật) có quy nguồn thật doanh thu cao hơn —
    # top 5 không còn chỗ cho ad giả của test
    top = attribution_repo.thong_ke_nguon(1000)
    ok("thống kê nguồn ra được số khách + doanh thu theo quảng cáo",
       any(r["ad_id"] == AD_GIA and r["so_khach"] >= 1 for r in top), str(top[:2]))

    print("== 7. LUẬT — bật/tắt đồng bộ theo page ==")
    page_row = integration_repo.find_page("facebook", PAGE_GIA)
    integration_service.bat_tat_page(page_row["id"], False)
    crm_sync._tat_cache["luc"] = 0.0        # ép đọc lại ngay, khỏi chờ 60s
    kq_tat = crm_sync.sync_batch(PAGE_GIA, "Page Thu 1", [
        conv("m4c10", name="KhachSauKhiTat", fb="fb-x")])
    with pool.connection() as conn:
        co = conn.execute("select count(*) n from crm.conversations where "
                          "external_conversation_id = 'm4c10'").fetchone()["n"]
    ok("page tắt đồng bộ -> hội thoại KHÔNG vào CRM (bot vẫn chạy)",
       kq_tat["bo_qua"] == 1 and co == 0)
    integration_service.bat_tat_page(page_row["id"], True)
    crm_sync._tat_cache["luc"] = 0.0

    print("== 8. LUẬT — token lỗi/hết hạn phải cảnh báo ==")
    acc = integration_repo.find_account("pancake_pages")
    integration_repo.update_account(acc["id"], {"token_status": "invalid",
                                                "last_error": "token het han"})
    tt = integration_service.tinh_trang()
    ok("token hỏng -> tinh_trang() trả cảnh báo cho màn Tích hợp",
       len(tt["canh_bao_token"]) >= 1, str(tt["canh_bao_token"]))
    integration_repo.update_account(acc["id"], {"token_status": "unknown",
                                                "last_error": None})

    print("== 9. LUẬT — không sửa ngược dữ liệu nguồn ==")
    ten_ham = [t for t in dir(integration_service) if not t.startswith("_")]
    ok("service tích hợp KHÔNG có hàm nào ghi ngược sang Pancake",
       not any(t.startswith(("push_", "gui_", "day_", "update_pancake")) for t in ten_ham))

    print("== 10. Nút mở đúng hội thoại Pancake từ hồ sơ CRM ==")
    link = link_hoi_thoai(PAGE_GIA, f"{PAGE_GIA}_37332576599720869")
    ok("dựng link hội thoại đúng mẫu (page + thread id)",
       PAGE_GIA in link and "37332576599720869" in link, link)
    ok("thiếu dữ liệu -> trả rỗng để view ẩn nút", link_hoi_thoai("", "abc") == "")
    ds = integration_repo.hoi_thoai_cua_khach(kh_a["id"])
    ok("tra hội thoại của khách đọc từ DB (không gọi API)",
       len(ds) >= 1 and ds[0]["external_page_id"] == PAGE_GIA)

    print("== 11. API INTEGRATION-001…010 + phân quyền ==")
    client = TestClient(app)

    def dang_nhap(u: str, p: str) -> dict:
        r = client.post("/api/v1/auth/login", json={"username": u, "password": p})
        assert r.status_code == 200, r.text[:200]
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    ha = dang_nhap(f"{DAU}admin", MK)
    hs = dang_nhap(f"{DAU}sale", MK)

    r = client.get("/api/v1/integrations", headers=ha)
    ok("INTEGRATION-001 danh sách kết nối", r.status_code == 200
       and len(r.json()["data"]["items"]) >= 1, r.text[:200])
    r = client.get("/api/v1/integrations", headers=hs)
    ok("Sale không có integration.manage -> 403", r.status_code == 403)

    r = client.get("/api/v1/integrations/tinh-trang", headers=ha)
    ok("INTEGRATION-002 tình trạng đồng bộ (công tắc + lỗi + quy nguồn)",
       r.status_code == 200 and "cong_tac" in r.json()["data"], r.text[:200])

    r = client.get("/api/v1/integrations/pages", headers=ha)
    ok("INTEGRATION-004 danh sách page + cờ đồng bộ", r.status_code == 200
       and any(p["external_page_id"] == PAGE_GIA for p in r.json()["data"]["items"]))

    r = client.put(f"/api/v1/integrations/pages/{page_row['id']}/dong-bo",
                   headers=ha, json={"sync_enabled": True})
    ok("INTEGRATION-005 bật/tắt đồng bộ page", r.status_code == 200)

    r = client.put("/api/v1/integrations/nhan-vien", headers=ha, json={
        "provider": "pancake_pages", "external_staff_id": NV_PANCAKE,
        "user_id": uid_sale})
    ok("INTEGRATION-008 gán nhân viên Pancake -> CRM", r.status_code == 200)

    r = client.get("/api/v1/integrations/nhat-ky?provider=pancake_pages", headers=ha)
    ok("INTEGRATION-009 nhật ký đồng bộ có phân trang",
       r.status_code == 200 and r.json()["data"]["pagination"]["total"] >= 1)

    r = client.get("/api/v1/integrations/loi?status=resolved", headers=ha)
    ok("INTEGRATION-010 danh sách lỗi lọc theo tình trạng", r.status_code == 200)

    r = client.get(f"/api/v1/customers/{kh_a['id']}/quy-nguon", headers=hs)
    ok("Sale xem được nguồn Ads của khách (customer.view)",
       r.status_code == 200 and len(r.json()["data"]["items"]) == 2, r.text[:200])
    r = client.get(f"/api/v1/customers/{kh_a['id']}/pancake-links", headers=hs)
    ok("API link mở hội thoại Pancake trả link dựng sẵn",
       r.status_code == 200 and r.json()["data"]["items"][0]["link"], r.text[:200])
    r = client.get("/api/v1/customers/99999999/pancake-links", headers=hs)
    ok("khách không tồn tại -> 404", r.status_code == 404)

    phai_loi("gán nhân viên với nguồn lạ -> VALIDATION_ERROR", "VALIDATION_ERROR",
             integration_service.gan_nhan_vien, "zalo_oa", "x", None)
    phai_loi("bật/tắt page không tồn tại -> NOT_FOUND", "NOT_FOUND",
             integration_service.bat_tat_page, 99999999, True)
    phai_loi("thử lại dòng lỗi không tồn tại -> NOT_FOUND", "NOT_FOUND",
             integration_service.thu_lai_ngay, 99999999)

    print("== 12. Bốn màn của mục 4 mở được (Kết nối · Nhật ký · Lỗi · Ánh xạ) ==")
    client.post("/dang-nhap", data={"username": f"{DAU}admin", "password": MK})
    for duong, ten in (("/quan-tri/tich-hop", "Kết nối"),
                       ("/quan-tri/tich-hop/nhat-ky", "Nhật ký đồng bộ"),
                       ("/quan-tri/tich-hop/loi", "Danh sách lỗi"),
                       ("/quan-tri/tich-hop/anh-xa", "Ánh xạ")):
        r = client.get(duong)
        ok(f"màn {ten} trả HTML 200", r.status_code == 200 and "<table" in r.text,
           f"{r.status_code}")
    r = client.get("/crm/khach-hang")
    ok("màn Khách hàng có nút mở hội thoại Pancake",
       r.status_code == 200 and "Pancake</a>" in r.text)

    client.post("/dang-xuat")
    client.post("/dang-nhap", data={"username": f"{DAU}sale", "password": MK})
    r = client.get("/quan-tri/tich-hop")
    ok("Sale mở màn Tích hợp -> 403", r.status_code == 403)

    print("== 13. Ánh xạ trạng thái đơn (màn 23) vẫn ăn ngay ==")
    ánh_xạ = order_repo.load_mapping_dict()
    ok("bảng ánh xạ 17 mã POS còn đủ", len(ánh_xạ) >= 17 and ánh_xạ.get(3) == "delivered")

    with pool.connection() as conn:
        don_dep(conn)

    print(f"\n=== KẾT QUẢ: {PASS} PASS · {FAIL} FAIL ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
