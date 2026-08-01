"""FR-012 — kéo NỘI DUNG tin nhắn về crm.messages (bù cho crm_sync chỉ có snippet).

Chạy tách khỏi poller: poller phải nhanh cho bot, còn kéo tin nhắn tốn thêm
1 lời gọi Pancake cho MỖI hội thoại nên đi vòng riêng (worker `messages_loop`,
công tắc `MSG_SYNC_ENABLED`, mặc định TẮT như các đồng bộ CRM khác).

Chọn hội thoại nào để kéo: so `external_updated_at` (mốc bên Pancake, crm_sync
cập nhật mỗi lượt poll) với `messages_synced_at` (lần cuối kéo tin) — chỉ kéo
khi có tin mới, không kéo lại cả kho mỗi vòng.

Xử lý lỗi chia 2 đường theo đúng triết lý hàng đợi mục 4:
  * GỌI Pancake hỏng  -> KHÔNG vào hàng đợi (không có gì để phát lại);
    mốc messages_synced_at không nhích nên vòng sau tự kéo lại.
  * GHI DB hỏng       -> vào `crm.sync_errors` kèm nguyên văn mẻ tin đã lấy,
    worker retry phát lại từ payload, không phải gọi lại Pancake.
"""

import asyncio
import sys

from app.db.repositories import conversation_repo
from app.integrations.pancake import client
from app.services import integration_service

_PROVIDER = "pancake_pages"


def _to_row(msg: dict, external_page_id: str) -> dict:
    """Từ message đã chuẩn hoá của client -> dict cột crm.messages.

    `is_page` (from.id trùng page) nghĩa là PAGE trả lời — người thật hay bot
    không phân biệt được từ API nên quy hết về 'agent'; sender_user_id để
    trống, nhân viên phụ trách nằm ở conversations.assignee_user_id.
    """
    att = msg.get("attachments") or []
    return {
        "external_message_id": msg.get("id") or None,
        "sender_type": "agent" if msg.get("is_page") else "customer",
        "sender_external_id": msg.get("sender_id") or None,
        "sender_name": msg.get("sender_name") or None,
        "content": msg.get("text") or "",
        "msg_type": "attachment" if att and not (msg.get("text") or "").strip()
                    else "text",
        "attachments": att,
        "sent_at": msg.get("inserted_at") or "",
    }


def ghi_mot_me(conv_crm_id: int, rows: list[dict]) -> int:
    """Ghi 1 mẻ tin + đóng dấu tươi. Tách riêng để retry phát lại được y hệt."""
    them = conversation_repo.upsert_messages(conv_crm_id, rows)
    conversation_repo.danh_dau_msg_sync(conv_crm_id)
    return them


async def dong_bo_mot(conv: dict) -> int:
    """Kéo trọn tin nhắn 1 hội thoại (dict từ `hoi_thoai_cho_dong_bo`).

    Trả số tin THÊM MỚI. Lỗi gọi API thì ném lên cho vòng ngoài đếm — mốc
    tươi chưa đóng nên không mất lượt.
    """
    data = await client.get_conversation(
        str(conv["external_page_id"]),
        str(conv["external_conversation_id"]),
        conv.get("external_customer_id") or None,
    )
    rows = [_to_row(m, str(conv["external_page_id"]))
            for m in data.get("messages") or []]
    if not rows:
        # Page tắt hoặc hội thoại rỗng: vẫn đóng dấu để khỏi kéo lại vô ích.
        await asyncio.to_thread(conversation_repo.danh_dau_msg_sync, conv["id"])
        return 0
    try:
        return await asyncio.to_thread(ghi_mot_me, conv["id"], rows)
    except Exception as err:  # noqa: BLE001 — ghi DB hỏng -> hàng đợi phát lại
        integration_service.ghi_loi(
            _PROVIDER, "message", str(conv["external_conversation_id"]),
            err,
            payload={"_conv_crm_id": conv["id"], "_rows": rows},
            scope=str(conv["external_page_id"]),
        )
        raise


async def dong_bo_lo(limit: int = 20) -> dict:
    """Một vòng worker: nhặt hội thoại có tin mới, kéo lần lượt (không dồn dập).

    Trả {hoi_thoai, tin_moi, loi}. Mỗi vòng 1 dòng sync_logs khi có việc thật.
    """
    ket = {"hoi_thoai": 0, "tin_moi": 0, "loi": 0}
    convs = await asyncio.to_thread(conversation_repo.hoi_thoai_cho_dong_bo, limit)
    if not convs:
        return ket

    log_id = None
    try:
        log_id = await asyncio.to_thread(
            integration_service.mo_log, _PROVIDER, "message")
    except Exception as err:  # noqa: BLE001 — thiếu nhật ký vẫn phải đồng bộ
        print(f"[msg_sync] không mở được nhật ký: {err}", file=sys.stderr)

    for conv in convs:
        try:
            ket["tin_moi"] += await dong_bo_mot(conv)
            ket["hoi_thoai"] += 1
        except Exception as err:  # noqa: BLE001 — 1 hội thoại hỏng không vỡ cả mẻ
            ket["loi"] += 1
            print(f"[msg_sync] loi conv {conv.get('external_conversation_id')}: "
                  f"{type(err).__name__}: {err}", file=sys.stderr)

    if log_id:
        try:
            await asyncio.to_thread(
                integration_service.dong_log, log_id,
                {"tao_moi": ket["tin_moi"], "cap_nhat": ket["hoi_thoai"],
                 "loi": ket["loi"]},
            )
        except Exception as err:  # noqa: BLE001
            print(f"[msg_sync] không đóng được nhật ký: {err}", file=sys.stderr)
    return ket
