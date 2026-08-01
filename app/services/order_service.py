"""Luật nghiệp vụ đơn hàng — B7 (FR-080…082).

- 11 trạng thái chuẩn + luật chuyển (TRANSITIONS); đổi trạng thái LUÔN ghi
  lịch sử, không bao giờ xoá lịch sử (order_status_history).
- Phân loại đơn đầu / mua lại TỰ ĐỘNG lúc tạo (đơn hủy không tính là đã mua).
- Giá dòng hàng chốt TẠI THỜI ĐIỂM BÁN (mặc định lấy products.price hiện tại,
  sau đó products.price đổi cũng không ảnh hưởng đơn cũ).
- Ánh xạ trạng thái Pancake POS -> CRM đọc/sửa ở đây (màn 23); phần ĐỔ đơn POS
  về nằm ở app/integrations/pancake_pos/pos_sync.py (gọi ngược vào service này).

KHÔNG import FastAPI (quy ước services/) — route chỉ là lớp mỏng gọi xuống.
"""

from decimal import Decimal

from psycopg.errors import ForeignKeyViolation, UniqueViolation

from app.core.errors import ApiError
from app.db.repositories import audit_repo, catalog_repo, customer_repo, order_repo

# 11 trạng thái chuẩn (FR-080) — thứ tự = vòng đời xuôi của đơn.
ORDER_STATUSES: list[str] = [
    "draft",              # Nháp — Sale đang lên đơn
    "pending",            # Chờ xác nhận
    "confirmed",          # Đã xác nhận (gồm chờ hàng / đã đặt hàng NCC)
    "packing",            # Đang đóng gói (gồm chờ in / đã in)
    "awaiting_shipment",  # Chờ chuyển hàng (chờ ĐVVC lấy)
    "shipping",           # Đang giao
    "delivered",          # Đã giao — đóng dấu delivered_at (mốc khởi tính CSKH)
    "collected",          # Đã thu tiền / đối soát
    "returning",          # Đang hoàn (gồm hoàn một phần)
    "returned",           # Đã hoàn
    "cancelled",          # Đã hủy (gồm đã xóa bên POS)
]

ORDER_TYPES = {"new", "repurchase", "upsell", "exchange"}

# Luật chuyển trạng thái cho thao tác TAY trong CRM. Đồng bộ POS đi đường
# force=True (POS là nguồn sự thật, CRM không cãi thực tế) nhưng vẫn ghi lịch sử.
TRANSITIONS: dict[str, set[str]] = {
    "draft":             {"pending", "confirmed", "cancelled"},
    "pending":           {"confirmed", "cancelled"},
    "confirmed":         {"packing", "awaiting_shipment", "shipping", "cancelled"},
    "packing":           {"awaiting_shipment", "shipping", "cancelled"},
    "awaiting_shipment": {"shipping", "cancelled"},
    "shipping":          {"delivered", "returning"},
    "delivered":         {"collected", "returning"},
    "collected":         {"returning"},
    "returning":         {"returned", "delivered"},
    "returned":          set(),   # trạng thái chót — không đi tiếp
    "cancelled":         set(),   # trạng thái chót
}


def _actor_id(actor: dict | None) -> int | None:
    return int(actor["sub"]) if actor else None


def _audit(actor: dict | None, **kw) -> None:
    audit_repo.ghi(user_id=_actor_id(actor), object_type="orders", **kw)


def _lay(order_id: int) -> dict:
    don = order_repo.get_order(order_id)
    if not don:
        raise ApiError("NOT_FOUND", "Không tìm thấy đơn hàng")
    return don


def phan_loai_don(customer_id: int, *, truoc_thoi_diem=None) -> str:
    """FR-082: khách đã có đơn (không tính hủy) -> 'repurchase', chưa -> 'new'."""
    so_don_truoc = order_repo.count_prior_orders(
        customer_id, truoc_thoi_diem=truoc_thoi_diem
    )
    return "repurchase" if so_don_truoc > 0 else "new"


# ------------------------------------------------------------------ tạo / sửa
def create_order(data: dict, *, actor: dict | None = None) -> dict:
    """ORDER-003 — tạo đơn tay trong CRM (đơn POS đi đường pos_sync, không vào đây).

    `data`: customer_id (bắt buộc), items (>=1 dòng: product_id, quantity,
    unit_price?, treatment_template_id?), status? (mặc định draft), order_type?
    (bỏ trống = tự phân loại new/mua lại), sale_owner_id?, cskh_owner_id?, note?.
    """
    customer_id = data.get("customer_id")
    if not customer_id or not customer_repo.get_customer(int(customer_id)):
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng",
                       errors={"customer_id": "không tồn tại"})

    items_in = data.get("items") or []
    if not items_in:
        raise ApiError("MISSING_REQUIRED_DATA", "Đơn phải có ít nhất 1 dòng hàng",
                       errors={"items": "trống"})

    status = data.get("status") or "draft"
    if status not in ORDER_STATUSES:
        raise ApiError("VALIDATION_ERROR", f"Trạng thái lạ: {status}",
                       errors={"status": "không thuộc 11 trạng thái chuẩn"})

    # Chốt giá từng dòng TẠI THỜI ĐIỂM BÁN: client không gửi giá thì lấy giá
    # hiện tại của sản phẩm — về sau đổi products.price không ảnh hưởng đơn này.
    items: list[dict] = []
    for it in items_in:
        sp = catalog_repo.get_product(int(it["product_id"]))
        if not sp:
            raise ApiError("NOT_FOUND", f"Không tìm thấy sản phẩm #{it['product_id']}",
                           errors={"items": f"product_id {it['product_id']} không tồn tại"})
        gia = it.get("unit_price")
        if gia is None:
            gia = sp.get("price")
        if gia is None:
            raise ApiError("MISSING_REQUIRED_DATA",
                           f"Sản phẩm '{sp['name']}' chưa có giá — phải gửi unit_price",
                           errors={"items": "thiếu unit_price"})
        items.append({
            "product_id": sp["id"],
            "treatment_template_id": it.get("treatment_template_id"),
            # Decimal cả hai vế: quantity từ API là float, price từ DB là
            # Decimal — nhân thẳng float*Decimal là TypeError. Qua str để
            # không rước sai số nhị phân của float vào tiền.
            "quantity": Decimal(str(it["quantity"])),
            "unit_price": Decimal(str(gia)),
        })

    order_type = data.get("order_type") or phan_loai_don(int(customer_id))
    if order_type not in ORDER_TYPES:
        raise ApiError("VALIDATION_ERROR", f"Loại đơn lạ: {order_type}",
                       errors={"order_type": "new/repurchase/upsell/exchange"})

    don = {
        "customer_id": int(customer_id),
        "external_order_id": data.get("external_order_id") or None,
        "order_type": order_type,
        "sale_owner_id": data.get("sale_owner_id"),
        "cskh_owner_id": data.get("cskh_owner_id"),
        "status": status,
        "total_amount": sum(i["quantity"] * i["unit_price"] for i in items),
        "note": data.get("note"),
        "source": "crm",
        "_changed_by": _actor_id(actor),
    }
    try:
        row = order_repo.create_order(don, items)
    except UniqueViolation as err:
        raise ApiError("CONFLICT", "Mã đơn ngoài (external_order_id) đã tồn tại",
                       errors={"external_order_id": "đã tồn tại"}) from err
    except ForeignKeyViolation as err:
        raise ApiError("VALIDATION_ERROR", "Tham chiếu không hợp lệ (owner/template?)") from err

    _audit(actor, action="create", object_id=row["id"],
           new_value={"customer_id": row["customer_id"], "status": row["status"],
                      "order_type": row["order_type"],
                      "total_amount": str(row["total_amount"])})
    return get_detail(row["id"])


def update_order(order_id: int, data: dict, *, actor: dict | None = None) -> dict:
    """ORDER-004 — sửa thông tin phụ của đơn (KHÔNG đổi trạng thái ở đây)."""
    don = _lay(order_id)
    cho_phep = {"sale_owner_id", "cskh_owner_id", "note", "order_type"}
    gan = {k: v for k, v in data.items() if k in cho_phep and v is not None}
    if "order_type" in gan and gan["order_type"] not in ORDER_TYPES:
        raise ApiError("VALIDATION_ERROR", f"Loại đơn lạ: {gan['order_type']}",
                       errors={"order_type": "new/repurchase/upsell/exchange"})
    if not gan:
        raise ApiError("VALIDATION_ERROR", "Không có trường nào để sửa")
    try:
        order_repo.update_order(order_id, gan)
    except ForeignKeyViolation as err:
        raise ApiError("VALIDATION_ERROR", "Owner không tồn tại") from err
    _audit(actor, action="update", object_id=order_id,
           old_value={k: str(don.get(k)) for k in gan},
           new_value={k: str(v) for k, v in gan.items()})
    return get_detail(order_id)


# ------------------------------------------------------------------ trạng thái
def change_status(
    order_id: int,
    to_status: str,
    *,
    actor: dict | None = None,
    reason: str | None = None,
    force: bool = False,
    ban_giao: bool = True,
) -> dict:
    """ORDER-005 — chuyển trạng thái theo luật TRANSITIONS, ghi lịch sử.

    `force=True` chỉ dành cho đồng bộ POS: bỏ qua luật chuyển (thực tế bên POS
    là nguồn sự thật) nhưng LỊCH SỬ vẫn ghi đầy đủ — truy vết được mọi bước.
    `ban_giao=False` khi backfill lịch sử — không sinh phiếu bàn giao B8.
    """
    if to_status not in ORDER_STATUSES:
        raise ApiError("VALIDATION_ERROR", f"Trạng thái lạ: {to_status}",
                       errors={"to_status": "không thuộc 11 trạng thái chuẩn"})
    don = _lay(order_id)
    if don["status"] == to_status:
        raise ApiError("CONFLICT", f"Đơn đã ở trạng thái '{to_status}' rồi")
    if not force and to_status not in TRANSITIONS[don["status"]]:
        raise ApiError(
            "INVALID_STAGE_TRANSITION",
            f"Không chuyển được '{don['status']}' → '{to_status}'",
            errors={"to_status": f"từ '{don['status']}' chỉ sang: "
                                 f"{sorted(TRANSITIONS[don['status']]) or 'không đâu cả'}"},
        )
    row = order_repo.set_status(order_id, to_status,
                                changed_by=_actor_id(actor), reason=reason)
    _audit(actor, action="update_status", object_id=order_id,
           old_value={"status": don["status"]},
           new_value={"status": to_status}, reason=reason)

    # B8/FR-090: giao thành công -> tự sinh phiếu bàn giao + hồ sơ chăm.
    # Hook TỰ NUỐT lỗi (luồng bồi) và idempotent (uq_handovers_order) nên gọi
    # thoải mái cả từ chuyển tay lẫn đồng bộ POS (force=True).
    if ban_giao and to_status in ("delivered", "collected"):
        from app.services import handover_service

        handover_service.hook_giao_thanh_cong(order_id)
        # B10/FR-122: có đơn mới = "Đã mua" — cơ hội mua lại đang mở tự chốt
        # won + đánh dấu chuyển đổi chiến dịch tái kích hoạt (đo doanh thu).
        from app.services import repurchase_service

        repurchase_service.hook_don_giao_thanh_cong(don["customer_id"])
    return row


# ------------------------------------------------------------------ đọc
def get_detail(order_id: int) -> dict:
    """ORDER-002 — đơn + dòng hàng + toàn bộ lịch sử trạng thái."""
    don = _lay(order_id)
    don["items"] = order_repo.list_items(order_id)
    don["status_history"] = order_repo.list_history(order_id)
    return don


# ------------------------------------------------------------------ ánh xạ POS
def list_mappings() -> list[dict]:
    """ORDER-009 — bảng ánh xạ POS -> CRM (màn 23)."""
    return order_repo.list_mappings()


def update_mapping(pancake_status: int, data: dict, *, actor: dict | None = None) -> dict:
    """ORDER-010 — admin sửa 1 dòng ánh xạ; lượt đồng bộ sau ăn ngay."""
    crm_status = data.get("crm_status") or ""
    if crm_status not in ORDER_STATUSES:
        raise ApiError("VALIDATION_ERROR", f"Trạng thái CRM lạ: {crm_status}",
                       errors={"crm_status": "không thuộc 11 trạng thái chuẩn"})
    cu = next((m for m in order_repo.list_mappings()
               if m["pancake_status"] == pancake_status), None)
    row = order_repo.update_mapping(
        pancake_status, {"crm_status": crm_status, "note": data.get("note")},
        _actor_id(actor),
    )
    if row is None:
        raise ApiError("NOT_FOUND", f"Chưa có ánh xạ cho mã POS {pancake_status}")
    _audit(actor, action="update", object_id=row["id"],
           old_value={"pancake_status": pancake_status,
                      "crm_status": cu["crm_status"] if cu else None},
           new_value={"pancake_status": pancake_status, "crm_status": crm_status})
    return row
