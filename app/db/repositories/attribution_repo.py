"""Truy vấn quy nguồn quảng cáo (BRD mục 4: campaign/adset/ad/creative + first/last touch).

Pancake CHỈ trả `ad_id` + `post_id` (kèm `ads_source`, `p_utm_*` ở đơn POS) — cây
campaign → adset → ad phải lấy từ Facebook Ads API, việc của C-MVP5. Nên ở đây:

  * `crm.ads` nhận ad_id lẻ (ad_set_id để rỗng — schema đã nới); MVP5 sau này chỉ
    cần lấp ad_set_id vào đúng dòng, KHÔNG phải sửa dữ liệu đã quy nguồn.
  * `crm.lead_attributions` giữ 2 dòng mỗi khách: 'first' (chạm đầu, không bao giờ
    đè) và 'last' (chạm cuối, luôn ghi đè khi có chạm mới hơn).
"""

import json

from app.db.client import get_pg_pool


def upsert_ad(
    *, external_ad_id: str, platform: str = "facebook", post_id: str = "",
    name: str = "", creative_id: str = "",
) -> dict | None:
    """Tìm-hoặc-tạo `crm.ads` theo external_ad_id (unique). Rỗng -> None."""
    if not external_ad_id:
        return None
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.ads (external_ad_id, platform, post_id, name,
                                 creative_id, first_seen_at)
            values (%s, %s, nullif(%s, ''), nullif(%s, ''), nullif(%s, ''), now())
            on conflict (external_ad_id) do update set
                post_id     = coalesce(crm.ads.post_id, excluded.post_id),
                name        = coalesce(crm.ads.name, excluded.name),
                creative_id = coalesce(crm.ads.creative_id, excluded.creative_id),
                platform    = coalesce(crm.ads.platform, excluded.platform)
            returning *
            """,
            (str(external_ad_id), platform, post_id, name, creative_id),
        ).fetchone()


def ghi_cham(
    *, customer_id: int, touch_type: str, attributed_at, ad_id: int | None = None,
    external_ad_id: str = "", post_id: str = "", source: str = "",
    utm: dict | None = None, lead_id: int | None = None,
) -> dict | None:
    """Ghi 1 chạm quy nguồn.

    'first' — chỉ ghi khi CHƯA có, hoặc chạm mới sớm hơn chạm đang lưu (backfill
    chạy ngược thời gian vẫn ra đúng chạm đầu tiên).
    'last'  — ghi đè khi chạm mới muộn hơn chạm đang lưu.
    """
    if touch_type not in ("first", "last"):
        raise ValueError(f"touch_type lạ: {touch_type}")
    dieu_kien = "<" if touch_type == "first" else ">"
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            insert into crm.lead_attributions
                (customer_id, lead_id, ad_id, touch_type, attributed_at,
                 source, external_ad_id, post_id, utm)
            values (%s, %s, %s, %s, %s, nullif(%s, ''), nullif(%s, ''),
                    nullif(%s, ''), %s::jsonb)
            on conflict (customer_id, touch_type)
                where customer_id is not null and touch_type in ('first','last')
            do update set
                ad_id          = excluded.ad_id,
                lead_id        = coalesce(excluded.lead_id, crm.lead_attributions.lead_id),
                attributed_at  = excluded.attributed_at,
                source         = excluded.source,
                external_ad_id = excluded.external_ad_id,
                post_id        = excluded.post_id,
                utm            = excluded.utm
            where crm.lead_attributions.attributed_at is null
               or excluded.attributed_at {dieu_kien} crm.lead_attributions.attributed_at
            returning *
            """,
            (
                customer_id, lead_id, ad_id, touch_type, attributed_at,
                source, str(external_ad_id or ""), str(post_id or ""),
                json.dumps(utm or {}, ensure_ascii=False),
            ),
        ).fetchone()


def cham_cua_khach(customer_id: int) -> list[dict]:
    """Chạm đầu/cuối của 1 khách (tab Nguồn Ads ở hồ sơ 360°)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select la.*, a.external_ad_id as ad_external, a.name as ad_name,
                   a.post_id as ad_post_id
              from crm.lead_attributions la
              left join crm.ads a on a.id = la.ad_id
             where la.customer_id = %s and la.touch_type in ('first','last')
             order by la.touch_type
            """,
            (customer_id,),
        ).fetchall()


def thong_ke_nguon(limit: int = 20) -> list[dict]:
    """Top quảng cáo theo số khách chạm CUỐI — số liệu "Attribution Marketing".

    Doanh thu cộng từ đơn KHÔNG huỷ/hoàn của những khách đó (đo Ads bằng tiền
    thật theo mục 1 BRD, không phải bằng số inbox).
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select coalesce(la.external_ad_id, '(không rõ)') as ad_id,
                   la.post_id,
                   la.source,
                   count(distinct la.customer_id) as so_khach,
                   coalesce(sum(d.tien), 0)       as doanh_thu
              from crm.lead_attributions la
              left join lateral (
                    select sum(o.total_amount) as tien
                      from crm.orders o
                     where o.customer_id = la.customer_id
                       and o.status not in ('cancelled','returned')
              ) d on true
             where la.touch_type = 'last'
             group by 1, 2, 3
             order by so_khach desc, doanh_thu desc
             limit %s
            """,
            (limit,),
        ).fetchall()


def dem_cham() -> dict:
    """Đếm nhanh cho khối tình trạng: bao nhiêu khách đã có chạm đầu/cuối."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select
              count(*) filter (where touch_type = 'first') as cham_dau,
              count(*) filter (where touch_type = 'last')  as cham_cuoi,
              count(distinct external_ad_id)               as so_ad
              from crm.lead_attributions
            """
        ).fetchone()
