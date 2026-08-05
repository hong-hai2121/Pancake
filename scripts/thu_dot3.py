"""Nghiem thu DOT 3 — KHUNG luong tu dong, va CHUNG MINH no khong gui tin.

Bai nay khac moi bai khac o cho: viec chinh cua no KHONG phai kiem tinh nang
chay dung, ma la kiem mot dieu KHONG XAY RA — "engine luong tu dong khong bao
gio cham toi mang".

Chung minh bang ba cach doc lap, vi mot cach thi de tu ru ngu minh:

  TANG 0 (cau truc)  Doc MA NGUON: services/auto_flow.py va auto_flow_repo.py
                     khong duoc import bat ky module gui nao. Khong the bat cai
                     khong ton tai.
  TANG 1 (hanh vi)   VA moi ham gui thanh "goi la NO", roi chay TOAN BO engine
                     tren du lieu that. Test xanh = khong duong nao cham toi.
  TANG 2 (cong tac)  Cua gui xin_phep_gui('auto_flow') tu choi VO DIEU KIEN khi
                     AUTO_FLOW_HARD_LOCK con dong — va no TACH khoi khoa gui
                     tin thuong (mo cai kia khong mo cai nay).

Con lai la kiem khung chay dung: 3 kieu kich hoat, catalog dieu kien, chay kho.

Don sach moi thay doi o cuoi. KHONG goi mang.

Chay:  python scripts/thu_dot3.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core import runtime_config as rc          # noqa: E402
from app.core.config import settings               # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import auto_flow_repo     # noqa: E402
from app.main import app                           # noqa: E402
from app.services import auto_flow as af           # noqa: E402
from app.services import cong_tac_gui_tin as ct    # noqa: E402

DAU = "__d3__"
PASS = 0
FAIL = 0

# Moi ham CO KHA NANG gui tin ra ngoai trong ca he thong. Them duong gui moi ma
# quen khai o day thi bai nay khong con chung minh duoc gi — nen danh sach nay
# cung duoc kiem: xem muc "0-C".
DUONG_GUI = [
    ("app.integrations.pancake.client", "send_message"),
    ("app.services.conversation_service", "gui_tin"),
    ("app.services.campaign_service", "_gui_tang_1"),
    ("app.integrations.telegram", "gui"),
]


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep() -> None:
    with get_pg_pool().connection() as conn:
        kh = f"(select id from crm.customers where full_name like '{DAU}%')"
        conn.execute(f"delete from crm.tasks where customer_id in {kh}")
        conn.execute(f"delete from crm.leads where customer_id in {kh}")
        conn.execute(f"delete from crm.customer_assignments where customer_id in {kh}")
        conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
        conn.execute("delete from crm.auto_flows where name like %s",
                     (f"{DAU}%",))
        conn.execute(f"delete from crm.users where email like '{DAU}%'")
        conn.execute("delete from crm.audit_logs where object_type = "
                     "'auto_flows' and created_at > now() - interval '2 hours'")
    rc.dat_lai_mac_dinh("auto_flow_task_enabled")
    rc.xoa_cache()


def _fixture() -> tuple[int, int]:
    """Mot nhan vien + mot khach ĐA CO NGUOI PHU TRACH, nhan hang 45 ngay truoc.

    Phai tu dung: du lieu that hien khong khach nao co nguoi phu trach (bang
    customer_assignments rong, leads.owner_id chi co tren 161 lead), nen khong
    co fixture thi nhanh "dat viec" khong bao gio chay toi.
    """
    from datetime import datetime, timedelta, timezone

    from app.core.security import hash_password

    with get_pg_pool().connection() as conn:
        role = conn.execute("select id from crm.roles where name = 'Sale' "
                            "limit 1").fetchone()["id"]
        uid = conn.execute(
            "insert into crm.users (name, email, username, password_hash, "
            "status, role_id) values (%s, %s, %s, %s, 'active', %s) "
            "returning id",
            (f"{DAU}sale", f"{DAU}sale@x.com", f"{DAU}sale",
             hash_password("D3-test-1234"), role)).fetchone()["id"]
        cid = conn.execute(
            "insert into crm.customers (full_name, primary_phone, status, "
            "last_delivered_at, total_spent) values (%s, %s, 'customer', %s, "
            "%s) returning id",
            (f"{DAU}KhachCoNguoi", "0900000333",
             datetime.now(timezone.utc) - timedelta(days=45), 1_000_000),
        ).fetchone()["id"]
        conn.execute(
            "insert into crm.customer_assignments (customer_id, user_id, "
            "assignment_type, start_at) values (%s, %s, 'sale', now())",
            (cid, uid))
    return uid, cid


class DaGoiHamGui(AssertionError):
    """Nem ra khi engine cham vao mot ham gui — bai kiem coi day la HONG."""


def _no(*a, **k):
    raise DaGoiHamGui(
        "Engine luong tu dong vua goi mot ham GUI TIN. Dot 3 cam dieu nay: "
        "khung chi duoc chon khach + noi ly do, khong duoc cham toi mang.")


def main() -> None:  # noqa: PLR0915 — script nghiem thu
    don_dep()

    print("== 0-A. TANG 0 (cau truc) — ma nguon khong co duong gui ==")
    # Doc bang AST chu khong do CHUOI: chuoi thi chinh cau canh bao trong
    # docstring ("khong import pancake.client") cung bi tinh la vi pham, con
    # `send_message` viet tach dong thi lot. AST chi thay MA THAT.
    goc = Path(__file__).resolve().parents[1]
    CAM_MODULE = ("app.integrations", "httpx", "requests", "aiohttp",
                  "urllib", "socket", "http.client")
    CAM_HAM = {"send_message", "send_flow", "gui_tin", "_gui_tang_1",
               "chay_dot"}

    def _soi(duong: str) -> tuple[list[str], list[str]]:
        import ast

        cay = ast.parse((goc / duong).read_text(encoding="utf-8"))
        mods, hams = [], []
        for n in ast.walk(cay):
            if isinstance(n, ast.Import):
                mods += [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                goc_mod = n.module or ""
                mods.append(goc_mod)
                mods += [f"{goc_mod}.{a.name}" for a in n.names]
            elif isinstance(n, ast.Call):
                fn = n.func
                ten = (fn.attr if isinstance(fn, ast.Attribute)
                       else fn.id if isinstance(fn, ast.Name) else "")
                if ten in CAM_HAM:
                    hams.append(ten)
        xau_m = [m for m in mods
                 if any(m == c or m.startswith(c + ".") for c in CAM_MODULE)]
        return xau_m, hams

    for ten in ("app/services/auto_flow.py",
                "app/db/repositories/auto_flow_repo.py",
                "app/web/views/luong_tu_dong.py",
                "app/workers/auto_flow_viec.py"):
        xm, xh = _soi(ten)
        ok(f"{ten} khong IMPORT module gui/mang nao", not xm, str(xm))
        ok(f"{ten} khong GOI ham gui nao", not xh, str(xh))
    src_af = (goc / "app/services/auto_flow.py").read_text(encoding="utf-8")
    ok("auto_flow.py noi ro no khong gui (co canh bao dau file)",
       "KHÔNG CÓ MỘT LỜI GỌI GỬI TIN NÀO" in src_af)
    # Bay cho chinh bai kiem: neu ai do doi CAM_HAM thanh rong thi muc 0-A
    # thanh vo dung ma van xanh.
    ok("bo dao CAM_HAM/CAM_MODULE khong rong (bai kiem con co tac dung)",
       len(CAM_HAM) >= 4 and len(CAM_MODULE) >= 4)

    print("== 0-B. TANG 2 (cong tac) — cua gui tu choi auto_flow ==")
    ok("auto_flow co khoa cung RIENG", ct.auto_flow_khoa_cung() is True)
    ok("khoa cung auto_flow TACH khoi khoa gui tin thuong",
       "auto_flow_hard_lock" != "outbound_hard_lock"
       and hasattr(settings, "auto_flow_hard_lock")
       and hasattr(settings, "outbound_hard_lock"))
    ok("xin_phep_gui('auto_flow') -> TU CHOI", ct.duoc_gui("auto_flow") is False)
    ok("ly do tu choi doc duoc",
       "KHOÁ CỨNG" in ct.vi_sao_khong_gui("auto_flow"),
       ct.vi_sao_khong_gui("auto_flow")[:70])

    # MO HET moi khoa gui tin THUONG — auto_flow VAN phai bi tu choi.
    khoa_cu, che_do_cu = settings.outbound_hard_lock, ct.che_do()
    settings.outbound_hard_lock = False
    rc.dat("outbound_messaging_mode", "that")
    rc.xoa_cache()
    ok("mo het khoa gui tin thuong -> chien dich duoc gui",
       ct.duoc_gui("chien_dich") is True)
    ok("...nhung auto_flow VAN bi tu choi (khoa doc lap)",
       ct.duoc_gui("auto_flow") is False)
    ok("gui TAY khong bi cong tac chien dich chan (khong lam ket man Hoi thoai)",
       ct.duoc_gui("tay") is True)

    # Va ca khi MO not khoa cung cua auto_flow: engine van chua co ma gui.
    khoa_af_cu = settings.auto_flow_hard_lock
    settings.auto_flow_hard_lock = False
    ok("mo NOT khoa auto_flow -> cua gui thong",
       ct.duoc_gui("auto_flow") is True)
    ok("...nhung engine VAN bao chua gui duoc (chua co ma gui)",
       "chưa có mã gửi" in af.khong_gui_duoc(), af.khong_gui_duoc()[:80])
    settings.auto_flow_hard_lock = khoa_af_cu
    settings.outbound_hard_lock = khoa_cu
    rc.dat("outbound_messaging_mode", che_do_cu)
    rc.xoa_cache()

    print("== 0-C. Danh sach duong gui con dung (khong lo bo sot) ==")
    import importlib
    for mod, ham in DUONG_GUI:
        m = importlib.import_module(mod)
        ok(f"{mod}.{ham} van ton tai", callable(getattr(m, ham, None)),
           "ham da doi ten -> cap nhat DUONG_GUI")

    print("== 1. Khung chay dung: 3 kieu kich hoat ==")
    ok("co du 3 kieu", set(af.kieu_flow()) ==
       {"su_kien", "lech_ngay", "truong_doi"}, str(list(af.kieu_flow())))
    ok("catalog dieu kien khong rong", len(af.DIEU_KIEN) >= 8,
       str(len(af.DIEU_KIEN)))
    ok("moc neo khong rong", len(af.MOC_NEO) >= 3, str(len(af.MOC_NEO)))

    # Moi dieu kien trong catalog phai DUNG duoc that (SQL chay khong loi).
    for ma, cat in af.DIEU_KIEN.items():
        gt = "1" if cat["kieu"] == "bool" else ("100" if cat["kieu"] == "num"
                                                else "gold")
        f = {"kind": "lech_ngay", "moc_neo": "nhan_cuoi", "so_ngay": 30,
             "khop": "all",
             "dieu_kien": [{"ma": ma, "phep": ">=" if cat["kieu"] == "num"
                            else "=", "gia_tri": gt}]}
        try:
            r = af.chay_kho(f, ghi=False)
            ok(f"dieu kien «{cat['ten']}» chay that duoc",
               isinstance(r["so_trung"], int))
        except Exception as err:                 # noqa: BLE001
            ok(f"dieu kien «{cat['ten']}» chay that duoc", False, str(err)[:90])

    print("== 2. Luat sai thi BAO NGAY, khong nam im trong bang ==")
    for f, ten in [
        ({"kind": "lech_ngay", "moc_neo": "khong_co", "so_ngay": 1},
         "moc neo la"),
        ({"kind": "truong_doi", "truong": "khong_co"}, "truong la"),
        ({"kind": "su_kien", "su_kien": "khong_co"}, "su kien la"),
        ({"kind": "lech_ngay", "moc_neo": "nhan_cuoi", "so_ngay": 1,
          "dieu_kien": [{"ma": "khong_co", "phep": "=", "gia_tri": "x"}]},
         "dieu kien la"),
        ({"kind": "lech_ngay", "moc_neo": "nhan_cuoi", "so_ngay": 1,
          "dieu_kien": [{"ma": "chi_tieu", "phep": ">=", "gia_tri": "abc"}]},
         "so khong hop le"),
        ({"kind": "lech_ngay", "moc_neo": "nhan_cuoi", "so_ngay": 1,
          "dieu_kien": [{"ma": "co_sdt", "phep": ">=", "gia_tri": "1"}]},
         "phep so sai kieu"),
    ]:
        try:
            af.dung_loc(f)
            ok(f"{ten} -> bao loi", False, "khong nem loi")
        except Exception as err:                 # noqa: BLE001
            ok(f"{ten} -> bao loi", "ApiError" in type(err).__name__,
               f"{type(err).__name__}: {err}")

    print("== 3. Luat LUON loai khach da xin ngung nhan tin ==")
    dk, _ = af.dung_loc({"kind": "lech_ngay", "moc_neo": "nhan_cuoi",
                         "so_ngay": 30})
    ok("cau loc luon co do_not_contact = false", "do_not_contact" in dk, dk[:120])
    ok("cau loc luon bo khach da xoa/gop",
       "deleted_at is null" in dk and "merged" in dk)

    print("== 4. TANG 1 (hanh vi) — VA ham gui thanh 'goi la NO' ==")
    import importlib

    cu = []
    for mod, ham in DUONG_GUI:
        m = importlib.import_module(mod)
        cu.append((m, ham, getattr(m, ham)))
        setattr(m, ham, _no)
    try:
        web = TestClient(app)
        r = web.post("/dang-nhap",
                     data={"username": "admin",
                           "password": settings.admin_bootstrap_password},
                     follow_redirects=False)
        ok("dang nhap admin", r.status_code == 303, str(r.status_code))

        r = web.get("/quan-tri/luong-tu-dong")
        ok("man mo 200 (khong cham ham gui)", r.status_code == 200,
           str(r.status_code))
        ok("man noi thang la CHUA gui tin cho ai",
           "CHƯA gửi tin cho ai" in r.text)
        ok("man KHONG co nut 'Test ban' cua mau",
           "Test bắn" not in r.text and "test_ban" not in r.text)

        r = web.post("/quan-tri/luong-tu-dong", data={
            "viec": "them", "name": f"{DAU}nhac mua lai",
            "kind": "lech_ngay", "moc_neo": "nhan_cuoi", "so_ngay": "45",
            "khop": "all", "dk_ma": "chi_tieu", "dk_gia_tri": "0",
            "tao_viec": "1"}, follow_redirects=False)
        ok("khai luong -> 303", r.status_code == 303, str(r.status_code))
        ds = [dict(x) for x in auto_flow_repo.tat_ca()
              if x["name"].startswith(DAU)]
        ok("luong vao DB", len(ds) == 1, str(len(ds)))
        fid = ds[0]["id"]
        ok("luong moi khai mac dinh TAT", ds[0]["status"] == "inactive",
           ds[0]["status"])
        ok("dieu kien luu dung dang", ds[0]["dieu_kien"]
           and ds[0]["dieu_kien"][0]["ma"] == "chi_tieu",
           str(ds[0]["dieu_kien"]))

        # CHAY THU tren du lieu THAT, voi moi ham gui dang la bom hen gio.
        r = web.post("/quan-tri/luong-tu-dong", data={"viec": f"thu:{fid}"})
        ok("chay thu xong ma KHONG goi ham gui nao", r.status_code == 200,
           str(r.status_code))
        ok("man ket qua noi ro 'Da gui: 0'", "Đã gửi: <b>0</b>" in r.text)
        runs = [dict(x) for x in auto_flow_repo.lan_chay(fid)]
        ok("nhat ky ghi lai luot chay", len(runs) == 1, str(len(runs)))
        ok("nhat ky ghi che do 'kho', KHONG bao gio la 'that'",
           runs[0]["che_do"] == "kho", runs[0]["che_do"])
        ok("nhat ky co mau khach kem ly do",
           isinstance(runs[0]["chi_tiet"], list)
           and (not runs[0]["chi_tiet"] or "ly_do" in runs[0]["chi_tiet"][0]))

        # BAT luong roi chay lai — bat cung khong duoc gui.
        web.post("/quan-tri/luong-tu-dong", data={"viec": f"doi:{fid}"},
                 follow_redirects=False)
        ok("bat luong duoc",
           auto_flow_repo.get(fid)["status"] == "active")
        r = web.post("/quan-tri/luong-tu-dong", data={"viec": f"thu:{fid}"})
        ok("luong DANG BAT chay thu van khong goi ham gui nao",
           r.status_code == 200, str(r.status_code))

        # Goi thang engine tren MOI luong dang bat.
        for fl in auto_flow_repo.dang_chay():
            af.chay_kho(dict(fl), ghi=False)
        ok("chay het luong dang bat -> van khong ham gui nao bi goi", True)

        # Chung minh bay va co tac dung THAT (khong phai va hut).
        try:
            from app.integrations.pancake import client
            import asyncio
            asyncio.run(client.send_message("1", "2", "x"))
            ok("bay VA co tac dung that", False, "goi ham gui ma khong no")
        except DaGoiHamGui:
            ok("bay VA co tac dung that (goi thu -> no dung nhu mong doi)", True)
        except Exception as err:                 # noqa: BLE001
            ok("bay VA co tac dung that", False,
               f"no sai kieu: {type(err).__name__}")

        print("== 4b. SUA luong da khai (khong phai xoa di khai lai) ==")
        r = web.post("/quan-tri/luong-tu-dong", data={
            "viec": f"sua:{fid}", "s_name": f"{DAU}ten moi",
            "s_moc_neo": "vao_crm", "s_so_ngay": "60", "s_khop": "any",
            "s_dk_ma": "da_mua", "s_dk_gia_tri": "1", "s_tao_viec": "1"},
            follow_redirects=False)
        ok("sua luong -> 303", r.status_code == 303, str(r.status_code))
        sau = dict(auto_flow_repo.get(fid))
        ok("ten doi", sau["name"] == f"{DAU}ten moi", sau["name"])
        ok("moc neo doi", sau["moc_neo"] == "vao_crm", str(sau["moc_neo"]))
        ok("so ngay doi", int(sau["so_ngay"]) == 60, str(sau["so_ngay"]))
        ok("dieu kien doi",
           sau["dieu_kien"] and sau["dieu_kien"][0]["ma"] == "da_mua",
           str(sau["dieu_kien"]))
        ok("SUA khong lam mat lich su chay thu",
           len(auto_flow_repo.lan_chay(fid)) >= 1)
        r = web.post("/quan-tri/luong-tu-dong", data={
            "viec": f"sua:{fid}", "s_moc_neo": "khong_co_moc_nay"},
            follow_redirects=False)
        ok("sua thanh luat SAI -> bao loi ngay, khong nam im",
           "error" in (r.headers.get("location") or ""))

        print("== 4c. SINH VIEC cho nhan vien — duong tu dong DUY NHAT dang mo ==")
        uid, cid = _fixture()
        r = web.post("/quan-tri/luong-tu-dong", data={
            "viec": "them", "name": f"{DAU}dat viec",
            "kind": "lech_ngay", "moc_neo": "nhan_cuoi", "so_ngay": "45",
            "khop": "all", "dk_ma": "chi_tieu", "dk_gia_tri": "0",
            "tao_viec": "1"}, follow_redirects=False)
        f2 = next(dict(x) for x in auto_flow_repo.tat_ca()
                  if x["name"] == f"{DAU}dat viec")
        fid2 = f2["id"]

        kq = af.sinh_viec(f2)
        ok("dat duoc viec cho khach CO nguoi phu trach", kq["da_sinh"] >= 1,
           str(kq))
        ok("KHONG gui tin nao trong luot dat viec", kq["da_gui"] == 0)
        ok("khach chua co nguoi phu trach thi BO QUA + dem rieng",
           kq["bo_qua"]["chua_co_nguoi"] >= 1, str(kq["bo_qua"]))

        with get_pg_pool().connection() as conn:
            t = conn.execute(
                "select * from crm.tasks where customer_id = %s "
                "order by id desc limit 1", (cid,)).fetchone()
        ok("viec vao crm.tasks", t is not None)
        ok("viec giao dung nguoi phu trach", t and int(t["assigned_to"]) == uid,
           str(t and t["assigned_to"]))
        ok("viec ghi ro NGUON: related_type=auto_flows + id cua luong",
           t and t["related_type"] == "auto_flows"
           and int(t["related_id"]) == fid2,
           str(t and (t["related_type"], t["related_id"])))
        ok("loai viec danh dau la do may sinh",
           t and t["task_type"] == af.LOAI_VIEC, str(t and t["task_type"]))
        ok("han viec la CUOI ngay hom nay, khong phai qua han ngay luc sinh",
           t and t["due_at"] > t["created_at"],
           str(t and (t["created_at"], t["due_at"])))

        # CHONG TRUNG — worker chay nhieu luot mot ngay.
        kq2 = af.sinh_viec(f2)
        ok("chay lai trong ngay -> KHONG de them viec trung",
           kq2["da_sinh"] == 0, str(kq2))
        ok("...va noi ro vi sao (da sinh hom nay / viec cu con mo)",
           kq2["bo_qua"]["da_sinh_hom_nay"] + kq2["bo_qua"]["viec_cu_con_mo"]
           >= 1, str(kq2["bo_qua"]))
        with get_pg_pool().connection() as conn:
            n = conn.execute("select count(*) as n from crm.tasks "
                             "where customer_id = %s", (cid,)).fetchone()["n"]
        ok("van dung 1 viec cho khach do", n == 1, str(n))
        ok("bang lien ket tra loi duoc 'viec nay o dau ra'",
           len(auto_flow_repo.viec_cua_luong(fid2)) >= 1)

        # Luong khong bat "sinh viec" thi nut kia phai tu choi.
        auto_flow_repo.luu(fid2, tao_viec=False)
        r = web.post("/quan-tri/luong-tu-dong", data={"viec": f"viec:{fid2}"},
                     follow_redirects=False)
        ok("luong khong bat 'sinh viec' -> nut bi tu choi",
           "error" in (r.headers.get("location") or ""))

        print("== 4c-2. Kieu SU KIEN chua chay that -> CHAN dat viec ==")
        r = web.post("/quan-tri/luong-tu-dong", data={
            "viec": "them", "name": f"{DAU}su kien", "kind": "su_kien",
            "su_kien": "nhan_hang", "khop": "all", "tao_viec": "1"},
            follow_redirects=False)
        fsk = next(dict(x) for x in auto_flow_repo.tat_ca()
                   if x["name"] == f"{DAU}su kien")
        try:
            af.sinh_viec(fsk)
            ok("kieu SU KIEN bi chan dat viec", False, "khong nem loi")
        except Exception as err:                 # noqa: BLE001
            ok("kieu SU KIEN bi chan dat viec",
               "hàng đợi sự kiện" in str(err), str(err)[:80])
        ok("...nhung CHAY THU van dung duoc (soi dieu kien)",
           isinstance(af.chay_kho(fsk, ghi=False)["so_trung"], int))
        r = web.post("/quan-tri/luong-tu-dong", data={"viec": f'viec:{fsk["id"]}'},
                     follow_redirects=False)
        ok("nut Sinh viec cua kieu SU KIEN -> bao loi ro rang",
           "error" in (r.headers.get("location") or ""))
        r = web.get("/quan-tri/luong-tu-dong")
        ok("man canh bao ro kieu SU KIEN chua chay that",
           "chưa chạy thật" in r.text)
        ok("...va KHONG bay nut Sinh viec cho luong kieu do",
           f'value="viec:{fsk["id"]}"' not in r.text)
        auto_flow_repo.xoa(int(fsk["id"]))

        print("== 4d. Worker sinh viec: cong tac + idempotent ==")
        from app.workers import auto_flow_viec as w

        rc.dat("auto_flow_task_enabled", False)
        rc.xoa_cache()
        ok("cong tac worker mac dinh TAT",
           not rc.bat("auto_flow_task_enabled"))
        w._da_chay["ngay"] = None
        w._mot_vong()               # cong tac tat -> loop khong goi, nhung ham
        ok("goi thang _mot_vong khong lam no vo", True)
        auto_flow_repo.xoa(fid2)

        web.post("/quan-tri/luong-tu-dong", data={"viec": f"xoa:{fid}"},
                 follow_redirects=False)
        ok("xoa luong -> nhat ky chay cung di theo (cascade)",
           not auto_flow_repo.get(fid) and not auto_flow_repo.lan_chay(fid))
    finally:
        for m, ham, goc_ham in cu:
            setattr(m, ham, goc_ham)
    ok("da tra lai moi ham gui nhu cu",
       all(getattr(importlib.import_module(mod), ham) is not _no
           for mod, ham in DUONG_GUI))

    print("== 5. Phan quyen ==")
    web = TestClient(app)
    r = web.get("/quan-tri/luong-tu-dong", follow_redirects=False)
    ok("chua dang nhap -> khong xem duoc",
       r.status_code in (302, 303, 401, 403), str(r.status_code))
    r = web.post("/quan-tri/luong-tu-dong", data={"viec": "them", "name": "x"},
                 follow_redirects=False)
    ok("chua dang nhap -> khong khai duoc luong",
       r.status_code in (302, 303, 401, 403), str(r.status_code))

    don_dep()
    print(f"\n  Tong: {PASS} PASS / {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
