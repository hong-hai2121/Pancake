"""B7 — đổ đơn hàng Pancake POS vào CRM (FR-081/082).

Một đơn POS đi qua đây thành: khách (`crm.customers`, khớp chống trùng qua
customer_service như B2) + dòng `crm.orders` với trạng thái ĐÃ ÁNH XẠ theo bảng
`crm.order_status_mappings` (admin sửa được — đọc lại MỖI mẻ, sửa là ăn ngay).

Nguyên tắc như crm_sync: hàm ở đây KHÔNG ném lỗi lên worker — lỗi row nào ghi
stderr row đó. Idempotent theo (pos_shop_id, pos_order_id): chạy lại bao nhiêu
lần cũng không tạo trùng; POS chưa đổi gì (updated_at y nguyên) thì bỏ qua.

Phạm vi B7: đồng bộ ĐƠN + TRẠNG THÁI + tiền + phân loại đầu/mua lại. Dòng hàng
(order_items) CHƯA đồng bộ — sản phẩm POS chưa ánh xạ vào crm.products; nguyên
văn đơn nằm ở orders.pos_raw, sau này cần thì backfill từ đó.

Ánh xạ khớp khách (thứ tự trong customer_service.upsert_from_source):
    customer.fb_id            -> PSID  (bậc 2)
    bill_phone_number         -> SĐT   (bậc 3)
    page_id + conversation_id -> hội thoại (bậc 4 — trùng định dạng conv B2)
KHÔNG dùng customer.id của POS làm external_customer_id: đó là KHÔNG GIAN ID
KHÁC với UUID khách bên pages.fm mà B2 đang lưu — trộn vào là khớp nhầm.
"""

import sys
from datetime import datetime

from app.db.repositories import order_repo
from app.services import customer_service, order_service
from app.integrations.pancake.crm_sync import _crm_page_id

# Mã POS chưa có trong bảng ánh xạ (POS thêm trạng thái mới) -> nhận về 'draft'
# kèm reason đánh dấu, KHÔNG bỏ rơi đơn; admin bổ sung ánh xạ rồi đồng bộ lại.
_TRANG_THAI_MAC_DINH = "draft"


def _tien(don_pos: dict):
    """Tổng tiền đơn: ưu tiên giá sau giảm, lùi dần; không âm."""
    for khoa in ("total_price_after_sub_discount", "total_price", "money_to_collect"):
        v = don_pos.get(khoa)
        if v is not None:
            try:
                return max(float(v), 0)
            except (TypeError, ValueError):
                continue
    return 0


def _thoi_diem(chuoi) -> datetime | None:
    """Parse mốc thời gian POS ('2026-07-31T17:13:30.022951') — hỏng thì None."""
    if not chuoi:
        return None
    try:
        return datetime.fromisoformat(str(chuoi))
    except ValueError:
        return None


def _moc_giao_thanh_cong(don_pos: dict) -> datetime | None:
    """Mốc giao THẬT từ POS: dòng status_history có status=3 (Đã nhận).

    POS giữ nhật ký trạng thái riêng — lấy mốc thật thay vì now() lúc đồng bộ,
    vì delivered_at là mốc khởi tính liệu trình/lịch CSKH (lệch là lệch cả B8/B9).
    """
    for dong in don_pos.get("status_history") or []:
        if isinstance(dong, dict) and dong.get("status") == 3:
            return _thoi_diem(dong.get("updated_at") or dong.get("inserted_at"))
    return None


def sync_row(don_pos: dict, anh_xa: dict[int, str]) -> str:
    """Đồng bộ MỘT đơn POS. Trả 'tao_moi' | 'cap_nhat' | 'bo_qua'. Idempotent."""
    shop_id = int(don_pos["shop_id"])
    pos_order_id = int(don_pos["id"])
    pos_status = don_pos.get("status")
    crm_status = anh_xa.get(pos_status, _TRANG_THAI_MAC_DINH)
    ly_do = "pos_sync" if pos_status in anh_xa else \
        f"pos_sync: mã POS {pos_status} chưa có ánh xạ — tạm nhận 'draft'"

    don_cu = order_repo.find_by_pos(shop_id, pos_order_id)

    # ---------- đơn đã có: POS không đổi gì thì thôi, đổi thì cập nhật ----------
    if don_cu:
        raw_cu = don_cu.get("pos_raw") or {}
        if raw_cu.get("updated_at") == don_pos.get("updated_at") \
                and don_cu["status"] == crm_status:
            return "bo_qua"

        order_repo.update_order(don_cu["id"], {
            "total_amount": _tien(don_pos),
            "pos_status": pos_status,
            "pos_updated_at": _thoi_diem(don_pos.get("updated_at")),
            "pos_raw": don_pos,
        })
        if don_cu["status"] != crm_status:
            # force: POS là nguồn sự thật — không bắt đơn POS đi đúng đường
            # chuyển tay của CRM, nhưng lịch sử vẫn ghi đủ từng bước.
            order_service.change_status(don_cu["id"], crm_status,
                                        reason=ly_do, force=True)
            moc = _moc_giao_thanh_cong(don_pos)
            if moc and crm_status in ("delivered", "collected"):
                order_repo.set_delivered_at(don_cu["id"], moc)
        return "cap_nhat"

    # ---------- đơn mới: khớp/tạo khách rồi tạo đơn ----------
    kh_pos = don_pos.get("customer") or {}
    page_id_pos = str(don_pos.get("page_id") or "")
    conv_id = str(don_pos.get("conversation_id") or "")
    crm_page_id = _crm_page_id(page_id_pos, "") if page_id_pos else None

    kh, _vua_tao = customer_service.upsert_from_source(
        platform="facebook",
        name=don_pos.get("bill_full_name"),
        phone=don_pos.get("bill_phone_number"),
        psid=str(kh_pos.get("fb_id") or "") or None,
        page_id=crm_page_id,
        external_conversation_id=conv_id or None,
        source="pancake_pos",
        # KHÔNG sinh lead: người ĐÃ mua không phải lead mới — backfill 53k đơn
        # mà bật cờ này là ngập hàng đợi chia lead của Sale (FR-030).
        create_lead=False,
    )

    pos_inserted_at = _thoi_diem(don_pos.get("inserted_at"))
    moc_giao = _moc_giao_thanh_cong(don_pos)
    don = {
        "customer_id": kh["id"],
        "external_order_id": f"pos:{shop_id}:{pos_order_id}",
        # FR-082: so theo THỜI ĐIỂM TẠO bên POS — backfill trả đơn mới trước,
        # so theo thứ tự chèn DB sẽ dán nhãn ngược (xem count_prior_orders).
        "order_type": order_service.phan_loai_don(
            kh["id"], truoc_thoi_diem=pos_inserted_at),
        "status": crm_status,
        "total_amount": _tien(don_pos),
        "delivered_at": moc_giao if crm_status in ("delivered", "collected") else None,
        "source": "pancake_pos",
        "pos_shop_id": shop_id,
        "pos_order_id": pos_order_id,
        "pos_status": pos_status,
        "pos_conversation_id": conv_id or None,
        "pos_page_id": page_id_pos or None,
        "pos_inserted_at": pos_inserted_at,
        "pos_updated_at": _thoi_diem(don_pos.get("updated_at")),
        "pos_raw": don_pos,
        "_reason": ly_do,
    }
    order_repo.create_order(don, [])
    return "tao_moi"


def sync_batch(dons: list[dict]) -> dict:
    """Đồng bộ một mẻ đơn POS. Nuốt lỗi từng row — không vỡ worker/backfill.

    Bảng ánh xạ đọc MỘT lần cho cả mẻ (đủ tươi: worker chạy lại mỗi vài phút).
    """
    anh_xa = order_repo.load_mapping_dict()
    ket_qua = {"tao_moi": 0, "cap_nhat": 0, "bo_qua": 0, "loi": 0}
    for don_pos in dons:
        try:
            ket_qua[sync_row(don_pos, anh_xa)] += 1
        except Exception as err:  # noqa: BLE001 — xem docstring
            ket_qua["loi"] += 1
            print(
                f"[pos_sync] loi don {don_pos.get('id')}: {type(err).__name__}: {err}",
                file=sys.stderr,
            )
    return ket_qua
