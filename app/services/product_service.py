"""Nghiệp vụ danh mục sản phẩm (B6 — FR-060). KHÔNG import FastAPI.

Luật FR-060:
  * KHÔNG có delete — sản phẩm đã có đơn không được biến mất; ngừng bán thì
    PATCH status (discontinued), lịch sử đơn cũ giữ nguyên.
  * ĐỔI GIÁ tạo phiên bản mới (product_versions.price) — đơn cũ không đổi vì
    order_items chốt giá lúc lên đơn.
  * Nội dung tư vấn (usage_text/claims) sửa là approval_status quay về
    `pending` — nội dung CHƯA DUYỆT không được AI/tư vấn dùng; duyệt lại bằng
    PRODUCT-006 (quyền content.approve).
"""

from psycopg.errors import UniqueViolation

from app.core.errors import ApiError
from app.db.repositories import audit_repo, catalog_repo


def _audit(actor: dict | None, **kw) -> None:
    audit_repo.ghi(
        user_id=int(actor["sub"]) if actor else None,
        object_type="products", **kw,
    )


def _lay(product_id: int) -> dict:
    sp = catalog_repo.get_product(product_id)
    if not sp:
        raise ApiError("NOT_FOUND", "Không tìm thấy sản phẩm")
    return sp


def create_product(data: dict, *, actor: dict | None = None) -> dict:
    try:
        sp = catalog_repo.create_product(data)
    except UniqueViolation as err:
        raise ApiError("VALIDATION_ERROR", "Mã sản phẩm đã tồn tại",
                       errors={"product_code": "đã tồn tại"}) from err
    # Phiên bản 1 chốt giá + nội dung ban đầu — có mốc đối chiếu ngay từ đầu
    catalog_repo.add_product_version(
        sp["id"], price=sp["price"], usage_text=data.get("usage_text"),
        approved_claims=data.get("approved_claims"),
        prohibited_claims=data.get("prohibited_claims"),
    )
    _audit(actor, action="product_create", object_id=sp["id"],
           new_value={"name": sp["name"], "price": str(sp["price"])})
    return catalog_repo.get_product(sp["id"])


def update_product(product_id: int, data: dict, *, actor: dict | None = None) -> dict:
    """PRODUCT-004 — đổi giá thì tự snapshot phiên bản mới (FR-060)."""
    sp = _lay(product_id)
    data = {k: v for k, v in data.items() if v is not None}
    truoc, sau = {}, {}
    for k, v in data.items():
        if sp.get(k) != v:
            truoc[k], sau[k] = sp.get(k), v
    if not sau:
        return sp
    try:
        catalog_repo.update_product(product_id, sau)
    except UniqueViolation as err:
        raise ApiError("VALIDATION_ERROR", "Mã sản phẩm đã tồn tại",
                       errors={"product_code": "đã tồn tại"}) from err
    if "price" in sau:
        catalog_repo.add_product_version(
            product_id, price=sau["price"], usage_text=None,
            approved_claims=None, prohibited_claims=None,
        )
    _audit(actor, action="product_update", object_id=product_id,
           old_value={k: str(v) for k, v in truoc.items()},
           new_value={k: str(v) for k, v in sau.items()})
    return catalog_repo.get_product(product_id)


def add_version(product_id: int, data: dict, *, actor: dict | None = None) -> dict:
    """PRODUCT-005 — phiên bản NỘI DUNG mới: chưa duyệt là chưa được dùng."""
    sp = _lay(product_id)
    pb = catalog_repo.add_product_version(
        product_id, price=data.get("price", sp["price"]),
        usage_text=data.get("usage_text"),
        approved_claims=data.get("approved_claims"),
        prohibited_claims=data.get("prohibited_claims"),
    )
    if data.get("price") is not None and data["price"] != sp["price"]:
        catalog_repo.update_product(product_id, {"price": data["price"]})
    catalog_repo.set_product_approval(product_id, "pending")
    _audit(actor, action="product_version_add", object_id=product_id,
           new_value={"version_no": pb["version_no"],
                      "price": str(pb["price"])},
           reason="nội dung mới -> approval_status=pending, chờ duyệt lại")
    return pb


def approve(product_id: int, *, approve_: bool = True,
            actor: dict | None = None) -> dict:
    """PRODUCT-006 — duyệt/từ chối nội dung (quyền content.approve ở API)."""
    sp = _lay(product_id)
    trang_thai = "approved" if approve_ else "rejected"
    catalog_repo.set_product_approval(product_id, trang_thai)
    _audit(actor, action="product_approval", object_id=product_id,
           old_value={"approval_status": sp["approval_status"]},
           new_value={"approval_status": trang_thai})
    return catalog_repo.get_product(product_id)


def set_status(product_id: int, status: str, *, actor: dict | None = None) -> dict:
    """PRODUCT-007 — khoá/ngừng bán. `discontinued` khi đã có đơn vẫn CHO PHÉP
    (chỉ chặn xoá — mà xoá thì không có đường nào), đơn cũ giữ nguyên."""
    sp = _lay(product_id)
    if status == sp["status"]:
        return sp
    catalog_repo.set_product_status(product_id, status)
    _audit(actor, action="product_status", object_id=product_id,
           old_value={"status": sp["status"]}, new_value={"status": status})
    return catalog_repo.get_product(product_id)


def history(product_id: int) -> dict:
    """PRODUCT-008 — phiên bản giá/nội dung + vết audit."""
    _lay(product_id)
    audit, _ = audit_repo.list_logs(
        object_type="products", object_id=product_id, limit=50, offset=0,
    )
    return {"versions": catalog_repo.list_product_versions(product_id),
            "audit": audit}
