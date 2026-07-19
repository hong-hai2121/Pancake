"""Tìm top-k cặp hỏi–đáp liên quan trong hoi_thoai_mau."""

from app.db.queries import search_similar
from app.rag.embedding import embed


async def retrieve(text: str, k: int = 5) -> list[str]:
    """Vector hóa câu hỏi rồi tìm k cặp gần nhất, trả về dạng ngữ cảnh cho LLM."""
    vector = await embed(text)
    rows = await search_similar(vector, k=k)
    return [
        f"Hỏi: {r.get('cau_hoi')} → Đáp: {r.get('cau_tra_loi')}"
        for r in rows
        if r.get("cau_tra_loi")
    ]
