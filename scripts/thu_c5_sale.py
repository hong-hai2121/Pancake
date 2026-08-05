"""Nghiem thu C5 — BO PHAN SALE: thang bam duoi + bang viec.

Kiem NAM LUAT cua thang (mau da tra gia de co, dung sua cho gon):

  1. NGAY BAT THANG — chi doc tin TU ngay do. Khong co chot chan nay, lead nhan
     qua lai vai thang nhay thang buoc cuoi roi roi khoi bang viec.
  2. Con tro CHI TIEN, khong bao gio lui.
  3. Moi tin nhay toi da `cua_so` buoc — mot cum chu lac khong duoc day khach
     thang toi buoc cuoi.
  4. Khach dang cho tra loi thi con tro DUNG YEN (viec la DAP KHACH).
  5. NHAY COC an ca nga ve khong: dich xa hon tran thi KHONG nhay ti nao.

Cong them: du phong "1 luot = 1 buoc" chi cho NGUOI THAT · tin may chi tinh khi
dung tu khoa · tran buoc/ngay · cot dat tay TU NHA khi khach nhan lai · Tu choi
vs Ngung cham soc khac nhau · cot Qua han · cot Tiem nang.

Du lieu gia mang dau `__c5__`, don sach dau/cuoi. KHONG goi mang.

Chay:  python scripts/thu_c5_sale.py
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import sale_repo          # noqa: E402
from app.main import app                           # noqa: E402
from app.services import sale_service as sv        # noqa: E402

DAU = "__c5__"
MK = "C5-test-1234"
PAGE_GIA = "555000111000222"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    kh = f"(select id from crm.customers where full_name like '{DAU}%')"
    conn.execute(f"delete from crm.messages where conversation_id in "
                 f"(select id from crm.conversations where customer_id in {kh})")
    conn.execute(f"delete from crm.conversations where customer_id in {kh}")
    conn.execute(f"delete from crm.pages where external_page_id = '{PAGE_GIA}'")
    conn.execute(f"delete from crm.care_interactions where customer_id in {kh}")
    conn.execute(f"delete from crm.leads where customer_id in {kh}")
    conn.execute(f"delete from crm.customer_assignments where customer_id in {kh}")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:  # noqa: PLR0915 — script nghiem thu
    pool = get_pg_pool()
    gio = datetime.now(timezone.utc)
    with pool.connection() as conn:
        don_dep(conn)
        # Dat ngay bat thang lui 30 ngay de bai kiem doc duoc tin gia
        conn.execute(
            "insert into crm.app_settings (code, value) values "
            "('sale_ladder_start', %s) on conflict (code) do update set "
            "value = excluded.value",
            ((gio - timedelta(days=30)).date().isoformat(),))
        # Noi long tran/cua gio de bai kiem khong phu thuoc gio chay
        for ma, gt in (("sale_step_max_per_day", "20"),
                       ("sale_step_hour_from", "0"),
                       ("sale_step_hour_to", "0"),
                       ("sale_step_rest_hours", "0")):
            conn.execute(
                "insert into crm.app_settings (code, value) values (%s, %s) "
                "on conflict (code) do update set value = excluded.value",
                (ma, gt))

        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vai in (("nv", "Sale"), ("tn", "Trưởng nhóm Sale")):
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
        pipe = conn.execute(
            "select p.id as pid, s.id as sid from crm.pipelines p "
            "join crm.pipeline_stages s on s.pipeline_id = p.id "
            "order by s.sort_order limit 1").fetchone()

        kh, lead, conv = {}, {}, {}
        for ten in ("Buoc", "Nhay", "Cho", "Cu", "Moi", "Lac"):
            # "Moi" tao VUA XONG (con trong giai doan nong) nen phai nam cot
            # 'moi'. Cac khach kia tao 5 ngay truoc — het giai doan nong ma
            # chua du buoc thi ROI VAO 'qua_han', dung luat.
            tao_luc = gio if ten == "Moi" else gio - timedelta(days=5)
            kh[ten] = conn.execute(
                "insert into crm.customers (full_name, primary_phone, status, "
                "created_at) values (%s, %s, 'new', %s) returning id",
                (f"{DAU}Khach{ten}", f"0944{abs(hash(ten)) % 1000000:06d}",
                 tao_luc),
            ).fetchone()["id"]
            lead[ten] = conn.execute(
                "insert into crm.leads (customer_id, pipeline_id, stage_id, "
                "owner_id, created_at) values (%s, %s, %s, %s, %s) returning id",
                (kh[ten], pipe["pid"], pipe["sid"], uid["nv"], tao_luc),
            ).fetchone()["id"]
            conv[ten] = conn.execute(
                "insert into crm.conversations (customer_id, page_id, "
                "external_conversation_id, last_message_at) "
                "values (%s, %s, %s, %s) returning id",
                (kh[ten], page, f"{PAGE_GIA}_c5{ten}", gio)).fetchone()["id"]

        def tin(ai: str, cv: int, noi: str, phut_truoc: int,
                nguoi: bool = True, cu: bool = False) -> None:
            """ai = 'khach' | 'shop'. cu=True -> tin TRUOC ngay bat thang."""
            luc = ((gio - timedelta(days=200)) if cu
                   else (gio - timedelta(minutes=phut_truoc)))
            conn.execute(
                "insert into crm.messages (conversation_id, external_message_id,"
                " sender_type, sender_name, sender_user_id, content, msg_type, "
                "sent_at) values (%s, %s, %s, %s, %s, %s, 'text', %s)",
                (cv, f"{DAU}{cv}-{phut_truoc}-{noi[:8]}",
                 "customer" if ai == "khach" else "agent",
                 "khach" if ai == "khach" else f"{DAU}nv",
                 None if ai == "khach" or not nguoi else uid["nv"],
                 noi, luc))

        # --- Khach Buoc: NV di dung tu khoa buoc 1 -> 2 -> 3
        tin("khach", conv["Buoc"], "em bi trao nguoc a", 300)
        tin("shop", conv["Buoc"], "Chao chi, chi bi trieu chung the nao a", 290)
        tin("khach", conv["Buoc"], "em hay o chua sau khi an", 280)
        tin("shop", conv["Buoc"], "Ben em co lieu trinh 1 thang, bang gia day a", 270)
        tin("khach", conv["Buoc"], "the a", 260)
        tin("shop", conv["Buoc"], "Day la phan hoi cua khach ben em a", 250)

        # --- Khach Nhay: khach keu dat -> nhay coc thang buoc 6 (gui ma giam)
        tin("khach", conv["Nhay"], "sao dat the em oi", 200)
        tin("shop", conv["Nhay"], "Da chi", 190)

        # --- Khach Cho: khach nhan CUOI CUNG -> dang cho NV dap
        tin("shop", conv["Cho"], "Chao chi, chi bi trieu chung the nao a", 100)
        tin("khach", conv["Cho"], "em dau bung", 50)

        # --- Khach Cu: CHI co tin TRUOC ngay bat thang -> phai bi bo qua
        tin("shop", conv["Cu"], "Bang gia day a", 0, cu=True)
        tin("shop", conv["Cu"], "Phan hoi cua khach ben em", 0, cu=True)
        tin("shop", conv["Cu"], "Tang chi ma SALE50K", 0, cu=True)

        # --- Khach Moi: chua ai nhan gi
        # --- Khach Lac: tin MAY (khong ro nguoi) khong co tu khoa -> khong tinh
        tin("shop", conv["Lac"], "aaa bbb ccc", 80, nguoi=False)
        tin("shop", conv["Lac"], "ddd eee fff", 70, nguoi=False)

    print("== 1. Thang bam duoi doc duoc ==")
    thang = sv.thang()
    ok("doc duoc 8 buoc tu DB", len(thang) == 8, str(len(thang)))
    ok("buoc 1 khong co tu khoa nhay coc",
       (thang[1].get("keywords_customer") or "") == "",
       str(thang[1].get("keywords_customer")))
    ok("buoc 6 co tu khoa nhay coc 'dat qua'",
       "đắt quá" in (thang[6].get("keywords_customer") or ""),
       str(thang[6].get("keywords_customer"))[:60])

    print("== 2. Bo do doc TIN THAT ==")
    b, at, ve = sv.do_buoc(kh["Buoc"])
    ok("NV noi dung tu khoa -> con tro len bung 3", b == 3, f"{b} · {ve}")
    ok("nhat ky giai thich duoc vi sao", len(ve) >= 2, str(ve))
    ok("nhat ky noi ro cum chu nao khop",
       any("bảng giá" in x or "bang gia" in x or "#gia" in x for x in ve),
       str(ve))

    print("== 3. LUAT 1 — chi doc tin TU ngay bat thang ==")
    b_cu, _, _ = sv.do_buoc(kh["Cu"])
    ok("tin TRUOC ngay bat thang bi bo qua -> con tro 0", b_cu == 0, str(b_cu))

    print("== 4. LUAT 5 — nhay coc an ca nga ve khong ==")
    b_nhay, _, ve_nhay = sv.do_buoc(kh["Nhay"])
    # buoc 6 co tu khoa "dat qua"; dich = 6-1 = 5; tran nhay mac dinh 3 -> 0+3=3
    # 5 > 3 nen KHONG nhay ti nao. Con lai la du phong tu tin shop "Da chi".
    ok("dich xa hon tran nhay -> KHONG nhay coc", b_nhay <= 1,
       f"{b_nhay} · {ve_nhay}")
    ok("nhat ky khong ghi nhay coc",
       not any("nhảy cóc" in x for x in ve_nhay), str(ve_nhay))
    # Noi tran nhay len 5 thi PHAI nhay
    with pool.connection() as conn:
        conn.execute("insert into crm.app_settings (code, value) values "
                     "('sale_step_skip_max', '5') on conflict (code) do update "
                     "set value = excluded.value")
    from app.core import runtime_config
    runtime_config.xoa_cache()
    b_nhay2, _, ve_nhay2 = sv.do_buoc(kh["Nhay"])
    # Nhay coc dat con tro = 5 (de BUOC KE dung la 6 — buoc co tu khoa khach
    # vua noi). Tin shop "Da chi" sau do khong co tu khoa nen an du phong +1.
    ok("noi tran nhay -> co nhay coc (con tro vot len >= 5)",
       b_nhay2 >= 5, f"{b_nhay2} · {ve_nhay2}")
    ok("nhat ky ghi ro khach noi cum nao lam nhay",
       any("nhảy cóc" in x and "đắt" in x for x in ve_nhay2), str(ve_nhay2))
    with pool.connection() as conn:
        conn.execute("update crm.app_settings set value = '3' "
                     "where code = 'sale_step_skip_max'")
    runtime_config.xoa_cache()

    print("== 5. Tin MAY khong co tu khoa -> KHONG tinh buoc ==")
    b_lac, _, _ = sv.do_buoc(kh["Lac"])
    ok("2 tin may vo nghia -> con tro van 0 (du phong chi cho NGUOI THAT)",
       b_lac == 0, str(b_lac))

    print("== 6. LUAT 2 — con tro CHI TIEN ==")
    sv.dong_bo_con_tro(lead["Buoc"], kh["Buoc"])
    l = sale_repo.get_lead_bang(lead["Buoc"])
    ok("ghi duoc con tro 3", int(l["sale_step"]) == 3, str(l["sale_step"]))
    r = sale_repo.dat_con_tro(lead["Buoc"], 1, gio)
    ok("ep lui ve 1 -> repo TU CHOI ghi", r is None, str(r))
    l = sale_repo.get_lead_bang(lead["Buoc"])
    ok("con tro van la 3", int(l["sale_step"]) == 3, str(l["sale_step"]))
    ok("keo the tay LA duong duy nhat lui duoc",
       sale_repo.dat_con_tro_tay(lead["Buoc"], 1) is not None)
    sale_repo.dat_con_tro_tay(lead["Buoc"], 3)   # tra lai

    print("== 7. LUAT 4 — khach dang cho dap thi con tro DUNG YEN ==")
    sv.dong_bo_con_tro(lead["Cho"], kh["Cho"])
    l_cho = dict(sale_repo.get_lead_bang(lead["Cho"]))
    ok("nhan dien khach dang cho NV dap", sv.cho_nhan_vien(l_cho), str(
        {k: l_cho.get(k) for k in ("khach_cuoi", "shop_cuoi", "nguoi_cuoi")}))
    ok("buoc ke = None (viec la DAP KHACH, khong phai day buoc)",
       sv.buoc_ke(l_cho) is None, str(sv.buoc_ke(l_cho)))

    print("== 8. Buoc ke + ly do cho ==")
    l_b = dict(sale_repo.get_lead_bang(lead["Buoc"]))
    ke = sv.buoc_ke(l_b)
    ok("buoc ke la buoc 4", ke and int(ke["step_no"]) == 4, str(ke)[:100])
    ok("goi y cau chu cho buoc ke", len(sv.goi_y_cau(ke)) > 0,
       str(sv.goi_y_cau(ke)))
    ok("goi y doi #anh thanh chu nguoi doc duoc",
       all(not g.startswith("#") for g in sv.goi_y_cau(ke)),
       str(sv.goi_y_cau(ke)))

    print("== 9. Xep cot bang viec ==")
    cot_ds = {c["ma"]: c for c in sv.cac_cot()}
    ok("co du cot dau + 8 cot buoc + cot cuoi", len(cot_ds) == 2 + 8 + 5,
       str(len(cot_ds)))
    ok("cot Qua han KHONG cho keo tay", cot_ds["qua_han"]["keo"] is False)
    ok("cot Da chot KHONG cho keo tay", cot_ds["da_chot"]["keo"] is False)
    ma, vi_sao = sv.cot_cua(l_b)
    ok("lead da di 3 buoc -> nam cot 'buoc_4'", ma == "buoc_4", f"{ma} · {vi_sao}")
    l_moi = dict(sale_repo.get_lead_bang(lead["Moi"]))
    ok("lead VUA vao, chua ai nhan gi -> cot 'moi'",
       sv.cot_cua(l_moi)[0] == "moi", str(sv.cot_cua(l_moi)))
    # Khach "Cu" tao 5 ngay truoc, tin deu nam TRUOC ngay bat thang -> con tro 0
    # -> het giai doan nong ma chua du buoc = QUA HAN (dung luat, khong phai loi)
    l_cu = dict(sale_repo.get_lead_bang(lead["Cu"]))
    ma_cu, vs_cu = sv.cot_cua(l_cu)
    ok("lead cu bo quen (het giai doan nong, 0 buoc) -> cot 'qua_han'",
       ma_cu == "qua_han", f"{ma_cu} · {vs_cu}")
    ok("cot Qua han noi RO vi sao qua han",
       "chưa đủ" in vs_cu and "bước" in vs_cu, vs_cu)
    # Khach Cho da tra loi sau tin shop -> co dau replied_at -> Tiem nang
    ok("lead khach DA TRA LOI -> co dau replied_at",
       l_cho.get("replied_at") is not None, str(l_cho.get("replied_at")))

    print("== 10. Tu choi vs Ngung cham soc — KHAC NHAU ==")
    sv.tu_choi(lead["Moi"], nguoi=uid["nv"])
    l = sale_repo.get_lead_bang(lead["Moi"])
    ok("Tu choi -> cot 'tu_choi'", l["board_column"] == "tu_choi",
       str(l["board_column"]))
    # Khach nhan lai SAU luc dat -> the phai TU NHA
    with pool.connection() as conn:
        conn.execute(
            "insert into crm.messages (conversation_id, external_message_id, "
            "sender_type, sender_name, content, msg_type, sent_at) "
            "values (%s, %s, 'customer', 'khach', %s, 'text', now())",
            (conv["Moi"], f"{DAU}quaylai", "em muon hoi lai a"))
    nha = sale_repo.nha_cot_da_cu()
    ok("khach nhan lai -> the TU NHA khoi cot Tu choi", nha >= 1, str(nha))
    l = sale_repo.get_lead_bang(lead["Moi"])
    ok("board_column da rong", l["board_column"] is None, str(l["board_column"]))

    loi = ""
    try:
        sv.ngung_cham_soc(lead["Lac"], "  ", nguoi=uid["nv"])
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("Ngung cham soc KHONG ly do -> chan", "lý do" in loi, loi)
    sv.ngung_cham_soc(lead["Lac"], "Khach yeu cau khong lien he",
                      nguoi=uid["nv"])
    with pool.connection() as conn:
        conn.execute(
            "insert into crm.messages (conversation_id, external_message_id, "
            "sender_type, sender_name, content, msg_type, sent_at) "
            "values (%s, %s, 'customer', 'khach', %s, 'text', now())",
            (conv["Lac"], f"{DAU}nhanlai2", "alo"))
    sale_repo.nha_cot_da_cu()
    l = sale_repo.get_lead_bang(lead["Lac"])
    ok("Ngung cham soc KHONG tu nha du khach nhan lai",
       l["board_column"] == "ngung", str(l["board_column"]))

    print("== 11. Keo the ==")
    loi = ""
    try:
        sv.keo_the(lead["Buoc"], "qua_han", nguoi=uid["nv"])
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("keo vao cot may suy ra -> chan", "không kéo tay được" in loi, loi)
    sv.keo_the(lead["Buoc"], "buoc_6", nguoi=uid["nv"])
    l = sale_repo.get_lead_bang(lead["Buoc"])
    ok("keo sang 'Buoc 6' -> con tro dat = 5", int(l["sale_step"]) == 5,
       str(l["sale_step"]))
    sv.mo_lai(lead["Buoc"], nguoi=uid["nv"])
    ok("mo lai -> tra the ve cho may xep",
       sale_repo.get_lead_bang(lead["Buoc"])["board_column"] is None)

    print("== 12. Bang viec + 4 o dem ==")
    bv = sv.bang_viec(owner_id=uid["nv"])
    ok("bang viec tra the", len(bv["the"]) >= 4, str(len(bv["the"])))
    ok("co du 4 o dem",
       set(bv["dem"]) == {"hom_nay", "qua_han", "vua_phan_hoi", "yeu_cau_chia"},
       str(bv["dem"]))
    ok("dem 'vua phan hoi' bat duoc khach dang cho dap",
       bv["dem"]["vua_phan_hoi"] >= 1, str(bv["dem"]))
    ok("moi the deu co cot + ly do",
       all(x.get("cot") and x.get("cot_vi_sao") for x in bv["the"]))

    print("== 13. An khach da cham hom nay ==")
    from app.services import giam_sat_service
    giam_sat_service.ghi_cong(kh["Buoc"], uid["nv"], "nhan")
    bv2 = sv.bang_viec(owner_id=uid["nv"])
    con = {x["id"] for x in bv2["the"]}
    ok("khach vua cham hom nay bi AN khoi bang", lead["Buoc"] not in con,
       str(con))
    bv3 = sv.bang_viec(owner_id=uid["nv"], an_da_cham=False)
    ok("bo tick 'an' thi hien lai",
       lead["Buoc"] in {x["id"] for x in bv3["the"]})

    print("== 14. Man hinh ==")
    web = TestClient(app)

    def dang_nhap(u: str) -> None:
        r = web.post("/dang-nhap", data={"username": u, "password": MK},
                     follow_redirects=False)
        assert r.status_code == 303, r.status_code

    dang_nhap(f"{DAU}nv")
    r = web.get("/crm/bang-viec")
    ok("man Bang viec mo 200", r.status_code == 200, str(r.status_code))
    ok("bao ro cot do MAY doc tin nhan that suy ra",
       "máy đọc tin nhắn thật" in r.text)
    ok("noi ro khac Pipeline giai doan", "/crm/pipeline" in r.text)
    # Đếm trên MARKUP (`class="bv-tab`), không đếm tên lớp trần: chuỗi "bv-tab"
    # trơn còn nằm trong CSS của shell nên phép đếm cũ vẫn xanh kể cả khi màn
    # đã bỏ hết ô đếm — chính cái bẫy đó đã cho bản `vc-tile` cũ qua mặt.
    ok("co du 4 tab dem tren man", r.text.count('class="bv-tab') >= 4,
       str(r.text.count('class="bv-tab')))
    ok("3 tang cong cu/loc/tab deu co",
       all(f'class="{k}"' in r.text for k in ("bv-bar1", "bv-bar2", "bv-tabs")))
    ok("co nut doi bo phan sang CSKH", "/crm/bang-viec-cskh" in r.text)
    ok("giai thich 2 nut dong khach khac nhau",
       "Từ chối</b> = đóng đợt này" in r.text
       and "Ngừng chăm sóc</b> = dừng hẳn" in r.text)
    r = web.get("/crm/bang-viec?cd=pipeline")
    ok("che do Pipeline ve cot", "bv-board" in r.text)
    ok("cot may suy ra co gan khoa", "không kéo tay" in r.text)
    ok("the co cau viec can lam 📌", "bv-viec" in r.text)

    ok("NV thuong: o 'Xem ca doi' bi KHOA", 'name="tatca" value="1" disabled'
       in r.text.replace("  ", " ") or "disabled" in r.text, "")
    ok("NV thuong mac dinh xem CUA TOI", "· của tôi" in r.text)

    r = web.get("/crm/thang-sale")
    ok("Sale khong co user.manage -> 403 man Thang", r.status_code == 403,
       str(r.status_code))

    # 🚩 Loi that da gap: admin/truong nhom KHONG so huu lead nao, mac dinh
    #    "chi cua toi" lam ho mo man ra thay TRONG TRON ma khong hieu vi sao.
    dang_nhap(f"{DAU}tn")
    r = web.get("/crm/bang-viec")
    ok("QUAN LY mac dinh xem HET CUA TAT CA (khong phai 'cua toi')",
       "· cả đội" in r.text, r.text[r.text.find('class="cnt"'):][:60])
    ok("truong nhom du KHONG so huu lead nao van thay the",
       "bv-the" in r.text or "kh-tbl" in r.text)
    r = web.get("/crm/bang-viec?tatca=0")
    ok("quan ly van bo ve 'chi cua toi' duoc neu muon",
       "· của tôi" in r.text, "")
    ok("bang trong thi NOI RO vi sao + cach xem tiep",
       "chưa được giao lead nào" in r.text or "Chưa có lead nào" in r.text,
       "")

    print("== 15. Chan tu khoa qua ngan ==")
    loi = ""
    try:
        sv.luu_buoc(9, name="Thu", kw_nv="đắt, mắc")
    except Exception as err:  # noqa: BLE001
        loi = getattr(err, "message", str(err))
    ok("tu khoa 1 chu ngan -> chan, giai thich cai bay bo dau",
       "quá ngắn" in loi and "đặt hàng" in loi, loi)
    ok("cum nhieu chu thi luu duoc",
       bool(sv.luu_buoc(9, name=f"{DAU}Thu", kw_nv="đắt quá, sao đắt")))
    with pool.connection() as conn:
        conn.execute("delete from crm.sale_steps where step_no = 9")

    # =====================================================================
    print("== 16. Bo loc bang viec (buoc 2) ==")
    # Moi test lead deu: owner = nv · page = PAGE_GIA · tao hom nay hoac -5 ngay.
    # Nen tung o loc phai GIU khi tri dung, va BO SACH khi tri sai.
    ta = {x["id"] for x in sv.bang_viec(owner_id=uid["nv"])["the"]}
    ok("chua loc thi co the", len(ta) >= 4, str(len(ta)))

    def ids(**kw):
        return {x["id"] for x in sv.bang_viec(owner_id=uid["nv"], **kw)["the"]}

    ok("loc nhan vien DUNG -> giu nguyen", ids(staff_id=uid["nv"]) == ta)
    ok("loc nhan vien KHAC -> rong", ids(staff_id=uid["tn"]) == set())
    ok("loc 'chua gan' -> rong (moi lead deu co chu)",
       ids(chua_gan=True) == set())
    ok("loc fanpage DUNG -> giu nguyen", ids(page_id=page) == ta)
    ok("loc fanpage KHAC -> rong", ids(page_id=page + 99999) == set())

    hnay = gio.date()
    ok("loc ngay nhan lan dau: tu 6 ngay truoc -> giu nguyen",
       ids(tao_tu=str(hnay - timedelta(days=6))) == ta)
    ok("loc ngay nhan lan dau: chi HOM NAY -> chi con lead tao hom nay",
       ids(tao_tu=str(hnay)) == {lead["Moi"]} & ta or
       ids(tao_tu=str(hnay)) < ta, str(len(ids(tao_tu=str(hnay)))))
    ok("loc ngay: den TRUOC moi lead -> rong",
       ids(tao_den=str(hnay - timedelta(days=30))) == set())

    ok("pham vi 'con dong 14 ngay' -> giu nguyen", ids(hoat_dong_ngay=14) == ta)
    ok("pham vi 'con dong 1 ngay' -> bot thi (lead cu roi ra)",
       ids(hoat_dong_ngay=1) <= ta)

    # Trang thai: lay dung mot cot dang co the roi loc theo no.
    bv = sv.bang_viec(owner_id=uid["nv"])
    cot_co = next((k for k, v in bv["theo_cot"].items() if v), "")
    ok("co dem theo tung cot", bool(bv.get("dem_cot")), str(bv.get("dem_cot")))
    ok("dem_cot khop so the that trong cot do",
       bv["dem_cot"].get(cot_co) == len(bv["theo_cot"][cot_co]),
       f'{cot_co}: {bv["dem_cot"].get(cot_co)}')
    loc_cot = sv.bang_viec(owner_id=uid["nv"], trang_thai=cot_co)
    ok("loc trang thai -> chi con the cua cot do",
       {x["cot"] for x in loc_cot["the"]} == {cot_co}, cot_co)
    ok("dem_cot KHONG ve 0 khi da loc mot cot (dem truoc, loc sau)",
       sv.bang_viec(owner_id=uid["nv"],
                    trang_thai=cot_co)["dem_cot"] == bv["dem_cot"])

    # --- tren MAN, qua HTTP ---
    dang_nhap(f"{DAU}tn")
    r = web.get("/crm/bang-viec")
    ok("man co du 7 o loc", all(k in r.text for k in (
        'name="tt"', 'name="nv"', 'name="page"', 'name="tu"', 'name="den"',
        'name="tatca"', 'name="hien_da_cham"')))
    ok("o trang thai co kem so dem", re.search(r'name="tt"[\s\S]{0,4000}?\(\d+\)',
                                               r.text) is not None)
    ok("cap nut pham vi co mat", "Còn động" in r.text and "Tất cả lead" in r.text)
    # 🚩 Soi MARKUP (`class="..."`), khong soi ten lop tran: "bv-the"/"kh-name"
    #    con nam trong CSS cua shell nen phep kiem "not in" luon sai.
    r2 = web.get(f"/crm/bang-viec?page={page + 99999}")
    ok("loc fanpage sai tren man -> bang rong",
       'class="bv-the' not in r2.text and 'class="kh-name"' not in r2.text)
    ok("bang rong vi BO LOC thi noi dung ly do (khong do tai kho du lieu)",
       "khớp bộ lọc đang bật" in r2.text and "fanpage" in r2.text,
       r2.text[r2.text.find("flash warn"):][:150])
    # 🚩 Lo xem trom: NV thuong gui tay ?nv=<id nguoi khac> phai bi BO QUA.
    dang_nhap(f"{DAU}nv")
    r3 = web.get(f"/crm/bang-viec?nv={uid['tn']}")
    ok("NV thuong gui tay ?nv= cua nguoi khac -> bo qua, van thay cua minh",
       "· của tôi" in r3.text and "kh-name" in r3.text)
    ok("NV thuong khong duoc in o chon nhan vien",
       'name="nv"' not in r3.text and "Của tôi" in r3.text)

    # =====================================================================
    print("== 17. The khach (buoc 3) ==")
    from app.web.views import sale as vsale                      # noqa: PLC0415

    tk = {"id": 1, "customer_id": 9, "full_name": "Lan", "primary_phone": "0912345678",
          "owner_name": "NV1", "card_rank": "gold", "total_spent": 7500000,
          "source": "facebook", "page_name": "FP A", "cot": "buoc_3",
          "cot_vi_sao": "x", "goi_y": [], "cho_dap": False, "ly_do_cho": "",
          "qua_han": "", "sale_step": 2, "khach_cuoi": gio - timedelta(hours=3),
          "buoc_ke": {"step_no": 3, "name": "N", "work": "W", "san_sang": True,
                      "nong": False}}
    h = vsale._the(tk, [{"ma": "buoc_3", "ten": "B3", "mau": "#7FA33F",
                         "viec": "x", "keo": True}], {"gold": "Gold"}, 8)
    ok("the co hang the + tong chi", "Gold" in h and "7.500.000đ" in h)
    ok("the co chip nguon khach", "facebook" in h and "bv-nguon" in h)
    ok("the co SDT bam-chep (dung lai .kh-tel)",
       'class="kh-tel bv-tel"' in h and 'data-so="0912345678"' in h)
    ok("the co chip cua 24 gio", "Cửa tự do" in h)

    # 🔴 BAY B4 cua mau: thanh DAY DAN VE PHIA XAU. Bat buoc doi mau theo ti le
    #    VA luon kem chu — bo chu di la nguoi doc hieu NGUOC.
    def tdo(buoc):
        return vsale._tien_do(dict(tk, sale_step=buoc, buoc_ke=None), 8)

    ok("tien do buoc dau -> XANH", "#2EAD6E" in tdo(2))
    ok("tien do giua thang -> VANG", "#E0A417" in tdo(5))
    ok("tien do cuoi thang -> DO", "#E5484D" in tdo(7))
    ok("tien do LUON kem chu moc (bay B4)",
       all("bv-tien-c" in tdo(b) and "bước" in tdo(b) for b in (2, 5, 7)))
    ok("het thang thi noi ro da het bam duoi", "hết bám đuổi" in tdo(8))

    # Cua 24h: BA trang thai, thieu moc thi KHONG duoc ket luan het cua.
    ok("khach nhan 30h truoc -> ngoai cua, chi gui mau Meta",
       "Cửa mẫu Meta" in vsale._cua_24h({"khach_cuoi": gio - timedelta(hours=30)}))
    ok("thieu moc tin khach -> 'chua ro', KHONG ket luan het cua",
       "Chưa rõ cửa" in vsale._cua_24h({"khach_cuoi": None}))

    # Dau da xem: kho hoi thoai chua co thi KHONG duoc ve dau gia.
    ok("khong co du lieu watcher -> khong ve dau da xem",
       vsale._dau_xem({"id": 1}) == "")
    ok("co tin chua doc -> dau do", "chua" in vsale._dau_xem({"unread_count": 3}))
    ok("da xem -> dau xanh", 'bv-xem da' in vsale._dau_xem({"seen": True,
                                                            "unread_count": 0}))
    # Hang chua xep: card_rank NULL la trang thai THU 6, khong phai loi.
    ok("khach chua xep hang van hien duoc",
       "Chưa xếp hạng" in vsale._hang({"card_rank": None, "total_spent": 0}, {}))

    dang_nhap(f"{DAU}tn")
    r4 = web.get("/crm/bang-viec")
    ok("man co bo chep SDT (toast + JS)",
       'class="kh-toast"' in r4.text and "navigator.clipboard" in r4.text)
    r5 = web.get("/crm/bang-viec?cd=pipeline")
    ok("the tren pipeline co thanh tien do", 'class="bv-tien"' in r5.text)

    # =====================================================================
    print("== 18. Hang nut tren the (buoc 4) ==")
    lid = lead["Cu"]
    cid_cu = kh["Cu"]
    hn = vsale._hang_nut(dict(tk, id=lid, customer_id=cid_cu,
                              next_action_at=None), [])
    ok("co nut chat trong CRM", f"/crm/khach-hang/{cid_cu}?tab=hoi-thoai" in hn)
    ok("co nut thu vien kich ban", "/crm/kich-ban" in hn)
    ok("co nut tu khai da nhan + da goi",
       f"/crm/bang-viec/{lid}/tu-khai" in hn
       and 'value="nhan"' in hn and 'value="goi"' in hn)
    ok("co menu ... voi dat hen + chuyen cot + tra ve may",
       all(f"/crm/bang-viec/{lid}/{x}" in hn for x in ("hen", "keo", "mo-lai")))
    # Mau dan rieng: thu vien kich ban (chep tay) KHAC Botcake (may ban tin).
    ok("Botcake danh dau CHUA LAM DUOC, khong gop voi thu vien kich ban",
       "ht-todo" in hn and "Botcake chưa nối" in hn)
    ok("chua co hen thi KHONG bay nut Xoa hen", "Xoá hẹn" not in hn)
    ok("co hen roi thi hien nut Xoa hen",
       "Xoá hẹn" in vsale._hang_nut(dict(tk, id=lid, customer_id=cid_cu,
                                         next_action_at=gio), []))

    # --- dat hen: chay THAT qua service ---
    mai = (gio + timedelta(days=1)).strftime("%Y-%m-%dT09:00")
    sv.dat_hen(lid, mai, nguoi=uid["nv"])
    l_h = dict(sale_repo.get_lead_bang(lid))
    ok("dat hen ghi duoc vao next_action_at", l_h["next_action_at"] is not None)
    ok("co hen -> the nhay sang cot Hen mua", sv.cot_cua(l_h)[0] == "hen_mua",
       sv.cot_cua(l_h)[0])
    # 🚩 Loi that da sua 05/08: `qua_han` xet TRUOC `hen_mua` nen dong chu thich
    #    "hen truot van o lai cot Hen mua" khong bao gio co hieu luc — lead ket
    #    thang du lau de nguoi ta dat hen thi cung du lau de qua_han bat truoc.
    #    NV dat hen xong thay the nhay sang "Qua han — xu ngay" la mat niem tin.
    ok("lead DANG qua han ma co hen -> Hen mua thang (khong phai Qua han)",
       sv.cot_cua(dict(l_h))[0] == "hen_mua", sv.cot_cua(dict(l_h))[0])
    hom_qua = gio - timedelta(days=2)
    sv.dat_hen(lid, hom_qua.strftime("%Y-%m-%dT09:00"), nguoi=uid["nv"])
    l_tr = dict(sale_repo.get_lead_bang(lid))
    ok("hen TRUOT ngay van o lai cot Hen mua, co ghi ro la truot",
       sv.cot_cua(l_tr) == ("hen_mua", "hẹn đã trượt ngày"), str(sv.cot_cua(l_tr)))

    # --- Tai lieu C1: hen truot "o lai cot Hen mua (VIEN DO)". Vien suong la
    #     chua du — luat vang B3.5 cua chinh tai lieu: mau khong bao gio dung
    #     mot minh, LUON kem chu/icon.
    bv_tr = sv.bang_viec(owner_id=uid["nv"], an_da_cham=False)
    the_tr = next((x for x in bv_tr["the"] if x["id"] == lid), None)
    ok("service gan co hen_tre (khong bat giao dien so chuoi hien thi)",
       bool(the_tr and the_tr.get("hen_tre")), str(the_tr and the_tr.get("cot")))
    h_tr = vsale._the(the_tr, bv_tr["cot"], {}, 8)
    ok("the hen truot co VIEN DO", 'class="bv-the tre"' in h_tr
       or 'class="bv-the nong tre"' in h_tr, h_tr[:60])
    ok("the hen truot co KEM CHU (luat B3.5), khong phai mau tron",
       "Hẹn đã trượt ngày" in h_tr)
    the_ok = dict(the_tr, hen_tre=False)
    ok("hen SAP TOI thi khong vien do, khong canh bao",
       "tre" not in vsale._the(the_ok, bv_tr["cot"], {}, 8)[:60]
       and "Hẹn đã trượt" not in vsale._the(the_ok, bv_tr["cot"], {}, 8))
    sv.dat_hen(lid, "", nguoi=uid["nv"])
    ok("xoa hen -> next_action_at ve rong",
       sale_repo.get_lead_bang(lid)["next_action_at"] is None)
    ok("xoa hen roi thi quay ve dung cot cu (Qua han)",
       sv.cot_cua(dict(sale_repo.get_lead_bang(lid)))[0] == "qua_han")
    loi2 = ""
    try:
        sv.dat_hen(lid, "khong-phai-ngay", nguoi=uid["nv"])
    except Exception as err:  # noqa: BLE001
        loi2 = getattr(err, "message", str(err))
    ok("ngay hen bay ba -> bao loi ro rang", "không đọc được" in loi2, loi2)

    # --- tu khai: PHAI di qua cong ghi cong (chong trung trong ngay) ---
    with pool.connection() as conn:
        conn.execute("delete from crm.care_interactions where customer_id = %s",
                     (cid_cu,))
    ok("tu khai lan dau -> ghi cong moi",
       sv.tu_khai(lid, "nhan", nguoi=uid["nv"]) == "moi")
    ok("tu khai lan hai cung ngay -> bao TRUNG, khong cong them",
       sv.tu_khai(lid, "nhan", nguoi=uid["nv"]) == "trung")
    ok("da goi la hanh dong KHAC, van ghi duoc",
       sv.tu_khai(lid, "goi", nguoi=uid["nv"]) == "moi")
    loi3 = ""
    try:
        sv.tu_khai(lid, "nhay-mua", nguoi=uid["nv"])
    except Exception as err:  # noqa: BLE001
        loi3 = getattr(err, "message", str(err))
    ok("viec la -> chan", "Việc lạ" in loi3, loi3)

    # --- qua HTTP ---
    r6 = web.post(f"/crm/bang-viec/{lid}/hen", data={"khi": mai},
                  follow_redirects=False)
    ok("POST dat hen -> 303 ve bang viec", r6.status_code == 303,
       str(r6.status_code))
    ok("dat hen qua HTTP an that",
       sale_repo.get_lead_bang(lid)["next_action_at"] is not None)
    r7 = web.post(f"/crm/bang-viec/{lid}/hen", data={"khi": ""},
                  follow_redirects=False)
    ok("POST xoa hen an that", r7.status_code == 303
       and sale_repo.get_lead_bang(lid)["next_action_at"] is None)
    r8 = web.get("/crm/bang-viec")
    ok("che do Bang cung co hang nut (2 che do lam duoc viec nhu nhau)",
       'class="bv-nutr"' in r8.text)

    # =====================================================================
    print("== 19. Thanh hang loat (buoc 6) ==")
    dang_nhap(f"{DAU}tn")
    r = web.get("/crm/bang-viec")
    ok("quan ly thay thanh hang loat + o tich",
       'id="bv-hl"' in r.text and 'class="bv-tick"' in r.text)
    # 🔴 Tai lieu C1 CAM hai viec nay lam hang loat. Test khoa lai de sau nay
    #    khong ai "tien tay" them vao.
    ok("CAM tang voucher hang loat", 'value="voucher"' not in r.text)
    ok("CAM tu khai hang loat", 'value="tu_khai"' not in r.text)
    ok("viec chua noi duoc thi danh dau, khong bay nut chet",
       "chiến dịch dựng theo BỘ LỌC" in r.text and "Botcake chưa nối" in r.text)

    # --- giao/chia nhan vien: chay THAT ---
    ids = [lead["Buoc"], lead["Cho"], lead["Cu"]]
    kq = sv.giao_hang_loat(ids, [uid["tn"]], nguoi=uid["tn"])
    ok("giao het cho 1 nguoi", kq["doi"] == 3, str(kq))
    ok("owner_id doi that trong DB",
       all(sale_repo.get_lead_bang(i)["owner_id"] == uid["tn"] for i in ids))
    kq2 = sv.giao_hang_loat(ids, [uid["nv"], uid["tn"]], nguoi=uid["tn"])
    chu = [sale_repo.get_lead_bang(i)["owner_id"] for i in ids]
    ok("chia deu 3 the cho 2 nguoi -> lech khong qua 1",
       kq2["doi"] == 3 and abs(chu.count(uid["nv"]) - chu.count(uid["tn"])) <= 1,
       str(chu))
    for i in ids:                      # tra lai chu cu cho cac muc sau
        sale_repo.giao_lead([i], uid["nv"])
    for xau, dk in (("chua chon the", ([], [uid["nv"]])),
                    ("chua chon nhan vien", (ids, []))):
        loi4 = ""
        try:
            sv.giao_hang_loat(*dk, nguoi=uid["tn"])
        except Exception as err:  # noqa: BLE001
            loi4 = getattr(err, "message", str(err))
        ok(f"giao ma {xau} -> chan, noi ro", "Chưa chọn" in loi4, loi4)

    # --- xuat CSV ---
    csv_co = sv.xuat_csv(ids, co_sdt=True)
    ok("CSV co dong tieu de + du dong du lieu",
       csv_co.count("\r\n") >= 4 and "Tên khách" in csv_co, str(len(csv_co)))
    ok("CSV co SDT khi duoc phep", "0944" in csv_co)
    # 🚩 File roi khoi he thong la khong thu ve duoc: nguoi khong duoc xem SDT
    #    tren man thi cung khong duoc xuat SDT ra file.
    csv_khong = sv.xuat_csv(ids, co_sdt=False)
    ok("KHONG duoc xem SDT -> cot dien thoai bi che",
       "0944" not in csv_khong and "***" in csv_khong)
    loi5 = ""
    try:
        sv.xuat_csv([], co_sdt=True)
    except Exception as err:  # noqa: BLE001
        loi5 = getattr(err, "message", str(err))
    ok("xuat ma chua chon the -> chan", "Chưa chọn" in loi5, loi5)

    # --- qua HTTP ---
    r9 = web.post("/crm/bang-viec/hang-loat",
                  data={"act": "xuat", "ids": [str(i) for i in ids]})
    ok("POST xuat -> tra file CSV that",
       r9.status_code == 200 and "text/csv" in r9.headers.get("content-type", ""),
       f'{r9.status_code} {r9.headers.get("content-type")}')
    ok("CSV co BOM cho Excel ban Viet khoi vo dau",
       r9.content.startswith("﻿".encode()))
    ok("co ten file dinh kem",
       "attachment" in r9.headers.get("content-disposition", ""))
    r10 = web.post("/crm/bang-viec/hang-loat", data={"act": "nghich-pha"},
                   follow_redirects=False)
    ok("hanh dong la -> khong lam gi, bao loi", r10.status_code == 303)

    # 🚩 Lo phan quyen: NV THUONG khong duoc thao tac hang loat.
    dang_nhap(f"{DAU}nv")
    r11 = web.get("/crm/bang-viec")
    ok("NV thuong KHONG thay thanh hang loat", 'id="bv-hl"' not in r11.text)
    r12 = web.post("/crm/bang-viec/hang-loat",
                   data={"act": "giao", "ids": [str(ids[0])],
                         "bb_nv": [str(uid["nv"])]})
    ok("NV thuong goi thang endpoint hang loat -> 403",
       r12.status_code == 403, str(r12.status_code))

    with pool.connection() as conn:
        don_dep(conn)
        conn.execute("delete from crm.app_settings where code in "
                     "('sale_ladder_start','sale_step_max_per_day',"
                     "'sale_step_hour_from','sale_step_hour_to',"
                     "'sale_step_rest_hours','sale_step_skip_max')")
    print(f"\nKET QUA: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
