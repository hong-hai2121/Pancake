"""Client gọi Pancake API (pages.fm) bằng access token trong .env."""

import base64
import binascii
import json
import re
from html import unescape

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


def _handle(resp: httpx.Response) -> dict:
    """Kiểm tra response Pancake, trả JSON dict hoặc raise PancakeError."""
    if resp.status_code != 200:
        raise PancakeError(f"Pancake API HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except ValueError as exc:  # trả HTML/không phải JSON -> sai endpoint/token
        raise PancakeError("Pancake API không trả về JSON (kiểm tra base_url/token)") from exc

    if isinstance(data, dict) and data.get("success") is False:
        raise PancakeError(data.get("message") or f"Pancake API báo lỗi: {data}")
    return data


def _url(path: str) -> str:
    """Ghép base_url + path thành URL đầy đủ (chuẩn hóa dấu '/')."""
    return f"{settings.pancake_base_url.rstrip('/')}/{path.lstrip('/')}"


def _with_token(params: dict | None) -> dict:
    """Sao chép params và tự đính kèm access_token; lỗi nếu chưa cấu hình token."""
    if not settings.pancake_access_token:
        raise PancakeError("Chưa cấu hình PANCAKE_ACCESS_TOKEN trong .env")
    query = dict(params or {})
    query["access_token"] = settings.pancake_access_token
    return query


async def _get(path: str, params: dict | None = None) -> dict:
    """GET tới Pancake API, tự đính kèm access_token, trả về JSON dict."""
    query = _with_token(params)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(_url(path), params=query)
    return _handle(resp)


async def _post(path: str, params: dict | None = None) -> dict:
    """POST tới Pancake API (access_token + params ở query string)."""
    query = _with_token(params)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(_url(path), params=query)
    return _handle(resp)


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


async def get_page(page_id: str) -> dict | None:
    """Tìm 1 page theo id trong danh sách page token có quyền (best-effort)."""
    for page in await list_pages():
        if page["id"] == str(page_id):
            return page
    return None


def _normalize_conv(conv: dict) -> dict:
    """Rút gọn 1 conversation về các field cần cho webview 'người nhắn tin'."""
    customer = (conv.get("customers") or [{}])[0]
    frm = conv.get("from") or {}
    return {
        "conv_id": str(conv.get("id", "")),
        "customer_id": str(customer.get("id") or ""),
        "name": customer.get("name") or frm.get("name") or "(không tên)",
        "fb_id": str(customer.get("fb_id") or frm.get("id") or ""),
        "snippet": unescape(conv.get("snippet") or "").strip(),
        "updated_at": conv.get("updated_at") or "",
        "message_count": int(conv.get("message_count") or 0),
        "unread_count": int(conv.get("unread_count") or 0),
        "seen": bool(conv.get("seen")),
    }


async def list_conversations(
    page_id: str, msg_type: str = "INBOX", limit: int | None = None
) -> list[dict]:
    """Danh sách hội thoại của 1 page, mới nhất trước.

    `msg_type` = "INBOX" (tin nhắn riêng) hoặc "COMMENT" (bình luận).
    Mỗi phần tử đã chuẩn hóa (xem `_normalize_conv`).
    """
    data = await _get(f"pages/{page_id}/conversations", {"type": msg_type})
    convs = data.get("conversations") or []
    items = [_normalize_conv(c) for c in convs if isinstance(c, dict)]
    items.sort(key=lambda c: c["updated_at"], reverse=True)
    if limit is not None:
        items = items[:limit]
    return items


def _plain_text(msg: dict) -> str:
    """Lấy nội dung text sạch: ưu tiên original_message, fallback bỏ tag HTML.

    Giữ lại xuống dòng (<br>, </div>) để hiển thị đúng trong khung chat.
    """
    text = msg.get("original_message")
    if not text:
        html = msg.get("message") or ""
        html = re.sub(r"(?i)<br\s*/?>", "\n", html)
        html = re.sub(r"(?i)</(div|p)>", "\n", html)
        text = unescape(re.sub(r"<[^>]+>", "", html))
    lines = [ln.strip() for ln in (text or "").splitlines()]
    return "\n".join(lines).strip()


def _normalize_msg(msg: dict, page_id: str) -> dict:
    """Rút gọn 1 message trong thread hội thoại."""
    frm = msg.get("from") or {}
    sender_id = str(frm.get("id") or "")
    attachments = []
    for att in msg.get("attachments") or []:
        if isinstance(att, dict):
            url = att.get("url") or att.get("image_url") or att.get("src")
            attachments.append({"type": att.get("type") or "file", "url": url})
    return {
        "id": str(msg.get("id") or ""),
        "sender_id": sender_id,
        "sender_name": frm.get("name") or "",
        "is_page": sender_id == str(page_id),
        "text": _plain_text(msg),
        "inserted_at": msg.get("inserted_at") or "",
        "attachments": attachments,
    }


async def get_conversation(
    page_id: str, conv_id: str, customer_id: str | None = None
) -> dict:
    """Toàn bộ tin nhắn của 1 hội thoại, sắp xếp cũ -> mới.

    Trả về {conv_id, customer_name, messages: [...]}.
    """
    params = {"customer_id": customer_id} if customer_id else None
    data = await _get(f"pages/{page_id}/conversations/{conv_id}/messages", params)
    raw = data.get("messages") or []
    msgs = [_normalize_msg(m, page_id) for m in raw if isinstance(m, dict)]
    msgs.sort(key=lambda m: m["inserted_at"])
    customer_name = next(
        (m["sender_name"] for m in reversed(msgs) if not m["is_page"] and m["sender_name"]),
        "",
    )
    return {"conv_id": conv_id, "customer_name": customer_name, "messages": msgs}


async def send_message(
    page_id: str, conv_id: str, message: str, customer_id: str | None = None
) -> dict:
    """Gửi 1 tin nhắn trả lời vào hội thoại (action=reply_inbox).

    ⚠️ Đây là hành động GỬI THẬT tới khách qua Pancake — không hoàn tác được.
    """
    params = {"action": "reply_inbox", "message": message}
    if customer_id:
        params["customer_id"] = customer_id
    return await _post(f"pages/{page_id}/conversations/{conv_id}/messages", params)


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
