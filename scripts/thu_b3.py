"""Kiểm thử B3 — luật lead & pipeline, chạy trên DB thật rồi TỰ DỌN SẠCH.

Chạy:  python scripts/thu_b3.py
Cần:   docker compose up -d  +  đã seed (seed_auth.py, seed_danh_muc.py)

Dữ liệu test đều mang dấu __b3test__ — có chết giữa chừng thì chạy lại,
script dọn dữ liệu cũ trước khi test.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.errors import ApiError          # noqa: E402
from app.db.client import get_pg_pool         # noqa: E402
from app.services import lead_service         # noqa: E402

DAU = "__b3test__"
PASS = 0
FAIL = 0


def ok(ten: str, dieu_kien: bool, them: str = "") -> None:
    global PASS, FAIL
    if dieu_kien:
        PASS += 1
        print(f"  PASS  {ten}")
    else:
        FAIL += 1
        print(f"  FAIL  {ten}  {them}")


def phai_loi(ten: str, ma: str, fn, *a, **kw) -> None:
    """Gọi fn và ĐÒI nó raise ApiError đúng mã."""
    try:
        fn(*a, **kw)
        ok(ten, False, "không raise gì cả")
    except ApiError as e:
        ok(ten, e.code == ma, f"raise {e.code} thay vì {ma}")


def don_dep(conn) -> None:
    conn.execute(f"delete from crm.leads where source like '{DAU}%'")
    conn.execute(f"delete from crm.orders where external_order_id like '{DAU}%'")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)

        # --- dựng dữ liệu test ---
        role_sale = conn.execute(
            "select id from crm.roles where name = 'Sale'"
        ).fetchone()
        assert role_sale, "Chưa seed vai trò — chạy scripts/seed_auth.py"
        s1 = conn.execute(
            "insert into crm.users (name, email, status, role_id) "
            "values (%s, %s, 'active', %s) returning id",
            (f"{DAU}Sale 1", f"{DAU}s1@x.com", role_sale["id"]),
        ).fetchone()["id"]
        s2 = conn.execute(
            "insert into crm.users (name, email, status, role_id) "
            "values (%s, %s, 'active', %s) returning id",
            (f"{DAU}Sale 2", f"{DAU}s2@x.com", role_sale["id"]),
        ).fetchone()["id"]
        kh1 = conn.execute(
            "insert into crm.customers (full_name) values (%s) returning id",
            (f"{DAU}Khach 1",),
        ).fetchone()["id"]
        kh2 = conn.execute(
            "insert into crm.customers (full_name) values (%s) returning id",
            (f"{DAU}Khach 2",),
        ).fetchone()["id"]
        ly_do = conn.execute(
            "select id from crm.lead_reasons where code = 'gia_cao'"
        ).fetchone()["id"]

    print("== 1. Tạo lead + chia tự động (FR-030) ==")
    l1 = lead_service.create_lead(customer_id=kh1, source=f"{DAU}fb")
    ok("lead 1 ở giai đoạn mở đầu", l1["stage_id"] is not None)
    ok("lead 1 được chia cho Sale test", l1["owner_id"] in (s1, s2))
    ok("lead 1 có hạn SLA", l1["sla_due_at"] is not None)
    l2 = lead_service.create_lead(customer_id=kh2, source=f"{DAU}fb")
    ok("vòng tròn: 2 lead chia 2 Sale khác nhau", l2["owner_id"] != l1["owner_id"])
    ls = lead_service.stage_history(l1["id"])
    ok("tạo lead có sẵn 1 dòng lịch sử", len(ls) == 1 and ls[0]["from_stage_id"] is None)

    print("== 2. Luật chặn chuyển giai đoạn (FR-040) ==")
    with get_pg_pool().connection() as conn:
        stages = {
            r["code"]: r["id"]
            for r in conn.execute(
                "select id, code from crm.pipeline_stages where pipeline_id = %s",
                (l1["pipeline_id"],),
            ).fetchall()
        }
    phai_loi(
        "'Đang cân nhắc' thiếu lý do -> chặn", "MISSING_REQUIRED_DATA",
        lead_service.move_stage,
        lead_id=l1["id"], to_stage_id=stages["dang_can_nhac"], actor_id=s1,
    )
    phai_loi(
        "'Đang cân nhắc' có lý do nhưng thiếu lịch hẹn -> chặn", "MISSING_REQUIRED_DATA",
        lead_service.move_stage,
        lead_id=l1["id"], to_stage_id=stages["dang_can_nhac"], actor_id=s1,
        reason="khách chê giá",
    )
    l1b = lead_service.move_stage(
        lead_id=l1["id"], to_stage_id=stages["dang_can_nhac"], actor_id=s1,
        reason="khách chê giá",
        next_action_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    ok("'Đang cân nhắc' đủ lý do + lịch hẹn -> qua", l1b["stage_code"] == "dang_can_nhac")
    phai_loi(
        "'Đã chốt' khi khách chưa có đơn -> chặn", "INVALID_STAGE_TRANSITION",
        lead_service.move_stage,
        lead_id=l1["id"], to_stage_id=stages["da_chot"], actor_id=s1,
    )
    with get_pg_pool().connection() as conn:
        conn.execute(
            "insert into crm.orders (customer_id, external_order_id, status) "
            "values (%s, %s, 'confirmed')",
            (kh1, f"{DAU}don1"),
        )
    l1c = lead_service.move_stage(
        lead_id=l1["id"], to_stage_id=stages["da_chot"], actor_id=s1,
    )
    ok("'Đã chốt' khi có đơn -> qua, closed_at có giá trị", l1c["closed_at"] is not None)
    phai_loi(
        "'Từ chối' không có lý do chuẩn -> chặn", "MISSING_REQUIRED_DATA",
        lead_service.move_stage,
        lead_id=l2["id"], to_stage_id=stages["tu_choi"], actor_id=s2,
    )
    l2b = lead_service.move_stage(
        lead_id=l2["id"], to_stage_id=stages["tu_choi"], actor_id=s2,
        lost_reason_id=ly_do, note="chê đắt",
    )
    ok("'Từ chối' kèm lost_reason_id -> qua", l2b["stage_code"] == "tu_choi")
    phai_loi(
        "giai đoạn không tồn tại -> NOT_FOUND", "NOT_FOUND",
        lead_service.move_stage,
        lead_id=l1["id"], to_stage_id=999999, actor_id=s1,
    )

    print("== 3. Lịch sử (FR-041) ==")
    hist = lead_service.stage_history(l1["id"])
    ok("l1 có 3 dòng lịch sử (tạo + 2 lần chuyển)", len(hist) == 3, f"được {len(hist)}")
    ok(
        "dòng mới nhất ghi người + lý do... ",
        hist[0]["to_stage_name"] == "Đã chốt" and hist[1]["reason"] == "khách chê giá",
    )

    print("== 4. Chuyển người + hàng đợi (FR-031/032) ==")
    l3 = lead_service.create_lead(customer_id=kh1, source=f"{DAU}zalo", auto_assign=False)
    ok("tắt auto_assign -> vào hàng đợi", l3["owner_id"] is None)
    queue = [x["id"] for x in lead_service.list_queue()]
    ok("l3 nằm trong hàng đợi", l3["id"] in queue)
    l3b = lead_service.assign_owner(lead_id=l3["id"], new_owner_id=s1, reason=None)
    ok("nhận lead từ hàng đợi không cần lý do", l3b["owner_id"] == s1)
    phai_loi(
        "chuyển sang người khác thiếu lý do -> chặn (FR-031)", "MISSING_REQUIRED_DATA",
        lead_service.assign_owner,
        lead_id=l3["id"], new_owner_id=s2, reason="",
    )
    l3c = lead_service.assign_owner(
        lead_id=l3["id"], new_owner_id=s2, reason="Sale 1 nghỉ phép",
    )
    ok("chuyển có lý do -> qua", l3c["owner_id"] == s2)

    print("== 5. SLA + nóng/ấm/lạnh (FR-042, LEAD-008/009) ==")
    with get_pg_pool().connection() as conn:
        conn.execute(
            "update crm.leads set sla_due_at = now() - interval '10 minutes', "
            "temperature = 'nong' where id = %s",
            (l3["id"],),
        )
    ok("l3 quá SLA chưa tương tác -> vào danh sách quá hạn",
       l3["id"] in [x["id"] for x in lead_service.list_overdue()])
    ok("l3 nhiệt độ nóng -> vào danh sách nóng",
       l3["id"] in [x["id"] for x in lead_service.list_hot()])
    lead_service.record_first_contact(l3["id"])
    ok("ghi tương tác đầu -> khỏi danh sách quá hạn",
       l3["id"] not in [x["id"] for x in lead_service.list_overdue()])

    print("== 6. Audit ==")
    with get_pg_pool().connection() as conn:
        n = conn.execute(
            "select count(*) as n from crm.audit_logs "
            "where object_type = 'leads' and object_id = any(%s)",
            ([l1["id"], l2["id"], l3["id"]],),
        ).fetchone()["n"]
        ok("mọi thao tác đều có vết audit (>= 8 dòng)", n >= 8, f"được {n}")

        don_dep(conn)
        con = conn.execute(
            f"select count(*) as n from crm.leads where source like '{DAU}%'"
        ).fetchone()["n"]
        ok("dọn sạch dữ liệu test", con == 0)

    print(f"\nKẾT QUẢ: {PASS} PASS / {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
