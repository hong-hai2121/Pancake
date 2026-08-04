"""Truy vấn cho MÀN ĐƠN HÀNG (C7 — port `don-hang.php` của mẫu Kallet).

Tách khỏi `order_repo` (nghiệp vụ đơn B7) vì đây thuần là câu hỏi của một cái
màn: lọc · đếm thẻ chỉ số · phân trang · xuất file. Nghiệp vụ đơn (luật chuyển
trạng thái, phân loại đầu/mua lại) vẫn nằm nguyên ở `services/order_service`.

Quy ước chung tầng repo CRM: gọi thẳng get_pg_pool() (dict_row, autocommit),
viết tay tiền tố `crm.` trong MỌI câu lệnh, tham số hoá toàn bộ giá trị.

MỘT BỘ LỌC — BỐN CÂU: bảng · thẻ chỉ số · danh sách id (tích "chọn cả bộ lọc")
· xuất theo lô. Cả bốn đi qua `_loc()` nên không bao giờ lệch nhau; sửa điều
kiện thì sửa đúng một chỗ.
"""

from app.db.client import get_pg_pool

# Ngày ĐẶT đơn: đơn POS lấy mốc bên POS, đơn CRM lấy mốc tạo. Dùng ở cả lọc
# khoảng ngày lẫn sắp xếp — có index idx_orders_ngay_dat theo đúng biểu thức.
NGAY_DAT = "coalesce(o.pos_inserted_at, o.created_at)"

# Cột sắp xếp cho phép (chặn caller nhét SQL vào ORDER BY).
SAP_XEP = {
    "ngay": NGAY_DAT,
    "gia":  "o.total_amount",
    "giao": "o.delivered_at",
}

# Trạng thái coi là "đã hoàn" — trừ khỏi doanh thu lên đơn (mẫu: mã POS 5).
# `returning` (đang hoàn) VẪN tính tiền: hàng chưa về kho, chưa mất doanh thu.
DA_HOAN = ("returned",)


def _loc(f: dict) -> tuple[str, list]:
    """Dựng WHERE + tham số từ bộ lọc của màn. Trả ('true', []) nếu không lọc gì.

    `f` nhận: q · status · order_type · effort · ads · nv · nv_pos · page ·
    ky · tu · den · nguoi_xem (phạm vi: chỉ đơn của tôi).
    """
    dk, ts = ["true"], []
    if f.get("status"):
        dk.append("o.status = %s"); ts.append(f["status"])
    if f.get("order_type"):
        dk.append("o.order_type = %s"); ts.append(f["order_type"])
    if f.get("effort"):
        dk.append("o.effort_axis = %s"); ts.append(f["effort"])
    if f.get("ads") == "co":
        dk.append("o.ads_attributed")
    elif f.get("ads") == "khong":
        dk.append("not o.ads_attributed")
    if f.get("nv"):
        # Một đơn có thể do Sale chốt rồi CSKH chăm — lọc "nhân viên" phải bắt
        # cả hai vai, không thì người xem tưởng đơn của mình biến mất.
        dk.append("(o.sale_owner_id = %s or o.cskh_owner_id = %s)")
        ts += [f["nv"], f["nv"]]
    if f.get("nv_pos"):
        dk.append("o.pos_seller_name = %s"); ts.append(f["nv_pos"])
    if f.get("page"):
        dk.append("o.pos_page_id = %s"); ts.append(f["page"])
    if f.get("ky"):
        dk.append("o.payroll_period = %s"); ts.append(f["ky"])
    if f.get("tu"):
        dk.append(f"{NGAY_DAT} >= %s"); ts.append(f["tu"])
    if f.get("den"):
        # `den` là NGÀY BAO GỒM — route cộng sẵn 1 ngày nên ở đây so "<".
        dk.append(f"{NGAY_DAT} < %s"); ts.append(f["den"])
    if f.get("nguoi_xem"):
        dk.append("(o.sale_owner_id = %s or o.cskh_owner_id = %s)")
        ts += [f["nguoi_xem"], f["nguoi_xem"]]
    if f.get("q"):
        # pos_display_id so BẰNG (có index) vì người dùng chép nguyên mã đơn;
        # ba cột còn lại so gần đúng. Đừng đổi cột này sang ilike '%…%': bảng
        # 53k đơn quét toàn bộ mỗi lần gõ ô tìm.
        dk.append("(c.full_name ilike %s or c.primary_phone ilike %s "
                  "or o.external_order_id ilike %s or o.pos_display_id = %s "
                  "or o.pos_order_id::text = %s)")
        q = f["q"].strip()
        ts += [f"%{q}%", f"%{q}%", f"%{q}%", q, q]
    return " and ".join(dk), ts


# Join tối thiểu dùng chung cho MỌI câu (khách là bắt buộc — bảng nào cũng cần
# tên/SĐT, và bộ lọc `q` tìm trên đó).
_JOIN = "from crm.orders o join crm.customers c on c.id = o.customer_id"

# Bồi thêm cho câu ĐỌC DÒNG (không dùng ở count/sum cho nhẹ).
_JOIN_HIEN = """
  left join crm.users us on us.id = o.sale_owner_id
  left join crm.users uc on uc.id = o.cskh_owner_id
  left join crm.pages  p on p.external_page_id = o.pos_page_id
"""

_COT_DONG = f"""
    o.id, o.status, o.order_type, o.total_amount, o.delivered_at,
    o.created_at, o.customer_id, o.external_order_id,
    o.pos_display_id, o.pos_order_id, o.pos_shop_id, o.pos_status,
    o.pos_page_id, o.pos_conversation_id, o.pos_ad_id,
    o.cod_amount, o.prepaid_amount,
    o.effort_axis, o.ads_attributed, o.payroll_period,
    {NGAY_DAT}            as ngay_dat,
    c.full_name           as khach,
    c.primary_phone       as sdt,
    us.name               as sale_ten,
    uc.name               as cskh_ten,
    o.pos_seller_name     as nv_pos,
    p.name                as page_ten,
    p.external_page_id    as page_ngoai
"""


def bang(f: dict, *, sort: str = "ngay", dir_: str = "desc",
         limit: int = 30, offset: int = 0) -> tuple[list[dict], int]:
    """Một trang của bảng đơn + TỔNG số đơn khớp bộ lọc (để phân trang)."""
    where, ts = _loc(f)
    cot = SAP_XEP.get(sort, NGAY_DAT)
    huong = "asc" if dir_ == "asc" else "desc"
    pool = get_pg_pool()
    with pool.connection() as conn:
        total = conn.execute(
            f"select count(*) as n {_JOIN} where {where}", ts or None
        ).fetchone()["n"]
        rows = conn.execute(
            # o.id ở cuối ORDER BY: cột sắp chính trùng giá trị hàng loạt (đơn
            # 0đ, cùng ngày) — thứ tự không duy nhất thì lật trang là lọt/trùng.
            f"""
            select {_COT_DONG}
              {_JOIN} {_JOIN_HIEN}
             where {where}
             order by {cot} {huong} nulls last, o.id desc
             limit %s offset %s
            """,
            [*ts, limit, offset],
        ).fetchall()
    return rows, total


def chi_so(f: dict) -> dict:
    """Dải thẻ chỉ số + thanh tổng trên bảng — ĐẾM TRÊN CẢ BỘ LỌC, không phải
    trên trang đang xem (mẫu làm vậy: đổi bộ lọc là mọi con số đổi theo).

      * `len_don`   — doanh thu LÊN ĐƠN: trừ đơn đã hoàn, giữ đơn đang hoàn
                      (hàng chưa về kho thì chưa mất tiền).
      * `thanh_cong`— doanh thu đơn đã giao/đã thu.
      * 3 tỉ lệ (thành công · hoàn · đổi) tính ở tầng view từ các số đếm này.
    """
    where, ts = _loc(f)
    hoan = ", ".join(f"'{s}'" for s in DA_HOAN)
    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            f"""
            select count(*)                                            as so_don,
                   coalesce(sum(o.total_amount) filter (
                       where o.status not in ({hoan})), 0)             as len_don,
                   coalesce(sum(o.total_amount) filter (
                       where o.status in ('delivered','collected')), 0) as thanh_cong,
                   count(*) filter (
                       where o.status in ('delivered','collected'))    as n_xong,
                   count(*) filter (
                       where o.status in ('returning','returned'))     as n_hoan,
                   count(*) filter (where o.order_type = 'exchange')   as n_doi
              {_JOIN} where {where}
            """,
            ts or None,
        ).fetchone()
    return dict(r)


def ids(f: dict, *, tran: int = 100_000) -> list[int]:
    """Toàn bộ id đơn khớp bộ lọc — cho nút "Chọn cả N đơn khớp bộ lọc".

    `tran` chặn trường hợp bấm khi chưa lọc gì: 53k id nhét vào form POST là
    request vài trăm KB. Vượt trần thì route chuyển sang đường "xuất cả bộ lọc"
    (không cần liệt kê id).
    """
    where, ts = _loc(f)
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"select o.id {_JOIN} where {where} order by o.id limit %s",
            [*ts, tran],
        ).fetchall()
    return [r["id"] for r in rows]


def xuat_theo_lo(f: dict, *, sort: str = "ngay", dir_: str = "desc",
                 lo: int = 2000):
    """Sinh từng LÔ dòng để xuất CSV — không nạp cả bộ lọc vào RAM một lúc.

    🔑 `o.id` PHẢI có trong ORDER BY: cột sắp chính trùng giá trị hàng loạt
    (đơn 0đ, cùng ngày đặt) nên thứ tự không duy nhất; mỗi lô Postgres được
    quyền xếp một kiểu khác nhau → lô này trùng hàng, lô kia lọt hàng. Mẫu đã
    dính đúng lỗi đó, xem chú thích trong `don-hang.php`.
    """
    where, ts = _loc(f)
    cot = SAP_XEP.get(sort, NGAY_DAT)
    huong = "asc" if dir_ == "asc" else "desc"
    pool = get_pg_pool()
    with pool.connection() as conn:
        vi_tri = 0
        while True:
            rows = conn.execute(
                f"""
                select {_COT_DONG}
                  {_JOIN} {_JOIN_HIEN}
                 where {where}
                 order by {cot} {huong} nulls last, o.id desc
                 limit %s offset %s
                """,
                [*ts, lo, vi_tri],
            ).fetchall()
            if not rows:
                return
            yield rows
            if len(rows) < lo:
                return
            vi_tri += lo


def theo_ids(danh_sach: list[int], *, nguoi_xem: int | None = None) -> list[dict]:
    """Đọc đơn theo danh sách id — cho lối xuất "những đơn đã tích".

    🔒 `nguoi_xem` KHÔNG được bỏ: id đơn là số tăng dần nên đoán được. Người
    chỉ có quyền xuất mà không được xem toàn bộ, nếu tự POST ids[] tuỳ ý, sẽ
    dump được tên/SĐT/doanh số đơn của nhân viên khác (mẫu đã vá đúng lỗ này).
    """
    if not danh_sach:
        return []
    dk, ts = "o.id = any(%s)", [list(danh_sach)]
    if nguoi_xem:
        dk += " and (o.sale_owner_id = %s or o.cskh_owner_id = %s)"
        ts += [nguoi_xem, nguoi_xem]
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select {_COT_DONG} {_JOIN} {_JOIN_HIEN} where {dk} "
            f"order by o.id desc", ts,
        ).fetchall()


# ------------------------------------------------------------------ ô lọc
def nhan_vien_pos(gioi_han: int = 300) -> list[str]:
    """Tên nhân viên POS đang có trên đơn — cho ô lọc "Nhân viên POS".

    Đọc thẳng từ đơn (index idx_orders_pos_seller) chứ không từ bảng nhân viên
    tích hợp: ô lọc chỉ nên liệt kê người THẬT SỰ có đơn, khỏi một danh sách
    trăm người mà chọn ai cũng ra 0 dòng.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select distinct pos_seller_name from crm.orders "
            "where pos_seller_name is not null order by pos_seller_name limit %s",
            (gioi_han,),
        ).fetchall()
    return [r["pos_seller_name"] for r in rows]


def fanpages() -> list[dict]:
    """Fanpage có đơn — (mã page bên ngoài, tên hiển thị) cho ô lọc.

    Nhóm theo pos_page_id vì đơn giữ mã page dạng chuỗi của POS; page chưa có
    trong crm.pages thì lấy chính mã đó làm nhãn (thà hiện mã còn hơn mất dòng).
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select o.pos_page_id                        as ma,
                   coalesce(max(p.name), o.pos_page_id) as ten,
                   count(*)                             as so_don
              from crm.orders o
              left join crm.pages p on p.external_page_id = o.pos_page_id
             where o.pos_page_id is not null
             group by o.pos_page_id
             order by count(*) desc
            """
        ).fetchall()


def ky_luong() -> list[str]:
    """Các kỳ lương đã ghi trên đơn (YYYY-MM), mới nhất trước."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select distinct payroll_period from crm.orders "
            "where payroll_period is not null order by payroll_period desc"
        ).fetchall()
    return [r["payroll_period"] for r in rows]
