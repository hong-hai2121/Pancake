"""Đổ CÂY QUẢNG CÁO + CHI PHÍ từ Pancake POS Ads Manager về CRM (BRD mục 4).

Vì sao đi đường Pancake mà không phải Facebook Ads API: POS đã nối sẵn tài khoản
quảng cáo và trả kèm `insights` (spend/impressions/clicks/reach) cho từng
campaign · adset · ad. Một api_key đang có là đủ — không phải xin thêm app FB,
không phải giữ thêm một token nữa.

Hai việc tách bạch:

  `dong_bo_cay()`     — ai là ai: campaign → adset → ad → creative. Chạy thưa
                        (ngày 1 lần) vì cấu trúc ít đổi.
  `dong_bo_chi_phi()` — số tiền của MỘT NGÀY. API trả số đã TỔNG HỢP theo khoảng
                        thời gian truyền vào, nên muốn dựng lại được mọi cửa sổ
                        (7/30/60/90 ngày của ADS-010) thì phải hỏi từng ngày và
                        lưu hạt ngày. Chạy lại cùng ngày = ghi đè, không cộng dồn.

⚠️ CHỈ ad thuộc tài khoản quảng cáo ĐÃ NỐI vào POS mới có chi phí. Ad thấy trên
đơn mà chưa nối tài khoản vẫn được giữ (biết doanh thu, chưa biết chi phí) —
xem `thong_ke_thieu_chi_phi()` để biết còn bao nhiêu ad như vậy.

Như mọi module đồng bộ khác: KHÔNG ném lỗi lên worker; lỗi từng dòng vào hàng
đợi retry (`crm.sync_errors`), mỗi lượt ghi 1 dòng `crm.sync_logs`.
"""

import sys
from datetime import date, datetime, time, timedelta

from app.db.repositories import ads_repo, integration_repo
from app.services import integration_service

_PROVIDER = "pancake_pos"

# Facebook trả cả chục trạng thái (ACTIVE, PAUSED, CAMPAIGN_PAUSED, ADSET_PAUSED,
# IN_PROCESS, WITH_ISSUES, PENDING_REVIEW…) — quy về 5 nhóm cho CHECK của DB,
# bản gốc vẫn giữ nguyên ở cột effective_status.
_TRANG_THAI = {
    "ACTIVE": "active", "PAUSED": "paused", "CAMPAIGN_PAUSED": "paused",
    "ADSET_PAUSED": "paused", "ARCHIVED": "archived", "DELETED": "deleted",
}


def _trang_thai(v) -> str | None:
    if not v:
        return None
    return _TRANG_THAI.get(str(v).upper(), "other")


def _tg(chuoi) -> datetime | None:
    """'2026-07-20T16:25:48' -> datetime; rác thì None (không làm vỡ cả mẻ)."""
    if not chuoi:
        return None
    try:
        return datetime.fromisoformat(str(chuoi).replace("Z", "+00:00"))
    except ValueError:
        return None


def _so(v):
    """Số từ insights: API có lúc trả chuỗi, có lúc null."""
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _moc_ngay(ngay: date) -> tuple[int, int]:
    """(start_time, end_time) unix giây bao trọn MỘT ngày theo giờ máy chủ."""
    return (
        int(datetime.combine(ngay, time.min).timestamp()),
        int(datetime.combine(ngay, time.max).timestamp()),
    )


# ------------------------------------------------------------------ cây
def _luu_ad(ad: dict) -> dict | None:
    """Lưu 1 ad KÈM adset/campaign đi cùng nó (ads_v2 trả sẵn cả cây)."""
    tk = ad.get("ad_account") or {}
    chien_dich = ad.get("ad_campaign") or {}
    nhom = ad.get("ad_set") or {}
    creative = ad.get("ad_creative") or {}

    cd = ads_repo.upsert_campaign({
        "external_campaign_id": chien_dich.get("id"),
        "name": chien_dich.get("name"),
        "platform": "facebook",
        "external_account_id": tk.get("id"),
        "account_name": tk.get("name"),
        "currency": tk.get("currency"),
        "daily_budget": chien_dich.get("daily_budget"),
        "lifetime_budget": chien_dich.get("lifetime_budget"),
    }) if chien_dich.get("id") else None

    ns = ads_repo.upsert_ad_set({
        "external_adset_id": nhom.get("id"),
        "campaign_id": (cd or {}).get("id"),
        "name": nhom.get("name"),
        "daily_budget": nhom.get("daily_budget"),
        "lifetime_budget": nhom.get("lifetime_budget"),
    }) if nhom.get("id") else None

    # object_story_id = "<page_id>_<post_id>" — cắt lấy post_id để khớp với
    # `post_id` mà đơn POS mang theo (cùng một bài viết).
    story = str(creative.get("object_story_id") or "")
    post_id = story.split("_", 1)[1] if "_" in story else ""

    return ads_repo.upsert_ad({
        "external_ad_id": ad.get("id"),
        "ad_set_id": (ns or {}).get("id"),
        "name": ad.get("name"),
        "status": _trang_thai(ad.get("status")),
        "effective_status": ad.get("effective_status"),
        "creative_id": creative.get("id"),
        "creative_name": (creative.get("name") or "")[:500] or None,
        "object_story_id": story or None,
        "post_id": post_id or None,
        "platform": "facebook",
        "external_account_id": tk.get("id"),
        "created_time": _tg(ad.get("created_time")),
    })


async def dong_bo_cay(*, so_ngay: int = 90, shop_id: str | int | None = None) -> dict:
    """Kéo campaign · adset · ad của `so_ngay` gần nhất về CRM. Idempotent.

    Đi 3 lời gọi: ads_v2 (dựng cả cây trong một lượt) rồi campaigns_v2 /
    ad_sets_v2 để bồi tên, mục tiêu, ngân sách cho những dòng chưa có ad nào chạy.
    """
    from app.integrations.pancake_pos import client

    den = date.today()
    tu = den - timedelta(days=so_ngay)
    st, _ = _moc_ngay(tu)
    _, en = _moc_ngay(den)

    ket_qua = {"tao_moi": 0, "cap_nhat": 0, "bo_qua": 0, "loi": 0, "noi_attribution": 0}
    log_id = None
    try:
        log_id = integration_service.mo_log(
            _PROVIDER, "ad", scope=str(shop_id or ""), run_type="poll")
    except Exception as err:  # noqa: BLE001
        print(f"[ads_sync] không mở được nhật ký: {err}", file=sys.stderr)

    ads = await client.list_ads(shop_id=shop_id, start_time=st, end_time=en)
    for ad in ads:
        try:
            _luu_ad(ad)
            ket_qua["cap_nhat"] += 1
        except Exception as err:  # noqa: BLE001 — 1 ad hỏng không làm vỡ cả mẻ
            ket_qua["loi"] += 1
            print(f"[ads_sync] loi ad {ad.get('id')}: {type(err).__name__}: {err}",
                  file=sys.stderr)
            integration_service.ghi_loi(
                _PROVIDER, "ad", str(ad.get("id") or ""), err,
                payload=ad, scope=str(shop_id or ""), sync_log_id=log_id)

    for cd in await client.list_ad_campaigns(shop_id=shop_id, start_time=st, end_time=en):
        try:
            tk = cd.get("ad_account") or {}
            ads_repo.upsert_campaign({
                "external_campaign_id": cd.get("id"), "name": cd.get("name"),
                "platform": "facebook", "status": _trang_thai(cd.get("status")),
                "effective_status": cd.get("effective_status"),
                "objective": cd.get("objective"),
                "external_account_id": tk.get("id"), "account_name": tk.get("name"),
                "currency": tk.get("currency"),
                "daily_budget": cd.get("daily_budget"),
                "lifetime_budget": cd.get("lifetime_budget"),
                "start_time": _tg(cd.get("start_time")),
                "end_time": _tg(cd.get("end_time")),
            })
        except Exception as err:  # noqa: BLE001
            ket_qua["loi"] += 1
            print(f"[ads_sync] loi campaign {cd.get('id')}: {err}", file=sys.stderr)

    for ns in await client.list_ad_sets(shop_id=shop_id, start_time=st, end_time=en):
        try:
            ads_repo.upsert_ad_set({
                "external_adset_id": ns.get("id"), "name": ns.get("name"),
                "status": _trang_thai(ns.get("status")),
                "effective_status": ns.get("effective_status"),
                "optimization_goal": ns.get("optimization_goal"),
                "destination_type": ns.get("destination_type"),
                "daily_budget": ns.get("daily_budget"),
                "lifetime_budget": ns.get("lifetime_budget"),
                "start_time": _tg(ns.get("start_time")),
                "end_time": _tg(ns.get("end_time")),
                "targeting": ns.get("targeting"),
            })
        except Exception as err:  # noqa: BLE001
            ket_qua["loi"] += 1
            print(f"[ads_sync] loi adset {ns.get('id')}: {err}", file=sys.stderr)

    # Đơn về trước, cây về sau (hoặc ngược lại) — nối lại cho khớp.
    ket_qua["noi_attribution"] = ads_repo.noi_attribution_vao_ads()

    if log_id:
        try:
            integration_service.dong_log(
                log_id, ket_qua,
                f"cây quảng cáo {so_ngay} ngày: {len(ads)} ad")
        except Exception as err:  # noqa: BLE001
            print(f"[ads_sync] không đóng được nhật ký: {err}", file=sys.stderr)
    return ket_qua


# ------------------------------------------------------------------ chi phí
def _dong_chi_phi(cap: str, row: dict, ngay: date, id_crm: int | None) -> dict | None:
    """Một dòng ad_metrics_daily từ `insights` của POS."""
    ins = row.get("insights") or {}
    if id_crm is None or not row.get("id"):
        return None
    tien = _so(ins.get("spend"))
    # Không có chi tiêu và không có hiển thị -> ngày đó ad không chạy, khỏi ghi
    # dòng rỗng (bảng này mỗi ad mỗi ngày một dòng, phình rất nhanh).
    if not tien and not _so(ins.get("impressions")):
        return None
    return {
        "entity_type": cap, "entity_id": id_crm, "external_id": str(row["id"]),
        "ngay": ngay, "spend": tien or 0,
        "impressions": int(_so(ins.get("impressions")) or 0),
        "clicks": int(_so(ins.get("clicks")) or 0),
        "reach": int(_so(ins.get("reach")) or 0),
        "cpc": _so(ins.get("cpc")), "cpm": _so(ins.get("cpm")),
        "ctr": _so(ins.get("ctr")), "frequency": _so(ins.get("frequency")),
        "currency": (row.get("ad_account") or {}).get("currency"),
    }


async def dong_bo_chi_phi(ngay: date, *, shop_id: str | int | None = None) -> dict:
    """Chi phí + chỉ số của MỘT ngày cho cả 3 cấp. Chạy lại = ghi đè (idempotent)."""
    from app.integrations.pancake_pos import client

    st, en = _moc_ngay(ngay)
    ket_qua = {"tao_moi": 0, "cap_nhat": 0, "bo_qua": 0, "loi": 0}
    log_id = None
    try:
        log_id = integration_service.mo_log(
            _PROVIDER, "ad", scope=str(ngay), run_type="poll")
    except Exception as err:  # noqa: BLE001
        print(f"[ads_sync] không mở được nhật ký: {err}", file=sys.stderr)

    rows: list[dict] = []
    try:
        # Tra id CRM một lần cho cả mẻ thay vì mỗi dòng một câu SELECT.
        ban_do = _ban_do_id()
        for cap, lay, khoa in (
            ("campaign", client.list_ad_campaigns, "campaign"),
            ("ad_set", client.list_ad_sets, "ad_set"),
            ("ad", client.list_ads, "ad"),
        ):
            for row in await lay(shop_id=shop_id, start_time=st, end_time=en):
                dong = _dong_chi_phi(cap, row, ngay, ban_do[khoa].get(str(row.get("id"))))
                if dong:
                    rows.append(dong)
                else:
                    ket_qua["bo_qua"] += 1
        ket_qua["cap_nhat"] = ads_repo.upsert_metrics(rows)
    except Exception as err:  # noqa: BLE001 — hỏng cả ngày thì xếp hàng chạy lại
        ket_qua["loi"] += 1
        print(f"[ads_sync] loi chi phi {ngay}: {type(err).__name__}: {err}",
              file=sys.stderr)
        integration_service.ghi_loi(
            _PROVIDER, "ad", f"chi-phi-{ngay}", err,
            payload={"ngay": str(ngay)}, scope=str(ngay), sync_log_id=log_id)

    if log_id:
        try:
            integration_service.dong_log(log_id, ket_qua, f"chi phí ngày {ngay}")
        except Exception as err:  # noqa: BLE001
            print(f"[ads_sync] không đóng được nhật ký: {err}", file=sys.stderr)
    return ket_qua


def _ban_do_id() -> dict[str, dict[str, int]]:
    """{cấp: {external_id: id CRM}} — dựng 1 lần cho mỗi mẻ chi phí."""
    from app.db.client import get_pg_pool

    pool = get_pg_pool()
    with pool.connection() as conn:
        cd = conn.execute(
            "select id, external_campaign_id x from crm.ad_campaigns").fetchall()
        ns = conn.execute(
            "select id, external_adset_id x from crm.ad_sets"
            " where external_adset_id is not null").fetchall()
        ad = conn.execute("select id, external_ad_id x from crm.ads").fetchall()
    return {
        "campaign": {r["x"]: r["id"] for r in cd},
        "ad_set": {r["x"]: r["id"] for r in ns},
        "ad": {r["x"]: r["id"] for r in ad},
    }


def thong_ke_thieu_chi_phi() -> dict:
    """Bao nhiêu quảng cáo đang có doanh thu mà CHƯA có chi phí (chưa nối tài khoản).

    Con số này là lời nhắc vận hành quan trọng: ROAS chỉ đúng trên phần ad đã nối
    tài khoản quảng cáo vào POS.
    """
    from app.db.client import get_pg_pool

    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select count(distinct la.external_ad_id) as ad_co_doanh_thu,
                   count(distinct la.external_ad_id) filter (
                       where exists (select 1 from crm.ad_metrics_daily m
                                      where m.entity_type = 'ad'
                                        and m.external_id = la.external_ad_id)
                   ) as ad_co_chi_phi
              from crm.lead_attributions la
             where la.external_ad_id is not null
            """
        ).fetchone()
