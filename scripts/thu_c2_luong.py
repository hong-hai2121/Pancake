"""Nghiem thu C2 — LUONG · THUONG · DOI SOAT (port mau Kallet).

Kiem BA LUAT tien bac ma mau dan "dung sua cho gon":

  1. Thuong cham soc CONG CHONG len hoa hong (khong thay the).
  2. Thuong nong 2 kieu chay SONG SONG va CONG DON (doanh thu NGAY + gia tri
     TUNG DON) — mot don to trong mot ngay to thi an ca hai.
  3. Don hoan/huy SAU khi chot luong -> TRU KY SAU, khong sua nguoc ky cu.

Cong them: hoa hong lay bac CAO NHAT cham toi (khong cong don bac), so thuong
tinh LAI o may chu, bac thuong bat buoc ly do, phan quyen 3 muc chan that.

Du lieu gia mang dau `__c2__`, don sach dau/cuoi. KHONG goi mang.

Chay:  python scripts/thu_c2_luong.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import payroll_repo       # noqa: E402
from app.main import app                           # noqa: E402
from app.services import payroll_service           # noqa: E402

DAU = "__c2__"
MK = "C2-test-1234"
KY = "2026-07"          # ky da qua -> chot duoc ma khong dung ky hien tai
KY_SAU = "2026-08"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    nv = f"(select id from crm.users where email like '{DAU}%')"
    kh = f"(select id from crm.customers where full_name like '{DAU}%')"
    don = f"(select id from crm.orders where customer_id in {kh})"
    conn.execute(f"delete from crm.care_bonus_reviews where order_id in {don}")
    conn.execute(f"delete from crm.payroll_adjustments where user_id in {nv}")
    conn.execute(f"delete from crm.payrolls where user_id in {nv}")
    conn.execute(f"delete from crm.user_goals where user_id in {nv}")
    conn.execute(f"delete from crm.care_interactions where customer_id in {kh}")
    conn.execute(f"delete from crm.orders where customer_id in {kh}")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.commission_tiers where role_id in "
                 f"(select id from crm.roles where name = '{DAU}vai')")
    conn.execute(f"delete from crm.care_bonus_tiers where role_id in "
                 f"(select id from crm.roles where name = '{DAU}vai')")
    conn.execute(f"delete from crm.hot_bonus_tiers where role_id in "
                 f"(select id from crm.roles where name = '{DAU}vai')")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")
    conn.execute(f"delete from crm.roles where name = '{DAU}vai'")


def main() -> None:  # noqa: PLR0915 — script nghiem thu
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)
        # Vai tro RIENG cua bai kiem -> bac luong khong dinh du lieu seed that
        vai = conn.execute(
            "insert into crm.roles (name, description, base_salary) "
            "values (%s, 'vai tro kiem thu C2', 5000000) returning id",
            (f"{DAU}vai",),
        ).fetchone()["id"]
        for nguong, kieu, gia in ((50_000_000, "phan_tram", 2),
                                  (100_000_000, "phan_tram", 5)):
            conn.execute(
                "insert into crm.commission_tiers (role_id, min_revenue, kind,"
                " value) values (%s, %s, %s, %s)", (vai, nguong, kieu, gia))
        conn.execute(
            "insert into crm.care_bonus_tiers (role_id, min_revenue, kind, value)"
            " values (%s, 0, 'tien', 50000)", (vai,))
        # Hai kieu thuong nong -> kiem LUAT 2
        conn.execute(
            "insert into crm.hot_bonus_tiers (role_id, basis, threshold, kind,"
            " value) values (%s, 'doanh_thu_ngay', 10000000, 'tien', 200000)",
            (vai,))
        conn.execute(
            "insert into crm.hot_bonus_tiers (role_id, basis, threshold, kind,"
            " value) values (%s, 'gia_tri_don', 10000000, 'tien', 300000)",
            (vai,))

        role_that = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vt in (("nv", f"{DAU}vai"), ("admin", "Admin"),
                        ("sale", "Sale")):
            uid[ten] = conn.execute(
                "insert into crm.users (name, email, username, password_hash, "
                "status, role_id) values (%s, %s, %s, %s, 'active', %s) "
                "returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role_that[vt]),
            ).fetchone()["id"]

        kh = conn.execute(
            "insert into crm.customers (full_name, primary_phone, status) "
            "values (%s, '0977000111', 'customer') returning id",
            (f"{DAU}Khach",),
        ).fetchone()["id"]

        # 3 don GIAO CUNG MOT NGAY 15/07: 12tr + 40tr + 10tr = 62tr
        #   -> doanh thu ngay 62tr  >= nguong ngay 10tr   -> +200k (1 lan)
        #   -> tung don >= 10tr: ca 3 don                  -> +900k
        #   -> tong doanh thu 62tr >= bac 50tr (2%)        -> hoa hong 1,24tr
        ngay_giao = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
        don_id = []
        for i, tien in enumerate((12_000_000, 40_000_000, 10_000_000)):
            don_id.append(conn.execute(
                "insert into crm.orders (customer_id, status, total_amount, "
                "sale_owner_id, delivered_at, payroll_period, effort_axis, "
                "external_order_id) values (%s, 'delivered', %s, %s, %s, %s, "
                "'cham_soc', %s) returning id",
                (kh, tien, uid["nv"], ngay_giao + timedelta(minutes=i), KY,
                 f"{DAU}DH{i}"),
            ).fetchone()["id"])

    print("== 1. Hoa hong lay bac CAO NHAT cham toi ==")
    hh, bac = payroll_service.hoa_hong(vai, 62_000_000)
    ok("62tr -> bac 50tr, 2%", hh == 1_240_000 and bac
       and float(bac["min_revenue"]) == 50_000_000, f"{hh} / {bac}")
    hh2, bac2 = payroll_service.hoa_hong(vai, 120_000_000)
    ok("120tr -> nhay len bac 100tr, 5% (KHONG cong don 2%+5%)",
       hh2 == 6_000_000, str(hh2))
    hh0, _ = payroll_service.hoa_hong(vai, 10_000_000)
    ok("duoi nguong thap nhat -> hoa hong 0", hh0 == 0, str(hh0))

    print("== 2. LUAT 2 — thuong nong 2 kieu CONG DON ==")
    tn = payroll_service.thuong_nong(vai, uid["nv"], KY)
    ok("co ca 2 kieu cung luc", len(tn["theo_ngay"]) == 1
       and len(tn["theo_don"]) == 3, str(tn)[:200])
    ok("theo ngay: 1 ngay dat nguong -> 200k",
       tn["theo_ngay"] and tn["theo_ngay"][0]["thuong"] == 200_000,
       str(tn["theo_ngay"]))
    ok("theo don: 3 don >= 10tr -> 900k",
       sum(x["thuong"] for x in tn["theo_don"]) == 900_000,
       str(tn["theo_don"]))
    ok("tong = CONG DON ca hai = 1,1tr", tn["tong"] == 1_100_000, str(tn["tong"]))

    print("== 3. LUAT 1 — thuong cham CONG CHONG len hoa hong ==")
    # Chua duyet don nao -> thuong cham = 0
    l0 = payroll_service.tinh_luong(uid["nv"], KY)
    ok("chua duyet thi thuong cham = 0", l0["thuong_cham"] == 0,
       str(l0["thuong_cham"]))
    ok("hoa hong van co", l0["hoa_hong"] == 1_240_000, str(l0["hoa_hong"]))
    for oid in don_id:
        payroll_service.duyet_thuong_cham(oid, nguoi=uid["admin"])
    l1 = payroll_service.tinh_luong(uid["nv"], KY, ghi=True)
    ok("duyet 3 don -> thuong cham 150k", l1["thuong_cham"] == 150_000,
       str(l1["thuong_cham"]))
    ok("hoa hong KHONG bi tru di (cong chong, khong thay the)",
       l1["hoa_hong"] == 1_240_000, str(l1["hoa_hong"]))
    mong = (5_000_000 + 1_240_000 + 150_000 + 1_100_000)
    ok(f"tong = luong cung + hoa hong + thuong cham + thuong nong = {mong:,}",
       l1["tong"] == mong, str(l1["tong"]))
    ok("doanh thu LEN DON va DA THU deu 62tr (don deu da giao)",
       l1["len_don"] == 62_000_000 and l1["da_thu"] == 62_000_000,
       f'{l1["len_don"]} / {l1["da_thu"]}')

    print("== 4. So thuong tinh LAI o may chu ==")
    with pool.connection() as conn:
        r = conn.execute("select amount from crm.care_bonus_reviews "
                         "where order_id = %s", (don_id[0],)).fetchone()
    ok("amount luu la so may chu tinh (50k), khong nhan tu client",
       float(r["amount"]) == 50_000.0, str(dict(r)))

    loi = ""
    try:
        payroll_service.bac_thuong_cham(don_id[0], "  ", nguoi=uid["admin"])
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("bac thuong KHONG co ly do -> chan", "lý do" in loi, loi)
    payroll_service.bac_thuong_cham(don_id[2], "Khach tu vao mua", nguoi=uid["admin"])
    l2 = payroll_service.tinh_luong(uid["nv"], KY, ghi=True)
    ok("bac 1 don -> thuong cham con 100k", l2["thuong_cham"] == 100_000,
       str(l2["thuong_cham"]))

    print("== 5. Ba ro doi soat ==")
    bang = payroll_service.bang_doi_soat()
    ma_don = {d["id"]: d for d in bang["rows"]}
    ok("3 don deu vao dien thuong cham", all(i in ma_don for i in don_id),
       str(list(ma_don)))
    ok("don da duyet/bac nam ro 'done'",
       all(ma_don[i]["ro"] == "done" for i in don_id), str(bang["dem"]))
    payroll_service.doi_phan_loai(don_id[1], "quang_cao", nguoi=uid["admin"],
                                  ly_do="Khach bam quang cao")
    bang2 = payroll_service.bang_doi_soat()
    ok("doi sang Quang cao -> don roi khoi dien thuong cham",
       don_id[1] not in {d["id"] for d in bang2["rows"]},
       str([d["id"] for d in bang2["rows"]]))
    l3 = payroll_service.tinh_luong(uid["nv"], KY, ghi=True)
    ok("TIEN DI THEO: thuong cham tut con 50k", l3["thuong_cham"] == 50_000,
       str(l3["thuong_cham"]))

    print("== 6. LUAT 3 — don hoan sau chot ky -> TRU KY SAU ==")
    kq = payroll_service.chot_ky(KY, uid["admin"])
    ok("chot ky ghi duoc", kq["so_dong"] >= 1, str(kq))
    pr = payroll_repo.get_payroll(uid["nv"], KY)
    ok("ky da dong bang", pr["frozen"], str(dict(pr))[:120])
    tong_da_chot = float(pr["total"])

    # Sau khi chot, don dau tien bi hoan
    with pool.connection() as conn:
        conn.execute("update crm.orders set status = 'returned' where id = %s",
                     (don_id[0],))
    truy = payroll_service.truy_thu_don_hoan(nguoi=uid["admin"])
    ok("sinh dung 1 khoan truy thu", len(truy) == 1, str(truy))
    ok("khoan truy thu la so AM", float(truy[0]["amount"]) < 0, str(truy[0]))
    ok("truy thu ghi vao KY SAU chu khong phai ky cu",
       truy[0]["period"] == KY_SAU, str(truy[0]["period"]))
    ok("chay lai KHONG nhan doi khoan tru",
       payroll_service.truy_thu_don_hoan(nguoi=uid["admin"]) == [])
    pr2 = payroll_repo.get_payroll(uid["nv"], KY)
    ok("ky cu KHONG bi sua nguoc", float(pr2["total"]) == tong_da_chot,
       f'{pr2["total"]} vs {tong_da_chot}')
    payroll_service.tinh_luong(uid["nv"], KY, ghi=True)
    pr3 = payroll_repo.get_payroll(uid["nv"], KY)
    ok("tinh lai ky DA CHOT cung khong ghi de duoc",
       float(pr3["total"]) == tong_da_chot, str(pr3["total"]))
    l_sau = payroll_service.tinh_luong(uid["nv"], KY_SAU)
    ok("ky sau nhan khoan tru", l_sau["dieu_chinh"] < 0, str(l_sau["dieu_chinh"]))

    print("== 7. Ky da chot thi chan sua phan loai ==")
    loi = ""
    try:
        payroll_service.doi_phan_loai(don_id[2], "quang_cao", nguoi=uid["admin"])
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("doi phan loai don thuoc ky da chot -> chan, chi ro phai dieu chinh ky sau",
       "đã chốt" in loi and "kỳ sau" in loi, loi)

    print("== 8. Man hinh + phan quyen ==")
    web = TestClient(app)

    def dang_nhap(u: str) -> None:
        r = web.post("/dang-nhap", data={"username": u, "password": MK},
                     follow_redirects=False)
        assert r.status_code == 303, r.status_code

    dang_nhap(f"{DAU}admin")
    r = web.get(f"/crm/thu-nhap?ky={KY}&nv={uid['nv']}")
    ok("admin xem duoc thu nhap nguoi khac (payroll.manage)",
       r.status_code == 200, str(r.status_code))
    ok("man ghi ro 'LEN DON' va 'DA THU'",
       "LÊN ĐƠN" in r.text and "ĐÃ THU" in r.text)
    ok("man giai thich thuong nong 2 kieu",
       "song song" in r.text and "cộng dồn" in r.text)
    ok("bao ky da chot", "đã chốt" in r.text)

    r = web.get(f"/crm/luong?ky={KY}")
    ok("man Luong thuong mo 200", r.status_code == 200, str(r.status_code))
    ok("bang luong co ten nhan vien", f"{DAU}nv" in r.text)
    ok("ghi chu 'thuong cham CONG CHONG len hoa hong'",
       "CHỒNG lên hoa hồng" in r.text)

    r = web.get("/crm/doi-soat")
    ok("man Doi soat mo 200", r.status_code == 200, str(r.status_code))
    ok("co du 4 chip ro", r.text.count("ds-chip") >= 4)

    r = web.get("/crm/bac-luong")
    ok("man Bac luong mo 200", r.status_code == 200, str(r.status_code))
    ok("hien ca 3 loai bac",
       "Bậc hoa hồng" in r.text and "Bậc thưởng chăm sóc" in r.text
       and "Bậc thưởng nóng" in r.text)

    dang_nhap(f"{DAU}sale")
    r = web.get("/crm/luong")
    ok("Sale KHONG co payroll.manage -> 403 man Luong thuong",
       r.status_code == 403, str(r.status_code))
    r = web.get("/crm/doi-soat")
    ok("Sale KHONG co payroll.approve -> 403 man Doi soat",
       r.status_code == 403, str(r.status_code))
    r = web.get("/crm/thu-nhap")
    ok("Sale VAN xem duoc thu nhap cua chinh minh", r.status_code == 200,
       str(r.status_code))
    r = web.get(f"/crm/thu-nhap?nv={uid['nv']}")
    ok("Sale go tay ?nv= cua nguoi khac -> van chi thay cua minh",
       f"{DAU}nv" not in r.text.split("Đơn tính vào kỳ")[0])

    print("== 9. Muc tieu ca nhan ==")
    r = web.post("/crm/thu-nhap/muc-tieu", data={"ky": KY, "trieu": "15"},
                 follow_redirects=False)
    ok("luu muc tieu tra 303", r.status_code == 303, str(r.status_code))
    with pool.connection() as conn:
        g = conn.execute("select target from crm.user_goals where user_id = %s "
                         "and period = %s", (uid["sale"], KY)).fetchone()
    ok("muc tieu ghi cho NGUOI DANG NHAP (khong phai ?nv=)",
       g and float(g["target"]) == 15_000_000.0, str(dict(g) if g else None))

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKET QUA: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
