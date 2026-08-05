"""Truy vấn C6 — QUY TRÌNH CSKH (port mẫu Kallet `includes/cskh_quy_trinh.php`
+ nửa CSKH của `includes/board_rules.php`).

Chỉ SQL. Toàn bộ luật (ba giai đoạn · thang mốc · nhịp nhắc voucher · đợt bám
đuổi khuyến mãi) nằm ở `services/cskh_service.py`.

Hai điểm khác mẫu, cố ý:
  * Mẫu có bảng `care_actions` riêng để ghi lượt gọi. Bên ta NỚI
    `care_interactions` (B9) — cùng khái niệm "một lần chạm khách", đẻ bảng thứ
    hai là hai nguồn đá nhau lúc đếm công.
  * Mẫu đọc `customers.ngay_nhan_hang_cuoi`. Bên ta là
    `customers.last_delivered_at` (C1 đã có, worker đơn hàng tự đóng dấu).
"""

from app.core.ngay import hom_nay
from app.db.client import get_pg_pool

# Trạng thái voucher tính là khách ĐANG CẦM MÃ.
TT_SONG = ("chua_bao_ma", "con_han")


# ------------------------------------------------------------------ thang mốc
def moc(dept: str = "cskh", chi_active: bool = True) -> list[dict]:
    """Bộ mốc trong bảng, theo thứ tự ngày."""
    dk = "dept = %s" + (" and active" if chi_active else "")
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select * from crm.care_milestones where {dk} order by offset_days",
            (dept,),
        ).fetchall()


def luu_moc(code: str, **f) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.care_milestones
                   (code, dept, offset_days, window_from, window_to,
                    board_column, promo, sender, active)
            values (%(code)s, %(dept)s, %(offset_days)s, %(window_from)s,
                    %(window_to)s, %(board_column)s, %(promo)s, %(sender)s, true)
            on conflict (code) do update set
                offset_days  = excluded.offset_days,
                window_from  = excluded.window_from,
                window_to    = excluded.window_to,
                board_column = excluded.board_column,
                promo        = excluded.promo,
                active       = true
            returning *
            """,
            {"code": code, "dept": "cskh", "sender": "nguoi", **f},
        ).fetchone()


def tat_moc(code: str) -> None:
    """TẮT chứ KHÔNG xoá — giữ lịch sử, lỡ cần quay lại còn dữ liệu."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.care_milestones set active = false where code = %s",
            (code,))


def sua_moc(moc_id: int, *, offset_days: int | None = None,
            label: str | None = None, sender: str | None = None,
            active: bool | None = None) -> dict | None:
    """Sửa MỘT mốc từ màn Cài đặt → 1D (số ngày · nhãn 📌 · ai gửi · bật/tắt).

    Chỉ đụng đúng trường được truyền — form 1D gửi cả bảng nên phải để trường
    nào không đổi thì y nguyên, không ghi đè bằng None."""
    dat, ts = [], {"id": moc_id}
    if offset_days is not None:
        dat.append("offset_days = %(ngay)s")
        ts["ngay"] = offset_days
    if label is not None:
        dat.append("label = %(nhan)s")
        ts["nhan"] = label.strip()
    if sender is not None:
        dat.append("sender = %(ai)s")
        ts["ai"] = sender
    if active is not None:
        dat.append("active = %(bat)s")
        ts["bat"] = active
    if not dat:
        return None
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"update crm.care_milestones set {', '.join(dat)} "
            "where id = %(id)s returning *", ts,
        ).fetchone()


# ------------------------------------------------------------------ khuyến mãi
def ctkm_dang_chay(ngay=None) -> dict | None:
    """Đợt khuyến mãi đang chạy hôm nay (mới nhất). None = không có đợt nào."""
    ngay = ngay or hom_nay()
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select * from crm.cskh_promos
             where active
               and (start_on is null or start_on <= %(n)s)
               and (end_on   is null or end_on   >= %(n)s)
             order by id desc limit 1
            """,
            {"n": ngay},
        ).fetchone()


def ctkm_ds(limit: int = 50) -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.cskh_promos order by active desc, id desc "
            "limit %s", (limit,)).fetchall()


def ctkm_luu(promo_id: int | None, **f) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        if promo_id:
            return conn.execute(
                """
                update crm.cskh_promos set
                       name = %(name)s, content = %(content)s,
                       start_on = %(start_on)s, end_on = %(end_on)s,
                       active = %(active)s
                 where id = %(id)s returning *
                """,
                {"id": promo_id, **f},
            ).fetchone()
        return conn.execute(
            """
            insert into crm.cskh_promos
                   (name, content, start_on, end_on, active, created_by)
            values (%(name)s, %(content)s, %(start_on)s, %(end_on)s,
                    %(active)s, %(created_by)s)
            returning *
            """,
            {"created_by": None, **f},
        ).fetchone()


def ctkm_xoa(promo_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("delete from crm.cskh_promos where id = %s", (promo_id,))


# ------------------------------------------------------------------ voucher
def voucher_song(customer_id: int, ngay=None) -> dict | None:
    """Voucher còn SỐNG của khách tại một mốc ngày.

    `ngay` truyền vào chính là cách vá BẪY 2 của mẫu: xét mã tại NGÀY ĐẶT ĐƠN
    chứ không phải ngày giao — xem `cskh_service.don_thanh_cong`.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select * from crm.vouchers
             where customer_id = %(kh)s and status = any(%(tt)s)
               and expires_on >= %(n)s
             order by expires_on desc limit 1
            """,
            {"kh": customer_id, "tt": list(TT_SONG), "n": ngay or hom_nay()},
        ).fetchone()


def voucher_map(ids: list[int], ngay=None) -> dict[int, dict]:
    """Voucher sống của NHIỀU khách một lượt — bảng việc nạp vài trăm khách,
    hỏi từng dòng là N+1.

    Xếp hạn TĂNG DẦN rồi để dòng sau đè dòng trước ⇒ giữ mã hết hạn XA NHẤT
    (đúng nết mẫu: khách cầm 2 mã thì nhắc theo mã dùng được lâu hơn).
    """
    ids = [int(i) for i in set(ids or []) if i]
    if not ids:
        return {}
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            select * from crm.vouchers
             where customer_id = any(%(ids)s) and status = any(%(tt)s)
               and expires_on >= %(n)s
             order by expires_on asc
            """,
            {"ids": ids, "tt": list(TT_SONG), "n": ngay or hom_nay()},
        ).fetchall()
    return {int(r["customer_id"]): dict(r) for r in rows}


def tieu_voucher(voucher_id: int, order_id: int) -> dict | None:
    """Đánh dấu mã đã dùng cho một đơn."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.vouchers set status = 'da_dung', order_used_id = %s, "
            "updated_at = now() where id = %s returning *",
            (order_id, voucher_id),
        ).fetchone()


def tang_voucher_may(customer_id: int, *, amount, granted_on, expires_on,
                     note: str, order_from_id: int | None = None) -> dict:
    """MÁY tặng mã: để trống `code` ⇒ trạng thái `chua_bao_ma`.

    Không phải lỗi dữ liệu mà là VIỆC CẦN LÀM — máy đã cấp quyền lợi, mã cụ thể
    thì khâu báo khách điền (luật 4 của C1).
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.vouchers
                   (customer_id, code, amount, granted_by_kind, granted_on,
                    expires_on, status, note, order_from_id)
            values (%(kh)s, '', %(tien)s, 'may', %(tu)s, %(den)s,
                    'chua_bao_ma', %(gc)s, %(don)s)
            returning *
            """,
            {"kh": customer_id, "tien": amount, "tu": granted_on,
             "den": expires_on, "gc": note[:255], "don": order_from_id},
        ).fetchone()


# ------------------------------------------------------------------ lượt gọi
def goi_map(ids: list[int], tu_ngay) -> dict[int, dict]:
    """Khách nào ĐÃ ĐƯỢC GỌI kể từ `tu_ngay` (một đợt bám đuổi).

    Lấy lượt gọi GẦN NHẤT của mỗi khách kèm kết quả — luật "mỗi khách chỉ gọi
    1 LẦN trong cả đợt" dựa hẳn vào đây.
    """
    ids = [int(i) for i in set(ids or []) if i]
    if not ids or not tu_ngay:
        return {}
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            select distinct on (ci.customer_id)
                   ci.customer_id, ci.call_result,
                   coalesce(ci.action_at, ci.created_at) as luc
              from crm.care_interactions ci
             where ci.customer_id = any(%(ids)s)
               and ci.channel = 'call'
               and coalesce(ci.verify_status, '') <> 'bac_bo'
               and coalesce(ci.action_at, ci.created_at) >= %(tu)s
             order by ci.customer_id, luc desc
            """,
            {"ids": ids, "tu": tu_ngay},
        ).fetchall()
    return {int(r["customer_id"]): dict(r) for r in rows}


def ghi_goi(customer_id: int, ket_qua: str, *, nguoi: int | None,
            tom_tat: str = "") -> dict:
    """Ghi một lượt GỌI vào `care_interactions` (bảng chạm khách dùng chung)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.care_interactions
                   (customer_id, user_id, channel, contacted, call_result,
                    summary, action_kind, action_at)
            values (%(kh)s, %(nv)s, 'call', %(gap)s, %(kq)s, %(tt)s, 'goi', now())
            returning *
            """,
            {"kh": customer_id, "nv": nguoi, "gap": ket_qua == "nghe",
             "kq": ket_qua, "tt": tom_tat[:500]},
        ).fetchone()


def ghi_cham(customer_id: int, *, nguoi: int | None, kenh: str = "chat",
             tom_tat: str = "") -> dict:
    """Ghi một lượt CHĂM (nhắn tin) — đóng mốc đang mở của khách."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.care_interactions
                   (customer_id, user_id, channel, contacted, summary,
                    action_kind, action_at)
            values (%(kh)s, %(nv)s, %(kenh)s, true, %(tt)s, 'nhan', now())
            returning *
            """,
            {"kh": customer_id, "nv": nguoi, "kenh": kenh,
             "tt": tom_tat[:500]},
        ).fetchone()


# ------------------------------------------------------------------ bảng việc
# Khách của bảng CSKH = khách ĐÃ TỪNG NHẬN HÀNG (có last_delivered_at). Chưa
# nhận hàng lần nào là việc của Sale, không phải của bảng này.
# Số ngày kể từ NGÀY NHẬN HÀNG CUỐI — trục thời gian của cả quy trình CSKH.
# Để một chỗ vì nó vừa nằm trong SELECT vừa nằm trong WHERE (bộ lọc dải ngày):
# chép hai bản là sớm muộn cũng lệch một bản, mà lệch kiểu này rất khó thấy.
_NGAY_SQL = ("(now() at time zone 'Asia/Ho_Chi_Minh')::date"
             " - (c.last_delivered_at at time zone 'Asia/Ho_Chi_Minh')::date")

_CHON = f"""
    c.id, c.full_name, c.primary_phone, c.card_rank, c.total_spent,
    c.do_not_contact,
    c.last_delivered_at, c.cskh_column, c.cskh_column_at,
    {_NGAY_SQL} as ngay,
    ht.khach_cuoi, ht.shop_cuoi,
    cs.cham_cuoi, cs.cham_hom_nay,
    dh.dang_chay,
    pt.owner_id, pt.owner_name,
    p.external_page_id, cv.external_conversation_id
"""

_TU = """
    from crm.customers c
    left join lateral (
        select max(m.sent_at) filter (where m.sender_type = 'customer')
                   as khach_cuoi,
               max(m.sent_at) filter (where m.sender_type = 'agent')
                   as shop_cuoi
          from crm.messages m
          join crm.conversations c2 on c2.id = m.conversation_id
         where c2.customer_id = c.id
    ) ht on true
    left join lateral (
        select max(coalesce(ci.action_at, ci.created_at)) as cham_cuoi,
               count(*) filter (
                   where (coalesce(ci.action_at, ci.created_at)
                          at time zone 'Asia/Ho_Chi_Minh')::date
                       = (now() at time zone 'Asia/Ho_Chi_Minh')::date
               ) as cham_hom_nay
          from crm.care_interactions ci
         where ci.customer_id = c.id
           and coalesce(ci.verify_status, '') <> 'bac_bo'
    ) cs on true
    left join lateral (
        select count(*) as dang_chay from crm.orders o
         where o.customer_id = c.id
           and o.status in ('confirmed', 'packing', 'shipping')
    ) dh on true
    left join lateral (
        select a.user_id as owner_id, u.name as owner_name
          from crm.customer_assignments a
          join crm.users u on u.id = a.user_id
         where a.customer_id = c.id and a.end_at is null
           and a.assignment_type = 'cskh'
         order by a.id desc limit 1
    ) pt on true
    left join lateral (
        select cv.external_conversation_id, cv.page_id
          from crm.conversations cv where cv.customer_id = c.id
         order by cv.last_message_at desc nulls last limit 1
    ) cv on true
    left join crm.pages p on p.id = cv.page_id
"""


def _dk_vong(ngay_buong: int) -> list[str]:
    """Điều kiện "khách đang trong VÒNG CHĂM" — dùng chung cho bảng việc và mọi
    ô đếm, để số trên dải lọc không bao giờ đá với số thẻ bày ra."""
    return ["c.deleted_at is null", "c.status <> 'merged'",
            "c.last_delivered_at is not null",
            f"{_NGAY_SQL} <= %(buong)s"]


def bang_viec(*, owner_id: int | None = None, q: str = "",
              ngay_buong: int = 210, limit: int = 500,
              staff_id: int | None = None, chua_gan: bool = False,
              page_id: int | None = None, hang_the: str = "",
              nhan_tu: int | None = None,
              nhan_den: int | None = None) -> list[dict]:
    """Khách đang trong VÒNG CHĂM — service tự xếp cột.

    Cắt sẵn ở tầng SQL hai nhóm không bao giờ lên bảng: khách chưa nhận hàng
    bao giờ, và khách đã quá ngày buông (mẫu: >210 ngày = coi như ngủ, thuộc
    màn Khách ngủ chứ không phải bảng việc).

    Bộ lọc màn (port từ dải lọc `index.php?bp=cskh`):
      `owner_id`         — bó về "khách của tôi" (do route quyết theo quyền).
      `staff_id`         — quản lý chọn XEM CỦA AI. Đi cùng `chua_gan`.
      `chua_gan`         — khách chưa có người phụ trách CSKH ("— Chưa gán —").
      `page_id`          — fanpage của hội thoại MỚI NHẤT của khách.
      `hang_the`         — mã hạng thẻ; "chua_xep_hang" = chưa có hạng nào.
      `nhan_tu/nhan_den` — DẢI SỐ NGÀY kể từ ngày nhận hàng cuối (không phải
                           ngày dương lịch): mẫu lọc "nhận hàng cách đây 45–104
                           ngày", vì cột trên bảng cũng đo bằng thang đó.

    🔑 `hang_the="chua_xep_hang"` là `card_rank is null` chứ không phải chuỗi
    rỗng: mẫu tính "Chưa xếp hạng" là trạng thái thứ 6 có thật (khách chi tiêu
    đúng 0đ), đếm riêng — không phải rác dữ liệu.
    """
    dk = _dk_vong(ngay_buong)
    ts: dict = {"buong": ngay_buong, "lim": limit}
    if owner_id:
        dk.append("pt.owner_id = %(nv)s")
        ts["nv"] = owner_id
    if staff_id:
        dk.append("pt.owner_id = %(nv2)s")
        ts["nv2"] = staff_id
    if chua_gan:
        dk.append("pt.owner_id is null")
    if page_id:
        dk.append("cv.page_id = %(page)s")
        ts["page"] = page_id
    if hang_the == "chua_xep_hang":
        dk.append("c.card_rank is null")
    elif hang_the:
        dk.append("c.card_rank = %(hang)s")
        ts["hang"] = hang_the
    if nhan_tu is not None:
        dk.append(f"{_NGAY_SQL} >= %(ntu)s")
        ts["ntu"] = nhan_tu
    if nhan_den is not None:
        dk.append(f"{_NGAY_SQL} <= %(nden)s")
        ts["nden"] = nhan_den
    if q.strip():
        dk.append("(c.full_name ilike %(q)s or c.primary_phone like %(q)s)")
        ts["q"] = f"%{q.strip()}%"
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON} {_TU} where {' and '.join(dk)} "
            "order by c.last_delivered_at desc nulls last limit %(lim)s",
            ts,
        ).fetchall()


# ------------------------------------------------------------ nguồn ô xổ lọc
def nhan_vien_co_khach(ngay_buong: int = 210) -> list[dict]:
    """Người đang phụ trách khách CSKH còn trong vòng chăm — nguồn ô lọc
    "nhân viên".

    Cố ý KHÔNG lấy cả bảng `users`: danh sách đó gồm kế toán, admin, người đã
    nghỉ — chọn xong bảng trắng mà không hiểu vì sao. Tên nào hiện ra ở đây
    cũng chắc chắn bấm vào là có thẻ.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select u.id, u.name, count(*) as so_khach
              from crm.customers c
              join crm.customer_assignments a
                on a.customer_id = c.id and a.end_at is null
               and a.assignment_type = 'cskh'
              join crm.users u on u.id = a.user_id
             where {' and '.join(_dk_vong(ngay_buong))}
             group by u.id, u.name
             order by u.name
            """,
            {"buong": ngay_buong},
        ).fetchall()


def fanpage_co_khach(ngay_buong: int = 210) -> list[dict]:
    """Fanpage có khách CSKH còn trong vòng chăm — nguồn ô lọc "fanpage"."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select p.id, p.name, count(*) as so_khach
              from crm.customers c
              join lateral (
                  select cv.page_id from crm.conversations cv
                   where cv.customer_id = c.id
                   order by cv.last_message_at desc nulls last limit 1
              ) cv on true
              join crm.pages p on p.id = cv.page_id
             where {' and '.join(_dk_vong(ngay_buong))}
             group by p.id, p.name
             order by p.name
            """,
            {"buong": ngay_buong},
        ).fetchall()


def hoi_thoai_map(ids: list[int]) -> dict[int, dict]:
    """Hội thoại MỚI NHẤT của mỗi khách — nuôi cột phải của màn focus 1 cột.

    Chỉ đọc `crm.conversations` (đã có sẵn `snippet` + `last_message_at` do
    worker đổ về), KHÔNG đụng `crm.messages`: danh sách bên phải chỉ cần một
    dòng xem trước, mở hẳn khung chat mới cần tin thật.
    """
    ids = [int(i) for i in set(ids or []) if i]
    if not ids:
        return {}
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            select distinct on (cv.customer_id)
                   cv.customer_id, cv.id as conversation_id, cv.snippet,
                   cv.last_message_at, cv.unread_count,
                   cv.external_conversation_id, p.external_page_id
              from crm.conversations cv
              left join crm.pages p on p.id = cv.page_id
             where cv.customer_id = any(%(ids)s)
             order by cv.customer_id, cv.last_message_at desc nulls last
            """,
            {"ids": ids},
        ).fetchall()
    return {int(r["customer_id"]): dict(r) for r in rows}


def hang_the_ds() -> list[dict]:
    """Bậc thang hạng thẻ, hạng TO trước — nguồn ô lọc "hạng thẻ"."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select code, name, emoji from crm.card_ranks "
            "order by sort_order desc, code"
        ).fetchall()


def dem_khach_ngu(ngay_buong: int = 210) -> int:
    """Khách đã QUÁ ngày buông = coi như ngủ, chỉ chăm khi có chiến dịch.

    Mẫu bày con số này ngay trên bảng việc CSKH: họ không nằm trong bảng nhưng
    vẫn là khách của mình — giấu hẳn thì đội tưởng đã mất.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            f"""
            select count(*) as n from crm.customers c
             where c.deleted_at is null and c.status <> 'merged'
               and c.last_delivered_at is not null
               and not c.do_not_contact
               and {_NGAY_SQL} > %(buong)s
            """,
            {"buong": ngay_buong},
        ).fetchone()
    return int((r or {}).get("n") or 0)


def mot_khach(customer_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON} {_TU} where c.id = %s", (customer_id,)
        ).fetchone()


# ------------------------------------------------------------------ cột đặt tay
def dat_cot(customer_id: int, cot: str | None, nguoi: int | None) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        # `%s::text` chứ không phải `%s` trần: trong nhánh CASE, Postgres không
        # suy được kiểu tham số nào cả (IndeterminateDatatype).
        return conn.execute(
            "update crm.customers set cskh_column = %s, "
            "cskh_column_at = case when %s::text is null then null "
            "                      else now() end, "
            "cskh_column_by = %s where id = %s returning id, cskh_column",
            (cot, cot, nguoi, customer_id),
        ).fetchone()


def nha_cot_da_cu() -> int:
    """Cột đặt tay TỰ NHẢ khi khách nhắn mới SAU lúc đặt.

    Thiếu bước này thì "Từ chối đợt này" kẹt vĩnh viễn: khách quay lại nhắn mà
    thẻ vẫn nằm im trong cột Từ chối, không ai thấy.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            """
            update crm.customers c set cskh_column = null, cskh_column_at = null
             where c.cskh_column is not null
               and exists (
                   select 1 from crm.messages m
                     join crm.conversations cv on cv.id = m.conversation_id
                    where cv.customer_id = c.id
                      and m.sender_type = 'customer'
                      and m.sent_at > c.cskh_column_at)
            """
        )
        return cur.rowcount or 0


# ------------------------------------------------------------------ đơn hàng
def don(order_id: int) -> dict | None:
    """Đơn + NGÀY ĐẶT.

    Ngày đặt = `pos_inserted_at` với đơn về từ POS, `created_at` với đơn nhập
    thẳng trên CRM — đúng quy ước bảng Đơn hàng đang dùng. Ngày này là mốc xét
    "khách có cầm mã lúc đặt không" (BẪY 2), đừng thay bằng ngày giao.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select id, customer_id, order_type, status, delivered_at, "
            "created_at, coalesce(pos_inserted_at, created_at) as ngay_dat "
            "from crm.orders where id = %s", (order_id,)
        ).fetchone()
