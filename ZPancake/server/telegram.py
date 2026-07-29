"""Gửi thông báo Telegram khi worker cảm xúc (`sentiment.py` + `main.py`) phát
hiện 1 khách hàng "negative".

Cấu hình qua `.env`: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (xem hướng dẫn lấy 2
giá trị này ở `README.md`/`server/README.md`). Thiếu 1 trong 2 -> tắt tính
năng này, `send_negative_alert()` chỉ return luôn, không gửi gì và không báo
lỗi gì cả.
"""

import os

import httpx

TELEGRAM_API_BASE = "https://api.telegram.org"

# Các ký tự Telegram MarkdownV2 bắt buộc phải escape, nếu không tin nhắn có
# chứa 1 trong số này (rất dễ gặp trong snippet tiếng Việt, vd dấu chấm/gạch
# ngang) sẽ bị Telegram trả lỗi 400 "can't parse entities" và không gửi được.
_MARKDOWN_V2_SPECIAL = set(r"_*[]()~`>#+-=|{}.!\\")


def _escape_markdown(text: str) -> str:
    return "".join(f"\\{ch}" if ch in _MARKDOWN_V2_SPECIAL else ch for ch in text)


async def send_negative_alert(
    *,
    name: str | None,
    snippet: str | None,
    platform: str | None,
    raw_id: str,
    page_id: str | None = None,
    conv_id: str | None = None,
) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return

    lines = [
        "⚠️ *Phát hiện khách hàng có cảm xúc tiêu cực*",
        f"*Khách:* {_escape_markdown(name or 'Không rõ tên')}",
    ]
    if platform:
        lines.append(f"*Nền tảng:* {_escape_markdown(platform)}")
    if snippet:
        lines.append(f"*Nội dung:* {_escape_markdown(snippet)}")
    # Luôn kèm 3 mã định danh để tra cứu/đối chiếu với /history hoặc DOM Pancake
    # (raw_id = page_id + "_" + conv_id, nhưng vẫn để riêng cho dễ copy từng mã).
    lines.append(f"*Raw ID:* {_escape_markdown(raw_id)}")
    if page_id:
        lines.append(f"*Page ID:* {_escape_markdown(page_id)}")
    if conv_id:
        lines.append(f"*Conv ID:* {_escape_markdown(conv_id)}")
    text = "\n".join(lines)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"},
            )
            resp.raise_for_status()
    except Exception as err:  # noqa: BLE001 - lỗi Telegram không được làm chết sentiment_worker
        print(f"[telegram] Gửi thông báo thất bại: {err}")
