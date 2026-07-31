"""Gửi tin Telegram khi worker cảm xúc phát hiện khách "negative".

Trước ở `ZPancake/server/telegram.py`, nay nằm hẳn trong app này. Khác bản cũ ở
chỗ đọc cấu hình qua `settings` (pydantic-settings, cùng `.env` với cả app) thay
vì `os.getenv` — bản cũ phải nạp `.env` bằng `load_dotenv` trước khi import, quên
là im lặng không gửi mà chẳng báo lỗi gì.

Thiếu `TELEGRAM_BOT_TOKEN` hoặc `TELEGRAM_CHAT_ID` -> tắt hẳn tính năng:
`send_negative_alert()` return luôn, không gửi và không báo lỗi.
"""

import httpx

from app.config import settings

TELEGRAM_API_BASE = "https://api.telegram.org"

# Ký tự Telegram MarkdownV2 bắt buộc escape; không escape thì tin có chứa 1 trong
# số này (rất dễ gặp trong tiếng Việt, vd dấu chấm/gạch ngang) bị Telegram trả
# 400 "can't parse entities" và không gửi được.
_MARKDOWN_V2_SPECIAL = set(r"_*[]()~`>#+-=|{}.!\\")


def escape_markdown(text: str) -> str:
    return "".join(f"\\{ch}" if ch in _MARKDOWN_V2_SPECIAL else ch for ch in text)


def da_cau_hinh() -> str:
    """Chat id đang cấu hình ("" = chưa đủ cấu hình -> tính năng đang TẮT)."""
    if not settings.telegram_bot_token:
        return ""
    return (settings.telegram_chat_id or "").strip()


async def gui(text: str) -> None:
    """Gửi 1 tin MarkdownV2. Ném lỗi ra ngoài — nơi gọi tự quyết nuốt hay báo."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/sendMessage",
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "MarkdownV2",
            },
        )
        resp.raise_for_status()


def dung_tin_canh_bao(
    *,
    name: str | None,
    snippet: str | None,
    platform: str | None,
    raw_id: str,
    page_id: str | None = None,
    conv_id: str | None = None,
    tu_khoa: list[str] | None = None,
) -> str:
    """Dựng nội dung tin cảnh báo (tách riêng để nút "Gửi tin thử" dùng lại)."""
    lines = [
        "⚠️ *Phát hiện khách hàng có cảm xúc tiêu cực*",
        f"*Khách:* {escape_markdown(name or 'Không rõ tên')}",
    ]
    if platform:
        lines.append(f"*Nền tảng:* {escape_markdown(platform)}")
    if snippet:
        lines.append(f"*Nội dung:* {escape_markdown(snippet)}")
    # Từ khoá đã làm bung cảnh báo — không có nó thì nhận tin xong vẫn phải mở
    # giao diện mới biết vì sao câu này bị bắt (nhất là khi báo nhầm).
    if tu_khoa:
        lines.append(f"*Khớp từ:* {escape_markdown(', '.join(tu_khoa))}")
    # Luôn kèm mã định danh để đối chiếu với giao diện / DOM Pancake.
    lines.append(f"*Raw ID:* {escape_markdown(raw_id)}")
    if page_id:
        lines.append(f"*Page ID:* {escape_markdown(page_id)}")
    if conv_id:
        lines.append(f"*Conv ID:* {escape_markdown(conv_id)}")
    return "\n".join(lines)


async def send_negative_alert(
    *,
    name: str | None,
    snippet: str | None,
    platform: str | None,
    raw_id: str,
    page_id: str | None = None,
    conv_id: str | None = None,
    tu_khoa: list[str] | None = None,
) -> None:
    """Báo 1 ca tiêu cực. Chưa cấu hình -> bỏ qua. Lỗi mạng -> nuốt + in log.

    CỐ Ý nuốt lỗi: một lần Telegram hỏng không được phép làm chết worker quét,
    vì việc ghi sổ và cập nhật kho quan trọng hơn cái tin báo.
    """
    if not da_cau_hinh():
        return
    text = dung_tin_canh_bao(
        name=name, snippet=snippet, platform=platform, raw_id=raw_id,
        page_id=page_id, conv_id=conv_id, tu_khoa=tu_khoa,
    )
    try:
        await gui(text)
    except Exception as err:  # noqa: BLE001
        print(f"[telegram] Gửi thông báo thất bại: {err}", flush=True)
