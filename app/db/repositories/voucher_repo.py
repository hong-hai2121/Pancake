"""Truy vấn crm.vouchers + card_ranks + card_rank_benefits (C1 — port từ mẫu
Kallet: voucher.php · hang-the.php).

Chỉ SQL. Luật nghiệp vụ (xếp hạng CHỈ NÂNG, giảm quyền lợi ngầm 180 ngày,
"còn voucher hiệu lực thì tắt mốc chăm chuẩn") nằm ở services/card_service.py
và services/voucher_service.py.
"""

from datetime import date

from app.core.ngay import hom_nay
from app.db.client import get_pg_pool

# ------------------------------------------------------------------ VOUCHER
_CHON = """
    v.*,
    c.full_name     as customer_name,
    c.primary_phone as customer_phone,
    c.card_rank     as customer_rank,
    u.name          as granted_by_name,
    (v.expires_on - %(hom_nay)s::date) as ngay_con_lai
"""
_TU = """
    from crm.vouchers v
    join crm.customers c on c.id = v.customer_id
    left join crm.users u on u.id = v.granted_by
"""


def _dieu_kien(
    *, status: str = "", kind: str = "", granted_by: int | None = None,
    tu_khoa: str = "", customer_id: int | None = None,
    owner_id: int | None = None,
) -> tuple[str, dict]:
    """Dựng WHERE dùng CHUNG cho bảng, 4 ô số và bộ chọn nhân viên — ba chỗ
    lệch điều kiện là số đếm không khớp bảng, lỗi rất khó thấy.

    `hom_nay` luôn có trong tham số vì `_CHON` tính "còn mấy ngày" theo NGÀY VN
    chứ không phải `current_date` của DB (DB chạy UTC — xem app/core/ngay.py)."""
    dk, ts = ["true"], {"hom_nay": hom_nay()}
    if status:
        dk.append("v.status = %(tt)s")
        ts["tt"] = status
    if kind in ("may", "nguoi"):
        dk.append("v.granted_by_kind = %(loai)s")
        ts["loai"] = kind
    if granted_by:
        dk.append("v.granted_by = %(nv)s")
        ts["nv"] = granted_by
    if customer_id:
        dk.append("v.customer_id = %(kh)s")
        ts["kh"] = customer_id
    if owner_id:
        # Phạm vi quyền: NV thường chỉ thấy voucher của khách MÌNH phụ trách.
        dk.append(
            "exists (select 1 from crm.customer_assignments a "
            " where a.customer_id = v.customer_id and a.user_id = %(pt)s "
            "   and a.end_at is null)"
        )
        ts["pt"] = owner_id
    if tu_khoa:
        dk.append("(v.code ilike %(kw)s or c.full_name ilike %(kw)s "
                  "or c.primary_phone like %(kw)s)")
        ts["kw"] = f"%{tu_khoa}%"
    return " and ".join(dk), ts


def danh_sach(
    *, status: str = "", kind: str = "", granted_by: int | None = None,
    tu_khoa: str = "", customer_id: int | None = None,
    owner_id: int | None = None, limit: int = 30, offset: int = 0,
) -> tuple[list[dict], int]:
    where, ts = _dieu_kien(
        status=status, kind=kind, granted_by=granted_by, tu_khoa=tu_khoa,
        customer_id=customer_id, owner_id=owner_id,
    )
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"select {_CHON} {_TU} where {where} "
            "order by v.expires_on asc, v.id desc limit %(l)s offset %(o)s",
            {**ts, "l": limit, "o": offset},
        ).fetchall()
        tong = conn.execute(
            f"select count(*) as n {_TU} where {where}", ts
        ).fetchone()["n"]
    return rows, tong


def o_so(*, owner_id: int | None = None) -> dict:
    """4 ô số đầu màn Voucher. CỐ Ý đếm theo PHẠM VI QUYỀN mà KHÔNG theo bộ lọc
    (giống mẫu): bấm ô là để LỌC, số trên ô phải đứng yên thì mới bấm được."""
    where, ts = _dieu_kien(owner_id=owner_id)
    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            f"""
            select count(*) filter (where v.status = 'con_han')     as con_han,
                   count(*) filter (where v.status = 'da_dung')     as da_dung,
                   count(*) filter (where v.status = 'chua_bao_ma') as chua_bao_ma,
                   coalesce(sum(v.amount), 0)                       as tien_tong,
                   coalesce(sum(v.amount) filter
                       (where v.granted_by_kind = 'may'), 0)        as tien_may
              {_TU} where {where}
            """,
            ts,
        ).fetchone()
    return dict(r)


def nguoi_tang(*, owner_id: int | None = None) -> list[dict]:
    """Danh sách nhân viên từng tặng voucher — đổ vào ô lọc."""
    where, ts = _dieu_kien(owner_id=owner_id)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select distinct v.granted_by as id, u.name {_TU} "
            f"where {where} and v.granted_by is not null order by u.name",
            ts,
        ).fetchall()


def get(voucher_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_CHON} {_TU} where v.id = %(id)s",
            {"id": voucher_id, "hom_nay": hom_nay()},
        ).fetchone()


def tao(
    *, customer_id: int, amount, expires_on: date, code: str = "",
    granted_by: int | None = None, granted_by_kind: str = "nguoi",
    note: str = "", granted_on: date | None = None,
    order_from_id: int | None = None,
) -> dict:
    """Mã trống = 'chua_bao_ma' (việc cần làm), có mã = 'con_han' ngay."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.vouchers
                   (customer_id, code, amount, granted_by_kind, granted_by,
                    order_from_id, granted_on, expires_on, status, note)
            values (%(kh)s, %(ma)s, %(tien)s, %(loai)s, %(nv)s, %(don)s,
                    %(ngay)s, %(han)s,
                    case when %(ma)s = '' then 'chua_bao_ma' else 'con_han' end,
                    %(ghi_chu)s)
            returning *
            """,
            # `granted_on` CỐ Ý tính ở Python: để DB điền current_date thì tặng
            # trước 07:00 giờ VN sẽ ghi lùi 1 ngày (DB chạy UTC).
            {"kh": customer_id, "ma": code, "tien": amount,
             "loai": granted_by_kind, "nv": granted_by, "don": order_from_id,
             "ngay": granted_on or hom_nay(), "han": expires_on,
             "ghi_chu": note},
        ).fetchone()


def cap_nhat(voucher_id: int, *, updated_by: int | None = None, **fields) -> dict | None:
    cho_phep = {"code", "amount", "expires_on", "status", "note",
                "order_used_id", "pos_discount"}
    fields = {k: v for k, v in fields.items() if k in cho_phep}
    if not fields:
        return get(voucher_id)
    dat = ", ".join(f"{k} = %({k})s" for k in fields)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"update crm.vouchers set {dat}, updated_by = %(nv)s "
            "where id = %(id)s returning *",
            {**fields, "id": voucher_id, "nv": updated_by},
        ).fetchone()


def het_han_hang_loat() -> int:
    """Voucher qua ngày mà chưa dùng → 'het_han_khong_dung'. Worker gọi hằng
    ngày; gọi lại nhiều lần không sao (điều kiện đã loại dòng đã đổi)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            "update crm.vouchers set status = 'het_han_khong_dung' "
            "where status in ('con_han','chua_bao_ma') and expires_on < %s",
            (hom_nay(),),
        )
        return cur.rowcount or 0


def con_hieu_luc(customer_id: int) -> dict | None:
    """Voucher còn hiệu lực gần hết hạn nhất của khách — C7: còn voucher thì
    TẮT mọi mốc chăm chuẩn, chỉ giữ mốc nhắc hạn voucher."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.vouchers where customer_id = %s "
            "and status in ('con_han','chua_bao_ma') and expires_on >= %s "
            "order by expires_on limit 1",
            (customer_id, hom_nay()),
        ).fetchone()


def sap_het_han(trong_ngay: int = 3, *, owner_id: int | None = None) -> list[dict]:
    """Voucher còn hạn nhưng sắp hết — cột 'Nhắc hạn voucher' của bảng CSKH."""
    where, ts = _dieu_kien(owner_id=owner_id)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select {_CHON} {_TU}
             where {where} and v.status in ('con_han','chua_bao_ma')
               and v.expires_on between %(hom_nay)s::date
                   and %(hom_nay)s::date + %(n)s
             order by v.expires_on limit 200
            """,
            {**ts, "n": trong_ngay},
        ).fetchall()


# --------------------------------------------------------------- HẠNG THẺ
def hang_the() -> list[dict]:
    """Bậc thang từ CAO xuống THẤP (màn Hạng thẻ bày theo chiều này)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.card_ranks order by sort_order desc"
        ).fetchall()


def hang_the_tang_dan() -> list[dict]:
    """Thấp → cao. Dùng để tra 'hạng thấp hơn 1 bậc' (luật giảm quyền lợi)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.card_ranks order by sort_order asc"
        ).fetchall()


def luu_hang(code: str, *, name: str, emoji: str = "", min_spent=None,
             max_spent=None, sort_order: int = 0) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.card_ranks (code, name, emoji, min_spent, max_spent,
                                        sort_order)
            values (%(ma)s, %(ten)s, %(emoji)s, %(min)s, %(max)s, %(tt)s)
            on conflict (code) do update set
                name = excluded.name, emoji = excluded.emoji,
                min_spent = excluded.min_spent, max_spent = excluded.max_spent,
                sort_order = excluded.sort_order
            returning *
            """,
            {"ma": code, "ten": name, "emoji": emoji, "min": min_spent,
             "max": max_spent, "tt": sort_order},
        ).fetchone()


def dat_nguong(code: str, min_spent) -> None:
    """Chỉ sửa ngưỡng (màn Cài đặt → Hạng thẻ). None = xoá ngưỡng, hạng đó
    ngừng nhận khách mới cho tới khi điền lại."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.card_ranks set min_spent = %s where code = %s",
            (min_spent, code),
        )


def quyen_loi() -> dict[str, list[dict]]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select * from crm.card_rank_benefits "
            "order by rank_code, sort_order, id"
        ).fetchall()
    gom: dict[str, list[dict]] = {}
    for r in rows:
        gom.setdefault(r["rank_code"], []).append(r)
    return gom


def them_quyen_loi(rank_code: str, benefit_key: str, benefit_value: str = "",
                   sort_order: int = 0) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.card_rank_benefits (rank_code, benefit_key, "
            "benefit_value, sort_order) values (%s, %s, %s, %s) returning *",
            (rank_code, benefit_key, benefit_value, sort_order),
        ).fetchone()


def xoa_quyen_loi(benefit_id: int) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("delete from crm.card_rank_benefits where id = %s",
                     (benefit_id,))


def dem_theo_hang() -> dict[str, int]:
    """Số khách mỗi hạng. Khách chưa xếp hạng gom vào khoá '' (card_rank NULL)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select coalesce(card_rank, '') as ma, count(*) as n "
            "from crm.customers where deleted_at is null and status <> 'merged' "
            "group by 1"
        ).fetchall()
    return {r["ma"]: r["n"] for r in rows}


def tong_khach() -> int:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select count(*) as n from crm.customers "
            "where deleted_at is null and status <> 'merged'"
        ).fetchone()["n"]


def dem_giam_quyen_loi(sau_ngay: int = 180) -> int:
    """Khách CÓ hạng nhưng đã `sau_ngay` ngày không nhận hàng — hạng hiển thị
    giữ nguyên, quyền lợi tụt 1 bậc. Luật NGẦM: KHÔNG báo cho khách."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select count(*) as n from crm.customers "
            "where card_rank is not null and deleted_at is null "
            "  and last_delivered_at is not null "
            "  and last_delivered_at < now() - make_interval(days => %s)",
            (sau_ngay,),
        ).fetchone()["n"]


def lam_moi_chi_tieu() -> int:
    """Tính lại total_spent + last_delivered_at từ orders (đơn đã giao TC).

    Đơn 0đ (đổi hàng/tặng) VẪN cập nhật last_delivered_at — mẫu quy định đơn
    tặng khởi động lại lịch chăm — nhưng cộng 0 vào tổng chi tiêu nên không
    đẩy hạng lên."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            """
            update crm.customers c set
                   total_spent = coalesce(k.tien, 0),
                   last_delivered_at = k.lan_cuoi
              from (select o.customer_id,
                           sum(o.total_amount) as tien,
                           max(o.delivered_at) as lan_cuoi
                      from crm.orders o where o.status = 'delivered'
                     group by o.customer_id) k
             where k.customer_id = c.id
               and (c.total_spent is distinct from coalesce(k.tien, 0)
                    or c.last_delivered_at is distinct from k.lan_cuoi)
            """
        )
        return cur.rowcount or 0


def lam_moi_chi_tieu_mot_khach(customer_id: int) -> dict | None:
    """Bản một-khách của `lam_moi_chi_tieu` — gọi ngay khi đơn giao xong, khỏi
    quét cả bảng chỉ vì một đơn."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            update crm.customers c set
                   total_spent = coalesce(k.tien, 0),
                   last_delivered_at = k.lan_cuoi
              from (select coalesce(sum(o.total_amount), 0) as tien,
                           max(o.delivered_at)              as lan_cuoi
                      from crm.orders o
                     where o.customer_id = %(kh)s and o.status = 'delivered') k
             where c.id = %(kh)s
            returning c.id, c.card_rank, c.total_spent
            """,
            {"kh": customer_id},
        ).fetchone()


def nang_hang_mot_khach(customer_id: int, bac: list[tuple[str, int, object]]) -> str | None:
    """Nâng hạng cho MỘT khách. Trả mã hạng mới nếu có đổi, None nếu giữ nguyên."""
    if not bac:
        return None
    nhanh_ma, nhanh_tt, ts = [], [], {"kh": customer_id}
    for i, (ma, thu_tu, nguong) in enumerate(bac):
        nhanh_ma.append(f"when c.total_spent >= %(n{i})s then %(m{i})s")
        nhanh_tt.append(f"when c.total_spent >= %(n{i})s then %(t{i})s")
        ts[f"n{i}"], ts[f"m{i}"], ts[f"t{i}"] = nguong, ma, thu_tu
    case_ma = "case " + " ".join(nhanh_ma) + " else c.card_rank end"
    case_tt = "case " + " ".join(nhanh_tt) + " else 0 end"
    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            f"""
            update crm.customers c set card_rank = ({case_ma})
             where c.id = %(kh)s
               and ({case_tt}) > coalesce(
                     (select r.sort_order from crm.card_ranks r
                       where r.code = c.card_rank), 0)
            returning c.card_rank
            """,
            ts,
        ).fetchone()
    return r["card_rank"] if r else None


def nang_hang(bac: list[tuple[str, int, object]]) -> int:
    """Xếp lại hạng theo `bac` = [(mã, sort_order, ngưỡng)] đã sắp GIẢM dần.

    CHỈ NÂNG: chỉ ghi khi hạng mới có sort_order LỚN HƠN hạng đang có. Khách
    tiêu ít đi (đơn hoàn) vẫn giữ hạng cũ — đúng luật mẫu "không ai bị tụt".
    """
    if not bac:
        return 0
    # CASE dựng bằng tham số, không nối chuỗi giá trị vào SQL.
    nhanh_ma, nhanh_tt, ts = [], [], {}
    for i, (ma, thu_tu, nguong) in enumerate(bac):
        nhanh_ma.append(f"when c.total_spent >= %(n{i})s then %(m{i})s")
        nhanh_tt.append(f"when c.total_spent >= %(n{i})s then %(t{i})s")
        ts[f"n{i}"], ts[f"m{i}"], ts[f"t{i}"] = nguong, ma, thu_tu
    case_ma = "case " + " ".join(nhanh_ma) + " else c.card_rank end"
    case_tt = "case " + " ".join(nhanh_tt) + " else 0 end"
    pool = get_pg_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            f"""
            update crm.customers c set card_rank = ({case_ma})
             where c.deleted_at is null and c.status <> 'merged'
               and ({case_tt}) > coalesce(
                     (select r.sort_order from crm.card_ranks r
                       where r.code = c.card_rank), 0)
            """,
            ts,
        )
        return cur.rowcount or 0
