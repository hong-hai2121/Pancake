"""Truy vấn dữ liệu, gom theo từng kho.

    queries.py       — kho RAG của bot (schema `public`: kịch bản, hội thoại mẫu)
    inbox_store.py   — kho hội thoại poll về từ Pancake (schema `watcher`)
    sentiment_log.py — nhật ký cảnh báo tiêu cực (schema `watcher`)
    tag_store.py     — kho tên/màu thẻ Pancake (schema `watcher`)

Bảng CRM (schema `crm` — xem scripts/init_crm.sql) mỗi nhóm một repo riêng, ví dụ:

    customer_repo · lead_repo · order_repo · task_repo · consult_repo · catalog_repo
    integration_repo  — khu Tích hợp (BRD mục 4): kết nối, nhật ký/lỗi đồng bộ,
                        ánh xạ page & nhân viên
    attribution_repo  — quy nguồn quảng cáo (ad_id, first/last touch)
"""
