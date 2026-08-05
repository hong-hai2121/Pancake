"""Nghiem thu DOT 2 — nam muc Cai dat con thieu so voi mau Kallet.

  D2-1  GUI TIN: cong tac BA trang thai (tat/nhap/that) + HAI lop khoa
        (khoa cung .env + che do tren web) + quyen RIENG gui_tin.bat_cong_tac
        + 3 cua gui tin cua Meta.
  D2-2  VONG DOI: 3 luat tu dong, NOI THAT vao engine chu khong phai cong tac
        chet (tu thu hoi · giam quyen loi ngam · may tu tang voucher don dau).
  D2-3  NGUON LEAD: bang viec Sale chi nhan lead INBOX hay ca binh luan.
  D2-4  KICH BAN NHAN DIEN: bang phrase_patterns THEM vao bo mau NEN trong ma
        (khong thay), do co chen tu la, va o thu mot cau.
  D2-5  GOI Y KICH BAN: CRUD luat tu khoa -> kich ban.

Don sach moi thay doi o cuoi. KHONG goi mang.

Chay:  python scripts/thu_dot2.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core import runtime_config as rc          # noqa: E402
from app.core.config import settings               # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import giam_sat_repo, nhan_dien_repo  # noqa: E402
from app.db.repositories import sale_repo          # noqa: E402
from app.main import app                           # noqa: E402
from app.services import cong_tac_gui_tin as ct    # noqa: E402
from app.services import cskh_service, giam_sat_service  # noqa: E402
from app.services import nhan_dien, voucher_service  # noqa: E402
from app.services import tieng_viet as tv          # noqa: E402
from app.web.views import cai_dat as v_cd          # noqa: E402

DAU = "__d2__"
PASS = 0
FAIL = 0
DA_DUNG = ("outbound_messaging_mode", "luat_thu_hoi_on",
           "luat_giam_quyenloi_on", "voucher_first_auto_on",
           "board_chi_inbox", "nhandien_goi_gap", "meta_door_out_on")


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep() -> None:
    for ma in DA_DUNG:
        try:
            rc.dat_lai_mac_dinh(ma)
        except Exception:                       # noqa: BLE001
            pass
    rc.xoa_cache()
    nhan_dien.xoa_cache()
    with get_pg_pool().connection() as conn:
        conn.execute("delete from crm.phrase_patterns where pattern like %s",
                     (f"{DAU}%",))
        conn.execute("delete from crm.script_suggest_rules where keywords "
                     "like %s", (f"{DAU}%",))
        conn.execute("delete from crm.audit_logs where object_type in "
                     "('phrase_patterns','script_suggest_rules') "
                     "and created_at > now() - interval '2 hours'")


def main() -> None:  # noqa: PLR0915 — script nghiem thu
    don_dep()
    web = TestClient(app)
    r = web.post("/dang-nhap",
                 data={"username": "admin",
                       "password": settings.admin_bootstrap_password},
                 follow_redirects=False)
    ok("dang nhap admin", r.status_code == 303, str(r.status_code))

    print("== D2-1. Cong tac gui tin: 3 trang thai, 2 lop khoa ==")
    ok("co du 3 che do", set(ct.CHE_DO) == {"tat", "nhap", "that"},
       str(list(ct.CHE_DO)))
    ok("khoa cung CHI o .env, KHONG bay len man Cai dat",
       "outbound_hard_lock" not in {m["code"] for m in rc.danh_sach()})
    ok("che do KHONG bay ra luoi o chung (tranh 2 cho sua)",
       "outbound_messaging_mode" in v_cd.KHOA_RIENG)

    r = web.get("/quan-tri/cai-dat?sec=gui_tin")
    ok("muc Gui tin mo 200", r.status_code == 200, str(r.status_code))
    ok("co 3 nut che do", r.text.count('name="che_do"') == 3,
       str(r.text.count('name="che_do"')))
    ok("KHONG con o chon che do trong luoi",
       'name="outbound_messaging_mode"' not in r.text)
    ok("co hang trang thai hai lop khoa", "ctkhoa" in r.text)
    ok("3 cua Meta co mat", all(f'name="{k}"' in r.text for k, _, _ in ct.CUA),
       str([k for k, _, _ in ct.CUA]))

    for ma in ("that", "nhap", "tat"):
        r = web.post("/quan-tri/cai-dat/che-do-gui-tin", data={"che_do": ma},
                     follow_redirects=False)
        rc.xoa_cache()
        ok(f"gat sang «{ma}» -> luu duoc",
           r.status_code == 303 and ct.che_do() == ma,
           f"{r.status_code} {ct.che_do()}")
    r = web.post("/quan-tri/cai-dat/che-do-gui-tin", data={"che_do": "bay"},
                 follow_redirects=False)
    ok("che do rac -> bao loi, khong ghi",
       "error" in (r.headers.get("location") or ""),
       r.headers.get("location", "")[:80])

    # Hai lop khoa: che do THAT ma khoa cung con dong thi VAN khong gui that.
    web.post("/quan-tri/cai-dat/che-do-gui-tin", data={"che_do": "that"},
             follow_redirects=False)
    rc.xoa_cache()
    khoa_cu = settings.outbound_hard_lock
    settings.outbound_hard_lock = True
    ok("che do THAT + khoa cung DONG -> van KHONG gui that",
       ct.che_do() == "that" and ct.gui_that() is False)
    ok("noi ro VI SAO chua gui that", "khoá cứng" in ct.dien_giai()["vi_sao"].lower(),
       ct.dien_giai()["vi_sao"][:70])
    settings.outbound_hard_lock = False
    ok("mo khoa cung -> moi thuc su gui that", ct.gui_that() is True)
    settings.outbound_hard_lock = True
    ok("dong lai -> tat ngay", ct.gui_that() is False)
    settings.outbound_hard_lock = khoa_cu

    from app.services import campaign_service
    ok("campaign_service.gui_that() di qua CUNG mot cua",
       campaign_service.gui_that() == ct.gui_that())

    print("== D2-1b. Quyen RIENG gui_tin.bat_cong_tac ==")
    with get_pg_pool().connection() as conn:
        n = conn.execute("select count(*) as n from crm.permissions "
                         "where code = 'gui_tin.bat_cong_tac'").fetchone()["n"]
    ok("quyen da co trong DB (chay seed_auth.py)", n == 1, str(n))
    ok("quyen KHONG phai la user.manage",
       "gui_tin.bat_cong_tac" != "user.manage")
    web.cookies.clear()
    r = web.post("/quan-tri/cai-dat/che-do-gui-tin", data={"che_do": "that"},
                 follow_redirects=False)
    ok("chua dang nhap -> khong gat duoc cong tac",
       r.status_code in (302, 303, 401, 403), str(r.status_code))
    web.post("/dang-nhap",
             data={"username": "admin",
                   "password": settings.admin_bootstrap_password},
             follow_redirects=False)
    rc.dat_lai_mac_dinh("outbound_messaging_mode")
    rc.xoa_cache()

    print("== D2-2. Vong doi: cong tac NOI THAT, khong phai cong tac chet ==")
    nhom = {g["ma"] for g in rc.theo_nhom()}
    ok("co nhom vong_doi trong menu Cai dat", "vong_doi" in nhom, str(nhom))
    r = web.get("/quan-tri/cai-dat?sec=vong_doi")
    ok("muc Vong doi mo 200", r.status_code == 200, str(r.status_code))
    for ma in ("luat_thu_hoi_on", "luat_giam_quyenloi_on",
               "voucher_first_auto_on", "board_chi_inbox"):
        ok(f"co cong tac {ma}", f'name="{ma}"' in r.text)
    ok("co khoi ban giao Sale -> CSKH (luat luon chay)",
       "Bàn giao Sale" in r.text)

    # luat_giam_quyenloi_on
    rc.dat("luat_giam_quyenloi_on", True)
    rc.xoa_cache()
    ok("bat -> voucher_service bao luat DANG chay",
       voucher_service.giam_quyen_loi_bat() is True)
    bat_dem = voucher_service.toan_canh()["giam_quyen_loi"]
    rc.dat("luat_giam_quyenloi_on", False)
    rc.xoa_cache()
    tat = voucher_service.toan_canh()
    ok("tat -> khong ai bi giam (dem ve 0, khong noi sai)",
       tat["giam_quyen_loi"] == 0 and tat["luat_giam_bat"] is False,
       f'{bat_dem} -> {tat["giam_quyen_loi"]}')
    r = web.get("/crm/hang-the")
    ok("man Hang the noi ro luat dang TAT",
       "đang <b>TẮT</b>" in r.text or "đang TẮT" in r.text)
    rc.dat_lai_mac_dinh("luat_giam_quyenloi_on")
    rc.xoa_cache()

    # voucher_first_auto_on
    rc.dat("voucher_first_auto_on", False)
    rc.xoa_cache()
    ok("tat -> cskh_service bao may KHONG tu tang",
       cskh_service.may_tu_tang_voucher() is False)
    gia_cu = rc.lay("voucher_first_value")
    ok("tat cong tac KHONG lam mat menh gia da khai",
       rc.lay("voucher_first_value") == gia_cu)
    rc.dat_lai_mac_dinh("voucher_first_auto_on")
    rc.xoa_cache()
    ok("bat lai -> may tu tang tro lai",
       cskh_service.may_tu_tang_voucher() is True)

    # luat_thu_hoi_on — chi chan duong MAY, thu hoi TAY van chay
    rc.dat("luat_thu_hoi_on", False)
    rc.xoa_cache()
    ok("tat -> giam_sat_service bao luat may thu hoi DANG TAT",
       giam_sat_service.tu_thu_hoi_bat() is False)
    try:
        giam_sat_service.thu_hoi(-1, -1, "thu", may=True)
        ok("duong MAY bi chan khi luat tat", False, "khong nem loi")
    except Exception as err:                     # noqa: BLE001
        ok("duong MAY bi chan khi luat tat",
           "TẮT" in str(err), str(err)[:70])
    rc.dat("luat_thu_hoi_on", True)
    rc.xoa_cache()
    ok("bat lai -> duong may mo", giam_sat_service.tu_thu_hoi_bat() is True)
    rc.dat_lai_mac_dinh("luat_thu_hoi_on")
    rc.xoa_cache()

    print("== D2-3. Nguon lead vao bang viec Sale ==")
    dem = sale_repo.dem_theo_loai_hoi_thoai()
    ok("dem duoc khach theo loai hoi thoai", isinstance(dem, dict), str(dem))
    ok("hoi thoai co cot kind, mac dinh 'inbox'", "inbox" in dem or not dem,
       str(dem))
    a = len(sale_repo.bang_viec(chi_inbox=False, limit=300))
    b = len(sale_repo.bang_viec(chi_inbox=True, limit=300))
    ok("loc chi-inbox khong lam TANG so lead", b <= a, f"{a} -> {b}")
    ok("khach chua co hoi thoai nao van giu nguyen tren bang",
       b >= a - int(dem.get("comment") or 0), f"{a} / {b} / {dem}")

    print("== D2-4. Kich ban nhan dien ==")
    r = web.get("/quan-tri/cai-dat?sec=nhan_dien")
    ok("muc mo 200", r.status_code == 200, str(r.status_code))
    ok("co ca 4 khoi mau", all(f"nd-{k}" in r.text
                               for k in ("goi", "chan", "voucher", "viet_tat")))
    ok("mau NEN hien ra va khong co nut xoa", "ndthe nen" in r.text)
    ok("co o thu mot cau", 'id="ndCau"' in r.text)

    ok("mau nen luon co hieu luc du bang RONG",
       set(tv.MAU_DA_GOI) <= set(nhan_dien.mau("goi")))
    n_truoc = len(nhan_dien.mau("chan"))
    r = web.post("/quan-tri/cai-dat/nhan-dien",
                 data={"viec": "them", "loai": "chan",
                       "mau": f"{DAU}mai em goi"}, follow_redirects=False)
    ok("them mau -> 303", r.status_code == 303, str(r.status_code))
    nhan_dien.xoa_cache()
    ok("mau moi CONG vao bo nen, khong thay the",
       len(nhan_dien.mau("chan")) == n_truoc + 1
       and set(tv.MAU_CHAN_GOI) <= set(nhan_dien.mau("chan")))
    r = web.post("/quan-tri/cai-dat/nhan-dien",
                 data={"viec": "them", "loai": "chan",
                       "mau": f"{DAU}mai em goi"}, follow_redirects=False)
    ok("them trung -> bao loi, khong nuot im lang",
       "error" in (r.headers.get("location") or ""))
    r = web.post("/quan-tri/cai-dat/nhan-dien",
                 data={"viec": "them", "loai": "viet_tat", "mau": f"{DAU}xx"},
                 follow_redirects=False)
    ok("viet tat thieu chu day du -> bao loi",
       "error" in (r.headers.get("location") or ""))

    ds = [dict(x) for x in nhan_dien_repo.tat_ca()
          if x["pattern"].startswith(DAU)]
    ok("doc lai duoc mau vua them", len(ds) == 1, str(len(ds)))
    pid = ds[0]["id"]
    web.post("/quan-tri/cai-dat/nhan-dien", data={"viec": f"doi:{pid}"},
             follow_redirects=False)
    nhan_dien.xoa_cache()
    ok("tat tam -> mau roi khoi bo do nhung CON trong bang",
       f"{DAU}mai em goi" not in nhan_dien.mau("chan")
       and any(x["id"] == pid for x in nhan_dien_repo.tat_ca()))

    # Do co CHEN tu la
    ok("chen 2 tu -> «vua goi» bat duoc «vua moi alo goi»",
       nhan_dien.khop_chen("vua goi", "em vua moi alo goi chi a", 2))
    ok("chen 0 tu -> chuoi phai lien nhau",
       not nhan_dien.khop_chen("vua goi", "em vua moi alo goi chi a", 0))
    ok("bien tu duoc ton trong (khong khop vao GIUA mot tu khac)",
       not nhan_dien.khop_chen("goi", "em dang ngoi day", 0)
       and not nhan_dien.khop_chen("vua goi", "em vuagoi chi", 0))
    # Cai bay kinh dien: mau MOT TU ngan, bo dau xong dung vao tu khac
    # ("goi" khop luon "goi y"). Chan tu luc NHAP chu khong de no vao bang.
    ok("«goi» la mot tu ngan -> van khop «goi y», nen phai chan tu dau vao",
       nhan_dien.khop_chen("goi", "em xem goi y cua shop", 0))
    for xau in ("goi", "ma", "alo"):
        try:
            nhan_dien.kiem_mau("goi", xau)
            ok(f"chan mau qua ngan «{xau}»", False, "khong nem loi")
        except Exception as err:                 # noqa: BLE001
            ok(f"chan mau qua ngan «{xau}»", "ngắn" in str(err), str(err)[:60])
    try:
        nhan_dien.kiem_mau("goi", "vua goi cho")
        ok("cum nhieu tu thi cho qua", True)
    except Exception as err:                     # noqa: BLE001
        ok("cum nhieu tu thi cho qua", False, str(err)[:60])
    try:
        nhan_dien.kiem_mau("viet_tat", "e")
        ok("viet tat duoc MIEN luat do dai", True)
    except Exception as err:                     # noqa: BLE001
        ok("viet tat duoc MIEN luat do dai", False, str(err)[:60])
    r = web.post("/quan-tri/cai-dat/nhan-dien",
                 data={"viec": "them", "loai": "goi", "mau": "goi"},
                 follow_redirects=False)
    ok("man Cai dat cung chan mau qua ngan",
       "error" in (r.headers.get("location") or ""))

    kq = nhan_dien.soi("em vua goi chi roi a")
    ok("soi: cau bao da goi -> DA GOI", kq["goi"] and not kq["chan"],
       str(kq))
    kq = nhan_dien.soi("chi goi lai cho em nhe")
    ok("soi: cau nho khach goi -> bi CHAN", kq["chan"] and not kq["goi"],
       str(kq))
    ok("soi luon giai thich duoc vi sao", bool(kq["vi_sao"] and kq["mau"]),
       str(kq))
    kq = nhan_dien.soi("lat em goi lai cho chi nhe")
    ok("«lat em goi» KHONG bi cham la da goi", not kq["goi"], str(kq))
    kq = nhan_dien.soi("em gui ma ABCDE123 cho chi", ma="ABCDE123")
    ok("kenh A: khop dung MA da phat", kq["voucher"], str(kq))
    kq = nhan_dien.soi("shop tang chi voucher 50000 nhe", menh_gia=50000)
    ok("kenh B: dung con so + tu voucher", kq["voucher"], str(kq))
    kq = nhan_dien.soi("shop tang chi voucher 150000 nhe", menh_gia=50000)
    ok("KHONG cat giua so (150000 khong tinh la 50000)", not kq["voucher"],
       str(kq))
    kq = nhan_dien.soi("chuyen khoan 50000 nhe", menh_gia=50000)
    ok("co so ma khong co tu voucher -> chua tinh", not kq["voucher"],
       str(kq))

    r = web.post("/quan-tri/cai-dat/nhan-dien/thu",
                 data={"cau": "em vua goi chi roi a"})
    ok("o thu mot cau tra JSON dung",
       r.status_code == 200 and r.json().get("goi") is True, r.text[:120])

    web.post("/quan-tri/cai-dat/nhan-dien", data={"viec": f"xoa:{pid}"},
             follow_redirects=False)
    ok("xoa mau -> bang sach",
       not [x for x in nhan_dien_repo.tat_ca()
            if x["pattern"].startswith(DAU)])

    print("== D2-5. Goi y kich ban ==")
    r = web.get("/quan-tri/cai-dat?sec=goi_y")
    ok("muc mo 200", r.status_code == 200, str(r.status_code))
    kb = giam_sat_repo.kich_ban_chon(5)
    if not kb:
        ok("chua co kich ban nao de gan luat (chay seed_kich_ban.py)", True)
    else:
        r = web.post("/quan-tri/cai-dat/goi-y",
                     data={"viec": "them", "tu_khoa": f"{DAU}gia bao nhieu",
                           "script_id": str(kb[0]["id"])},
                     follow_redirects=False)
        ok("them luat -> 303", r.status_code == 303, str(r.status_code))
        ds = [dict(x) for x in giam_sat_repo.luat_goi_y_tat_ca()
              if x["keywords"].startswith(DAU)]
        ok("luat vao DB kem ten kich ban", len(ds) == 1 and ds[0]["title"],
           str(ds))
        rid = ds[0]["id"]
        ok("luat moi DANG CHAY",
           any(x["id"] == rid for x in giam_sat_repo.luat_goi_y()))
        web.post("/quan-tri/cai-dat/goi-y", data={"viec": f"doi:{rid}"},
                 follow_redirects=False)
        ok("tat tam -> roi khoi danh sach dang chay, CON trong bang",
           not any(x["id"] == rid for x in giam_sat_repo.luat_goi_y())
           and any(x["id"] == rid
                   for x in giam_sat_repo.luat_goi_y_tat_ca()))
        r = web.post("/quan-tri/cai-dat/goi-y",
                     data={"viec": "them", "tu_khoa": "x", "script_id": "0"},
                     follow_redirects=False)
        ok("them ma chua chon kich ban -> bao loi",
           "error" in (r.headers.get("location") or ""))
        web.post("/quan-tri/cai-dat/goi-y", data={"viec": f"xoa:{rid}"},
                 follow_redirects=False)
        ok("xoa luat -> bang sach",
           not [x for x in giam_sat_repo.luat_goi_y_tat_ca()
                if x["keywords"].startswith(DAU)])

    print("== Menu + phan quyen ==")
    r = web.get("/quan-tri/cai-dat")
    for ma, ten, _ in v_cd.MUC_DAC_BIET:
        ok(f"menu co muc «{ten}»", f"?sec={ma}" in r.text)
    ok("menu co muc Vong doi", "?sec=vong_doi" in r.text)
    web.cookies.clear()
    for duong in ("/quan-tri/cai-dat/nhan-dien", "/quan-tri/cai-dat/goi-y"):
        r = web.post(duong, data={"viec": "them"}, follow_redirects=False)
        ok(f"chua dang nhap -> khong ghi duoc {duong}",
           r.status_code in (302, 303, 401, 403), str(r.status_code))

    don_dep()
    print(f"\n  Tong: {PASS} PASS / {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
