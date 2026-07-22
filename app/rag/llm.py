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


async def complete(
    prompt: str, temperature: float = 0.4, response_format: dict | None = None
) -> str:
    """Sinh câu trả lời từ prompt đã ghép sẵn (xem bot/prompt.build_prompt).

    `response_format` — truyền thẳng cho OpenAI, vd {"type": "json_object"} để ép
    model trả JSON hợp lệ (dùng cho bước CHỌN câu mẫu). None = trả text thường.
    """
    if settings.llm_provider != "openai":
        raise LLMError(
            f"Chỉ hỗ trợ llm_provider=openai (đang là '{settings.llm_provider}'). "
            f"Đặt LLM_PROVIDER=openai."
        )
    kwargs: dict = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = await _client().chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()
