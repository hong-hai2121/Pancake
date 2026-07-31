"""Chưng cất chat cũ -> cặp hỏi–đáp (gọi LLM gpt-4o-mini)."""

import json
import re

from app.ai.llm import complete

DISTILL_PROMPT = (
    "Dưới đây là một đoạn chat giữa khách và nhân viên bán hàng đã chốt đơn.\n"
    "Hãy rút ra các cặp (câu hỏi của khách, câu trả lời tốt của shop).\n"
    "CHỈ trả về JSON array, mỗi phần tử dạng "
    '{{"cau_hoi": "...", "cau_tra_loi": "..."}}. '
    "Không thêm chữ nào ngoài JSON.\n\n"
    "=== ĐOẠN CHAT ===\n{conversation}"
)


def _parse_pairs(raw: str) -> list[dict]:
    """Bóc JSON array từ output LLM (bỏ ```json fence nếu có)."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
    # Lấy đoạn từ '[' đầu tiên tới ']' cuối cho chắc.
    if "[" in text and "]" in text:
        text = text[text.index("["): text.rindex("]") + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    pairs = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and item.get("cau_hoi") and item.get("cau_tra_loi"):
            pairs.append(
                {
                    "cau_hoi": str(item["cau_hoi"]).strip(),
                    "cau_tra_loi": str(item["cau_tra_loi"]).strip(),
                }
            )
    return pairs


async def distill(conversation: str) -> list[dict]:
    """Biến một đoạn chat thành danh sách cặp {cau_hoi, cau_tra_loi}."""
    raw = await complete(
        DISTILL_PROMPT.format(conversation=conversation), temperature=0.0
    )
    return _parse_pairs(raw)
