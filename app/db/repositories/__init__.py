"""Truy vấn dữ liệu, gom theo từng kho.

    queries.py       — kho RAG của bot (schema `public`: kịch bản, hội thoại mẫu)
    inbox_store.py   — kho hội thoại poll về từ Pancake (schema `watcher`)
    sentiment_log.py — nhật ký cảnh báo tiêu cực (schema `watcher`)

Bảng CRM (schema `crm`, 56 bảng — xem scripts/init_crm.sql) sẽ thêm repository
riêng ở đây khi làm API.
"""
