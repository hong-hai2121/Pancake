"""Nghiệm thu C6 — QUY TRÌNH CSKH BA GIAI ĐOẠN (port từ mẫu Kallet).

Kiểm SÁU luật mà mẫu ghi rõ "đừng sửa cho gọn" — đây là những chỗ nhìn qua
tưởng sai/thừa nên rất dễ bị "sửa lỗi" rồi hỏng nghiệp vụ:

  1. Đơn giao thành công: TIÊU mã cũ TRƯỚC, rồi mới xét tặng mã mới.
  2. Xét mã sống tại NGÀY ĐẶT ĐƠN, không phải ngày giao.
  3. Việc tặng voucher CÒN NẰM ĐÓ tới khi tặng xong (không mở đúng 1 ngày).
  4. Mệnh giá 0 = máy KHÔNG tặng.
  5. Mốc khuyến mãi không có đợt đang chạy thì chăm như mốc thường.
  6. Khách đang có ĐƠN CHẠY thì rời hẳn bảng việc, kể cả cột gấp.

Cộng thêm: thang mốc sinh từ 3 con số · nhịp nhắc voucher 15/7/3/0 · quá hạn
mốc · cột đặt tay tự nhả · công tắc TẮT thì chạy luật dải ngày cũ · 3 màn web
mở được và các nút chặn đúng quyền.

Dữ liệu giả mang dấu `__c6__`, dọn sạch đầu/cuối. KHÔNG gọi mạng.

Chạy:  python scripts/thu_c6_cskh.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient           # noqa: E402

from app.core import runtime_config                 # noqa: E402
from app.core.ngay import hom_nay                   # noqa: E402
from app.core.security import hash_password         # noqa: E402
from app.db.client import get_pg_pool               # noqa: E402
from app.db.repositories import cskh_repo           # noqa: E402
from app.main import app                            # noqa: E402
from app.services import cskh_service as svc        # noqa: E402

DAU = "__c6__"
MK = "C6-test-1234"
PASS = 0
FAIL = 0

# Cài đặt bị đổi trong lúc chạy — trả lại đúng như cũ ở cuối, kể cả khi FAIL.
KHOA_CAU_HINH = ("cskh_flow_enabled", "voucher_first_value",
                 "voucher_expiry_days", "voucher_remind_days",
                 "cskh_first_milestone", "cskh_milestone_gap",
                 "cskh_leave_days", "cskh_safety_days", "cskh_call_after_days",
                 "cskh_overdue_days", "cskh_promo_days")


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    # In KHONG dau: console Windows cp1252 khong in duoc tieng Viet co dau.
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    kh = f"(select id from crm.customers where full_name like '{DAU}%')"
    conn.execute(f"delete from crm.care_interactions where customer_id in {kh}")
    conn.execute(f"delete from crm.vouchers where customer_id in {kh}")
    conn.execute("delete from crm.messages where conversation_id in "
                 f"(select id from crm.conversations where customer_id in {kh})")
    conn.execute(f"delete from crm.conversations where customer_id in {kh}")
    conn.execute(f"delete from crm.order_status_history where order_id in "
                 f"(select id from crm.orders where customer_id in {kh})")
    conn.execute(f"delete from crm.orders where customer_id in {kh}")
    conn.execute(f"delete from crm.customer_assignments where customer_id in {kh}")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")
    conn.execute(f"delete from crm.cskh_promos where name like '{DAU}%'")


def khach(conn, ten: str, ngay_nhan: int | None, **cot) -> int:
    """Tạo khách đã nhận hàng cách đây `ngay_nhan` ngày (None = chưa nhận)."""
    nhan = (datetime.now(timezone.utc) - timedelta(days=ngay_nhan)) \
        if ngay_nhan is not None else None
    cid = conn.execute(
        "insert into crm.customers (full_name, primary_phone, status, "
        "last_delivered_at) values (%s, %s, 'customer', %s) returning id",
        (f"{DAU}{ten}", f"09{abs(hash(ten)) % 100000000:08d}", nhan),
    ).fetchone()["id"]
    if cot:
        dat = ", ".join(f"{k} = %s" for k in cot)
        conn.execute(f"update crm.customers set {dat} where id = %s",
                     (*cot.values(), cid))
    return cid


def voucher(conn, cid: int, *, het_sau: int, trang_thai: str = "con_han",
            tien: int = 50000, ma: str = "") -> int:
    """Voucher hết hạn sau `het_sau` ngày (âm = đã quá hạn)."""
    return conn.execute(
        "insert into crm.vouchers (customer_id, code, amount, granted_on, "
        "expires_on, status) values (%s, %s, %s, %s, %s, %s) returning id",
        (cid, ma, tien, hom_nay() - timedelta(days=30),
         hom_nay() + timedelta(days=het_sau), trang_thai),
    ).fetchone()["id"]


def don(conn, cid: int, *, trang_thai: str, dat_truoc: int = 0,
        loai: str = "new") -> int:
    """Đơn đặt cách đây `dat_truoc` ngày."""
    luc = datetime.now(timezone.utc) - timedelta(days=dat_truoc)
    return conn.execute(
        "insert into crm.orders (customer_id, status, order_type, "
        "total_amount, created_at, delivered_at) values (%s, %s, %s, %s, %s, %s) "
        "returning id",
        (cid, trang_thai, loai, 1_000_000, luc,
         datetime.now(timezone.utc) if trang_thai == "delivered" else None),
    ).fetchone()["id"]


def tin(conn, cid: int, *, ai: str, truoc_ngay: float) -> None:
    """Một tin nhắn của khách/shop cách đây `truoc_ngay` ngày."""
    cv = conn.execute(
        "select id from crm.conversations where customer_id = %s limit 1",
        (cid,)).fetchone()
    if not cv:
        cv = conn.execute(
            "insert into crm.conversations (customer_id, external_conversation_id"
            ", last_message_at) values (%s, %s, now()) returning id",
            (cid, f"{DAU}{cid}")).fetchone()
    conn.execute(
        "insert into crm.messages (conversation_id, sender_type, content, "
        "sent_at) values (%s, %s, 'test', %s)",
        (cv["id"], ai,
         datetime.now(timezone.utc) - timedelta(days=truoc_ngay)))


def the_cua(bang: dict, cid: int) -> dict | None:
    return next((t for t in bang["the"] if int(t["id"]) == cid), None)


def main() -> None:  # noqa: PLR0912, PLR0915 — script nghiem thu
    pool = get_pg_pool()
    cu = {k: (runtime_config.lay(k), runtime_config.da_doi(k))
          for k in KHOA_CAU_HINH}
    try:
        chay(pool)
    finally:
        for k, (gt, da_doi) in cu.items():
            if da_doi:
                runtime_config.dat(k, gt)
            else:
                runtime_config.dat_lai_mac_dinh(k)
        with pool.connection() as conn:
            don_dep(conn)
    print(f"\nKET QUA: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


def chay(pool) -> None:  # noqa: PLR0912, PLR0915
    with pool.connection() as conn:
        don_dep(conn)

    # Cấu hình chuẩn của bài kiểm — chốt cứng để không phụ thuộc máy đang chạy.
    for k, v in [("cskh_flow_enabled", True), ("voucher_first_value", 50000),
                 ("voucher_expiry_days", 30),
                 ("voucher_remind_days", "15,7,3,0"),
                 ("cskh_first_milestone", 45), ("cskh_milestone_gap", 15),
                 ("cskh_leave_days", 210), ("cskh_safety_days", 3),
                 ("cskh_call_after_days", 1), ("cskh_overdue_days", 3),
                 ("cskh_promo_days", 3)]:
        runtime_config.dat(k, v)

    print("== 1. Thang moc sinh tu 3 con so ==")
    muon = svc.thang_mong_muon()
    ma = [m["code"] for m in muon]
    ok("moc dau D45, cach 15 ngay", ma[:3] == ["cskh_45", "cskh_60", "cskh_75"],
       str(ma[:3]))
    ok("moc cuoi la moc BUONG D210", muon[-1]["code"] == "cskh_210"
       and muon[-1]["board_column"] == "moc_out", str(muon[-1]))
    ok("co dung 11 moc cham + 1 moc buong", len(muon) == 12, str(len(muon)))
    promo = [m["offset_days"] for m in muon if m["promo"]]
    ok("co khuyen mai XEN KE (45·75·105·135·165·195)",
       promo == [45, 75, 105, 135, 165, 195], str(promo))
    cua = [(m["window_from"], m["window_to"]) for m in muon[:3]]
    ok("cua so LIEN NHAU, khong chong lan",
       cua == [(45, 59), (60, 74), (75, 89)], str(cua))

    svc.seed_thang(dry=False)
    thang = svc.moc_thang()
    ok("moc BUONG khong nam trong thang cham",
       all(m["board_column"] != "moc_out" for m in thang), str(len(thang)))
    ok("moc hien tai cua khach D50 = D45",
       (svc.moc_hien_tai(50) or {}).get("offset_days") == 45)
    ok("khach D20 chua toi moc nao", svc.moc_hien_tai(20) is None)

    print("\n== 2. LUAT 1+2 — don giao thanh cong: tieu ma cu roi moi tang ==")
    with pool.connection() as conn:
        # BẪY 2: đặt đơn ngày -7 (mã còn hạn tới -2), hàng về hôm nay.
        k_bay2 = khach(conn, "Bay2", 0)
        v_cu = voucher(conn, k_bay2, het_sau=-2, ma="OLD1")
        d_bay2 = don(conn, k_bay2, trang_thai="delivered", dat_truoc=7)

    kq = svc.don_thanh_cong(d_bay2, dry=True)
    ok("chay kho KHONG ghi gi", "tiêu mã OLD1" in " ".join(kq["viec"]))
    with pool.connection() as conn:
        v = conn.execute("select status from crm.vouchers where id = %s",
                         (v_cu,)).fetchone()
    ok("sau chay kho ma cu VAN con_han", v["status"] == "con_han", str(dict(v)))

    kq = svc.don_thanh_cong(d_bay2, dry=False)
    with pool.connection() as conn:
        v = conn.execute("select status, order_used_id from crm.vouchers "
                         "where id = %s", (v_cu,)).fetchone()
        moi = conn.execute(
            "select * from crm.vouchers where customer_id = %s and id <> %s",
            (k_bay2, v_cu)).fetchall()
    ok("BAY 2: ma het han ngay -2 VAN bi tieu (xet theo ngay DAT don)",
       v["status"] == "da_dung" and int(v["order_used_id"]) == d_bay2,
       str(dict(v)))
    ok("BAY 1: tieu ma cu xong thi TANG duoc ma moi", len(moi) == 1,
       f"{len(moi)} ma moi")
    if moi:
        m = dict(moi[0])
        ok("ma moi de TRONG -> trang thai chua_bao_ma",
           m["code"] == "" and m["status"] == "chua_bao_ma", str(m["status"]))
        ok("ma moi do MAY tang", m["granted_by_kind"] == "may")
        ok("han ma moi = 30 ngay ke tu hom nay",
           m["expires_on"] == hom_nay() + timedelta(days=30), str(m["expires_on"]))

    with pool.connection() as conn:
        k_con = khach(conn, "ConMa", 0)
        voucher(conn, k_con, het_sau=10, ma="LIVE1")
        d_con = don(conn, k_con, trang_thai="delivered", dat_truoc=0)
    # Đơn đặt HÔM NAY, mã còn hạn 10 ngày ⇒ tiêu mã, rồi tặng lại mã mới.
    kq = svc.don_thanh_cong(d_con, dry=False)
    with pool.connection() as conn:
        n = conn.execute("select count(*) as n from crm.vouchers where "
                         "customer_id = %s and status = 'chua_bao_ma'",
                         (k_con,)).fetchone()["n"]
    ok("khach dung ma xong duoc tang ma moi ngay", n == 1, str(n))

    print("\n== 3. LUAT 4 — menh gia 0 thi may KHONG tang ==")
    runtime_config.dat("voucher_first_value", 0)
    with pool.connection() as conn:
        k_mg0 = khach(conn, "MG0", 0)
        d_mg0 = don(conn, k_mg0, trang_thai="delivered", dat_truoc=1)
    kq = svc.don_thanh_cong(d_mg0, dry=False)
    with pool.connection() as conn:
        n = conn.execute("select count(*) as n from crm.vouchers where "
                         "customer_id = %s", (k_mg0,)).fetchone()["n"]
    ok("menh gia 0 -> KHONG tang ma nao", n == 0, str(n))
    ok("va noi ro ly do CHUA CAU HINH menh gia",
       any("CHƯA CẤU HÌNH" in x for x in kq["viec"]), str(kq["viec"]))
    runtime_config.dat("voucher_first_value", 50000)

    print("\n== 4. Don DOI khong tieu ma, khong sinh ma ==")
    with pool.connection() as conn:
        k_doi = khach(conn, "DonDoi", 0)
        voucher(conn, k_doi, het_sau=10, ma="KEEP1")
        d_doi = don(conn, k_doi, trang_thai="delivered", dat_truoc=1,
                    loai="exchange")
    kq = svc.don_thanh_cong(d_doi, dry=False)
    with pool.connection() as conn:
        v = conn.execute("select status from crm.vouchers where customer_id = %s",
                         (k_doi,)).fetchall()
    ok("don doi: ma cu KHONG bi tieu",
       len(v) == 1 and v[0]["status"] == "con_han", str([dict(x) for x in v]))

    print("\n== 5. GD2 — nhip nhac voucher 15·7·3·0 ==")
    ok("nhip doc tu cai dat, xa -> gan", svc.nhip_voucher() == [15, 7, 3, 0],
       str(svc.nhip_voucher()))
    for con, mong in [(15, True), (7, True), (3, True), (0, True),
                      (14, False), (8, False), (1, False)]:
        v = {"expires_on": hom_nay() + timedelta(days=con), "code": "X"}
        dung = (svc.nhip_nhac_hom_nay(v) is not None)
        ok(f"con {con:>2} ngay -> {'DUNG' if mong else 'khong'} nhip",
           dung is mong)
    v = {"expires_on": hom_nay() + timedelta(days=7), "code": "ABC"}
    ok("cau nhac DONG theo so ngay that",
       svc.cau_nhac_han(v) == "Voucher ABC còn 7 ngày — nhắc lần 2",
       svc.cau_nhac_han(v))
    v0 = {"expires_on": hom_nay(), "code": "ABC"}
    ok("het han HOM NAY -> nhac gap", "HẾT HẠN HÔM NAY" in svc.cau_nhac_han(v0))
    vqh = {"expires_on": hom_nay() - timedelta(days=2), "code": "ABC"}
    ok("ma qua han ma con 'song' -> bao kiem tra luot quet",
       "kiểm tra lượt quét" in svc.cau_nhac_han(vqh), svc.cau_nhac_han(vqh))

    print("\n== 6. Bang viec — cot cua tung khach ==")
    with pool.connection() as conn:
        k_nhac = khach(conn, "NhacHan", 10)
        voucher(conn, k_nhac, het_sau=7, ma="RM7")
        k_goi = khach(conn, "NhacGoi", 2)          # im lang 2 ngay, chua goi
        k_tang = khach(conn, "CanTang", 8)         # LUAT 3: qua luoi 3 ngay
        k_luoi = khach(conn, "ChuaToiLuoi", 0)     # ngay 0 — chua toi han goi
        k_moc = khach(conn, "QuaHanMoc", 50)       # moc D45 mo tu ngay 45
        k_don = khach(conn, "DonDangChay", 8)
        don(conn, k_don, trang_thai="shipping", dat_truoc=1)
        k_dinh_ky = khach(conn, "DinhKy", 46)      # da cham hom nay
        conn.execute(
            "insert into crm.care_interactions (customer_id, channel, "
            "contacted, action_kind, action_at) values (%s, 'chat', true, "
            "'nhan', now())", (k_dinh_ky,))

    bang = svc.bang_viec(q=DAU)
    t = the_cua(bang, k_nhac)
    ok("khach cam ma con 7 ngay -> cot Nhac han voucher",
       t and t["cot"] == "nhac_han_voucher", str(t and t["cot"]))
    ok("cau viec noi ro con may ngay",
       t and "còn 7 ngày" in t["cau_viec"], str(t and t["cau_viec"]))

    t = the_cua(bang, k_goi)
    ok("khach im 2 ngay, chua goi -> cot Nhac goi",
       t and t["cot"] == "nhac_goi", str(t and t["cot"]))

    t = the_cua(bang, k_tang)
    ok("LUAT 3: qua luoi 5 ngay VAN nam cot Can tang voucher",
       t and t["cot"] == "can_tang_voucher", str(t and t["cot"]))
    ok("cau viec ghi ro 'du 3 ngay khong phan hoi'",
       t and "3 ngày không phản hồi" in t["cau_viec"], str(t and t["cau_viec"]))

    t = the_cua(bang, k_luoi)
    ok("ngay 0 chua toi han goi -> chua vao cot gap nao",
       t and t["cot"] == "moi_nhan_hang", str(t and t["cot"]))

    t = the_cua(bang, k_moc)
    ok("D50 ma moc D45 mo tu ngay 45, qua 5 ngay -> Qua han",
       t and t["cot"] == "qua_han", str(t and t["cot"]))
    ok("cau viec goi dung ten moc", t and "mốc D45" in t["cau_viec"],
       str(t and t["cau_viec"]))

    t = the_cua(bang, k_don)
    ok("LUAT 6: khach dang co don chay -> KHONG phai viec hom nay",
       t and t["la_viec"] is False, str(t and (t["cot"], t["la_viec"])))

    t = the_cua(bang, k_dinh_ky)
    ok("da cham o moc dang mo -> khong con la viec",
       t and t["la_viec"] is False, str(t and (t["cot"], t["la_viec"])))

    print("\n== 7. Da goi roi thi KHONG goi lan 2 ==")
    with pool.connection() as conn:
        conn.execute(
            "insert into crm.care_interactions (customer_id, channel, "
            "contacted, call_result, action_kind, action_at) values "
            "(%s, 'call', true, 'khong_nghe', 'goi', now())", (k_goi,))
    bang = svc.bang_viec(q=DAU)
    t = the_cua(bang, k_goi)
    ok("goi roi -> roi khoi cot Nhac goi", t and t["cot"] != "nhac_goi",
       str(t and t["cot"]))

    print("\n== 8. LUAT 5 — moc khuyen mai khong co dot dang chay ==")
    kh_ct = {"last_delivered_at": datetime.now(timezone.utc) - timedelta(days=45),
             "cham_cuoi": None}
    cau = svc.ctkm_cau_viec(kh_ct, 45)
    ok("chua co dot -> cau viec chung, KHONG biat noi dung uu dai",
       cau == "Gửi ưu đãi khuyến mãi", cau)
    with pool.connection() as conn:
        conn.execute(
            "insert into crm.cskh_promos (name, content, start_on, end_on, "
            "active) values (%s, 'Giam 20%%', %s, %s, true)",
            (f"{DAU}Uu dai T8", hom_nay() - timedelta(days=1),
             hom_nay() + timedelta(days=10)))
    ct = svc.ctkm_dang_chay()
    ok("doc duoc dot dang chay", ct and ct["name"] == f"{DAU}Uu dai T8",
       str(ct and ct["name"]))
    cau = svc.ctkm_cau_viec(kh_ct, 45)
    ok("co dot -> cau viec goi dung TEN dot", DAU in cau, cau)
    cau_het = svc.ctkm_cau_viec(kh_ct, 45 + svc.ctkm_ngay())
    ok("qua 3 ngay bam duoi -> het viec trong dot", cau_het == "", cau_het)
    ok("moc D60 KHONG phai moc khuyen mai",
       svc.ctkm_cau_viec({"last_delivered_at": None, "cham_cuoi": None}, 60) == "")

    print("\n== 9. Cot dat tay + tu nha ==")
    with pool.connection() as conn:
        k_tay = khach(conn, "DatTay", 50)
    svc.keo_the(k_tay, "tu_choi")
    bang = svc.bang_viec(q=DAU)
    t = the_cua(bang, k_tay)
    ok("keo tay -> nam dung cot da chon", t and t["cot"] == "tu_choi",
       str(t and t["cot"]))
    ok("cot Tu choi khong sinh viec", t and t["la_viec"] is False)
    loi = ""
    try:
        svc.keo_the(k_tay, "qua_han")
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("cot may suy ra -> KHONG keo tay duoc", "không kéo tay được" in loi, loi)

    with pool.connection() as conn:
        tin(conn, k_tay, ai="customer", truoc_ngay=0)
    so_nha = cskh_repo.nha_cot_da_cu()
    with pool.connection() as conn:
        c = conn.execute("select cskh_column from crm.customers where id = %s",
                         (k_tay,)).fetchone()
    ok("khach nhan lai -> cot dat tay TU NHA", c["cskh_column"] is None,
       f"nha {so_nha} the, con {c['cskh_column']}")

    print("\n== 10. Khach vua nhan tin -> cot Nong ==")
    with pool.connection() as conn:
        k_nong = khach(conn, "Nong", 50)
        tin(conn, k_nong, ai="customer", truoc_ngay=0.2)
    bang = svc.bang_viec(q=DAU)
    t = the_cua(bang, k_nong)
    ok("tin cuoi la cua khach, trong 24h -> cot Nong",
       t and t["cot"] == "nong", str(t and t["cot"]))
    ok("khach cho dap -> la viec hom nay", t and t["la_viec"] is True)
    with pool.connection() as conn:
        tin(conn, k_nong, ai="agent", truoc_ngay=0.1)
    bang = svc.bang_viec(q=DAU)
    t = the_cua(bang, k_nong)
    ok("nhan vien dap xong -> khong con dung cot Nong",
       t and t["cot"] != "nong", str(t and t["cot"]))

    print("\n== 11. Khach qua ngay BUONG roi khoi bang ==")
    with pool.connection() as conn:
        k_ngu = khach(conn, "DaBuong", 250)
    bang = svc.bang_viec(q=DAU)
    ok("khach 250 ngay khong nhan hang -> khong con tren bang",
       the_cua(bang, k_ngu) is None)

    print("\n== 12. Cong tac TAT -> chay luat dai ngay cu ==")
    runtime_config.dat("cskh_flow_enabled", False)
    ok("nguong dai ngay ve bo cu [30,60,150]", svc.nguong() == (30, 60, 150),
       str(svc.nguong()))
    bang = svc.bang_viec(q=DAU)
    t = the_cua(bang, k_nhac)
    ok("TAT: khach cam voucher KHONG con vao cot nhac han",
       t and t["cot"] != "nhac_han_voucher", str(t and t["cot"]))
    ok("TAT: ten cot ve 'Cham hang thang'",
       next(c["ten"] for c in bang["cot"] if c["ma"] == "cham_dinh_ky")
       == "Chăm hàng tháng")
    with pool.connection() as conn:
        k_tat = khach(conn, "TatCongTac", 0)
        d_tat = don(conn, k_tat, trang_thai="delivered", dat_truoc=0)
    svc.hook_don_giao_thanh_cong(d_tat)
    with pool.connection() as conn:
        n = conn.execute("select count(*) as n from crm.vouchers where "
                         "customer_id = %s", (k_tat,)).fetchone()["n"]
    ok("TAT: hook don giao thanh cong KHONG dong gi toi voucher", n == 0, str(n))
    runtime_config.dat("cskh_flow_enabled", True)
    ok("BAT lai: nguong ve [45,105,165]", svc.nguong() == (45, 105, 165),
       str(svc.nguong()))

    print("\n== 13. Man web ==")
    with pool.connection() as conn:
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vai in (("admin", "Admin"), ("cskh", "CSKH"),
                         ("ketoan", "Kế toán")):
            uid[ten] = conn.execute(
                "insert into crm.users (name, email, username, password_hash, "
                "status, role_id) values (%s, %s, %s, %s, 'active', %s) "
                "returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai])).fetchone()["id"]

    web = TestClient(app)

    def dang_nhap(u: str) -> None:
        web.cookies.clear()
        r = web.post("/dang-nhap", data={"username": u, "password": MK},
                     follow_redirects=False)
        assert r.status_code in (302, 303), r.status_code

    dang_nhap(f"{DAU}admin")
    r = web.get("/crm/bang-viec-cskh")
    ok("man Bang viec CSKH mo duoc", r.status_code == 200, str(r.status_code))
    ok("co bang bao quy trinh dang BAT", "Quy trình CSKH đang BẬT" in r.text)
    ok("noi ro khac man Cham soc C01-C09", "C01-C09" in r.text)
    ok("the khach hien cau viec 📌", "📌" in r.text)
    r = web.get("/crm/bang-viec-cskh?viec=1")
    ok("loc 'chi viec hom nay' chay", r.status_code == 200, str(r.status_code))
    r = web.get("/crm/bang-viec-cskh?q=" + DAU + "NhacHan")
    ok("o tim theo ten khach chay",
       r.status_code == 200 and f"{DAU}NhacHan" in r.text, str(r.status_code))

    r = web.get("/crm/cskh/khuyen-mai")
    ok("man Dot khuyen mai mo duoc", r.status_code == 200, str(r.status_code))
    ok("bay dot dang khai", f"{DAU}Uu dai T8" in r.text)

    r = web.post("/crm/bang-viec-cskh/%d/cham" % k_moc, follow_redirects=False)
    ok("ghi luot cham tra 303", r.status_code == 303, str(r.status_code))
    bang = svc.bang_viec(q=DAU)
    t = the_cua(bang, k_moc)
    ok("cham xong -> khach roi khoi Qua han",
       t and t["cot"] != "qua_han", str(t and t["cot"]))

    r = web.post("/crm/bang-viec-cskh/%d/goi" % k_luoi,
                 data={"ket_qua": "nghe"}, follow_redirects=False)
    ok("ghi cuoc goi tra 303", r.status_code == 303, str(r.status_code))
    with pool.connection() as conn:
        g = conn.execute("select call_result, channel from crm.care_interactions "
                         "where customer_id = %s order by id desc limit 1",
                         (k_luoi,)).fetchone()
    ok("ket qua goi luu dung cot call_result",
       g["call_result"] == "nghe" and g["channel"] == "call", str(dict(g)))

    r = web.post("/crm/cskh/dung-thang", follow_redirects=False)
    ok("admin dung lai thang -> 303", r.status_code == 303, str(r.status_code))

    dang_nhap(f"{DAU}cskh")
    r = web.get("/crm/bang-viec-cskh")
    ok("CSKH xem duoc bang viec", r.status_code == 200, str(r.status_code))
    r = web.post("/crm/cskh/dung-thang", follow_redirects=False)
    ok("CSKH KHONG duoc dung lai thang -> 403", r.status_code == 403,
       str(r.status_code))
    r = web.post("/crm/cskh/khuyen-mai", data={"ten": f"{DAU}lau"},
                 follow_redirects=False)
    ok("CSKH KHONG duoc them dot khuyen mai -> 403", r.status_code == 403,
       str(r.status_code))

    dang_nhap(f"{DAU}ketoan")
    r = web.post("/crm/bang-viec-cskh/%d/cham" % k_luoi, follow_redirects=False)
    ok("Ke toan (khong co customer.edit) KHONG ghi cham duoc -> 403",
       r.status_code == 403, str(r.status_code))


if __name__ == "__main__":
    main()
