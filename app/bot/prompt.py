"""Ghép system prompt + persona + ngữ cảnh RAG."""

PERSONA = (
    "Bạn là trợ lý bán hàng thân thiện của shop trên Facebook. "
    "Trả lời ngắn gọn, tự nhiên, đúng trọng tâm, bằng tiếng Việt. "
    "Chỉ dựa trên thông tin được cung cấp; nếu không chắc thì hỏi lại khách."
)


def build_prompt(session: dict, context: list[str], text: str) -> str:
    context_block = "\n".join(f"- {c}" for c in context) or "(không có)"
    trang_thai = session.get("trang_thai", "moi")

    return (
        f"{PERSONA}\n\n"
        f"# Trạng thái khách: {trang_thai}\n\n"
        f"# Ngữ cảnh tham khảo\n{context_block}\n\n"
        f"# Tin nhắn của khách\n{text}\n\n"
        f"# Trả lời"
    )
