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


# --------------------------------------------------------------- Ads Manager
# Cây quảng cáo + CHI PHÍ nằm ở đây, KHÔNG cần Facebook Ads API riêng (dò 01/08):
#   ad_accounts · campaigns_v2 · ad_sets_v2 · ads_v2
# Mỗi dòng kèm `insights` (spend/impressions/clicks/reach/cpc/cpm/ctr/frequency)
# TỔNG HỢP theo khoảng start_time..end_time (unix giây) truyền vào — muốn số theo
# ngày thì hỏi từng ngày một (xem ads_sync.dong_bo_chi_phi).
async def list_ad_accounts(*, shop_id: str | int | None = None) -> list[dict]:
    """Tài khoản quảng cáo ĐÃ NỐI vào shop POS. Chưa nối = không có chi phí."""
    data = await _get(f"shops/{_shop_id(shop_id)}/ads_manager/ad_accounts",
                      {"page": 1, "page_size": 100})
    return [a for a in data.get("data") or [] if isinstance(a, dict)]


async def _ads_manager(
    duong: str, *, shop_id: str | int | None = None,
    start_time: int | None = None, end_time: int | None = None,
    page_size: int = 100, max_trang: int = 50,
) -> list[dict]:
    """Lật hết trang của một endpoint ads_manager, trả list dòng đã gộp."""
    ra: list[dict] = []
    trang = 1
    while trang <= max_trang:
        params: dict = {"page": trang, "page_size": min(page_size, 100)}
        if start_time is not None:
            params["start_time"] = int(start_time)
        if end_time is not None:
            params["end_time"] = int(end_time)
        data = await _get(f"shops/{_shop_id(shop_id)}/ads_manager/{duong}", params)
        mot_trang = [x for x in data.get("data") or [] if isinstance(x, dict)]
        ra.extend(mot_trang)
        if not mot_trang or trang >= int(data.get("total_pages") or 1):
            break
        trang += 1
    return ra


async def list_ad_campaigns(**kw) -> list[dict]:
    """Chiến dịch + insights trong khoảng thời gian."""
    return await _ads_manager("campaigns_v2", **kw)


async def list_ad_sets(**kw) -> list[dict]:
    """Nhóm quảng cáo + insights."""
    return await _ads_manager("ad_sets_v2", **kw)


async def list_ads(**kw) -> list[dict]:
    """Quảng cáo + insights, KÈM ad_campaign / ad_set / ad_creative của từng ad —
    một lời gọi này dựng được cả cây, không phải ghép tay 3 endpoint."""
    return await _ads_manager("ads_v2", **kw)


async def get_order(order_id: int | str, *, shop_id: str | int | None = None) -> dict:
    """Chi tiết 1 đơn theo id POS (id chạy theo shop, ví dụ 54307)."""
    data = await _get(f"shops/{_shop_id(shop_id)}/orders/{order_id}")
    don = data.get("data") or data.get("order") or {}
    if not isinstance(don, dict) or not don:
        raise PancakePosError(f"POS không trả đơn {order_id}")
    return don
