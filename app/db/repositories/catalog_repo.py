"""SQL danh mục sản phẩm & liệu trình (B6 — FR-060…062).

products/product_versions · treatment_templates/items/rules ·
treatment_recommendations · customer_treatments(+items). Luật (versioning giá,
duyệt nội dung, rule engine, chặn cờ đỏ...) nằm ở services/product_service.py
và services/treatment_service.py.
"""

import json

from app.db.client import get_pg_pool


# ------------------------------------------------------------------ sản phẩm
def list_products(
    *, q: str = "", status: str = "", limit: int = 50, offset: int = 0,
) -> tuple[list[dict], int]:
    dieu_kien, tham_so = ["true"], []
    if q:
        dieu_kien.append("(p.name ilike %s or p.product_code ilike %s)")
        tham_so += [f"%{q}%"] * 2
    if status:
        dieu_kien.append("p.status = %s")
        tham_so.append(status)
    where = " and ".join(dieu_kien)
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"select p.* from crm.products p where {where} "
            "order by p.name limit %s offset %s",
            (*tham_so, limit, offset),
        ).fetchall()
        total = conn.execute(
            f"select count(*) as n from crm.products p where {where}",
            tham_so or None,
        ).fetchone()["n"]
    return rows, total


def get_product(product_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.products where id = %s", (product_id,)
        ).fetchone()


def create_product(fields: dict) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.products (product_code, name, product_type, price,
                                      package, units_per_package)
            values (%s, %s, %s, %s, %s, %s) returning *
            """,
            (fields.get("product_code"), fields["name"],
             fields.get("product_type"), fields.get("price"),
             fields.get("package"), fields.get("units_per_package")),
        ).fetchone()


def update_product(product_id: int, fields: dict) -> None:
    cho_phep = {"product_code", "name", "product_type", "price", "package",
                "units_per_package"}
    gan = {k: v for k, v in fields.items() if k in cho_phep}
    if not gan:
        return
    dat = ", ".join(f"{k} = %s" for k in gan)
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            f"update crm.products set {dat} where id = %s",
            (*gan.values(), product_id),
        )


def set_product_status(product_id: int, status: str) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.products set status = %s where id = %s",
            (status, product_id),
        )


def set_product_approval(product_id: int, approval: str) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.products set approval_status = %s where id = %s",
            (approval, product_id),
        )


def add_product_version(
    product_id: int, *, price, usage_text: str | None,
    approved_claims: list | None, prohibited_claims: list | None,
) -> dict:
    """Snapshot phiên bản mới: đóng hiệu lực bản trước, version_no tự tăng."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute(
                "update crm.product_versions set effective_to = now() "
                "where product_id = %s and effective_to is null",
                (product_id,),
            )
            return conn.execute(
                """
                insert into crm.product_versions
                       (product_id, version_no, price, usage_text,
                        approved_claims, prohibited_claims)
                select %s, coalesce(max(version_no), 0) + 1, %s, %s,
                       %s::jsonb, %s::jsonb
                  from crm.product_versions where product_id = %s
                returning *
                """,
                (product_id, price, usage_text,
                 json.dumps(approved_claims or [], ensure_ascii=False),
                 json.dumps(prohibited_claims or [], ensure_ascii=False),
                 product_id),
            ).fetchone()


def list_product_versions(product_id: int) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.product_versions where product_id = %s "
            "order by version_no desc",
            (product_id,),
        ).fetchall()


def product_co_don(product_id: int) -> bool:
    """FR-060 'không xoá sản phẩm đã có đơn' — kiểm trước khi discontinued."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select 1 from crm.order_items where product_id = %s limit 1",
            (product_id,),
        ).fetchone() is not None


# ------------------------------------------------------------------ mẫu liệu trình
def list_templates(
    *, q: str = "", status: str = "", problem_group: str = "",
    limit: int = 50, offset: int = 0,
) -> tuple[list[dict], int]:
    dieu_kien, tham_so = ["true"], []
    if q:
        dieu_kien.append("(t.name ilike %s or t.template_code ilike %s)")
        tham_so += [f"%{q}%"] * 2
    if status:
        dieu_kien.append("t.status = %s")
        tham_so.append(status)
    if problem_group:
        dieu_kien.append("t.problem_group = %s")
        tham_so.append(problem_group)
    where = " and ".join(dieu_kien)
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"""
            select t.*,
                   (select count(*) from crm.treatment_template_items i
                     where i.template_id = t.id) as so_san_pham,
                   (select count(*) from crm.treatment_rules r
                     where r.template_id = t.id and r.status = 'active') as so_luat
              from crm.treatment_templates t where {where}
             order by t.name limit %s offset %s
            """,
            (*tham_so, limit, offset),
        ).fetchall()
        total = conn.execute(
            f"select count(*) as n from crm.treatment_templates t where {where}",
            tham_so or None,
        ).fetchone()["n"]
    return rows, total


def get_template(template_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        tpl = conn.execute(
            "select * from crm.treatment_templates where id = %s", (template_id,)
        ).fetchone()
        if not tpl:
            return None
        items = conn.execute(
            """
            select i.*, p.name as product_name, p.product_code
              from crm.treatment_template_items i
              join crm.products p on p.id = i.product_id
             where i.template_id = %s order by i.sort_order, i.id
            """,
            (template_id,),
        ).fetchall()
        rules = conn.execute(
            "select * from crm.treatment_rules where template_id = %s "
            "order by priority desc, id",
            (template_id,),
        ).fetchall()
    return {**tpl, "items": items, "rules": rules}


def create_template(fields: dict) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.treatment_templates
                   (template_code, name, problem_group, level, base_price,
                    duration_days, status)
            values (%s, %s, %s, %s, %s, %s, coalesce(%s, 'draft'))
            returning *
            """,
            (fields["template_code"], fields["name"],
             fields.get("problem_group"), fields.get("level"),
             fields.get("base_price"), fields.get("duration_days"),
             fields.get("status")),
        ).fetchone()


def update_template(template_id: int, fields: dict) -> None:
    cho_phep = {"name", "problem_group", "level", "base_price",
                "duration_days", "status"}
    gan = {k: v for k, v in fields.items() if k in cho_phep}
    if not gan:
        return
    dat = ", ".join(f"{k} = %s" for k in gan)
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            f"update crm.treatment_templates set {dat} where id = %s",
            (*gan.values(), template_id),
        )


def add_template_item(template_id: int, fields: dict) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.treatment_template_items
                   (template_id, product_id, quantity, dose_text, sort_order)
            values (%s, %s, %s, %s, %s) returning *
            """,
            (template_id, fields["product_id"], fields["quantity"],
             fields.get("dose_text"), fields.get("sort_order", 0)),
        ).fetchone()


def update_template_item(item_id: int, template_id: int, fields: dict) -> dict | None:
    cho_phep = {"quantity", "dose_text", "sort_order"}
    gan = {k: v for k, v in fields.items() if k in cho_phep and v is not None}
    if not gan:
        return None
    dat = ", ".join(f"{k} = %s" for k in gan)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"update crm.treatment_template_items set {dat} "
            "where id = %s and template_id = %s returning *",
            (*gan.values(), item_id, template_id),
        ).fetchone()


# ------------------------------------------------------------------ luật liệu trình
def add_rule(template_id: int, fields: dict) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.treatment_rules
                   (template_id, rule_type, condition_json, action_json, priority)
            values (%s, %s, %s::jsonb, %s::jsonb, %s) returning *
            """,
            (template_id, fields["rule_type"],
             json.dumps(fields.get("condition") or {}, ensure_ascii=False),
             json.dumps(fields.get("action") or {}, ensure_ascii=False),
             fields.get("priority", 0)),
        ).fetchone()


def list_rules(template_id: int, *, chi_active: bool = False) -> list[dict]:
    them = "and status = 'active'" if chi_active else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select * from crm.treatment_rules where template_id = %s {them} "
            "order by priority desc, id",
            (template_id,),
        ).fetchall()


def list_active_templates_with_rules() -> list[dict]:
    """Đầu vào rule engine FR-062: mọi template active kèm luật active."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        tpls = conn.execute(
            "select * from crm.treatment_templates where status = 'active' "
            "order by name"
        ).fetchall()
        rules = conn.execute(
            """
            select r.* from crm.treatment_rules r
              join crm.treatment_templates t on t.id = r.template_id
             where t.status = 'active' and r.status = 'active'
             order by r.priority desc, r.id
            """
        ).fetchall()
    theo_tpl: dict[int, list[dict]] = {}
    for r in rules:
        theo_tpl.setdefault(r["template_id"], []).append(r)
    return [{**t, "rules": theo_tpl.get(t["id"], [])} for t in tpls]


# ------------------------------------------------------------------ đề xuất
def create_recommendation(
    *, customer_id: int, template_id: int, recommended_by: int | None,
    status: str, needs_approval: bool, reasons: list, warnings: list,
    missing_info: list, note: str | None,
) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.treatment_recommendations
                   (customer_id, template_id, recommended_by, status,
                    needs_approval, reasons, warnings, missing_info, note)
            values (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            returning *
            """,
            (customer_id, template_id, recommended_by, status, needs_approval,
             json.dumps(reasons, ensure_ascii=False),
             json.dumps(warnings, ensure_ascii=False),
             json.dumps(missing_info, ensure_ascii=False), note),
        ).fetchone()


def get_recommendation(rec_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select r.*, t.name as template_name, c.full_name as customer_name
              from crm.treatment_recommendations r
              join crm.treatment_templates t on t.id = r.template_id
              join crm.customers c on c.id = r.customer_id
             where r.id = %s
            """,
            (rec_id,),
        ).fetchone()


def set_recommendation_status(
    rec_id: int, *, status: str, approved_by: int | None = None,
    note: str | None = None,
) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            update crm.treatment_recommendations
               set status = %s,
                   approved_by = coalesce(%s, approved_by),
                   approved_at = case when %s in ('approved','rejected')
                                      then now() else approved_at end,
                   note = coalesce(%s, note)
             where id = %s
            """,
            (status, approved_by, status, note, rec_id),
        )


# ------------------------------------------------------------------ liệu trình khách
def create_customer_treatment(
    *, customer_id: int, template_id: int, order_id: int | None,
    approved_by: int | None, start_date, expected_end_date,
) -> dict:
    """Tạo liệu trình + SNAPSHOT items từ mẫu (đổi mẫu sau này không sửa
    liệu trình đang chạy)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        with conn.transaction():
            ct = conn.execute(
                """
                insert into crm.customer_treatments
                       (customer_id, template_id, order_id, approved_by,
                        start_date, expected_end_date)
                values (%s, %s, %s, %s, %s, %s) returning *
                """,
                (customer_id, template_id, order_id, approved_by,
                 start_date, expected_end_date),
            ).fetchone()
            conn.execute(
                """
                insert into crm.customer_treatment_items
                       (customer_treatment_id, product_id, quantity, dose_text)
                select %s, product_id, quantity, dose_text
                  from crm.treatment_template_items where template_id = %s
                """,
                (ct["id"], template_id),
            )
    return ct


def get_customer_treatment(ct_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        ct = conn.execute(
            """
            select ct.*, t.name as template_name, t.duration_days,
                   c.full_name as customer_name
              from crm.customer_treatments ct
              left join crm.treatment_templates t on t.id = ct.template_id
              join crm.customers c on c.id = ct.customer_id
             where ct.id = %s
            """,
            (ct_id,),
        ).fetchone()
        if not ct:
            return None
        items = conn.execute(
            """
            select i.*, p.name as product_name
              from crm.customer_treatment_items i
              join crm.products p on p.id = i.product_id
             where i.customer_treatment_id = %s order by i.id
            """,
            (ct_id,),
        ).fetchall()
    return {**ct, "items": items}


def update_customer_treatment(ct_id: int, fields: dict) -> None:
    cho_phep = {"start_date", "expected_end_date", "status"}
    gan = {k: v for k, v in fields.items() if k in cho_phep and v is not None}
    if not gan:
        return
    dat = ", ".join(f"{k} = %s" for k in gan)
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            f"update crm.customer_treatments set {dat} where id = %s",
            (*gan.values(), ct_id),
        )
