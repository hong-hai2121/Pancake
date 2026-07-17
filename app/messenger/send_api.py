"""Gửi câu trả lời qua Facebook Send API."""

import httpx

from app.config import settings

GRAPH_API_URL = "https://graph.facebook.com/v19.0/me/messages"


async def send_text(recipient_id: str, text: str) -> None:
    """Gửi một tin nhắn văn bản tới người dùng."""
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }
    params = {"access_token": settings.fb_page_access_token}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(GRAPH_API_URL, params=params, json=payload)
        resp.raise_for_status()


async def send_typing_on(recipient_id: str) -> None:
    """Bật báo 'đang soạn tin' cho tự nhiên hơn (tùy chọn)."""
    payload = {"recipient": {"id": recipient_id}, "sender_action": "typing_on"}
    params = {"access_token": settings.fb_page_access_token}

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(GRAPH_API_URL, params=params, json=payload)
