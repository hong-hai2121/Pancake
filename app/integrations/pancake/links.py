"""Dựng link mở ĐÚNG hội thoại bên Pancake từ hồ sơ CRM (BRD mục 4).

Chỉ ghép chuỗi — KHÔNG gọi API (luật mục 4: "Không gọi API Pancake trực tiếp mỗi
lần mở màn hình"). Mẫu link đổi được bằng `PANCAKE_CONVERSATION_URL` trong .env
cho khỏi phải sửa code khi Pancake đổi đường dẫn:

    https://pancake.vn/{page_id}?c_id={conversation_id}

Hội thoại Pancake mang id dạng "<page_id>_<thread_id>"; phần sau dấu gạch dưới là
thứ giao diện Pancake cần, nên hàm dưới cắt sẵn.
"""

from app.core.config import settings


def link_hoi_thoai(external_page_id: str, external_conversation_id: str) -> str:
    """Link tới 1 hội thoại. Thiếu page hoặc hội thoại -> chuỗi rỗng (view ẩn nút)."""
    page = str(external_page_id or "").strip()
    conv = str(external_conversation_id or "").strip()
    if not (page and conv):
        return ""
    thread = conv.split("_", 1)[1] if "_" in conv else conv
    return (settings.pancake_conversation_url
            .replace("{page_id}", page)
            .replace("{conversation_id}", thread)
            .replace("{conversation_full_id}", conv))


def link_khach(external_page_id: str, external_customer_id: str) -> str:
    """Link tới hồ sơ khách bên Pancake (POS trả sẵn dạng này ở customer.conversation_link)."""
    page = str(external_page_id or "").strip()
    kh = str(external_customer_id or "").strip()
    if not (page and kh):
        return ""
    return f"https://pancake.vn/{page}?customer_id={kh}"
