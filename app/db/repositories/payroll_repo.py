"""Truy vấn C2 — lương · thưởng · đối soát (port mẫu Kallet luong*.php,
doi-soat.php).

Chỉ SQL. Ba luật dễ hỏng (thưởng chăm CHỒNG hoa hồng · thưởng nóng 2 kiểu cộng
dồn · đơn hoàn trừ KỲ SAU) nằm ở services/payroll_service.py.
"""

from app.core.ngay import hom_nay
from app.db.client import get_pg_pool


# ------------------------------------------------------------------ cấu hình
def bac_hoa_hong(role_id: int | None = None) -> list[dict]:
    """Bậc hoa hồng, ngưỡng TĂNG DẦN (service duyệt xuôi rồi lấy bậc cuối khớp)."""
    dk = "where t.role_id = %s" if role_id else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select t.*, r.name as role_name from crm.commission_tiers t "
            f"join crm.roles r on r.id = t.role_id {dk} "
            "order by t.role_id, t.min_revenue asc, t.sort_order asc",
            (role_id,) if role_id else None,
        ).fetchall()


def bac_thuong_cham(role_id: int | None = None) -> list[dict]:
    dk = "where t.role_id = %s" if role_id else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select t.*, r.name as role_name from crm.care_bonus_tiers t "
            f"join crm.roles r on r.id = t.role_id {dk} "
            "order by t.role_id, t.min_revenue asc, t.sort_order asc",
            (role_id,) if role_id else None,
        ).fetchall()


def bac_thuong_nong(role_id: int | None = None) -> list[dict]:
    dk = "where t.role_id = %s" if role_id else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select t.*, r.name as role_name from crm.hot_bonus_tiers t "
            f"join crm.roles r on r.id = t.role_id {dk} "
            "order by t.role_id, t.basis, t.threshold asc, t.sort_order asc",
            (role_id,) if role_id else None,
        ).fetchall()


def luu_bac(bang: str, **f) -> dict:
    """Thêm 1 bậc vào `commission_tiers` / `care_bonus_tiers` / `hot_bonus_tiers`."""
    if bang == "hot_bonus_tiers":
        cot = "(role_id, basis, threshold, kind, value, sort_order)"
        gia = "(%(role_id)s, %(basis)s, %(threshold)s, %(kind)s, %(value)s, %(sort_order)s)"
    elif bang in ("commission_tiers", "care_bonus_tiers"):
        cot = "(role_id, min_revenue, kind, value, sort_order)"
        gia = "(%(role_id)s, %(min_revenue)s, %(kind)s, %(value)s, %(sort_order)s)"
    else:
        raise ValueError(f"Bang la: {bang}")
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"insert into crm.{bang} {cot} values {gia} returning *", f
        ).fetchone()


def xoa_bac(bang: str, bac_id: int) -> None:
    if bang not in ("commission_tiers", "care_bonus_tiers", "hot_bonus_tiers"):
        raise ValueError(f"Bang la: {bang}")
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(f"delete from crm.{bang} where id = %s", (bac_id,))


def luong_cung(user_id: int) -> float:
    """Lương cứng có hiệu lực: của RIÊNG người này, thiếu thì lấy của vai trò."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            "select coalesce(u.base_salary, r.base_salary, 0) as tien "
            "from crm.users u left join crm.roles r on r.id = u.role_id "
            "where u.id = %s", (user_id,),
        ).fetchone()
    return float(r["tien"]) if r else 0.0


# ------------------------------------------------------------------ đơn của kỳ
_DON_KY = """
    from crm.orders o
   where o.payroll_period = %(ky)s
     and coalesce(o.sale_owner_id, o.cskh_owner_id) = %(nv)s
"""


def don_trong_ky(user_id: int, ky: str) -> list[dict]:
    """Mọi đơn tính vào kỳ lương của một người (cả đơn đã hoàn — service lọc)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select o.id, o.external_order_id, o.pos_order_id, o.status,
                   o.total_amount, o.order_type, o.effort_axis, o.ads_attributed,
                   o.classified_manually, o.classify_reason, o.delivered_at,
                   o.created_at, o.customer_id,
                   c.full_name as customer_name, c.primary_phone as customer_phone,
                   rv.status as review_status, rv.amount as review_amount,
                   rv.reason as review_reason
              from crm.orders o
              join crm.customers c on c.id = o.customer_id
              left join crm.care_bonus_reviews rv on rv.order_id = o.id
             where o.payroll_period = %(ky)s
               and coalesce(o.sale_owner_id, o.cskh_owner_id) = %(nv)s
             order by o.delivered_at desc nulls last, o.id desc
            """,
            {"ky": ky, "nv": user_id},
        ).fetchall()


def doanh_thu_theo_ngay(user_id: int, ky: str) -> list[dict]:
    """Doanh thu ĐÃ THU gom theo NGÀY — nền cho thưởng nóng kiểu doanh_thu_ngay.

    Gom theo ngày GIỜ VN (delivered_at là timestamptz, DB chạy UTC) — không đổi
    múi giờ thì đơn giao buổi tối bị tính sang ngày hôm sau, thưởng nóng lệch."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select (o.delivered_at at time zone 'Asia/Ho_Chi_Minh')::date as ngay,
                   sum(o.total_amount) as tien,
                   count(*) as so_don
              {_DON_KY} and o.status in ('delivered','collected')
             group by 1 order by 1
            """,
            {"ky": ky, "nv": user_id},
        ).fetchall()


def tong_hop_ky(user_id: int, ky: str) -> dict:
    """Doanh thu LÊN ĐƠN vs ĐÃ THU + số đơn — hai con số này luôn phải đi kèm
    nhãn rõ ràng trên giao diện (luật vàng B3.1 của mẫu)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select coalesce(sum(o.total_amount) filter (
                       where o.status not in ('cancelled','draft')), 0) as len_don,
                   coalesce(sum(o.total_amount) filter (
                       where o.status in ('delivered','collected')), 0) as da_thu,
                   count(*) filter (
                       where o.status in ('delivered','collected'))     as so_don,
                   count(*) filter (
                       where o.status in ('returned','returning'))      as so_don_hoan
              {_DON_KY}
            """,
            {"ky": ky, "nv": user_id},
        ).fetchone()


def dat_ky_luong(order_id: int, ky: str) -> None:
    """Ghi CỨNG kỳ lương cho đơn lúc giao thành công."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("update crm.orders set payroll_period = %s where id = %s",
                     (ky, order_id))


def phan_loai(order_id: int, *, effort_axis: str | None = None,
              ads_attributed: bool | None = None, bang_tay: bool = False,
              ly_do: str = "", nguoi: int | None = None) -> dict | None:
    """Đổi phân loại đơn. `bang_tay=True` thì máy THÔI tự đổi đơn này về sau."""
    dat, ts = [], {"id": order_id}
    if effort_axis is not None:
        dat.append("effort_axis = %(cs)s")
        ts["cs"] = effort_axis
    if ads_attributed is not None:
        dat.append("ads_attributed = %(qc)s")
        ts["qc"] = ads_attributed
    if bang_tay:
        dat += ["classified_manually = true", "classify_reason = %(ld)s",
                "classified_by = %(nv)s", "classified_at = now()"]
        ts["ld"], ts["nv"] = ly_do, nguoi
    if not dat:
        return None
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"update crm.orders set {', '.join(dat)} where id = %(id)s returning *",
            ts,
        ).fetchone()


# ------------------------------------------------------------------ đối soát
def don_cho_doi_soat(*, ro: str = "all", limit: int = 300) -> list[dict]:
    """Đơn ứng viên thưởng chăm sóc + rổ suy từ DB.

    3 rổ của mẫu: `fixed` (người đã sửa tay phân loại) · `wonder` (máy tự phân,
    chưa ai xác nhận) · `done` (đã duyệt/bác). Rổ suy ra lúc đọc, KHÔNG lưu cột
    riêng — lưu cột là có ngày lệch với sự thật."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            select o.id, o.external_order_id, o.pos_order_id, o.total_amount,
                   o.effort_axis, o.ads_attributed, o.classified_manually,
                   o.classify_reason, o.classified_at, o.payroll_period,
                   o.customer_id, c.full_name as customer_name,
                   nv.id as staff_id, nv.name as staff_name,
                   nv.role_id as staff_role_id,
                   rv.status as review_status, rv.amount as review_amount,
                   rv.reason as review_reason, rv.reviewed_at,
                   ng.name as reviewed_by_name,
                   pr.frozen as ky_da_chot
              from crm.orders o
              join crm.customers c on c.id = o.customer_id
              left join crm.users nv on nv.id = coalesce(o.sale_owner_id,
                                                         o.cskh_owner_id)
              left join crm.care_bonus_reviews rv on rv.order_id = o.id
              left join crm.users ng on ng.id = rv.reviewed_by
              left join crm.payrolls pr on pr.user_id = nv.id
                                       and pr.period = o.payroll_period
             where o.effort_axis = 'cham_soc'
             order by (rv.status is not null) asc,
                      o.classified_manually desc,
                      o.delivered_at desc nulls last, o.id desc
             limit %s
            """,
            (limit,),
        ).fetchall()
    ra = []
    for r in rows:
        d = dict(r)
        d["ro"] = ("done" if d["review_status"]
                   else ("fixed" if d["classified_manually"] else "wonder"))
        ra.append(d)
    return ra if ro in ("", "all") else [d for d in ra if d["ro"] == ro]


def duyet_thuong(order_id: int, *, so_tien, nguoi: int | None) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.care_bonus_reviews
                   (order_id, status, amount, reason, reviewed_by)
            values (%s, 'duyet', %s, '', %s)
            on conflict (order_id) do update set
                status = 'duyet', amount = excluded.amount, reason = '',
                reviewed_by = excluded.reviewed_by, reviewed_at = now()
            returning *
            """,
            (order_id, so_tien, nguoi),
        ).fetchone()


def bac_thuong(order_id: int, ly_do: str, *, nguoi: int | None) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.care_bonus_reviews
                   (order_id, status, amount, reason, reviewed_by)
            values (%s, 'tu_choi', 0, %s, %s)
            on conflict (order_id) do update set
                status = 'tu_choi', amount = 0, reason = excluded.reason,
                reviewed_by = excluded.reviewed_by, reviewed_at = now()
            returning *
            """,
            (order_id, ly_do, nguoi),
        ).fetchone()


def xoa_duyet(order_id: int) -> None:
    """Đơn rời khỏi diện thưởng chăm (đổi phân loại) thì huỷ luôn phiếu duyệt."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("delete from crm.care_bonus_reviews where order_id = %s",
                     (order_id,))


def thuong_cham_da_duyet(user_id: int, ky: str) -> float:
    """Tổng thưởng chăm ĐÃ DUYỆT của một người trong kỳ — chỉ đơn được duyệt
    mới vào lương, đơn chờ duyệt KHÔNG tính."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            f"""
            select coalesce(sum(rv.amount), 0) as tien
              from crm.orders o
              join crm.care_bonus_reviews rv on rv.order_id = o.id
             where o.payroll_period = %(ky)s
               and coalesce(o.sale_owner_id, o.cskh_owner_id) = %(nv)s
               and rv.status = 'duyet'
            """,
            {"ky": ky, "nv": user_id},
        ).fetchone()
    return float(r["tien"])


# ------------------------------------------------------------------ bảng lương
def get_payroll(user_id: int, ky: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.payrolls where user_id = %s and period = %s",
            (user_id, ky),
        ).fetchone()


def luu_payroll(user_id: int, ky: str, so: dict) -> dict:
    """Ghi/cập nhật một dòng lương. Kỳ ĐÃ CHỐT (frozen) thì giữ nguyên số cũ —
    chặn ngay ở SQL để worker chạy lại không ghi đè kỳ đã trả tiền."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.payrolls
                   (user_id, period, base_salary, revenue_booked,
                    revenue_collected, commission, care_bonus, hot_bonus,
                    adjustment, total)
            values (%(nv)s, %(ky)s, %(luong_cung)s, %(len_don)s, %(da_thu)s,
                    %(hoa_hong)s, %(thuong_cham)s, %(thuong_nong)s,
                    %(dieu_chinh)s, %(tong)s)
            on conflict (user_id, period) do update set
                base_salary = excluded.base_salary,
                revenue_booked = excluded.revenue_booked,
                revenue_collected = excluded.revenue_collected,
                commission = excluded.commission,
                care_bonus = excluded.care_bonus,
                hot_bonus = excluded.hot_bonus,
                adjustment = excluded.adjustment,
                total = excluded.total
              where not crm.payrolls.frozen
            returning *
            """,
            {"nv": user_id, "ky": ky, **so},
        ).fetchone() or get_payroll(user_id, ky)


def bang_luong(ky: str) -> list[dict]:
    """Bảng lương TOÀN ĐỘI của một kỳ (màn Lương thưởng)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select p.*, u.name as staff_name, u.username, r.name as role_name
              from crm.payrolls p
              join crm.users u on u.id = p.user_id
              left join crm.roles r on r.id = u.role_id
             where p.period = %s
             order by p.total desc, u.name
            """,
            (ky,),
        ).fetchall()


def cac_ky() -> list[str]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select distinct period from crm.payrolls order by period desc limit 36"
        ).fetchall()
    return [r["period"] for r in rows]


def chot_ky(ky: str, nguoi: int | None) -> int:
    """Đóng băng cả kỳ. Sau bước này mọi thay đổi phải đi qua điều chỉnh kỳ sau."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            "update crm.payrolls set frozen = true, closed_at = now(), "
            "closed_by = %s where period = %s and not frozen",
            (nguoi, ky),
        )
        return cur.rowcount or 0


def dieu_chinh(user_id: int, ky: str) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select a.*, o.external_order_id, o.pos_order_id "
            "from crm.payroll_adjustments a "
            "left join crm.orders o on o.id = a.order_id "
            "where a.user_id = %s and a.period = %s order by a.id",
            (user_id, ky),
        ).fetchall()


def them_dieu_chinh(user_id: int, ky: str, so_tien, ly_do: str, *,
                    order_id: int | None = None,
                    nguoi: int | None = None) -> dict | None:
    """Thêm khoản cộng/trừ vào kỳ. Gắn `order_id` thì mỗi đơn chỉ vào MỘT lần
    (unique index) — worker truy thu chạy lại không nhân đôi khoản trừ."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.payroll_adjustments "
            "(user_id, period, order_id, amount, reason, created_by) "
            "values (%s, %s, %s, %s, %s, %s) "
            "on conflict (order_id) where order_id is not null do nothing "
            "returning *",
            (user_id, ky, order_id, so_tien, ly_do, nguoi),
        ).fetchone()


def tong_dieu_chinh(user_id: int, ky: str) -> float:
    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            "select coalesce(sum(amount), 0) as tien from crm.payroll_adjustments "
            "where user_id = %s and period = %s", (user_id, ky),
        ).fetchone()
    return float(r["tien"])


def don_hoan_sau_chot() -> list[dict]:
    """LUẬT 3 — đơn hoàn/huỷ mà kỳ lương của nó ĐÃ CHỐT và chưa bị truy thu.

    Trả kèm phần tiền đã trả cho đơn đó (thưởng chăm đã duyệt) để service tính
    số phải trừ sang kỳ sau."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select o.id, o.external_order_id, o.pos_order_id, o.total_amount,
                   o.payroll_period, o.status,
                   coalesce(o.sale_owner_id, o.cskh_owner_id) as staff_id,
                   nv.role_id as staff_role_id,
                   coalesce(rv.amount, 0) as thuong_cham_da_tra
              from crm.orders o
              join crm.users nv on nv.id = coalesce(o.sale_owner_id,
                                                    o.cskh_owner_id)
              join crm.payrolls p on p.user_id = nv.id
                                 and p.period = o.payroll_period
              left join crm.care_bonus_reviews rv on rv.order_id = o.id
                                                 and rv.status = 'duyet'
             where o.status in ('returned','cancelled')
               and p.frozen
               and not exists (select 1 from crm.payroll_adjustments a
                                where a.order_id = o.id)
             limit 500
            """
        ).fetchall()


# ------------------------------------------------------------------ mục tiêu
def muc_tieu(user_id: int, ky: str) -> float | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            "select target from crm.user_goals where user_id = %s and period = %s",
            (user_id, ky),
        ).fetchone()
    return float(r["target"]) if r else None


def dat_muc_tieu(user_id: int, ky: str, target) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.user_goals (user_id, period, target) "
            "values (%s, %s, %s) on conflict (user_id, period) "
            "do update set target = excluded.target returning *",
            (user_id, ky, target),
        ).fetchone()


def nhan_vien_co_don(ky: str) -> list[dict]:
    """Người có đơn trong kỳ — danh sách cần tính lương."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select distinct u.id, u.name, u.role_id
              from crm.orders o
              join crm.users u on u.id = coalesce(o.sale_owner_id, o.cskh_owner_id)
             where o.payroll_period = %s
             order by u.name
            """,
            (ky,),
        ).fetchall()


def ky_hien_tai() -> str:
    """Kỳ lương của hôm nay, dạng YYYY-MM theo giờ VN."""
    return hom_nay().strftime("%Y-%m")
