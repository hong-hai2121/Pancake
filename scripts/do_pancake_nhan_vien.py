"""Dò xem Pancake pages.fm có trả DANH SÁCH NHÂN VIÊN không (song song với POS).

Chạy:  python scripts/do_pancake_nhan_vien.py

Bên POS đã có `GET /shops/{id}/users` (xem scripts/do_pos_nhan_vien.py). Bên
pages.fm xác thực KHÁC HẲN: JWT người dùng trong `PANCAKE_ACCESS_TOKEN` chứ
không phải api_key theo shop, và nhiều route trả 406/HTML thay vì JSON.

LƯU Ý theo đúng cảnh báo trong app/integrations/pancake/client.py: KHÔNG gửi
header `Accept: application/json` — Pancake đổi hành vi theo header đó, route
không phải API sẽ trả 406 thay vì HTML, làm sai kết luận dò.

Chỉ GET, không tạo/sửa gì.
"""

import json
import sys
from pathlib import Path

import httpx

GOC = Path(__file__).resolve().parent.parent

# Đường ứng viên. {pid} = page_id. Đường không có {pid} là cấp tài khoản.
DUONG_UNG_VIEN = [
    "me",
    "users/me",
    "users",
    "pages/{pid}/users",
    "pages/{pid}/staffs",
    "pages/{pid}/members",
    "pages/{pid}/agents",
    "pages/{pid}/settings",          # thẻ lấy được ở đây -> biết đâu có cả người
]

TRUONG_NGUOI = ("id", "user_id", "name", "fullname", "email", "phone_number",
                "phone", "role", "avatar_url")


def doc_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (GOC / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def che(v: str) -> str:
    return f"{v[:6]}…{v[-4:]}" if len(v) > 12 else "•" * len(v)


def co_ve_la_nguoi(d: dict) -> bool:
    """Dict này trông có phải hồ sơ một con người không (có tên/email/uuid)?"""
    return isinstance(d, dict) and any(k in d for k in ("name", "fullname", "email"))


def soi(nut, duong: str, sau: int = 0, toi_da: int = 4) -> list[tuple[str, dict]]:
    """Lần xuống JSON tìm mọi list-of-dict trông giống danh sách người.

    Pancake gói dữ liệu mỗi endpoint một kiểu (data / users / categorized…),
    nên dò mù bằng cách đi hết cây thay vì đoán tên khoá."""
    thay: list[tuple[str, dict]] = []
    if sau > toi_da:
        return thay
    if isinstance(nut, list):
        if nut and isinstance(nut[0], dict) and co_ve_la_nguoi(nut[0]):
            thay.append((duong, nut[0]))
        elif nut and isinstance(nut[0], (dict, list)):
            thay += soi(nut[0], f"{duong}[0]", sau + 1, toi_da)
    elif isinstance(nut, dict):
        for k, v in nut.items():
            thay += soi(v, f"{duong}.{k}" if duong else k, sau + 1, toi_da)
    return thay


def main() -> int:
    env = doc_env()
    token = env.get("PANCAKE_ACCESS_TOKEN", "")
    base = env.get("PANCAKE_BASE_URL", "https://pages.fm/api/v1").rstrip("/")
    if not token:
        print("Thiếu PANCAKE_ACCESS_TOKEN trong .env")
        return 1

    # KHÔNG set Accept — xem docstring.
    http = httpx.Client(timeout=30, follow_redirects=False)

    def goi(path: str, **params):
        resp = http.get(f"{base}/{path.lstrip('/')}",
                        params={"access_token": token, **params})
        ct = resp.headers.get("content-type", "")
        if "json" not in ct:
            return resp.status_code, f"(không phải JSON · {ct}) {resp.text[:120]}"
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text[:160]

    print(f"Base {base} · token {che(token)}\n")

    # Lấy 1 page_id thật để thử các đường có {pid}
    code, data = goi("pages")
    pid = ""
    if code == 200 and isinstance(data, dict):
        cat = (data.get("categorized") or {})
        for nhom in ("activated", "inactivated", "hidden"):
            ds = cat.get(nhom) or []
            if ds and isinstance(ds[0], dict):
                pid = str(ds[0].get("id") or "")
                print(f"Dùng page mẫu: {pid} — {ds[0].get('name')}")
                break
    if not pid:
        print(f"Không lấy được page_id mẫu (GET /pages -> HTTP {code}); "
              "các đường có {pid} sẽ bị bỏ qua.")

    thay_gi = []
    for mau in DUONG_UNG_VIEN:
        if "{pid}" in mau and not pid:
            continue
        path = mau.format(pid=pid)
        code, data = goi(path)
        print(f"\n===== GET /{path} -> HTTP {code}")
        if code != 200 or not isinstance(data, dict):
            print(f"  {str(data)[:170]}")
            continue
        print(f"  keys = {sorted(data.keys())[:14]}")
        ung_vien = soi(data, "")
        if not ung_vien:
            print("  (không thấy list nào trông giống danh sách người)")
            continue
        for duong, mau_dong in ung_vien[:3]:
            print(f"  ==> {duong or '(gốc)'} trông giống danh sách người:")
            print(f"      trường: {sorted(mau_dong.keys())[:16]}")
            for k in TRUONG_NGUOI:
                if k in mau_dong and not isinstance(mau_dong[k], (dict, list)):
                    print(f"        {k:13} = "
                          f"{json.dumps(mau_dong.get(k), ensure_ascii=False)[:80]}")
            thay_gi.append((path, duong))

    http.close()
    print("\n" + "=" * 68)
    if thay_gi:
        print("KẾT LUẬN: pages.fm CÓ chỗ lấy được người ->")
        for p, d in thay_gi:
            print(f"   /{p} tại {d or '(gốc)'}")
    else:
        print("KẾT LUẬN: pages.fm KHÔNG trả danh sách nhân viên qua JWT này.")
    print("Chỉ gọi GET, không ghi gì lên Pancake.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
