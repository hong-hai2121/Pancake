"""Kiểm thử B2 — đồng bộ Pancake vào CRM qua crm_sync (không gọi Pancake thật).

Chạy:  python scripts/thu_b2.py
Dữ liệu test mang dấu __b2__, tự dọn.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.client import get_pg_pool                    # noqa: E402
from app.integrations.pancake import crm_sync            # noqa: E402

DAU = "__b2__"
PASS = FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    conn.execute(
        f"""delete from crm.leads where customer_id in
            (select id from crm.customers where full_name like '{DAU}%')"""
    )
    conn.execute(
        f"""delete from crm.conversations where page_id in
            (select id from crm.pages where external_page_id like '{DAU}%')"""
    )
    conn.execute(
        f"""delete from crm.customer_identities where customer_id in
            (select id from crm.customers where full_name like '{DAU}%')"""
    )
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.pages where external_page_id like '{DAU}%'")
    # "Row rác" ở mục 4 KHÔNG mang dấu {DAU}: nó không có tên nên customer_service
    # đặt tên mặc định "Khách chưa rõ tên" -> mấy câu xoá theo dấu ở trên không với
    # tới, mỗi lần chạy script bỏ lại 1 khách ma + 1 lead rác trên bảng việc Sale.
    # Dấu vân tay dưới đây chỉ khớp đúng loại rác đó (khách thật luôn có ít nhất
    # một định danh/hội thoại/đơn — FR-020 bắt buộc SĐT hoặc định danh MXH).
    # crm.leads và phần còn lại cascade theo customers.
    conn.execute("""
        delete from crm.customers c
         where c.full_name = 'Khách chưa rõ tên'
           and c.source = 'pancake'
           and c.primary_phone is null
           and not exists (select 1 from crm.customer_identities i
                            where i.customer_id = c.id)
           and not exists (select 1 from crm.conversations v
                            where v.customer_id = c.id)
           and not exists (select 1 from crm.orders o where o.customer_id = c.id)
    """)
    crm_sync._page_cache.clear()


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)

    row1 = {
        "conv_id": f"{DAU}pg1_conv1", "customer_id": f"{DAU}uuid-1",
        "name": f"{DAU}Chi Hoa", "fb_id": f"{DAU}fb1",
        "phones": ["+84 91 222 3344"], "updated_at": "2026-07-31T10:00:00+07:00",
    }

    print("== 1. Lần đầu: tạo đủ khách + trang + hội thoại + lead ==")
    tao = crm_sync.sync_row(f"{DAU}pg1", f"{DAU}Page Mot", row1)
    ok("tạo khách mới", tao)
    with pool.connection() as conn:
        kh = conn.execute(
            f"select * from crm.customers where full_name = '{DAU}Chi Hoa'"
        ).fetchone()
        ok("SĐT đã chuẩn hoá khi vào CRM", kh and kh["primary_phone"] == "0912223344")
        ok("nguồn = pancake", kh["source"] == "pancake")
        pg = conn.execute(
            f"select * from crm.pages where external_page_id = '{DAU}pg1'"
        ).fetchone()
        ok("tự tạo crm.pages", pg is not None and pg["platform"] == "facebook")
        conv = conn.execute(
            "select * from crm.conversations where external_conversation_id = %s",
            (row1["conv_id"],),
        ).fetchone()
        ok("có dòng crm.conversations gắn đúng khách",
           conv is not None and conv["customer_id"] == kh["id"])
        so_lead = conn.execute(
            "select count(*) as n from crm.leads where customer_id = %s and closed_at is null",
            (kh["id"],),
        ).fetchone()["n"]
        ok("sinh 1 lead tự động", so_lead == 1)
        idents = conn.execute(
            "select * from crm.customer_identities where customer_id = %s", (kh["id"],)
        ).fetchall()
        ok("định danh có cả UUID + PSID", len(idents) == 1
           and idents[0]["external_customer_id"] == f"{DAU}uuid-1"
           and idents[0]["psid"] == f"{DAU}fb1")

    print("== 2. Đồng bộ lại — không nhân đôi (nghiệm thu FR-011) ==")
    tao2 = crm_sync.sync_row(f"{DAU}pg1", f"{DAU}Page Mot", row1)
    ok("lần 2 không tạo mới", not tao2)
    with pool.connection() as conn:
        n_kh = conn.execute(
            f"select count(*) as n from crm.customers where full_name like '{DAU}%'"
        ).fetchone()["n"]
        n_lead = conn.execute(
            f"""select count(*) as n from crm.leads l join crm.customers c
                on c.id = l.customer_id where c.full_name like '{DAU}%'"""
        ).fetchone()["n"]
        ok("vẫn 1 khách · 1 lead", n_kh == 1 and n_lead == 1,
           f"kh={n_kh} lead={n_lead}")

    print("== 3. Cùng khách nhắn từ HỘI THOẠI khác — nhận ra qua UUID ==")
    row2 = {
        "conv_id": f"{DAU}pg2_conv9", "customer_id": f"{DAU}uuid-1",
        "name": f"{DAU}Chi Hoa", "fb_id": f"{DAU}fb1", "phones": [],
        "updated_at": "2026-07-31T11:00:00+07:00",
    }
    tao3 = crm_sync.sync_row(f"{DAU}pg2", f"{DAU}Page Hai", row2)
    with pool.connection() as conn:
        n_kh = conn.execute(
            f"select count(*) as n from crm.customers where full_name like '{DAU}%'"
        ).fetchone()["n"]
        n_conv = conn.execute(
            f"""select count(*) as n from crm.conversations v join crm.customers c
                on c.id = v.customer_id where c.full_name like '{DAU}%'"""
        ).fetchone()["n"]
    ok("vẫn 1 khách, 2 hội thoại 2 page", not tao3 and n_kh == 1 and n_conv == 2,
       f"kh={n_kh} conv={n_conv}")

    print("== 4. Row thiếu sạch định danh (chỉ tên) — vẫn không vỡ ==")
    kq = crm_sync.sync_batch(f"{DAU}pg1", f"{DAU}Page Mot", [
        {"conv_id": f"{DAU}c_moi", "name": f"{DAU}Vo Danh", "phones": "[]"},
        {"conv_id": "", "name": None},          # row rác
    ])
    ok("batch chạy hết, không ném lỗi", sum(kq.values()) == 2, str(kq))
    # Row rác không có nổi 1 trong 4 bậc chống trùng -> khách tạo từ nó vĩnh viễn
    # không khớp lại được, cứ đồng bộ là đẻ thêm một "Khách chưa rõ tên" nữa.
    ok("row rác bị BỎ QUA, không đẻ khách ma + lead rác",
       kq["bo_qua"] == 1 and kq["tao_moi"] == 1, str(kq))
    with pool.connection() as conn:
        ma = conn.execute(
            "select count(*) as n from crm.customers where full_name = 'Khách chưa rõ tên'"
            " and source = 'pancake' and primary_phone is null"
            " and not exists (select 1 from crm.customer_identities i where i.customer_id = customers.id)"
            " and not exists (select 1 from crm.conversations v where v.customer_id = customers.id)"
            " and not exists (select 1 from crm.orders o where o.customer_id = customers.id)"
        ).fetchone()["n"]
    ok("không còn khách ma nào trong DB", ma == 0, f"còn {ma}")

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKẾT QUẢ: {PASS} PASS / {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
