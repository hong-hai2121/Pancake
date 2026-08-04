"""Truy vấn Postgres cho đơn hàng B7 (crm.orders + items + history + ánh xạ POS).

Quy ước chung của tầng repo CRM: gọi thẳng get_pg_pool() (dict_row, autocommit),
schema prefix `crm.` viết tay trong MỌI câu lệnh, update dựng động qua whitelist.
Luật nghiệp vụ KHÔNG nằm ở đây — xem app/services/order_service.py.
"""

import json

from app.db.client import get_pg_pool

# Cột được phép ghi khi tạo/sửa đơn — chặn caller nhét cột lạ vào SQL.
_COT_DON = {
    "customer_id", "external_order_id", "order_type", "sale_owner_id",
    "cskh_owner_id", "status", "total_amount", "delivered_at", "note", "source",
    "pos_shop_id", "pos_order_id", "pos_status", "pos_conversation_id",
    "pos_page_id", "pos_inserted_at", "pos_updated_at", "pos_raw",
    "synced_at",   # mục 4: lần cuối dòng này được đồng bộ về
    # C7 — bản sao rút từ pos_raw để màn Đơn hàng lọc/xuất được (xem
    # init_crm.sql khối "C7 — MÀN ĐƠN HÀNG"); pos_sync._cot_pos_rut dựng bộ này
    "pos_display_id", "cod_amount", "prepaid_amount", "pos_ad_id",
    "pos_seller_id", "pos_seller_name",
}
# jsonb phải đi qua json.dumps + ::jsonb (giống catalog_repo)
_COT_JSONB = {"pos_raw"}


def _gia_tri(cot: str, v):
    """Đổi giá trị Python -> tham số SQL (jsonb thì dumps sẵn)."""
    if cot in _COT_JSONB and v is not None and not isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    return v


def _ep_kieu(cot: str) -> str:
    """Placeholder cho cột: jsonb cần ::jsonb, còn lại %s trơn."""
    return "%s::jsonb" if cot in _COT_JSONB else "%s"


# ------------------------------------------------------------------ tạo / đọc
def create_order(don: dict, items: list[dict]) -> dict:
    """Tạo đơn + dòng hàng + dòng lịch sử đầu tiên trong MỘT transaction.

    `don` chỉ nhận cột trong _COT_DON; `items` mỗi phần tử
    {product_id, treatment_template_id?, quantity, unit_price} — line_total tính
    luôn ở đây (= quantity*unit_price, giá TẠI THỜI ĐIỂM BÁN, không tra ngược).
    """
    gan = {k: v for k, v in don.items() if k in _COT_DON}
    cot = ", ".join(gan)
    cho = ", ".join(_ep_kieu(k) for k in gan)
    pool = get_pg_pool()
    with pool.connection() as conn, conn.transaction():
        row = conn.execute(
            f"insert into crm.orders ({cot}) values ({cho}) returning *",
            tuple(_gia_tri(k, v) for k, v in gan.items()),
        ).fetchone()
        for it in items:
            conn.execute(
                """
                insert into crm.order_items
                    (order_id, product_id, treatment_template_id, quantity,
                     unit_price, line_total)
                values (%s, %s, %s, %s, %s, %s)
                """,
                (
                    row["id"], it["product_id"], it.get("treatment_template_id"),
                    it["quantity"], it["unit_price"],
                    it["quantity"] * it["unit_price"],
                ),
            )
        conn.execute(
            "insert into crm.order_status_history "
            "(order_id, from_status, to_status, changed_by, reason) "
            "values (%s, null, %s, %s, %s)",
            (row["id"], row["status"], don.get("_changed_by"), don.get("_reason")),
        )
    return row


def get_order(order_id: int) -> dict | None:
    """1 đơn kèm tên khách (join) — None nếu không có."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select o.*, c.full_name as customer_name, c.primary_phone as customer_phone
              from crm.orders o
              join crm.customers c on c.id = o.customer_id
             where o.id = %s
            """,
            (order_id,),
        ).fetchone()


def find_by_pos(pos_shop_id: int, pos_order_id: int) -> dict | None:
    """Tìm đơn đã đồng bộ theo cặp định danh POS (unique index uq_orders_pos)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.orders where pos_shop_id = %s and pos_order_id = %s",
            (pos_shop_id, pos_order_id),
        ).fetchone()


def list_orders(
    *,
    status: str = "",
    order_type: str = "",
    customer_id: int | None = None,
    source: str = "",
    q: str = "",
    tu: str = "",
    den: str = "",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Danh sách đơn mới nhất trước + tổng số (cho màn 21).

    `q` tìm theo tên/điện thoại khách hoặc mã đơn ngoài; `tu`/`den` lọc
    created_at (ISO date, `den` là NGÀY BAO GỒM nên cộng 1 ngày ở service).
    """
    dieu_kien, tham_so = ["true"], []
    if status:
        dieu_kien.append("o.status = %s"); tham_so.append(status)
    if order_type:
        dieu_kien.append("o.order_type = %s"); tham_so.append(order_type)
    if customer_id is not None:
        dieu_kien.append("o.customer_id = %s"); tham_so.append(customer_id)
    if source:
        dieu_kien.append("o.source = %s"); tham_so.append(source)
    if q:
        dieu_kien.append(
            "(c.full_name ilike %s or c.primary_phone ilike %s "
            "or o.external_order_id ilike %s)")
        tham_so += [f"%{q}%"] * 3
    if tu:
        dieu_kien.append("o.created_at >= %s"); tham_so.append(tu)
    if den:
        dieu_kien.append("o.created_at < %s"); tham_so.append(den)
    where = " and ".join(dieu_kien)

    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"""
            select o.*, c.full_name as customer_name, c.primary_phone as customer_phone
              from crm.orders o
              join crm.customers c on c.id = o.customer_id
             where {where}
             order by o.created_at desc, o.id desc
             limit %s offset %s
            """,
            (*tham_so, limit, offset),
        ).fetchall()
        total = conn.execute(
            f"select count(*) as n from crm.orders o "
            f"join crm.customers c on c.id = o.customer_id where {where}",
            tham_so or None,
        ).fetchone()["n"]
    return rows, total


def list_items(order_id: int) -> list[dict]:
    """Dòng hàng của 1 đơn, kèm tên sản phẩm để hiển thị."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select i.*, p.name as product_name, p.product_code
              from crm.order_items i
              join crm.products p on p.id = i.product_id
             where i.order_id = %s
             order by i.id
            """,
            (order_id,),
        ).fetchall()


def list_history(order_id: int) -> list[dict]:
    """Nhật ký trạng thái cũ -> mới (KHÔNG bao giờ xoá — FR-080)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select h.*, u.name as changed_by_name
              from crm.order_status_history h
              left join crm.users u on u.id = h.changed_by
             where h.order_id = %s
             order by h.changed_at, h.id
            """,
            (order_id,),
        ).fetchall()


def count_prior_orders(
    customer_id: int,
    *,
    exclude_id: int | None = None,
    truoc_thoi_diem=None,
) -> int:
    """Số đơn TRƯỚC ĐÓ của khách, KHÔNG tính đơn hủy (phân loại đơn đầu/mua lại).

    Đơn hủy không tính là "đã mua" — khách đặt rồi hủy ngay thì đơn kế tiếp
    vẫn là đơn đầu (new), không phải mua lại.

    `truoc_thoi_diem`: chỉ đếm đơn có mốc tạo (pos_inserted_at, thiếu thì
    created_at) SỚM HƠN mốc này — bắt buộc khi đồng bộ/backfill POS vì đơn về
    KHÔNG theo thứ tự thời gian (trang 1 là đơn mới nhất); so theo thứ tự chèn
    vào DB sẽ dán nhãn ngược (đơn cũ thành "mua lại" của đơn mới).
    """
    dieu_kien = "customer_id = %s and status <> 'cancelled'"
    tham_so: list = [customer_id]
    if exclude_id is not None:
        dieu_kien += " and id <> %s"
        tham_so.append(exclude_id)
    if truoc_thoi_diem is not None:
        dieu_kien += " and coalesce(pos_inserted_at, created_at) < %s"
        tham_so.append(truoc_thoi_diem)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select count(*) as n from crm.orders where {dieu_kien}", tham_so
        ).fetchone()["n"]


# ------------------------------------------------------------------ cập nhật
def update_order(order_id: int, fields: dict) -> None:
    """Sửa cột trong whitelist (không đụng status — đổi trạng thái đi set_status)."""
    gan = {k: v for k, v in fields.items() if k in _COT_DON and k != "status"}
    if not gan:
        return
    dat = ", ".join(f"{k} = {_ep_kieu(k)}" for k in gan)
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            f"update crm.orders set {dat} where id = %s",
            (*(_gia_tri(k, v) for k, v in gan.items()), order_id),
        )


def set_status(
    order_id: int,
    to_status: str,
    *,
    changed_by: int | None = None,
    reason: str | None = None,
) -> dict | None:
    """Đổi trạng thái + ghi lịch sử ATOMIC (mẫu lead_repo).

    Đọc lại trạng thái hiện tại TRONG transaction (for update) để dòng lịch sử
    luôn khớp thực tế kể cả khi 2 nguồn (người + đồng bộ POS) đổi cùng lúc.
    Sang 'delivered' lần đầu thì đóng dấu delivered_at (mốc khởi tính CSKH).
    Trả về đơn sau cập nhật; None nếu đơn không tồn tại.
    """
    pool = get_pg_pool()
    with pool.connection() as conn, conn.transaction():
        cu = conn.execute(
            "select id, status from crm.orders where id = %s for update", (order_id,)
        ).fetchone()
        if cu is None:
            return None
        row = conn.execute(
            """
            update crm.orders
               set status = %s,
                   delivered_at = case when %s = 'delivered' and delivered_at is null
                                       then now() else delivered_at end
             where id = %s
            returning *
            """,
            (to_status, to_status, order_id),
        ).fetchone()
        conn.execute(
            "insert into crm.order_status_history "
            "(order_id, from_status, to_status, changed_by, reason) "
            "values (%s, %s, %s, %s, %s)",
            (order_id, cu["status"], to_status, changed_by, reason),
        )
    return row


def set_delivered_at(order_id: int, delivered_at) -> None:
    """Ghi đè mốc giao thành công bằng thời điểm THẬT từ POS (nếu POS có)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.orders set delivered_at = %s where id = %s",
            (delivered_at, order_id),
        )


# ------------------------------------------------------------------ tổng quan
def dem_theo_trang_thai() -> dict:
    """Đếm đơn theo trạng thái + theo loại (đầu/mua lại) cho màn 21."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        theo_status = conn.execute(
            "select status, count(*) as n from crm.orders group by status"
        ).fetchall()
        theo_loai = conn.execute(
            "select coalesce(order_type,'?') as order_type, count(*) as n "
            "from crm.orders group by order_type"
        ).fetchall()
    return {
        "theo_trang_thai": {r["status"]: r["n"] for r in theo_status},
        "theo_loai": {r["order_type"]: r["n"] for r in theo_loai},
    }


# ------------------------------------------------------------------ ánh xạ POS
def list_mappings() -> list[dict]:
    """Toàn bộ bảng ánh xạ POS -> CRM, kèm tên người sửa cuối (màn 23)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select m.*, u.name as updated_by_name
              from crm.order_status_mappings m
              left join crm.users u on u.id = m.updated_by
             order by m.pancake_status
            """
        ).fetchall()


def load_mapping_dict() -> dict[int, str]:
    """{mã POS: trạng thái CRM} — đồng bộ đọc MỖI LẦN chạy, admin sửa là ăn ngay."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select pancake_status, crm_status from crm.order_status_mappings"
        ).fetchall()
    return {r["pancake_status"]: r["crm_status"] for r in rows}


def update_mapping(pancake_status: int, fields: dict, updated_by: int | None) -> dict | None:
    """Sửa 1 dòng ánh xạ (crm_status/note). None nếu mã POS chưa có trong bảng."""
    gan = {k: v for k, v in fields.items() if k in {"crm_status", "note"}}
    if not gan:
        return None
    dat = ", ".join(f"{k} = %s" for k in gan)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"update crm.order_status_mappings set {dat}, updated_by = %s "
            f"where pancake_status = %s returning *",
            (*gan.values(), updated_by, pancake_status),
        ).fetchone()
