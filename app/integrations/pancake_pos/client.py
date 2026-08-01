"""Client gọi Pancake POS Open API bằng api_key trong .env (B7).

Base: https://pos.pages.fm/api/v1 — spec 82 endpoint tại
https://docs.pancake.biz/pos/api/openapi.json (dò 01/08, scripts/do_pos_api.py).
Xác thực: query `api_key` (theo TỪNG shop), KHÔNG phải JWT của pages.fm.

Chỉ bọc các endpoint ĐỌC mà B7 cần: shops, orders. Dùng chung httpx client
keep-alive với luồng chat (app/integrations/pancake/client.py) — cùng vòng đời,
cùng chỗ đóng lúc shutdown, khỏi thêm một pool thứ hai.
"""

import httpx

from app.core.config import settings
from app.integrations.pancake.client import http


class PancakePosError(RuntimeError):
    """Lỗi khi gọi Pancake POS API (HTTP lỗi hoặc success=false)."""


def _shop_id(shop_id: str | int | None = None) -> str:
    """Shop id dùng cho lời gọi: tham số truyền vào > .env; thiếu cả hai -> lỗi."""
    sid = str(shop_id or settings.pancake_pos_shop_id or "").strip()
    if not sid:
        raise PancakePosError("Chưa cấu hình PANCAKE_POS_SHOP_ID trong .env")
    return sid


async def _get(path: str, params: dict | None = None) -> dict:
    """GET tới POS API, tự đính api_key, trả JSON dict hoặc raise PancakePosError."""
    if not settings.pancake_pos_api_key:
        raise PancakePosError("Chưa cấu hình PANCAKE_POS_API_KEY trong .env")
    query = dict(params or {})
    query["api_key"] = settings.pancake_pos_api_key
    url = f"{settings.pancake_pos_base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        resp = await http().get(url, params=query, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise PancakePosError(f"Không gọi được Pancake POS: {exc}") from exc

    if resp.status_code != 200:
        raise PancakePosError(f"Pancake POS HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise PancakePosError("Pancake POS không trả JSON (kiểm tra base_url/api_key)") from exc
    if isinstance(data, dict) and data.get("success") is False:
        raise PancakePosError(str(data.get("message") or f"Pancake POS báo lỗi: {data}")[:300])
    return data


async def list_shops() -> list[dict]:
    """Danh sách shop mà api_key truy cập được (mỗi shop kèm list page liên kết)."""
    data = await _get("shops")
    return [s for s in data.get("shops") or [] if isinstance(s, dict)]


async def list_orders(
    *,
    shop_id: str | int | None = None,
    page_number: int = 1,
    page_size: int = 100,
    since: int | None = None,
    until: int | None = None,
    update_status: str = "updated_at",
) -> dict:
    """Một trang đơn hàng của shop. Trả nguyên payload POS.

    Payload: {"data": [...], "total_entries": N, "total_pages": M, ...}.
    `since`/`until` = unix timestamp, lọc theo mốc `update_status`
    ("updated_at" — mặc định, dùng cho đồng bộ tăng dần; "inserted_at" — backfill
    theo ngày tạo). page_size trần 100 cho lành: POS phân trang chuẩn, kéo nhiều
    thì lật trang, không xin trang khổng lồ.
    """
    params: dict = {
        "page_number": page_number,
        "page_size": min(int(page_size), 100),
        "updateStatus": update_status,
    }
    if since is not None:
        params["startDateTime"] = int(since)
    if until is not None:
        params["endDateTime"] = int(until)
    return await _get(f"shops/{_shop_id(shop_id)}/orders", params)


async def get_order(order_id: int | str, *, shop_id: str | int | None = None) -> dict:
    """Chi tiết 1 đơn theo id POS (id chạy theo shop, ví dụ 54307)."""
    data = await _get(f"shops/{_shop_id(shop_id)}/orders/{order_id}")
    don = data.get("data") or data.get("order") or {}
    if not isinstance(don, dict) or not don:
        raise PancakePosError(f"POS không trả đơn {order_id}")
    return don
