"""Luật hội thoại CRM — FR-012 + CONV-001…006 + PANCAKE-010.

Nguồn dữ liệu là crm.conversations/crm.messages (đồng bộ về bằng
integrations/pancake/message_sync.py) — MỌI hàm đọc ở đây KHÔNG gọi Pancake
(luật mục 4 "không gọi API mỗi lần mở màn hình"). Ngoại lệ duy nhất là
`gui_tin` (CONV-006): người chủ động bấm gửi thì mới gọi thật.

Luật FR-012 cài ở các tầng:
  * Nội dung gốc không sửa — repo upsert DO NOTHING, service không có hàm sửa/xoá tin.
  * Tin phải gắn đúng khách — gắn/gỡ qua CONV-004 có kiểm khách sống + audit.
  * Lỗi đồng bộ phải retry — message_sync đẩy hàng đợi sync_errors (mục 4).
"""

from app.core.errors import ApiError
from app.db.repositories import audit_repo, conversation_repo, customer_repo, user_repo
from app.integrations.pancake.links import link_hoi_thoai


def _actor_id(actor: dict | None) -> int | None:
    try:
        return int((actor or {}).get("sub") or 0) or None
    except (TypeError, ValueError):
        return None


def _lay(conv_id: int) -> dict:
    row = conversation_repo.get(conv_id)
    if not row:
        raise ApiError("NOT_FOUND", "Không tìm thấy hội thoại")
    return row


# ------------------------------------------------------------------ đọc
def danh_sach(*, customer_id: int | None, page_id: int | None, q: str,
              limit: int, offset: int) -> tuple[list[dict], int]:
    """CONV-001 — danh sách hội thoại (lọc theo khách/page/từ khoá)."""
    return conversation_repo.list_conversations(
        customer_id=customer_id, page_id=page_id, q=q, limit=limit, offset=offset)


def chi_tiet(conv_id: int) -> dict:
    """CONV-002 — kèm cờ `tin_da_tuoi` để màn hình biết kho tin đầy đủ chưa."""
    row = _lay(conv_id)
    row["tin_da_tuoi"] = bool(
        row.get("messages_synced_at")
        and (row.get("external_updated_at") is None
             or row["external_updated_at"] <= row["messages_synced_at"])
    )
    return row


def tin_nhan(conv_id: int, *, limit: int, offset: int) -> tuple[list[dict], int, dict]:
    """CONV-003 — trang tin nhắn + meta cho màn hình biết nguồn tươi tới đâu.

    Chưa đồng bộ lần nào thì trả rỗng kèm `chua_dong_bo=True` (màn hình bày
    nút "Mở trên Pancake" thay vì khung trống không lời giải thích).
    """
    conv = _lay(conv_id)
    rows, total = conversation_repo.list_messages(
        conv_id, limit=limit, offset=offset)
    meta = {
        "chua_dong_bo": conv.get("messages_synced_at") is None,
        "messages_synced_at": conv.get("messages_synced_at"),
        "external_link": link_hoi_thoai(
            conv.get("external_page_id") or "",
            conv.get("external_conversation_id") or ""),
    }
    return rows, total, meta


def link_ngoai(conv_id: int) -> dict:
    """PANCAKE-010 — link mở đúng hội thoại bên Pancake (chỉ ghép chuỗi)."""
    conv = _lay(conv_id)
    link = link_hoi_thoai(conv.get("external_page_id") or "",
                          conv.get("external_conversation_id") or "")
    if not link:
        raise ApiError("NOT_FOUND",
                       "Hội thoại không có định danh Pancake — không dựng được link")
    return {"link": link}


# ------------------------------------------------------------------ ghi
def gan_khach(conv_id: int, customer_id: int, actor: dict | None = None) -> dict:
    """CONV-004 — gắn hội thoại vào khách ("tin nhắn phải gắn đúng khách").

    Cho gắn LẠI (đổi khách) vì đây chính là công cụ sửa khi máy gắn sai;
    mọi lần đổi đều vào audit kèm giá trị cũ→mới.
    """
    conv = _lay(conv_id)
    kh = customer_repo.get_customer(customer_id)
    if not kh or kh.get("deleted_at") or kh.get("status") == "merged":
        raise ApiError("NOT_FOUND", "Khách không tồn tại (hoặc đã gộp/xoá)")
    if conv.get("customer_id") == customer_id:
        return conv  # gắn đúng chỗ cũ — không ghi audit rác
    moi = conversation_repo.attach_customer(conv_id, customer_id)
    audit_repo.ghi(
        action="conversation_attach", object_type="conversations",
        object_id=conv_id, user_id=_actor_id(actor),
        old_value={"customer_id": conv.get("customer_id")},
        new_value={"customer_id": customer_id},
    )
    return moi


def gan_nhan_vien(conv_id: int, user_id: int | None,
                  actor: dict | None = None) -> dict:
    """CONV-005 — gán nhân viên CRM phụ trách hội thoại (None = bỏ gán).

    CHỈ đụng conversations.assignee_user_id — ownership KHÁCH có luật riêng
    (customer_assignments, A5), không tự lây từ hội thoại sang.
    """
    conv = _lay(conv_id)
    if user_id is not None:
        nv = user_repo.get_user(user_id)
        if not nv:
            raise ApiError("NOT_FOUND", "Không tìm thấy nhân viên")
        if nv.get("status") != "active":
            raise ApiError("CONFLICT", "Nhân viên không còn hoạt động — không gán được")
    if conv.get("assignee_user_id") == user_id:
        return conv
    moi = conversation_repo.assign(conv_id, user_id)
    audit_repo.ghi(
        action="conversation_assign", object_type="conversations",
        object_id=conv_id, user_id=_actor_id(actor),
        old_value={"assignee_user_id": conv.get("assignee_user_id")},
        new_value={"assignee_user_id": user_id},
    )
    return moi


async def gui_tin(conv_id: int, message: str, actor: dict | None = None) -> dict:
    """CONV-006 — GỬI THẬT một tin vào hội thoại qua Pancake (không hoàn tác được).

    Đặc tả: "Chỉ dùng nếu Pancake cho phép và quyền đã được cấp" — page đang
    TẮT thì client tự chặn. Gửi xong ghi luôn bản CRM (khỏi chờ vòng đồng bộ)
    + audit. Tin ghi tay không có external_message_id — vòng đồng bộ sau kéo
    bản chính thức về sẽ THÊM dòng mới chứ không đè (chấp nhận 1 tin 2 dòng
    trong cửa sổ ngắn, dọn ở B11 nếu thành phiền).
    """
    from app.integrations.pancake import client

    noi_dung = (message or "").strip()
    if not noi_dung:
        raise ApiError("VALIDATION_ERROR", "Nội dung tin nhắn trống")
    conv = _lay(conv_id)
    if not (conv.get("external_page_id") and conv.get("external_conversation_id")):
        raise ApiError("CONFLICT", "Hội thoại không có định danh Pancake — không gửi được")

    try:
        kq = await client.send_message(
            str(conv["external_page_id"]), str(conv["external_conversation_id"]),
            noi_dung)
    except client.PancakeError as err:
        raise ApiError("INTEGRATION_ERROR", f"Pancake từ chối: {err}") from err

    conversation_repo.upsert_messages(conv_id, [{
        "external_message_id": str((kq or {}).get("id") or "") or None,
        "sender_type": "agent",
        "sender_user_id": _actor_id(actor),
        "content": noi_dung,
        "msg_type": "text",
        "sent_at": "",          # repo tự lấy now()
    }])
    audit_repo.ghi(
        action="message_sent", object_type="conversations", object_id=conv_id,
        user_id=_actor_id(actor), new_value={"length": len(noi_dung)},
    )
    return {"sent": True}
