"""Nghiem thu C3 — CHIEN DICH 2 TANG + MAU TIN (port mau Kallet).

Kiem cac luat de hong nhat:

  1. CONG TAC GUI TIN mac dinh TAT -> chay dot la chay NHAP: khong tin nao roi
     he thong VA khach KHONG bi danh dau 'da gui' (bat that van gui du).
  2. HAI TANG: khach TRA LOI moi sinh viec tang 2 — va chi MOT viec du khach
     nhan bao nhieu cau.
  3. J5 — 1 khach khong nam 2 chien dich cung luc; DONG chien dich thi NHA
     khach ra de ho vao duoc chien dich khac.
  4. Xem truoc va nap that dung CHUNG mot bo loc.
  5. Mau tin: bien phai khai truoc; mau tu_do KHONG duoc danh dau gui ngoai cua.

Du lieu gia mang dau `__c3__`, don sach dau/cuoi. KHONG goi mang (cong tac tat
nen khong nhanh nao cham toi Pancake).

Chay:  python scripts/thu_c3_chien_dich.py
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import campaign_repo      # noqa: E402
from app.main import app                           # noqa: E402
from app.services import campaign_service          # noqa: E402

DAU = "__c3__"
MK = "C3-test-1234"
PAGE_GIA = "888000111000222"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    kh = f"(select id from crm.customers where full_name like '{DAU}%')"
    cd = f"(select id from crm.reactivation_campaigns where name like '{DAU}%')"
    conn.execute(f"delete from crm.reactivation_members where campaign_id in {cd}"
                 f" or customer_id in {kh}")
    conn.execute(f"delete from crm.reactivation_campaigns where name like '{DAU}%'")
    conn.execute(f"delete from crm.tasks where customer_id in {kh}")
    conn.execute(f"delete from crm.messages where conversation_id in "
                 f"(select id from crm.conversations where customer_id in {kh})")
    conn.execute(f"delete from crm.conversations where customer_id in {kh}")
    conn.execute(f"delete from crm.pages where external_page_id = '{PAGE_GIA}'")
    conn.execute(f"delete from crm.orders where customer_id in {kh}")
    conn.execute(f"delete from crm.customer_assignments where customer_id in {kh}")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.message_templates where code like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:  # noqa: PLR0915 — script nghiem thu
    pool = get_pg_pool()
    gio = datetime.now(timezone.utc)
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vai in (("mkt", "Marketing"), ("cskh", "CSKH"), ("sale", "Sale")):
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

        # 4 khach ngu qua 210 ngay + 1 khach moi mua (khong duoc vao tep)
        kh = {}
        for ten, ngay_ngu in (("A", 300), ("B", 320), ("C", 400), ("D", 250),
                              ("Moi", 10)):
            kh[ten] = conn.execute(
                "insert into crm.customers (full_name, primary_phone, status, "
                "last_delivered_at, total_spent) "
                "values (%s, %s, 'customer', %s, 5000000) returning id",
                (f"{DAU}Khach{ten}", f"09660011{ord(ten[0]) % 10}0",
                 gio - timedelta(days=ngay_ngu)),
            ).fetchone()["id"]
            conn.execute(
                "insert into crm.conversations (customer_id, page_id, "
                "external_conversation_id, last_message_at) "
                "values (%s, %s, %s, %s)",
                (kh[ten], page, f"{PAGE_GIA}_c3{ten}", gio))
            conn.execute(
                "insert into crm.customer_assignments (customer_id, user_id, "
                "assignment_type) values (%s, %s, 'cskh')", (kh[ten], uid["cskh"]))

    print("== 1. Cong tac gui tin mac dinh TAT ==")
    ok("gui_that() = False khi chua bat cong tac",
       campaign_service.gui_that() is False, str(campaign_service.gui_that()))

    print("== 2. Mau tin — chan sai truoc khi luu ==")
    loi = ""
    try:
        campaign_service.luu_mau_tin(code=f"{DAU}M1", name="x",
                                     body="Chao {{ten_khach}}", variables="")
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("bien dung ma khong khai -> chan", "chưa khai" in loi, loi)

    loi = ""
    try:
        campaign_service.luu_mau_tin(code=f"{DAU}M2", name="x", body="hi",
                                     kind="tu_do", meta_status="gui_ngoai_cua")
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("mau TU DO ma danh dau gui ngoai cua -> chan", "ngoài cửa" in loi, loi)

    mau = campaign_service.luu_mau_tin(
        code=f"{DAU}M1", name="Moi khach ngu quay lai",
        body="Chao {{ten_khach}}, ben em co uu dai thang nay a!",
        variables="ten_khach", nguoi=uid["mkt"])
    ok("luu duoc mau dung", bool(mau["id"]), str(mau)[:100])
    ok("ma luu VIET HOA", mau["code"] == f"{DAU}M1".upper(), mau["code"])
    thu = campaign_service.xem_thu(int(mau["id"]))
    ok("xem thu dien duoc bien", "Chị Lan" in thu, thu)
    ok("bien khong co gia tri thi GIU nguyen dau ngoac",
       "{{con_thieu}}" in campaign_service.dien_bien("x {{con_thieu}}", {}))

    print("== 3. Xem truoc va nap that dung CHUNG bo loc ==")
    loc = {"nhom": "ngu210"}
    truoc = campaign_service.xem_truoc(loc)
    ok("xem truoc bat duoc 4 khach ngu (khong dinh khach moi mua)",
       truoc >= 4, str(truoc))
    cd = campaign_service.tao(ten=f"{DAU}CD1", loc=loc,
                              template_id=int(mau["id"]), moi_dot=2,
                              nguoi=uid["mkt"])
    ok("nap dung bang so xem truoc", cd["so_khach"] == truoc,
       f'{cd["so_khach"]} vs {truoc}')
    cid = int(cd["id"])

    print("== 4. LUAT J5 — 1 khach khong 2 chien dich cung luc ==")
    truoc2 = campaign_service.xem_truoc(loc)
    ok("xem truoc lan 2 = 0 (khach da nam trong CD1)", truoc2 == 0, str(truoc2))
    cd2 = campaign_service.tao(ten=f"{DAU}CD2", loc=loc, nguoi=uid["mkt"])
    ok("chien dich 2 khong cuop duoc khach nao", cd2["so_khach"] == 0,
       str(cd2["so_khach"]))

    print("== 5. Chay dot o che do NHAP ==")
    loi = ""
    try:
        asyncio.run(campaign_service.chay_dot(cid, 2))
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("chien dich con NHAP -> chan chay dot", "Đang chạy" in loi, loi)

    campaign_service.doi_trang_thai(cid, "running", nguoi=uid["mkt"])
    kq = asyncio.run(campaign_service.chay_dot(cid, 2))
    ok("chay nhap: chon dung 2 khach (tran moi dot)", kq["chon"] == 2, str(kq))
    ok("chay nhap: KHONG gui tin nao", kq["da_gui"] == 0, str(kq))
    ok("bao ro dang o che do nhap", kq["gui_that"] is False, str(kq))
    with pool.connection() as conn:
        n = conn.execute("select count(*) as n from crm.reactivation_members "
                         "where campaign_id = %s and sent_at is not null",
                         (cid,)).fetchone()["n"]
    ok("chay nhap KHONG 'tieu' khach nao (sent_at van rong)", n == 0, str(n))
    kq2 = asyncio.run(campaign_service.chay_dot(cid, 2))
    ok("chay nhap lan 2 van chon dung 2 khach do", kq2["chon"] == 2, str(kq2))

    print("== 6. TANG 2 — khach tra loi moi sinh viec ==")
    tv = campaign_repo.thanh_vien_dang_cham(kh["A"])
    ok("khach A dang nam trong chien dich", tv and int(tv["campaign_id"]) == cid,
       str(dict(tv) if tv else None))
    m1 = campaign_service.hook_khach_tra_loi(kh["A"])
    ok("khach tra loi -> danh dau responded", m1 and m1["responded_at"],
       str(dict(m1) if m1 else None))
    ok("sinh viec tang 2 gan cho nguoi phu trach", m1 and m1["task_id"],
       str(m1["task_id"] if m1 else None))
    m2 = campaign_service.hook_khach_tra_loi(kh["A"])
    ok("khach nhan them cau nua -> KHONG sinh viec thu 2", m2 is None, str(m2))
    with pool.connection() as conn:
        so_viec = conn.execute(
            "select count(*) as n from crm.tasks where customer_id = %s",
            (kh["A"],)).fetchone()["n"]
    ok("dung 1 viec trong DB", so_viec == 1, str(so_viec))

    ok("khach khong nam chien dich nao -> hook khong lam gi",
       campaign_service.hook_khach_tra_loi(kh["Moi"]) is None)

    print("== 7. So sanh chien dich (R6) ==")
    ss = {c["name"]: c for c in campaign_service.so_sanh()}
    c1 = ss.get(f"{DAU}CD1")
    ok("dem duoc so khach", c1 and int(c1["so_khach"]) == truoc, str(c1)[:120])
    ok("dem duoc so tra loi", c1 and int(c1["da_tra_loi"]) == 1,
       str(c1["da_tra_loi"] if c1 else None))
    ok("chua gui that -> ty le tra loi = None (khong bia 0%)",
       c1 and c1["tra_loi_pct"] is None, str(c1["tra_loi_pct"] if c1 else None))

    print("== 8. Dong chien dich thi NHA khach ==")
    kq = campaign_service.doi_trang_thai(cid, "finished", nguoi=uid["mkt"])
    ok("dong chien dich nha khach chua chot", kq["nha_khach"] >= 3,
       str(kq["nha_khach"]))
    truoc3 = campaign_service.xem_truoc(loc)
    ok("khach duoc nha ra thi vao duoc chien dich khac", truoc3 >= 3,
       str(truoc3))
    with pool.connection() as conn:
        r = conn.execute("select status from crm.reactivation_members "
                         "where campaign_id = %s and customer_id = %s",
                         (cid, kh["A"])).fetchone()
    ok("khach DA TRA LOI khong bi nha (viec tang 2 con do)",
       r["status"] == "responded", str(dict(r)))

    print("== 9. Man hinh + phan quyen ==")
    web = TestClient(app)

    def dang_nhap(u: str) -> None:
        r = web.post("/dang-nhap", data={"username": u, "password": MK},
                     follow_redirects=False)
        assert r.status_code == 303, r.status_code

    dang_nhap(f"{DAU}mkt")
    r = web.get("/crm/chien-dich")
    ok("Marketing mo duoc man Chien dich", r.status_code == 200,
       str(r.status_code))
    ok("BAO RO dang o che do nhap", "chế độ NHÁP" in r.text)
    ok("ve dai 2 tang", "TẦNG 1" in r.text and "TẦNG 2" in r.text)
    ok("bang co chien dich vua tao", f"{DAU}CD1" in r.text)

    r = web.get("/crm/chien-dich?xem=1&nhom=ngu210")
    ok("xem truoc tra so khach ngay tren man",
       "khớp" in r.text and "khách</b>" in r.text)

    r = web.get(f"/crm/chien-dich/{cid}")
    ok("man chi tiet mo 200", r.status_code == 200, str(r.status_code))
    ok("tach ro 2 tang", "TẦNG 1 — máy gửi" in r.text
       and "TẦNG 2 — khách đã trả lời" in r.text)

    r = web.get("/crm/mau-tin")
    ok("man Mau tin mo 200", r.status_code == 200, str(r.status_code))
    ok("canh bao tu_do vs meta_duyet", "cửa 24h" in r.text)
    ok("hien mau vua tao", f"{DAU}M1".upper() in r.text)

    dang_nhap(f"{DAU}sale")
    for duong in ("/crm/chien-dich", "/crm/mau-tin"):
        r = web.get(duong)
        ok(f"Sale khong co campaign.manage -> 403 {duong}",
           r.status_code == 403, str(r.status_code))

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKET QUA: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
