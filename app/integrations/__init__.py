"""Mọi kết nối ra hệ thống ngoài.

    pancake/   — pages.fm: đọc hội thoại, trả lời, thẻ, đơn (luồng chính)
    messenger/ — Facebook Graph Send API (luồng trực tiếp, hiện không dùng)
    telegram.py — bắn cảnh báo cho quản trị

Đặc tả CRM còn yêu cầu tổng đài và Facebook Ads; khi làm sẽ thêm `call_center/`
và `facebook_ads/` vào đây.
"""
