"""Các vòng lặp chạy NỀN của app, độc lập với request của trình duyệt.

    poller.py    — đều đặn kéo hội thoại mới của MỌI page đang BẬT về kho DB
    sentiment.py — quét cảm xúc tiêu cực cho hội thoại mới trong kho

Cả hai được khởi động ở `app/main.py` (lifespan) nên **chạy suốt lúc server còn
sống**, không phụ thuộc việc có ai đang mở màn Tin nhắn hay không.
"""

from app.workers.poller import poll_loop
from app.workers.sentiment import sentiment_loop

__all__ = ["poll_loop", "sentiment_loop"]
