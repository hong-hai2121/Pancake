"""Điểm khởi động ứng dụng: tạo FastAPI app và gắn các route.

Luồng hiện tại dùng POLLING qua Pancake (app/pancake) để nhận/ trả lời tin nhắn,
KHÔNG dùng webhook Facebook nữa — nên chỉ đăng ký `pancake_router`.
(Thư mục app/webhook đã bị bỏ; nếu sau này muốn dùng lại webhook Graph thì thêm
router tương ứng vào đây.)
"""

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.cam_xuc.routes import router as cam_xuc_router
from app.config import settings
from app.data.routes import router as data_router
from app.pancake.client import close_http
from app.pancake.routes import router as pancake_router
from app.ui.routes import router as ui_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Bật 2 worker nền lúc khởi động, dọn tài nguyên khi tắt server.

    Worker (xem app/workers/) chạy suốt vòng đời server — poll hội thoại về kho
    và quét cảm xúc — nên hoạt động cả khi KHÔNG ai mở trình duyệt. Tắt từng cái
    bằng `INBOX_POLL_ENABLED` / `SENTIMENT_ENABLED` trong .env.

    Client HTTP tới Pancake được dùng CHUNG cho cả vòng đời app (giữ keep-alive,
    đỡ bắt tay TLS mỗi request — xem app/pancake/client.py) nên phải tự đóng lại
    ở đây, không còn `async with` tự đóng sau mỗi lời gọi nữa.
    """
    tasks: list[asyncio.Task] = []
    if settings.inbox_poll_enabled:
        from app.workers import poll_loop

        tasks.append(asyncio.create_task(poll_loop(), name="inbox-poller"))
    # Worker cảm xúc LUÔN được tạo; quét hay không do công tắc ở trang /cam-xuc
    # quyết định (mặc định lấy theo SENTIMENT_ENABLED trong .env). Nhờ vậy bật
    # lại từ giao diện là chạy ngay, không phải khởi động lại server.
    from app.workers import sentiment_loop

    tasks.append(asyncio.create_task(sentiment_loop(), name="sentiment"))

    yield

    # Huỷ gọn gàng, nếu không uvicorn --reload sẽ để lại vòng lặp mồ côi.
    for t in tasks:
        t.cancel()
    for t in tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):  # noqa: B014 — tắt máy, nuốt hết
            pass
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

# Màn hình Cảm xúc: xem hội thoại tiêu cực + BẬT/TẮT worker quét (/cam-xuc).
app.include_router(cam_xuc_router)


@app.get("/health")
def health() -> dict:
    """Endpoint kiểm tra 'sống': trả {"status": "ok"} để biết server còn chạy."""
    return {"status": "ok"}


@app.get("/poller")
def poller_status(limit: int = 20) -> dict:
    """Soi 2 worker nền: vòng chạy gần nhất, tin MỚI, page LỖI, số liệu kho.

    Mở thẳng trên trình duyệt (http://127.0.0.1:8000/poller) — tiện hơn phải
    ngồi canh log console, và xem được cả khi server chạy nền không có console.
    `limit` = số hội thoại tiêu cực gần nhất lấy từ kho.
    """
    from app.db import inbox_store

    out: dict = {}
    try:
        from app.workers import poller

        out["poller"] = poller.last_run
        out["nhip_tung_page"] = poller.trang_thai_page()
    except Exception as err:  # noqa: BLE001 — worker bị tắt trong .env
        out["poller"] = {"tat": True, "ly_do": str(err)}
    try:
        from app.workers import sentiment as sentiment_worker

        out["sentiment"] = sentiment_worker.last_run
    except Exception as err:  # noqa: BLE001
        out["sentiment"] = {"tat": True, "ly_do": str(err)}

    try:
        out["kho"] = inbox_store.stats()
        out["tieu_cuc_trong_kho"] = [
            {
                "page": r.get("page_name"), "khach": r.get("name"),
                "snippet": r.get("snippet"), "luc": r.get("updated_at"),
                "cach_quet": r.get("sentiment_method"),
            }
            for r in inbox_store.list_recent(limit, only_negative=True)
        ]
    except Exception as err:  # noqa: BLE001 — Postgres chưa bật
        out["kho"] = {"loi": str(err)}
    return out


if __name__ == "__main__":
    # Chạy trực tiếp `python app/main.py`: bật uvicorn kèm auto-reload khi sửa code.
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
