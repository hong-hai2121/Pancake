"""Vector hóa câu (gọi API embedding).

Provider mặc định: OpenAI text-embedding-3-small (chiều gốc 1536). Số chiều lấy
từ `settings.embedding_dim` (đặt trong .env = 1536) để khớp cột embedding
`vector(1536)` trong DB thật. Truyền `dimensions=1536` = dùng TRỌN kích thước gốc
của model, KHÔNG cắt bớt (không mất thông tin).
"""

from functools import lru_cache

from app.core.config import settings


class EmbeddingError(RuntimeError):
    """Lỗi khi gọi API embedding."""


@lru_cache
def _client():
    from openai import AsyncOpenAI

    if not settings.openai_api_key:
        raise EmbeddingError("Chưa cấu hình OPENAI_API_KEY trong .env")
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _clean(text: str) -> str:
    return (text or "").replace("\n", " ").strip()


async def _openai_embed(texts: list[str]) -> list[list[float]]:
    # OpenAI không nhận chuỗi rỗng -> thay bằng khoảng trắng.
    inputs = [t or " " for t in texts]
    resp = await _client().embeddings.create(
        model=settings.embedding_model,       # text-embedding-3-small
        input=inputs,
        dimensions=settings.embedding_dim,    # 1536 = full, khớp cột vector(1536) DB thật
    )
    return [d.embedding for d in resp.data]


async def embed(text: str) -> list[float]:
    """Trả về vector embedding cho một câu (dài `embedding_dim`)."""
    if settings.embedding_provider != "openai":
        raise EmbeddingError(
            f"Chỉ hỗ trợ embedding_provider=openai (đang là "
            f"'{settings.embedding_provider}'). Đặt EMBEDDING_PROVIDER=openai."
        )
    return (await _openai_embed([_clean(text)]))[0]


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Vector hóa nhiều câu trong 1 lần gọi (dùng cho ingestion)."""
    if not texts:
        return []
    if settings.embedding_provider != "openai":
        raise EmbeddingError("Chỉ hỗ trợ embedding_provider=openai")
    return await _openai_embed([_clean(t) for t in texts])
