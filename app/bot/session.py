"""Quản lý phiên hội thoại của khách cho LUỒNG nhiều bước (bảng trang_thai_khach).

Bọc quanh 2 hàm DB (load/upsert_customer_state) và thêm khái niệm "phiên mới".
Một khách được định danh bằng cặp **(page_id, psid)** — đúng khoá duy nhất của
bảng. Session là dict theo đúng cột bảng:

    page_id, psid, kich_ban (đang theo luồng nào / None), buoc_hien_tai (bước hiện
    tại / None), ngu_canh (jsonb gom dữ liệu + lịch sử), trang_thai ('active'…).

Dùng cho động cơ luồng `bot/flow.next_step` + bot tự động Tầng 2. Nút "Gợi ý trả
lời" hiện KHÔNG dùng phiên (stateless).
"""

from app.db.queries import load_customer_state, upsert_customer_state


def _new_session(page_id: str, psid: str) -> dict:
    """Phiên rỗng cho khách mới: chưa vào kịch bản nào, ngữ cảnh trống."""
    return {
        "page_id": str(page_id),
        "psid": str(psid),
        "kich_ban": None,
        "buoc_hien_tai": None,
        "ngu_canh": {},
        "trang_thai": "active",
    }


async def get_session(page_id: str, psid: str) -> dict:
    """Đọc phiên khách theo (page_id, psid); chưa có thì mở phiên mới."""
    state = await load_customer_state(page_id, psid)
    return state or _new_session(page_id, psid)


async def save_session(page_id: str, psid: str, session: dict) -> None:
    """Ghi (tạo/cập nhật) phiên hiện tại của khách xuống DB."""
    await upsert_customer_state(page_id, psid, session)


async def reset_session(page_id: str, psid: str) -> None:
    """Xoá tiến trình cũ: ghi đè bằng phiên mới tinh (bắt đầu lại luồng)."""
    await upsert_customer_state(page_id, psid, _new_session(page_id, psid))
