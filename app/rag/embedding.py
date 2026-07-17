"""Vector hóa câu (gọi API embedding)."""

from app.config import settings


async def embed(text: str) -> list[float]:
    """Trả về vector embedding cho một câu.

    TODO: gọi API theo settings.embedding_provider:
      - gemini: genai.embed_content(model=settings.embedding_model, ...)  -> 768d
      - openai: client.embeddings.create(model="text-embedding-3-small")  -> 1536d
    Nhớ đồng bộ số chiều với vector(...) trong scripts/init_db.sql.
    """
    raise NotImplementedError("Cài đặt gọi API embedding")


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Vector hóa nhiều câu một lần (dùng cho ingestion)."""
    return [await embed(t) for t in texts]
