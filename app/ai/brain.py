"""Não của bot: điều phối tổng, quyết định trả lời gì cho một tin nhắn.

Thứ tự ưu tiên: (1) đi theo KỊCH BẢN bán hàng nếu khớp, (2) nếu không thì dùng
RAG (tìm hội thoại mẫu tương tự) + LLM để trả lời tự nhiên.
"""

import json

from app.ai.flow import next_step
from app.ai.prompt import build_extract_prompt, build_prompt, build_suggest_prompt
from app.ai.session import get_session, save_session
from app.core.config import settings
from app.db.repositories.queries import search_similar
from app.ai.embedding import embed
from app.ai.llm import complete
from app.ai.retriever import retrieve

# Số câu mẫu tương đồng gửi lên GPT để CHỌN (top N trong số top-k đã tìm được).
_SUGGEST_CANDIDATES = 3

# Chặn trên số đề xuất trích tri thức/lần gọi (phòng model trả về danh sách bất
# thường dài) — 1 đoạn hội thoại thật hiếm khi có quá chừng này cặp hỏi-đáp giá
# trị dùng chung.
_EXTRACT_MAX_ITEMS = 20


def _parse_choice_json(raw: str, n: int) -> int | None:
    """Đọc {"chon": <số>} từ output JSON của model -> index 0-based (hoặc None).

    AN TOÀN: JSON hỏng / thiếu "chon" / chon=0 / ngoài [1, n] -> None (không gợi ý).
    Dùng SỐ thay chuỗi NO_MATCH nên hết lệ thuộc so chuỗi ("NO_MATCH." / **NO_MATCH**
    / "tôi phải trả về NO_MATCH" đều không còn làm trượt).
    """
    try:
        data = json.loads(raw or "")
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    chon = data.get("chon")
    if not isinstance(chon, int) or isinstance(chon, bool):
        try:                                   # phòng model trả "2" dạng chuỗi
            chon = int(str(chon).strip())
        except (ValueError, TypeError, AttributeError):
            return None
    return chon - 1 if 1 <= chon <= n else None


async def choose_reply(question: str, candidates: list[dict]) -> dict:
    """GPT CHỌN 1 câu mẫu, ta trả về câu trả lời NGUYÊN VĂN (KHÔNG cho model viết).

    An toàn y tế: câu trả lời mẫu do Bác Sĩ Hội soạn & kiểm chứng nên model chỉ
    được đóng vai NGƯỜI CHỌN — trả JSON {"chon": <số>} (0 = không có câu nào hợp).
    Câu gửi khách lấy y nguyên `cau_tra_loi` của câu mẫu đó, không sửa một chữ,
    tránh việc model lược mất vế điều kiện / đổi sắc thái / trộn câu.

    3 lớp chặn (defense-in-depth):
      1. NGƯỠNG (code): bỏ câu mẫu có similarity < `rag_suggest_threshold` TRƯỚC khi
         gọi LLM. Không câu nào đạt -> NO_MATCH luôn, KHÔNG tốn 1 lượt gọi model.
      2. JSON `{"chon": <số>}` — parse chắc, không lệ thuộc so chuỗi.
      3. output lạ / số ngoài phạm vi -> coi là không gợi ý.

    Tách riêng để nút "Gợi ý trả lời" và trang "Thử tin nhắn" dùng CHUNG một logic.
    `candidates` = list {cau_hoi, cau_tra_loi, similarity, ...} đã xếp theo tương đồng.

    Trả về:
      - chọn được: {"reply": <cau_tra_loi NGUYÊN VĂN>, "no_match": False,
                    "chosen": <câu mẫu được chọn>}
      - không đạt ngưỡng / chon=0 / output lạ: {"reply": None, "no_match": True,
                    "chosen": None}
    """
    # Lớp 1 — chặn bằng code: chỉ giữ câu đạt ngưỡng rồi lấy top N.
    floor = settings.rag_suggest_threshold
    cands = [c for c in candidates if (c.get("similarity") or 0) >= floor]
    cands = cands[:_SUGGEST_CANDIDATES]
    if not cands:                          # lạc đề hết -> NO_MATCH, KHÔNG gọi LLM
        return {"reply": None, "no_match": True, "chosen": None}

    prompt = build_suggest_prompt(question, cands)
    raw = await complete(
        prompt, temperature=0.0, response_format={"type": "json_object"}
    )
    idx = _parse_choice_json(raw, len(cands))
    if idx is None:                        # chon=0 / JSON hỏng / ngoài phạm vi
        return {"reply": None, "no_match": True, "chosen": None}

    chosen = cands[idx]
    reply = (chosen.get("cau_tra_loi") or "").strip()   # NGUYÊN VĂN, không sửa
    if not reply:                          # câu mẫu rỗng bất thường -> coi như không có
        return {"reply": None, "no_match": True, "chosen": None}
    return {"reply": reply, "no_match": False, "chosen": chosen}


async def suggest_reply(text: str) -> dict:
    """Soạn GỢI Ý trả lời cho một tin của khách — RAG + GPT làm NGƯỜI CHỌN.

    Dùng cho nút "Gợi ý trả lời" ở màn Tin nhắn (human-in-the-loop): người bấm
    nút, câu gợi ý đổ vào ô trả lời để sửa rồi TỰ bấm Gửi. Vì vậy hàm này KHÔNG
    gửi tin đi và KHÔNG đọc/ghi phiên khách (tránh lệ thuộc bảng trang_thai_khach
    còn lệch schema — việc căn lại thuộc Tầng 2 của lộ trình).

    Luồng:
      1. Nhúng câu hỏi rồi lấy **top-k** câu mẫu tương đồng (kèm điểm similarity).
      2. `choose_reply` lo phần còn lại: chặn ngưỡng (code) -> GPT CHỌN (JSON) ->
         trả NGUYÊN VĂN câu mẫu được chọn, hoặc NO_MATCH.

    Trả về:
      - có gợi ý:  {"reply": <NGUYÊN VĂN>, "nguon": [<câu mẫu được chọn>]}
      - không hợp: {"reply": None, "nguon": [], "no_match": True}
    """
    vector = await embed(text)
    # Lấy top-k kèm điểm; việc lọc ngưỡng + chọn dồn hết vào choose_reply cho nhất quán.
    rows = await search_similar(vector, k=settings.rag_top_k)
    if not rows:                       # kho tri thức chưa có gì để đối chiếu
        return {"reply": None, "nguon": [], "no_match": True}

    result = await choose_reply(text, rows)   # chặn ngưỡng + GPT chọn / NO_MATCH
    if result["no_match"]:
        return {"reply": None, "nguon": [], "no_match": True}
    # nguon = đúng câu mẫu được chọn (reply là NGUYÊN VĂN câu trả lời của nó).
    chosen = result.get("chosen")
    return {"reply": result["reply"], "nguon": [chosen] if chosen else rows}


async def generate_reply(page_id: str, psid: str, text: str) -> str:
    """Nhận tin `text` của khách (page_id, psid), trả về câu trả lời của bot.

    ⚠️ Đây là luồng bot TỰ ĐỘNG (Tầng 2) — hiện CHƯA nối vào endpoint nào; giữ ở
    đây làm khung. Khi nối thật cần: (a) code `flow.next_step`, (b) xử lý trường
    hợp RAG trả về NO_MATCH (không gửi chuỗi "NO_MATCH" cho khách).
    """
    # Đọc phiên hiện tại của khách (đang ở kịch bản/bước nào, ngữ cảnh...).
    session = await get_session(page_id, psid)

    # 1) Ưu tiên đi theo kịch bản (luồng nhiều bước). Khớp -> lưu phiên & trả lời.
    scripted = next_step(session, text)
    if scripted is not None:
        await save_session(page_id, psid, session)
        return scripted

    # 2) Không khớp kịch bản -> RAG + LLM.
    context = await retrieve(text)                  # tìm các đoạn liên quan trong DB
    prompt = build_prompt(session, context, text)   # ghép persona + ngữ cảnh + câu hỏi
    reply = await complete(prompt)                  # gọi LLM sinh câu trả lời

    # Lưu lịch sử vào ngữ cảnh phiên (ngu_canh jsonb) rồi ghi xuống DB.
    session.setdefault("ngu_canh", {}).setdefault("history", []).append(
        {"user": text, "bot": reply}
    )
    await save_session(page_id, psid, session)
    return reply


def _parse_extract_json(raw: str) -> list[dict]:
    """Đọc {"de_xuat": [{cau_hoi, cau_tra_loi}]} từ output model -> list đã lọc sạch.

    AN TOÀN: JSON hỏng / sai dạng / thiếu chữ -> bỏ qua phần tử đó (không ném lỗi
    cả loạt); ai gọi hàm này nhận về [] nếu model không trích được gì hợp lệ.
    """
    try:
        data = json.loads(raw or "")
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    items = data.get("de_xuat")
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for it in items[:_EXTRACT_MAX_ITEMS]:
        if not isinstance(it, dict):
            continue
        cau_hoi = str(it.get("cau_hoi") or "").strip()
        cau_tra_loi = str(it.get("cau_tra_loi") or "").strip()
        if cau_hoi and cau_tra_loi:
            out.append({"cau_hoi": cau_hoi, "cau_tra_loi": cau_tra_loi})
    return out


async def extract_qa_candidates(transcript: str) -> list[dict]:
    """Trích đề xuất cặp hỏi-đáp từ 1 đoạn hội thoại thật (nút "Trích tri thức").

    CHỈ đề xuất — KHÔNG ghi DB (người dùng xem/sửa/bỏ ở màn hình trước khi bấm
    Lưu, xem app/web/routes/main.py). Hội thoại rỗng hoặc model không trích được gì
    hợp lệ -> trả về [].
    """
    transcript = (transcript or "").strip()
    if not transcript:
        return []
    prompt = build_extract_prompt(transcript)
    raw = await complete(
        prompt, temperature=0.0, response_format={"type": "json_object"}
    )
    return _parse_extract_json(raw)
