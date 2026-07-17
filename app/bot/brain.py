"""Não của bot: điều phối tổng, quyết định trả lời gì."""

from app.bot.flow import next_step
from app.bot.prompt import build_prompt
from app.bot.session import get_session, save_session
from app.rag.llm import complete
from app.rag.retriever import retrieve


async def generate_reply(sender_id: str, text: str) -> str:
    session = await get_session(sender_id)

    # 1) Ưu tiên đi theo kịch bản (Bảng 1).
    scripted = next_step(session, text)
    if scripted is not None:
        await save_session(sender_id, session)
        return scripted

    # 2) Không khớp kịch bản -> RAG + LLM.
    context = await retrieve(text)
    prompt = build_prompt(session, context, text)
    reply = await complete(prompt)

    session.setdefault("history", []).append({"user": text, "bot": reply})
    await save_session(sender_id, session)
    return reply
