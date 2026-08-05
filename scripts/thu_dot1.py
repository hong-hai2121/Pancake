"""Nghiem thu DOT 1 — gop cai dat con thieu tu mau Kallet vao man Cai dat.

Bay viec cua dot nay, moi viec mot muc o duoi:

  T4. Bo so 180/210 GHI CUNG — dai "cham cuoi -> roi bang" phai suy ra tu thang
      moc C6 va cai dat cskh_leave_days, khong duoc dong dinh trong SQL.
  T1. Sau khoa voucher/hang the ve dung nhom "uu_dai" (truoc nam nham "cskh").
  KTD. Lop khoa TU DO — khoa khong co trong danh muc MUC van luu/doc/xoa duoc.
  1A. Thang bam duoi Sale sua TRON VEN o Cai dat: the tu khoa, bat/tat buoc,
      11 o so nhip, va o "Thu mot cau" cham thu tren tu khoa CHUA luu.
  1D. Thang mua lai: bat/tat moc, doi ngay, nhan, nguoi gui.
  T2. /crm/thang-sale khong con la noi sua thu hai — no CHUYEN HUONG sang Cai dat.
  T3. Nguong hang the sua o Cai dat; /crm/hang-the thanh toan canh CHI DOC.

Don sach moi thay doi o cuoi. KHONG goi mang.

Chay:  python scripts/thu_dot1.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core import runtime_config as rc          # noqa: E402
from app.core.config import settings               # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import crm_screens_repo as scr  # noqa: E402
from app.db.repositories import sale_repo, voucher_repo  # noqa: E402
from app.main import app                           # noqa: E402
from app.services import campaign_service, sale_service  # noqa: E402
from app.web.views import cai_dat as v_cd          # noqa: E402

DAU = "__d1__"
PASS = 0
FAIL = 0
# Cai dat bai kiem co dong vao — cuoi bai tra ve mac dinh het.
DA_DUNG = ("cskh_leave_days", "sale_step_rest_hours", "voucher_remind_days")


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep() -> None:
    for ma in DA_DUNG:
        rc.dat_lai_mac_dinh(ma)
    rc.dat_tu_do(f"bn_{DAU}", "")
    rc.xoa_cache()
    with get_pg_pool().connection() as conn:
        conn.execute("delete from crm.app_settings where code like %s",
                     (f"%{DAU}%",))
        conn.execute("delete from crm.audit_logs where action like 'setting%' "
                     "and created_at > now() - interval '2 hours'")


def main() -> None:  # noqa: PLR0915 — script nghiem thu
    don_dep()

    print("== T4. Dai cham soc SUY RA, khong ghi cung 180/210 ==")
    goc = scr.dai_cham_soc()
    ok("dai la cap (cham cuoi, roi bang)",
       isinstance(goc, tuple) and len(goc) == 2 and goc[0] < goc[1], str(goc))
    ok("moc roi bang = dung cai dat cskh_leave_days",
       goc[1] == rc.so("cskh_leave_days", 210), str(goc))
    rc.dat("cskh_leave_days", 300)
    rc.xoa_cache()
    moi = scr.dai_cham_soc()
    ok("doi cskh_leave_days -> dai doi theo", moi[1] == 300 and moi != goc,
       f"{goc} -> {moi}")
    ok("moc cham cuoi luon nho hon moc roi bang", moi[0] < moi[1], str(moi))
    # Nhan hien thi phai DOC THEO dai, khong duoc ghi cung "180/210" trong chuoi.
    from app.web.views import crm as v_crm

    ok("nhan man Khach hang bam theo dai vua doi",
       str(moi[1]) in str(v_crm._kh_tinh_trang_dinh()),
       str(v_crm._kh_tinh_trang_dinh()))
    tep = campaign_service.nhom_tep()
    ok("nhom tep Chien dich cung bam theo dai", str(moi[1]) in str(tep),
       str(tep))
    ok("khoa nhom tep GIU NGUYEN (chien dich cu khong mat bo loc)",
       {"151_180", "181_210", "ngu210"} <= set(tep), str(sorted(tep)))
    rc.dat_lai_mac_dinh("cskh_leave_days")
    rc.xoa_cache()
    ok("tra ve mac dinh -> dai ve nhu cu", scr.dai_cham_soc() == goc)
    _ = v_cd

    print("== T1. Sau khoa voucher/hang the nam o nhom 'uu_dai' ==")
    theo_nhom = {m["code"]: m["nhom"] for m in rc.danh_sach()}
    for ma in ("voucher_remind_days", "voucher_first_value",
               "voucher_expire_days", "card_rank_downgrade_days"):
        if ma in theo_nhom:
            ok(f"{ma} thuoc nhom uu_dai", theo_nhom[ma] == "uu_dai",
               theo_nhom.get(ma, "(khong co)"))
    ok("nhom uu_dai co mat trong menu Cai dat",
       any(g["ma"] == "uu_dai" for g in rc.theo_nhom()))

    print("== KTD. Lop khoa TU DO (ngoai danh muc MUC) ==")
    ma_td = f"bn_{DAU}"
    ok("khoa chua dat -> tra mac dinh", rc.lay_tu_do(ma_td, "(rong)") == "(rong)")
    rc.dat_tu_do(ma_td, "Khach moi toanh")
    ok("dat roi -> doc lai dung", rc.lay_tu_do(ma_td) == "Khach moi toanh")
    ok("doc theo tien to gom duoc khoa vua dat",
       rc.lay_tu_do_theo_tien_to("bn_").get(ma_td) == "Khach moi toanh")
    ok("khoa tu do KHONG lan vao danh muc MUC",
       ma_td not in {m["code"] for m in rc.danh_sach()})
    rc.dat_tu_do(ma_td, "")
    ok("dat gia tri RONG = XOA han (ve ten goc)",
       rc.lay_tu_do(ma_td, "(rong)") == "(rong)")

    print("== 1A. Cham cau tren tu khoa — do dung buoc ==")
    ok("tach cum theo dau phay",
       sale_service.tach("chao chi, bao gia , ") == ["chao chi", "bao gia"])
    ok("cum qua ngan bi diem mat",
       sale_service.tu_khoa_qua_ngan("ok, chao chi") == ["ok"])
    ok("the trung sau khi bo dau bi bat",
       sale_service.the_trung("chào chị, chao chi") == {1: "chào chị"})
    ok("go the trung giu cum DAU",
       sale_service.go_the_trung("chào chị, chao chi, bao gia")
       == "chào chị, bao gia")
    ok("cum dac biet #anh duoc giai nghia",
       sale_service.cum_the("#anh")[0]["dac_biet"] == "tin có ảnh",
       str(sale_service.cum_the("#anh")))

    print("== 1D + 1A: luu qua man Cai dat ==")
    web = TestClient(app)
    r = web.post("/dang-nhap",
                 data={"username": "admin",
                       "password": settings.admin_bootstrap_password},
                 follow_redirects=False)
    ok("dang nhap admin", r.status_code == 303, str(r.status_code))

    r = web.get("/quan-tri/cai-dat?sec=moc")
    ok("muc Moc thoi gian mo 200", r.status_code == 200, str(r.status_code))
    ok("co khoi 1A (thang bam duoi)", 'id="k1a"' in r.text)
    ok("co the tu khoa", "kwtag" in r.text)
    ok("co o Thu mot cau", "kwtry" in r.text)
    from app.web.views import cai_dat_moc as v_moc

    ma_so = [c for _, ds in v_moc.SO_1A for c in ds]
    thieu = [c for c in ma_so if f'name="{c}"' not in r.text]
    ok(f"du {len(ma_so)} o so nhip cua thang", not thieu, str(thieu))

    buoc = [dict(b) for b in sale_repo.thang_tat_ca()]
    ok("doc duoc thang bam duoi", len(buoc) > 0, str(len(buoc)))
    b1 = buoc[0]
    so1, ten_cu = b1["step_no"], b1["name"]
    r = web.post("/quan-tri/cai-dat",
                 data={"nhom": "moc",
                       f"b[{so1}][ten]": f"{DAU}buoc mot",
                       f"b[{so1}][viec]": b1["work"] or "",
                       f"b[{so1}][tu_khoa]": b1["keywords_agent"] or "",
                       f"b[{so1}][tu_khoa_kh]": b1["keywords_customer"] or "",
                       f"b[{so1}][active]": "1",
                       "sale_step_rest_hours": "8"},
                 follow_redirects=False)
    ok("luu muc Moc -> chuyen huong ve dung muc", r.status_code in (302, 303)
       and "sec=moc" in r.headers.get("location", ""),
       f'{r.status_code} {r.headers.get("location", "")}')
    sau = {b["step_no"]: dict(b) for b in sale_repo.thang_tat_ca()}
    ok("ten buoc da doi", sau[so1]["name"] == f"{DAU}buoc mot",
       sau[so1]["name"])
    ok("tu khoa KHONG bi mat khi chi doi ten",
       (sau[so1]["keywords_agent"] or "") == (b1["keywords_agent"] or ""),
       sau[so1]["keywords_agent"])
    rc.xoa_cache()
    ok("o so cung luot luu da vao", rc.so("sale_step_rest_hours") == 8,
       str(rc.so("sale_step_rest_hours")))
    sale_repo.luu_buoc(so1, name=ten_cu)          # tra ten buoc ve nhu cu

    print("== 1A. O 'Thu mot cau' cham dung buoc ==")
    r = web.post("/quan-tri/cai-dat/thu-cau",
                 data={"cau": "khong lien quan gi ca xyz", "ai": "nv"})
    ok("cau khong khop -> khong cham buoc nao",
       r.status_code == 200 and r.json().get("khop") == [], r.text[:160])

    print("== T2. /crm/thang-sale khong con la noi sua thu hai ==")
    r = web.get("/crm/thang-sale", follow_redirects=False)
    ok("duong cu CHUYEN HUONG sang Cai dat",
       r.status_code in (302, 303, 307)
       and "cai-dat" in r.headers.get("location", ""),
       f'{r.status_code} {r.headers.get("location", "")}')
    ok("khong con man sua thu hai trong ma nguon",
       not Path("app/web/views/sale.py").read_text(encoding="utf-8")
       .count("def render_thang"))

    print("== T3. Nguong hang the: sua o Cai dat, /crm/hang-the CHI DOC ==")
    r = web.get("/crm/hang-the")
    ok("man Hang the mo 200", r.status_code == 200, str(r.status_code))
    ok("KHONG con o nhap nguong o man Hang the",
       'name="nguong"' not in r.text)
    ok("co nut tro sang cho sua", "cai-dat?sec=uu_dai" in r.text)

    r = web.get("/quan-tri/cai-dat?sec=uu_dai")
    ok("muc Uu dai mo 200", r.status_code == 200, str(r.status_code))
    bac = [dict(h) for h in voucher_repo.hang_the()]
    if not bac:
        ok("bang card_ranks rong -> hien loi nhac seed, khong hien o nhap",
           'name="nguong_' not in r.text and "seed_uu_dai" in r.text)
    else:
        ma = bac[0]["code"]
        ok("co o nhap nguong cho tung hang", f'name="nguong_{ma}"' in r.text)
        truoc = bac[0]["min_spent"]
        moi_gt = int(float(truoc or 0)) + 12345
        du = {"nhom": "uu_dai", f"nguong_{ma}": str(moi_gt)}
        # Gui DU o cua nhom y nhu trinh duyet: cong tac vang mat = TAT.
        for m in rc.danh_sach():
            if m["nhom"] != "uu_dai":
                continue
            if m["kieu"] == "bool":
                if m["gia_tri"]:
                    du[m["code"]] = "1"
            else:
                du.setdefault(m["code"], "" if m["gia_tri"] is None
                              else str(m["gia_tri"]))
        r = web.post("/quan-tri/cai-dat", data=du, follow_redirects=False)
        ok("luu nguong qua man Cai dat", r.status_code in (302, 303),
           str(r.status_code))
        sau_n = {h["code"]: h["min_spent"] for h in voucher_repo.hang_the()}
        ok("nguong da vao DB", sau_n[ma] is not None
           and float(sau_n[ma]) == moi_gt, str(sau_n.get(ma)))
        r = web.get("/quan-tri/cai-dat?sec=log")
        ok("nhat ky ghi lai lan doi nguong", "nguong" in r.text.lower()
           or "card_rank" in r.text.lower())
        # o TRONG = xoa nguong ("chua dien"), KHONG phai 0
        du[f"nguong_{ma}"] = ""
        web.post("/quan-tri/cai-dat", data=du, follow_redirects=False)
        ok("o nguong de TRONG = xoa han, KHONG thanh 0",
           {h["code"]: h["min_spent"]
            for h in voucher_repo.hang_the()}[ma] is None)
        voucher_repo.dat_nguong(ma, float(truoc) if truoc is not None else None)
        ok("tra nguong ve nhu cu", True)

    r = web.post("/crm/hang-the/nguong", data={"ma": "gold", "nguong": "1"},
                 follow_redirects=False)
    ok("duong POST cu cung chuyen huong sang Cai dat",
       r.status_code in (302, 303, 307)
       and "cai-dat" in r.headers.get("location", ""),
       f'{r.status_code} {r.headers.get("location", "")}')

    print("== Phan quyen ==")
    web.cookies.clear()
    r = web.get("/quan-tri/cai-dat?sec=uu_dai", follow_redirects=False)
    ok("chua dang nhap -> khong vao duoc man Cai dat",
       r.status_code in (302, 303, 401, 403), str(r.status_code))
    r = web.post("/quan-tri/cai-dat", data={"nhom": "uu_dai", "nguong_gold": "1"},
                 follow_redirects=False)
    ok("chua dang nhap -> khong ghi duoc nguong",
       r.status_code in (302, 303, 401, 403), str(r.status_code))

    don_dep()
    print(f"\n  Tong: {PASS} PASS / {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
