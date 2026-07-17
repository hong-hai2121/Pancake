"""Client gọi Pancake API (pages.fm) bằng access token trong .env."""

import base64
import binascii
import json

import httpx

from app.config import settings

# Nhãn tiếng Việt cho từng nhóm page mà Pancake trả về trong `categorized`.
# Bỏ qua `activated_page_ids` vì đó là list id, không phải list page.
_GROUPS: list[tuple[str, str]] = [
    ("activated", "Đang hoạt động"),
    ("inactivated", "Chưa kích hoạt"),
    ("hidden", "Đang ẩn"),
    ("nopermission", "Không có quyền"),
]


class PancakeError(RuntimeError):
    """Lỗi khi gọi Pancake API (HTTP lỗi hoặc success=false)."""


async def _get(path: str, params: dict | None = None) -> dict:
    """GET tới Pancake API, tự đính kèm access_token, trả về JSON dict."""
    if not settings.pancake_access_token:
        raise PancakeError("Chưa cấu hình PANCAKE_ACCESS_TOKEN trong .env")

    query = dict(params or {})
    query["access_token"] = settings.pancake_access_token
    url = f"{settings.pancake_base_url.rstrip('/')}/{path.lstrip('/')}"

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, params=query)

    if resp.status_code != 200:
        raise PancakeError(f"Pancake API HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except ValueError as exc:  # trả HTML/không phải JSON -> sai endpoint/token
        raise PancakeError("Pancake API không trả về JSON (kiểm tra base_url/token)") from exc

    if isinstance(data, dict) and data.get("success") is False:
        raise PancakeError(f"Pancake API báo lỗi: {data}")
    return data


def _normalize(page: dict, group_key: str, group_label: str) -> dict:
    """Rút gọn 1 page về các field cần cho webview."""
    return {
        "id": str(page.get("id", "")),
        "name": page.get("name") or "(không tên)",
        "platform": page.get("platform") or "unknown",
        "username": page.get("username"),
        "shop_id": page.get("shop_id"),
        "role": page.get("role_in_page"),
        "is_activated": bool(page.get("is_activated")),
        "group": group_key,
        "group_label": group_label,
    }


async def list_pages() -> list[dict]:
    """Trả về danh sách page mà access token có quyền truy cập.

    Mỗi phần tử là dict đã chuẩn hóa (xem `_normalize`), gắn kèm nhóm
    (đang hoạt động / chưa kích hoạt / ẩn / không quyền).
    """
    data = await _get("pages")
    categorized = data.get("categorized", {}) or {}

    pages: list[dict] = []
    for key, label in _GROUPS:
        for page in categorized.get(key, []) or []:
            if isinstance(page, dict):
                pages.append(_normalize(page, key, label))
    return pages


def token_owner() -> dict:
    """Giải mã payload JWT của access token để biết chủ token (không cần mạng).

    Trả về {} nếu không giải mã được — chỉ dùng để hiển thị, không dùng xác thực.
    """
    token = settings.pancake_access_token
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # pad base64url
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (IndexError, ValueError, binascii.Error):
        return {}
    return {
        "name": payload.get("fb_name") or payload.get("name"),
        "fb_id": payload.get("fb_id"),
        "exp": payload.get("exp"),
    }
