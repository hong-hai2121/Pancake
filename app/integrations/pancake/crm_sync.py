"""B2 — đổ hội thoại Pancake vào CRM (FR-011, FR-012 phần tối thiểu).

Một hội thoại từ poller đi qua đây thành: khách (`crm.customers`, chống trùng
4 bậc) + định danh + dòng `crm.conversations` + lead tự động nếu chưa có.

Nguyên tắc sống còn: hàm ở đây KHÔNG BAO GIỜ được ném lỗi lên poller — bot
trả lời khách là luồng chính, CRM là luồng bồi. Lỗi row nào ghi stderr row đó.

Ánh xạ trường (xem app/db/repositories/inbox_store.py):
    customer_id (UUID Pancake)  -> bậc 1: external_customer_id
    fb_id                       -> bậc 2: PSID
    phones[0]                   -> bậc 3: SĐT (chuẩn hoá trong service)
    page_id + conv_id           -> bậc 4: page + external_conversation_id
"""

import json
import sys

from app.db.repositories import customer_repo, page_repo
from app.services import customer_service

_page_cache: dict[str, int] = {}   # external_page_id -> crm.pages.id


def _crm_page_id(external_page_id: str, page_name: str) -> int:
    """Tìm-hoặc-tạo crm.pages cho page Pancake; cache vì poller gọi dày."""
    pid = _page_cache.get(external_page_id)
    if pid is None:
        pid = page_repo.find_or_create(
            platform="facebook",
            external_page_id=external_page_id,
            name=page_name or external_page_id,
        )["id"]
        _page_cache[external_page_id] = pid
    return pid


def _phones(raw) -> str | None:
    """`phones` là list (từ API) hoặc chuỗi JSON (đọc lại từ DB) — lấy số đầu."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except ValueError:
            return None
    return (raw or [None])[0]


def sync_row(external_page_id: str, page_name: str, conv: dict) -> bool:
    """Đồng bộ MỘT hội thoại. Trả True nếu vừa tạo khách mới. Idempotent."""
    page_id = _crm_page_id(str(external_page_id), page_name)
    conv_id = str(conv.get("conv_id") or "")
    kh, vua_tao = customer_service.upsert_from_source(
        platform="facebook",
        name=conv.get("name"),
        phone=_phones(conv.get("phones")),
        external_customer_id=conv.get("customer_id") or None,
        psid=conv.get("fb_id") or None,
        page_id=page_id,
        external_conversation_id=conv_id or None,
        source="pancake",
    )
    if conv_id:
        customer_repo.upsert_conversation(
            customer_id=kh["id"], page_id=page_id,
            external_conversation_id=conv_id,
            last_message_at=conv.get("updated_at") or None,
        )
    return vua_tao


def sync_batch(external_page_id: str, page_name: str, convs: list[dict]) -> dict:
    """Poller gọi sau mỗi mẻ upsert. Nuốt lỗi từng row — không vỡ luồng bot."""
    ket_qua = {"tao_moi": 0, "cap_nhat": 0, "loi": 0}
    for conv in convs:
        try:
            if sync_row(external_page_id, page_name, conv):
                ket_qua["tao_moi"] += 1
            else:
                ket_qua["cap_nhat"] += 1
        except Exception as err:  # noqa: BLE001 — xem docstring
            ket_qua["loi"] += 1
            print(
                f"[crm_sync] loi conv {conv.get('conv_id')}: {type(err).__name__}: {err}",
                file=sys.stderr,
            )
    return ket_qua
