"""Não của bot: điều phối tổng, quyết định trả lời gì cho một tin nhắn.

Thứ tự ưu tiên: (1) đi theo KỊCH BẢN bán hàng nếu khớp, (2) nếu không thì dùng
RAG (tìm hội thoại mẫu tương tự) + LLM để trả lời tự nhiên.
"""

from app.bot.flow import next_step
from app.bot.prompt import NO_MATCH_SENTINEL, build_prompt, build_suggest_prompt
from app.bot.session import get_session, save_session
from app.config import settings
from app.db.queries import search_similar
from app.rag.embedding import embed
from app.rag.llm import complete
from app.rag.retriever import retrieve

# Số câu mẫu tương đồng gửi lên GPT để CHỌN (top N trong số top-k đã tìm được).
_SUGGEST_CANDIDATES = 3


async def choose_reply(question: str, candidates: list[dict]) -> dict:
    """GPT CHỌN/soạn câu trả lời từ các câu mẫu ĐÃ TÌM SẴN (không tự tìm lại).

    Tách riêng để nút "Gợi ý trả lời" và trang "Thử tin nhắn" dùng CHUNG một
    logic. `candidates` = list {cau_hoi, cau_tra_loi, ...} đã xếp theo tương đồng;
    chỉ lấy top `_SUGGEST_CANDIDATES` đưa lên GPT.

    Trả về {"reply": <câu>, "no_match": False} nếu chọn được;
    {"reply": None, "no_match": True} nếu không có câu mẫu / GPT trả NO_MATCH.
    """
    cands = candidates[:_SUGGEST_CANDIDATES]
    if not cands:
        return {"reply": None, "no_match": True}

    prompt = build_suggest_prompt(question, cands)
    raw = await complete(prompt, temperature=0.3)   # chọn -> cần ổn định
    reply = (raw or "").strip()

    # GPT tự quyết: không câu mẫu nào phù hợp -> NO_MATCH -> không gợi ý.
    if not reply or NO_MATCH_SENTINEL in reply.upper():
        return {"reply": None, "no_match": True}
    return {"reply": reply, "no_match": False}


async def suggest_reply(text: str) -> dict:
    """Soạn GỢI Ý trả lời cho một tin của khách — RAG + GPT làm NGƯỜI CHỌN.

    Dùng cho nút "Gợi ý trả lời" ở màn Tin nhắn (human-in-the-loop): người bấm
    nút, câu gợi ý đổ vào ô trả lời để sửa rồi TỰ bấm Gửi. Vì vậy hàm này KHÔNG
    gửi tin đi và KHÔNG đọc/ghi phiên khách (tránh lệ thuộc bảng trang_thai_khach
    còn lệch schema — việc căn lại thuộc Tầng 2 của lộ trình).

    Luồng (đúng logic mong muốn):
      1. Nhúng câu hỏi rồi lấy **top-k** câu mẫu tương đồng từ Supabase (mặc định
         KHÔNG cắt cứng theo cosine — để GPT tự phán xử; `rag_suggest_threshold`
         chỉ là bộ sàng thô tuỳ chọn, mặc định 0 = tắt).
      2. Gửi câu hỏi + **top {_SUGGEST_CANDIDATES}** câu mẫu lên GPT để CHỌN/soạn
         câu trả lời phù hợp nhất, chỉ dựa vào các câu mẫu.
      3. GPT thấy không câu nào hợp -> trả `NO_MATCH` -> ta coi là "câu hỏi chưa
         có trong tri thức" -> KHÔNG gợi ý.

    Trả về:
      - có gợi ý:  {"reply": <câu>, "nguon": [<câu mẫu đã gửi GPT>...]}
      - không hợp: {"reply": None, "nguon": [], "no_match": True}
    """
    vector = await embed(text)
    # Top-k câu mẫu tương đồng; threshold mặc định 0 -> lấy đủ để GPT xét.
    rows = await search_similar(
        vector, k=settings.rag_top_k, threshold=settings.rag_suggest_threshold
    )
    if not rows:                       # kho tri thức chưa có gì để đối chiếu
        return {"reply": None, "nguon": [], "no_match": True}

    candidates = rows[:_SUGGEST_CANDIDATES]
    result = await choose_reply(text, candidates)   # GPT chọn / NO_MATCH
    if result["no_match"]:
        return {"reply": None, "nguon": [], "no_match": True}
    return {"reply": result["reply"], "nguon": candidates}


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
