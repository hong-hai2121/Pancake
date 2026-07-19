"""Quản lý phiên hội thoại của khách: đọc / mở mới / lưu / reset.

Bọc quanh 2 hàm DB (load/upsert_customer_state) và thêm khái niệm "phiên mới".
Một `session` là dict gồm: sender_id, trang_thai (bước hiện tại), history (list
cặp hỏi–đáp).

⚠️ Lưu ý: schema thật của bảng trang_thai_khach (page_id/psid/ngu_canh) khác với
cấu trúc session ở đây (sender_id/du_lieu/history) — cần căn lại khi nối bot poll.
"""

from app.db.queries import load_customer_state, upsert_customer_state


def _new_session(sender_id: str) -> dict:
    """Tạo phiên rỗng cho khách mới: trạng thái 'moi', lịch sử trống."""
    return {"sender_id": sender_id, "trang_thai": "moi", "history": []}


async def get_session(sender_id: str) -> dict:
    """Đọc trạng thái khách từ DB; nếu chưa có thì mở phiên mới."""
    state = await load_customer_state(sender_id)
    return state or _new_session(sender_id)


async def save_session(sender_id: str, session: dict) -> None:
    """Ghi (tạo/cập nhật) phiên hiện tại của khách xuống DB."""
    await upsert_customer_state(sender_id, session)


async def reset_session(sender_id: str) -> None:
    """Xoá tiến trình cũ: ghi đè bằng một phiên mới tinh (bắt đầu lại kịch bản)."""
    await upsert_customer_state(sender_id, _new_session(sender_id))
