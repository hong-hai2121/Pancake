"""Các vòng lặp chạy NỀN của app, độc lập với request của trình duyệt.

    poller.py       — đều đặn kéo hội thoại mới của MỌI page đang BẬT về kho DB
    sentiment.py    — quét cảm xúc tiêu cực cho hội thoại mới trong kho
    tasks_qua_han.py — đánh dấu việc quá hạn + audit "báo quản lý" (B4, mục 19)
    pos_orders.py   — kéo đơn Pancake POS mới cập nhật về crm.orders (B7)

Tất cả được khởi động ở `app/main.py` (lifespan) nên **chạy suốt lúc server còn
sống**, không phụ thuộc việc có ai đang mở màn Tin nhắn hay không.
"""

from app.workers.poller import poll_loop
from app.workers.pos_orders import pos_orders_loop
from app.workers.sentiment import sentiment_loop
from app.workers.tasks_qua_han import task_escalation_loop

__all__ = ["poll_loop", "pos_orders_loop", "sentiment_loop", "task_escalation_loop"]
