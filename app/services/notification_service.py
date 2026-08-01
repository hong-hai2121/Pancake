"""Trung tâm thông báo — màn 3 · NOTIFY-001…004.

Đúng 11 loại theo "Danh sách màn hình CRM" mục 3. Nguyên tắc thiết kế:

  * Thông báo do **worker QUÉT DB** sinh ra, KHÔNG nhét lệnh gửi vào từng
    service nghiệp vụ. Nhờ vậy thêm/bớt loại thông báo chỉ sửa file này, không
    đụng luật B1…B8 (và không có nguy cơ vỡ luồng bán vì một câu thông báo).
  * Mỗi sự việc một `dedupe_key` -> quét lại 5 phút/lần vẫn 1 dòng; người đã
    đọc rồi thì KHÔNG réo lại (do unique key vẫn còn đó).
  * Mỗi nguồn có TRẦN (`_TRAN`) — lần chạy đầu trên DB đang có sẵn hàng trăm
    việc quá hạn cũng không đổ ập vào chuông.
  * Ai TẮT loại nào (NOTIFY-004) thì nguồn bỏ qua ngay từ SQL.

Người nhận: việc/lead/đơn -> người phụ trách bản ghi đó; nội dung chờ duyệt ->
ai có `content.approve`; lỗi đồng bộ -> ai có `integration.manage`.
"""

import sys

from app.core.errors import ApiError
from app.db.client import get_pg_pool
from app.db.repositories import notification_repo as repo

# Trần mỗi nguồn cho một lượt quét (chống dội khi chạy lần đầu)
_TRAN = 200

# 11 loại — mã, nhãn tiếng Việt, mức ưu tiên mặc định, đường dẫn màn liên quan
LOAI: dict[str, tuple[str, str, str]] = {
    "lead_moi":                    ("Lead mới", "normal", "/crm/pipeline"),
    "viec_sap_den_han":            ("Công việc sắp đến hạn", "normal", "/crm/cong-viec"),
    "viec_qua_han":                ("Công việc quá hạn", "high", "/crm/cong-viec"),
    "khach_can_goi_lai":           ("Khách cần gọi lại", "high", "/crm/pipeline"),
    "khach_co_phan_ung":           ("Khách có phản ứng", "urgent", "/crm/khach-hang"),
    "khach_can_chuyen_chuyen_mon": ("Khách cần chuyển chuyên môn", "urgent",
                                    "/crm/khach-hang"),
    "don_giao_thanh_cong":         ("Đơn giao thành công", "normal", "/crm/ban-giao"),
    "don_hoan":                    ("Đơn hoàn", "high", "/crm/don-hang"),
    "khach_den_han_mua_lai":       ("Khách đến hạn mua lại", "normal", "/crm/mua-lai"),
    "noi_dung_cho_duyet":          ("Nội dung chờ duyệt", "normal", "/crm/san-pham"),
    "loi_dong_bo":                 ("Lỗi đồng bộ Pancake / tổng đài", "high",
                                    "/quan-tri/tich-hop/loi"),
}


def _actor_id(actor: dict | None) -> int:
    try:
        return int((actor or {}).get("sub") or 0)
    except (TypeError, ValueError):
        return 0


def _day(loai: str, user_id: int | None, tieu_de: str, khoa: str, **kw) -> bool:
    """Gói repo.day: tự lấy nhãn/ưu tiên/link mặc định của loại."""
    if not user_id:
        return False
    _nhan, uu_tien, link = LOAI[loai]
    return repo.day(
        user_id=int(user_id), type_=loai, title=tieu_de,
        dedupe_key=khoa, priority=kw.pop("priority", uu_tien),
        link=kw.pop("link", link), **kw,
    )


def _truy_van(sql: str, tham_so: tuple = ()) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(sql, tham_so).fetchall()


# ------------------------------------------------------------------ 11 nguồn
def _quet_lead_moi(tat: set[int]) -> int:
    """Lead vừa được chia mà Sale CHƯA liên hệ lần nào."""
    rows = _truy_van(
        f"""
        select l.id, l.owner_id, c.full_name, c.primary_phone
          from crm.leads l join crm.customers c on c.id = l.customer_id
         where l.owner_id is not null and l.first_contact_at is null
           and l.closed_at is null
           and l.created_at > now() - interval '3 days'
         order by l.created_at desc limit {_TRAN}
        """)
    n = 0
    for r in rows:
        if r["owner_id"] in tat:
            continue
        n += _day("lead_moi", r["owner_id"],
                  f"Lead mới: {r['full_name']}",
                  f"lead_moi:{r['id']}",
                  body=f"SĐT {r['primary_phone'] or '—'} — chưa liên hệ lần nào",
                  related_type="lead", related_id=r["id"])
    return n


def _quet_viec(tat_sap: set[int], tat_qua: set[int]) -> tuple[int, int]:
    """Việc sắp đến hạn (24h tới) và việc ĐÃ quá hạn — hai loại, một câu quét."""
    rows = _truy_van(
        f"""
        select t.id, t.assigned_to, t.title, t.task_type, t.due_at,
               t.due_at < now() as qua_han, c.full_name
          from crm.tasks t left join crm.customers c on c.id = t.customer_id
         where t.assigned_to is not null and t.status in ('open','in_progress')
           and t.due_at is not null
           and t.due_at < now() + interval '24 hours'
         order by t.due_at asc limit {_TRAN}
        """)
    n_sap = n_qua = 0
    for r in rows:
        khach = f" — {r['full_name']}" if r.get("full_name") else ""
        ten = r["title"] or r["task_type"]
        if r["qua_han"]:
            if r["assigned_to"] in tat_qua:
                continue
            n_qua += _day("viec_qua_han", r["assigned_to"],
                          f"Việc quá hạn: {ten}", f"viec_qua_han:{r['id']}",
                          body=f"Hạn {r['due_at']:%d/%m %H:%M}{khach}",
                          related_type="task", related_id=r["id"])
        else:
            if r["assigned_to"] in tat_sap:
                continue
            n_sap += _day("viec_sap_den_han", r["assigned_to"],
                          f"Sắp đến hạn: {ten}", f"viec_sap_den_han:{r['id']}",
                          body=f"Hạn {r['due_at']:%d/%m %H:%M}{khach}",
                          related_type="task", related_id=r["id"])
    return n_sap, n_qua


def _quet_goi_lai(tat: set[int]) -> int:
    """Lead có lịch hẹn hành động đã tới/qua giờ mà chưa đóng."""
    rows = _truy_van(
        f"""
        select l.id, l.owner_id, l.next_action_at, c.full_name, c.primary_phone
          from crm.leads l join crm.customers c on c.id = l.customer_id
         where l.owner_id is not null and l.closed_at is null
           and l.next_action_at is not null and l.next_action_at <= now()
         order by l.next_action_at asc limit {_TRAN}
        """)
    n = 0
    for r in rows:
        if r["owner_id"] in tat:
            continue
        n += _day("khach_can_goi_lai", r["owner_id"],
                  f"Đến hẹn gọi lại: {r['full_name']}",
                  # theo NGÀY hẹn: dời lịch sang hôm khác thì báo lại lần nữa
                  f"khach_can_goi_lai:{r['id']}:{r['next_action_at']:%Y%m%d}",
                  body=f"Hẹn {r['next_action_at']:%d/%m %H:%M} · "
                       f"SĐT {r['primary_phone'] or '—'}",
                  related_type="lead", related_id=r["id"])
    return n


def _quet_ca_chuyen_mon(tat_pu: set[int], tat_cm: set[int]) -> tuple[int, int]:
    """Ca lâm sàng đang mở (B5). Nguồn `medication_risk` = khách có PHẢN ỨNG
    với thuốc (FR-052); còn lại là ca cần chuyển chuyên môn (FR-053).

    Chưa gán ai thì gửi cho vai trò "Người chuyên môn" — KHÔNG dùng quyền
    `health.view` vì quyền đó Sale/CSKH cũng có, báo cả công ty là dội."""
    rows = _truy_van(
        f"""
        select e.id, e.assigned_to, e.source, e.reason, e.risk_level,
               c.full_name
          from crm.clinical_escalations e
          join crm.customers c on c.id = e.customer_id
         where e.status = 'pending'
         order by e.created_at desc limit {_TRAN}
        """)
    chuyen_mon = repo.users_theo_vai_tro("Người chuyên môn")
    n_pu = n_cm = 0
    for r in rows:
        phan_ung = r["source"] == "medication_risk"
        loai = "khach_co_phan_ung" if phan_ung else "khach_can_chuyen_chuyen_mon"
        tat = tat_pu if phan_ung else tat_cm
        nhan = [r["assigned_to"]] if r["assigned_to"] else chuyen_mon
        for uid in nhan:
            if uid in tat:
                continue
            them = _day(loai, uid,
                        f"{LOAI[loai][0]}: {r['full_name']}",
                        f"{loai}:{r['id']}:{uid}",
                        body=r["reason"],
                        priority="urgent" if r["risk_level"] in ("high", "critical")
                                 else "high",
                        related_type="clinical_escalation", related_id=r["id"])
            if phan_ung:
                n_pu += them
            else:
                n_cm += them
    return n_pu, n_cm


def _quet_don(tat_giao: set[int], tat_hoan: set[int]) -> tuple[int, int]:
    """Đơn giao thành công / đơn hoàn — báo Sale và CSKH đang giữ khách."""
    rows = _truy_van(
        f"""
        select o.id, o.status, o.total_amount, o.delivered_at, c.full_name,
               o.sale_owner_id, o.cskh_owner_id,
               (select a.user_id from crm.customer_assignments a
                 where a.customer_id = o.customer_id and a.assignment_type = 'sale'
                   and a.end_at is null limit 1) as sale_pt,
               (select a.user_id from crm.customer_assignments a
                 where a.customer_id = o.customer_id and a.assignment_type = 'cskh'
                   and a.end_at is null limit 1) as cskh_pt
          from crm.orders o join crm.customers c on c.id = o.customer_id
         where o.updated_at > now() - interval '3 days'
           and o.status in ('delivered','collected','returning','returned')
         order by o.updated_at desc limit {_TRAN}
        """)
    n_giao = n_hoan = 0
    for r in rows:
        hoan = r["status"] in ("returning", "returned")
        loai = "don_hoan" if hoan else "don_giao_thanh_cong"
        tat = tat_hoan if hoan else tat_giao
        tien = f"{float(r['total_amount'] or 0):,.0f} ₫".replace(",", ".")
        nhan = {r["sale_owner_id"], r["sale_pt"], r["cskh_owner_id"], r["cskh_pt"]}
        for uid in nhan:
            if not uid or uid in tat:
                continue
            them = _day(loai, uid,
                        f"{LOAI[loai][0]}: {r['full_name']}",
                        f"{loai}:{r['id']}:{uid}",
                        body=f"Đơn #{r['id']} · {tien}",
                        related_type="order", related_id=r["id"])
            if hoan:
                n_hoan += them
            else:
                n_giao += them
    return n_giao, n_hoan


def _quet_mua_lai(tat: set[int]) -> int:
    """Cơ hội mua lại tới ngày dự kiến chốt (B10 đổ dữ liệu)."""
    rows = _truy_van(
        f"""
        select r.id, r.owner_id, r.expected_close_date, r.expected_value,
               c.full_name
          from crm.repurchase_opportunities r
          join crm.customers c on c.id = r.customer_id
         where r.owner_id is not null
           and r.stage not in ('won','lost')
           and r.expected_close_date is not null
           and r.expected_close_date <= current_date
         order by r.expected_close_date asc limit {_TRAN}
        """)
    n = 0
    for r in rows:
        if r["owner_id"] in tat:
            continue
        n += _day("khach_den_han_mua_lai", r["owner_id"],
                  f"Đến hạn mua lại: {r['full_name']}",
                  f"khach_den_han_mua_lai:{r['id']}",
                  body=f"Dự kiến chốt {r['expected_close_date']:%d/%m/%Y}",
                  related_type="repurchase_opportunity", related_id=r["id"])
    return n


def _quet_cho_duyet(tat: set[int]) -> int:
    """Sản phẩm sửa nội dung chờ duyệt (B6) + đề xuất liệu trình chờ chuyên môn."""
    nhan = [u for u in repo.users_co_quyen("content.approve") if u not in tat]
    if not nhan:
        return 0
    sp = _truy_van(
        f"select id, name from crm.products where approval_status = 'pending' "
        f"order by updated_at desc limit {_TRAN}")
    dx = _truy_van(
        f"""
        select r.id, c.full_name
          from crm.treatment_recommendations r
          join crm.customers c on c.id = r.customer_id
         where r.status = 'pending_approval'
         order by r.created_at desc limit {_TRAN}
        """)
    n = 0
    for uid in nhan:
        for r in sp:
            n += _day("noi_dung_cho_duyet", uid,
                      f"Sản phẩm chờ duyệt: {r['name']}",
                      f"noi_dung_cho_duyet:product:{r['id']}:{uid}",
                      related_type="product", related_id=r["id"])
        for r in dx:
            n += _day("noi_dung_cho_duyet", uid,
                      f"Đề xuất liệu trình chờ duyệt: {r['full_name']}",
                      f"noi_dung_cho_duyet:recommendation:{r['id']}:{uid}",
                      priority="high", link="/crm/khach-hang",
                      related_type="treatment_recommendation", related_id=r["id"])
    return n


def _quet_loi_dong_bo(tat: set[int]) -> int:
    """Hàng đợi lỗi đồng bộ: chỉ báo dòng ĐÃ BỎ CUỘC (given_up) hoặc thử lại
    nhiều lần — lỗi mạng thoáng qua worker tự chữa, không cần réo người."""
    rows = _truy_van(
        f"""
        select id, provider, entity, external_id, error_message, retry_count, status
          from crm.sync_errors
         where status = 'given_up' or (status = 'pending' and retry_count >= 3)
         order by updated_at desc limit {_TRAN}
        """)
    nhan = [u for u in repo.users_co_quyen("integration.manage") if u not in tat]
    n = 0
    for r in rows:
        for uid in nhan:
            n += _day("loi_dong_bo", uid,
                      f"Lỗi đồng bộ {r['provider']} · {r['entity']}",
                      f"loi_dong_bo:{r['id']}:{uid}",
                      body=f"#{r['external_id']} — {(r['error_message'] or '')[:180]}"
                           f" (đã thử {r['retry_count']} lần)",
                      priority="urgent" if r["status"] == "given_up" else "high",
                      related_type="sync_error", related_id=r["id"])
    return n


def quet_tat_ca() -> dict:
    """Một lượt quét đủ 11 loại. Trả {loại: số thông báo MỚI}.

    Từng nguồn tự nuốt lỗi: một nguồn hỏng (bảng của lát chưa làm, DB đang
    migrate…) không được chặn 10 nguồn còn lại.
    """
    tat = {loai: repo.dang_tat(loai) for loai in LOAI}
    ket: dict[str, int] = {}

    def chay(ten: str, fn, *a) -> None:
        try:
            ket[ten] = fn(*a)
        except Exception as err:  # noqa: BLE001 — xem docstring
            ket[ten] = 0
            print(f"[notify] nguồn {ten} lỗi: {type(err).__name__}: {err}",
                  file=sys.stderr)

    chay("lead_moi", _quet_lead_moi, tat["lead_moi"])
    try:
        sap, qua = _quet_viec(tat["viec_sap_den_han"], tat["viec_qua_han"])
        ket["viec_sap_den_han"], ket["viec_qua_han"] = sap, qua
    except Exception as err:  # noqa: BLE001
        ket["viec_sap_den_han"] = ket["viec_qua_han"] = 0
        print(f"[notify] nguồn việc lỗi: {err}", file=sys.stderr)
    chay("khach_can_goi_lai", _quet_goi_lai, tat["khach_can_goi_lai"])
    try:
        pu, cm = _quet_ca_chuyen_mon(tat["khach_co_phan_ung"],
                                     tat["khach_can_chuyen_chuyen_mon"])
        ket["khach_co_phan_ung"], ket["khach_can_chuyen_chuyen_mon"] = pu, cm
    except Exception as err:  # noqa: BLE001
        ket["khach_co_phan_ung"] = ket["khach_can_chuyen_chuyen_mon"] = 0
        print(f"[notify] nguồn ca lâm sàng lỗi: {err}", file=sys.stderr)
    try:
        giao, hoan = _quet_don(tat["don_giao_thanh_cong"], tat["don_hoan"])
        ket["don_giao_thanh_cong"], ket["don_hoan"] = giao, hoan
    except Exception as err:  # noqa: BLE001
        ket["don_giao_thanh_cong"] = ket["don_hoan"] = 0
        print(f"[notify] nguồn đơn lỗi: {err}", file=sys.stderr)
    chay("khach_den_han_mua_lai", _quet_mua_lai, tat["khach_den_han_mua_lai"])
    chay("noi_dung_cho_duyet", _quet_cho_duyet, tat["noi_dung_cho_duyet"])
    chay("loi_dong_bo", _quet_loi_dong_bo, tat["loi_dong_bo"])
    return ket


# ------------------------------------------------------------------ đọc/ghi
def danh_sach(user_id: int, **kw) -> tuple[list[dict], int]:
    """NOTIFY-001."""
    return repo.list_notifications(user_id=user_id, **kw)


def dem_chua_doc(user_id: int) -> dict:
    return repo.dem_chua_doc(user_id)


def danh_dau_doc(notification_id: int, actor: dict | None) -> dict:
    """NOTIFY-002 — không tìm thấy CỦA MÌNH thì 404 (không lộ của người khác)."""
    uid = _actor_id(actor)
    row = repo.danh_dau_doc(notification_id, uid)
    if row:
        return row
    cu = repo.get(notification_id, uid)
    if not cu:
        raise ApiError("NOT_FOUND", "Không tìm thấy thông báo")
    return cu   # đã đọc từ trước — coi như thành công, khỏi báo lỗi vô ích


def danh_dau_doc_het(actor: dict | None) -> dict:
    """NOTIFY-003."""
    return {"da_danh_dau": repo.danh_dau_doc_het(_actor_id(actor))}


def lay_cai_dat(actor: dict | None) -> dict:
    """Trả ĐỦ 11 loại kèm nhãn + trạng thái bật/tắt (thiếu dòng = bật)."""
    da_doi = repo.cai_dat(_actor_id(actor))
    return {
        "items": [
            {"type": ma, "label": nhan, "enabled": da_doi.get(ma, True)}
            for ma, (nhan, _uu, _link) in LOAI.items()
        ]
    }


def dat_cai_dat(doi: dict[str, bool], actor: dict | None) -> dict:
    """NOTIFY-004 — chỉ nhận mã trong 11 loại chuẩn."""
    la = [k for k in doi if k not in LOAI]
    if la:
        raise ApiError("VALIDATION_ERROR",
                       f"Loại thông báo không hợp lệ: {', '.join(la)}",
                       errors={"types": f"hợp lệ: {', '.join(LOAI)}"})
    repo.dat_cai_dat(_actor_id(actor), doi)
    return lay_cai_dat(actor)
