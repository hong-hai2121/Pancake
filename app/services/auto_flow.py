"""LUỒNG TỰ ĐỘNG — Đợt 3, mới dựng KHUNG (mẫu Kallet `luong-tu-dong.php` +
`includes/auto_flow.php`).

🔴 ĐỌC KỸ ĐOẠN NÀY TRƯỚC KHI SỬA FILE

    File này CỐ Ý KHÔNG CÓ MỘT LỜI GỌI GỬI TIN NÀO.

Nó chỉ làm ba việc: đọc luật admin khai → chọn ra khách trúng luật → nói VÌ SAO
trúng. Hết. Không import `pancake.client`, không import Botcake, không đụng vào
hàng đợi gửi. Muốn bắn tin thật thì phải viết thêm mã mới — đó là một quyết
định có người ký, không phải hệ quả của việc ai đó gạt một công tắc.

Ba lớp chặn, xếp từ ngoài vào:

  0. CẤU TRÚC — không có mã gửi ở đây (lớp mạnh nhất: không thể bật cái không
     tồn tại). `scripts/thu_dot3.py` chứng minh lại điều này mỗi lần chạy test,
     bằng cách vá mọi hàm gửi thành "gọi là nổ" rồi chạy cả engine.
  1. CỬA GỬI — `cong_tac_gui_tin.xin_phep_gui("auto_flow")` từ chối vô điều
     kiện khi khoá cứng riêng còn đóng.
  2. KHOÁ CỨNG RIÊNG — `AUTO_FLOW_HARD_LOCK` trong `.env`, mặc định `true`,
     TÁCH khỏi `OUTBOUND_HARD_LOCK`. Mở đường gửi tay không mở kèm cái này.

Vì sao vẫn đáng làm khung trước: luật tự động sai thì sai với hàng chục nghìn
khách trong một đêm, và không ai kịp nhận ra. Khai luật rồi CHẠY KHÔ trên dữ
liệu thật, xem đúng những ai sẽ trúng và vì sao — đó là cách duy nhất kiểm
chứng một luật trước khi nó có quyền bắn tin.

## Ba kiểu kích hoạt

    su_kien     POS/Pancake báo một chuyện vừa xảy ra (khách nhận hàng, chốt
                đơn, nhắn lần đầu…)
    lech_ngay   N ngày kể từ một MỐC NEO (nhận hàng cuối, tin cuối của khách…)
    truong_doi  một trường của khách đổi sang giá trị nào đó (hạng thẻ lên Gold)

## Điều kiện lọc

Catalog `DIEU_KIEN` bên dưới CHỈ khai những trường CÓ THẬT trong `crm.customers`
/ `crm.leads`. Mẫu có vài điều kiện dựa trên cột mà bên ta không có (`ad_at`,
`ngung_cham_soc`…) — bỏ hẳn chứ không khai rồi để trả về rỗng: một điều kiện
lúc nào cũng không khớp là cái bẫy im lặng, admin tưởng luật chặt mà thật ra
luật chẳng lọc gì.
"""

from app.core import runtime_config
from app.core.errors import ApiError
from app.core.ngay import hom_nay

# ------------------------------------------------------------------ catalog
# (mã, nhãn, nguồn dữ liệu) — nguồn ghi ra để admin biết ai báo tin này.
SU_KIEN: dict[str, tuple[str, str]] = {
    "nhan_hang": ("Khách nhận hàng thành công", "POS"),
    "chot_don": ("Khách chốt đơn — lên đơn POS", "POS"),
    "don_huy": ("Đơn bị huỷ", "POS"),
    "nhan_dau": ("Khách nhắn tin lần đầu", "Pancake"),
    "voucher_tang": ("Vừa tặng voucher cho khách", "CRM"),
    "voucher_het_han": ("Voucher hết hạn mà khách không dùng", "CRM"),
}

# Mốc neo cho kiểu `lech_ngay`. Giá trị thứ 2 là biểu thức SQL trả về NGÀY.
MOC_NEO: dict[str, tuple[str, str, str]] = {
    "nhan_cuoi": ("Lần nhận hàng cuối", "c.last_delivered_at::date", "POS"),
    "vao_crm": ("Ngày khách vào CRM", "c.created_at::date", "CRM"),
    "tin_khach_cuoi": (
        "Tin nhắn CUỐI của khách",
        "(select max(m.sent_at)::date from crm.messages m "
        " join crm.conversations cv on cv.id = m.conversation_id "
        " where cv.customer_id = c.id and m.sender_type = 'customer')",
        "Pancake"),
    "cham_cuoi": (
        "Lần nhân viên chăm cuối",
        "(select max(i.created_at)::date from crm.care_interactions i "
        " where i.customer_id = c.id)", "CRM"),
}

# Điều kiện lọc. `kieu`: num | bool | list. `sql` là biểu thức so được.
DIEU_KIEN: dict[str, dict] = {
    "chi_tieu": {"ten": "Tổng chi tiêu", "kieu": "num", "dv": "đ",
                 "sql": "coalesce(c.total_spent, 0)"},
    "im_lang_ngay": {
        "ten": "Số ngày im lặng (từ tin cuối của khách)", "kieu": "num",
        "dv": "ngày",
        "sql": "coalesce(current_date - (select max(m.sent_at)::date "
               "from crm.messages m join crm.conversations cv "
               "on cv.id = m.conversation_id where cv.customer_id = c.id "
               "and m.sender_type = 'customer'), 99999)"},
    "ngay_tu_nhan_hang": {
        "ten": "Số ngày từ lần nhận hàng cuối", "kieu": "num", "dv": "ngày",
        "sql": "coalesce(current_date - c.last_delivered_at::date, 99999)"},
    "da_mua": {"ten": "Đã từng mua hàng", "kieu": "bool",
               "sql": "(c.last_delivered_at is not null)"},
    "co_sdt": {"ten": "Có số điện thoại", "kieu": "bool",
               "sql": "(coalesce(c.primary_phone, '') <> '')"},
    "xin_ngung": {"ten": "Đã xin NGỪNG nhận tin", "kieu": "bool",
                  "sql": "coalesce(c.do_not_contact, false)"},
    "co_canh_bao_yte": {"ten": "Có cờ cảnh báo y tế", "kieu": "bool",
                        "sql": "(coalesce(c.safety_flag, '') <> '')"},
    "hang_the": {"ten": "Hạng thẻ", "kieu": "list", "nguon": "hang",
                 "sql": "coalesce(c.card_rank, '')"},
    "tinh": {"ten": "Tỉnh/thành", "kieu": "list", "nguon": "tinh",
             "sql": "coalesce(c.province, '')"},
    "phu_trach": {"ten": "Người phụ trách", "kieu": "list", "nguon": "nhan_vien",
                  "sql": "coalesce(l.owner_id::text, '')"},
}

PHEP = {
    "num": [(">=", "≥"), ("<=", "≤"), ("=", "="), (">", ">"), ("<", "<")],
    "bool": [("=", "là")],
    "list": [("=", "là"), ("<>", "không phải")],
}

# Trường theo dõi cho kiểu `truong_doi`.
TRUONG_DOI: dict[str, tuple[str, str]] = {
    "card_rank": ("Hạng thẻ", "hang"),
    "cskh_column": ("Cột bảng việc CSKH", ""),
    "status": ("Tình trạng khách", ""),
}


def kieu_flow() -> dict[str, str]:
    return {
        "su_kien": "Khi một SỰ KIỆN xảy ra",
        "lech_ngay": "Sau N NGÀY kể từ một mốc",
        "truong_doi": "Khi một TRƯỜNG của khách đổi",
    }


# ------------------------------------------------------------------ dựng SQL
def _mot_dieu_kien(dk: dict, i: int) -> tuple[str, dict]:
    """Một điều kiện → (mảnh SQL, tham số). Điều kiện lạ thì NÉM lỗi chứ không
    bỏ qua: bỏ qua im lặng làm luật lỏng hơn admin tưởng."""
    ma = str(dk.get("ma") or "")
    cat = DIEU_KIEN.get(ma)
    if not cat:
        raise ApiError("VALIDATION_ERROR", f"Điều kiện lạ: {ma!r}")
    phep = str(dk.get("phep") or "=")
    if phep not in {p for p, _ in PHEP[cat["kieu"]]}:
        raise ApiError("VALIDATION_ERROR",
                       f"Phép so «{phep}» không dùng được cho «{cat['ten']}»")
    khoa = f"dk{i}"
    gt = dk.get("gia_tri")
    if cat["kieu"] == "num":
        try:
            gt = float(gt)
        except (TypeError, ValueError):
            raise ApiError("VALIDATION_ERROR",
                           f"«{cat['ten']}» cần một con số.") from None
        return f"{cat['sql']} {phep} %({khoa})s::numeric", {khoa: gt}
    if cat["kieu"] == "bool":
        return f"{cat['sql']} = %({khoa})s::boolean", {khoa: str(gt) in
                                                       ("1", "true", "True")}
    return f"{cat['sql']} {phep} %({khoa})s::text", {khoa: str(gt or "")}


def dung_loc(flow: dict) -> tuple[str, dict]:
    """Luật → (mệnh đề WHERE, tham số). KHÔNG chạy gì, chỉ dựng chuỗi — tách ra
    để màn hình soi được câu lọc mà không phải chạm DB."""
    manh: list[str] = []
    ts: dict = {}
    kind = flow.get("kind") or "lech_ngay"

    if kind == "lech_ngay":
        ma = str(flow.get("moc_neo") or "")
        neo = MOC_NEO.get(ma)
        if not neo:
            raise ApiError("VALIDATION_ERROR",
                           f"Mốc neo lạ: {ma!r} — chọn một trong "
                           f"{', '.join(MOC_NEO)}.")
        so = int(flow.get("so_ngay") or 0)
        lech = int(flow.get("lech") or 0)
        manh.append(f"({neo[1]}) = %(moc_ngay)s::date")
        ts["moc_ngay"] = hom_nay().fromordinal(
            hom_nay().toordinal() - so + lech)
    elif kind == "truong_doi":
        tr = str(flow.get("truong") or "")
        if tr not in TRUONG_DOI:
            raise ApiError("VALIDATION_ERROR", f"Trường lạ: {tr!r}")
        manh.append(f"coalesce(c.{tr}::text, '') = %(tr_gt)s")
        ts["tr_gt"] = str(flow.get("truong_gia_tri") or "")
    else:                                    # su_kien
        sk = str(flow.get("su_kien") or "")
        if sk not in SU_KIEN:
            raise ApiError("VALIDATION_ERROR", f"Sự kiện lạ: {sk!r}")
        # ⚠️ KIỂU SỰ KIỆN CHƯA CHẠY THẬT — chưa có hàng đợi sự kiện, nên ở đây
        # chỉ lọc theo ĐIỀU KIỆN chứ không biết sự kiện có vừa xảy ra hay không.
        # Chạy thử vẫn dùng được (xem điều kiện lọc trúng ai), nhưng SINH VIỆC
        # thì bị chặn ở `sinh_viec()`: luật ghi "khi khách nhận hàng" mà thực tế
        # bắn cho mọi khách thoả điều kiện, MỖI NGÀY, là sai hẳn ý người khai.
        manh.append("true")

    dk_ds = flow.get("dieu_kien") or []
    con: list[str] = []
    for i, dk in enumerate(dk_ds):
        sql, tham = _mot_dieu_kien(dk, i)
        con.append(sql)
        ts.update(tham)
    if con:
        noi = " and " if (flow.get("khop") or "all") == "all" else " or "
        manh.append("(" + noi.join(con) + ")")

    # LUÔN loại khách đã xin ngừng nhận tin và khách đã xoá/gộp — kể cả admin
    # không khai. Đây không phải bộ lọc tuỳ chọn: gửi cho người đã bảo "đừng
    # nhắn nữa" là chuyện không được phép xảy ra vì admin quên tick một ô.
    manh.append("c.deleted_at is null and c.status <> 'merged' "
                "and coalesce(c.do_not_contact, false) = false")
    return " and ".join(manh), ts


def _ly_do(flow: dict, kh: dict) -> str:
    """Câu giải thích vì sao khách này trúng — để soi luật bằng mắt."""
    kind = flow.get("kind")
    if kind == "lech_ngay":
        ten = MOC_NEO[flow["moc_neo"]][0]
        return (f'{ten} rơi đúng {flow.get("so_ngay") or 0} ngày trước '
                f"(lệch {flow.get('lech') or 0})")
    if kind == "truong_doi":
        return (f'{TRUONG_DOI[flow["truong"]][0]} đang là '
                f'«{flow.get("truong_gia_tri")}»')
    return f'thoả điều kiện của luật «{SU_KIEN[flow["su_kien"]][0]}»'


# --------------------------------------------------------------- CHẠY KHÔ
def chay_kho(flow: dict, *, mau: int = 30, boi: int | None = None,
             ghi: bool = True) -> dict:
    """Chạy KHÔ một luồng: luật này hôm nay trúng ai, vì sao.

    KHÔNG gửi gì. KHÔNG đánh dấu gì lên khách. Chạy lại bao nhiêu lần cũng ra
    kết quả như nhau — đó chính là điều làm nó dùng được để kiểm chứng luật.

    `mau` — số khách lấy ra làm ví dụ. Đếm thì đếm hết, nhưng lưu cả tệp vào
    nhật ký là vô ích và phình DB.
    """
    from app.db.repositories import auto_flow_repo
    from app.db.client import get_pg_pool

    dk, ts = dung_loc(flow)
    ts["mau"] = max(1, min(int(mau), 200))
    pool = get_pg_pool()
    with pool.connection() as conn:
        tong = conn.execute(
            f"""
            select count(*) as n from crm.customers c
              left join crm.leads l on l.customer_id = c.id
                                   and l.closed_at is null
             where {dk}
            """, ts).fetchone()["n"]
        vi_du = conn.execute(
            f"""
            select c.id, c.full_name, c.primary_phone, c.card_rank,
                   c.last_delivered_at, c.total_spent
              from crm.customers c
              left join crm.leads l on l.customer_id = c.id
                                   and l.closed_at is null
             where {dk}
             order by c.id limit %(mau)s
            """, ts).fetchall()
        # Đếm riêng số khách BỊ LOẠI vì đã xin ngừng nhận tin — con số này là
        # thứ admin cần thấy nhất khi soi một luật gửi hàng loạt.
        bo_qua = conn.execute(
            "select count(*) as n from crm.customers c "
            "where c.deleted_at is null and c.status <> 'merged' "
            "and coalesce(c.do_not_contact, false) = true"
        ).fetchone()["n"]

    ly_do = _ly_do(flow, {})
    chi_tiet = [{"id": r["id"], "ten": r["full_name"],
                 "sdt": r["primary_phone"], "hang": r["card_rank"],
                 "ly_do": ly_do} for r in vi_du]
    if ghi and flow.get("id"):
        auto_flow_repo.ghi_lan_chay(int(flow["id"]), so_trung=int(tong),
                                    so_bo_qua=int(bo_qua), chi_tiet=chi_tiet,
                                    boi=boi)
    return {
        "so_trung": int(tong), "so_bo_qua": int(bo_qua),
        "vi_du": chi_tiet, "ly_do": ly_do,
        "cau_loc": dk,
        # Nói thẳng ra ở MỌI lượt chạy, không để người dùng phải suy: lượt này
        # không gửi gì cả.
        "da_gui": 0,
        "ghi_chu_an_toan": khong_gui_duoc(),
    }


# ------------------------------------------------------------- SINH VIỆC
# Đây là đường TỰ ĐỘNG DUY NHẤT đang mở, và cố ý là đường an toàn: máy quét
# theo luật rồi đặt một VIỆC vào bảng việc của nhân viên. Người vẫn là người
# đọc, người vẫn là người bấm gửi. Toàn bộ giá trị của tự động hoá (không ai
# phải nhớ mốc, không ai bị bỏ sót) mà không có rủi ro của nó (tin sai bay tới
# hàng nghìn khách trước khi kịp nhận ra).
LOAI_VIEC = "auto_flow"


def sinh_viec_bat() -> bool:
    """Công tắc worker sinh việc. Mặc định TẮT — kéo mã về mà bảng việc của cả
    phòng tự nhiên đầy việc máy đẻ ra là mất lòng tin ngay ngày đầu."""
    return bool(runtime_config.bat("auto_flow_task_enabled"))


def sinh_viec(flow: dict, *, gioi_han: int = 200,
              boi: int | None = None) -> dict:
    """Chạy luật rồi ĐẶT VIỆC cho nhân viên phụ trách. KHÔNG gửi tin.

    Ba lý do bỏ qua một khách, đếm riêng từng loại để màn hình nói được vì sao
    "trúng 500 mà chỉ sinh 12 việc" — con số không giải thích được thì không ai
    dám bật công tắc:

      * chưa có người phụ trách  → đặt việc cho ai bây giờ? Đặt việc treo lơ
        lửng là nó nằm đó mãi không ai thấy.
      * việc cũ của luồng còn mở → nhắc lại khi việc trước chưa làm xong thì
        nhân viên thấy ba dòng y hệt và ngừng tin cả bảng việc.
      * hôm nay đã sinh rồi      → worker chạy nhiều lượt một ngày.
    """
    from app.db.client import get_pg_pool
    from app.db.repositories import auto_flow_repo, task_repo

    # Kiểu SỰ KIỆN chưa có hàng đợi sự kiện (xem `dung_loc`), nên nó KHÔNG biết
    # sự kiện có vừa xảy ra không — chỉ biết ai thoả điều kiện. Cho nó đặt việc
    # là mỗi ngày một loạt việc sai cho những khách chẳng có gì mới xảy ra.
    # Chặn ở đây chứ không chỉ cảnh báo trên màn: hàm này còn được worker gọi.
    if (flow.get("kind") or "") == "su_kien":
        raise ApiError(
            "CONFLICT",
            "Luồng kiểu SỰ KIỆN chưa đặt việc được: hàng đợi sự kiện chưa dựng "
            "nên máy không biết sự kiện có vừa xảy ra hay không, chỉ biết ai "
            "thoả điều kiện — đặt việc là sai hẳn ý luật. Dùng kiểu «sau N "
            "ngày» hoặc «trường đổi», hoặc Chạy thử để xem điều kiện trúng ai.")
    fid = int(flow["id"])
    dk, ts = dung_loc(flow)
    ts["lim"] = max(1, min(int(gioi_han), 1000))
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"""
            select c.id, c.full_name,
                   -- Người phụ trách: bảng phân công là nguồn CHUẨN, còn
                   -- leads.owner_id là nguồn ĐANG CÓ DỮ LIỆU. Lấy cả hai, ưu
                   -- tiên bảng chuẩn — khỏi phải sửa lại khi phân công đầy lên.
                   coalesce(a.user_id, l.owner_id) as nguoi
              from crm.customers c
              left join crm.leads l on l.customer_id = c.id
                                   and l.closed_at is null
              left join crm.customer_assignments a on a.customer_id = c.id
                                                  and a.end_at is null
             where {dk}
             order by c.id limit %(lim)s
            """, ts).fetchall()

    da_hom_nay = auto_flow_repo.da_sinh_viec_hom_nay(fid)
    con_mo = auto_flow_repo.con_viec_mo(fid)
    bo_qua = {"chua_co_nguoi": 0, "viec_cu_con_mo": 0, "da_sinh_hom_nay": 0}
    het_ngay = bay_gio_cuoi_ngay()
    ten = (flow.get("name") or "").strip() or f"Luồng #{fid}"
    da_sinh = 0

    for kh in rows:
        cid = int(kh["id"])
        if cid in da_hom_nay:
            bo_qua["da_sinh_hom_nay"] += 1
            continue
        if cid in con_mo:
            bo_qua["viec_cu_con_mo"] += 1
            continue
        if not kh["nguoi"]:
            bo_qua["chua_co_nguoi"] += 1
            continue
        viec = task_repo.create_task(
            title=ten, task_type=LOAI_VIEC, assigned_to=int(kh["nguoi"]),
            due_at=het_ngay, priority="normal", customer_id=cid,
            # related_* trả lời được câu "việc này ở đâu ra" ngay trên thẻ việc.
            related_type="auto_flows", related_id=fid, created_by=boi)
        auto_flow_repo.ghi_viec(fid, cid, int(viec["id"]))
        da_sinh += 1
    return {"xet": len(rows), "da_sinh": da_sinh, "bo_qua": bo_qua,
            "da_gui": 0, "ghi_chu_an_toan": khong_gui_duoc()}


def bay_gio_cuoi_ngay():
    """Hạn việc = CUỐI ngày hôm nay theo giờ VN. Đặt hạn "ngay bây giờ" thì
    việc vừa sinh đã quá hạn và worker leo thang bắn cảnh báo oan."""
    from datetime import datetime, time

    from app.core.ngay import MUI_GIO

    return datetime.combine(hom_nay(), time(23, 59), tzinfo=MUI_GIO)


def khong_gui_duoc() -> str:
    """Vì sao luồng tự động chưa gửi được gì. Rỗng = ĐÃ gửi được (chưa bao giờ
    xảy ra ở Đợt 3 — engine còn chưa có mã gửi)."""
    from app.services import cong_tac_gui_tin

    ly_do = cong_tac_gui_tin.vi_sao_khong_gui("auto_flow")
    if ly_do:
        return ly_do
    return ("Khoá cứng đã mở, NHƯNG engine luồng tự động vẫn chưa có mã gửi tin "
            "nào (Đợt 3 mới dựng khung). Không tin nào rời hệ thống.")


def gio_quet() -> int:
    """Giờ trong ngày worker sẽ quét — để sẵn cho ngày có worker thật."""
    return max(0, min(23, int(runtime_config.so("af_gio_quet", 9))))
