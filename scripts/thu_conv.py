"""Kiểm thử FR-012 + CONV-001…006 — tin nhắn về crm.messages + API hội thoại.

Nghiệm thu theo đặc tả:
  FR-012   dữ liệu đủ trường (id/người gửi/nội dung/thời gian/loại/file) ·
           KHÔNG chỉnh sửa nội dung gốc · tin gắn đúng khách ·
           có nút mở Pancake · lỗi đồng bộ phải retry được
  CONV-001…006  danh sách · chi tiết · tin nhắn · gắn khách · gán NV · gửi tin
  PANCAKE-010   link mở hội thoại

KHÔNG gọi mạng: client.get_conversation/send_message được thay bằng hàm giả.
Dữ liệu giả mang dấu `__tconv__`, dọn sạch đầu và cuối.

Chạy:  python scripts/thu_conv.py
Cần:   DB chạy + init_crm.sql bản FR-012 (cột messages mới) + seed_auth.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core import runtime_config                # noqa: E402
from app.core.errors import ApiError               # noqa: E402
from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import (                  # noqa: E402
    conversation_repo,
    customer_repo,
    integration_repo,
)
from app.integrations.pancake import client as pk_client  # noqa: E402
from app.integrations.pancake import crm_sync, message_sync  # noqa: E402
from app.main import app                           # noqa: E402
from app.services import conversation_service, integration_service  # noqa: E402

DAU = "__tconv__"
MK = "Tconv-test-1234"
PAGE_GIA = "888000111000999"
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
    conn.execute(
        "delete from crm.messages where conversation_id in "
        "(select c.id from crm.conversations c join crm.pages p on p.id = c.page_id "
        f" where p.external_page_id = '{PAGE_GIA}')")
    conn.execute(
        "delete from crm.conversations where page_id in "
        f"(select id from crm.pages where external_page_id = '{PAGE_GIA}')")
    conn.execute(
        "delete from crm.leads where customer_id in "
        f"(select id from crm.customers where full_name like '{DAU}%')")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.pages where external_page_id = '{PAGE_GIA}'")
    conn.execute(f"delete from crm.sync_errors where scope = '{PAGE_GIA}' "
                 "or external_id like 'tc-%'")
    conn.execute(f"delete from crm.sync_logs where scope = '{PAGE_GIA}'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")
    crm_sync._page_cache.clear()
    crm_sync._tat_cache.update({"luc": 0.0, "ids": set()})
    crm_sync._the_cache.update({"luc": 0.0, "data": {}})


def msg_gia(mid: str, text: str, *, is_page: bool = False,
            luc: str = "2026-08-01T09:00:00", att: list | None = None) -> dict:
    """Message đúng shape client._normalize_msg trả về."""
    return {
        "id": mid, "sender_id": PAGE_GIA if is_page else "psid-tc-1",
        "sender_name": "Page Thu" if is_page else f"{DAU}KhachA",
        "is_page": is_page, "text": text, "inserted_at": luc,
        "attachments": att or [],
    }


def main() -> None:  # noqa: PLR0915 — script nghiệm thu, dài là bình thường
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
            "select id from crm.users where username = %s", (f"{DAU}sale",),
        ).fetchone()["id"]

    print("== 1. Chuẩn bị: hội thoại về CRM qua đường B2 ==")
    kq = crm_sync.sync_batch(PAGE_GIA, "Page Thu Conv", [{
        "conv_id": f"{PAGE_GIA}_tconv1", "name": f"{DAU}KhachA",
        "customer_id": "uuid-tconv-1", "fb_id": "psid-tc-1",
        # Mốc bên Pancake phải ở QUÁ KHỨ so với giờ chạy test (DB lưu UTC):
        # để tương lai là "kéo xong vẫn stale" -> so mốc sai hết phía sau.
        "phones": ["0911222333"], "updated_at": "2026-07-31T09:00:00",
        "snippet": "xin chao", "message_count": 3, "unread_count": 1,
        "tags": [], "assignee_ids": [],
    }])
    ok("hội thoại giả đã vào crm.conversations", kq["tao_moi"] == 1, str(kq))
    with pool.connection() as conn:
        hc = conn.execute(
            "select c.*, p.external_page_id from crm.conversations c "
            "join crm.pages p on p.id = c.page_id "
            "where p.external_page_id = %s", (PAGE_GIA,)).fetchone()
    conv_id = hc["id"]

    print("== 2. FR-012: kéo tin nhắn (message_sync, client giả) ==")
    goc_get = pk_client.get_conversation

    async def get_gia(page_id, cid, customer_id=None):
        # CHỈ phục vụ hội thoại test — hội thoại thật lỡ lọt vào mẻ thì ném lỗi
        # (mốc tươi không nhích, KHÔNG ghi tin giả / KHÔNG đóng dấu bậy).
        if cid != f"{PAGE_GIA}_tconv1":
            raise RuntimeError("thu_conv: chỉ giả lập hội thoại test")
        return {"conv_id": cid, "customer_name": f"{DAU}KhachA", "messages": [
            msg_gia("m1", "em bi dau da day"),
            msg_gia("m2", "chao anh, em tu van nhe", is_page=True,
                    luc="2026-08-01T09:01:00"),
            msg_gia("m3", "", luc="2026-08-01T09:02:00",
                    att=[{"type": "photo", "url": "https://x/pic.jpg"}]),
        ]}

    pk_client.get_conversation = get_gia
    try:
        me = conversation_repo.hoi_thoai_cho_dong_bo(1000)
        muc_tieu = next((c for c in me if c["id"] == conv_id), None)
        ok("hội thoại CHƯA kéo tin nằm trong mẻ chờ", muc_tieu is not None)
        them = asyncio.run(message_sync.dong_bo_mot(muc_tieu))
        ok("kéo được 3 tin", them == 3, f"them={them}")

        rows, total = conversation_repo.list_messages(conv_id)
        ok("đủ trường FR-012: id ngoài + người gửi + thời gian",
           total == 3 and all(r["external_message_id"] and r["sent_at"]
                              for r in rows))
        ok("phân biệt khách/nhân viên (from.id trùng page -> agent)",
           rows[0]["sender_type"] == "customer"
           and rows[1]["sender_type"] == "agent")
        ok("tin chỉ có ảnh -> msg_type=attachment + giữ url",
           rows[2]["msg_type"] == "attachment"
           and (rows[2]["attachments"] or [{}])[0].get("url") == "https://x/pic.jpg")
        ok("tin nhắn gắn đúng hội thoại của đúng khách",
           all(r["conversation_id"] == conv_id for r in rows))

        them2 = asyncio.run(message_sync.dong_bo_mot(muc_tieu))
        ok("kéo LẠI không nhân đôi (idempotent)", them2 == 0
           and conversation_repo.list_messages(conv_id)[1] == 3)
        ok("kéo xong đóng dấu — mẻ chờ không nhặt lại nữa",
           all(c["id"] != conv_id
               for c in conversation_repo.hoi_thoai_cho_dong_bo(1000)))

        print("== 3. Luật 'không chỉnh sửa nội dung gốc' ==")
        conversation_repo.upsert_messages(conv_id, [{
            "external_message_id": "m1", "sender_type": "customer",
            "content": "NOI DUNG BI SUA", "sent_at": "2026-08-01T09:00:00",
        }])
        rows, _ = conversation_repo.list_messages(conv_id)
        ok("ghi đè cùng external_message_id -> nội dung gốc GIỮ NGUYÊN",
           rows[0]["content"] == "em bi dau da day", rows[0]["content"])

        print("== 4. Có tin mới -> được nhặt lại, chỉ thêm phần mới ==")
        # Mốc bên Pancake phải MỚI HƠN messages_synced_at (vừa đóng dấu = giờ
        # thật) nên tính từ đồng hồ thật, rồi ngủ qua mốc đó để lượt kéo sau
        # đóng dấu MUỘN hơn — cờ tin_da_tuoi ở bước 6 mới True.
        from datetime import datetime, timedelta, timezone

        bump = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        customer_repo.upsert_conversation(
            customer_id=hc["customer_id"], page_id=hc["page_id"],
            external_conversation_id=hc["external_conversation_id"],
            last_message_at=bump, external_updated_at=bump)
        me = conversation_repo.hoi_thoai_cho_dong_bo(1000)
        ok("external_updated_at nhích -> vào lại mẻ chờ",
           any(c["id"] == conv_id for c in me))

        async def get_gia2(page_id, cid, customer_id=None):
            d = await get_gia(page_id, cid, customer_id)
            d["messages"].append(msg_gia("m4", "gia bao nhieu vay",
                                         luc="2026-08-01T10:00:00"))
            return d

        pk_client.get_conversation = get_gia2
        import time as _time

        _time.sleep(1.2)
        vong = asyncio.run(message_sync.dong_bo_lo(1000))
        ok("vòng worker: 1 hội thoại · chỉ 1 tin MỚI",
           vong["hoi_thoai"] >= 1 and vong["tin_moi"] == 1, str(vong))
        with pool.connection() as conn:
            log = conn.execute(
                "select * from crm.sync_logs where entity = 'message' "
                "order by id desc limit 1").fetchone()
        ok("mỗi vòng có 1 dòng sync_logs entity='message'", bool(log))
    finally:
        pk_client.get_conversation = goc_get

    print("== 5. Lỗi ghi DB -> hàng đợi retry phát lại được (mục 4) ==")
    integration_service.ghi_loi(
        "pancake_pages", "message", "tc-err-1", RuntimeError("gia lap db loi"),
        payload={"_conv_crm_id": conv_id, "_rows": [{
            "external_message_id": "m9", "sender_type": "customer",
            "content": "tin phat lai tu hang doi",
            "sent_at": "2026-08-01T11:00:00"}]},
        scope=PAGE_GIA)
    with pool.connection() as conn:
        err_id = conn.execute(
            "select id from crm.sync_errors where external_id = 'tc-err-1' "
            "and status = 'pending'").fetchone()["id"]
    integration_repo.hen_lai(err_id, 0)
    kq_retry = integration_service.chay_hang_doi(100)
    rows, total = conversation_repo.list_messages(conv_id)
    ok("chay_hang_doi phát lại entity='message' từ payload",
       kq_retry["xong"] >= 1 and any(r["external_message_id"] == "m9" for r in rows),
       str(kq_retry))

    print("== 6. API CONV-001…006 + PANCAKE-010 ==")
    web = TestClient(app)

    def dang_nhap(u: str) -> dict:
        r = web.post("/api/v1/auth/login", json={"username": u, "password": MK})
        assert r.status_code == 200, r.text[:200]
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    ha = dang_nhap(f"{DAU}admin")
    hs = dang_nhap(f"{DAU}sale")

    r = web.get("/api/v1/conversations")
    ok("chưa đăng nhập -> 401", r.status_code == 401, str(r.status_code))

    r = web.get(f"/api/v1/conversations?customer_id={hc['customer_id']}", headers=hs)
    ok("CONV-001 danh sách theo khách (Sale xem được)",
       r.status_code == 200 and r.json()["data"]["pagination"]["total"] >= 1,
       r.text[:200])
    r = web.get(f"/api/v1/conversations?q={DAU}KhachA", headers=ha)
    ok("CONV-001 tìm theo tên khách", r.status_code == 200
       and r.json()["data"]["pagination"]["total"] >= 1)

    r = web.get(f"/api/v1/conversations/{conv_id}", headers=hs)
    ok("CONV-002 chi tiết + cờ tin_da_tuoi", r.status_code == 200
       and r.json()["data"]["tin_da_tuoi"] is True, r.text[:200])
    r = web.get("/api/v1/conversations/99999999", headers=hs)
    ok("CONV-002 không có -> 404", r.status_code == 404)

    r = web.get(f"/api/v1/conversations/{conv_id}/messages?per_page=3", headers=hs)
    d = r.json()["data"]
    ok("CONV-003 phân trang + cũ trước mới sau", r.status_code == 200
       and len(d["items"]) == 3
       and d["items"][0]["sent_at"] <= d["items"][-1]["sent_at"], r.text[:300])
    ok("CONV-003 meta: đã đồng bộ + có link Pancake",
       d["meta"]["chua_dong_bo"] is False and PAGE_GIA in d["meta"]["external_link"])

    r = web.get(f"/api/v1/conversations/{conv_id}/external-link", headers=hs)
    ok("PANCAKE-010 link mở hội thoại", r.status_code == 200
       and PAGE_GIA in r.json()["data"]["link"])

    kh_b, _ = customer_repo_upsert_khach_b()
    r = web.post(f"/api/v1/conversations/{conv_id}/attach-customer",
                 json={"customer_id": kh_b["id"]}, headers=ha)
    ok("CONV-004 gắn hội thoại sang khách khác", r.status_code == 200
       and r.json()["data"]["customer_id"] == kh_b["id"], r.text[:200])
    with pool.connection() as conn:
        au = conn.execute(
            "select * from crm.audit_logs where action = 'conversation_attach' "
            "and object_id = %s order by id desc limit 1", (conv_id,)).fetchone()
    ok("CONV-004 có audit cũ->mới", bool(au) and au["old_value"] is not None)
    r = web.post(f"/api/v1/conversations/{conv_id}/attach-customer",
                 json={"customer_id": 99999999}, headers=ha)
    ok("CONV-004 khách không tồn tại -> 404", r.status_code == 404)

    r = web.post(f"/api/v1/conversations/{conv_id}/assign",
                 json={"user_id": uid_sale}, headers=ha)
    ok("CONV-005 gán nhân viên phụ trách", r.status_code == 200
       and r.json()["data"]["assignee_user_id"] == uid_sale, r.text[:200])
    r = web.post(f"/api/v1/conversations/{conv_id}/assign",
                 json={"user_id": 99999999}, headers=ha)
    ok("CONV-005 nhân viên không tồn tại -> 404", r.status_code == 404)

    print("== 7. CONV-006 gửi tin (client giả — không gọi Pancake thật) ==")
    goc_send = pk_client.send_message
    gui_log = []

    async def send_gia(page_id, cid, message, customer_id=None):
        gui_log.append((page_id, cid, message))
        return {"id": "tc-sent-1"}

    pk_client.send_message = send_gia
    try:
        r = web.post(f"/api/v1/conversations/{conv_id}/messages",
                     json={"message": "  "}, headers=ha)
        ok("CONV-006 tin trống -> 422", r.status_code == 422, str(r.status_code))
        r = web.post(f"/api/v1/conversations/{conv_id}/messages",
                     json={"message": "chao anh, em gui bang gia"}, headers=ha)
        ok("CONV-006 gửi OK qua đúng page/hội thoại", r.status_code == 200
           and gui_log and gui_log[0][0] == PAGE_GIA, r.text[:200])
        rows, _ = conversation_repo.list_messages(conv_id)
        gui = next((r for r in rows if r["external_message_id"] == "tc-sent-1"), None)
        ok("tin vừa gửi ghi luôn bản CRM kèm người gửi",
           gui is not None and gui["sender_type"] == "agent"
           and gui["sender_user_id"] is not None)
    finally:
        pk_client.send_message = goc_send

    print("== 8. Công tắc + worker đã đăng ký ==")
    ok("3 cài đặt msg_sync_* có trong danh mục màn Cài đặt",
       all(k in runtime_config.THEO_MA
           for k in ("msg_sync_enabled", "msg_sync_interval", "msg_sync_batch")))
    from app.workers import messages_loop  # noqa: F401
    ok("worker messages_loop import được từ app.workers", True)
    ok("mặc định TẮT (giống các đồng bộ CRM khác)",
       runtime_config.bat("msg_sync_enabled") is False)

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKẾT QUẢ: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


def customer_repo_upsert_khach_b() -> tuple[dict, bool]:
    """Khách thứ 2 để thử CONV-004 (gắn lại hội thoại)."""
    from app.services import customer_service

    return customer_service.upsert_from_source(
        platform="facebook", name=f"{DAU}KhachB", phone="0988777666",
        external_customer_id="uuid-tconv-2", psid=None, page_id=None,
        external_conversation_id=None, source="pancake")


if __name__ == "__main__":
    main()
