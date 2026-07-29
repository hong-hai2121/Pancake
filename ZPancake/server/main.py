"""Server local nhận dữ liệu từ extension Pancake Watcher và lưu vào SQLite.

Chạy: uvicorn main:app --host 127.0.0.1 --port 8787 --reload
(hoặc `python main.py`)

Độc lập hoàn toàn với backend chính ở thư mục gốc repo (app/) — không dùng
chung DB, không dùng chung access token Pancake, chỉ lưu lại đúng những gì
extension quét được (snippet rút gọn + metadata hội thoại).
"""

import asyncio
from collections import deque
from datetime import datetime, timezone
from itertools import count
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
    cleanup_scanned,
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


# ------------------------------------------------------ nhật ký quét (bộ nhớ)

# Chỉ giữ trong RAM, KHÔNG ghi ra server.log/file nào — gui.py poll qua HTTP
# (/api/scan-events) để đổ vào khung "Nhật ký" theo thời gian thực mà không
# làm rác server.log (trước đó in bằng print() ra đúng file log của uvicorn).
# maxlen=200: đủ cho vài phút hoạt động gần nhất, tự động rớt sự kiện cũ,
# không bao giờ phình bộ nhớ dù server chạy nhiều ngày.
SCAN_EVENTS: deque = deque(maxlen=200)
_scan_event_seq = count(1)


def _record_scan_event(*, name: Optional[str], raw_id: str, snippet: Optional[str], sentiment_result: str) -> None:
    SCAN_EVENTS.append(
        {
            "seq": next(_scan_event_seq),
            "name": name,
            "rawId": raw_id,
            "snippet": snippet,
            "sentiment": sentiment_result,
        }
    )


# ------------------------------------------------------ worker nền: sentiment

SENTIMENT_WORKER_INTERVAL_S = 8  # quét lại mỗi 8s, đủ nhanh mà không tốn CPU vô ích
SENTIMENT_BATCH_SIZE = 10  # mỗi lượt quét tối đa N khách, tránh 1 lượt chạy quá lâu

CLEANUP_WORKER_INTERVAL_S = 1800  # 30 phút/lần — đủ thưa so với ngưỡng 1h bên dưới
CLEANUP_OLDER_THAN_HOURS = 1
CLEANUP_KEEP_RECENT = 20  # sàn tối thiểu hội thoại đã quét luôn được giữ lại, xem db.cleanup_scanned


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
                    # Ghi vào bộ nhớ (không phải server.log) cho mọi lượt quét, kể cả
                    # neutral — gui.py poll /api/scan-events để hiện lên khung "Nhật ký",
                    # cho thấy worker đang hoạt động bình thường mà không cần mở server.log.
                    _record_scan_event(
                        name=row["name"], raw_id=row["raw_id"], snippet=row["snippet"], sentiment_result=result
                    )
                    if result == "negative":
                        # Best-effort, không chặn/làm hỏng vòng lặp nếu Telegram lỗi hoặc
                        # chưa cấu hình (send_negative_alert tự bỏ qua khi thiếu .env).
                        await telegram.send_negative_alert(
                            name=row["name"],
                            snippet=row["snippet"],
                            platform=row["platform"],
                            raw_id=row["raw_id"],
                            page_id=row["page_id"],
                            conv_id=row["conv_id"],
                        )
                except Exception as err:  # noqa: BLE001 - không để 1 khách lỗi chặn cả batch
                    print(f"[sentiment_worker] Lỗi quét {row['raw_id']}: {err}")
        except Exception as err:  # noqa: BLE001 - không để lỗi bất ngờ giết chết worker
            print(f"[sentiment_worker] Lỗi vòng lặp: {err}")
        await asyncio.sleep(SENTIMENT_WORKER_INTERVAL_S)


# ------------------------------------------------------ worker nền: dọn dẹp


async def cleanup_worker() -> None:
    """Chạy NỀN định kỳ, xoá bớt hội thoại đã quét cảm xúc + không tiêu cực +
    cũ hơn CLEANUP_OLDER_THAN_HOURS — luôn giữ lại CLEANUP_KEEP_RECENT hội
    thoại đã quét gần nhất và mọi hội thoại tiêu cực (xem db.cleanup_scanned).
    """
    while True:
        try:
            deleted = cleanup_scanned(
                older_than_hours=CLEANUP_OLDER_THAN_HOURS, keep_recent=CLEANUP_KEEP_RECENT
            )
            if deleted:
                print(f"[cleanup_worker] Đã xoá {deleted} hội thoại cũ.")
        except Exception as err:  # noqa: BLE001 - không để lỗi bất ngờ giết chết worker
            print(f"[cleanup_worker] Lỗi: {err}")
        await asyncio.sleep(CLEANUP_WORKER_INTERVAL_S)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    asyncio.create_task(sentiment_worker())
    asyncio.create_task(cleanup_worker())


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/scan-events/cursor")
def scan_events_cursor() -> dict:
    """GUI gọi 1 lần lúc mở/khi bật hiển thị nhật ký để lấy seq mới nhất hiện
    có, dùng làm điểm bắt đầu poll — tránh dội nguyên buffer cũ (tối đa 200
    sự kiện tích luỹ từ lúc server bật) vào khung Nhật ký ngay khi vừa bật."""
    return {"latestSeq": SCAN_EVENTS[-1]["seq"] if SCAN_EVENTS else 0}


@app.get("/api/scan-events")
def scan_events(after: int = 0, limit: int = 50) -> dict:
    """GUI poll định kỳ để lấy các lượt quét MỚI (seq > after) đổ vào khung
    "Nhật ký" — chỉ đọc từ SCAN_EVENTS trong bộ nhớ, không đụng file nào."""
    items = [e for e in SCAN_EVENTS if e["seq"] > after][-limit:]
    return {"items": items, "latestSeq": SCAN_EVENTS[-1]["seq"] if SCAN_EVENTS else after}


@app.post("/api/messages")
def receive_messages(payload: MessagesPayload) -> dict:
    inserted = 0
    for ev in payload.events:
        # Tin do PAGE tự gửi (nhãn "Botcake", xem sentiment.is_page_message)
        # không phải tin của khách -> bỏ hẳn, không lưu DB và khỏi cần quét
        # cảm xúc (sentiment_worker chỉ quét những gì đã lưu).
        if sentiment.is_page_message(ev.snippet):
            continue
        save_event(ev.model_dump())
        inserted += 1
    return {"status": "ok", "inserted": inserted}


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

    # reload=False: reload=True dùng multiprocessing để tự khởi động lại khi
    # sửa code, nhưng tiến trình con đó KHÔNG bao giờ được tạo ra khi main.py
    # bị bật bởi gui.py qua pythonw.exe (không có console) — treo vĩnh viễn
    # ngay sau "Started reloader process", không lỗi/không log gì thêm, khiến
    # /health không bao giờ phản hồi. Đang phát triển và muốn auto-reload thì
    # tự thêm lại --reload khi chạy tay: `uvicorn main:app --reload --port 8787`.
    uvicorn.run("main:app", host="127.0.0.1", port=8787)
