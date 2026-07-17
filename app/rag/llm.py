"""Gọi LLM (Gemini/OpenAI) sinh câu trả lời."""

from app.config import settings


async def complete(prompt: str) -> str:
    """Sinh câu trả lời từ prompt đã ghép sẵn.

    TODO: gọi LLM theo settings.llm_provider:
      - gemini: genai.GenerativeModel("gemini-1.5-flash").generate_content(prompt)
      - openai: client.chat.completions.create(model="gpt-4o-mini", ...)
    """
    raise NotImplementedError("Cài đặt gọi LLM")
