"""Nghiệm thu C1 — VOUCHER + HẠNG THẺ (port từ mẫu Kallet).

Kiểm 4 luật mà mẫu ghi rõ "đừng sửa mất", vì đây là chỗ dễ bị sửa hỏng nhất:

  1. Xếp hạng CHỈ NÂNG — khách tiêu ít đi vẫn giữ hạng cũ.
  2. Giảm quyền lợi NGẦM sau 180 ngày — hạng hiển thị KHÔNG đổi.
  3. Còn voucher hiệu lực → `dang_co_voucher` trả bản ghi (nơi khác tắt mốc chăm).
  4. Tặng không kèm mã → trạng thái `chua_bao_ma`, báo mã xong mới `con_han`.

Cộng thêm: phân quyền `voucher.grant` chặn thật, ô lọc hạng thẻ ở màn Khách
hàng ăn đúng, voucher quá hạn tự chuyển trạng thái.

Dữ liệu giả mang dấu `__c1__`, dọn sạch đầu/cuối. KHÔNG gọi mạng.

Chạy:  python scripts/thu_c1_uu_dai.py
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import voucher_repo       # noqa: E402
from app.main import app                           # noqa: E402
from app.services import voucher_service           # noqa: E402

DAU = "__c1__"
MK = "C1-test-1234"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    # In KHONG dau: console Windows cp1252 khong in duoc tieng Viet co dau.
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    kh = f"(select id from crm.customers where full_name like '{DAU}%')"
    conn.execute(f"delete from crm.vouchers where customer_id in {kh}")
    conn.execute(f"delete from crm.orders where customer_id in {kh}")
    conn.execute(f"delete from crm.customer_assignments where customer_id in {kh}")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:  # noqa: PLR0915 — script nghiem thu
    pool = get_pg_pool()
    gio = datetime.now(timezone.utc)
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vai in (("admin", "Admin"), ("sale", "Sale"), ("cskh", "CSKH")):
            uid[ten] = conn.execute(
                "insert into crm.users (name, email, username, password_hash, "
                "status, role_id) values (%s, %s, %s, %s, 'active', %s) "
                "returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]),
            ).fetchone()["id"]

        # 3 khách: chi tiêu to (len Gold) · chi tieu nho · khach lau khong mua
        kh = {}
        for ten, sdt in (("To", "0966000111"), ("Nho", "0966000222"),
                         ("Cu", "0966000333")):
            kh[ten] = conn.execute(
                "insert into crm.customers (full_name, primary_phone, status) "
                "values (%s, %s, 'customer') returning id",
                (f"{DAU}Khach{ten}", sdt),
            ).fetchone()["id"]
            conn.execute(
                "insert into crm.customer_assignments (customer_id, user_id, "
                "assignment_type) values (%s, %s, 'cskh')", (kh[ten], uid["cskh"]))

        # don da giao: To = 6tr (Gold) · Nho = 1,2tr (Member) · Cu = 12tr nhung
        # giao tu 400 ngay truoc -> dinh luat giam quyen loi ngam
        for ten, tien, ngay in (("To", 6_000_000, 3), ("Nho", 1_200_000, 5),
                                ("Cu", 12_000_000, 400)):
            conn.execute(
                "insert into crm.orders (customer_id, status, total_amount, "
                "delivered_at, external_order_id) "
                "values (%s, 'delivered', %s, %s, %s)",
                (kh[ten], tien, gio - timedelta(days=ngay), f"{DAU}DH{ten}"))

    print("== 1. Bac thang hang the ==")
    bac = voucher_service.bac_thang()
    ok("doc duoc bac thang tu card_ranks", len(bac) >= 5, str(len(bac)))
    ok("sap tu CAO xuong THAP",
       [b["code"] for b in bac][:2] == ["diamond", "gold"],
       str([b["code"] for b in bac]))
    ok("moi bac co mat hien thi (icon/mau/nen)",
       all(b.get("mat", {}).get("icon") for b in bac))
    thap = voucher_service.hang_thap_hon()
    ok("day thang khong co bac duoi", thap.get("new_member") is None)
    ok("gold tut xuong silver", thap.get("gold") == "Silver", str(thap))

    print("== 2. LUAT 1 — tinh lai hang CHI NANG ==")
    kq = voucher_service.tinh_lai_hang()
    ok("tinh lai chay duoc", isinstance(kq.get("len_hang"), int), str(kq))
    with pool.connection() as conn:
        hang = {r["full_name"]: (r["card_rank"], r["total_spent"])
                for r in conn.execute(
                    "select full_name, card_rank, total_spent from crm.customers "
                    f"where full_name like '{DAU}%'").fetchall()}
    ok("khach 6tr len Gold", hang[f"{DAU}KhachTo"][0] == "gold", str(hang))
    ok("khach 1,2tr len Member", hang[f"{DAU}KhachNho"][0] == "member", str(hang))
    ok("khach 12tr len Diamond", hang[f"{DAU}KhachCu"][0] == "diamond", str(hang))
    ok("tong chi tieu tinh tu don da giao",
       float(hang[f"{DAU}KhachTo"][1]) == 6_000_000.0, str(hang))

    # Ha chi tieu roi tinh lai: hang PHAI giu nguyen (khong ai bi tut)
    with pool.connection() as conn:
        conn.execute("update crm.orders set total_amount = 100000 "
                     f"where external_order_id = '{DAU}DHTo'")
    voucher_service.tinh_lai_hang()
    with pool.connection() as conn:
        r = conn.execute("select card_rank, total_spent from crm.customers "
                         "where id = %s", (kh["To"],)).fetchone()
    ok("chi tieu tut xuong 100k nhung VAN Gold (chi nang)",
       r["card_rank"] == "gold" and float(r["total_spent"]) == 100000.0,
       str(dict(r)))

    print("== 3. LUAT 2 — giam quyen loi NGAM sau 180 ngay ==")
    n = voucher_repo.dem_giam_quyen_loi(180)
    ok("dem duoc khach qua 180 ngay khong nhan hang", n >= 1, str(n))
    with pool.connection() as conn:
        r = conn.execute("select card_rank from crm.customers where id = %s",
                         (kh["Cu"],)).fetchone()
    ok("hang HIEN THI cua khach do KHONG doi", r["card_rank"] == "diamond",
       str(dict(r)))

    print("== 4. LUAT 4 — tang voucher, chua bao ma ==")
    v1 = voucher_service.tang_voucher(sdt="0966000111", menh_gia="200000",
                                      nguoi_tang=uid["cskh"])
    ok("tang duoc theo SDT", bool(v1.get("id")), str(v1)[:120])
    ok("khong co ma -> trang thai chua_bao_ma",
       v1["status"] == "chua_bao_ma", str(v1["status"]))
    ok("ghi dung nguoi tang", v1["granted_by_kind"] == "nguoi")
    ok("han mac dinh lay tu cai dat",
       (v1["expires_on"] - v1["granted_on"]).days == voucher_service.han_mac_dinh(),
       str(v1["expires_on"]))
    v1b = voucher_service.bao_ma(v1["id"], "sale50k", nguoi_sua=uid["cskh"])
    ok("bao ma xong -> con_han", v1b["status"] == "con_han", str(v1b["status"]))
    ok("ma luu VIET HOA", v1b["code"] == "SALE50K", str(v1b["code"]))

    v2 = voucher_service.tang_voucher(sdt="0966000222", menh_gia="500.000",
                                      ma="tet2026", nguoi_tang=uid["cskh"])
    ok("menh gia co dau cham van doc duoc", float(v2["amount"]) == 500000.0,
       str(v2["amount"]))
    ok("co ma san -> con_han ngay", v2["status"] == "con_han")

    loi = ""
    try:
        voucher_service.tang_voucher(sdt="0900000000", menh_gia="100000")
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("SDT khong co trong he thong -> bao loi ro", "Số điện thoại" in loi
       or "không tìm thấy" in loi.lower(), loi)

    print("== 5. LUAT 3 — con voucher thi TAT moc cham chuan ==")
    ok("khach vua tang -> co voucher hieu luc",
       voucher_service.dang_co_voucher(kh["To"]) is not None)
    ok("khach chua tang -> khong co",
       voucher_service.dang_co_voucher(kh["Cu"]) is None)

    print("== 6. Voucher qua han tu chuyen trang thai ==")
    with pool.connection() as conn:
        conn.execute("update crm.vouchers set expires_on = %s where id = %s",
                     (date.today() - timedelta(days=1), v2["id"]))
    so = voucher_repo.het_han_hang_loat()
    ok("quet duoc it nhat 1 voucher qua han", so >= 1, str(so))
    ok("voucher qua han khong con tinh la hieu luc",
       voucher_service.dang_co_voucher(kh["Nho"]) is None)
    ok("chay lai lan 2 khong doi them dong nao",
       voucher_repo.het_han_hang_loat() == 0)

    print("== 7. O so + bo loc ==")
    so4 = voucher_repo.o_so()
    ok("o so dem duoc tien da phat", float(so4["tien_tong"]) >= 700000.0,
       str(so4))
    ds, tong = voucher_repo.danh_sach(status="con_han")
    ok("loc theo trang thai con_han", all(v["status"] == "con_han" for v in ds),
       str(tong))
    ds, _ = voucher_repo.danh_sach(kind="may")
    ok("loc 'may tang' khong dinh voucher nguoi tang", len(ds) == 0, str(len(ds)))
    ds, _ = voucher_repo.danh_sach(tu_khoa="SALE50K")
    ok("tim theo ma voucher", len(ds) == 1, str(len(ds)))
    ds, _ = voucher_repo.danh_sach(owner_id=uid["sale"])
    ok("pham vi quyen: Sale khong phu trach thi khong thay voucher nao",
       len(ds) == 0, str(len(ds)))
    ds, _ = voucher_repo.danh_sach(owner_id=uid["cskh"])
    ok("CSKH phu trach thi thay du 2 voucher", len(ds) == 2, str(len(ds)))

    print("== 8. Man hinh ==")
    web = TestClient(app)

    def dang_nhap(u: str) -> None:
        r = web.post("/dang-nhap", data={"username": u, "password": MK},
                     follow_redirects=False)
        assert r.status_code == 303, r.status_code

    dang_nhap(f"{DAU}cskh")
    r = web.get("/crm/voucher")
    ok("CSKH mo duoc man Voucher", r.status_code == 200, str(r.status_code))
    ok("bang co ma voucher that", "SALE50K" in r.text)
    ok("co du 4 o so", r.text.count("vc-tile") >= 4)
    ok("o 'chua bao cho khach' co mat", "CHƯA BÁO CHO KHÁCH" in r.text)
    r = web.get("/crm/voucher?tt=da_dung")
    ok("loc trang thai khong con SALE50K", "SALE50K" not in r.text)

    dang_nhap(f"{DAU}sale")
    r = web.get("/crm/voucher")
    ok("Sale KHONG co voucher.grant -> 403", r.status_code == 403,
       str(r.status_code))

    dang_nhap(f"{DAU}admin")
    r = web.get("/crm/hang-the")
    ok("man Hang the mo 200", r.status_code == 200, str(r.status_code))
    ok("hien du 5 bac + o chua xep hang", r.text.count("ht-cot") >= 6)
    ok("co khoi giam quyen loi ngam", "giảm quyền lợi ngầm" in r.text)
    ok("ghi ro KHONG gui tin cho khach",
       "KHÔNG gửi tin thông báo cho khách" in r.text)
    ok("co nut Tinh lai hang", "Tính lại hạng" in r.text)
    ok("co bang quyen loi tung hang", "Quyền lợi từng hạng" in r.text)

    r = web.get("/crm/khach-hang?tier=gold")
    ok("man Khach hang loc duoc theo hang the",
       r.status_code == 200 and f"{DAU}KhachTo" in r.text
       and f"{DAU}KhachNho" not in r.text, str(r.status_code))
    r = web.get("/crm/khach-hang?tier=chua_xep")
    ok("loc 'chua xep hang' khong dinh khach da co hang",
       f"{DAU}KhachTo" not in r.text)
    r = web.get("/crm/khach-hang")
    ok("cot Hang the hien pill that (khong con 'chua co bang hang the')",
       "kh-tier" in r.text and "chưa có bảng hạng thẻ" not in r.text)

    print("== 9. Sua nguong hang the (T3: mot cua o man Cai dat) ==")

    def dat_nguong(gia_tri: str):
        """Ngưỡng nay sửa ở Cài đặt → Ưu đãi, không còn ô nhập ở /crm/hang-the.

        Phải gửi ĐỦ ô của nhóm y như trình duyệt gửi: công tắc vắng mặt nghĩa là
        TẮT, gửi thiếu là vô tình tắt mất công tắc của nhóm.
        """
        from app.core import runtime_config as _rc

        du = {"nhom": "uu_dai", "nguong_silver": gia_tri}
        for m in _rc.danh_sach():
            if m["nhom"] != "uu_dai":
                continue
            if m["kieu"] == "bool":
                if m["gia_tri"]:
                    du[m["code"]] = "1"
            else:
                du[m["code"]] = "" if m["gia_tri"] is None else str(m["gia_tri"])
        return web.post("/quan-tri/cai-dat", data=du, follow_redirects=False)

    r = dat_nguong("")
    ok("xoa nguong tra 303", r.status_code == 303, str(r.status_code))
    with pool.connection() as conn:
        v = conn.execute("select min_spent from crm.card_ranks where code = "
                         "'silver'").fetchone()
    ok("nguong trong = NULL (chua dien), KHONG phai 0", v["min_spent"] is None,
       str(dict(v)))
    r = web.get("/crm/hang-the")
    ok("man hien chu 'chua dien' mau cam", "chưa điền" in r.text)
    ok("man Hang the CHI DOC — khong con o nhap nguong",
       'name="nguong"' not in r.text)
    dat_nguong("3.000.000")
    with pool.connection() as conn:
        v = conn.execute("select min_spent from crm.card_ranks where code = "
                         "'silver'").fetchone()
    ok("go nguong co dau cham van luu dung 3tr",
       float(v["min_spent"]) == 3_000_000.0, str(dict(v)))

    dang_nhap(f"{DAU}sale")
    r = web.post("/crm/hang-the/tinh-lai", follow_redirects=False)
    ok("Sale khong duoc tinh lai hang -> 403", r.status_code == 403,
       str(r.status_code))

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKET QUA: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
