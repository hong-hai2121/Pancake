"""PRODUCT-001…008 (B6 — FR-060). Luật ở services/product_service.py.

Quyền: đọc = `customer.view` · sửa danh mục = `user.manage` (như sửa cấu trúc
pipeline B3 — việc quản trị) · duyệt nội dung = `content.approve` (nội dung
chưa duyệt không được AI/tư vấn dùng).
"""

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_permission
from app.core.errors import ApiError
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.db.repositories import catalog_repo
from app.schemas.catalog import (
    ProductApproveIn, ProductCreateIn, ProductStatusIn, ProductUpdateIn,
    ProductVersionIn,
)
from app.services import product_service

router = APIRouter(prefix="/api/v1/products", tags=["products"])

_xem = Depends(require_permission("customer.view"))
_danh_muc = Depends(require_permission("user.manage"))
_duyet = Depends(require_permission("content.approve"))


@router.get("")
async def list_products(
    q: str = "",
    status: str = Query("", pattern="^(active|inactive|discontinued)?$"),
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _xem,
):
    """PRODUCT-001."""
    rows, total = catalog_repo.list_products(
        q=q, status=status, limit=pt.limit, offset=pt.offset,
    )
    return ok(bao_trang(rows, total, pt))


@router.get("/{product_id}")
async def get_product(product_id: int, _user: dict = _xem):
    """PRODUCT-002 — kèm các phiên bản giá/nội dung."""
    sp = catalog_repo.get_product(product_id)
    if not sp:
        raise ApiError("NOT_FOUND", "Không tìm thấy sản phẩm")
    return ok({**sp, "versions": catalog_repo.list_product_versions(product_id)})


@router.post("", status_code=201)
async def create_product(body: ProductCreateIn, user: dict = _danh_muc):
    """PRODUCT-003 — tự chốt phiên bản 1 (giá + nội dung ban đầu)."""
    return ok(product_service.create_product(body.model_dump(), actor=user),
              "Đã tạo sản phẩm")


@router.put("/{product_id}")
async def update_product(product_id: int, body: ProductUpdateIn, user: dict = _danh_muc):
    """PRODUCT-004 — đổi giá tự snapshot phiên bản mới (FR-060)."""
    return ok(product_service.update_product(product_id, body.model_dump(), actor=user),
              "Đã cập nhật")


@router.post("/{product_id}/versions", status_code=201)
async def add_version(product_id: int, body: ProductVersionIn, user: dict = _danh_muc):
    """PRODUCT-005 — nội dung mới => approval quay về pending, chờ duyệt lại."""
    return ok(product_service.add_version(product_id, body.model_dump(), actor=user),
              "Đã tạo phiên bản — chờ duyệt nội dung")


@router.post("/{product_id}/approve")
async def approve_product(product_id: int, body: ProductApproveIn, user: dict = _duyet):
    """PRODUCT-006 — chỉ `content.approve`."""
    return ok(product_service.approve(product_id, approve_=body.approve, actor=user),
              "Đã duyệt nội dung" if body.approve else "Đã từ chối nội dung")


@router.patch("/{product_id}/status")
async def set_status(product_id: int, body: ProductStatusIn, user: dict = _danh_muc):
    """PRODUCT-007 — khoá/ngừng bán (không có delete: FR-060)."""
    return ok(product_service.set_status(product_id, body.status, actor=user),
              "Đã đổi trạng thái bán")


@router.get("/{product_id}/history")
async def history(product_id: int, _user: dict = _xem):
    """PRODUCT-008 — phiên bản + vết audit."""
    return ok(product_service.history(product_id))
