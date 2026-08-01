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
from datetime import datetime, timezone

from app.db.repositories import attribution_repo, integration_repo, order_repo
from app.services import customer_service, integration_service, order_service
from app.integrations.pancake.crm_sync import _crm_page_id

_PROVIDER = "pancake_pos"

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


def _pos_order_id(don_pos: dict) -> int:
    """Khoá đơn phía POS. Dùng `system_id`, KHÔNG dùng `id`.

    1.535/53.642 đơn (toàn bộ đơn trước ~06/2025, nhập từ hệ thống cũ) có
    `id` dạng chuỗi 'C430270742.88' — `int()` thẳng là vỡ, backfill mất sạch
    đơn cũ. Đã đối chiếu cả 53.642 đơn của shop (01/08):
      * đơn nào cũng có `system_id` kiểu số;
      * `id` là số thì LUÔN bằng `system_id` (0 đơn lệch) — đơn đã đồng bộ
        trước đây giữ nguyên khoá, không bị nhân đôi;
      * `system_id` của nhóm id-chuỗi KHÔNG đụng `id` của nhóm id-số (0 va chạm).
    """
    for khoa in ("system_id", "id"):
        v = don_pos.get(khoa)
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    raise ValueError(
        f"Đơn POS không có system_id/id dạng số: id={don_pos.get('id')!r}")


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


def _quy_nguon(customer_id: int, don_pos: dict) -> None:
    """Ghi nguồn quảng cáo của đơn (BRD mục 4: ad_id, creative, first/last touch).

    Pancake trả `ad_id` + `post_id` + `p_utm_*` ngay trên đơn. Chạm ĐẦU lấy mốc
    tạo đơn sớm nhất, chạm CUỐI lấy mốc muộn nhất — repo tự so mốc nên thứ tự
    backfill (mới → cũ) không làm sai nhãn.
    """
    ad_ngoai = str(don_pos.get("ad_id") or "").strip()
    post_id = str(don_pos.get("post_id") or "").strip()
    if not (ad_ngoai or post_id):
        return
    moc = _thoi_diem(don_pos.get("inserted_at"))
    utm = {
        k[6:]: don_pos.get(k) for k in
        ("p_utm_source", "p_utm_medium", "p_utm_campaign",
         "p_utm_content", "p_utm_term", "p_utm_id")
        if don_pos.get(k)
    }
    if don_pos.get("ads_source"):
        utm["ads_source"] = don_pos["ads_source"]

    ad = attribution_repo.upsert_ad(
        external_ad_id=ad_ngoai, platform="facebook", post_id=post_id)
    for loai in ("first", "last"):
        attribution_repo.ghi_cham(
            customer_id=customer_id, touch_type=loai, attributed_at=moc,
            ad_id=(ad or {}).get("id"), external_ad_id=ad_ngoai, post_id=post_id,
            source=_PROVIDER, utm=utm,
        )


def _nhan_vien_pos(don_pos: dict) -> None:
    """Ghi nhận nhân viên POS (bán / chăm / marketer) vào bảng ánh xạ.

    Chỉ GHI NHẬN để Admin gán ở màn Ánh xạ — KHÔNG tự phân công khách trong CRM:
    ownership của CRM có luật riêng (FR-030…032, B1/B3), máy đồng bộ không được
    tự ý đè lên.
    """
    for khoa, vai in (("assigning_seller_id", "seller"),
                      ("assigning_care_id", "care"),
                      ("marketer_id", "marketer")):
        ngoai = str(don_pos.get(khoa) or "").strip()
        if not ngoai:
            continue
        try:
            integration_repo.upsert_staff(
                provider=_PROVIDER, external_staff_id=ngoai, role_hint=vai)
        except Exception:  # noqa: BLE001 — phụ trợ, không được chặn đồng bộ đơn
            pass


def sync_row(don_pos: dict, anh_xa: dict[int, str],
             *, hook_ban_giao: bool = True) -> str:
    """Đồng bộ MỘT đơn POS. Trả 'tao_moi' | 'cap_nhat' | 'bo_qua'. Idempotent.

    `hook_ban_giao=False` khi BACKFILL lịch sử: đơn giao từ đời nào rồi mà vẫn
    sinh phiếu bàn giao + việc onboarding thì CSKH ngập 53k việc ảo (FR-090
    chỉ dành cho đơn giao MỚI)."""
    shop_id = int(don_pos["shop_id"])
    pos_order_id = _pos_order_id(don_pos)
    pos_status = don_pos.get("status")
    crm_status = anh_xa.get(pos_status, _TRANG_THAI_MAC_DINH)
    ly_do = "pos_sync" if pos_status in anh_xa else \
        f"pos_sync: mã POS {pos_status} chưa có ánh xạ — tạm nhận 'draft'"

    don_cu = order_repo.find_by_pos(shop_id, pos_order_id)
    _nhan_vien_pos(don_pos)

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
            "synced_at": datetime.now(timezone.utc),
        })
        if don_cu["status"] != crm_status:
            # Mốc giao đóng dấu TRƯỚC change_status: hook bàn giao B8 chạy
            # trong change_status cần delivered_at để tính ngày dự kiến bắt đầu.
            moc = _moc_giao_thanh_cong(don_pos)
            if moc and crm_status in ("delivered", "collected"):
                order_repo.set_delivered_at(don_cu["id"], moc)
            # force: POS là nguồn sự thật — không bắt đơn POS đi đúng đường
            # chuyển tay của CRM, nhưng lịch sử vẫn ghi đủ từng bước.
            order_service.change_status(don_cu["id"], crm_status,
                                        reason=ly_do, force=True,
                                        ban_giao=hook_ban_giao)
        _quy_nguon(don_cu["customer_id"], don_pos)
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
        "synced_at": datetime.now(timezone.utc),
        "_reason": ly_do,
    }
    don_moi = order_repo.create_order(don, [])
    _quy_nguon(kh["id"], don_pos)
    # Đơn về CRM khi ĐÃ giao xong (poll thưa/webhook trễ) không đi qua
    # change_status -> gọi hook bàn giao B8 trực tiếp (tự nuốt lỗi, idempotent).
    if hook_ban_giao and crm_status in ("delivered", "collected"):
        from app.services import handover_service

        handover_service.hook_giao_thanh_cong(don_moi["id"])
    return "tao_moi"


def sync_batch(dons: list[dict], *, run_type: str = "poll") -> dict:
    """Đồng bộ một mẻ đơn POS. Nuốt lỗi từng row — không vỡ worker/backfill.

    Bảng ánh xạ đọc MỘT lần cho cả mẻ (đủ tươi: worker chạy lại mỗi vài phút).
    Mẻ nào cũng ghi 1 dòng `crm.sync_logs`; đơn hỏng vào `crm.sync_errors` kèm
    nguyên văn đơn để worker retry chạy lại mà không phải gọi lại POS (mục 4).
    """
    anh_xa = order_repo.load_mapping_dict()
    ket_qua = {"tao_moi": 0, "cap_nhat": 0, "bo_qua": 0, "loi": 0}
    shop = str((dons[0].get("shop_id") if dons else "") or "")
    # Backfill lịch sử KHÔNG sinh phiếu bàn giao/việc (xem sync_row)
    hook_ban_giao = run_type != "backfill"

    log_id = None
    try:
        log_id = integration_service.mo_log(
            _PROVIDER, "order", scope=shop, run_type=run_type)
    except Exception as err:  # noqa: BLE001 — không có nhật ký vẫn phải đồng bộ
        print(f"[pos_sync] không mở được nhật ký: {err}", file=sys.stderr)

    for don_pos in dons:
        try:
            ket_qua[sync_row(don_pos, anh_xa,
                             hook_ban_giao=hook_ban_giao)] += 1
        except Exception as err:  # noqa: BLE001 — xem docstring
            ket_qua["loi"] += 1
            print(
                f"[pos_sync] loi don {don_pos.get('id')}: {type(err).__name__}: {err}",
                file=sys.stderr,
            )
            integration_service.ghi_loi(
                _PROVIDER, "order", str(don_pos.get("id") or ""), err,
                payload=don_pos, scope=shop, sync_log_id=log_id,
            )

    if log_id:
        try:
            integration_service.dong_log(log_id, ket_qua)
        except Exception as err:  # noqa: BLE001
            print(f"[pos_sync] không đóng được nhật ký: {err}", file=sys.stderr)
    return ket_qua
