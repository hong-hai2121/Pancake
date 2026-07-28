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

import json
import os
import re
from pathlib import Path

SENTIMENT_METHOD = os.getenv("SENTIMENT_METHOD", "keyword").strip().lower()

# Danh sách từ khoá/cụm từ tiêu cực tiếng Việt lưu ở keywords.json (cùng thư
# mục) thay vì hard-code — GUI (gui.py, cửa sổ "Quản lý từ khoá tiêu cực")
# đọc/ghi thẳng vào file này qua get_keywords()/add_keyword()/remove_keyword()
# bên dưới. File chưa tồn tại (lần chạy đầu) thì tự tạo với bộ từ khoá khởi
# điểm DEFAULT_NEGATIVE_KEYWORDS. Đọc lại file mỗi lần quét (analyze_keyword)
# nên sửa qua GUI có tác dụng ngay, không cần khởi động lại server.
KEYWORDS_PATH = Path(__file__).parent / "keywords.json"

DEFAULT_NEGATIVE_KEYWORDS = [
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
    "đm",
    "đmm",
    "đcm",
    "vãi lồn",
    "vl",
    "vcl",
    "vkl",
    "địt",
    "đéo",
    "đếch",
    "ngu",
    "óc chó",
    "đồ ngu",
    "đồ chó",
    "chó chết",
    "khốn nạn",
    "đồ khốn",
    "súc vật",
    "mất dạy",
    "vô học",
    "vô liêm sỉ",
    "rác rưởi",
    "thằng ngu",
    "con ngu",
    "đồ điên",
    "bố láo",
    "láo toét",
    "ăn cắp",
    "ăn chặn",
    "chết tiệt",
    "đồ lừa đảo",
    "thằng lừa đảo",
]


def get_keywords() -> list[str]:
    if not KEYWORDS_PATH.exists():
        set_keywords(DEFAULT_NEGATIVE_KEYWORDS)
        return list(DEFAULT_NEGATIVE_KEYWORDS)
    try:
        data = json.loads(KEYWORDS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(kw) for kw in data]
    except (json.JSONDecodeError, OSError):
        pass
    return list(DEFAULT_NEGATIVE_KEYWORDS)


def set_keywords(keywords: list[str]) -> None:
    KEYWORDS_PATH.write_text(json.dumps(keywords, ensure_ascii=False, indent=2), encoding="utf-8")


def add_keyword(keyword: str) -> list[str]:
    keyword = keyword.strip().lower()
    keywords = get_keywords()
    if keyword and keyword not in keywords:
        keywords.append(keyword)
        set_keywords(keywords)
    return keywords


def remove_keyword(keyword: str) -> list[str]:
    keywords = [kw for kw in get_keywords() if kw != keyword]
    set_keywords(keywords)
    return keywords


def analyze_keyword(text: str) -> str:
    if not text:
        return "neutral"
    lowered = text.lower()
    for kw in get_keywords():
        if not kw:
            continue
        # \b theo ranh giới TỪ, không phải khớp substring thô — nếu không, từ
        # khoá ngắn như "ngu" sẽ khớp nhầm vào giữa "Nguyễn" (họ phổ biến nhất
        # VN, gần như luôn xuất hiện ở phần [Tên người gửi] đầu mỗi snippet),
        # khiến gần như MỌI tin nhắn đều bị báo tiêu cực oan. \w trong Python
        # regex (chế độ Unicode mặc định với chuỗi str) đã tính cả chữ có dấu
        # tiếng Việt là ký tự "từ" nên hoạt động đúng cho cả từ khoá có dấu.
        if re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", lowered):
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


# Snippet có dạng "[Tên/nhãn người gửi] nội dung" — khi PAGE tự động gửi tin
# (kịch bản chatbot, không phải tin của khách), Pancake hiện nhãn "Botcake"
# thay vì tên khách. Loại thẳng những tin này khỏi việc quét cảm xúc: đây là
# lời page tự nói (thường hỏi lại khách "đang gặp vấn đề gì"...), không phải
# cảm xúc của khách hàng, quét vào sẽ báo tiêu cực oan + tốn phí LLM vô ích.
PAGE_MESSAGE_MARKERS = ["[botcake]"]


def is_page_message(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in PAGE_MESSAGE_MARKERS)


async def analyze(text: str) -> tuple[str, str]:
    """Trả về (sentiment, method_đã_dùng)."""
    if is_page_message(text):
        return "neutral", "skipped_page_message"
    if SENTIMENT_METHOD == "llm":
        return await analyze_llm(text), "llm"
    return analyze_keyword(text), "keyword"
