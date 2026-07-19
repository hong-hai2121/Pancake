"""Gửi câu trả lời qua Facebook Send API (Graph).

Thuộc luồng Facebook trực tiếp (không phải Pancake). Hiện app dùng Pancake để
gửi tin nên module này đang không được gọi tới; giữ lại để dùng nếu sau này
nối lại webhook/Send API của Meta.
"""

import httpx

from app.config import settings

# Endpoint Send API của Meta (v19.0). "me" = chính page ứng với page access token.
GRAPH_API_URL = "https://graph.facebook.com/v19.0/me/messages"


async def send_text(recipient_id: str, text: str) -> None:
    """Gửi một tin nhắn văn bản tới người dùng (theo PSID `recipient_id`).

    `messaging_type=RESPONSE` = đang trả lời tin khách vừa gửi (nằm trong cửa sổ
    24h của Messenger). Ném lỗi nếu Graph trả HTTP != 2xx (raise_for_status).
    """
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }
    # Token page đính kèm ở query string theo yêu cầu của Graph API.
    params = {"access_token": settings.fb_page_access_token}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(GRAPH_API_URL, params=params, json=payload)
        resp.raise_for_status()   # 4xx/5xx -> ném HTTPStatusError để nơi gọi biết


async def send_typing_on(recipient_id: str) -> None:
    """Bật báo 'đang soạn tin' cho tự nhiên hơn (tùy chọn, lỗi thì bỏ qua).

    Khác `send_text`: không check status vì đây chỉ là hiệu ứng phụ, thất bại
    cũng không ảnh hưởng việc trả lời.
    """
    payload = {"recipient": {"id": recipient_id}, "sender_action": "typing_on"}
    params = {"access_token": settings.fb_page_access_token}

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(GRAPH_API_URL, params=params, json=payload)
