"""Điều phối: nhận 1 sự kiện messaging -> gọi bot -> gửi trả lời."""

from app.bot.brain import generate_reply
from app.messenger.send_api import send_text


async def handle_event(event: dict) -> None:
    sender_id = event.get("sender", {}).get("id")
    message = event.get("message", {})
    text = message.get("text")

    # Bỏ qua sự kiện không phải tin nhắn văn bản (echo, delivery, read...).
    if not sender_id or not text or message.get("is_echo"):
        return

    reply = await generate_reply(sender_id, text)
    if reply:
        await send_text(sender_id, reply)
