"""Màn hình "Cảm xúc": theo dõi + BẬT/TẮT worker quét tin nhắn tiêu cực.

    routes.py  — /cam-xuc (xem), /cam-xuc/bat-tat, /cam-xuc/cach-quet, /cam-xuc/quet-lai
    webview.py — dựng HTML

Worker thật nằm ở `app/workers/sentiment.py`; trang này chỉ đọc kho
`watcher.hoi_thoai` và lật công tắc ở `app/workers/switch.py`.
"""
