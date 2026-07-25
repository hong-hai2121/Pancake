"""Quét cảm xúc tiêu cực trong snippet tin nhắn khách hàng về dịch vụ tư vấn.

Chỉ dùng đúng snippet rút gọn mà extension đã quét được (không gọi API Pancake
nào để lấy thêm nội dung) — nên độ chính xác bị giới hạn bởi việc snippet có
thể thiếu ngữ cảnh.

2 cách quét, chọn qua biến môi trường SENTIMENT_METHOD (đổi trong `.env`):
- "keyword" (mặc định): khớp danh sách từ khoá/cụm từ tiêu cực tiếng Việt —
  nhanh, chạy ngay tại máy, không tốn phí, không cần internet. Độ chính xác
  giới hạn: có thể bỏ sót câu tiêu cực không chứa đúng từ khoá, hoặc báo nhầm
  câu có từ nhạy cảm nhưng ngữ cảnh khác.
- "llm": gọi OpenAI (model rẻ, `gpt-4o-mini`) để phân loại — chính xác hơn
  nhiều vì hiểu ngữ cảnh/mỉa mai, nhưng cần biến môi trường OPENAI_API_KEY
  riêng cho ZPancake (không dùng chung với app/ ở gốc repo) và tốn phí nhỏ
  mỗi lần gọi + cần internet.
"""

import os

SENTIMENT_METHOD = os.getenv("SENTIMENT_METHOD", "keyword").strip().lower()

# Danh sách từ khoá/cụm từ tiêu cực tiếng Việt thường gặp khi khách phàn nàn
# về dịch vụ tư vấn — chỉ cần khớp 1 cụm là coi như "negative". Thêm/bớt tuỳ
# thực tế sử dụng, không cần khởi động lại server (đọc lại mỗi lần gọi).
NEGATIVE_KEYWORDS = [
    "không hài lòng",
    "không hiệu quả",
    "không tin tưởng",
    "không đáng tiền",
    "không như quảng cáo",
    "lừa đảo",
    "thất vọng",
    "phàn nàn",
    "khiếu nại",
    "tố cáo",
    "report",
    "kiện",
    "trả lại",
    "hoàn tiền",
    "hủy đơn",
    "hủy dịch vụ",
    "quá tệ",
    "rất tệ",
    "tệ quá",
    "quá kém",
    "dịch vụ kém",
    "chán",
    "bực",
    "khó chịu",
    "tức giận",
    "vô trách nhiệm",
    "chậm trễ",
    "mất thời gian",
    "không phản hồi",
    "bỏ rơi",
]


def analyze_keyword(text: str) -> str:
    if not text:
        return "neutral"
    lowered = text.lower()
    for kw in NEGATIVE_KEYWORDS:
        if kw in lowered:
            return "negative"
    return "neutral"


async def analyze_llm(text: str) -> str:
    if not text:
        return "neutral"
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Chưa cấu hình key -> không chặn worker, coi như trung tính rồi thôi.
        return "neutral"

    import httpx

    prompt = (
        "Phân loại cảm xúc của khách hàng trong tin nhắn sau về dịch vụ tư vấn "
        "sức khoẻ. Chỉ trả lời đúng 1 từ, không giải thích gì thêm: "
        "negative, neutral, hoặc positive.\n\n"
        f"Tin nhắn: {text}"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 5,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data["choices"][0]["message"]["content"].strip().lower()

    if "negative" in answer:
        return "negative"
    if "positive" in answer:
        return "positive"
    return "neutral"


async def analyze(text: str) -> tuple[str, str]:
    """Trả về (sentiment, method_đã_dùng)."""
    if SENTIMENT_METHOD == "llm":
        return await analyze_llm(text), "llm"
    return analyze_keyword(text), "keyword"
