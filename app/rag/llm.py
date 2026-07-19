"""Gọi LLM (OpenAI) sinh câu trả lời — "não" của bot."""

from functools import lru_cache

from app.config import settings


class LLMError(RuntimeError):
    """Lỗi khi gọi LLM."""


@lru_cache
def _client():
    from openai import AsyncOpenAI

    if not settings.openai_api_key:
        raise LLMError("Chưa cấu hình OPENAI_API_KEY trong .env")
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def complete(prompt: str, temperature: float = 0.4) -> str:
    """Sinh câu trả lời từ prompt đã ghép sẵn (xem bot/prompt.build_prompt)."""
    if settings.llm_provider != "openai":
        raise LLMError(
            f"Chỉ hỗ trợ llm_provider=openai (đang là '{settings.llm_provider}'). "
            f"Đặt LLM_PROVIDER=openai."
        )
    resp = await _client().chat.completions.create(
        model=settings.llm_model,             # gpt-4o-mini
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return (resp.choices[0].message.content or "").strip()
