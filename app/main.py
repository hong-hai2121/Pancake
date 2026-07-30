"""Điểm khởi động ứng dụng: tạo FastAPI app và gắn các route.

Luồng hiện tại dùng POLLING qua Pancake (app/pancake) để nhận/ trả lời tin nhắn,
KHÔNG dùng webhook Facebook nữa — nên chỉ đăng ký `pancake_router`.
(Thư mục app/webhook đã bị bỏ; nếu sau này muốn dùng lại webhook Graph thì thêm
router tương ứng vào đây.)
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.data.routes import router as data_router
from app.pancake.client import close_http
from app.pancake.routes import router as pancake_router
from app.ui.routes import router as ui_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Dọn tài nguyên khi tắt server.

    Client HTTP tới Pancake được dùng CHUNG cho cả vòng đời app (giữ keep-alive,
    đỡ bắt tay TLS mỗi request — xem app/pancake/client.py) nên phải tự đóng lại
    ở đây, không còn `async with` tự đóng sau mỗi lời gọi nữa.
    """
    yield
    await close_http()


# Khởi tạo ứng dụng FastAPI. `title` hiển thị ở trang tài liệu tự sinh /docs.
app = FastAPI(title="FB Sales Bot", lifespan=lifespan)

# Giao diện chính (menu trái): / , Bảng điều khiển, Tin nhắn, Khách hàng.
app.include_router(ui_router)

# Gắn toàn bộ route Pancake: webview danh sách page, xem hội thoại, trả lời,
# auto-refresh fragment, poll... (xem app/pancake/routes.py).
app.include_router(pancake_router)

# Giao diện quản lý dữ liệu bot: thêm/xem/xoá kịch bản & hội thoại mẫu (/data).
app.include_router(data_router)


@app.get("/health")
def health() -> dict:
    """Endpoint kiểm tra 'sống': trả {"status": "ok"} để biết server còn chạy."""
    return {"status": "ok"}


if __name__ == "__main__":
    # Chạy trực tiếp `python app/main.py`: bật uvicorn kèm auto-reload khi sửa code.
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
