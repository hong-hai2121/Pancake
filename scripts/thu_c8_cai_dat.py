"""Nghiem thu C8 — MAN CAI DAT (port bo cuc tu mau Kallet cai-dat.php).

Kiem cac diem mau chot lai:

  1. Menu muc con ben trai, hien MOT muc moi lan (?sec=) — khong do ca 56 cai
     dat cua 8 nhom vao mot trang dai.
  2. LUAT B3.3: o TRONG hien chu "chua dien" MAU CAM, KHONG phai so 0.
     (0 la gia tri da dat; trong nghia la chua ai dat va module tu tat.)
  3. Menu dem so o CHUA DIEN cua tung muc — khoi phai mo tung muc ra moi biet.
  4. Muc da co MAN RIENG thi menu tro thang sang, khong de o nhap thu hai.
  5. Luu xong quay lai DUNG muc dang mo (khong ban ve muc dau).
  6. NHAT KY CAU HINH: ai doi cai dat nao, tu gia tri nao sang gi.
  7. O CHU de trong VAN GHI DUOC (do la "chua dien" hop le); o SO de trong thi
     bo qua (xoa so di khong co nghia, muon ve mac dinh thi bam nut).
  8. Phan quyen: khong co user.manage -> 403.

Don sach moi thay doi o cuoi. KHONG goi mang.

Chay:  python scripts/thu_c8_cai_dat.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core import runtime_config as rc          # noqa: E402
from app.core.config import settings               # noqa: E402
from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.main import app                           # noqa: E402
from app.web.views import cai_dat as v             # noqa: E402

DAU = "__c8__"
MK = "C6-test-1234"
PASS = 0
FAIL = 0
# Cai dat bai kiem co dong vao — cuoi bai tra ve mac dinh het.
DA_DUNG = ("sale_stuck_days", "sale_ladder_start", "sale_scan_enabled",
           "sale_step_max_per_day", "sale_step_rest_hours",
           "sale_step_hour_from", "sale_step_hour_to", "sale_hot_hours",
           "sale_hot_max_steps", "sale_step_window", "sale_step_skip_max")


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    conn.execute(f"delete from crm.users where email like '{DAU}%'")
    conn.execute("delete from crm.audit_logs where action like 'setting%' "
                 "and created_at > now() - interval '2 hours'")


def main() -> None:  # noqa: PLR0915 — script nghiem thu
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        conn.execute(
            "insert into crm.users (name, email, username, password_hash, "
            "status, role_id) values (%s, %s, %s, %s, 'active', %s)",
            (f"{DAU}sale", f"{DAU}sale@x.com", f"{DAU}sale",
             hash_password(MK), role["Sale"]))
    for ma in DA_DUNG:
        rc.dat_lai_mac_dinh(ma)
    rc.xoa_cache()

    print("== 1. Luat B3.3 — 'chua dien' KHAC so 0 ==")
    ok("o CHU rong -> chua dien",
       v.chua_dien({"kieu": "str", "gia_tri": ""}) is True)
    ok("o CHU chi co khoang trang -> van chua dien",
       v.chua_dien({"kieu": "str", "gia_tri": "   "}) is True)
    ok("SO 0 -> DA DAT, khong phai chua dien",
       v.chua_dien({"kieu": "int", "gia_tri": 0}) is False)
    ok("None -> chua dien", v.chua_dien({"kieu": "int", "gia_tri": None}) is True)
    ok("cong tac bool khong bao gio 'chua dien'",
       v.chua_dien({"kieu": "bool", "gia_tri": False}) is False)

    web = TestClient(app)

    def dang_nhap(u: str, mk: str) -> int:
        r = web.post("/dang-nhap", data={"username": u, "password": mk},
                     follow_redirects=False)
        return r.status_code

    ok("dang nhap admin", dang_nhap("admin", settings.admin_bootstrap_password)
       == 303)

    print("== 2. Menu muc con — hien MOT muc moi lan ==")
    nhom = [g["ma"] for g in rc.theo_nhom()]
    ok("co it nhat 8 nhom cai dat", len(nhom) >= 8, str(nhom))
    r = web.get("/quan-tri/cai-dat")
    ok("man mo 200", r.status_code == 200, str(r.status_code))
    ok("co menu muc con ben trai", "cd-menu" in r.text)
    # Nhom trong NHOM_AN da duoc GOP tron ven vao muc "Moc thoi gian" (dot 1),
    # nen co mat trong danh muc ma KHONG co muc menu rieng — dung la vay.
    hien = [g for g in nhom if g not in v.NHOM_AN]
    ok("moi nhom (tru nhom da gop) co mot muc menu",
       all(f"?sec={g}" in r.text for g in hien), str(hien))
    ok("nhom da gop KHONG de muc menu thu hai",
       all(f"?sec={g}" not in r.text for g in v.NHOM_AN), str(sorted(v.NHOM_AN)))
    so_o_mac_dinh = r.text.count('class="cd-o')
    r2 = web.get(f"/quan-tri/cai-dat?sec={nhom[-1]}")
    so_o_khac = r2.text.count('class="cd-o')
    ok("doi ?sec= thi noi dung DOI (khong do het vao mot trang)",
       so_o_mac_dinh != so_o_khac or nhom[0] == nhom[-1],
       f"{so_o_mac_dinh} vs {so_o_khac}")
    tong_muc = sum(len(g["muc"]) for g in rc.theo_nhom())
    ok("mot muc hien IT hon tong so cai dat", so_o_mac_dinh < tong_muc,
       f"{so_o_mac_dinh} / {tong_muc}")
    r = web.get("/quan-tri/cai-dat?sec=linh_tinh_khong_co")
    ok("?sec= la thi lui ve muc dau, khong 404/500", r.status_code == 200,
       str(r.status_code))

    print("== 3. O chua dien to CAM + chuong dem tren menu ==")
    # sale_ladder_start mac dinh la chuoi RONG -> phai la o "chua dien"
    r = web.get("/quan-tri/cai-dat?sec=sale")
    ok("man Sale co o 'chua dien'", "chưa điền" in r.text)
    ok("o do duoc to lop rieng", "cd-o trong" in r.text)
    ok("input cung mang lop 'trong'", "cd-in" in r.text and "trong" in r.text)
    ok("menu co chuong dem so o chua dien", "cd-cam" in r.text)

    print("== 4. Muc co MAN RIENG tro thang sang ==")
    for ten, duong, _ in v.MAN_RIENG:
        ok(f"menu tro sang {duong}", duong in r.text, duong)
    ok("khong de o nhap token trong man Cai dat",
       "cố ý không" in r.text and "/quan-tri/tich-hop" in r.text)

    print("== 5. Luu xong quay lai DUNG muc ==")
    r = web.post("/quan-tri/cai-dat",
                 data={"nhom": "sale", "sale_stuck_days": "7",
                       "sale_scan_enabled": "on"}, follow_redirects=False)
    ok("luu tra 303", r.status_code == 303, str(r.status_code))
    vi_tri = r.headers.get("location", "")
    ok("quay lai dung ?sec=sale", "sec=sale" in vi_tri, vi_tri)
    ok("URL khong bi hong 2 dau ?", vi_tri.count("?") == 1, vi_tri)
    rc.xoa_cache()
    ok("gia tri da doi that", int(rc.so("sale_stuck_days")) == 7,
       str(rc.so("sale_stuck_days")))
    ok("cong tac gui kem KHONG bi tat oan",
       rc.bat("sale_scan_enabled") is True)

    print("== 6. O CHU de trong VAN ghi duoc ==")
    web.post("/quan-tri/cai-dat",
             data={"nhom": "sale", "sale_ladder_start": "2026-01-15",
                   "sale_scan_enabled": "on"}, follow_redirects=False)
    rc.xoa_cache()
    ok("dat duoc ngay bat thang", str(rc.lay("sale_ladder_start")) == "2026-01-15",
       str(rc.lay("sale_ladder_start")))
    web.post("/quan-tri/cai-dat",
             data={"nhom": "sale", "sale_ladder_start": "",
                   "sale_scan_enabled": "on"}, follow_redirects=False)
    rc.xoa_cache()
    ok("XOA ve rong duoc (o chu rong la gia tri hop le 'chua dien')",
       str(rc.lay("sale_ladder_start") or "") == "",
       repr(rc.lay("sale_ladder_start")))

    print("== 7. Nhat ky cau hinh ==")
    r = web.get("/quan-tri/cai-dat?sec=log")
    ok("mo duoc muc Nhat ky", r.status_code == 200, str(r.status_code))
    ok("ghi ten cai dat vua doi", "sale_stuck_days" in r.text)
    ok("ghi gia tri CU -> MOI", "→" in r.text)
    ok("ghi ten nguoi doi",
       "Quản trị" in r.text or "admin" in r.text)
    from app.db.repositories import audit_repo
    ds = audit_repo.nhat_ky_cai_dat()
    ok("repo tra ca old_value lan new_value",
       bool(ds) and "old_value" in ds[0] and "new_value" in ds[0],
       str(list(ds[0]) if ds else []))
    # Nguong hang the (T3) cung sua NGAY TREN man Cai dat nen phai co mat o day;
    # ngoai 3 hanh dong nay thi khong duoc lot them gi (nhat ky chung o man khac).
    ok("chi lay dung cac hanh dong cua man Cai dat",
       all(r["action"] in ("setting_update", "setting_reset",
                           "sua_nguong_hang_the") for r in ds),
       str(sorted({r["action"] for r in ds})))

    print("== 8. Tra ve mac dinh ==")
    r = web.post("/quan-tri/cai-dat",
                 data={"nhom": "sale", "mac_dinh": "1"},
                 follow_redirects=False)
    ok("tra ve mac dinh -> 303 dung muc", r.status_code == 303
       and "sec=sale" in r.headers.get("location", ""),
       r.headers.get("location", ""))
    rc.xoa_cache()
    ok("gia tri quay ve .env", int(rc.so("sale_stuck_days")) == 3,
       str(rc.so("sale_stuck_days")))
    r = web.get("/quan-tri/cai-dat?sec=log")
    ok("nhat ky ghi ca luot 'tra ve mac dinh'", "mặc định" in r.text)

    print("== 9. Phan quyen ==")
    ok("dang nhap Sale", dang_nhap(f"{DAU}sale", MK) == 303)
    r = web.get("/quan-tri/cai-dat")
    ok("Sale khong co user.manage -> 403", r.status_code == 403,
       str(r.status_code))
    r = web.post("/quan-tri/cai-dat", data={"nhom": "sale"},
                 follow_redirects=False)
    ok("Sale khong luu duoc cai dat -> 403", r.status_code == 403,
       str(r.status_code))

    # --- don dep: tra MOI cai dat bai kiem dong vao ve mac dinh ---
    for ma in DA_DUNG:
        rc.dat_lai_mac_dinh(ma)
    rc.xoa_cache()
    with pool.connection() as conn:
        don_dep(conn)
    print(f"\nKET QUA: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
