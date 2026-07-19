"""Não của bot: điều phối tổng, quyết định trả lời gì cho một tin nhắn.

Thứ tự ưu tiên: (1) đi theo KỊCH BẢN bán hàng nếu khớp, (2) nếu không thì dùng
RAG (tìm hội thoại mẫu tương tự) + LLM để trả lời tự nhiên.
"""

from app.bot.flow import next_step
from app.bot.prompt import build_prompt
from app.bot.session import get_session, save_session
from app.rag.llm import complete
from app.rag.retriever import retrieve


async def generate_reply(sender_id: str, text: str) -> str:
    """Nhận tin nhắn `text` của khách `sender_id`, trả về câu trả lời của bot."""
    # Đọc phiên hiện tại của khách (trạng thái đang ở bước nào, lịch sử chat...).
    session = await get_session(sender_id)

    # 1) Ưu tiên đi theo kịch bản (Bảng 1). Khớp -> lưu phiên & trả lời luôn.
    scripted = next_step(session, text)
    if scripted is not None:
        await save_session(sender_id, session)
        return scripted

    # 2) Không khớp kịch bản -> RAG + LLM.
    context = await retrieve(text)                  # tìm các đoạn liên quan trong DB
    prompt = build_prompt(session, context, text)   # ghép persona + ngữ cảnh + câu hỏi
    reply = await complete(prompt)                  # gọi LLM sinh câu trả lời

    # Lưu lại cặp hỏi–đáp vào lịch sử phiên rồi ghi xuống DB.
    session.setdefault("history", []).append({"user": text, "bot": reply})
    await save_session(sender_id, session)
    return reply
