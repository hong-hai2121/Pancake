"""Bộ quét cảm xúc tiêu cực — trước ở `ZPancake/server/sentiment.py`, nay nằm hẳn
trong app này (ZPancake đã bỏ, app không còn phụ thuộc thư mục đó nữa).

Chỉ đọc đúng `snippet` rút gọn mà Pancake trả về, KHÔNG gọi thêm API để lấy toàn
văn hội thoại — nên độ chính xác bị giới hạn bởi việc snippet có thể thiếu ngữ
cảnh. Đây là đánh đổi cố ý: quét mọi hội thoại mới mà không tốn thêm lượt gọi.

2 cách quét, chọn bằng công tắc trên giao diện (`app/workers/switch.py`), truyền
vào qua tham số `cach` — KHÔNG đọc biến môi trường như bản cũ, vì biến môi trường
chỉ đọc được 1 lần lúc khởi động nên bấm nút phải restart mới ăn:

  * "keyword" (mặc định): khớp danh sách từ khoá tiếng Việt trong `keywords.json`
    — chạy tại máy, miễn phí, không cần mạng. Bỏ sót câu tiêu cực không chứa
    đúng từ khoá, và báo nhầm câu có từ nhạy cảm nhưng ngữ cảnh khác.
  * "llm": nhờ model đọc hiểu ngữ cảnh/mỉa mai — chính xác hơn nhưng tốn phí
    mỗi lần gọi và cần mạng.

`keywords.json` được đọc lại MỖI lần quét nên sửa từ khoá trên giao diện là có
tác dụng ngay, không cần khởi động lại.
"""

import json
import re
from pathlib import Path

from app.config import settings

KEYWORDS_PATH = Path(__file__).parent / "keywords.json"

DEFAULT_NEGATIVE_KEYWORDS = [
    "không hài lòng", "không hiệu quả", "không tin tưởng", "không đáng tiền",
    "không như quảng cáo", "lừa đảo", "thất vọng", "phàn nàn", "khiếu nại",
    "tố cáo", "report", "kiện", "trả lại", "hoàn tiền", "hủy đơn", "hủy dịch vụ",
    "quá tệ", "rất tệ", "tệ quá", "quá kém", "dịch vụ kém", "chán", "bực",
    "khó chịu", "tức giận", "vô trách nhiệm", "chậm trễ", "mất thời gian",
    "không phản hồi", "bỏ rơi", "đm", "đmm", "đcm", "vãi lồn", "vl", "vcl",
    "vkl", "địt", "đéo", "đếch", "ngu", "óc chó", "đồ ngu", "đồ chó",
    "chó chết", "khốn nạn", "đồ khốn", "súc vật", "mất dạy", "vô học",
    "vô liêm sỉ", "rác rưởi", "thằng ngu", "con ngu", "đồ điên", "bố láo",
    "láo toét", "ăn cắp", "ăn chặn", "chết tiệt", "đồ lừa đảo", "thằng lừa đảo",
]


# ------------------------------------------------------------ danh sách từ khoá
def get_keywords() -> list[str]:
    """Danh sách từ khoá hiện hành; file chưa có thì tự tạo với bộ khởi điểm."""
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
    KEYWORDS_PATH.write_text(
        json.dumps(keywords, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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


# ------------------------------------------------------------------ khớp từ khoá
def mau_khop(kw: str) -> str:
    r"""Regex khớp 1 từ khoá theo ranh giới TỪ — nguồn luật khớp DUY NHẤT.

    Không khớp substring thô: từ khoá ngắn như "ngu" sẽ dính vào giữa "Nguyễn"
    (họ phổ biến nhất VN, gần như luôn có ở phần [Tên người gửi] đầu mỗi
    snippet), khiến gần như MỌI tin nhắn bị báo tiêu cực oan. `\w` trong regex
    Python (chế độ Unicode mặc định với chuỗi str) đã tính cả chữ có dấu tiếng
    Việt là ký tự "từ" nên hoạt động đúng cho cả từ khoá có dấu.
    """
    return r"(?<!\w)" + re.escape(kw) + r"(?!\w)"


def tim_tu_khoa(text: str) -> list[str]:
    """TẤT CẢ từ khoá tiêu cực khớp trong `text` (rỗng = không khớp gì).

    Tách riêng khỏi `analyze_keyword` để nơi ghi nhật ký biết câu đã dính ĐÚNG
    TỪ NÀO: `analyze_keyword` chỉ trả "negative"/"neutral", không nói vì sao —
    mà không biết vì sao thì không sửa được từ khoá hay báo nhầm.

    Trả về CẢ danh sách chứ không dừng ở từ đầu tiên: câu dính 3 từ khác hẳn về
    mức độ so với câu chỉ chạm 1 từ ở ranh giới.
    """
    if not text:
        return []
    lowered = text.lower()
    return [kw for kw in get_keywords() if kw and re.search(mau_khop(kw), lowered)]


def analyze_keyword(text: str) -> str:
    return "negative" if tim_tu_khoa(text) else "neutral"


# ------------------------------------------------------------------------- LLM
async def analyze_llm(text: str) -> str:
    """Nhờ model phân loại. Thiếu API key -> coi như trung tính, không chặn worker."""
    if not text:
        return "neutral"
    api_key = settings.openai_api_key
    if not api_key:
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
                "model": settings.sentiment_llm_model,
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


# --------------------------------------------------------------- tin của PAGE
# Snippet có dạng "[Tên/nhãn người gửi] nội dung" — khi PAGE tự gửi tin (kịch bản
# chatbot, không phải tin của khách), Pancake hiện nhãn "Botcake" thay vì tên
# khách. Loại thẳng những tin này khỏi việc quét: đây là lời page tự nói (thường
# là câu hỏi lại khách), quét vào sẽ báo tiêu cực oan + tốn phí LLM vô ích.
PAGE_MESSAGE_MARKERS = ["[botcake]"]


def is_page_message(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in PAGE_MESSAGE_MARKERS)


async def analyze(text: str, cach: str = "keyword") -> tuple[str, str, list[str]]:
    """Quét 1 đoạn text. Trả về (sentiment, cách đã dùng, từ khoá đã khớp).

    Khác bản cũ ở 2 chỗ: `cach` truyền vào thay vì đọc biến môi trường (để bấm
    nút trên giao diện ăn ngay), và trả thêm danh sách từ khoá đã khớp để ghi
    vào sổ cảnh báo. Cách quét `llm` không có từ khoá nào -> trả về list rỗng.
    """
    if is_page_message(text):
        return "neutral", "skipped_page_message", []
    if cach == "llm":
        return await analyze_llm(text), "llm", []
    khop = tim_tu_khoa(text)
    return ("negative" if khop else "neutral"), "keyword", khop
