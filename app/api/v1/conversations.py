"""API hội thoại & tin nhắn — CONV-001…006 + PANCAKE-010 (FR-012).

Route là lớp mỏng: luật nằm ở services/conversation_service.py.

Quyền: đọc = `customer.view` (hội thoại là dữ liệu khách — Sale/CSKH xem từ hồ
sơ 360°); gắn khách/gán nhân viên/gửi tin = `customer.edit`. CONV-007/008 (AI)
thuộc C-MVP4, chưa làm.
"""

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_permission
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.schemas.conversation import AssignIn, AttachCustomerIn, SendMessageIn
from app.services import conversation_service

router = APIRouter(prefix="/api/v1", tags=["conversations"])

_xem = Depends(require_permission("customer.view"))
_sua = Depends(require_permission("customer.edit"))


@router.get("/conversations")
async def list_conversations(
    customer_id: int | None = Query(None, gt=0),
    page_id: int | None = Query(None, gt=0),
    q: str = "",
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _xem,
):
    """CONV-001 — danh sách hội thoại, mới nhất trước (tab Hội thoại màn 9)."""
    rows, total = conversation_service.danh_sach(
        customer_id=customer_id, page_id=page_id, q=q,
        limit=pt.limit, offset=pt.offset)
    return ok(bao_trang(rows, total, pt))


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: int, _user: dict = _xem):
    """CONV-002 — chi tiết + cờ `tin_da_tuoi` (kho tin đã đủ so với Pancake chưa)."""
    return ok(conversation_service.chi_tiet(conversation_id))


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: int,
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _xem,
):
    """CONV-003 — trang tin nhắn (cũ trước mới sau); đọc từ crm.messages,
    KHÔNG gọi Pancake. Kèm meta {chua_dong_bo, external_link}."""
    rows, total, meta = conversation_service.tin_nhan(
        conversation_id, limit=pt.limit, offset=pt.offset)
    data = bao_trang(rows, total, pt)
    data["meta"] = meta
    return ok(data)


@router.get("/conversations/{conversation_id}/external-link")
async def external_link(conversation_id: int, _user: dict = _xem):
    """PANCAKE-010 — link mở đúng hội thoại bên Pancake (chỉ ghép chuỗi)."""
    return ok(conversation_service.link_ngoai(conversation_id))


@router.post("/conversations/{conversation_id}/attach-customer")
async def attach_customer(
    conversation_id: int, body: AttachCustomerIn, user: dict = _sua,
):
    """CONV-004 — gắn hội thoại vào khách (sửa cả trường hợp máy gắn sai)."""
    return ok(
        conversation_service.gan_khach(conversation_id, body.customer_id, actor=user),
        "Đã gắn hội thoại vào khách",
    )


@router.post("/conversations/{conversation_id}/assign")
async def assign(conversation_id: int, body: AssignIn, user: dict = _sua):
    """CONV-005 — gán nhân viên CRM phụ trách hội thoại."""
    return ok(
        conversation_service.gan_nhan_vien(conversation_id, body.user_id, actor=user),
        "Đã gán nhân viên" if body.user_id else "Đã bỏ gán",
    )


@router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: int, body: SendMessageIn, user: dict = _sua):
    """CONV-006 — GỬI THẬT tin nhắn tới khách qua Pancake (page tắt thì chặn)."""
    return ok(
        await conversation_service.gui_tin(conversation_id, body.message, actor=user),
        "Đã gửi tin nhắn",
    )
