"""Công tắc BẬT/TẮT + chọn cách quét cho worker cảm xúc — đổi ngay lúc đang chạy.

Vì sao không dùng thẳng `.env`: `SENTIMENT_ENABLED` / `SENTIMENT_METHOD` chỉ được
đọc MỘT lần lúc khởi động (pydantic-settings + biến module của ZPancake), nên đổi
là phải restart server. Công tắc ở đây lưu ra `sentiment_switch.json` và được
worker đọc lại MỖI vòng lặp → bấm nút trên giao diện là có tác dụng ngay.

Giá trị mặc định khi chưa có file: lấy theo `.env` (`SENTIMENT_ENABLED`,
`SENTIMENT_METHOD`) — nên hành vi của bản cũ giữ nguyên cho tới khi bạn bấm nút
lần đầu. Cùng kiểu với công tắc BẬT/TẮT page ở `app/pancake/switches.py`.
"""

import json
import os
from pathlib import Path

from app.config import settings

# app/workers/switch.py -> parents[2] = gốc project (giống page_switches.json)
_FILE = Path(__file__).resolve().parents[2] / "sentiment_switch.json"

_CACH_QUET_HOP_LE = ("keyword", "llm")

_cache: dict | None = None   # None = chưa nạp


def _mac_dinh() -> dict:
    """Giá trị khi chưa từng bấm nút: theo .env."""
    method = (os.getenv("SENTIMENT_METHOD") or "keyword").strip().lower()
    return {
        "bat": bool(settings.sentiment_enabled),
        "cach_quet": method if method in _CACH_QUET_HOP_LE else "keyword",
    }


def _load() -> dict:
    """Đọc file; thiếu/hỏng -> mặc định theo .env (không làm gãy worker)."""
    data = _mac_dinh()
    try:
        raw = json.loads(_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return data
    if isinstance(raw, dict):
        if isinstance(raw.get("bat"), bool):
            data["bat"] = raw["bat"]
        if raw.get("cach_quet") in _CACH_QUET_HOP_LE:
            data["cach_quet"] = raw["cach_quet"]
    return data


def _state() -> dict:
    """Trạng thái hiện tại (nạp 1 lần rồi giữ trong RAM)."""
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def _save() -> None:
    """Ghi xuống file (best-effort; lỗi ghi không được làm gãy luồng chính)."""
    try:
        _FILE.write_text(
            json.dumps(_state(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def is_on() -> bool:
    """Worker cảm xúc có đang được phép quét không."""
    return bool(_state()["bat"])


def set_on(bat: bool) -> bool:
    """Đặt BẬT/TẮT rồi lưu. Trả về trạng thái mới."""
    _state()["bat"] = bool(bat)
    _save()
    return is_on()


def toggle() -> bool:
    """Lật công tắc; trả về trạng thái MỚI (True = đang quét)."""
    return set_on(not is_on())


def cach_quet() -> str:
    """Cách quét đang chọn: "keyword" (miễn phí) hoặc "llm" (gọi OpenAI)."""
    return _state()["cach_quet"]


def set_cach_quet(value: str) -> str:
    """Đổi cách quét (bỏ qua giá trị lạ). Trả về giá trị đang dùng sau khi đổi."""
    value = (value or "").strip().lower()
    if value in _CACH_QUET_HOP_LE:
        _state()["cach_quet"] = value
        _save()
    return cach_quet()
