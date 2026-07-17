"""Tìm top-k đoạn liên quan trong kich_ban / hoi_thoai_mau."""

from app.db.queries import search_similar
from app.rag.embedding import embed


async def retrieve(text: str, k: int = 5) -> list[str]:
    """Vector hóa câu hỏi rồi tìm k đoạn gần nhất trong DB."""
    vector = await embed(text)
    rows = await search_similar(vector, k=k)
    return [row["noi_dung"] for row in rows]
