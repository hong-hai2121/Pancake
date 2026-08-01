"""Truy vấn cây quảng cáo + chi phí + báo cáo hiệu quả (BRD mục 4 — nguồn quảng cáo).

Ba nhóm:
  * upsert cây  : ad_campaigns / ad_sets / ads (từ Pancake POS Ads Manager)
  * chi phí     : ad_metrics_daily (theo NGÀY — cộng ra được mọi cửa sổ)
  * báo cáo     : ghép chi phí với dữ liệu CRM (khách quy nguồn, lead, đơn,
                  giao thành công, doanh thu) -> ROAS · LTV · tỷ lệ chốt

Nối chi phí ↔ doanh thu bằng `crm.lead_attributions.external_ad_id` (id quảng cáo
Facebook mà đơn Pancake mang theo). Ad chưa nối tài khoản quảng cáo vào POS thì
KHÔNG có dòng chi phí — báo cáo vẫn hiện đủ phần doanh thu, cột chi phí để rỗng.
"""

import json

from app.db.client import get_pg_pool

# Cửa sổ ROAS/LTV theo đặc tả ADS-010 (?window=30|60|90)
WINDOWS = (7, 30, 60, 90)


def _json(v):
    return json.dumps(v, ensure_ascii=False) if v is not None else None


# ------------------------------------------------------------------ cây
def upsert_campaign(c: dict) -> dict | None:
    """Tìm-hoặc-cập-nhật chiến dịch theo (platform, external_campaign_id)."""
    if not c.get("external_campaign_id"):
        return None
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.ad_campaigns
                (external_campaign_id, name, platform, status, effective_status,
                 objective, external_account_id, account_name, currency,
                 daily_budget, lifetime_budget, start_time, end_time, synced_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            on conflict (platform, external_campaign_id) do update set
                name             = coalesce(excluded.name, crm.ad_campaigns.name),
                status           = coalesce(excluded.status, crm.ad_campaigns.status),
                effective_status = excluded.effective_status,
                objective        = coalesce(excluded.objective, crm.ad_campaigns.objective),
                external_account_id = coalesce(excluded.external_account_id,
                                               crm.ad_campaigns.external_account_id),
                account_name     = coalesce(excluded.account_name, crm.ad_campaigns.account_name),
                currency         = coalesce(excluded.currency, crm.ad_campaigns.currency),
                daily_budget     = excluded.daily_budget,
                lifetime_budget  = excluded.lifetime_budget,
                start_time       = coalesce(excluded.start_time, crm.ad_campaigns.start_time),
                end_time         = excluded.end_time,
                synced_at        = now()
            returning *
            """,
            (
                str(c["external_campaign_id"]), c.get("name") or str(c["external_campaign_id"]),
                c.get("platform") or "facebook", c.get("status"), c.get("effective_status"),
                c.get("objective"), c.get("external_account_id"), c.get("account_name"),
                c.get("currency"), c.get("daily_budget"), c.get("lifetime_budget"),
                c.get("start_time"), c.get("end_time"),
            ),
        ).fetchone()


def upsert_ad_set(s: dict) -> dict | None:
    """Tìm-hoặc-cập-nhật nhóm quảng cáo theo external_adset_id (unique)."""
    if not s.get("external_adset_id"):
        return None
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.ad_sets
                (external_adset_id, campaign_id, name, status, effective_status,
                 optimization_goal, destination_type, daily_budget, lifetime_budget,
                 start_time, end_time, targeting, synced_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
            on conflict (external_adset_id) do update set
                campaign_id      = coalesce(excluded.campaign_id, crm.ad_sets.campaign_id),
                name             = coalesce(excluded.name, crm.ad_sets.name),
                status           = coalesce(excluded.status, crm.ad_sets.status),
                effective_status = excluded.effective_status,
                optimization_goal = coalesce(excluded.optimization_goal,
                                             crm.ad_sets.optimization_goal),
                destination_type = coalesce(excluded.destination_type,
                                            crm.ad_sets.destination_type),
                daily_budget     = excluded.daily_budget,
                lifetime_budget  = excluded.lifetime_budget,
                start_time       = coalesce(excluded.start_time, crm.ad_sets.start_time),
                end_time         = excluded.end_time,
                targeting        = coalesce(excluded.targeting, crm.ad_sets.targeting),
                synced_at        = now()
            returning *
            """,
            (
                str(s["external_adset_id"]), s.get("campaign_id"), s.get("name"),
                s.get("status"), s.get("effective_status"), s.get("optimization_goal"),
                s.get("destination_type"), s.get("daily_budget"), s.get("lifetime_budget"),
                s.get("start_time"), s.get("end_time"), _json(s.get("targeting")),
            ),
        ).fetchone()


def upsert_ad(a: dict) -> dict | None:
    """Tìm-hoặc-cập-nhật quảng cáo theo external_ad_id (unique).

    Dùng chung dòng với `attribution_repo.upsert_ad` (nơi đơn POS tạo ad "trần"
    chỉ có mỗi id): ở đây bồi thêm tên, creative, adset, chi phí… vào đúng dòng đó.
    """
    if not a.get("external_ad_id"):
        return None
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.ads
                (external_ad_id, ad_set_id, name, status, effective_status,
                 creative_id, creative_name, object_story_id, post_id, platform,
                 external_account_id, created_time, first_seen_at, synced_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
            on conflict (external_ad_id) do update set
                ad_set_id        = coalesce(excluded.ad_set_id, crm.ads.ad_set_id),
                name             = coalesce(excluded.name, crm.ads.name),
                status           = coalesce(excluded.status, crm.ads.status),
                effective_status = excluded.effective_status,
                creative_id      = coalesce(excluded.creative_id, crm.ads.creative_id),
                creative_name    = coalesce(excluded.creative_name, crm.ads.creative_name),
                object_story_id  = coalesce(excluded.object_story_id, crm.ads.object_story_id),
                post_id          = coalesce(crm.ads.post_id, excluded.post_id),
                external_account_id = coalesce(excluded.external_account_id,
                                               crm.ads.external_account_id),
                created_time     = coalesce(crm.ads.created_time, excluded.created_time),
                synced_at        = now()
            returning *
            """,
            (
                str(a["external_ad_id"]), a.get("ad_set_id"), a.get("name"),
                a.get("status"), a.get("effective_status"), a.get("creative_id"),
                a.get("creative_name"), a.get("object_story_id"), a.get("post_id"),
                a.get("platform") or "facebook", a.get("external_account_id"),
                a.get("created_time"),
            ),
        ).fetchone()


def find_ad(external_ad_id: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.ads where external_ad_id = %s", (str(external_ad_id),)
        ).fetchone()


def noi_attribution_vao_ads() -> int:
    """Lấp `lead_attributions.ad_id` cho các dòng mới chỉ có external_ad_id.

    Đơn POS về TRƯỚC, cây quảng cáo đồng bộ SAU (hoặc ngược lại) — hàm này chạy
    cuối mỗi lượt đồng bộ cây để hai bên gặp nhau. Trả số dòng vừa nối.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            update crm.lead_attributions la
               set ad_id = a.id
              from crm.ads a
             where la.ad_id is null
               and la.external_ad_id is not null
               and a.external_ad_id = la.external_ad_id
            """
        ).rowcount


# ------------------------------------------------------------------ chi phí
def upsert_metrics(rows: list[dict]) -> int:
    """Ghi chỉ số 1 ngày cho nhiều thực thể. Chạy lại cùng ngày = ghi đè (idempotent)."""
    if not rows:
        return 0
    pool = get_pg_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            insert into crm.ad_metrics_daily
                (entity_type, entity_id, external_id, ngay, spend, impressions,
                 clicks, reach, cpc, cpm, ctr, frequency, currency)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (entity_type, entity_id, ngay) do update set
                spend = excluded.spend, impressions = excluded.impressions,
                clicks = excluded.clicks, reach = excluded.reach,
                cpc = excluded.cpc, cpm = excluded.cpm, ctr = excluded.ctr,
                frequency = excluded.frequency, currency = excluded.currency
            """,
            [
                (
                    r["entity_type"], r["entity_id"], str(r["external_id"]), r["ngay"],
                    r.get("spend") or 0, r.get("impressions") or 0, r.get("clicks") or 0,
                    r.get("reach") or 0, r.get("cpc"), r.get("cpm"), r.get("ctr"),
                    r.get("frequency"), r.get("currency"),
                )
                for r in rows
            ],
        )
    return len(rows)


def chi_phi_theo_ngay(tu: str = "", den: str = "") -> list[dict]:
    """Chi phí toàn hệ thống theo ngày (biểu đồ màn Nguồn quảng cáo)."""
    dk, ts = ["entity_type = 'ad'"], []
    if tu:
        dk.append("ngay >= %s")
        ts.append(tu)
    if den:
        dk.append("ngay <= %s")
        ts.append(den)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select ngay, sum(spend) as chi_phi, sum(impressions) as hien_thi,
                   sum(clicks) as click
              from crm.ad_metrics_daily where {' and '.join(dk)}
             group by ngay order by ngay
            """,
            tuple(ts),
        ).fetchall()


def ngay_da_co_chi_phi(tu: str, den: str) -> set:
    """Những ngày đã có dữ liệu chi phí — backfill bỏ qua cho nhanh."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select distinct ngay from crm.ad_metrics_daily"
            " where ngay between %s and %s", (tu, den)
        ).fetchall()
    return {r["ngay"] for r in rows}


# ------------------------------------------------------------------ báo cáo
# Khối dùng chung: mỗi khách quy nguồn (chạm CUỐI) kèm số liệu CRM của khách đó.
# Đặt riêng để 3 mức campaign/adset/ad dùng lại y hệt cách tính — nếu không, ba
# nơi tính ba kiểu là báo cáo "vênh nhau" ngay từ trong ruột.
_KHACH_QUY_NGUON = """
    select la.external_ad_id,
           la.customer_id,
           la.attributed_at,
           (select count(*) from crm.leads l where l.customer_id = la.customer_id)
               as so_lead,
           (select count(*) from crm.orders o
             where o.customer_id = la.customer_id
               and o.status not in ('cancelled','draft')) as so_don,
           (select count(*) from crm.orders o
             where o.customer_id = la.customer_id
               and o.status in ('delivered','collected')) as so_don_giao,
           (select coalesce(sum(o.total_amount), 0) from crm.orders o
             where o.customer_id = la.customer_id
               and o.status in ('delivered','collected')) as doanh_thu,
           (select count(*) from crm.orders o
             where o.customer_id = la.customer_id
               and o.status in ('returned','returning')) as so_hoan
      from crm.lead_attributions la
     where la.touch_type = 'last' and la.customer_id is not null
       and (%(tu)s = '' or la.attributed_at >= %(tu)s::timestamptz)
       and (%(den)s = '' or la.attributed_at < (%(den)s::date + 1)::timestamptz)
"""

_CHI_PHI = """
    select external_id, sum(spend) as chi_phi, sum(impressions) as hien_thi,
           sum(clicks) as click, sum(reach) as tiep_can
      from crm.ad_metrics_daily
     where entity_type = %(cap)s
       and (%(tu)s = '' or ngay >= %(tu)s::date)
       and (%(den)s = '' or ngay <= %(den)s::date)
     group by external_id
"""


def bao_cao_ad(tu: str = "", den: str = "", limit: int = 100) -> list[dict]:
    """Màn 55 — hiệu quả TỪNG QUẢNG CÁO: chi phí · khách · lead · đơn · doanh thu · ROAS.

    `tu`/`den` (YYYY-MM-DD) lọc cả chi phí (theo ngày) lẫn khách (theo mốc quy
    nguồn) để hai vế cùng một kỳ — so lệch kỳ là ROAS sai ngay.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            with kh as ({_KHACH_QUY_NGUON}),
                 cp as ({_CHI_PHI})
            select coalesce(kh.external_ad_id, cp.external_id) as external_ad_id,
                   a.name, a.creative_name, a.status, a.post_id,
                   s.name as ad_set_name, c.name as campaign_name,
                   coalesce(cp.chi_phi, 0)   as chi_phi,
                   cp.hien_thi, cp.click,
                   count(kh.customer_id)     as so_khach,
                   coalesce(sum(kh.so_lead), 0)     as so_lead,
                   coalesce(sum(kh.so_don), 0)      as so_don,
                   coalesce(sum(kh.so_don_giao), 0) as so_don_giao,
                   coalesce(sum(kh.so_hoan), 0)     as so_hoan,
                   coalesce(sum(kh.doanh_thu), 0)   as doanh_thu,
                   case when coalesce(cp.chi_phi, 0) > 0
                        then round(coalesce(sum(kh.doanh_thu), 0) / cp.chi_phi, 2) end as roas,
                   case when count(kh.customer_id) > 0
                        then round(coalesce(sum(kh.doanh_thu), 0)
                                   / count(kh.customer_id), 0) end as ltv,
                   (cp.external_id is null) as thieu_chi_phi
              from kh
              full join cp on cp.external_id = kh.external_ad_id
              left join crm.ads a on a.external_ad_id
                        = coalesce(kh.external_ad_id, cp.external_id)
              left join crm.ad_sets s      on s.id = a.ad_set_id
              left join crm.ad_campaigns c on c.id = s.campaign_id
             group by 1, a.name, a.creative_name, a.status, a.post_id, s.name, c.name,
                      cp.chi_phi, cp.hien_thi, cp.click, cp.external_id
             order by doanh_thu desc, chi_phi desc
             limit %(limit)s
            """,
            {"tu": tu, "den": den, "cap": "ad", "limit": limit},
        ).fetchall()


def _bao_cao_cap_tren(cap: str, tu: str, den: str, limit: int) -> list[dict]:
    """Gộp báo cáo lên mức adset (màn 54) hoặc campaign (màn 53).

    Doanh thu gộp từ ad con (đi qua cây ads -> ad_sets -> ad_campaigns); chi phí
    lấy THẲNG ở mức đó (POS trả insights riêng cho từng cấp) — chính xác hơn cộng
    dồn từ ad, vì ad ngừng chạy vẫn còn chi phí ở cấp trên.
    """
    if cap == "ad_set":
        bang, khoa, ten = "crm.ad_sets", "s.external_adset_id", "s.name"
        join = ("left join crm.ad_sets s on s.id = a.ad_set_id")
        nhom_them = ""
    else:
        bang, khoa, ten = "crm.ad_campaigns", "c.external_campaign_id", "c.name"
        join = ("left join crm.ad_sets s on s.id = a.ad_set_id "
                "left join crm.ad_campaigns c on c.id = s.campaign_id")
        nhom_them = ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            with kh as ({_KHACH_QUY_NGUON}),
                 cp as ({_CHI_PHI}),
                 gop as (
                    select {khoa} as external_id, {ten} as name,
                           count(kh.customer_id)            as so_khach,
                           coalesce(sum(kh.so_lead), 0)     as so_lead,
                           coalesce(sum(kh.so_don), 0)      as so_don,
                           coalesce(sum(kh.so_don_giao), 0) as so_don_giao,
                           coalesce(sum(kh.so_hoan), 0)     as so_hoan,
                           coalesce(sum(kh.doanh_thu), 0)   as doanh_thu
                      from kh
                      join crm.ads a on a.external_ad_id = kh.external_ad_id
                      {join}
                     where {khoa} is not null
                     group by 1, 2 {nhom_them}
                 )
            select coalesce(gop.external_id, cp.external_id) as external_id,
                   coalesce(gop.name, t.name)                as name,
                   coalesce(cp.chi_phi, 0) as chi_phi, cp.hien_thi, cp.click,
                   coalesce(gop.so_khach, 0)     as so_khach,
                   coalesce(gop.so_lead, 0)      as so_lead,
                   coalesce(gop.so_don, 0)       as so_don,
                   coalesce(gop.so_don_giao, 0)  as so_don_giao,
                   coalesce(gop.so_hoan, 0)      as so_hoan,
                   coalesce(gop.doanh_thu, 0)    as doanh_thu,
                   case when coalesce(cp.chi_phi, 0) > 0
                        then round(coalesce(gop.doanh_thu, 0) / cp.chi_phi, 2) end as roas,
                   case when coalesce(gop.so_khach, 0) > 0
                        then round(gop.doanh_thu / gop.so_khach, 0) end as ltv,
                   (cp.external_id is null) as thieu_chi_phi
              from gop
              full join cp on cp.external_id = gop.external_id
              left join {bang} t on t.{'external_adset_id' if cap == 'ad_set' else 'external_campaign_id'}
                        = coalesce(gop.external_id, cp.external_id)
             order by doanh_thu desc, chi_phi desc
             limit %(limit)s
            """,
            {"tu": tu, "den": den, "cap": cap, "limit": limit},
        ).fetchall()


def bao_cao_ad_set(tu: str = "", den: str = "", limit: int = 100) -> list[dict]:
    """Màn 54 — hiệu quả theo nhóm quảng cáo."""
    return _bao_cao_cap_tren("ad_set", tu, den, limit)


def bao_cao_campaign(tu: str = "", den: str = "", limit: int = 100) -> list[dict]:
    """Màn 53 — hiệu quả theo chiến dịch."""
    return _bao_cao_cap_tren("campaign", tu, den, limit)


def tong_hop(tu: str = "", den: str = "") -> dict:
    """Dòng TỔNG của kỳ: chi phí, khách, đơn, doanh thu, ROAS chung (màn 7)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            with kh as ({_KHACH_QUY_NGUON}),
                 cp as ({_CHI_PHI})
            select (select coalesce(sum(chi_phi), 0) from cp)          as chi_phi,
                   (select count(*) from kh)                          as so_khach,
                   (select coalesce(sum(so_don), 0) from kh)          as so_don,
                   (select coalesce(sum(so_don_giao), 0) from kh)     as so_don_giao,
                   (select coalesce(sum(doanh_thu), 0) from kh)       as doanh_thu,
                   (select count(*) from crm.ads)                     as so_ad,
                   (select count(distinct external_id)
                      from crm.ad_metrics_daily where entity_type = 'ad') as so_ad_co_chi_phi
            """,
            {"tu": tu, "den": den, "cap": "ad"},
        ).fetchone()


def hieu_qua_ad(external_ad_id: str, window: int = 30) -> dict:
    """ADS-010 — ROAS/LTV của 1 quảng cáo trong cửa sổ N ngày gần nhất."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            with cp as (
                select coalesce(sum(spend), 0) as chi_phi,
                       coalesce(sum(impressions), 0) as hien_thi,
                       coalesce(sum(clicks), 0) as click
                  from crm.ad_metrics_daily
                 where entity_type = 'ad' and external_id = %(ad)s
                   and ngay > current_date - %(w)s
            ), kh as (
                select la.customer_id,
                       (select coalesce(sum(o.total_amount), 0) from crm.orders o
                         where o.customer_id = la.customer_id
                           and o.status in ('delivered','collected')) as doanh_thu,
                       (select count(*) from crm.orders o
                         where o.customer_id = la.customer_id
                           and o.status in ('delivered','collected')
                           and o.order_type <> 'new') as don_mua_lai
                  from crm.lead_attributions la
                 where la.touch_type = 'last' and la.external_ad_id = %(ad)s
                   and la.attributed_at > now() - make_interval(days => %(w)s)
            )
            select %(ad)s as external_ad_id, %(w)s as window,
                   (select chi_phi from cp)  as chi_phi,
                   (select hien_thi from cp) as hien_thi,
                   (select click from cp)    as click,
                   (select count(*) from kh) as so_khach,
                   (select coalesce(sum(doanh_thu), 0) from kh) as doanh_thu,
                   (select coalesce(sum(don_mua_lai), 0) from kh) as don_mua_lai,
                   case when (select chi_phi from cp) > 0
                        then round((select coalesce(sum(doanh_thu), 0) from kh)
                                   / (select chi_phi from cp), 2) end as roas,
                   case when (select count(*) from kh) > 0
                        then round((select coalesce(sum(doanh_thu), 0) from kh)
                                   / (select count(*) from kh), 0) end as ltv
            """,
            {"ad": str(external_ad_id), "w": window},
        ).fetchone()


def phieu_theo_ad(external_ad_id: str) -> dict:
    """ADS-006 — phễu của 1 quảng cáo: khách → lead → tư vấn → đơn → giao thành công.

    Suy TỪ DỮ LIỆU THẬT (leads/consultation_sessions/orders) chứ không đợi bảng
    funnel_events được đổ đầy — số liệu đúng ngay, không phải chờ lát cắt sau.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            with kh as (
                select distinct customer_id from crm.lead_attributions
                 where touch_type = 'last' and external_ad_id = %s
                   and customer_id is not null
            )
            select (select count(*) from kh) as khach,
                   (select count(distinct l.customer_id) from crm.leads l
                     join kh on kh.customer_id = l.customer_id) as lead,
                   (select count(distinct s.customer_id)
                      from crm.consultation_sessions s
                      join kh on kh.customer_id = s.customer_id) as tu_van,
                   (select count(distinct o.customer_id) from crm.orders o
                     join kh on kh.customer_id = o.customer_id
                    where o.status not in ('draft','cancelled')) as co_don,
                   (select count(distinct o.customer_id) from crm.orders o
                     join kh on kh.customer_id = o.customer_id
                    where o.status in ('delivered','collected')) as giao_thanh_cong,
                   (select count(distinct o.customer_id) from crm.orders o
                     join kh on kh.customer_id = o.customer_id
                    where o.order_type <> 'new'
                      and o.status in ('delivered','collected')) as mua_lai
            """,
            (str(external_ad_id),),
        ).fetchone()


def ly_do_chua_chot_theo_ad(external_ad_id: str) -> list[dict]:
    """ADS-008 — lý do chưa chốt của khách đến từ 1 quảng cáo (màn 56/58)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select r.name as ly_do, r.category, count(*) as so_lead
              from crm.lead_lost_reasons llr
              join crm.leads l        on l.id = llr.lead_id
              join crm.lead_reasons r on r.id = llr.lost_reason_id
              join crm.lead_attributions la on la.customer_id = l.customer_id
             where la.touch_type = 'last' and la.external_ad_id = %s
             group by r.name, r.category
             order by so_lead desc
            """,
            (str(external_ad_id),),
        ).fetchall()


def khach_cua_ad(external_ad_id: str, limit: int = 50) -> list[dict]:
    """Danh sách khách minh chứng (mọi số trên màn đều bấm ra được — FR-171)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select c.id, c.full_name, c.primary_phone, c.status,
                   la.attributed_at, la.post_id,
                   (select coalesce(sum(o.total_amount), 0) from crm.orders o
                     where o.customer_id = c.id
                       and o.status in ('delivered','collected')) as doanh_thu
              from crm.lead_attributions la
              join crm.customers c on c.id = la.customer_id
             where la.touch_type = 'last' and la.external_ad_id = %s
             order by la.attributed_at desc nulls last
             limit %s
            """,
            (str(external_ad_id), limit),
        ).fetchall()


def list_campaigns(limit: int = 100) -> list[dict]:
    """ADS-002 — danh sách chiến dịch (dữ liệu cây, chưa ghép hiệu quả)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.ad_campaigns order by start_time desc nulls last limit %s",
            (limit,),
        ).fetchall()


def list_ad_sets(campaign_id: int | None = None, limit: int = 100) -> list[dict]:
    """ADS-003 — danh sách nhóm quảng cáo, lọc theo chiến dịch."""
    where, ts = "", ()
    if campaign_id is not None:
        where, ts = "where s.campaign_id = %s", (campaign_id,)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select s.*, c.name as campaign_name
              from crm.ad_sets s
              left join crm.ad_campaigns c on c.id = s.campaign_id
              {where}
             order by s.start_time desc nulls last limit %s
            """,
            (*ts, limit),
        ).fetchall()


def list_ads(ad_set_id: int | None = None, limit: int = 100) -> list[dict]:
    """ADS-004 — danh sách quảng cáo, lọc theo nhóm."""
    where, ts = "", ()
    if ad_set_id is not None:
        where, ts = "where a.ad_set_id = %s", (ad_set_id,)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select a.*, s.name as ad_set_name, c.name as campaign_name
              from crm.ads a
              left join crm.ad_sets s      on s.id = a.ad_set_id
              left join crm.ad_campaigns c on c.id = s.campaign_id
              {where}
             order by a.created_time desc nulls last, a.id desc limit %s
            """,
            (*ts, limit),
        ).fetchall()
