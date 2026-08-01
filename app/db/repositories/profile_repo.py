"""Gom dữ liệu cho các màn CHI TIẾT — CHỈ ĐỌC (màn 9 · 10 · 22).

Màn 9 (hồ sơ khách 360°) gồm 9 khu vực theo "Danh sách màn hình CRM": Tổng
quan · Hội thoại · Cuộc gọi · Hồ sơ tư vấn · Liệu trình · Đơn hàng · Chăm sóc ·
Marketing · Lịch sử thay đổi. Màn 10 dò hồ sơ nghi trùng, màn 22 chi tiết đơn.

Mỗi khu vực lấy từ đúng lát đã làm (B1…B9) nên file này chỉ JOIN lại, KHÔNG có
luật nghiệp vụ. Chia nhỏ theo khu vực để màn nạp đúng tab đang xem — mở hồ sơ
không phải bắn 15 câu truy vấn một lúc.
"""

from app.db.client import get_pg_pool


def _q(sql: str, tham_so: tuple = ()) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(sql, tham_so).fetchall()


def _q1(sql: str, tham_so: tuple = ()) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(sql, tham_so).fetchone()


# ------------------------------------------------------------------ tổng quan
def tong_quan(customer_id: int) -> dict | None:
    """Thông tin cơ bản + người phụ trách + trạng thái + cảnh báo (cờ an toàn)."""
    kh = _q1(
        """
        select c.*,
               (select u.name from crm.customer_assignments a
                  join crm.users u on u.id = a.user_id
                 where a.customer_id = c.id and a.assignment_type = 'sale'
                   and a.end_at is null limit 1) as sale_phu_trach,
               (select u.name from crm.customer_assignments a
                  join crm.users u on u.id = a.user_id
                 where a.customer_id = c.id and a.assignment_type = 'cskh'
                   and a.end_at is null limit 1) as cskh_phu_trach,
               (select json_agg(json_build_object('id', t.id, 'name', t.name))
                  from crm.customer_tags ct join crm.tags t on t.id = ct.tag_id
                 where ct.customer_id = c.id)                    as tags,
               (select count(*) from crm.orders o
                 where o.customer_id = c.id and o.status <> 'cancelled') as so_don,
               (select coalesce(sum(o.total_amount), 0) from crm.orders o
                 where o.customer_id = c.id
                   and o.status in ('delivered','collected'))    as tong_chi_tieu,
               (select max(o.delivered_at) from crm.orders o
                 where o.customer_id = c.id)                     as mua_cuoi
          from crm.customers c
         where c.id = %s
        """,
        (customer_id,),
    )
    if not kh:
        return None
    kh["lead"] = _q1(
        """
        select l.id, l.temperature, l.next_action_at, l.closed_at,
               s.name as stage_name, u.name as owner_name
          from crm.leads l
          join crm.pipeline_stages s on s.id = l.stage_id
          left join crm.users u on u.id = l.owner_id
         where l.customer_id = %s
         order by l.created_at desc limit 1
        """,
        (customer_id,),
    )
    kh["viec_tiep"] = _q(
        """
        select t.id, t.title, t.task_type, t.due_at, t.priority, u.name as nguoi
          from crm.tasks t left join crm.users u on u.id = t.assigned_to
         where t.customer_id = %s and t.status in ('open','in_progress')
         order by t.due_at asc nulls last limit 5
        """,
        (customer_id,),
    )
    kh["canh_bao"] = _q(
        """
        select screening_type, value, risk_level, created_at
          from crm.safety_screenings
         where customer_id = %s and cleared_at is null
           and risk_level in ('high','critical')
         order by created_at desc
        """,
        (customer_id,),
    )
    return kh


# ------------------------------------------------------------------ hội thoại
def hoi_thoai(customer_id: int) -> list[dict]:
    """Tab Hội thoại — danh sách hội thoại Pancake + số tin đã kéo về (FR-012)."""
    return _q(
        """
        select c.id, c.external_conversation_id, c.snippet, c.last_message_at,
               c.message_count, c.unread_count, c.messages_synced_at,
               p.name as page_name, p.external_page_id, u.name as assignee_name,
               (select count(*) from crm.messages m
                 where m.conversation_id = c.id) as tin_da_luu
          from crm.conversations c
          left join crm.pages p on p.id = c.page_id
          left join crm.users u on u.id = c.assignee_user_id
         where c.customer_id = %s
         order by c.last_message_at desc nulls last
        """,
        (customer_id,),
    )


def tin_nhan_gan_nhat(conversation_id: int, limit: int = 50) -> list[dict]:
    """Khung chat của MỘT hội thoại (cũ trước mới sau) — đọc từ crm.messages."""
    rows = _q(
        """
        select * from (
            select m.*, u.name as sender_user_name
              from crm.messages m left join crm.users u on u.id = m.sender_user_id
             where m.conversation_id = %s
             order by m.sent_at desc, m.id desc limit %s
        ) t order by sent_at asc, id asc
        """,
        (conversation_id, limit),
    )
    return rows


# ------------------------------------------------------------------ tư vấn (B5)
def ho_so_tu_van(customer_id: int) -> dict:
    return {
        "trieu_chung": _q(
            """
            select cs.*, s.name as symptom_name, s.group_name
              from crm.customer_symptoms cs
              join crm.symptoms s on s.id = cs.symptom_id
             where cs.customer_id = %s order by cs.id
            """,
            (customer_id,),
        ),
        "kham": _q(
            "select * from crm.examinations where customer_id = %s "
            "order by exam_date desc nulls last, id desc",
            (customer_id,),
        ),
        "thuoc": _q(
            "select * from crm.current_medications where customer_id = %s order by id",
            (customer_id,),
        ),
        "da_dung": _q(
            "select * from crm.previous_treatments where customer_id = %s order by id",
            (customer_id,),
        ),
        "sang_loc": _q(
            "select * from crm.safety_screenings where customer_id = %s "
            "and cleared_at is null order by created_at desc",
            (customer_id,),
        ),
        "ca_chuyen_mon": _q(
            "select * from crm.clinical_escalations where customer_id = %s "
            "order by created_at desc",
            (customer_id,),
        ),
    }


# ------------------------------------------------------------------ liệu trình (B6)
def lieu_trinh(customer_id: int) -> dict:
    dang_dung = _q(
        """
        select ct.*, tt.name as template_name, u.name as approved_by_name
          from crm.customer_treatments ct
          left join crm.treatment_templates tt on tt.id = ct.template_id
          left join crm.users u on u.id = ct.approved_by
         where ct.customer_id = %s
         order by ct.created_at desc
        """,
        (customer_id,),
    )
    for lt in dang_dung:
        lt["items"] = _q(
            """
            select i.*, p.name as product_name, p.product_code
              from crm.customer_treatment_items i
              join crm.products p on p.id = i.product_id
             where i.customer_treatment_id = %s order by i.id
            """,
            (lt["id"],),
        )
    return {
        "lieu_trinh": dang_dung,
        "de_xuat": _q(
            """
            select r.*, tt.name as template_name, u.name as nguoi_de_xuat
              from crm.treatment_recommendations r
              join crm.treatment_templates tt on tt.id = r.template_id
              left join crm.users u on u.id = r.recommended_by
             where r.customer_id = %s order by r.created_at desc
            """,
            (customer_id,),
        ),
    }


# ------------------------------------------------------------------ đơn hàng (B7)
def don_hang(customer_id: int) -> list[dict]:
    return _q(
        """
        select o.*, u.name as sale_name
          from crm.orders o left join crm.users u on u.id = o.sale_owner_id
         where o.customer_id = %s order by o.created_at desc
        """,
        (customer_id,),
    )


# ------------------------------------------------------------------ chăm sóc (B8+B9)
def cham_soc(customer_id: int) -> dict:
    ke_hoach = _q(
        """
        select cp.*, u.name as owner_name
          from crm.care_plans cp left join crm.users u on u.id = cp.owner_id
         where cp.customer_id = %s order by cp.created_at desc
        """,
        (customer_id,),
    )
    for kh in ke_hoach:
        kh["moc"] = _q(
            "select * from crm.care_plan_steps where care_plan_id = %s "
            "order by planned_at asc nulls last, id",
            (kh["id"],),
        )
    return {
        "ke_hoach": ke_hoach,
        "ban_giao": _q(
            """
            select h.*, us.name as sale_name, uc.name as cskh_name
              from crm.handovers h
              left join crm.users us on us.id = h.sale_user_id
              left join crm.users uc on uc.id = h.cskh_user_id
             where h.customer_id = %s order by h.created_at desc
            """,
            (customer_id,),
        ),
        "mua_lai": _q(
            """
            select r.*, tt.name as next_template_name, u.name as owner_name
              from crm.repurchase_opportunities r
              left join crm.treatment_templates tt on tt.id = r.next_template_id
              left join crm.users u on u.id = r.owner_id
             where r.customer_id = %s order by r.created_at desc
            """,
            (customer_id,),
        ),
    }


# ------------------------------------------------------------------ marketing
def marketing(customer_id: int) -> dict:
    return {
        "quy_nguon": _q(
            """
            select a.*, ad.name as ad_name, ads.name as adset_name,
                   c.name as campaign_name
              from crm.lead_attributions a
              left join crm.ads ad on ad.external_ad_id = a.external_ad_id
              left join crm.ad_sets ads on ads.id = ad.ad_set_id
              left join crm.ad_campaigns c on c.id = ads.campaign_id
             where a.customer_id = %s order by a.touch_type
            """,
            (customer_id,),
        ),
        "doanh_thu": _q1(
            "select coalesce(sum(total_amount), 0) as tong from crm.orders "
            "where customer_id = %s and status in ('delivered','collected')",
            (customer_id,),
        ),
    }


# ------------------------------------------------------------------ lịch sử
def lich_su(customer_id: int, limit: int = 100) -> list[dict]:
    """Tab Lịch sử thay đổi — audit của CHÍNH khách này + các bản ghi con.

    Audit ghi theo (object_type, object_id) nên gom bằng UNION: dòng của
    `customers` + dòng của lead/đơn/liệu trình/phiếu thuộc khách này.
    """
    return _q(
        """
        select a.*, u.name as user_name
          from crm.audit_logs a left join crm.users u on u.id = a.user_id
         where (a.object_type = 'customers' and a.object_id = %(kh)s)
            or (a.object_type = 'leads' and a.object_id in
                (select id from crm.leads where customer_id = %(kh)s))
            or (a.object_type = 'orders' and a.object_id in
                (select id from crm.orders where customer_id = %(kh)s))
            or (a.object_type = 'handovers' and a.object_id in
                (select id from crm.handovers where customer_id = %(kh)s))
         order by a.created_at desc
         limit %(lim)s
        """,
        {"kh": customer_id, "lim": limit},
    )


# ------------------------------------------------------------------ gộp trùng (màn 10)
def nghi_trung(limit: int = 50) -> list[dict]:
    """Các nhóm khách NGHI TRÙNG cho màn 10 — theo SĐT **và** Facebook ID.

    Phần "trùng SĐT" dùng lại `customer_repo.find_duplicate_groups` (CUSTOMER-006,
    đã nghiệm thu ở B1) — KHÔNG viết lại truy vấn thứ hai để hai chỗ khỏi lệch
    định nghĩa "khách sống". Ở đây chỉ bù thêm nhánh PSID mà đặc tả màn 10 đòi.
    """
    from app.db.repositories import customer_repo

    nhom: list[dict] = []
    for g in customer_repo.find_duplicate_groups(limit):
        nhom.append({
            "ly_do": f"SĐT {g['primary_phone']}",
            "so_ho_so": len(g["members"] or []),
            "ho_so": [
                {"id": m["id"], "ten": m["full_name"], "sdt": g["primary_phone"],
                 "ma": None, "tao": m.get("created_at")}
                for m in (g["members"] or [])
            ],
        })

    da_co = {h["id"] for n in nhom for h in n["ho_so"]}
    for g in _q(
        """
        select i.psid,
               json_agg(distinct jsonb_build_object(
                   'id', c.id, 'ten', c.full_name, 'sdt', c.primary_phone,
                   'ma', c.customer_code, 'tao', c.created_at
               )) as ho_so,
               count(distinct c.id) as so_ho_so
          from crm.customer_identities i
          join crm.customers c on c.id = i.customer_id
         where i.psid is not null and i.psid <> ''
           and c.deleted_at is null and c.status <> 'merged'
         group by i.psid
        having count(distinct c.id) > 1
         order by count(distinct c.id) desc
         limit %s
        """,
        (limit,),
    ):
        # nhóm nào đã bị bắt bởi nhánh SĐT thì thôi, khỏi bày hai lần
        if {h["id"] for h in g["ho_so"]} <= da_co:
            continue
        nhom.append({"ly_do": f"Facebook ID {g['psid']}",
                     "so_ho_so": g["so_ho_so"], "ho_so": g["ho_so"]})

    nhom.sort(key=lambda n: (-n["so_ho_so"], n["ly_do"]))
    return nhom[:limit]


def checklist_tu_van(customer_id: int) -> set[str]:
    """Màn 13 — 7 câu bắt buộc (CONSULT-005) câu nào ĐÃ có dữ liệu thật.

    Suy từ dữ liệu đã nhập chứ không hỏi lại người dùng: có triệu chứng nào
    chưa, có mức độ/tần suất chưa, đã ghi bệnh nền / thuốc đang dùng chưa…
    """
    r = _q1(
        """
        select
          exists(select 1 from crm.customer_symptoms where customer_id = %(k)s)
              as trieu_chung_chinh,
          exists(select 1 from crm.customer_symptoms
                  where customer_id = %(k)s and severity is not null) as muc_do,
          exists(select 1 from crm.customer_symptoms
                  where customer_id = %(k)s and frequency is not null) as tan_suat,
          exists(select 1 from crm.customer_symptoms
                  where customer_id = %(k)s and started_at is not null)
              as thoi_gian_mac,
          exists(select 1 from crm.customer_symptoms
                  where customer_id = %(k)s and meal_relation is not null)
              as lien_quan_bua_an,
          exists(select 1 from crm.safety_screenings
                  where customer_id = %(k)s and screening_type = 'benh_nen'
                    and cleared_at is null) as benh_nen,
          exists(select 1 from crm.current_medications where customer_id = %(k)s)
              as thuoc_dang_dung
        """,
        {"k": customer_id},
    )
    return {k for k, v in (r or {}).items() if v}


def hoi_thoai_moi_nhat(customer_id: int) -> dict | None:
    """Hội thoại mới nhất của khách + định danh để dựng link Pancake (màn 13)."""
    return _q1(
        """
        select c.id, c.external_conversation_id, p.external_page_id
          from crm.conversations c
          left join crm.pages p on p.id = c.page_id
         where c.customer_id = %s
         order by c.last_message_at desc nulls last limit 1
        """,
        (customer_id,),
    )


def chi_tiet_don(order_id: int) -> dict | None:
    """Màn 22 — đơn + khách + dòng hàng + lịch sử + việc/liệu trình/quy nguồn.

    Địa chỉ · vận chuyển · thanh toán KHÔNG có cột riêng trong `crm.orders`
    (đơn về từ POS) — lấy nguyên văn từ `pos_raw` để bày, không tự dịch nghĩa.
    """
    don = _q1(
        """
        select o.*, c.full_name as customer_name, c.primary_phone as customer_phone,
               c.customer_code, us.name as sale_name, uc.name as cskh_name
          from crm.orders o
          join crm.customers c on c.id = o.customer_id
          left join crm.users us on us.id = o.sale_owner_id
          left join crm.users uc on uc.id = o.cskh_owner_id
         where o.id = %s
        """,
        (order_id,),
    )
    if not don:
        return None
    don["items"] = _q(
        """
        select i.*, p.name as product_name, p.product_code,
               tt.name as template_name
          from crm.order_items i
          left join crm.products p on p.id = i.product_id
          left join crm.treatment_templates tt on tt.id = i.treatment_template_id
         where i.order_id = %s order by i.id
        """,
        (order_id,),
    )
    don["lich_su"] = _q(
        """
        select h.*, u.name as changed_by_name
          from crm.order_status_history h
          left join crm.users u on u.id = h.changed_by
         where h.order_id = %s order by h.created_at asc, h.id asc
        """,
        (order_id,),
    )
    don["viec"] = _q(
        """
        select t.*, u.name as nguoi
          from crm.tasks t left join crm.users u on u.id = t.assigned_to
         where t.related_type = 'order' and t.related_id = %s
         order by t.due_at asc nulls last
        """,
        (order_id,),
    )
    don["lieu_trinh"] = _q(
        """
        select ct.id, ct.status, ct.start_date, ct.expected_end_date,
               tt.name as template_name
          from crm.customer_treatments ct
          left join crm.treatment_templates tt on tt.id = ct.template_id
         where ct.order_id = %s
        """,
        (order_id,),
    )
    don["ban_giao"] = _q1(
        "select id, status, is_complete from crm.handovers where order_id = %s",
        (order_id,),
    )
    don["quy_nguon"] = _q(
        """
        select a.touch_type, a.external_ad_id, a.source, a.utm,
               ad.name as ad_name
          from crm.lead_attributions a
          left join crm.ads ad on ad.external_ad_id = a.external_ad_id
         where a.customer_id = %s order by a.touch_type
        """,
        (don["customer_id"],),
    )
    return don


def tom_tat_de_gop(customer_ids: list[int]) -> list[dict]:
    """Số liệu từng hồ sơ trong nhóm trùng — để người chọn giữ hồ sơ nào."""
    if not customer_ids:
        return []
    return _q(
        """
        select c.id, c.customer_code, c.full_name, c.primary_phone, c.status,
               c.created_at,
               (select count(*) from crm.orders o where o.customer_id = c.id) as so_don,
               (select count(*) from crm.conversations v where v.customer_id = c.id)
                                                                        as so_hoi_thoai,
               (select count(*) from crm.leads l where l.customer_id = c.id) as so_lead,
               (select u.name from crm.customer_assignments a
                  join crm.users u on u.id = a.user_id
                 where a.customer_id = c.id and a.end_at is null limit 1) as phu_trach
          from crm.customers c
         where c.id = any(%s)
         order by c.created_at
        """,
        (list(customer_ids),),
    )
