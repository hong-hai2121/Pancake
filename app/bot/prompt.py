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
