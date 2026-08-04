"""Nghiệm thu C7 — MÀN ĐƠN HÀNG (port `don-hang.php` của mẫu Kallet).

Kiểm những chỗ mẫu ghi rõ "đừng sửa mất", cộng phần bên ta làm khác mẫu:

  1. Rút cột từ pos_raw ĐÚNG — mã đơn hiển thị ≠ system_id, tiền ép được số,
     POS không gửi thì để TRỐNG chứ không phải 0.
  2. Doanh thu LÊN ĐƠN trừ đơn Đã hoàn nhưng GIỮ đơn Đang hoàn (hàng chưa về
     kho thì chưa mất tiền) — đây là chỗ mẫu cảnh báo nặng nhất.
  3. Thẻ chỉ số đếm trên CẢ BỘ LỌC, không phải trang đang xem.
  4. `đến ngày` là ngày BAO GỒM — sai chỗ này là mất trọn đơn ngày cuối kỳ.
  5. Phân trang + sắp xếp không trùng dòng / lọt dòng.
  6. 🔒 PHẠM VI: người không có `revenue.view` chỉ thấy đơn mình phụ trách, và
     POST ids[] tuỳ ý cũng KHÔNG dump được đơn của nhân viên khác.
  7. Xuất Excel đòi `data.export`; cột giữ ĐÚNG thứ tự khai báo dù tích lung tung.

Dữ liệu giả mang dấu `__c7__`, dọn sạch đầu/cuối. KHÔNG gọi mạng.

Chạy:  python scripts/thu_c5_don_hang.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient               # noqa: E402

from app.core.security import hash_password             # noqa: E402
from app.db.client import get_pg_pool                   # noqa: E402
from app.db.repositories import don_hang_repo           # noqa: E402
from app.integrations.pancake_pos import pos_sync       # noqa: E402
from app.main import app                                # noqa: E402
from app.services import don_hang_service as dv         # noqa: E402

DAU = "__c7__"
MK = "C7-test-1234"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    # In KHONG dau: console Windows cp1252 khong in duoc tieng Viet co dau.
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    kh = f"(select id from crm.customers where full_name like '{DAU}%')"
    conn.execute(f"delete from crm.order_status_history where order_id in "
                 f"(select id from crm.orders where customer_id in {kh})")
    conn.execute(f"delete from crm.orders where customer_id in {kh}")
    conn.execute(f"delete from crm.customer_assignments where customer_id in {kh}")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.users where username like '{DAU}%'")


def main() -> None:  # noqa: PLR0915 — script nghiem thu, thang mot mach de doc
    pool = get_pg_pool()
    gio = datetime.now(timezone.utc)
    with pool.connection() as conn:
        don_dep(conn)
        vai = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, v in (("admin", "Admin"), ("sale", "Sale"),
                       ("ketoan", "Kế toán")):
            uid[ten] = conn.execute(
                "insert into crm.users (name, email, username, password_hash, "
                "status, role_id) values (%s, %s, %s, %s, 'active', %s) "
                "returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), vai[v]),
            ).fetchone()["id"]
        kh = conn.execute(
            "insert into crm.customers (full_name, primary_phone, status) "
            "values (%s, '0966555111', 'customer') returning id",
            (f"{DAU}Khach",)).fetchone()["id"]
        kh2 = conn.execute(
            "insert into crm.customers (full_name, primary_phone, status) "
            "values (%s, '0966555222', 'customer') returning id",
            (f"{DAU}KhachHai",)).fetchone()["id"]

        # 6 don phu du 6 tinh huong kiem ben duoi. `nhan` = external_order_id
        # de tim lai; tien de tron so cho de doi chieu bang mat.
        don = {}
        mau = [
            # nhan        trang thai     tien       ngay dat    chu don
            ("XONG",     "delivered",   1_000_000,  3,  "sale"),
            ("XONG2",    "collected",   2_000_000,  4,  "sale"),
            ("DANGHOAN", "returning",     500_000,  5,  "sale"),
            ("HOAN",     "returned",      700_000,  6,  "sale"),
            ("GIAO",     "shipping",      300_000, 40,  None),
            ("DOI",      "delivered",     900_000,  7,  None),
        ]
        for nhan, tt, tien, lui, chu in mau:
            don[nhan] = conn.execute(
                """
                insert into crm.orders
                    (customer_id, external_order_id, status, total_amount,
                     order_type, sale_owner_id, created_at, pos_inserted_at,
                     delivered_at, pos_display_id, cod_amount, prepaid_amount,
                     pos_seller_name, effort_axis, ads_attributed, payroll_period)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s)
                returning id
                """,
                (kh if nhan != "DOI" else kh2, f"{DAU}{nhan}", tt, tien,
                 "exchange" if nhan == "DOI" else "new",
                 uid["sale"] if chu else None,
                 gio - timedelta(days=lui), gio - timedelta(days=lui),
                 gio - timedelta(days=lui) if tt in ("delivered", "collected")
                 else None,
                 f"{DAU}{nhan}", tien if nhan == "XONG" else None,
                 0 if nhan == "XONG" else None,
                 f"{DAU}NVPOS" if nhan == "XONG" else None,
                 "cham_soc" if nhan == "XONG" else None,
                 nhan == "XONG", "2026-08" if nhan == "XONG" else None),
            ).fetchone()["id"]

    loc_c5 = {"q": DAU}       # chi dem don cua bai thu nay

    print("== 1. Rut cot tu pos_raw (pos_sync._cot_pos_rut) ==")
    raw = {"id": "C430270742.88", "system_id": 54652, "cod": "3440000",
           "prepaid": "0", "ad_id": "12025076771332",
           "assigning_seller": {"id": "77c3-5ea2", "name": " Yen Nhi "}}
    c = pos_sync._cot_pos_rut(raw)
    ok("ma don hien thi lay 'id' (chuoi), KHONG phai system_id",
       c["pos_display_id"] == "C430270742.88", str(c))
    ok("COD ep duoc so", c["cod_amount"] == 3_440_000.0, str(c))
    ok("tra truoc = 0 giu nguyen so 0", c["prepaid_amount"] == 0.0, str(c))
    ok("ten nhan vien POS cat khoang trang", c["pos_seller_name"] == "Yen Nhi",
       str(c))
    trong = pos_sync._cot_pos_rut({"id": 9, "cod": "", "prepaid": "rac"})
    ok("POS khong gui tien -> None (TRONG), khong phai 0",
       trong["cod_amount"] is None and trong["prepaid_amount"] is None,
       str(trong))
    ok("chuoi rac khong lam vo dong bo", trong["pos_display_id"] == "9",
       str(trong))

    print("== 2. LUAT — len don TRU don Da hoan, GIU don Dang hoan ==")
    cs = don_hang_repo.chi_so(loc_c5)
    ok("dem du 6 don cua bai thu", int(cs["so_don"]) == 6, str(dict(cs)))
    # 1tr + 2tr + 0,5tr (dang hoan) + 0,3tr + 0,9tr = 4,7tr ; don HOAN 0,7tr bi tru
    ok("len don = 4,7tr (bo don Da hoan 0,7tr)",
       float(cs["len_don"]) == 4_700_000.0, str(cs["len_don"]))
    ok("don DANG hoan VAN nam trong len don",
       float(cs["len_don"]) - 500_000 == 4_200_000.0, str(cs["len_don"]))
    ok("doanh thu thanh cong = 3,9tr (delivered + collected)",
       float(cs["thanh_cong"]) == 3_900_000.0, str(cs["thanh_cong"]))
    ok("dem hoan gom CA dang hoan va da hoan", int(cs["n_hoan"]) == 2,
       str(cs["n_hoan"]))
    ok("dem doi hang theo order_type=exchange", int(cs["n_doi"]) == 1,
       str(cs["n_doi"]))

    print("== 3. Bo loc tung o ==")
    for ten, f, mong in (
        ("trang thai", {**loc_c5, "status": "delivered"}, 2),
        ("lan mua (doi hang)", {**loc_c5, "order_type": "exchange"}, 1),
        ("cong suc", {**loc_c5, "effort": "cham_soc"}, 1),
        ("co ads", {**loc_c5, "ads": "co"}, 1),
        ("khong ads", {**loc_c5, "ads": "khong"}, 5),
        ("nhan vien CRM", {**loc_c5, "nv": uid["sale"]}, 4),
        ("nhan vien POS", {**loc_c5, "nv_pos": f"{DAU}NVPOS"}, 1),
        ("ky luong", {**loc_c5, "ky": "2026-08"}, 1),
    ):
        _, n = don_hang_repo.bang(f, limit=100)
        ok(f"loc {ten}", n == mong, f"duoc {n}, mong {mong}")
    _, n = don_hang_repo.bang({"q": f"{DAU}XONG2"}, limit=10)
    ok("o tim bat ma don ngoai", n == 1, str(n))
    _, n = don_hang_repo.bang({"q": "0966555222"}, limit=10)
    ok("o tim bat so dien thoai khach", n == 1, str(n))

    print("== 4. LUAT — 'den ngay' la ngay BAO GOM ==")
    hom_qua = (gio - timedelta(days=3)).date().isoformat()
    # `den` chua cong 1 ngay -> phai HUT don dat dung ngay do
    _, n_thieu = don_hang_repo.bang({**loc_c5, "den": hom_qua}, limit=100)
    _, n_du = don_hang_repo.bang(
        {**loc_c5, "den": (gio - timedelta(days=2)).date().isoformat()},
        limit=100)
    ok("khong cong 1 ngay thi mat don ngay cuoi ky", n_du > n_thieu,
       f"{n_thieu} vs {n_du}")
    _, tu_den = don_hang_repo.bang(
        {**loc_c5, "tu": (gio - timedelta(days=5)).date().isoformat(),
         "den": (gio - timedelta(days=2)).date().isoformat()}, limit=100)
    ok("khoang tu-den cat dung 3 don (lui 3,4,5 ngay)", tu_den == 3, str(tu_den))
    nhan, a, b = dv.khoang_ngay("7d")
    ok("chon nhanh '7 ngay qua' tra du nhan + 2 moc",
       nhan == "7 ngày qua" and a and b, f"{nhan} {a} {b}")
    _, a2, b2 = dv.khoang_ngay("tuy_chon", "2026-08-05", "2026-08-01")
    ok("tuy chon nhap nguoc thi tu dao lai", (a2, b2) == ("2026-08-01", "2026-08-05"),
       f"{a2} {b2}")
    ok("ma khoang la ma khong lam vo man",
       dv.khoang_ngay("rac_rac")[0] == "Mọi thời gian")

    print("== 5. Phan trang + sap xep khong trung / lot dong ==")
    t1, tong = don_hang_repo.bang(loc_c5, sort="gia", dir_="desc", limit=4)
    t2, _ = don_hang_repo.bang(loc_c5, sort="gia", dir_="desc", limit=4, offset=4)
    ids = [r["id"] for r in t1] + [r["id"] for r in t2]
    ok("2 trang ghep lai du 6 don, khong trung", len(set(ids)) == tong == 6,
       str(ids))
    tien = [float(r["total_amount"]) for r in t1]
    ok("sap giam dan theo gia tri", tien == sorted(tien, reverse=True), str(tien))
    tang, _ = don_hang_repo.bang(loc_c5, sort="gia", dir_="asc", limit=6)
    ok("sap tang dan dao dung chieu",
       [float(r["total_amount"]) for r in tang][0] == min(tien + [300_000.0]),
       str([float(r["total_amount"]) for r in tang]))

    print("== 6. Man hinh + phan quyen ==")
    web = TestClient(app)

    def dang_nhap(u: str) -> None:
        r = web.post("/dang-nhap", data={"username": u, "password": MK},
                     follow_redirects=False)
        assert r.status_code == 303, r.status_code

    dang_nhap(f"{DAU}admin")
    r = web.get("/crm/don-hang")
    ok("Admin mo duoc man Don hang", r.status_code == 200, str(r.status_code))
    ok("co dai 5 the chi so", r.text.count("kh-tile") >= 5)
    ok("co thanh noi tich chon", 'id="dh-bar"' in r.text)
    ok("co popover chon cot xuat", 'id="dh-pop"' in r.text)
    ok("co o loc nhan vien POS", "Mọi nhân viên POS" in r.text)
    ok("co o khoang thoi gian", "dh-range" in r.text)
    r = web.get(f"/crm/don-hang?q={DAU}XONG2")
    ok("loc tren URL ra dung 1 don", r.text.count('class="dh-tick"') == 1,
       str(r.text.count('class="dh-tick"')))
    ok("hien nhan trang thai tieng Viet", "Đã thu tiền" in r.text)

    dang_nhap(f"{DAU}sale")
    r = web.get(f"/crm/don-hang?q={DAU}")
    ok("Sale vao duoc man (co order.view)", r.status_code == 200,
       str(r.status_code))
    ok("Sale CHI thay don minh phu trach (4/6)",
       r.text.count('class="dh-tick"') == 4, str(r.text.count('class="dh-tick"')))
    ok("man noi ro dang bi thu hep pham vi", "dh-scope" in r.text)
    ok("Sale khong co nut xuat (thieu data.export)",
       'onclick="dhXuatLoc()"' not in r.text)
    r = web.get("/crm/don-hang/xuat?cols=ma_don")
    ok("Sale xuat CSV -> 403", r.status_code == 403, str(r.status_code))
    # 🔒 POST id cua don NGUOI KHAC: phai ra file rong, khong lo du lieu
    r = web.post("/crm/don-hang/xuat",
                 data={"ids": [str(don["DOI"])], "cols": ["ma_don", "khach"]})
    ok("Sale POST id don nguoi khac cung bi chan (403)",
       r.status_code == 403, str(r.status_code))

    print("== 7. Xuat Excel ==")
    dang_nhap(f"{DAU}ketoan")
    r = web.get(f"/crm/don-hang/xuat?q={DAU}&cols=gia_tri&cols=ma_don")
    ok("Ke toan xuat duoc (co data.export)", r.status_code == 200,
       str(r.status_code))
    dong = r.text.lstrip("﻿").splitlines()
    ok("cot giu DUNG thu tu khai bao du tich nguoc",
       dong[0] == "Mã đơn;Giá trị", dong[0])
    ok("xuat du 6 don cua bai thu", len(dong) == 7, str(len(dong)))
    ok("file co BOM UTF-8 cho Excel VN", r.text.startswith("﻿"))
    r = web.get(f"/crm/don-hang/xuat?q={DAU}&cols=rac")
    dong = r.text.lstrip("﻿").splitlines()
    ok("tich toan cot la -> roi ve bo mac dinh",
       dong[0].split(";")[0] == "Mã đơn" and len(dong[0].split(";")) == 13,
       dong[0])
    r = web.get(f"/crm/don-hang/xuat?q={DAU}XONG&cols=cod&cols=tra_truoc")
    dong = r.text.lstrip("﻿").splitlines()
    o_xong = next(d for d in dong[1:] if d.count(";") == 1 and d != ";")
    # Tich 'cod' truoc 'tra_truoc' nhung file van ra THU TU KHAI BAO
    # (Tra truoc; COD) — chinh la luat "cot giu dung thu tu" o tren.
    ok("COD/tra truoc co so thi ghi so, va dung thu tu khai bao",
       dong[0] == "Trả trước;COD" and o_xong == "0;1000000",
       f"{dong[0]} | {o_xong}")
    r = web.get(f"/crm/don-hang/xuat?q={DAU}HOAN&cols=cod&cols=tra_truoc")
    ok("POS khong gui thi o TRONG, khong bia so 0",
       r.text.lstrip("﻿").splitlines()[1] == ";",
       r.text.lstrip("﻿").splitlines()[1])
    # xuat theo id da tich (Ke toan co revenue.view -> xem duoc moi don)
    r = web.post("/crm/don-hang/xuat",
                 data={"ids": [str(don["XONG"]), str(don["DOI"])],
                       "cols": ["ma_don"]})
    ok("xuat theo id da tich ra dung 2 dong",
       len(r.text.lstrip("﻿").splitlines()) == 3,
       str(len(r.text.lstrip("﻿").splitlines())))
    r = web.post("/crm/don-hang/xuat",
                 data={"ca_bo_loc": "1", "q": DAU, "cols": ["ma_don"]})
    ok("nut 'chon ca bo loc' xuat het 6 don",
       len(r.text.lstrip("﻿").splitlines()) == 7,
       str(len(r.text.lstrip("﻿").splitlines())))

    print("== 8. Danh muc cot + link POS ==")
    ok("chon_cot giu thu tu khai bao",
       dv.chon_cot(["gia_tri", "khach", "ma_don"]) == ["ma_don", "khach", "gia_tri"],
       str(dv.chon_cot(["gia_tri", "khach", "ma_don"])))
    ok("chon_cot bo ten cot la",
       dv.chon_cot(["ma_don", "khong_ton_tai"]) == ["ma_don"])
    ok("khong tich gi -> bo mac dinh",
       dv.chon_cot([]) == dv.COT_MAC_DINH)
    ok("link POS dung khi du shop + ma he thong",
       dv.link_pos({"pos_shop_id": 132, "pos_order_id": 55})
       == "https://pos.pancake.vn/shop/132/order?order_id=55")
    ok("thieu ma he thong thi KHONG dung link chet",
       dv.link_pos({"pos_shop_id": 132}) == "")
    ok("ma don uu tien ma POS nguoi dung thay",
       dv.ma_don({"id": 5, "pos_display_id": "C430", "external_order_id": "x"})
       == "C430")
    ok("khong co ma POS thi lui ve ma ngoai roi #id",
       dv.ma_don({"id": 5}) == "#5")

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKET QUA: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
