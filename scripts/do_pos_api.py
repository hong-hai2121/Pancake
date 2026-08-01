"""Dò Pancake POS Open API bằng api_key trong .env (bắt buộc trước B7 — xem docs/TIEN-DO.md).

Chạy:  python scripts/do_pos_api.py

Đọc PANCAKE_POS_API_KEY / PANCAKE_POS_SHOP_ID / PANCAKE_POS_BASE_URL từ .env rồi
gọi thử lần lượt: /shops -> orders -> customers -> products/variations, in ra
cấu trúc dữ liệu THẬT của shop mình (spec là một chuyện, dữ liệu thật là chuyện
khác). Chỉ GET, không tạo/sửa gì trên POS.

Cố tình KHÔNG import app.* để chạy được độc lập cả khi app chưa cấu hình xong
(script dò một lần rồi thôi; client chính thức sẽ nằm ở app/integrations/pancake_pos/).
"""

import json
import sys
from pathlib import Path

import httpx

GOC = Path(__file__).resolve().parent.parent

# Base dự phòng: shop chạy trên pos.pancake.vn (domain VN) — cùng hệ thống với
# pos.pages.fm nhưng nếu base chính bị chặn/401 thì thử base kia.
BASE_DU_PHONG = ["https://pos.pages.fm/api/v1", "https://pos.pancake.vn/api/v1"]


def doc_env() -> dict[str, str]:
    """Đọc .env ở gốc project thành dict (đủ dùng cho script, không cần lib)."""
    env: dict[str, str] = {}
    for line in (GOC / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def che(key: str) -> str:
    """Che bớt api_key khi in ra màn hình/log."""
    return f"{key[:6]}…{key[-4:]}" if len(key) > 12 else "•" * len(key)


def main() -> int:
    env = doc_env()
    api_key = env.get("PANCAKE_POS_API_KEY", "")
    shop_id = env.get("PANCAKE_POS_SHOP_ID", "")
    if not api_key or not shop_id:
        print("Thiếu PANCAKE_POS_API_KEY / PANCAKE_POS_SHOP_ID trong .env")
        return 1

    bases = [env["PANCAKE_POS_BASE_URL"]] if env.get("PANCAKE_POS_BASE_URL") else []
    bases += [b for b in BASE_DU_PHONG if b not in bases]

    http = httpx.Client(timeout=30, headers={"Accept": "application/json"})

    def goi(base: str, path: str, **params) -> tuple[int, dict | str]:
        """GET 1 endpoint POS, tự đính api_key. Trả (status_code, json|text)."""
        resp = http.get(
            f"{base}/{path.lstrip('/')}", params={"api_key": api_key, **params}
        )
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text[:200]

    # ---- Bước 1: tìm base chạy được bằng GET /shops --------------------------
    base_ok, shops = None, None
    for base in bases:
        code, data = goi(base, "shops")
        print(f"GET {base}/shops -> HTTP {code}")
        if code == 200 and isinstance(data, dict) and data.get("success", True):
            base_ok, shops = base, data
            break
        print(f"   {str(data)[:200]}")
    if base_ok is None:
        print(f"\nKhông base nào chạy với key {che(api_key)} — kiểm tra key còn 'Bật' không.")
        return 1

    print(f"\n===== Base dùng được: {base_ok} (key {che(api_key)})")
    for s in shops.get("shops", []):
        print(f"  shop {s.get('id')} — {s.get('name')} — {len(s.get('pages') or [])} page liên kết")

    # ---- Bước 2: đơn hàng ----------------------------------------------------
    code, data = goi(base_ok, f"shops/{shop_id}/orders", page_size=5, page_number=1)
    print(f"\n===== GET /shops/{shop_id}/orders?page_size=5 -> HTTP {code}")
    if isinstance(data, dict):
        print(f"  tổng đơn: {data.get('total_entries')} | tổng trang: {data.get('total_pages')}")
        don_hang = data.get("data") or data.get("orders") or []
        if don_hang:
            don = don_hang[0]
            print(f"  1 đơn có {len(don)} trường: {sorted(don.keys())}")
            print("\n  --- Các trường quan trọng cho B7 (đơn mới nhất):")
            for k in ("id", "system_id", "status", "status_name", "inserted_at",
                      "conversation_id", "page_id", "post_id", "ad_id",
                      "bill_full_name", "bill_phone_number", "total_price",
                      "cod", "order_sources_name"):
                if k in don:
                    print(f"      {k:20} = {json.dumps(don.get(k), ensure_ascii=False)[:80]}")
            items = don.get("items") or []
            if items and isinstance(items[0], dict):
                print(f"      items[0] có {len(items[0])} trường: {sorted(items[0].keys())[:15]}")
        else:
            print("  (shop chưa có đơn nào)")
    else:
        print(f"  {data}")

    # ---- Bước 3: khách + sản phẩm (mỗi thứ 2 dòng, chỉ xem shape) ------------
    for ten, path, tham_so in [
        ("khách hàng", f"shops/{shop_id}/customers", {"page_size": 2}),
        ("mẫu mã sản phẩm", f"shops/{shop_id}/products/variations", {"page_size": 2}),
    ]:
        code, data = goi(base_ok, path, **tham_so)
        print(f"\n===== GET /{path} -> HTTP {code}")
        if isinstance(data, dict):
            dong = data.get("data") or []
            print(f"  tổng {ten}: {data.get('total_entries')}")
            if dong:
                print(f"  1 dòng có {len(dong[0])} trường: {sorted(dong[0].keys())}")
        else:
            print(f"  {data}")

    http.close()
    print("\nDò xong. KHÔNG gọi endpoint ghi (POST/PUT) nào.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
