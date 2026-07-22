"""Ghép prompt gửi cho LLM = persona (vai) + ngữ cảnh RAG + tin nhắn khách."""

# Persona cố định: định hình giọng điệu & giới hạn của trợ lý bán hàng.
PERSONA = (
    "Bạn là trợ lý bán hàng thân thiện của shop trên Facebook. "
    "Trả lời ngắn gọn, tự nhiên, đúng trọng tâm, bằng tiếng Việt. "
    "Chỉ dựa trên thông tin được cung cấp; nếu không chắc thì hỏi lại khách."
)


def build_prompt(session: dict, context: list[str], text: str) -> str:
    """Dựng chuỗi prompt hoàn chỉnh cho LLM.

    - `session`: phiên khách (lấy trạng thái để LLM biết ngữ cảnh bước bán hàng).
    - `context`: các đoạn liên quan tìm được từ RAG (mỗi phần tử 1 dòng gạch đầu).
    - `text`: tin nhắn hiện tại của khách.
    """
    # Gộp ngữ cảnh RAG thành các gạch đầu dòng; rỗng thì ghi "(không có)".
    context_block = "\n".join(f"- {c}" for c in context) or "(không có)"
    trang_thai = session.get("trang_thai", "moi")

    # Bố cục prompt: vai -> trạng thái -> ngữ cảnh -> câu hỏi -> chỗ cho LLM viết.
    return (
        f"{PERSONA}\n\n"
        f"# Trạng thái khách: {trang_thai}\n\n"
        f"# Ngữ cảnh tham khảo\n{context_block}\n\n"
        f"# Tin nhắn của khách\n{text}\n\n"
        f"# Trả lời"
    )


# Dấu hiệu GPT báo "không câu mẫu nào phù hợp" — dùng ASCII, không dấu, để bắt
# chính xác (câu trả lời tiếng Việt thật sẽ không bao giờ chứa chuỗi này).
NO_MATCH_SENTINEL = "NO_MATCH"

# Prompt cho nút "Gợi ý trả lời": GPT đóng vai NGƯỜI CHỌN — chỉ được dùng các câu
# mẫu lấy từ kho tri thức, nếu không có cái nào hợp thì phải nói thẳng NO_MATCH.
_SUGGEST_SYSTEM = (
    "Bạn là trợ lý bán hàng của shop trên Facebook. Dưới đây là câu hỏi của khách "
    "và một số cặp hỏi–đáp mẫu lấy từ kho tri thức (đã xếp theo độ tương đồng).\n"
    "Nhiệm vụ: dựa DUY NHẤT vào các câu mẫu, chọn và soạn câu trả lời phù hợp nhất "
    "cho câu hỏi của khách. Được chỉnh lời cho tự nhiên, ngắn gọn, tiếng Việt, "
    "nhưng KHÔNG được bịa thông tin không có trong các câu mẫu.\n"
    f"Nếu KHÔNG có câu mẫu nào thực sự phù hợp với câu hỏi, chỉ trả về đúng một "
    f"dòng: {NO_MATCH_SENTINEL} (không thêm bất kỳ chữ nào khác)."
)


def build_suggest_prompt(question: str, candidates: list[dict]) -> str:
    """Ghép prompt cho GPT CHỌN câu trả lời từ các câu mẫu tương đồng.

    `candidates` = danh sách dict {cau_hoi, cau_tra_loi} (top N đã tìm được).
    GPT trả về câu trả lời đã chọn/chỉnh, hoặc đúng `NO_MATCH_SENTINEL` nếu không
    có câu mẫu nào phù hợp.
    """
    lines = []
    for i, c in enumerate(candidates, 1):
        q = (c.get("cau_hoi") or "").strip()
        a = (c.get("cau_tra_loi") or "").strip()
        lines.append(f"{i}. Hỏi: {q}\n   Đáp: {a}")
    block = "\n".join(lines) or "(không có câu mẫu nào)"
    return (
        f"{_SUGGEST_SYSTEM}\n\n"
        f"# Câu hỏi của khách\n{question}\n\n"
        f"# Các câu mẫu trong kho tri thức\n{block}\n\n"
        f"# Câu trả lời (hoặc {NO_MATCH_SENTINEL})"
    )
