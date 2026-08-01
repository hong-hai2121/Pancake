"""Tích hợp Pancake POS (Open API pos.pages.fm/api/v1) — B7 đơn hàng.

KHÁC với app/integrations/pancake (chat pages.fm, xác thực JWT): POS xác thực
bằng `api_key` riêng theo TỪNG SHOP, tạo trong POS UI. Hai luồng song song,
không gộp — đúng nguyên tắc "Pancake bổ sung, không thay".

client.py   — gọi API POS (chỉ GET; tạo/sửa đơn trên POS không thuộc phạm vi B7)
pos_sync.py — đổ đơn POS về crm.orders (ánh xạ trạng thái đọc từ DB)
"""
