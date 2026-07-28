"""Server local nhận dữ liệu từ extension Pancake Watcher và lưu vào SQLite.

Chạy: uvicorn main:app --host 127.0.0.1 --port 8787 --reload
(hoặc `python main.py`)

Độc lập hoàn toàn với backend chính ở thư mục gốc repo (app/) — không dùng
chung DB, không dùng chung access token Pancake, chỉ lưu lại đúng những gì
extension quét được (snippet rút gọn + metadata hội thoại).
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import sentiment
import telegram
from db import (
    delete_customer,
    get_all_customers,
    get_recent_sentiments,
    get_unanalyzed,
    init_db,
    save_event,
    update_sentiment,
)

HISTORY_HTML_PATH = Path(__file__).parent / "history.html"

load_dotenv()  # đọc .env riêng của ZPancake/server (SENTIMENT_METHOD, OPENAI_API_KEY...)

app = FastAPI(title="Pancake Watcher Local Server")

# Extension gọi từ background service worker (không phải trang web) nên về
# nguyên tắc không bị chặn CORS, nhưng vẫn bật rộng rãi để tiện test bằng
# curl/trình duyệt/công cụ khác trong lúc dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class MessageEvent(BaseModel):
    rawId: str
    platform: Optional[str] = None
    kind: Optional[str] = None
    pageId: Optional[str] = None
    convId: Optional[str] = None
    name: Optional[str] = None
    snippet: Optional[str] = None
    time: Optional[str] = None
    unreadCount: Optional[int] = None
    platformClass: Optional[str] = None
    reason: Optional[str] = None
    detectedAt: Optional[str] = None


class MessagesPayload(BaseModel):
    events: list[MessageEvent]


# ------------------------------------------------------ worker nền: sentiment

SENTIMENT_WORKER_INTERVAL_S = 8  # quét lại mỗi 8s, đủ nhanh mà không tốn CPU vô ích
SENTIMENT_BATCH_SIZE = 10  # mỗi lượt quét tối đa N khách, tránh 1 lượt chạy quá lâu


async def sentiment_worker() -> None:
    """Chạy NỀN, tách hẳn khỏi request POST /api/messages — quét cảm xúc không
    bao giờ làm chậm việc lưu tin nhắn mới của extension. Lỗi từng khách (vd
    LLM timeout) chỉ log rồi bỏ qua, không làm chết cả vòng lặp.
    """
    while True:
        try:
            rows = get_unanalyzed(limit=SENTIMENT_BATCH_SIZE)
            for row in rows:
                try:
                    result, method = await sentiment.analyze(row["snippet"])
                    update_sentiment(
                        row["raw_id"], result, method, datetime.now(timezone.utc).isoformat()
                    )
                    if result == "negative":
                        # Best-effort, không chặn/làm hỏng vòng lặp nếu Telegram lỗi hoặc
                        # chưa cấu hình (send_negative_alert tự bỏ qua khi thiếu .env).
                        await telegram.send_negative_alert(
                            name=row["name"],
                            snippet=row["snippet"],
                            platform=row["platform"],
                            raw_id=row["raw_id"],
                        )
                except Exception as err:  # noqa: BLE001 - không để 1 khách lỗi chặn cả batch
                    print(f"[sentiment_worker] Lỗi quét {row['raw_id']}: {err}")
        except Exception as err:  # noqa: BLE001 - không để lỗi bất ngờ giết chết worker
            print(f"[sentiment_worker] Lỗi vòng lặp: {err}")
        await asyncio.sleep(SENTIMENT_WORKER_INTERVAL_S)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    asyncio.create_task(sentiment_worker())


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/messages")
def receive_messages(payload: MessagesPayload) -> dict:
    for ev in payload.events:
        save_event(ev.model_dump())
    return {"status": "ok", "inserted": len(payload.events)}


@app.get("/api/sentiment")
def sentiment_updates() -> dict:
    """Extension poll định kỳ (chrome.alarms, ~1 phút/lần) để lấy kết quả quét
    cảm xúc mới nhất, gộp vào danh sách đang hiển thị trên popup/panel."""
    rows = get_recent_sentiments(limit=200)
    return {
        "items": [
            {
                "rawId": row["raw_id"],
                "sentiment": row["sentiment"],
                "sentimentMethod": row["sentiment_method"],
                "sentimentCheckedAt": row["sentiment_checked_at"],
            }
            for row in rows
        ]
    }


@app.get("/history", response_class=HTMLResponse)
def history_page() -> str:
    """Webview xem lịch sử toàn bộ khách hàng đã quét được, sắp xếp theo thời
    gian — chỉ đọc file HTML tĩnh (tự chứa CSS/JS, không cần build gì) rồi trả
    thẳng về, trang tự gọi /api/customers qua fetch()."""
    return HISTORY_HTML_PATH.read_text(encoding="utf-8")


@app.get("/api/customers")
def list_customers(sort: str = "detected_at", order: str = "desc") -> dict:
    rows = get_all_customers(order_by=sort, direction=order)
    return {
        "items": [
            {
                "rawId": row["raw_id"],
                "platform": row["platform"],
                "kind": row["kind"],
                "pageId": row["page_id"],
                "convId": row["conv_id"],
                "name": row["name"],
                "snippet": row["snippet"],
                "time": row["time_text"],
                "unreadCount": row["unread_count"],
                "reason": row["reason"],
                "detectedAt": row["detected_at"],
                "firstSeenAt": row["first_seen_at"],
                "lastSeenAt": row["last_seen_at"],
                "sentiment": row["sentiment"],
                "sentimentMethod": row["sentiment_method"],
                "sentimentCheckedAt": row["sentiment_checked_at"],
            }
            for row in rows
        ]
    }


@app.delete("/api/customers/{raw_id}")
def delete_customer_endpoint(raw_id: str) -> dict:
    if not delete_customer(raw_id):
        raise HTTPException(status_code=404, detail="raw_id không tồn tại")
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8787, reload=True)
