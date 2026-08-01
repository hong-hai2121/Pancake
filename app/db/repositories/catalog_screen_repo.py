"""Dữ liệu cho các màn quản trị/marketing còn lại — CHỈ ĐỌC + vài thao tác nhẹ.

    màn 16-17  khách chưa mua cần bám đuổi + chuỗi bám đuổi
    màn 57-58  báo cáo băn khoăn / lý do chưa chốt
    màn 69-71  automation đang chạy + mẫu chuỗi follow-up (read-only, trung thực:
               hệ thống hiện chạy automation CỨNG trong code, chưa có builder)
    màn 72     danh mục dùng chung (`ref_codes`)
"""

from app.db.client import get_pg_pool


def _q(sql: str, tham_so=()) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(sql, tham_so).fetchall()


# ------------------------------------------------------- màn 16-17 bám đuổi
def khach_can_bam_duoi(ly_do_id: int | None = None, limit: int = 100) -> list[dict]:
    """Lead CHƯA đóng, đã qua giai đoạn tiếp cận mà chưa chốt — kèm lý do
    chưa mua (nếu Sale đã ghi) và số lần đã chạm."""
    dk = ["l.closed_at is null"]
    ts: list = []
    if ly_do_id:
        dk.append("llr.lost_reason_id = %s")
        ts.append(ly_do_id)
    where = " and ".join(dk)
    return _q(
        f"""
        select l.id as lead_id, l.temperature, l.next_action_at, l.created_at,
               l.first_contact_at,
               c.id as customer_id, c.full_name, c.primary_phone,
               s.name as stage_name, u.name as sale_name,
               r.name as ly_do, r.id as ly_do_id,
               (select count(*) from crm.tasks t
                 where t.customer_id = c.id and t.status = 'done') as so_cham,
               (select max(t.completed_at) from crm.tasks t
                 where t.customer_id = c.id and t.status = 'done') as cham_cuoi
          from crm.leads l
          join crm.customers c on c.id = l.customer_id
          join crm.pipeline_stages s on s.id = l.stage_id
          left join crm.users u on u.id = l.owner_id
          left join crm.lead_lost_reasons llr on llr.lead_id = l.id
          left join crm.lead_reasons r on r.id = llr.lost_reason_id
         where {where}
         order by l.next_action_at asc nulls last, l.created_at desc
         limit {limit}
        """,
        tuple(ts),
    )


def danh_muc_ly_do() -> list[dict]:
    return _q("select id, code, name from crm.lead_reasons order by id")


def chuoi_bam_duoi(customer_id: int) -> dict:
    """Màn 17 — các lần chạm đã làm với khách + chuỗi không phản hồi (nếu có)."""
    return {
        "cham": _q(
            """
            select t.id, t.task_type, t.title, t.due_at, t.completed_at, t.result,
                   t.status, u.name as nguoi
              from crm.tasks t left join crm.users u on u.id = t.assigned_to
             where t.customer_id = %s order by t.created_at
            """,
            (customer_id,),
        ),
        "chuoi": _q(
            """
            select s.*, (select count(*) from crm.no_response_attempts a
                          where a.sequence_id = s.id) as so_lan
              from crm.no_response_sequences s
             where s.customer_id = %s order by s.id desc
            """,
            (customer_id,),
        ),
    }


# --------------------------------------------------- màn 57-58 báo cáo lý do
def bao_cao_ly_do(tu: str = "", den: str = "") -> dict:
    """Màn 58 — tỷ trọng từng lý do chưa chốt; màn 57 gom theo NHÓM băn khoăn.

    Nhóm băn khoăn suy từ mã lý do (`lead_reasons.code`) — BRD dùng chung bộ mã
    này cho cả hai màn, không đẻ danh mục thứ hai.
    """
    loc, ts = "", []
    if tu:
        loc += " and llr.created_at >= %s::date"
        ts.append(tu)
    if den:
        loc += " and llr.created_at < %s::date + 1"
        ts.append(den)
    theo_ly_do = _q(
        f"""
        select r.id, r.code, r.name, count(*) as n
          from crm.lead_lost_reasons llr
          join crm.lead_reasons r on r.id = llr.lost_reason_id
         where true {loc}
         group by r.id, r.code, r.name order by count(*) desc
        """,
        tuple(ts),
    )
    theo_sale = _q(
        f"""
        select coalesce(u.name, '(chưa giao)') as sale, r.name as ly_do,
               count(*) as n
          from crm.lead_lost_reasons llr
          join crm.lead_reasons r on r.id = llr.lost_reason_id
          join crm.leads l on l.id = llr.lead_id
          left join crm.users u on u.id = l.owner_id
         where true {loc}
         group by u.name, r.name order by count(*) desc limit 50
        """,
        tuple(ts),
    )
    theo_ad = _q(
        f"""
        select coalesce(ad.name, a.external_ad_id, '(không rõ)') as quang_cao,
               r.name as ly_do, count(*) as n
          from crm.lead_lost_reasons llr
          join crm.lead_reasons r on r.id = llr.lost_reason_id
          join crm.leads l on l.id = llr.lead_id
          join crm.lead_attributions a on a.customer_id = l.customer_id
          left join crm.ads ad on ad.external_ad_id = a.external_ad_id
         where a.touch_type = 'last' {loc}
         group by 1, r.name order by count(*) desc limit 50
        """,
        tuple(ts),
    )
    tong = sum(r["n"] for r in theo_ly_do)
    return {"theo_ly_do": theo_ly_do, "theo_sale": theo_sale,
            "theo_ad": theo_ad, "tong": tong}


# ----------------------------------------------------------- màn 72 danh mục
def nhom_danh_muc() -> list[dict]:
    return _q(
        "select group_code, count(*) as n from crm.ref_codes "
        "group by group_code order by group_code")


def danh_muc(group_code: str = "") -> list[dict]:
    if group_code:
        return _q(
            "select * from crm.ref_codes where group_code = %s "
            "order by sort_order, code", (group_code,))
    return _q("select * from crm.ref_codes order by group_code, sort_order, code")


def them_ma(group_code: str, code: str, name: str,
            description: str = "", sort_order: int = 0) -> dict | None:
    """Thêm một mã vào danh mục. Trùng (group_code, code) thì bỏ qua."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.ref_codes (group_code, code, name, description, sort_order)
            values (%s, %s, %s, %s, %s)
            on conflict (group_code, code) do nothing
            returning *
            """,
            (group_code, code, name, description or None, sort_order),
        ).fetchone()


def doi_trang_thai_ma(ma_id: int, status: str) -> dict | None:
    """Ngừng dùng một mã — KHÔNG xoá vì dữ liệu cũ còn tham chiếu."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.ref_codes set status = %s, updated_at = now() "
            "where id = %s returning *",
            (status, ma_id),
        ).fetchone()


# ------------------------------------------------------- màn 68 nhóm & ca trực
def nhom_va_thanh_vien() -> list[dict]:
    nhom = _q(
        """
        select t.*, u.name as manager_name,
               (select count(*) from crm.users x where x.team_id = t.id) as so_nguoi
          from crm.teams t left join crm.users u on u.id = t.manager_id
         order by t.department, t.name
        """)
    for n in nhom:
        n["thanh_vien"] = _q(
            "select u.id, u.name, r.name as vai_tro, u.status "
            "from crm.users u left join crm.roles r on r.id = u.role_id "
            "where u.team_id = %s order by u.name", (n["id"],))
    return nhom


def nhan_vien_chua_nhom() -> list[dict]:
    return _q(
        "select u.id, u.name, r.name as vai_tro from crm.users u "
        "left join crm.roles r on r.id = u.role_id "
        "where u.team_id is null and u.status = 'active' order by u.name")
