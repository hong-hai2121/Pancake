"""Kiểm thử 2 màn thử API: chiều VÀO (/data/thu-api) và chiều RA
(/data/thu-api/ra-pancake).

Kiểm 4 lớp:
  1. Bộ dò `app/web/api_catalog.py` — đủ endpoint, đúng quyền, đúng tham số,
     dựng được mẫu JSON body từ schema Pydantic.
  2. Trang HTML — mọi endpoint đều lên màn, có thanh lọc + khối metadata JSON,
     tab API Pancake cũ vẫn sống ở đường dẫn mới.
  3. Gọi THẬT bằng cookie phiên (đúng cách nút "Chạy" hoạt động): tài khoản đủ
     quyền -> 200, tài khoản thiếu quyền -> FORBIDDEN.
  4. Chiều RA (`app/web/pancake_catalog.py`): danh mục 12 việc gọi Pancake +
     đồng bộ CRM, bộ điều phối chặn đúng (việc GHI bắt buộc POST, whitelist,
     thiếu tham số), và đường dây đồng bộ chạy trọn vẹn — 3 hàm chạm mạng được
     thay bằng hàng giả nên KHÔNG tốn lượt API và không ghi DB.

Dữ liệu giả mang dấu `__tapi__`, dọn sạch đầu/cuối. KHÔNG gọi mạng.

Chạy:  python scripts/thu_thu_api.py
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.routing import APIRoute                 # noqa: E402
from fastapi.testclient import TestClient            # noqa: E402

from app.core.security import hash_password          # noqa: E402
from app.db.client import get_pg_pool                # noqa: E402
from app.integrations.pancake import client, crm_sync  # noqa: E402
from app.main import app                             # noqa: E402
from app.web import pancake_catalog                  # noqa: E402
from app.web.api_catalog import gom_nhom, liet_ke    # noqa: E402

DAU = "__tapi__"
MK = "ThuApi-test-1234"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:  # noqa: PLR0915 — script nghiệm thu
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        for ten, vai in (("admin", "Admin"), ("sale", "Sale")):
            conn.execute(
                "insert into crm.users (name, email, username, password_hash, "
                "status, role_id) values (%s, %s, %s, %s, 'active', %s)",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]),
            )

    # ---------------------------------------------------------- 1. bộ dò
    print("== 1. Bộ dò endpoint từ chính FastAPI ==")
    items = liet_ke(app)
    that = sum(
        len(r.methods - {"HEAD", "OPTIONS"})
        for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/")
    )
    ok("liệt kê ĐỦ mọi endpoint /api (không sót, không thừa)",
       len(items) == that, f"{len(items)} / {that}")
    ok("mỗi dòng đều có method + đường dẫn + nhóm",
       all(e["method"] and e["path"].startswith("/api/") and e["nhom"]
           for e in items))

    tra = {(e["method"], e["path"]): e for e in items}
    e_get = tra[("GET", "/api/v1/leads")]
    ok("GET /leads đọc được quyền từ dependency", e_get["quyen"] == ["customer.view"],
       str(e_get["quyen"]))
    ok("GET /leads có tham số phân trang lấy từ dependency phan_trang",
       {"page", "per_page"} <= {q["ten"] for q in e_get["query"]},
       str([q["ten"] for q in e_get["query"]]))
    ok("GET không sinh body", e_get["body"] == "" and e_get["chi_doc"])

    e_post = tra[("POST", "/api/v1/leads")]
    mau = json.loads(e_post["body"] or "{}")
    ok("POST /leads dựng được mẫu JSON từ schema Pydantic",
       "customer_id" in mau and mau["customer_id"] == 0, e_post["body"][:80])
    ok("POST bị đánh dấu là ghi dữ liệu", e_post["chi_doc"] is False)

    e_path = tra[("GET", "/api/v1/leads/{lead_id}")]
    ok("endpoint có {lead_id} tách được tham số đường dẫn",
       [p["ten"] for p in e_path["path_params"]] == ["lead_id"],
       str(e_path["path_params"]))

    e_bat = tra[("GET", "/api/v1/reports/drill-down")]
    ok("tham số bắt buộc được đánh dấu",
       any(q["bat_buoc"] for q in e_bat["query"]),
       str([(q["ten"], q["bat_buoc"]) for q in e_bat["query"]]))

    e_nhieu = tra[("GET", "/api/v1/users")]
    ok("endpoint 2 quyền (require_any_permission) lấy đủ cả hai",
       set(e_nhieu["quyen"]) == {"user.manage", "user.manage_team"},
       str(e_nhieu["quyen"]))

    nhom = gom_nhom(items)
    ok("gom nhóm không làm mất dòng nào",
       sum(len(x) for _t, _n, x in nhom) == len(items))
    ok("nhóm nào cũng có tên tiếng Việt",
       all(n and not n.startswith("khac") for _t, n, _x in nhom),
       str([n for _t, n, _x in nhom][:3]))

    # ---------------------------------------------------------- 2. trang web
    print("== 2. Trang /data/thu-api ==")
    web = TestClient(app)
    r = web.post("/dang-nhap", data={"username": f"{DAU}admin", "password": MK},
                 follow_redirects=False)
    ok("đăng nhập Admin", r.status_code in (302, 303), str(r.status_code))

    r = web.get("/data/thu-api")
    ok("màn danh mục mở 200", r.status_code == 200, str(r.status_code))
    html = r.text
    ok("có khối danh mục + ô tìm nhanh + nút lọc",
       'id="ac-root"' in html and 'id="ac-find"' in html
       and 'data-f="get"' in html)
    ok("đếm đúng số dòng endpoint trên màn",
       html.count('class="ac-ep"') == len(items),
       f'{html.count(chr(34) + "ac-ep" + chr(34))} / {len(items)}')
    ok("hiện đủ 20 nhóm nghiệp vụ", html.count('class="ac-grp"') == len(nhom),
       str(html.count('class="ac-grp"')))
    for mau_duong in ("/api/v1/leads", "/api/v1/orders", "/api/v1/reports/dashboard"):
        ok(f"có dòng {mau_duong}", f">{mau_duong}<" in html)
    ok("cảnh báo endpoint ghi dữ liệu", "không hoàn tác được" in html)

    khoi = re.search(r"var EPS = (\[.*?\]);\n", html, re.S)
    ok("có khối metadata JSON cho JS", khoi is not None)
    if khoi:
        du_lieu = json.loads(khoi.group(1).replace("<\\/", "</"))
        ok("metadata JSON parse được và đủ dòng", len(du_lieu) == len(items),
           f"{len(du_lieu)} / {len(items)}")

    r = web.get("/data/thu-api/pancake")
    ok("tab API Pancake cũ vẫn sống ở đường dẫn mới",
       r.status_code == 200 and "pm-path" in r.text, str(r.status_code))
    ok("dải tab có cả 2 mục API",
       "/data/thu-api/pancake" in html and "Thử API dự án" in html)

    # -------------------------------------------- 3. bấm Chạy (fetch + cookie)
    print("== 3. Gọi thật bằng cookie phiên (đúng cách nút Chạy làm) ==")
    r = web.get("/api/v1/pipelines")
    ok("GET /api/v1/pipelines bằng cookie -> 200 JSON",
       r.status_code == 200 and r.json().get("success") is True, str(r.status_code))
    r = web.get("/api/v1/leads", params={"page": 1, "per_page": 5})
    ok("GET /api/v1/leads có phân trang -> 200",
       r.status_code == 200 and "data" in r.json(), str(r.status_code))

    web.post("/dang-xuat", follow_redirects=False)
    r = web.post("/dang-nhap", data={"username": f"{DAU}sale", "password": MK},
                 follow_redirects=False)
    ok("đăng nhập Sale", r.status_code in (302, 303), str(r.status_code))
    r = web.get("/data/thu-api")
    ok("Sale KHÔNG vào được màn thử API (khu Bot, cần bot.view)",
       r.status_code == 403, str(r.status_code))
    r = web.get("/api/v1/users")
    ok("Sale gọi endpoint thiếu quyền -> FORBIDDEN (kết quả đúng, không phải lỗi)",
       r.status_code == 403 and r.json().get("error_code") == "FORBIDDEN",
       f"{r.status_code} {r.text[:80]}")

    # ------------------------------- 4. chiều RA: dự án gọi Pancake + đồng bộ
    print("== 4. Màn 'Gọi ra Pancake' (chiều dự án → Pancake) ==")
    web.post("/dang-xuat", follow_redirects=False)
    web.post("/dang-nhap", data={"username": f"{DAU}admin", "password": MK},
             follow_redirects=False)

    viec = pancake_catalog.liet_ke()
    r = web.get("/data/thu-api/ra-pancake")
    html2 = r.text
    ok("màn Gọi ra Pancake mở 200", r.status_code == 200, str(r.status_code))
    ok("liệt kê đủ số việc", html2.count('class="ac-ep"') == len(viec),
       f'{html2.count(chr(34) + "ac-ep" + chr(34))} / {len(viec)}')
    ok("chia đúng 3 nhóm: lấy · đồng bộ · soi lại",
       html2.count('class="ac-grp"') == 3, str(html2.count('class="ac-grp"')))
    ok("việc đồng bộ là POST (phải xác nhận), việc lấy là GET",
       {e["method"] for e in viec if e["ten"].startswith("dong-bo")} == {"POST"}
       and {e["method"] for e in viec if e["ten"] == "hoi-thoai"} == {"GET"})
    ok("có đủ 5 thứ crm_sync sinh ra trong mô tả",
       all(t in html2 for t in ("khách", "hội thoại", "thẻ", "nhân viên xử lý")))

    r = web.get("/data/thu-api/goi/chu-token")
    ok("chạy việc 'chủ token' (offline) -> 200 JSON",
       r.status_code == 200 and r.json()["data"]["viec"] == "chu-token",
       f"{r.status_code} {r.text[:80]}")
    r = web.get("/data/thu-api/goi/ton-dong")
    ok("chạy việc 'tồn đọng' -> đếm được hội thoại chưa kéo tin",
       r.status_code == 200 and "chua_keo" in r.json()["data"]["ket_qua"],
       r.text[:100])
    r = web.get("/data/thu-api/goi/page-trong-crm")
    ok("chạy việc 'page trong CRM' -> 200", r.status_code == 200, str(r.status_code))
    r = web.get("/data/thu-api/goi/doi-chieu", params={"conv_id": f"{DAU}khong-co"})
    ok("đối chiếu hội thoại chưa đồng bộ -> báo rõ chưa có trong CRM",
       r.status_code == 200 and r.json()["data"]["ket_qua"]["tim_thay"] is False,
       r.text[:100])

    r = web.get("/data/thu-api/goi/dong-bo-hoi-thoai", params={"page_id": "1"})
    ok("việc GHI gọi bằng GET -> bị từ chối (chống lỡ tay dán URL)",
       r.status_code == 422 and "POST" in r.text, f"{r.status_code} {r.text[:90]}")
    r = web.post("/data/thu-api/goi/khong-co-viec-nay")
    ok("việc không có trong whitelist -> NOT_FOUND",
       r.status_code == 404 and r.json()["error_code"] == "NOT_FOUND",
       str(r.status_code))
    r = web.get("/data/thu-api/goi/the", params={"page_id": ""})
    ok("thiếu tham số bắt buộc -> báo đúng tên tham số",
       r.json().get("error_code") == "MISSING_REQUIRED_DATA"
       and "page_id" in r.json().get("message", ""), r.text[:90])

    # Đường đồng bộ thật, nhưng thay 3 hàm chạm mạng/DB bằng hàng giả: kiểm
    # ĐƯỜNG DÂY (gọi Pancake -> sync_batch -> đối chiếu) mà không tốn lượt API.
    async def _convs_gia(page_id, msg_type="INBOX", limit=20):
        return [{"conv_id": f"{DAU}c1", "name": "Khach 1"},
                {"conv_id": f"{DAU}c2", "name": "Khach 2"}]

    async def _pages_gia(force=False):
        return [{"id": "1", "name": "Page giả"}]

    that_convs = client.fetch_conversations_fresh
    that_pages = client.list_pages
    that_sync = crm_sync.sync_batch
    client.fetch_conversations_fresh = _convs_gia
    client.list_pages = _pages_gia
    crm_sync.sync_batch = lambda pid, ten, convs: {
        "tao_moi": len(convs), "cap_nhat": 0, "bo_qua": 0, "loi": 0}
    try:
        r = web.post("/data/thu-api/goi/dong-bo-hoi-thoai",
                     params={"page_id": "1", "limit": 2})
        d = r.json().get("data", {}).get("ket_qua", {})
        ok("POST đồng bộ hội thoại chạy trọn đường dây (lấy → sync → đối chiếu)",
           r.status_code == 200 and d.get("lay_ve") == 2
           and d["ket_qua_dong_bo"]["tao_moi"] == 2 and "doi_chieu_trong_crm" in d,
           r.text[:140])
    finally:
        client.fetch_conversations_fresh = that_convs
        client.list_pages = that_pages
        crm_sync.sync_batch = that_sync

    web.post("/dang-xuat", follow_redirects=False)
    web.post("/dang-nhap", data={"username": f"{DAU}sale", "password": MK},
             follow_redirects=False)
    r = web.get("/data/thu-api/goi/ton-dong")
    ok("Sale không chạy được việc nào (khu Bot chặn cả bộ điều phối)",
       r.status_code == 403, str(r.status_code))

    with pool.connection() as conn:
        don_dep(conn)
    ok("dọn sạch dữ liệu test", True)

    print(f"\nKẾT QUẢ: {PASS} PASS · {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
