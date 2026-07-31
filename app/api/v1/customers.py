"""CUSTOMER-001…012 + IDENTITY-001/002 (B1 — docs/B1-KHACH-HANG.md).

Quyền: đọc = `customer.view` · ghi = `customer.edit`.
Riêng GỘP KHÁCH (CUSTOMER-007) = `user.manage` — FR-022 ghi rõ "Admin, quản lý
có quyền", gộp sai là dồn nhầm cả lịch sử đơn/hội thoại của hai người.
ATTRIBUTION-001/002 chưa làm — thuộc module Marketing (giai đoạn C-MVP5).
"""

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_permission
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.schemas.customer import (
    CustomerAssignIn, CustomerCreateIn, CustomerUpdateIn, DeleteIn,
    IdentityIn, MergeIn, TagIn,
)
from app.services import customer_service

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

_xem = Depends(require_permission("customer.view"))
_sua = Depends(require_permission("customer.edit"))
_quan_tri = Depends(require_permission("user.manage"))


# /customers/duplicates phải khai TRƯỚC /customers/{id} kẻo bị nuốt.

@router.get("/duplicates")
async def duplicates(limit: int = Query(50, ge=1, le=200), _user: dict = _xem):
    """CUSTOMER-006 — nhóm nghi trùng theo SĐT chuẩn hoá."""
    return ok({"items": customer_service.find_duplicates(limit)})


@router.get("")
async def list_customers(
    keyword: str = "",
    status: str = Query("", pattern="^(new|consulting|customer|treating|completed|churned|blocked)?$"),
    source: str = "",
    owner_id: int | None = Query(None),
    assignment_type: str = Query("", pattern="^(sale|cskh|chuyen_mon)?$"),
    tag_id: int | None = Query(None),
    has_order: bool | None = Query(None),
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _xem,
):
    """CUSTOMER-001 — bộ lọc màn 8 (phần dữ liệu đã có ở lát này)."""
    rows, total = customer_service.list_customers(
        keyword=keyword, status=status or None, source=source or None,
        owner_id=owner_id, assignment_type=assignment_type or None,
        tag_id=tag_id, has_order=has_order, limit=pt.limit, offset=pt.offset,
    )
    return ok(bao_trang(rows, total, pt))


@router.get("/{customer_id}")
async def get_customer(customer_id: int, _user: dict = _xem):
    """CUSTOMER-002 — kèm tags + người phụ trách đang mở."""
    return ok(customer_service.get_customer(customer_id))


@router.post("", status_code=201)
async def create_customer(body: CustomerCreateIn, user: dict = _sua):
    """CUSTOMER-003 / FR-020 — nghi trùng trả DUPLICATE_CUSTOMER kèm ứng viên."""
    kh = customer_service.create_customer(
        body.model_dump(exclude={"force"}), force=body.force,
        actor_id=int(user["sub"]),
    )
    return ok(kh, "Đã tạo khách hàng")


@router.put("/{customer_id}")
async def update_customer(
    customer_id: int, body: CustomerUpdateIn, user: dict = _sua
):
    """CUSTOMER-004."""
    kh = customer_service.update_customer(
        customer_id, body.model_dump(exclude_none=True), actor_id=int(user["sub"])
    )
    return ok(kh, "Đã cập nhật")


@router.delete("/{customer_id}")
async def delete_customer(
    customer_id: int, body: DeleteIn | None = None, user: dict = _sua
):
    """CUSTOMER-005 — xoá MỀM (đặc tả cấm xoá cứng)."""
    customer_service.delete_customer(
        customer_id, actor_id=int(user["sub"]),
        reason=body.reason if body else None,
    )
    return ok({}, "Đã xoá (mềm)")


@router.post("/merge")
async def merge(body: MergeIn, user: dict = _quan_tri):
    """CUSTOMER-007 / FR-022 — hồ sơ phụ giữ nguyên, status=merged."""
    out = customer_service.merge_customers(
        primary_id=body.primary_customer_id,
        duplicate_ids=body.duplicate_customer_ids,
        actor_id=int(user["sub"]),
    )
    return ok(out, "Đã hợp nhất")


@router.get("/{customer_id}/timeline")
async def timeline(
    customer_id: int, limit: int = Query(100, ge=1, le=500), _user: dict = _xem
):
    """CUSTOMER-008 — tin nhắn/cuộc gọi/lead/đơn/chăm/việc trộn theo thời gian."""
    return ok({"items": customer_service.timeline(customer_id, limit)})


@router.post("/{customer_id}/tags", status_code=201)
async def add_tag(customer_id: int, body: TagIn, user: dict = _sua):
    """CUSTOMER-009 — tag_id có sẵn hoặc name(+type) tìm-hoặc-tạo."""
    out = customer_service.add_tag(
        customer_id=customer_id, tag_id=body.tag_id,
        name=body.name, type_=body.type, actor_id=int(user["sub"]),
    )
    return ok(out, "Đã gắn tag")


@router.delete("/{customer_id}/tags/{tag_id}")
async def remove_tag(customer_id: int, tag_id: int, user: dict = _sua):
    """CUSTOMER-010."""
    customer_service.remove_tag(
        customer_id=customer_id, tag_id=tag_id, actor_id=int(user["sub"])
    )
    return ok({}, "Đã gỡ tag")


@router.post("/{customer_id}/assign")
async def assign(customer_id: int, body: CustomerAssignIn, user: dict = _sua):
    """CUSTOMER-011 — Sale/CSKH là 2 ownership riêng; thay người phải có lý do."""
    out = customer_service.assign(
        customer_id=customer_id, user_id=body.user_id,
        assignment_type=body.assignment_type, reason=body.reason,
        actor_id=int(user["sub"]),
    )
    return ok(out, "Đã phân công")


@router.get("/{customer_id}/assignment-history")
async def assignment_history(customer_id: int, _user: dict = _xem):
    """CUSTOMER-012."""
    return ok({"items": customer_service.assignment_history(customer_id)})


@router.get("/{customer_id}/identities")
async def list_identities(customer_id: int, _user: dict = _xem):
    """IDENTITY-001."""
    return ok({"items": customer_service.list_identities(customer_id)})


@router.post("/{customer_id}/identities", status_code=201)
async def add_identity(customer_id: int, body: IdentityIn, user: dict = _sua):
    """IDENTITY-002 — định danh đã thuộc khách khác thì DUPLICATE_CUSTOMER."""
    row = customer_service.add_identity(
        customer_id=customer_id, platform=body.platform,
        external_customer_id=body.external_customer_id,
        psid=body.psid, page_id=body.page_id, actor_id=int(user["sub"]),
    )
    return ok(row, "Đã thêm định danh")
