"""Truy vấn crm.handovers + crm.care_plans (B8 — FR-090/091).

Chỉ SQL — luật (tự động khi giao thành công, kiểm hồ sơ đủ/thiếu, trả lại
Sale) nằm ở services/handover_service.py. Ngày giao thành công KHÔNG lưu ở
handovers — luôn join lấy orders.delivered_at (comment trong schema).
"""

import json

from app.db.client import get_pg_pool

# Cột join dùng chung cho get/list — đúng các cột màn 24 cần
_CHON = """
    h.*,
    c.full_name              as customer_name,
    c.primary_phone          as customer_phone,
    o.external_order_id      as order_code,
    o.total_amount           as order_amount,
    o.delivered_at           as delivered_at,
    us.name                  as sale_name,
    uc.name                  as cskh_name,
    tt.name                  as treatment_name
"""
_TU = """
    from crm.handovers h
    join crm.customers c  on c.id = h.customer_id
    left join crm.orders o on o.id = h.order_id
    left join crm.users us on us.id = h.sale_user_id
    left join crm.users uc on uc.id = h.cskh_user_id
    left join crm.customer_treatments ct on ct.id = h.customer_treatment_id
    left join crm.treatment_templates tt on tt.id = ct.template_id
"""


def create(fields: dict) -> dict | None:
    """Chèn 1 phiếu; đơn đã có phiếu (uq_handovers_order) -> None, KHÔNG đè."""
    fields = {k: v for k, v in fields.items() if v is not None}
    if "missing_fields" in fields:
        fields["missing_fields"] = json.dumps(fields["missing_fields"],
                                              ensure_ascii=False)
    cot = list(fields)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"insert into crm.handovers ({', '.join(cot)}) "
            f"values ({', '.join(['%s'] * len(cot))}) "
            "on conflict (order_id) where order_id is not null do nothing "
            "returning *",
            list(fields.values()),
        ).fetchone()


def get(handover_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON} {_TU} where h.id = %s", (handover_id,)
        ).fetchone()


def get_by_order(order_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON} {_TU} where h.order_id = %s", (order_id,)
        ).fetchone()


def list_handovers(
    *, status: str = "", cskh_user_id: int | None = None,
    customer_id: int | None = None, limit: int = 20, offset: int = 0,
) -> tuple[list[dict], int]:
    """Màn 24 + HANDOVER-001. `status` rỗng = mọi trạng thái; 'cho' = chờ xử lý
    (pending + assigned + returned — các phiếu CHƯA ai nhận xong)."""
    dk, ts = ["1=1"], []
    if status == "cho":
        dk.append("h.status in ('pending','assigned','returned')")
    elif status:
        dk.append("h.status = %s")
        ts.append(status)
    if cskh_user_id:
        dk.append("h.cskh_user_id = %s")
        ts.append(cskh_user_id)
    if customer_id:
        dk.append("h.customer_id = %s")
        ts.append(customer_id)
    where = " and ".join(dk)
    pool = get_pg_pool()
    with pool.connection() as conn:
        total = conn.execute(
            f"select count(*) as n from crm.handovers h where {where}", ts
        ).fetchone()["n"]
        rows = conn.execute(
            f"select {_CHON} {_TU} where {where} "
            "order by h.created_at desc limit %s offset %s",
            [*ts, limit, offset],
        ).fetchall()
    return rows, total


def update(handover_id: int, fields: dict) -> dict | None:
    if not fields:
        return get(handover_id)
    fields = dict(fields)
    if "missing_fields" in fields:
        fields["missing_fields"] = json.dumps(fields["missing_fields"],
                                              ensure_ascii=False)
    dat = ", ".join(f"{cot} = %s" for cot in fields)
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            f"update crm.handovers set {dat} where id = %s",
            [*fields.values(), handover_id],
        )
    return get(handover_id)


def dem_theo_trang_thai() -> dict:
    """Số phiếu từng trạng thái — dải stat màn 24 + menu."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select status, count(*) as n from crm.handovers group by status"
        ).fetchall()
    return {r["status"]: r["n"] for r in rows}


def cskh_it_viec() -> dict | None:
    """CSKH active đang giữ ÍT phiếu chưa xong nhất — chia vòng tròn theo tải
    (cùng triết lý chia lead B3: đếm việc đang mở, không đếm lịch sử)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select u.id, u.name, count(h.id) as dang_giu
            from crm.users u
            join crm.roles r on r.id = u.role_id and r.name = 'CSKH'
            left join crm.handovers h on h.cskh_user_id = u.id
                 and h.status in ('pending','assigned','returned')
            where u.status = 'active'
            group by u.id, u.name
            order by count(h.id) asc, u.id asc
            limit 1
            """,
        ).fetchone()


# ------------------------------------------------------------------ care plan
def create_care_plan(
    *, customer_id: int, customer_treatment_id: int | None,
    owner_id: int | None,
) -> dict:
    """FR-090 "tạo hồ sơ chăm" — vỏ kế hoạch; mốc CS01-CS11 do B9 sinh."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.care_plans (customer_id, customer_treatment_id, owner_id) "
            "values (%s, %s, %s) returning *",
            (customer_id, customer_treatment_id, owner_id),
        ).fetchone()


def set_care_plan_owner(care_plan_id: int, owner_id: int | None) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.care_plans set owner_id = %s where id = %s",
            (owner_id, care_plan_id),
        )


# ---------------------------------------------------- dữ liệu mồi cho phiếu
def lieu_trinh_cua_don(order_id: int, customer_id: int) -> dict | None:
    """Liệu trình gắn ĐÚNG đơn này; không có thì liệu trình mới nhất còn sống
    của khách (planned/active) — nguồn chép 'thông tin liệu trình' FR-090."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """
            select ct.*, tt.name as template_name
            from crm.customer_treatments ct
            left join crm.treatment_templates tt on tt.id = ct.template_id
            where ct.order_id = %s
            order by ct.id desc limit 1
            """,
            (order_id,),
        ).fetchone()
        if row:
            return row
        return conn.execute(
            """
            select ct.*, tt.name as template_name
            from crm.customer_treatments ct
            left join crm.treatment_templates tt on tt.id = ct.template_id
            where ct.customer_id = %s and ct.status in ('planned','active')
            order by ct.id desc limit 1
            """,
            (customer_id,),
        ).fetchone()


def cach_dung_lieu_trinh(customer_treatment_id: int) -> str:
    """Ghép 'Sản phẩm × SL — cách dùng' từ items đã snapshot (B6)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            select p.name, i.quantity, i.dose_text
            from crm.customer_treatment_items i
            join crm.products p on p.id = i.product_id
            where i.customer_treatment_id = %s
            order by i.id
            """,
            (customer_treatment_id,),
        ).fetchall()
    dong = []
    for r in rows:
        sl = f" × {r['quantity']:g}" if r.get("quantity") is not None else ""
        cach = f" — {r['dose_text']}" if r.get("dose_text") else ""
        dong.append(f"{r['name']}{sl}{cach}")
    return "\n".join(dong)


def du_lieu_tu_van(customer_id: int) -> dict:
    """Mồi phiếu bàn giao từ hồ sơ tư vấn B5: triệu chứng, thuốc, bệnh nền."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        trieu_chung = conn.execute(
            """
            select s.name from crm.customer_symptoms cs
            join crm.symptoms s on s.id = cs.symptom_id
            where cs.customer_id = %s order by cs.id
            """,
            (customer_id,),
        ).fetchall()
        thuoc = conn.execute(
            "select name, dosage from crm.current_medications "
            "where customer_id = %s and is_active order by id",
            (customer_id,),
        ).fetchall()
        benh_nen = conn.execute(
            """
            select coalesce(nullif(value, ''), 'Có (chưa ghi rõ)') as mo_ta
            from crm.safety_screenings
            where customer_id = %s and screening_type = 'benh_nen'
              and cleared_at is null
            order by id desc limit 1
            """,
            (customer_id,),
        ).fetchone()
    return {
        "main_symptoms": ", ".join(r["name"] for r in trieu_chung),
        "current_medications": ", ".join(
            f"{r['name']} ({r['dosage']})" if r.get("dosage") else r["name"]
            for r in thuoc),
        "comorbidities": (benh_nen or {}).get("mo_ta") or "",
    }
