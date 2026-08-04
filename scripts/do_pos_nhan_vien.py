"""Dò xem Pancake POS có trả DANH SÁCH NHÂN VIÊN không (bước 0 của việc ghép NV).

Chạy:  python scripts/do_pos_nhan_vien.py

Vì sao cần: `pos_sync._nhan_vien_pos()` hiện chỉ nhặt được ID nhân viên nằm
trong đơn (assigning_seller_id/assigning_care_id/marketer_id) — KHÔNG có tên,
nên màn Ánh xạ chỉ bày ra dãy số trần, Admin không biết gán cho ai. Muốn có tên
thì phải lấy roster từ POS. Spec 82 endpoint là một chuyện, shop mình trả gì là
chuyện khác -> dò trước, viết client sau (đúng nếp scripts/do_pos_api.py).

Thử lần lượt vài đường ứng viên; đường nào 200 thì in cấu trúc THẬT của 1 dòng
để biết trường nào map được sang staff_mappings (id · tên · email · SĐT · vai).
Chỉ GET, không tạo/sửa gì trên POS.
"""

import json
import sys
from pathlib import Path

import httpx

GOC = Path(__file__).resolve().parent.parent

# Các đường ứng viên cho "danh sách nhân viên" — POS mỗi bản đặt tên một kiểu.
DUONG_UNG_VIEN = [
    "shops/{shop}/users",
    "shops/{shop}/staffs",
    "shops/{shop}/employees",
    "shops/{shop}/members",
    "shops/{shop}/user_groups",
]

# Trường hay gặp cho một "người" — in ra để biết map sang cột nào.
TRUONG_QUAN_TAM = ("id", "user_id", "name", "fullname", "full_name", "username",
                   "email", "phone_number", "phone", "role", "role_id", "roles",
                   "status", "active", "avatar_url", "inserted_at")


def doc_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (GOC / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def che(key: str) -> str:
    return f"{key[:6]}…{key[-4:]}" if len(key) > 12 else "•" * len(key)


# Dòng user của POS mang CẢ api_key riêng của người đó -> che khi in ra màn hình.
TRUONG_BI_MAT = ("api_key", "note_api_key", "token", "access_token", "password")


def _gia_tri(dong: dict, k: str) -> str:
    if k in TRUONG_BI_MAT:
        return f'"{che(str(dong.get(k) or ""))}"'
    return json.dumps(dong.get(k), ensure_ascii=False)[:90]


def in_mot_dong(dong: dict, thut: str = "      ") -> None:
    """In các trường quan tâm của 1 bản ghi người + liệt kê đủ tên trường.

    POS gói tên/email/SĐT trong object LỒNG (`user`, `profile`) chứ không để
    phẳng, nên phải mở từng object con ra mới biết map vào cột nào."""
    print(f"{thut}({len(dong)} trường) {sorted(dong.keys())}")
    for k in TRUONG_QUAN_TAM:
        if k in dong and not isinstance(dong.get(k), (dict, list)):
            print(f"{thut}  {k:14} = {_gia_tri(dong, k)}")
    for k, v in sorted(dong.items()):
        if isinstance(v, dict) and v:
            print(f"{thut}  ├─ {k} (object, {len(v)} trường):")
            for kk in sorted(v.keys()):
                print(f"{thut}  │    {kk:16} = {_gia_tri(v, kk)}")
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            print(f"{thut}  ├─ {k} (list {len(v)}), trường dòng đầu: {sorted(v[0].keys())}")


def main() -> int:
    env = doc_env()
    api_key = env.get("PANCAKE_POS_API_KEY", "")
    shop_id = env.get("PANCAKE_POS_SHOP_ID", "")
    base = env.get("PANCAKE_POS_BASE_URL", "https://pos.pages.fm/api/v1").rstrip("/")
    if not api_key or not shop_id:
        print("Thiếu PANCAKE_POS_API_KEY / PANCAKE_POS_SHOP_ID trong .env")
        return 1

    http = httpx.Client(timeout=30, headers={"Accept": "application/json"})

    def goi(path: str, **params):
        resp = http.get(f"{base}/{path.lstrip('/')}",
                        params={"api_key": api_key, **params})
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text[:200]

    print(f"Base {base} · shop {shop_id} · key {che(api_key)}\n")

    # ---- 1. Shop object có sẵn danh sách người không? ------------------------
    code, data = goi("shops")
    print(f"===== GET /shops -> HTTP {code}")
    if code == 200 and isinstance(data, dict):
        for s in data.get("shops") or []:
            if str(s.get("id")) != str(shop_id):
                continue
            print(f"  shop {s.get('id')} — {s.get('name')}")
            print(f"  các trường của shop: {sorted(s.keys())}")
            for khoa in ("users", "staffs", "members", "employees"):
                nguoi = s.get(khoa)
                if isinstance(nguoi, list) and nguoi:
                    print(f"  ==> shop.{khoa}: {len(nguoi)} người, mẫu 1 dòng:")
                    if isinstance(nguoi[0], dict):
                        in_mot_dong(nguoi[0])
    else:
        print(f"  {str(data)[:200]}")

    # ---- 2. Các endpoint roster ứng viên ------------------------------------
    thay = []
    for mau in DUONG_UNG_VIEN:
        path = mau.format(shop=shop_id)
        code, data = goi(path, page_size=50)
        print(f"\n===== GET /{path} -> HTTP {code}")
        if code != 200:
            print(f"  {str(data)[:160]}")
            continue
        if not isinstance(data, dict):
            print(f"  (không phải JSON dict) {str(data)[:160]}")
            continue
        # POS trả khi thì {data:[…]}, khi thì {users:[…]}
        dong = None
        for khoa in ("data", "users", "staffs", "employees", "members", "entries"):
            if isinstance(data.get(khoa), list):
                dong, ten_khoa = data[khoa], khoa
                break
        if dong is None:
            print(f"  keys = {sorted(data.keys())} | {str(data)[:200]}")
            continue
        print(f"  success={data.get('success')} | khoá dữ liệu = '{ten_khoa}' | "
              f"{len(dong)} dòng | total_entries={data.get('total_entries')}")
        if dong and isinstance(dong[0], dict):
            print("  --- mẫu dòng đầu:")
            in_mot_dong(dong[0])
            thay.append((path, ten_khoa, len(dong)))

    # ---- 3. Chi tiết 1 đơn: có object nhân viên đầy đủ không? ----------------
    # Đây là PHƯƠNG ÁN B nếu không có endpoint roster.
    code, data = goi(f"shops/{shop_id}/orders", page_size=1, page_number=1)
    if code == 200 and isinstance(data, dict):
        don_list = data.get("data") or []
        if don_list:
            don = don_list[0]
            print(f"\n===== Đơn mới nhất (id {don.get('id')}) — trường liên quan nhân viên:")
            for k in sorted(don.keys()):
                if any(t in k for t in ("seller", "care", "marketer", "user",
                                        "creator", "assign", "staff")):
                    print(f"      {k:26} = {json.dumps(don.get(k), ensure_ascii=False)[:110]}")

    http.close()
    print("\n" + "=" * 68)
    if thay:
        print("KẾT LUẬN: có endpoint roster ->", ", ".join(
            f"/{p} (khoá '{k}', {n} dòng)" for p, k, n in thay))
    else:
        print("KẾT LUẬN: KHÔNG đường nào trả roster -> phải dùng phương án B "
              "(rút tên nhân viên từ chi tiết đơn).")
    print("Chỉ gọi GET, không ghi gì lên POS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
