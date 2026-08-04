"""Nghiem thu C4 — THU VIEN KICH BAN · KHO DATA · GIAM SAT (SOI TIN).

Kiem cac luat de hong nhat:

  1. So khop tieng Viet BA KIEU: co dau · bo dau · viet tat ("e vua goi c").
  2. 1 CONG / khach / nhan vien / hanh dong / NGAY — nhan 10 tin van 1 cong.
  3. CUA SO SOI ±1 NGAY (nhan vien nhan sang, toi moi tick).
  4. Chua toi han thi CHO THEM, KHONG bac voi. Qua han moi bac.
  5. Bang chung den SAU thi NANG ban tu khai len da xac minh.
  6. THU VIEN kich ban = chep tay, KHONG gui gi (khac han Chien dich).
  7. Thu hoi khach BAT BUOC ly do + khoa khong chia lai cho chinh nguoi do.

Du lieu gia mang dau `__c4__`, don sach dau/cuoi. KHONG goi mang.

Chay:  python scripts/thu_c4_giam_sat.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core.ngay import bay_gio                  # noqa: E402
from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import giam_sat_repo      # noqa: E402
from app.main import app                           # noqa: E402
from app.services import giam_sat_service as gs    # noqa: E402
from app.services import tieng_viet as tv          # noqa: E402

DAU = "__c4__"
MK = "C4-test-1234"
PAGE_GIA = "999000111000222"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    kh = f"(select id from crm.customers where full_name like '{DAU}%')"
    conn.execute(f"delete from crm.care_interactions where customer_id in {kh}")
    conn.execute(f"delete from crm.recall_blocks where customer_id in {kh}")
    conn.execute(f"delete from crm.assignment_logs where customer_id in {kh}")
    conn.execute(f"delete from crm.messages where conversation_id in "
                 f"(select id from crm.conversations where customer_id in {kh})")
    conn.execute(f"delete from crm.conversations where customer_id in {kh}")
    conn.execute(f"delete from crm.pages where external_page_id = '{PAGE_GIA}'")
    conn.execute(f"delete from crm.customer_assignments where customer_id in {kh}")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.script_suggest_rules where script_id in "
                 f"(select id from crm.sale_scripts where title like '{DAU}%')")
    conn.execute(f"delete from crm.sale_scripts where title like '{DAU}%'")
    conn.execute(f"delete from crm.export_logs where scope like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:  # noqa: PLR0915 — script nghiem thu
    print("== 1. So khop tieng Viet BA KIEU ==")
    ok("bo dau: 'Đau dạ dày' -> 'dau da day'",
       tv.chuan_hoa("Đau dạ dày") == "dau da day", tv.chuan_hoa("Đau dạ dày"))
    ok("chu Đ hoa cung bo duoc (NFD khong tach duoc chu nay)",
       tv.bo_dau("ĐAU") == "DAU", tv.bo_dau("ĐAU"))
    ok("bung viet tat: 'e vua goi c r' -> 'em vua goi chi roi'",
       tv.bung_viet_tat("e vua goi c r") == "em vua goi chi roi",
       tv.bung_viet_tat("e vua goi c r"))
    ok("khop khi mau CO DAU, van ban KHONG dau",
       tv.khop("vừa gọi", "em vua goi chi roi a"))
    ok("khop khi van ban VIET TAT", tv.khop("vua goi", "e vua goi c r a"))
    ok("khong khop bua", tv.khop("tang voucher", "em vua goi chi roi") is False)
    ok("nhan dien tin 'da goi'", tv.la_tin_da_goi("e vua goi c ma ko ai bat may"))
    ok("MAU CHAN chay TRUOC: 'chị gọi lại cho em' KHONG tinh la da goi",
       tv.la_tin_da_goi("chi goi lai cho em nhe") is False)

    pool = get_pg_pool()
    gio = datetime.now(timezone.utc)
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vai in (("nv", "Sale"), ("tn", "Trưởng nhóm Sale"),
                         ("admin", "Admin")):
            uid[ten] = conn.execute(
                "insert into crm.users (name, email, username, password_hash, "
                "status, role_id) values (%s, %s, %s, %s, 'active', %s) "
                "returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]),
            ).fetchone()["id"]

        page = conn.execute(
            "insert into crm.pages (platform, external_page_id, name) "
            f"values ('facebook', '{PAGE_GIA}', '{DAU}Page') returning id"
        ).fetchone()["id"]

        kh = {}
        for ten in ("CoTin", "KhongTin", "GoiDien", "ChuaChia"):
            kh[ten] = conn.execute(
                "insert into crm.customers (full_name, primary_phone, status) "
                "values (%s, %s, 'customer') returning id",
                (f"{DAU}Khach{ten}", f"0955{abs(hash(ten)) % 1000000:06d}"),
            ).fetchone()["id"]
        # 3 khach dau co nguoi phu trach; ChuaChia CO Y de trong
        for ten in ("CoTin", "KhongTin", "GoiDien"):
            conn.execute(
                "insert into crm.customer_assignments (customer_id, user_id, "
                "assignment_type) values (%s, %s, 'sale')", (kh[ten], uid["nv"]))
            conv = conn.execute(
                "insert into crm.conversations (customer_id, page_id, "
                "external_conversation_id, last_message_at) "
                "values (%s, %s, %s, %s) returning id",
                (kh[ten], page, f"{PAGE_GIA}_c4{ten}", gio)).fetchone()["id"]
            kh[f"conv_{ten}"] = conv

        # Khach CoTin: NV nhan tin THAT hom qua (trong cua ±1 ngay)
        conn.execute(
            "insert into crm.messages (conversation_id, external_message_id, "
            "sender_type, sender_name, sender_user_id, content, msg_type, sent_at)"
            " values (%s, %s, 'agent', %s, %s, %s, 'text', %s)",
            (kh["conv_CoTin"], f"{DAU}m1", f"{DAU}nv", uid["nv"],
             "Da chi oi, ben em co uu dai thang nay a", gio - timedelta(hours=20)))
        # Khach GoiDien: NV go cau bao da goi (VIET TAT)
        conn.execute(
            "insert into crm.messages (conversation_id, external_message_id, "
            "sender_type, sender_name, sender_user_id, content, msg_type, sent_at)"
            " values (%s, %s, 'agent', %s, %s, %s, 'text', %s)",
            (kh["conv_GoiDien"], f"{DAU}m2", f"{DAU}nv", uid["nv"],
             "e vua goi c ma ko ai bat may a", gio - timedelta(hours=10)))
        # Khach KhongTin: CO Y khong co tin nao cua NV

    print("== 2. LUAT 1 CONG / khach / NV / hanh dong / NGAY ==")
    r1 = gs.ghi_cong(kh["CoTin"], uid["nv"], "nhan")
    ok("ghi cong lan dau -> 'moi'", r1 == "moi", r1)
    r2 = gs.ghi_cong(kh["CoTin"], uid["nv"], "nhan")
    ok("ghi lai cung ngay -> 'trung' (KHONG cong them)", r2 == "trung", r2)
    r3 = gs.ghi_cong(kh["CoTin"], uid["nv"], "goi")
    ok("hanh dong KHAC cung ngay -> van duoc 1 cong", r3 == "moi", r3)
    with pool.connection() as conn:
        n = conn.execute(
            "select count(*) as n from crm.care_interactions where customer_id "
            "= %s and user_id = %s", (kh["CoTin"], uid["nv"])).fetchone()["n"]
    ok("dung 2 dong trong DB (nhan + goi)", n == 2, str(n))

    print("== 3. May TU LAM thi xac minh ngay ==")
    r = gs.ghi_cong(kh["KhongTin"], uid["nv"], "tang_voucher", may_tu_lam=True,
                    ly_do="may ghi: voucher da tao trong he thong")
    ok("may tu lam -> 'moi'", r == "moi", r)
    with pool.connection() as conn:
        row = conn.execute(
            "select verify_status, verify_source from crm.care_interactions "
            "where customer_id = %s and action_kind = 'tang_voucher'",
            (kh["KhongTin"],)).fetchone()
    ok("trang thai da_xac_minh ngay, khong cho soi",
       row["verify_status"] == "da_xac_minh", str(dict(row)))
    ok("nguon = may_tu_nhan", row["verify_source"] == "may_tu_nhan",
       row["verify_source"])

    print("== 4. Bang chung den SAU thi NANG ban tu khai ==")
    gs.ghi_cong(kh["KhongTin"], uid["nv"], "nhan")          # tu khai truoc
    r = gs.ghi_cong(kh["KhongTin"], uid["nv"], "nhan", may_tu_lam=True)
    ok("co bang chung sau -> 'nang_cap'", r == "nang_cap", r)
    with pool.connection() as conn:
        row = conn.execute(
            "select verify_status from crm.care_interactions where customer_id "
            "= %s and action_kind = 'nhan'", (kh["KhongTin"],)).fetchone()
    ok("ban tu khai duoc nang len da_xac_minh",
       row["verify_status"] == "da_xac_minh", str(dict(row)))

    print("== 5. SOI TIN — cua ±1 ngay, chua han thi CHO THEM ==")
    # Cong cua khach CoTin (hanh dong 'nhan') moi khai -> chua qua 72h
    with pool.connection() as conn:
        cong_moi = conn.execute(
            "select * from crm.care_interactions where customer_id = %s "
            "and action_kind = 'nhan'", (kh["CoTin"],)).fetchone()
    kq = gs.soi_mot(dict(cong_moi))
    ok("khach CO tin cua NV trong cua -> xac minh ngay",
       kq["ket_qua"] == "da_xac_minh", str(kq))
    ok("ly do noi ro may soi thay gi", "máy soi" in kq["ly_do"], kq["ly_do"])

    gs.ghi_cong(kh["GoiDien"], uid["nv"], "goi")
    kq2 = gs.soi_mot(dict(_cong(pool, kh["GoiDien"], uid["nv"], "goi")))
    ok("hanh dong GOI: khop cau bao da goi VIET TAT",
       kq2["ket_qua"] == "da_xac_minh", str(kq2))

    # Khach KhongTin: khai 'goi' hom nay, khong co tin nao -> CHUA qua han
    gs.ghi_cong(kh["KhongTin"], uid["nv"], "goi")
    kq3 = gs.soi_mot(dict(_cong(pool, kh["KhongTin"], uid["nv"], "goi")))
    ok("khong co bang chung nhung CHUA qua han -> cho_them, KHONG bac voi",
       kq3["ket_qua"] == "cho_them", str(kq3))

    # Day mocs khai lui 5 ngay -> qua han 72h
    with pool.connection() as conn:
        conn.execute(
            "update crm.care_interactions set action_at = %s where customer_id "
            "= %s and action_kind = 'goi'",
            (bay_gio() - timedelta(days=5), kh["KhongTin"]))
    kq4 = gs.soi_mot(dict(_cong(pool, kh["KhongTin"], uid["nv"], "goi")))
    ok("qua han ma van khong thay tin -> bac_bo", kq4["ket_qua"] == "bac_bo",
       str(kq4))
    ok("ly do bac noi ro qua bao lau + cua bao rong",
       "72 giờ" in kq4["ly_do"] and "±1 ngày" in kq4["ly_do"], kq4["ly_do"])

    print("== 6. Soi hang loat + duyet tay ==")
    kq = gs.soi_hang_loat()
    ok("soi hang loat chay duoc", kq["soi"] >= 1, str(kq))
    bac = [c for c in giam_sat_repo.bang_cong(trang_thai="bac_bo")
           if str(c["customer_name"] or "").startswith(DAU)]
    ok("co ban bi bac de vot tay", len(bac) >= 1, str(len(bac)))
    loi = ""
    try:
        gs.duyet_tay(int(bac[0]["id"]), True, "   ", nguoi=uid["tn"])
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("vot tay KHONG ghi ly do -> chan", "lý do" in loi, loi)
    v = gs.duyet_tay(int(bac[0]["id"]), True, "NV goi that, khach xac nhan",
                     nguoi=uid["tn"])
    ok("vot tay co ly do -> da_xac_minh", v["verify_status"] == "da_xac_minh",
       str(v)[:120])
    ok("ghi ro la duyet tay", "duyệt tay" in (v["verify_reason"] or ""),
       v["verify_reason"])

    print("== 7. THU VIEN kich ban — chep tay, KHONG gui gi ==")
    kb = gs.luu_kich_ban(kind="sale", situation="Kiem thu",
                         title=f"{DAU}Cau mau",
                         body="Dạ chị ơi, bên em có ưu đãi tháng này ạ",
                         tags="kiem-thu")
    ok("luu duoc kich ban", bool(kb["id"]), str(kb)[:100])
    ok("tu sinh ban BO DAU de tim kiem",
       kb["body_nodiacritic"] == "da chi oi ben em co uu dai thang nay a",
       kb["body_nodiacritic"])
    rows, _ = giam_sat_repo.kich_ban(tu_khoa="uu dai thang")
    ok("go KHONG DAU van tim ra cau CO DAU",
       any(int(r["id"]) == int(kb["id"]) for r in rows), str(len(rows)))
    chep = gs.chep(int(kb["id"]))
    ok("chep tra ve noi dung", "ưu đãi" in chep["body"], chep["body"][:40])
    ok("chep KHONG gui gi cho ai", chep["da_gui"] is False, str(chep["da_gui"]))
    kb2 = giam_sat_repo.get_kich_ban(int(kb["id"]))
    ok("chep chi dem luot dung", int(kb2["use_count"]) == 1,
       str(kb2["use_count"]))

    print("== 8. Goi y theo tu khoa (khong AI) ==")
    gy = gs.goi_y("sao dat the em oi")
    ok("do duoc tu khoa 'dat'", len(gy) >= 1, str(gy)[:150])
    ok("goi y GIAI THICH duoc vi sao", gy and "vi_sao" in gy[0], str(gy[:1]))
    ok("tin khong co tu khoa -> khong goi y bua",
       gs.goi_y("hom nay troi dep qua") == [])
    ok("tin rong -> khong goi y", gs.goi_y("") == [])

    print("== 9. Kho data — thu hoi BAT BUOC ly do + khoa chia lai ==")
    tq = gs.tong_quan_kho()
    ok("bat duoc khach chua co nguoi phu trach",
       any(int(r["id"]) == kh["ChuaChia"] for r in tq["chua_chia"]),
       str(tq["so_chua_chia"]))
    loi = ""
    try:
        gs.thu_hoi(kh["CoTin"], uid["nv"], "", nguoi=uid["tn"])
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("thu hoi KHONG ly do -> chan", "lý do" in loi, loi)
    gs.thu_hoi(kh["CoTin"], uid["nv"], "NV nghi viec", nguoi=uid["tn"])
    ok("thu hoi xong thi khoa chia lai cho CHINH nguoi do",
       giam_sat_repo.dang_bi_khoa(kh["CoTin"], uid["nv"]))
    loi = ""
    try:
        gs.chia(kh["CoTin"], uid["nv"], nguoi=uid["tn"])
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("chia lai cho nguoi vua bi thu hoi -> chan", "khoá" in loi, loi)
    gs.chia(kh["CoTin"], uid["tn"], nguoi=uid["tn"])
    ok("chia cho NGUOI KHAC thi duoc",
       not giam_sat_repo.dang_bi_khoa(kh["CoTin"], uid["tn"]))
    nk = giam_sat_repo.nhat_ky_chia(customer_id=kh["CoTin"])
    ok("nhat ky ghi ca thu hoi lan chia lai", len(nk) >= 2, str(len(nk)))
    ok("thu hoi luu nguyen ly do",
       any("nghi viec" in (r["reason"] or "") for r in nk), str(nk[:1]))

    print("== 10. Man hinh + phan quyen ==")
    web = TestClient(app)

    def dang_nhap(u: str) -> None:
        r = web.post("/dang-nhap", data={"username": u, "password": MK},
                     follow_redirects=False)
        assert r.status_code == 303, r.status_code

    dang_nhap(f"{DAU}nv")
    r = web.get("/crm/kich-ban")
    ok("ai cung mo duoc Thu vien kich ban", r.status_code == 200,
       str(r.status_code))
    ok("man BAO RO la chep tay, khong gui gi",
       "không gửi gì cho khách" in r.text)
    ok("hien cau mau seed", "Trả lời khách chê đắt" in r.text)
    r = web.post("/crm/kich-ban/goi-y", data={"tin": "sao dat the"})
    ok("goi y hien tren man", "Gợi ý cho tin vừa dán" in r.text)

    r = web.get("/crm/giam-sat")
    ok("Sale khong co audit.view -> 403 man Giam sat", r.status_code == 403,
       str(r.status_code))
    r = web.get("/crm/kho-data")
    ok("Sale khong co data.export -> 403 man Kho data", r.status_code == 403,
       str(r.status_code))

    dang_nhap(f"{DAU}admin")
    r = web.get("/crm/giam-sat")
    ok("Admin mo duoc man Giam sat", r.status_code == 200, str(r.status_code))
    ok("man giai thich cua soi + 3 kieu go",
       "cửa ±1 ngày" in r.text and "viết tắt" in r.text)
    ok("hien LY DO may bac ngay tren dong", "máy" in r.text)
    r = web.get("/crm/kho-data")
    ok("Admin mo duoc man Kho data", r.status_code == 200, str(r.status_code))
    ok("hien khoi khach chua chia + khach ket",
       "chưa có người phụ trách" in r.text and "KẸT không chia được" in r.text)
    ok("ghi ro nhom chua chia KHONG chay dong ho SLA",
       "không chạy đồng hồ SLA" in r.text)

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKET QUA: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


def _cong(pool, customer_id: int, user_id: int, hd: str) -> dict:
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.care_interactions where customer_id = %s "
            "and user_id = %s and action_kind = %s",
            (customer_id, user_id, hd)).fetchone()


if __name__ == "__main__":
    main()
