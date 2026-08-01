"""Luật + tổng hợp báo cáo NGUỒN QUẢNG CÁO (BRD mục 4 · màn 7, 53-56, 62).

Nguyên tắc đo của BRD mục 1: *"đo quảng cáo bằng doanh thu thật"* — nên mọi con
số ở đây đi từ đơn ĐÃ GIAO THÀNH CÔNG (`delivered`/`collected`) của khách được
quy nguồn, không phải từ số inbox hay số đơn tạo.

Cách nối hai vế:
    chi phí  <- crm.ad_metrics_daily (Pancake POS Ads Manager, hạt NGÀY)
    doanh thu <- crm.lead_attributions (chạm CUỐI) -> crm.orders
    khớp nhau bằng `external_ad_id` (id quảng cáo Facebook trên đơn Pancake)

Cảnh báo vận hành quan trọng (trả kèm trong `tong_quan`): ad nào thuộc tài khoản
quảng cáo CHƯA nối vào POS thì không có chi phí -> ROAS của ad đó là rỗng chứ
KHÔNG phải 0. Trộn hai thứ đó vào nhau là báo cáo nói dối.

KHÔNG import FastAPI (quy ước services/).
"""

from datetime import date, timedelta

from app.core.errors import ApiError
from app.db.repositories import ads_repo, attribution_repo, audit_repo, customer_repo

CAP = {"campaign": ads_repo.bao_cao_campaign,
       "ad_set": ads_repo.bao_cao_ad_set,
       "ad": ads_repo.bao_cao_ad}


def _actor_id(actor: dict | None) -> int | None:
    return int(actor["sub"]) if actor else None


def ky_mac_dinh(so_ngay: int = 30) -> tuple[str, str]:
    """Kỳ mặc định của màn báo cáo: N ngày gần nhất (kể cả hôm nay)."""
    den = date.today()
    return (den - timedelta(days=so_ngay - 1)).isoformat(), den.isoformat()


def bao_cao(cap: str = "ad", tu: str = "", den: str = "", limit: int = 100) -> list[dict]:
    """Bảng hiệu quả theo cấp (campaign · ad_set · ad) — màn 53/54/55."""
    if cap not in CAP:
        raise ApiError("VALIDATION_ERROR",
                       f"Cấp lạ: {cap} (campaign | ad_set | ad)")
    return CAP[cap](tu, den, limit)


def tong_quan(tu: str = "", den: str = "") -> dict:
    """Màn 7 — khối số tổng + cảnh báo phần chưa có chi phí."""
    from app.integrations.pancake_pos.ads_sync import thong_ke_thieu_chi_phi

    tong = dict(ads_repo.tong_hop(tu, den))
    thieu = thong_ke_thieu_chi_phi()
    chi_phi = float(tong.get("chi_phi") or 0)
    doanh_thu = float(tong.get("doanh_thu") or 0)
    tong["roas"] = round(doanh_thu / chi_phi, 2) if chi_phi else None
    tong["ltv"] = round(doanh_thu / tong["so_khach"], 0) if tong.get("so_khach") else None
    tong["ad_co_doanh_thu"] = thieu["ad_co_doanh_thu"]
    tong["ad_co_chi_phi"] = thieu["ad_co_chi_phi"]
    tong["ad_thieu_chi_phi"] = thieu["ad_co_doanh_thu"] - thieu["ad_co_chi_phi"]
    tong["chi_phi_theo_ngay"] = ads_repo.chi_phi_theo_ngay(tu, den)
    # Vế doanh thu trống thì phải nói RÕ VÌ SAO: có chi phí mà không có đơn nào đổ
    # về CRM là do công tắc đồng bộ đơn, không phải quảng cáo bán được 0 đồng.
    from app.core import runtime_config

    tong["pos_sync_enabled"] = runtime_config.bat("pos_sync_enabled")
    tong["thieu_don_pos"] = bool(chi_phi) and not tong.get("so_khach")
    return tong


def chi_tiet_ad(external_ad_id: str, window: int = 30) -> dict:
    """Màn 56 (phiếu sức khỏe quảng cáo) — phễu + hiệu quả + lý do chưa chốt + khách."""
    ad = ads_repo.find_ad(external_ad_id)
    hieu_qua = ads_repo.hieu_qua_ad(external_ad_id, window)
    if not ad and not (hieu_qua or {}).get("so_khach"):
        raise ApiError("NOT_FOUND", f"Chưa thấy quảng cáo {external_ad_id} trong CRM")
    return {
        "ad": ad,
        "hieu_qua": hieu_qua,
        "phieu": ads_repo.phieu_theo_ad(external_ad_id),
        "ly_do_chua_chot": ads_repo.ly_do_chua_chot_theo_ad(external_ad_id),
        "khach": ads_repo.khach_cua_ad(external_ad_id, 50),
    }


def hieu_qua(external_ad_id: str, window: int = 30) -> dict:
    """ADS-010 — ROAS/LTV theo cửa sổ 7/30/60/90 ngày."""
    if window not in ads_repo.WINDOWS:
        raise ApiError("VALIDATION_ERROR",
                       f"window chỉ nhận {', '.join(map(str, ads_repo.WINDOWS))}")
    return ads_repo.hieu_qua_ad(external_ad_id, window)


# ------------------------------------------------------------ ATTRIBUTION-001
def gan_nguon(customer_id: int, du_lieu: dict, actor: dict | None = None) -> dict:
    """ATTRIBUTION-001 — gắn nguồn quảng cáo TAY cho 1 khách (khách gọi điện tới,
    Sale biết khách xem quảng cáo nào mà đơn không mang ad_id).

    Vẫn đi qua đúng đường của máy đồng bộ (`attribution_repo.ghi_cham`) nên luật
    "chạm đầu không bị đè, chạm cuối lấy mốc muộn nhất" giữ nguyên.
    """
    if not customer_repo.get_customer(customer_id):
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    ad_ngoai = str(du_lieu.get("external_ad_id") or "").strip()
    post_id = str(du_lieu.get("post_id") or "").strip()
    if not (ad_ngoai or post_id):
        raise ApiError("VALIDATION_ERROR",
                       "Phải có external_ad_id hoặc post_id để gắn nguồn")
    loai = du_lieu.get("touch_type") or "last"
    if loai not in ("first", "last"):
        raise ApiError("VALIDATION_ERROR", "touch_type chỉ nhận first | last")

    ad = attribution_repo.upsert_ad(external_ad_id=ad_ngoai, post_id=post_id) \
        if ad_ngoai else None
    dong = attribution_repo.ghi_cham(
        customer_id=customer_id, touch_type=loai,
        attributed_at=du_lieu.get("attributed_at") or None,
        ad_id=(ad or {}).get("id"), external_ad_id=ad_ngoai, post_id=post_id,
        source=du_lieu.get("source") or "tay", utm=du_lieu.get("utm") or {},
        lead_id=du_lieu.get("lead_id"),
    )
    audit_repo.ghi(
        user_id=_actor_id(actor), object_type="lead_attributions",
        object_id=(dong or {}).get("id"), action="attribution_set",
        new_value={"customer_id": customer_id, "external_ad_id": ad_ngoai,
                   "touch_type": loai},
    )
    # `ghi_cham` trả None khi giữ lại chạm cũ (mốc cũ hơn) — nói rõ ra cho người gọi.
    return dong or {"giu_nguyen": True,
                    "message": "Đã có chạm phù hợp hơn — giữ nguyên bản cũ"}


def nguon_cua_khach(customer_id: int) -> list[dict]:
    """ATTRIBUTION-002 — xem nguồn của 1 khách (tab Nguồn Ads, màn 8)."""
    if not customer_repo.get_customer(customer_id):
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    return attribution_repo.cham_cua_khach(customer_id)


# ------------------------------------------------------------ đồng bộ tay
async def dong_bo_ngay(so_ngay: int = 7, actor: dict | None = None) -> dict:
    """ADS-005 — kéo tay cây quảng cáo + chi phí `so_ngay` ngày gần nhất.

    Dành cho quản trị (vừa nối thêm tài khoản quảng cáo, muốn thấy số ngay).
    Lịch sử dài hơn: scripts/backfill_quang_cao.py.
    """
    from app.core.config import settings
    from app.integrations.pancake_pos import ads_sync
    from app.integrations.pancake_pos.client import PancakePosError

    if not (settings.pancake_pos_api_key and settings.pancake_pos_shop_id):
        raise ApiError("VALIDATION_ERROR",
                       "Chưa cấu hình PANCAKE_POS_API_KEY / PANCAKE_POS_SHOP_ID trong .env")
    try:
        cay = await ads_sync.dong_bo_cay(so_ngay=max(so_ngay, 30))
        chi_phi = {"cap_nhat": 0, "loi": 0}
        for i in range(so_ngay):
            kq = await ads_sync.dong_bo_chi_phi(date.today() - timedelta(days=i))
            chi_phi["cap_nhat"] += kq["cap_nhat"]
            chi_phi["loi"] += kq["loi"]
    except PancakePosError as err:
        raise ApiError("INTEGRATION_ERROR", f"Pancake POS lỗi: {err}") from err

    audit_repo.ghi(user_id=_actor_id(actor), object_type="ads",
                   action="ads_sync", new_value={"so_ngay": so_ngay})
    return {"cay": cay, "chi_phi": chi_phi}
