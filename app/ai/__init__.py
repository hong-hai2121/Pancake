"""Toàn bộ phần AI của hệ thống, gom về một chỗ.

    llm.py        — gọi model sinh văn bản (OpenAI/tương thích)
    embedding.py  — sinh vector cho tìm kiếm ngữ nghĩa
    retriever.py  — tra kho tri thức bằng vector
    prompt.py     — dựng prompt (chọn câu mẫu, trích tri thức, gợi ý trả lời)
    brain.py      — điều phối RAG: hỏi → tìm → chọn câu trả lời
    session.py    — trạng thái hội thoại nhiều bước của từng khách
    flow.py       — bước tiếp theo trong luồng nghiệp vụ (còn stub)
    sentiment.py  — quét cảm xúc tiêu cực (từ khoá hoặc LLM)

Trước đây nằm rải ở `app/rag`, `app/bot` và `app/cam_xuc`. Đặc tả CRM còn cần
thêm chấm điểm cuộc gọi và kiểm duyệt nội dung — cũng sẽ đặt vào đây.
"""
