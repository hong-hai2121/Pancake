"""Truy vấn C5 — thang bám đuổi Sale + bảng việc (port mẫu Kallet
includes/sale_buoc.php · includes/board_rules.php).

Chỉ SQL. Luật (con trỏ chỉ tiến · nhảy cóc · trần bước/ngày · cửa giờ) nằm ở
services/sale_service.py.
"""

from app.core.ngay import hom_nay
from app.db.client import get_pg_pool


# ------------------------------------------------------------------ thang bước
def thang() -> list[dict]:
    """Các bước ĐANG DÙNG, theo thứ tự. Thang rỗng = mọi luật thang tự tắt."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.sale_steps where status = 'active' "
            "order by step_no"
        ).fetchall()


def luu_buoc(step_no: int, *, name: str | None = None, work: str | None = None,
             kw_nv: str | None = None, kw_kh: str | None = None,
             status: str | None = None) -> dict:
    """Ghi một bước. Trường nào KHÔNG truyền thì GIỮ NGUYÊN giá trị đang có.

    Phân biệt rõ hai thứ hay bị lẫn: `None` = "không đụng tới", còn chuỗi RỖNG
    = "admin xoá trắng ô này" và phải ghi được. Nhờ vậy form sửa tên không thổi
    bay từ khoá, và `status=None` không vô tình bật lại bước admin đã tắt.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.sale_steps
                   (step_no, name, work, keywords_agent, keywords_customer,
                    status)
            values (%(step_no)s, coalesce(%(name)s::text, ''),
                    coalesce(%(work)s::text, ''),
                    coalesce(%(kw_nv)s::text, ''),
                    coalesce(%(kw_kh)s::text, ''),
                    coalesce(%(status)s::text, 'active'))
            on conflict (step_no) do update set
                name = coalesce(%(name)s::text, crm.sale_steps.name),
                work = coalesce(%(work)s::text, crm.sale_steps.work),
                keywords_agent = coalesce(%(kw_nv)s::text,
                                          crm.sale_steps.keywords_agent),
                keywords_customer = coalesce(%(kw_kh)s::text,
                                             crm.sale_steps.keywords_customer),
                status = coalesce(%(status)s::text, crm.sale_steps.status)
            returning *
            """,
            {"step_no": step_no, "name": name, "work": work, "kw_nv": kw_nv,
             "kw_kh": kw_kh, "status": status},
        ).fetchone()


def thang_tat_ca() -> list[dict]:
    """CẢ bước đang tắt — màn cấu hình phải thấy hết để bật lại được.
    (Khác `thang()` chỉ trả bước đang dùng cho bộ dò.)"""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.sale_steps order by step_no"
        ).fetchall()


# ------------------------------------------------------------------ tin nhắn
def tin_cua_lead(customer_id: int, tu_ngay, gioi_han: int = 500) -> list[dict]:
    """Tin hai chiều của khách kể từ NGÀY BẬT THANG, theo đúng thứ tự thời gian.

    Lấy `gioi_han` tin CUỐI rồi lật lại (không phải tin ĐẦU): hội thoại dài
    vượt trần thì các tin MỚI NHẤT mới là thứ cần đọc — bản cũ của mẫu lấy tin
    đầu nên con trỏ đóng băng vĩnh viễn với khách nhắn nhiều.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select huong, nguoi_that, noi_dung, co_anh, sent_at,
                   sender_user_id from (
                select case when m.sender_type = 'customer' then 'khach'
                            else 'shop' end                     as huong,
                       -- Tin MÁY (bot/không rõ người) vẫn được tính bước, nhưng
                       -- CHỈ khi dò ra đúng từ khoá — xem sale_service.do_buoc.
                       (m.sender_type = 'agent'
                        and m.sender_user_id is not null)        as nguoi_that,
                       m.content                                as noi_dung,
                       (coalesce(m.msg_type, '') = 'image'
                        or m.attachments is not null)            as co_anh,
                       m.sent_at, m.sender_user_id, m.id
                  from crm.messages m
                  join crm.conversations cv on cv.id = m.conversation_id
                 where cv.customer_id = %(kh)s and m.sent_at >= %(tu)s
                   and m.sender_type in ('customer', 'agent', 'bot')
                 order by m.sent_at desc, m.id desc
                 limit %(lim)s
            ) t order by t.sent_at, t.id
            """,
            {"kh": customer_id, "tu": tu_ngay, "lim": gioi_han},
        ).fetchall()


def moc_tin(customer_id: int) -> dict | None:
    """Ba mốc quyết định "ai nhắn cuối": tin khách cuối · tin shop cuối · tin
    của NGƯỜI THẬT cuối (loại tin bot/máy — chúng không tính là đã tư vấn)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select max(m.sent_at) filter (where m.sender_type = 'customer')
                       as khach_cuoi,
                   max(m.sent_at) filter (where m.sender_type = 'agent')
                       as shop_cuoi,
                   max(m.sent_at) filter (where m.sender_type = 'agent'
                                            and m.sender_user_id is not null)
                       as nguoi_cuoi
              from crm.messages m
              join crm.conversations cv on cv.id = m.conversation_id
             where cv.customer_id = %s
            """,
            (customer_id,),
        ).fetchone()


# ------------------------------------------------------------------ con trỏ
def dat_con_tro(lead_id: int, buoc: int, luc, *, cong_dem: bool = True) -> dict | None:
    """Đẩy con trỏ. CHỈ TIẾN (điều kiện `sale_step < %s` ở WHERE).

    `cong_dem` — có tính vào trần bước/ngày không. Nhảy cóc do khách nói thì
    KHÔNG tính (khách nói toạc ra rồi, không phải nhân viên bắn tin cho xong)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            update crm.leads set
                   sale_step = %(buoc)s,
                   sale_step_at = %(luc)s,
                   sale_step_day = case when %(dem)s then %(ngay)s
                                        else sale_step_day end,
                   sale_step_count = case
                       when not %(dem)s then sale_step_count
                       when sale_step_day = %(ngay)s then sale_step_count + 1
                       else 1 end
             where id = %(id)s and sale_step < %(buoc)s
            returning *
            """,
            {"id": lead_id, "buoc": buoc, "luc": luc, "dem": cong_dem,
             "ngay": hom_nay()},
        ).fetchone()


def dat_lai_con_tro(lead_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.leads set sale_step = 0, sale_step_at = null, "
            "sale_step_day = null, sale_step_count = 0 where id = %s",
            (lead_id,))


def dat_con_tro_tay(lead_id: int, buoc: int) -> dict | None:
    """Nhân viên kéo thẻ sang cột "Bước N" ⇒ con trỏ = N-1 (đã làm tới N-1,
    việc kế đúng là N). Đây là đường DUY NHẤT cho phép con trỏ LÙI."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.leads set sale_step = %s, sale_step_at = now() "
            "where id = %s returning *", (max(0, buoc), lead_id),
        ).fetchone()


def danh_dau_tra_loi(lead_id: int, luc) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.leads set replied_at = greatest(coalesce(replied_at, "
            "%s), %s) where id = %s", (luc, luc, lead_id))


# ------------------------------------------------------------------ cột đặt tay
def dat_cot(lead_id: int, cot: str | None, nguoi: int | None) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        # Ép kiểu ::text cho tham số cột: nhả cột thì truyền NULL, mà NULL trần
        # trong `case when ... is null` làm Postgres không đoán được kiểu.
        return conn.execute(
            "update crm.leads set board_column = %(cot)s::text, "
            "board_column_at = case when %(cot)s::text is null then null "
            "                       else now() end, "
            "board_column_by = %(nv)s where id = %(id)s returning *",
            {"cot": cot, "nv": nguoi, "id": lead_id},
        ).fetchone()


def dat_hen(lead_id: int, luc) -> dict | None:
    """Đặt (hoặc xoá, `luc=None`) mốc hẹn mua của lead.

    Mốc này chính là thứ đẩy thẻ sang cột "Hẹn mua" (xem `cot_cua`), và hẹn quá
    ngày thì Ở LẠI cột đó với viền đỏ chứ không sang Quá hạn — ngoại lệ mẫu ghi
    rõ: hẹn trượt vẫn là hẹn, xử khác việc bị bỏ quên.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.leads set next_action_at = %s, updated_at = now() "
            "where id = %s and closed_at is null returning id, next_action_at",
            (luc, lead_id),
        ).fetchone()


def nha_cot_da_cu() -> int:
    """Cột đặt tay TỰ NHẢ khi khách nhắn mới SAU lúc đặt.

    Không có bước này thì "Từ chối đợt này" kẹt vĩnh viễn — khách quay lại nhắn
    mà thẻ vẫn nằm im trong cột Từ chối, không ai thấy."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            """
            update crm.leads l set board_column = null, board_column_at = null
             where l.board_column is not null
               and l.board_column <> 'ngung'
               and exists (
                   select 1 from crm.messages m
                     join crm.conversations cv on cv.id = m.conversation_id
                    where cv.customer_id = l.customer_id
                      and m.sender_type = 'customer'
                      and m.sent_at > l.board_column_at)
            """
        )
        return cur.rowcount or 0


# ------------------------------------------------------------------ bảng việc
_CHON_BANG = """
    l.id, l.customer_id, l.owner_id, l.sale_step, l.sale_step_at,
    l.sale_step_day, l.sale_step_count, l.replied_at, l.board_column,
    l.board_column_at, l.next_action_at, l.temperature, l.closed_at,
    l.created_at, l.stage_id,
    c.full_name, c.primary_phone, c.card_rank, c.do_not_contact,
    c.total_spent, c.source,
    u.name as owner_name,
    s.code as stage_code, s.name as stage_name,
    ht.khach_cuoi, ht.shop_cuoi, ht.nguoi_cuoi,
    p.external_page_id, p.name as page_name, cv.page_id,
    cv.external_conversation_id,
    (select count(*) from crm.care_interactions ci
      where ci.customer_id = l.customer_id
        and ci.verify_status <> 'bac_bo'
        and (ci.action_at at time zone 'Asia/Ho_Chi_Minh')::date
            = (now() at time zone 'Asia/Ho_Chi_Minh')::date) as cham_hom_nay
"""

_TU_BANG = """
    from crm.leads l
    join crm.customers c on c.id = l.customer_id
    left join crm.users u on u.id = l.owner_id
    left join crm.pipeline_stages s on s.id = l.stage_id
    left join lateral (
        select max(m.sent_at) filter (where m.sender_type = 'customer')
                   as khach_cuoi,
               max(m.sent_at) filter (where m.sender_type = 'agent')
                   as shop_cuoi,
               max(m.sent_at) filter (where m.sender_type = 'agent'
                                        and m.sender_user_id is not null)
                   as nguoi_cuoi
          from crm.messages m
          join crm.conversations c2 on c2.id = m.conversation_id
         where c2.customer_id = l.customer_id
    ) ht on true
    left join lateral (
        select cv.external_conversation_id, cv.page_id
          from crm.conversations cv where cv.customer_id = l.customer_id
         order by cv.last_message_at desc nulls last limit 1
    ) cv on true
    left join crm.pages p on p.id = cv.page_id
"""

# Dấu "đã xem / chưa đọc" nằm ở kho hội thoại của worker nền
# (`watcher.hoi_thoai`, xem inbox_store) chứ không có trong schema `crm`.
# Bảng đó TẠO LƯỜI — lần đầu inbox_store chạy mới có. Nối thẳng vào là DB nào
# chưa từng bật watcher sẽ hỏng SẠCH bảng việc, nên phải hỏi trước.
_NOI_KHO_HT = """
    left join watcher.hoi_thoai wh
           on wh.page_id = p.external_page_id
          and wh.conv_id = cv.external_conversation_id
"""
_CHON_KHO_HT = ", wh.seen, wh.unread_count"


def _co_kho_hoi_thoai() -> bool:
    """Kho hội thoại của watcher đã tồn tại chưa? Hỏi MỘT lần rồi nhớ.

    `to_regclass` trả NULL thay vì nổ lỗi khi bảng chưa có — đúng thứ cần ở đây.
    """
    global _KHO_HT
    if _KHO_HT is None:
        pool = get_pg_pool()
        with pool.connection() as conn:
            _KHO_HT = bool(conn.execute(
                "select to_regclass('watcher.hoi_thoai') is not null as co"
            ).fetchone()["co"])
    return _KHO_HT


_KHO_HT: bool | None = None


def bang_viec(*, owner_id: int | None = None, q: str = "",
              chi_inbox: bool = False, limit: int = 500,
              staff_id: int | None = None, chua_gan: bool = False,
              page_id: int | None = None, tao_tu: str = "", tao_den: str = "",
              hoat_dong_ngay: int | None = None) -> list[dict]:
    """Lead ĐANG MỞ của Sale — service tự xếp vào cột.

    `chi_inbox` (Đ2) — bỏ lead mà khách CHỈ có hội thoại bình luận. Khách vừa
    bình luận vừa nhắn tin thì VẪN còn việc: điều kiện là "không có hội thoại
    inbox nào", không phải "có hội thoại bình luận". Khách chưa có hội thoại nào
    (nhập tay, đổ từ POS) cũng giữ nguyên — họ không phải lead bình luận.

    Bộ lọc màn (bước 2, port từ mẫu):
      `owner_id`       — bó về "khách của tôi" (do route quyết theo quyền).
      `staff_id`       — quản lý chọn XEM CỦA AI. Đi cùng `chua_gan`.
      `chua_gan`       — chỉ lead chưa có người phụ trách (mẫu: "— Chưa gán —").
      `page_id`        — fanpage của hội thoại MỚI NHẤT của khách.
      `tao_tu/tao_den` — ngày khách nhắn đến lần đầu (= ngày tạo lead), giờ VN.
      `hoat_dong_ngay` — chỉ lead còn động trong N ngày; None = cả kho.

    `hoat_dong_ngay` đo trên mốc MỚI NHẤT trong ba mốc (khách nhắn · shop nhắn ·
    ngày tạo). Đo mỗi tin khách là lead mình vừa nhắn xong hôm qua mà khách chưa
    đáp sẽ rơi khỏi bảng — đúng lúc cần bám nhất.
    """
    dk, ts = ["l.closed_at is null", "c.deleted_at is null"], {"lim": limit}
    if chi_inbox:
        dk.append(
            "(not exists (select 1 from crm.conversations cv"
            "              where cv.customer_id = c.id and cv.kind = 'comment')"
            " or exists (select 1 from crm.conversations cv2"
            "             where cv2.customer_id = c.id and cv2.kind = 'inbox'))")
    if owner_id:
        dk.append("l.owner_id = %(nv)s")
        ts["nv"] = owner_id
    if chua_gan:
        dk.append("l.owner_id is null")
    elif staff_id:
        dk.append("l.owner_id = %(nvloc)s")
        ts["nvloc"] = staff_id
    if page_id:
        dk.append("cv.page_id = %(page)s")
        ts["page"] = page_id
    if tao_tu:
        dk.append("(l.created_at at time zone 'Asia/Ho_Chi_Minh')::date"
                  " >= %(tao_tu)s")
        ts["tao_tu"] = tao_tu
    if tao_den:
        dk.append("(l.created_at at time zone 'Asia/Ho_Chi_Minh')::date"
                  " <= %(tao_den)s")
        ts["tao_den"] = tao_den
    if hoat_dong_ngay and hoat_dong_ngay > 0:
        dk.append("greatest(coalesce(ht.khach_cuoi, l.created_at),"
                  "         coalesce(ht.shop_cuoi, l.created_at),"
                  "         l.created_at)"
                  " >= now() - make_interval(days => %(hd)s)")
        ts["hd"] = hoat_dong_ngay
    if q.strip():
        dk.append("(c.full_name ilike %(q)s or c.primary_phone like %(q)s)")
        ts["q"] = f"%{q.strip()}%"
    co_ht = _co_kho_hoi_thoai()
    chon = _CHON_BANG + (_CHON_KHO_HT if co_ht else "")
    tu = _TU_BANG + (_NOI_KHO_HT if co_ht else "")
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {chon} {tu} where {' and '.join(dk)} "
            "order by l.next_action_at nulls last, l.id desc limit %(lim)s",
            ts,
        ).fetchall()


def giao_lead(lead_ids: list[int], owner_id: int) -> int:
    """Giao một lô lead cho MỘT người. Trả số dòng đổi thật.

    Chỉ đụng lead ĐANG MỞ: giao lại một lead đã đóng là làm sai lịch sử, mà
    người bấm cũng không thấy nó trên bảng để mà cố ý.
    """
    if not lead_ids:
        return 0
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            "update crm.leads set owner_id = %s, updated_at = now() "
            "where id = any(%s) and closed_at is null",
            (owner_id, list(lead_ids)),
        )
        return cur.rowcount or 0


def lead_de_xuat(lead_ids: list[int]) -> list[dict]:
    """Dòng dữ liệu cho file xuất. Cố ý KHÔNG dùng lại `_CHON_BANG`: bảng việc
    kéo theo cả mốc tin nhắn và đếm phụ, xuất ra thì thừa mà chậm."""
    if not lead_ids:
        return []
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select l.id, c.full_name, c.primary_phone, c.card_rank,
                   c.total_spent, c.source, u.name as owner_name,
                   l.sale_step, l.next_action_at, l.created_at
              from crm.leads l
              join crm.customers c on c.id = l.customer_id
              left join crm.users u on u.id = l.owner_id
             where l.id = any(%s)
             order by l.id
            """,
            (list(lead_ids),),
        ).fetchall()


def nhan_vien_co_lead() -> list[dict]:
    """Người đang ôm lead Sale ĐANG MỞ — nguồn cho ô lọc "nhân viên".

    Cố ý KHÔNG lấy cả bảng `users`: danh sách đó gồm cả kế toán, admin, người đã
    nghỉ — chọn xong bảng trắng mà không hiểu vì sao. Ở đây tên nào hiện ra cũng
    chắc chắn bấm vào là có thẻ."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select u.id, u.name, count(*) as so_lead
              from crm.leads l
              join crm.users u on u.id = l.owner_id
              join crm.customers c on c.id = l.customer_id
             where l.closed_at is null and c.deleted_at is null
             group by u.id, u.name
             order by u.name
            """
        ).fetchall()


def fanpage_co_lead() -> list[dict]:
    """Fanpage có lead Sale đang mở — nguồn cho ô lọc "fanpage"."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select p.id, p.name, count(*) as so_lead
              from crm.leads l
              join crm.customers c on c.id = l.customer_id
              join lateral (
                  select cv.page_id from crm.conversations cv
                   where cv.customer_id = l.customer_id
                   order by cv.last_message_at desc nulls last limit 1
              ) cv on true
              join crm.pages p on p.id = cv.page_id
             where l.closed_at is null and c.deleted_at is null
             group by p.id, p.name
             order by p.name
            """
        ).fetchall()


def dem_theo_loai_hoi_thoai() -> dict[str, int]:
    """Đ2 — đếm KHÁCH theo loại hội thoại họ có, để màn Cài đặt nói được công
    tắc «chỉ nhận lead inbox» đang chạm tới bao nhiêu người thật.

    Khách có cả hai loại tính vào "inbox" (họ vẫn còn việc), nên ba con số này
    cộng lại đúng bằng số khách có hội thoại — không chồng nhau.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            select case when bool_or(cv.kind = 'inbox') then 'inbox'
                        when bool_or(cv.kind = 'comment') then 'comment'
                        else 'khac' end as loai,
                   count(*) as n
              from crm.conversations cv
             where cv.customer_id is not null
             group by cv.customer_id
            """
        ).fetchall()
    ra: dict[str, int] = {}
    for r in rows:
        ra[r["loai"]] = ra.get(r["loai"], 0) + 1
    return ra


def get_lead_bang(lead_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON_BANG} {_TU_BANG} where l.id = %s", (lead_id,)
        ).fetchone()


def lead_can_do(*, gioi_han: int = 300) -> list[dict]:
    """Lead cần chạy lại bộ dò con trỏ: đang mở và CÓ TIN MỚI sau lần dò cuối."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select l.id, l.customer_id, l.sale_step, l.sale_step_at
              from crm.leads l
             where l.closed_at is null
               and exists (
                   select 1 from crm.messages m
                     join crm.conversations cv on cv.id = m.conversation_id
                    where cv.customer_id = l.customer_id
                      and m.sent_at > coalesce(l.sale_step_at,
                                               to_timestamp(0)))
             order by l.id limit %s
            """,
            (gioi_han,),
        ).fetchall()


def dong_lead(lead_id: int, ly_do: str | None = None) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.leads set closed_at = now() where id = %s returning *",
            (lead_id,),
        ).fetchone()
