"""Số liệu báo cáo B11 (REPORT-001…011, FR-170…173).

Trái tim là SỔ ĐĂNG KÝ METRIC (`METRICS`): mỗi chỉ số khai MỘT lần gồm
FROM + WHERE + cột danh sách — số tổng (count/sum) và danh sách drill-down
(REPORT-010) chạy trên CÙNG một điều kiện, nên không bao giờ lệch nhau
(luật FR-173: "danh sách chi tiết phải dùng cùng điều kiện lọc với số tổng").

Bộ lọc chuẩn mọi metric: %(tu)s · %(den)s (khoảng thời gian) và %(uid)s
(người phụ trách — cột nào là "người" do metric tự khai ở `cot_nguoi`).
"""

from dataclasses import dataclass, field

from app.db.client import get_pg_pool


@dataclass(frozen=True)
class Metric:
    ten: str                       # nhãn tiếng Việt (màn drill-down)
    quyen: str                     # quyền cần có để XEM metric này
    tu_bang: str                   # FROM ... JOIN ...
    dieu_kien: str                 # WHERE (dùng %(tu)s %(den)s)
    cot_rows: str                  # SELECT cho danh sách chi tiết
    sap_xep: str = "1 desc"
    bieu_thuc: str = "count(*)"    # count(*) hoặc coalesce(sum(...),0)
    cot_nguoi: str = ""            # cột lọc theo người ("" = không lọc được)
    cot: list[str] = field(default_factory=list)   # nhãn cột cho UI


_LEAD_TU = """
    from crm.leads l
    join crm.customers c on c.id = l.customer_id
    join crm.pipeline_stages s on s.id = l.stage_id
    left join crm.users u on u.id = l.owner_id
"""
_LEAD_COT = ("l.id, c.full_name as khach, s.name as giai_doan, "
             "u.name as phu_trach, l.created_at as luc")
_LEAD_NHAN = ["ID", "Khách", "Giai đoạn", "Phụ trách", "Lúc"]

# Khách tiềm năng ĐI QUA một giai đoạn trong kỳ — đếm theo lịch sử FR-041, không phải
# trạng thái hiện tại (khách đã sang bước sau vẫn được tính là "đã tư vấn")
_QUA_BUOC_TU = """
    from crm.lead_stage_history h
    join crm.pipeline_stages ps on ps.id = h.to_stage_id
    join crm.leads l on l.id = h.lead_id
    join crm.customers c on c.id = l.customer_id
    left join crm.users u on u.id = l.owner_id
"""
_QUA_BUOC_COT = ("h.lead_id as id, c.full_name as khach, ps.name as sang_buoc, "
                 "u.name as phu_trach, h.changed_at as luc")
_QUA_BUOC_NHAN = ["ID", "Khách", "Sang bước", "Phụ trách", "Lúc"]

_DON_TU = """
    from crm.orders o
    join crm.customers c on c.id = o.customer_id
    left join crm.users u on u.id = o.sale_owner_id
"""
_DON_COT = ("o.id, c.full_name as khach, o.status as trang_thai, "
            "o.total_amount as so_tien, u.name as sale, o.created_at as luc")
_DON_NHAN = ["Mã đơn", "Khách", "Trạng thái", "Số tiền", "Sale", "Lúc"]

_VIEC_TU = """
    from crm.tasks t
    left join crm.customers c on c.id = t.customer_id
    left join crm.users u on u.id = t.assigned_to
"""
_VIEC_COT = ("t.id, t.title as viec, t.task_type as loai, c.full_name as khach, "
             "u.name as nguoi_lam, t.due_at as han")
_VIEC_NHAN = ["ID", "Việc", "Loại", "Khách", "Người làm", "Hạn"]

_MOC_TU = """
    from crm.care_plan_steps st
    join crm.care_plans p on p.id = st.care_plan_id
    join crm.customers c on c.id = p.customer_id
    left join crm.users u on u.id = p.owner_id
"""
_MOC_COT = ("st.id, st.step_code as moc, c.full_name as khach, "
            "u.name as phu_trach, st.planned_at as lich")
_MOC_NHAN = ["ID", "Mốc", "Khách", "Phụ trách", "Lịch hẹn"]

_CO_HOI_TU = """
    from crm.repurchase_opportunities r
    join crm.customers c on c.id = r.customer_id
    left join crm.users u on u.id = r.owner_id
"""
_CO_HOI_COT = ("r.id, c.full_name as khach, r.stage as buoc, "
               "r.expected_close_date as ngay_het, r.expected_value as gia_tri, "
               "u.name as phu_trach")
_CO_HOI_NHAN = ["ID", "Khách", "Bước", "Ngày hết", "Giá trị", "Phụ trách"]


METRICS: dict[str, Metric] = {
    # ---------------- khách tiềm năng (FR-170) ----------------
    "lead_moi": Metric("Khách tiềm năng mới trong kỳ", "customer.view", _LEAD_TU,
                       "l.created_at between %(tu)s and %(den)s",
                       _LEAD_COT, "l.created_at desc",
                       cot_nguoi="l.owner_id", cot=_LEAD_NHAN),
    "lead_chua_lien_he": Metric(
        "Khách tiềm năng chưa liên hệ (đang mở)", "customer.view", _LEAD_TU,
        "l.closed_at is null and l.first_contact_at is null "
        "and l.created_at between %(tu)s and %(den)s",
        _LEAD_COT, "l.created_at", cot_nguoi="l.owner_id", cot=_LEAD_NHAN),
    "lead_nong": Metric("Khách tiềm năng nóng đang mở", "customer.view", _LEAD_TU,
                        "l.closed_at is null and l.temperature = 'nong'",
                        _LEAD_COT, "l.updated_at desc",
                        cot_nguoi="l.owner_id", cot=_LEAD_NHAN),
    "lead_qua_sla": Metric(
        "Khách tiềm năng quá SLA nhận (FR-042)", "customer.view", _LEAD_TU,
        "l.closed_at is null and l.first_contact_at is null "
        "and l.sla_due_at < now()",
        _LEAD_COT, "l.sla_due_at", cot_nguoi="l.owner_id", cot=_LEAD_NHAN),
    "lead_lien_he": Metric(
        "Khách tiềm năng có tương tác đầu trong kỳ", "customer.view", _LEAD_TU,
        "l.first_contact_at between %(tu)s and %(den)s",
        _LEAD_COT, "l.first_contact_at desc",
        cot_nguoi="l.owner_id", cot=_LEAD_NHAN),
    "lead_tu_van": Metric(
        "Khách tiềm năng vào bước Đã tư vấn trong kỳ", "customer.view",
        _QUA_BUOC_TU,
        "ps.name = 'Đã tư vấn' and h.changed_at between %(tu)s and %(den)s",
        _QUA_BUOC_COT, "h.changed_at desc",
        cot_nguoi="l.owner_id", cot=_QUA_BUOC_NHAN),
    "lead_bao_gia": Metric(
        "Khách tiềm năng vào bước Đã báo giá trong kỳ", "customer.view",
        _QUA_BUOC_TU,
        "ps.name = 'Đã báo giá' and h.changed_at between %(tu)s and %(den)s",
        _QUA_BUOC_COT, "h.changed_at desc",
        cot_nguoi="l.owner_id", cot=_QUA_BUOC_NHAN),
    "lead_chot": Metric(
        "Khách tiềm năng chốt (vào Đã chốt) trong kỳ", "customer.view",
        _QUA_BUOC_TU,
        "ps.name = 'Đã chốt' and h.changed_at between %(tu)s and %(den)s",
        _QUA_BUOC_COT, "h.changed_at desc",
        cot_nguoi="l.owner_id", cot=_QUA_BUOC_NHAN),
    # ---------------- đơn & doanh thu (FR-170/172) ----------------
    "don_tao": Metric("Đơn tạo trong kỳ", "revenue.view", _DON_TU,
                      "o.created_at between %(tu)s and %(den)s",
                      _DON_COT, "o.created_at desc",
                      cot_nguoi="o.sale_owner_id", cot=_DON_NHAN),
    "don_giao": Metric("Đơn giao thành công trong kỳ", "revenue.view", _DON_TU,
                       "o.status = 'delivered' "
                       "and o.delivered_at between %(tu)s and %(den)s",
                       _DON_COT, "o.delivered_at desc",
                       cot_nguoi="o.sale_owner_id", cot=_DON_NHAN),
    "don_hoan": Metric("Đơn hoàn trong kỳ", "revenue.view", _DON_TU,
                       "o.status in ('returned','returning') "
                       "and o.updated_at between %(tu)s and %(den)s",
                       _DON_COT, "o.updated_at desc",
                       cot_nguoi="o.sale_owner_id", cot=_DON_NHAN),
    "doanh_thu_giao": Metric(
        "Doanh thu giao thành công", "revenue.view", _DON_TU,
        "o.status = 'delivered' and o.delivered_at between %(tu)s and %(den)s",
        _DON_COT, "o.delivered_at desc",
        bieu_thuc="coalesce(sum(o.total_amount), 0)",
        cot_nguoi="o.sale_owner_id", cot=_DON_NHAN),
    "doanh_thu_mua_lai": Metric(
        "Doanh thu mua lại (đơn repurchase giao TC)", "revenue.view", _DON_TU,
        "o.status = 'delivered' and o.order_type = 'repurchase' "
        "and o.delivered_at between %(tu)s and %(den)s",
        _DON_COT, "o.delivered_at desc",
        bieu_thuc="coalesce(sum(o.total_amount), 0)",
        cot_nguoi="o.sale_owner_id", cot=_DON_NHAN),
    # "Lên đơn" = tiền đã LÊN ĐƠN trong kỳ, đơn ở MỌI trạng thái trừ huỷ/hoàn —
    # khác "đã thu" (chỉ đơn giao thành công). Trang chủ bày cạnh nhau để thấy
    # ngay phần tiền còn treo trên đường.
    "doanh_thu_len_don": Metric(
        "Doanh thu lên đơn (mọi trạng thái, bỏ huỷ/hoàn)", "revenue.view", _DON_TU,
        "o.created_at between %(tu)s and %(den)s "
        "and o.status not in ('cancelled','returned','returning')",
        _DON_COT, "o.created_at desc",
        bieu_thuc="coalesce(sum(o.total_amount), 0)",
        cot_nguoi="o.sale_owner_id", cot=_DON_NHAN),
    "doanh_thu_len_don_sale": Metric(
        "Doanh thu lên đơn — bán mới (Sale)", "revenue.view", _DON_TU,
        "o.created_at between %(tu)s and %(den)s "
        "and o.status not in ('cancelled','returned','returning') "
        "and coalesce(o.order_type, 'new') <> 'repurchase'",
        _DON_COT, "o.created_at desc",
        bieu_thuc="coalesce(sum(o.total_amount), 0)",
        cot_nguoi="o.sale_owner_id", cot=_DON_NHAN),
    "doanh_thu_len_don_cskh": Metric(
        "Doanh thu lên đơn — chăm sóc/mua lại (CSKH)", "revenue.view", _DON_TU,
        "o.created_at between %(tu)s and %(den)s "
        "and o.status not in ('cancelled','returned','returning') "
        "and o.order_type = 'repurchase'",
        _DON_COT, "o.created_at desc",
        bieu_thuc="coalesce(sum(o.total_amount), 0)",
        cot_nguoi="o.cskh_owner_id", cot=_DON_NHAN),
    # ---------------- việc (FR-160/171) ----------------
    "viec_hoan_thanh": Metric(
        "Việc hoàn thành trong kỳ", "customer.view", _VIEC_TU,
        "t.status = 'done' and t.completed_at between %(tu)s and %(den)s",
        _VIEC_COT, "t.completed_at desc",
        cot_nguoi="t.assigned_to", cot=_VIEC_NHAN),
    "viec_dung_han": Metric(
        "Việc hoàn thành ĐÚNG hạn trong kỳ", "customer.view", _VIEC_TU,
        "t.status = 'done' and t.completed_at between %(tu)s and %(den)s "
        "and t.completed_at <= t.due_at",
        _VIEC_COT, "t.completed_at desc",
        cot_nguoi="t.assigned_to", cot=_VIEC_NHAN),
    "viec_qua_han": Metric(
        "Việc đang QUÁ hạn", "customer.view", _VIEC_TU,
        "t.status in ('open','in_progress') and t.due_at < now()",
        _VIEC_COT, "t.due_at", cot_nguoi="t.assigned_to", cot=_VIEC_NHAN),
    # ---------------- chăm sóc (FR-171) ----------------
    "ban_giao_moi": Metric(
        "Khách mới bàn giao trong kỳ", "customer.view",
        """
        from crm.handovers h
        join crm.customers c on c.id = h.customer_id
        left join crm.users u on u.id = h.cskh_user_id
        """,
        "h.created_at between %(tu)s and %(den)s",
        "h.id, c.full_name as khach, h.status as trang_thai, "
        "u.name as cskh, h.created_at as luc",
        "h.created_at desc", cot_nguoi="h.cskh_user_id",
        cot=["Phiếu", "Khách", "Trạng thái", "CSKH", "Lúc"]),
    "moc_den_han": Metric(
        "Mốc chăm đến hạn (chưa làm)", "customer.view", _MOC_TU,
        "st.status in ('pending','due') and st.planned_at <= now() "
        "and p.status = 'active' and not c.do_not_contact",
        _MOC_COT, "st.planned_at", cot_nguoi="p.owner_id", cot=_MOC_NHAN),
    "moc_dung_han": Metric(
        "Mốc chăm làm ĐÚNG hạn trong kỳ", "customer.view", _MOC_TU,
        "st.status = 'done' and st.completed_at between %(tu)s and %(den)s "
        "and st.completed_at <= st.planned_at + interval '1 day'",
        _MOC_COT, "st.completed_at desc", cot_nguoi="p.owner_id", cot=_MOC_NHAN),
    "moc_hoan_thanh": Metric(
        "Mốc chăm hoàn thành trong kỳ", "customer.view", _MOC_TU,
        "st.status = 'done' and st.completed_at between %(tu)s and %(den)s",
        _MOC_COT, "st.completed_at desc", cot_nguoi="p.owner_id", cot=_MOC_NHAN),
    "khach_phan_ung": Metric(
        "Khách có phản ứng (phiếu chăm ghi Vừa/Nặng)", "customer.view", _MOC_TU,
        "st.data->>'adverse_event' in ('Vừa','Nặng') "
        "and st.completed_at between %(tu)s and %(den)s",
        _MOC_COT, "st.completed_at desc", cot_nguoi="p.owner_id", cot=_MOC_NHAN),
    # ---------------- mua lại (FR-171/172) ----------------
    "co_hoi_mo": Metric(
        "Cơ hội mua lại đang mở", "customer.view", _CO_HOI_TU,
        "r.stage not in ('won','lost')",
        _CO_HOI_COT, "r.expected_close_date nulls last",
        cot_nguoi="r.owner_id", cot=_CO_HOI_NHAN),
    "co_hoi_won": Metric(
        "Cơ hội chốt ĐƯỢC (won) trong kỳ", "customer.view", _CO_HOI_TU,
        "r.stage = 'won' and r.stage_moved_at between %(tu)s and %(den)s",
        _CO_HOI_COT, "r.stage_moved_at desc",
        cot_nguoi="r.owner_id", cot=_CO_HOI_NHAN),
    # ---------------- marketing (FR-172) ----------------
    "chi_phi_qc": Metric(
        "Chi phí quảng cáo trong kỳ", "ads.view",
        "from crm.ad_metrics_daily m",
        "m.entity_type = 'ad' and m.ngay between %(tu)s::date and %(den)s::date",
        "m.external_id as ad, m.ngay, m.spend as chi_phi, m.impressions, m.clicks",
        "m.ngay desc", bieu_thuc="coalesce(sum(m.spend), 0)",
        cot=["Ad", "Ngày", "Chi phí", "Hiển thị", "Click"]),
    "hoi_thoai_moi": Metric(
        "Hội thoại mới trong kỳ", "customer.view",
        """
        from crm.conversations cv
        left join crm.customers c on c.id = cv.customer_id
        left join crm.pages pg on pg.id = cv.page_id
        """,
        "cv.created_at between %(tu)s and %(den)s",
        "cv.id, coalesce(c.full_name, '—') as khach, pg.name as page, "
        "cv.created_at as luc",
        "cv.created_at desc", cot=["ID", "Khách", "Page", "Lúc"]),
    "khach_moi": Metric(
        "Khách mới trong kỳ", "customer.view",
        "from crm.customers c",
        "c.created_at between %(tu)s and %(den)s and c.status <> 'deleted'",
        "c.id, c.full_name as khach, c.primary_phone as sdt, c.created_at as luc",
        "c.created_at desc", cot=["ID", "Khách", "SĐT", "Lúc"]),
}


def tinh(metric: Metric, ts: dict) -> float:
    """Số tổng — CÙNG điều kiện với rows() (FR-173)."""
    loc_nguoi = f"and {metric.cot_nguoi} = %(uid)s" \
        if metric.cot_nguoi and ts.get("uid") else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            f"select {metric.bieu_thuc} as x {metric.tu_bang} "
            f"where {metric.dieu_kien} {loc_nguoi}",
            ts,
        ).fetchone()
    return float(r["x"] or 0)


def rows(metric: Metric, ts: dict, limit: int = 200) -> list[dict]:
    """Danh sách chi tiết (REPORT-010) — CÙNG điều kiện với tinh()."""
    loc_nguoi = f"and {metric.cot_nguoi} = %(uid)s" \
        if metric.cot_nguoi and ts.get("uid") else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {metric.cot_rows} {metric.tu_bang} "
            f"where {metric.dieu_kien} {loc_nguoi} "
            f"order by {metric.sap_xep} limit {int(limit)}",
            ts,
        ).fetchall()


# ------------------------------------------------------------ tổng hợp theo người
def theo_nhan_vien_sale(ts: dict) -> list[dict]:
    """REPORT-002 — một dòng mỗi Sale: phễu lead + đơn + doanh thu trong kỳ."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select u.id, u.name,
              (select count(*) from crm.leads l
                where l.owner_id = u.id
                  and l.created_at between %(tu)s and %(den)s)      as lead_moi,
              (select count(*) from crm.leads l
                where l.owner_id = u.id
                  and l.first_contact_at between %(tu)s and %(den)s) as lien_he,
              (select count(*) from crm.lead_stage_history h
                join crm.pipeline_stages ps on ps.id = h.to_stage_id
                join crm.leads l on l.id = h.lead_id
                where l.owner_id = u.id and ps.name = 'Đã tư vấn'
                  and h.changed_at between %(tu)s and %(den)s)      as tu_van,
              (select count(*) from crm.lead_stage_history h
                join crm.pipeline_stages ps on ps.id = h.to_stage_id
                join crm.leads l on l.id = h.lead_id
                where l.owner_id = u.id and ps.name = 'Đã báo giá'
                  and h.changed_at between %(tu)s and %(den)s)      as bao_gia,
              (select count(*) from crm.lead_stage_history h
                join crm.pipeline_stages ps on ps.id = h.to_stage_id
                join crm.leads l on l.id = h.lead_id
                where l.owner_id = u.id and ps.name = 'Đã chốt'
                  and h.changed_at between %(tu)s and %(den)s)      as chot,
              (select count(*) from crm.orders o
                where o.sale_owner_id = u.id and o.status = 'delivered'
                  and o.delivered_at between %(tu)s and %(den)s)    as don_giao,
              (select count(*) from crm.orders o
                where o.sale_owner_id = u.id
                  and o.status in ('returned','returning')
                  and o.updated_at between %(tu)s and %(den)s)      as don_hoan,
              (select coalesce(sum(o.total_amount),0) from crm.orders o
                where o.sale_owner_id = u.id and o.status = 'delivered'
                  and o.delivered_at between %(tu)s and %(den)s)    as doanh_thu
              from crm.users u
              join crm.roles r on r.id = u.role_id
             where r.name in ('Sale','Trưởng nhóm Sale') and u.status = 'active'
             order by doanh_thu desc, u.name
            """,
            ts,
        ).fetchall()


def theo_nhan_vien_cskh(ts: dict) -> list[dict]:
    """REPORT-003 — một dòng mỗi CSKH: khách phụ trách, mốc, việc, mua lại."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select u.id, u.name,
              (select count(*) from crm.care_plans p
                where p.owner_id = u.id and p.status = 'active')     as khach_phu_trach,
              (select count(*) from crm.care_plan_steps st
                join crm.care_plans p on p.id = st.care_plan_id
                where p.owner_id = u.id and st.status = 'done'
                  and st.completed_at between %(tu)s and %(den)s)    as moc_xong,
              (select count(*) from crm.care_plan_steps st
                join crm.care_plans p on p.id = st.care_plan_id
                where p.owner_id = u.id and st.status = 'done'
                  and st.completed_at between %(tu)s and %(den)s
                  and st.completed_at <= st.planned_at + interval '1 day')
                                                                     as moc_dung_han,
              (select count(*) from crm.care_plan_steps st
                join crm.care_plans p on p.id = st.care_plan_id
                join crm.customers c on c.id = p.customer_id
                where p.owner_id = u.id and st.status in ('pending','due')
                  and st.planned_at < now() and p.status = 'active'
                  and not c.do_not_contact)                          as moc_qua_han,
              (select count(*) from crm.tasks t
                where t.assigned_to = u.id
                  and t.status in ('open','in_progress')
                  and t.due_at < now())                              as viec_qua_han,
              (select count(*) from crm.care_plans p
                where p.owner_id = u.id and p.cycle_no >= 2
                  and p.created_at between %(tu)s and %(den)s)       as ke_hoach_lt2,
              (select coalesce(sum(o.total_amount),0) from crm.orders o
                join crm.care_plans p on p.customer_id = o.customer_id
                    and p.owner_id = u.id
                where o.status = 'delivered' and o.order_type = 'repurchase'
                  and o.delivered_at between %(tu)s and %(den)s)     as doanh_thu_mua_lai
              from crm.users u
              join crm.roles r on r.id = u.role_id
             where r.name in ('CSKH','Trưởng nhóm CSKH') and u.status = 'active'
             order by u.name
            """,
            ts,
        ).fetchall()


def doanh_thu_theo_ngay(ts: dict) -> list[dict]:
    """REPORT-006 — chuỗi ngày: doanh thu giao TC, tách bán mới / mua lại."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select o.delivered_at::date as ngay,
                   coalesce(sum(o.total_amount), 0) as tong,
                   coalesce(sum(o.total_amount)
                        filter (where o.order_type = 'repurchase'), 0) as mua_lai,
                   count(*) as so_don
              from crm.orders o
             where o.status = 'delivered'
               and o.delivered_at between %(tu)s and %(den)s
             group by 1 order by 1
            """,
            ts,
        ).fetchall()


def ly_do_chua_chot(ts: dict) -> list[dict]:
    """FR-172 'lý do chưa chốt' — gộp lịch sử lead vào bước đóng-thua (kèm
    reason FR-041) + lý do cơ hội mua lại lost."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select ly_do, count(*) as n from (
                select coalesce(nullif(trim(h.reason), ''), '(không ghi)') as ly_do
                  from crm.lead_stage_history h
                  join crm.pipeline_stages ps on ps.id = h.to_stage_id
                 where ps.is_closed and ps.name <> 'Đã chốt'
                   and h.changed_at between %(tu)s and %(den)s
                union all
                select coalesce(lr.name, nullif(trim(r.lost_note), ''),
                                '(không ghi)')
                  from crm.repurchase_opportunities r
                  left join crm.lead_reasons lr on lr.id = r.lost_reason_id
                 where r.stage = 'lost'
                   and r.stage_moved_at between %(tu)s and %(den)s
            ) x group by ly_do order by n desc limit 15
            """,
            ts,
        ).fetchall()


def don_theo_trang_thai(ts: dict) -> list[dict]:
    """REPORT-005 — đơn trong kỳ nhóm theo trạng thái (đếm + tiền)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select o.status, count(*) as n, coalesce(sum(o.total_amount),0) as tien "
            "from crm.orders o where o.created_at between %(tu)s and %(den)s "
            "group by o.status order by n desc",
            ts,
        ).fetchall()


def viec_theo_loai(ts: dict) -> list[dict]:
    """REPORT-009 — việc trong kỳ theo loại: tạo/xong/đúng hạn/quá hạn."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select t.task_type,
                   count(*) filter (where t.created_at
                        between %(tu)s and %(den)s)                 as tao,
                   count(*) filter (where t.status = 'done'
                        and t.completed_at between %(tu)s and %(den)s) as xong,
                   count(*) filter (where t.status = 'done'
                        and t.completed_at between %(tu)s and %(den)s
                        and t.completed_at <= t.due_at)             as dung_han,
                   count(*) filter (where t.status in ('open','in_progress')
                        and t.due_at < now())                       as dang_qua_han
              from crm.tasks t
             where t.created_at between %(tu)s and %(den)s
                or (t.status in ('open','in_progress') and t.due_at < now())
                or (t.status = 'done'
                    and t.completed_at between %(tu)s and %(den)s)
             group by t.task_type order by tao desc
            """,
            ts,
        ).fetchall()
