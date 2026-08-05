"""Truy vấn Đợt 3 — luồng tự động (`crm.auto_flows`, `crm.auto_flow_runs`).

Chỉ SQL. Luật (mốc neo · điều kiện · chạy khô) nằm ở `services/auto_flow.py`.

🔴 File này KHÔNG có hàm nào gửi tin, và cũng không được có. Xem đầu
`services/auto_flow.py`.
"""

import json

from app.db.client import get_pg_pool


# ------------------------------------------------------------------ luồng
def tat_ca() -> list[dict]:
    """Cả luồng đang tắt — màn cấu hình phải thấy hết để bật lại được."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select f.*, t.name as template_name, s.title as script_title,
                   (select count(*) from crm.auto_flow_runs r
                     where r.auto_flow_id = f.id) as so_lan_chay
              from crm.auto_flows f
              left join crm.message_templates t on t.id = f.template_id
              left join crm.sale_scripts s on s.id = f.script_id
             order by f.id desc
            """
        ).fetchall()


def get(flow_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.auto_flows where id = %s", (flow_id,)
        ).fetchone()


def dang_chay() -> list[dict]:
    """Luồng đang BẬT. Lưu ý: "bật" ở đây nghĩa là được tính khi chạy khô —
    KHÔNG có nghĩa là được gửi tin (xem docstring bảng)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.auto_flows where status = 'active' order by id"
        ).fetchall()


def luu(flow_id: int | None, **f) -> dict:
    """Thêm mới (flow_id rỗng) hoặc sửa. Trường nào không truyền thì giữ nguyên
    — cùng nếp với `sale_repo.luu_buoc`."""
    cot = ("name", "kind", "status", "su_kien", "so_ngay", "lech", "moc_neo",
           "truong", "truong_gia_tri", "khop", "template_id", "script_id",
           "gio_quet", "tao_viec")
    ts = {c: f.get(c) for c in cot}
    ts["dieu_kien"] = json.dumps(f.get("dieu_kien") or [], ensure_ascii=False)
    ts["id"] = flow_id
    ts["boi"] = f.get("created_by")
    pool = get_pg_pool()
    with pool.connection() as conn:
        if flow_id:
            dat = ", ".join(
                f"{c} = coalesce(%({c})s, {c})" for c in cot
                if c not in ("lech", "tao_viec", "khop", "kind", "status"))
            return conn.execute(
                f"""
                update crm.auto_flows set {dat},
                       kind = coalesce(%(kind)s::text, kind),
                       status = coalesce(%(status)s::text, status),
                       khop = coalesce(%(khop)s::text, khop),
                       lech = coalesce(%(lech)s::int, lech),
                       tao_viec = coalesce(%(tao_viec)s::boolean, tao_viec),
                       dieu_kien = %(dieu_kien)s::jsonb
                 where id = %(id)s returning *
                """, ts,
            ).fetchone()
        return conn.execute(
            """
            insert into crm.auto_flows
                   (name, kind, status, su_kien, so_ngay, lech, moc_neo,
                    truong, truong_gia_tri, khop, dieu_kien, template_id,
                    script_id, gio_quet, tao_viec, created_by)
            values (coalesce(%(name)s, ''), coalesce(%(kind)s, 'lech_ngay'),
                    coalesce(%(status)s, 'inactive'), %(su_kien)s, %(so_ngay)s,
                    coalesce(%(lech)s, 0), %(moc_neo)s, %(truong)s,
                    %(truong_gia_tri)s, coalesce(%(khop)s, 'all'),
                    %(dieu_kien)s::jsonb, %(template_id)s, %(script_id)s,
                    %(gio_quet)s, coalesce(%(tao_viec)s, false), %(boi)s)
            returning *
            """, ts,
        ).fetchone()


def doi_trang_thai(flow_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.auto_flows set status = case when status = 'active' "
            "then 'inactive' else 'active' end where id = %s returning *",
            (flow_id,),
        ).fetchone()


def xoa(flow_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("delete from crm.auto_flows where id = %s", (flow_id,))


# ------------------------------------------------------------- lượt chạy khô
def ghi_lan_chay(flow_id: int, *, so_trung: int, so_bo_qua: int,
                 chi_tiet: list[dict], boi: int | None = None) -> dict:
    """Ghi một lượt CHẠY KHÔ. `che_do` cố định 'kho' — không có tham số để
    truyền 'that' vào, đúng ý đồ: chưa đường nào gửi được thì cũng không nên có
    cách ghi nhật ký nói rằng đã gửi."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("update crm.auto_flows set lan_chay_cuoi = now() "
                     "where id = %s", (flow_id,))
        return conn.execute(
            """
            insert into crm.auto_flow_runs
                   (auto_flow_id, che_do, so_trung, so_bo_qua, chi_tiet, boi)
            values (%s, 'kho', %s, %s, %s::jsonb, %s) returning *
            """,
            (flow_id, so_trung, so_bo_qua,
             json.dumps(chi_tiet, ensure_ascii=False, default=str), boi),
        ).fetchone()


# --------------------------------------------------------------- sinh VIỆC
def da_sinh_viec_hom_nay(flow_id: int) -> set[int]:
    """Khách đã được luồng này sinh việc TRONG NGÀY (giờ VN). Worker chạy nhiều
    lượt một ngày thì lượt sau bỏ qua họ."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select customer_id from crm.auto_flow_tasks "
            "where auto_flow_id = %s "
            "and ngay = (now() at time zone 'Asia/Ho_Chi_Minh')::date",
            (flow_id,),
        ).fetchall()
    return {int(r["customer_id"]) for r in rows}


def con_viec_mo(flow_id: int) -> set[int]:
    """Khách còn việc CHƯA LÀM XONG do chính luồng này sinh ra.

    Không nhắc lại khi việc cũ còn nằm đó: nhân viên mở bảng thấy ba việc y hệt
    cho cùng một khách thì họ ngừng tin cả bảng việc.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            select ft.customer_id from crm.auto_flow_tasks ft
              join crm.tasks t on t.id = ft.task_id
             where ft.auto_flow_id = %s and t.status = 'open'
            """, (flow_id,),
        ).fetchall()
    return {int(r["customer_id"]) for r in rows}


def ghi_viec(flow_id: int, customer_id: int, task_id: int | None) -> None:
    """Đóng dấu "luồng này đã sinh việc cho khách này hôm nay".

    `on conflict do nothing` chứ không kiểm trước rồi ghi: hai lượt worker chạy
    chồng nhau thì phép kiểm-rồi-ghi vẫn lọt, chỉ ràng buộc ở DB mới chắc.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "insert into crm.auto_flow_tasks (auto_flow_id, customer_id, "
            "task_id) values (%s, %s, %s) on conflict do nothing",
            (flow_id, customer_id, task_id))


def viec_cua_luong(flow_id: int, limit: int = 50) -> list[dict]:
    """Việc luồng này đã sinh — để màn hình trả lời "việc kia ở đâu ra"."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select ft.ngay, ft.created_at, c.full_name, c.primary_phone,
                   t.id as task_id, t.status, t.title, u.name as nguoi
              from crm.auto_flow_tasks ft
              join crm.customers c on c.id = ft.customer_id
              left join crm.tasks t on t.id = ft.task_id
              left join crm.users u on u.id = t.assigned_to
             where ft.auto_flow_id = %s
             order by ft.id desc limit %s
            """, (flow_id, limit),
        ).fetchall()


def lan_chay(flow_id: int, limit: int = 10) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.auto_flow_runs where auto_flow_id = %s "
            "order by id desc limit %s", (flow_id, limit),
        ).fetchall()
