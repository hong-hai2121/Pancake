"""Chưng cất chat cũ -> cặp hỏi–đáp (gọi LLM)."""

from app.rag.llm import complete

DISTILL_PROMPT = (
    "Dưới đây là một đoạn chat giữa khách và nhân viên bán hàng đã chốt đơn.\n"
    "Hãy rút ra các cặp (câu hỏi của khách, câu trả lời tốt của shop) dạng JSON.\n\n"
    "{conversation}"
)


async def distill(conversation: str) -> list[dict]:
    """Biến một đoạn chat thành danh sách cặp hỏi–đáp.

    TODO: parse kết quả LLM thành list[{"cau_hoi": ..., "cau_tra_loi": ...}].
    """
    _ = await complete(DISTILL_PROMPT.format(conversation=conversation))
    raise NotImplementedError("Parse output LLM thành cặp hỏi–đáp")
