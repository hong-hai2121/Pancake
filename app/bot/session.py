"""Quản lý phiên: đọc/reset trang_thai_khach, mở phiên mới."""

from app.db.queries import load_customer_state, upsert_customer_state


def _new_session(sender_id: str) -> dict:
    return {"sender_id": sender_id, "trang_thai": "moi", "history": []}


async def get_session(sender_id: str) -> dict:
    """Đọc trạng thái khách; nếu chưa có thì mở phiên mới."""
    state = await load_customer_state(sender_id)
    return state or _new_session(sender_id)


async def save_session(sender_id: str, session: dict) -> None:
    await upsert_customer_state(sender_id, session)


async def reset_session(sender_id: str) -> None:
    await upsert_customer_state(sender_id, _new_session(sender_id))
