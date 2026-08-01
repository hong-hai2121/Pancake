"""API Marketing & quảng cáo — ADS-002…006 · ADS-008 · ADS-010 ·
ATTRIBUTION-001/002 · FUNNEL-004 (BRD mục 4 phần nguồn quảng cáo, màn 7 + 53-56).

Route mỏng: luật + cách tính nằm ở services/ads_service.py và
db/repositories/ads_repo.py. Quyền:
    ads.view     — xem báo cáo quảng cáo (Marketing, Chủ DN, Admin)
    user.manage  — kéo đồng bộ tay (việc quản trị)
    customer.edit— gắn nguồn tay cho 1 khách (Sale làm khi khách gọi tới)

CHƯA làm ở đây (cần AI/tư vấn của giai đoạn sau, ghi rõ để khỏi tưởng bị bỏ sót):
    ADS-007 phiếu sức khỏe có NHẬN ĐỊNH AI  — phần số liệu đã có ở /ads/{id}/health-report,
                                              riêng câu kết luận AI thuộc C-MVP4/5
    ADS-009 băn khoăn khách theo quảng cáo   — cần bảng băn khoăn (màn 57), chưa có
"""

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_permission
from app.core.response import ok
from app.db.repositories import ads_repo
from app.schemas.ads import AttributionIn, SyncAdsIn
from app.services import ads_service

router = APIRouter(prefix="/api/v1", tags=["ads"])

_xem = Depends(require_permission("ads.view"))
_quan_tri = Depends(require_permission("user.manage"))
_sua_khach = Depends(require_permission("customer.edit"))


# ------------------------------------------------------------------ cây
@router.get("/ad-campaigns")
async def list_campaigns(
    tu: str = "", den: str = "", hieu_qua: bool = True,
    limit: int = Query(100, ge=1, le=500), _user: dict = _xem,
):
    """ADS-002 — chiến dịch. `hieu_qua=false` chỉ trả cây (tên, ngân sách, mục tiêu)."""
    if not hieu_qua:
        return ok({"items": ads_repo.list_campaigns(limit)})
    return ok({"items": ads_service.bao_cao("campaign", tu, den, limit)})


@router.get("/ad-sets")
async def list_ad_sets(
    campaign_id: int | None = None, tu: str = "", den: str = "",
    hieu_qua: bool = True, limit: int = Query(100, ge=1, le=500), _user: dict = _xem,
):
    """ADS-003 — nhóm quảng cáo (lọc theo chiến dịch khi xem cây)."""
    if not hieu_qua:
        return ok({"items": ads_repo.list_ad_sets(campaign_id, limit)})
    return ok({"items": ads_service.bao_cao("ad_set", tu, den, limit)})


@router.get("/ads")
async def list_ads(
    ad_set_id: int | None = None, tu: str = "", den: str = "",
    hieu_qua: bool = True, limit: int = Query(100, ge=1, le=500), _user: dict = _xem,
):
    """ADS-004 — quảng cáo kèm chi phí · khách · đơn · doanh thu · ROAS · LTV (màn 55)."""
    if not hieu_qua:
        return ok({"items": ads_repo.list_ads(ad_set_id, limit)})
    return ok({"items": ads_service.bao_cao("ad", tu, den, limit)})


@router.get("/ads/tong-quan")
async def tong_quan(tu: str = "", den: str = "", _user: dict = _xem):
    """Màn 7 — tổng chi phí/doanh thu/ROAS kỳ + cảnh báo ad chưa có chi phí."""
    if not (tu or den):
        tu, den = ads_service.ky_mac_dinh(30)
    return ok(ads_service.tong_quan(tu, den))


# ------------------------------------------------------------------ 1 quảng cáo
@router.get("/ads/{external_ad_id}/performance")
async def performance(
    external_ad_id: str, window: int = Query(30, ge=1, le=90), _user: dict = _xem
):
    """ADS-010 — ROAS và LTV theo cửa sổ (?window=7|30|60|90)."""
    return ok(ads_service.hieu_qua(external_ad_id, window))


@router.get("/ads/{external_ad_id}/funnel")
async def funnel(external_ad_id: str, _user: dict = _xem):
    """ADS-006 · FUNNEL-004 — phễu khách → lead → tư vấn → đơn → giao thành công."""
    return ok(ads_repo.phieu_theo_ad(external_ad_id))


@router.get("/ads/{external_ad_id}/lost-reasons")
async def lost_reasons(external_ad_id: str, _user: dict = _xem):
    """ADS-008 — lý do chưa chốt của khách đến từ quảng cáo này."""
    return ok({"items": ads_repo.ly_do_chua_chot_theo_ad(external_ad_id)})


@router.get("/ads/{external_ad_id}/health-report")
async def health_report(
    external_ad_id: str, window: int = Query(30, ge=1, le=90), _user: dict = _xem
):
    """ADS-007 (phần số liệu) — phiếu sức khỏe: phễu + hiệu quả + lý do + khách."""
    return ok(ads_service.chi_tiet_ad(external_ad_id, window))


@router.get("/ads/{external_ad_id}/customers")
async def khach_cua_ad(
    external_ad_id: str, limit: int = Query(50, ge=1, le=200), _user: dict = _xem
):
    """Danh sách khách minh chứng — mọi số trên báo cáo đều bấm ra được (FR-171)."""
    return ok({"items": ads_repo.khach_cua_ad(external_ad_id, limit)})


# ------------------------------------------------------------------ quy nguồn
@router.post("/customers/{customer_id}/attributions")
async def gan_nguon(customer_id: int, body: AttributionIn, user: dict = _sua_khach):
    """ATTRIBUTION-001 — gắn nguồn quảng cáo tay cho 1 khách."""
    return ok(
        ads_service.gan_nguon(customer_id, body.model_dump(exclude_none=True), actor=user),
        "Đã gắn nguồn",
    )


@router.get("/customers/{customer_id}/attributions")
async def nguon_khach(customer_id: int, _user: dict = _sua_khach):
    """ATTRIBUTION-002 — xem nguồn của khách (chạm đầu / chạm cuối)."""
    return ok({"items": ads_service.nguon_cua_khach(customer_id)})


# ------------------------------------------------------------------ đồng bộ
@router.post("/integrations/facebook-ads/sync")
async def sync_ads(body: SyncAdsIn, user: dict = _quan_tri):
    """ADS-005 — kéo tay cây quảng cáo + chi phí (nguồn: Pancake POS Ads Manager).

    Giữ đúng đường dẫn đặc tả đặt cho "đồng bộ chi phí"; khác đặc tả ở chỗ dữ liệu
    đi qua Pancake POS chứ không phải Facebook Ads API — cùng một cây, cùng số tiền,
    ít hơn một token phải giữ.
    """
    return ok(await ads_service.dong_bo_ngay(body.so_ngay, actor=user), "Đã đồng bộ")
