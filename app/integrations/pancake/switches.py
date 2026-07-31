"""Công tắc BẬT/TẮT từng page.

- BẬT (mặc định): mọi chức năng được phép LẤY và GỬI tin của page đó.
- TẮT: không lấy (list_conversations/get_conversation trả rỗng) và không gửi
  (send_message bị chặn) — áp cho MỌI nơi vì guard đặt trong pancake/client.py.

Trạng thái lưu ở `page_switches.json` (gốc project, đã gitignore) để giữ qua lần
chạy lại. Chỉ lưu danh sách page ĐÃ TẮT; page không có trong file = BẬT (giữ
nguyên hành vi cũ cho các page hiện có). Đọc/ghi qua cache trong RAM để không
chạm đĩa mỗi lần poll.
"""

import json

from app.core.paths import PROJECT_ROOT

_FILE = PROJECT_ROOT / "page_switches.json"

_off_cache: set[str] | None = None   # None = chưa nạp


def _load_off() -> set[str]:
    """Đọc danh sách page TẮT từ file; lỗi/không có -> tập rỗng."""
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    off = data.get("off") if isinstance(data, dict) else None
    return {str(x) for x in off} if isinstance(off, list) else set()


def _off() -> set[str]:
    """Tập page TẮT (nạp 1 lần rồi giữ trong RAM)."""
    global _off_cache
    if _off_cache is None:
        _off_cache = _load_off()
    return _off_cache


def _save() -> None:
    """Ghi cache xuống file (best-effort; lỗi ghi không làm gãy luồng chính)."""
    try:
        _FILE.write_text(
            json.dumps({"off": sorted(_off())}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def is_page_enabled(page_id: str) -> bool:
    """True nếu page được phép lấy/gửi tin (mặc định BẬT nếu chưa từng tắt)."""
    return str(page_id) not in _off()


def set_page_enabled(page_id: str, enabled: bool) -> None:
    """Đặt trạng thái BẬT/TẮT cho 1 page rồi lưu lại."""
    off = _off()
    if enabled:
        off.discard(str(page_id))
    else:
        off.add(str(page_id))
    _save()


def toggle_page(page_id: str) -> bool:
    """Lật trạng thái page; trả về trạng thái MỚI (True = BẬT)."""
    new_state = not is_page_enabled(page_id)
    set_page_enabled(page_id, new_state)
    return new_state


def enable_all() -> None:
    """BẬT lại TẤT CẢ page (xoá sạch danh sách tắt)."""
    _off().clear()
    _save()


def disable_all(page_ids) -> None:
    """TẮT tất cả page trong danh sách truyền vào (thường là toàn bộ page có quyền)."""
    off = _off()
    off.clear()
    off.update(str(x) for x in page_ids if x)
    _save()


def disabled_page_ids() -> set[str]:
    """Bản sao tập page đang TẮT (cho phần hiển thị)."""
    return set(_off())
