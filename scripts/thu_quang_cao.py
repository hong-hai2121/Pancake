"""Kiểm thử NGUỒN QUẢNG CÁO (BRD mục 4 phần Ads · màn 7 + 53-56 · ADS/ATTRIBUTION).

Nghiệm thu:
  cây       campaign → adset → ad → creative dựng đúng từ payload Pancake POS
  chi phí   lưu theo NGÀY, chạy lại là ghi đè (không cộng dồn), cộng ra được
            mọi cửa sổ 7/30/60/90 ngày
  báo cáo   ROAS = doanh thu ĐƠN ĐÃ GIAO / chi phí cùng kỳ · LTV/khách ·
            gộp đúng lên adset và campaign
  luật      ad chưa nối tài khoản quảng cáo -> chi phí RỖNG (không phải 0);
            đơn về trước cây về sau vẫn nối được (noi_attribution_vao_ads)
  màn/API   ADS-002/003/004/006/008/010 · ATTRIBUTION-001/002 · phân quyền ads.view

Dữ liệu GIẢ hết (dấu `__qctest__`, ad id 9990000000000001…) — KHÔNG gọi mạng.

Chạy:  python scripts/thu_quang_cao.py
Cần:   DB + init_crm.sql bản nguồn quảng cáo + seed_auth (có ads.view).
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core.errors import ApiError               # noqa: E402
from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.db.repositories import ads_repo, attribution_repo  # noqa: E402
from app.integrations.pancake_pos import ads_sync  # noqa: E402
from app.main import app                           # noqa: E402
from app.services import ads_service                # noqa: E402

DAU = "__qctest__"
MK = "QC-test-1234"
AD1 = "9990000000000001"     # ad có cả chi phí lẫn doanh thu
AD2 = "9990000000000002"     # ad CÓ doanh thu nhưng CHƯA có chi phí
CD = "9990000000009001"      # campaign
NHOM = "9990000000008001"    # adset
HOM_NAY = date.today()
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def phai_loi(ten: str, ma: str, fn, *a, **kw) -> None:
    try:
        fn(*a, **kw)
        ok(ten, False, "không raise gì cả")
    except ApiError as e:
        ok(ten, e.code == ma, f"raise {e.code} thay vì {ma}")


def don_dep(conn) -> None:
    conn.execute(
        "delete from crm.ad_metrics_daily where external_id = any(%s)",
        ([AD1, AD2, CD, NHOM],))
    conn.execute(
        "delete from crm.lead_attributions where customer_id in "
        f"(select id from crm.customers where full_name like '{DAU}%')")
    conn.execute(
        "delete from crm.orders where customer_id in "
        f"(select id from crm.customers where full_name like '{DAU}%')")
    conn.execute(
        "delete from crm.lead_lost_reasons where lead_id in (select l.id from crm.leads l "
        f"join crm.customers c on c.id = l.customer_id where c.full_name like '{DAU}%')")
    conn.execute(
        "delete from crm.leads where customer_id in "
        f"(select id from crm.customers where full_name like '{DAU}%')")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute("delete from crm.ads where external_ad_id = any(%s)", ([AD1, AD2],))
    conn.execute("delete from crm.ad_sets where external_adset_id = %s", (NHOM,))
    conn.execute("delete from crm.ad_campaigns where external_campaign_id = %s", (CD,))
    conn.execute(f"delete from crm.users where email like '{DAU}%'")
    conn.execute("delete from crm.sync_logs where scope like '__qc%'")


def ad_pos(ad_id: str, *, spend: float, ten: str) -> dict:
    """Một dòng ads_v2 giả — đúng shape Pancake POS trả về."""
    return {
        "id": ad_id, "name": ten, "status": "ACTIVE", "effective_status": "ACTIVE",
        "created_time": "2026-07-20T16:25:51",
        "ad_account": {"id": "77770000", "name": f"{DAU}TK", "currency": "VND"},
        "ad_campaign": {"id": CD, "name": f"{DAU}Chien dich", "daily_budget": 200000},
        "ad_set": {"id": NHOM, "name": f"{DAU}Nhom 36-65", "daily_budget": 0},
        "ad_creative": {"id": "5550001", "name": f"{DAU}Creative dạ dày",
                        "object_story_id": "182693004923170_122203562270131010"},
        "insights": {"spend": spend, "impressions": 1000, "clicks": 20,
                     "reach": 900, "cpc": spend / 20 if spend else 0,
                     "cpm": 1000, "ctr": 2.0, "frequency": 1.1},
    }


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        for ten, vai in (("mkt", "Marketing"), ("sale", "Sale")):
            conn.execute(
                "insert into crm.users (name, email, username, password_hash, status, role_id) "
                "values (%s, %s, %s, %s, 'active', %s)",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]))
        kh = [conn.execute(
            "insert into crm.customers (full_name, primary_phone, source) "
            "values (%s, %s, 'pancake_pos') returning id",
            (f"{DAU}Khach{i}", f"09000000{i:02d}")).fetchone()["id"] for i in (1, 2, 3)]

    print("== 1. Dựng cây quảng cáo từ payload Pancake POS ==")
    ads_sync._luu_ad(ad_pos(AD1, spend=0, ten=f"{DAU}Ad 1"))
    ad = ads_repo.find_ad(AD1)
    ok("ad lưu được kèm creative + tên", ad and ad["creative_id"] == "5550001"
       and ad["creative_name"].startswith(DAU), str(ad)[:120])
    ok("cắt post_id từ object_story_id để khớp bài viết trên đơn",
       ad["post_id"] == "122203562270131010", str(ad.get("post_id")))
    ds = ads_repo.list_ads(limit=500)
    dong = next((r for r in ds if r["external_ad_id"] == AD1), None)
    ok("ad nối đúng nhóm + chiến dịch (cây 3 tầng)",
       dong and dong["ad_set_name"] == f"{DAU}Nhom 36-65"
       and dong["campaign_name"] == f"{DAU}Chien dich", str(dong)[:160])
    ads_sync._luu_ad(ad_pos(AD1, spend=0, ten=f"{DAU}Ad 1"))
    ok("chạy lại -> không tạo trùng (idempotent)",
       len([r for r in ads_repo.list_ads(limit=500)
            if r["external_ad_id"] == AD1]) == 1)

    print("== 2. Chi phí theo NGÀY — chạy lại là ghi đè, không cộng dồn ==")
    ad_id_crm = ads_repo.find_ad(AD1)["id"]
    for lui, tien in ((0, 100000), (1, 200000), (40, 900000)):
        ads_repo.upsert_metrics([{
            "entity_type": "ad", "entity_id": ad_id_crm, "external_id": AD1,
            "ngay": HOM_NAY - timedelta(days=lui), "spend": tien,
            "impressions": 500, "clicks": 10, "reach": 400}])
    ads_repo.upsert_metrics([{
        "entity_type": "ad", "entity_id": ad_id_crm, "external_id": AD1,
        "ngay": HOM_NAY, "spend": 150000, "impressions": 500,
        "clicks": 10, "reach": 400}])
    # Đọc THẲNG dòng của AD1: `chi_phi_theo_ngay` cộng cả hệ thống, mà DB thật có
    # thể đang giữ chi phí của quảng cáo thật -> so số sẽ lệch vì lý do không liên quan.
    with pool.connection() as conn:
        theo_ngay = {r["ngay"]: float(r["spend"]) for r in conn.execute(
            "select ngay, spend from crm.ad_metrics_daily"
            " where entity_type = 'ad' and external_id = %s", (AD1,)).fetchall()}
    ok("ghi lại cùng ngày -> ĐÈ (150k chứ không phải 250k)",
       theo_ngay.get(HOM_NAY) == 150000, str(theo_ngay.get(HOM_NAY)))
    ok("mỗi ngày một dòng riêng",
       theo_ngay.get(HOM_NAY - timedelta(days=1)) == 200000 and len(theo_ngay) == 3,
       str(theo_ngay))

    hq7 = ads_repo.hieu_qua_ad(AD1, 7)
    hq90 = ads_repo.hieu_qua_ad(AD1, 90)
    ok("cửa sổ 7 ngày chỉ cộng chi phí trong 7 ngày (350k)",
       float(hq7["chi_phi"]) == 350000, str(hq7["chi_phi"]))
    ok("cửa sổ 90 ngày cộng cả ngày cũ (1.250k)",
       float(hq90["chi_phi"]) == 1250000, str(hq90["chi_phi"]))

    print("== 3. Quy nguồn + doanh thu -> ROAS/LTV ==")
    with pool.connection() as conn:
        for i, (kid, tien, tt) in enumerate((
            (kh[0], 600000, "delivered"),
            (kh[1], 400000, "collected"),
            (kh[2], 900000, "cancelled"),     # đơn hủy KHÔNG được tính doanh thu
        )):
            conn.execute(
                "insert into crm.orders (customer_id, status, total_amount, order_type,"
                " source, external_order_id) values (%s, %s, %s, 'new', 'pancake_pos', %s)",
                (kid, tt, tien, f"{DAU}don{i}"))
    for kid in (kh[0], kh[1]):
        attribution_repo.ghi_cham(
            customer_id=kid, touch_type="last", attributed_at=datetime.now(),
            external_ad_id=AD1, source="pancake_pos")
    attribution_repo.ghi_cham(
        customer_id=kh[2], touch_type="last", attributed_at=datetime.now(),
        external_ad_id=AD2, source="pancake_pos")   # ad CHƯA có chi phí

    tu = (HOM_NAY - timedelta(days=7)).isoformat()
    den = HOM_NAY.isoformat()
    bang = {r["external_ad_id"]: r for r in ads_repo.bao_cao_ad(tu, den)}
    r1 = bang.get(AD1)
    ok("doanh thu chỉ tính đơn ĐÃ GIAO (600k + 400k = 1.000k)",
       r1 and float(r1["doanh_thu"]) == 1000000, str(r1 and r1["doanh_thu"]))
    ok("ROAS = doanh thu / chi phí cùng kỳ (1.000k / 350k = 2.86)",
       float(r1["roas"]) == 2.86, str(r1["roas"]))
    ok("LTV = doanh thu / số khách (500k)", float(r1["ltv"]) == 500000, str(r1["ltv"]))
    ok("đếm đúng khách + đơn giao thành công", r1["so_khach"] == 2
       and r1["so_don_giao"] == 2, f"{r1['so_khach']} {r1['so_don_giao']}")

    r2 = bang.get(AD2)
    ok("ad chưa nối tài khoản QC -> đánh dấu thiếu chi phí, ROAS RỖNG (không phải 0)",
       r2 and r2["thieu_chi_phi"] and r2["roas"] is None, str(r2)[:160])
    ok("ad thiếu chi phí vẫn hiện trong báo cáo (không bị giấu đi)", r2 is not None)

    print("== 4. Gộp lên nhóm và chiến dịch ==")
    ns = {r["external_id"]: r for r in ads_repo.bao_cao_ad_set(tu, den)}
    cd = {r["external_id"]: r for r in ads_repo.bao_cao_campaign(tu, den)}
    ok("nhóm quảng cáo gộp đúng doanh thu của ad con",
       NHOM in ns and float(ns[NHOM]["doanh_thu"]) == 1000000, str(ns.get(NHOM))[:140])
    ok("chiến dịch gộp đúng doanh thu",
       CD in cd and float(cd[CD]["doanh_thu"]) == 1000000, str(cd.get(CD))[:140])

    print("== 5. Đơn về TRƯỚC, cây quảng cáo về SAU vẫn nối được ==")
    with pool.connection() as conn:
        conn.execute("update crm.lead_attributions set ad_id = null "
                     "where external_ad_id = %s", (AD1,))
    so_noi = ads_repo.noi_attribution_vao_ads()
    with pool.connection() as conn:
        con_trong = conn.execute(
            "select count(*) n from crm.lead_attributions"
            " where external_ad_id = %s and ad_id is null", (AD1,)).fetchone()["n"]
    ok("noi_attribution_vao_ads lấp ad_id cho dòng quy nguồn",
       so_noi >= 2 and con_trong == 0, f"nối {so_noi}, còn trống {con_trong}")

    print("== 6. Phễu + lý do chưa chốt của 1 quảng cáo ==")
    with pool.connection() as conn:
        pipeline = conn.execute(
            "select id from crm.pipelines order by id limit 1").fetchone()
        stage = conn.execute(
            "select id from crm.pipeline_stages where pipeline_id = %s"
            " order by sort_order limit 1", (pipeline["id"],)).fetchone()
        lead_id = conn.execute(
            "insert into crm.leads (customer_id, pipeline_id, stage_id, source) "
            "values (%s, %s, %s, 'pancake') returning id",
            (kh[0], pipeline["id"], stage["id"])).fetchone()["id"]
        ly_do = conn.execute(
            "select id, name from crm.lead_reasons order by id limit 1").fetchone()
        conn.execute(
            "insert into crm.lead_lost_reasons (lead_id, lost_reason_id) values (%s, %s)",
            (lead_id, ly_do["id"]))
    ph = ads_repo.phieu_theo_ad(AD1)
    ok("phễu đếm khách → lead → đơn → giao thành công",
       ph["khach"] == 2 and ph["lead"] == 1 and ph["giao_thanh_cong"] == 2, str(ph))
    ld = ads_repo.ly_do_chua_chot_theo_ad(AD1)
    ok("lý do chưa chốt gom theo quảng cáo",
       any(r["ly_do"] == ly_do["name"] for r in ld), str(ld[:2]))
    khach = ads_repo.khach_cua_ad(AD1)
    ok("bấm ra được danh sách khách minh chứng (FR-171)", len(khach) == 2)

    print("== 7. Tổng quan + cảnh báo thiếu chi phí ==")
    tq = ads_service.tong_quan(tu, den)
    # >= thay vì == : DB thật (POS_SYNC bật) có doanh thu quy nguồn thật cộng
    # thêm vào kỳ — chỉ cần chắc 1 triệu của dữ liệu giả nằm TRONG tổng
    ok("tổng quan cộng đúng chi phí + doanh thu kỳ",
       float(tq["chi_phi"]) >= 350000 and float(tq["doanh_thu"]) >= 1000000,
       f"{tq['chi_phi']} {tq['doanh_thu']}")
    ok("đếm được số ad có doanh thu mà CHƯA có chi phí (nhắc nối tài khoản QC)",
       tq["ad_thieu_chi_phi"] >= 1, str(tq["ad_thieu_chi_phi"]))

    print("== 8. ATTRIBUTION-001 — gắn nguồn tay ==")
    cu = attribution_repo.cham_cua_khach(kh[0])
    cham_dau = ads_service.gan_nguon(kh[0], {
        "external_ad_id": AD2, "touch_type": "first",
        "attributed_at": datetime.now() - timedelta(days=10), "source": "tay"})
    moi = {c["touch_type"]: c for c in attribution_repo.cham_cua_khach(kh[0])}
    ok("gắn tay chạm ĐẦU không đụng chạm CUỐI đã có",
       moi["first"]["external_ad_id"] == AD2
       and moi["last"]["external_ad_id"] == AD1, str(moi)[:200])
    giu = ads_service.gan_nguon(kh[0], {
        "external_ad_id": AD1, "touch_type": "first",
        "attributed_at": datetime.now(), "source": "tay"})
    ok("chạm đầu mới HƠN chạm đang lưu -> giữ bản cũ (không đè lịch sử)",
       giu.get("giu_nguyen") is True, str(giu)[:120])
    phai_loi("gắn nguồn thiếu cả ad lẫn post -> VALIDATION_ERROR", "VALIDATION_ERROR",
             ads_service.gan_nguon, kh[0], {"touch_type": "last"})
    phai_loi("gắn nguồn cho khách không tồn tại -> NOT_FOUND", "NOT_FOUND",
             ads_service.gan_nguon, 99999999, {"external_ad_id": AD1})
    phai_loi("cấp báo cáo lạ -> VALIDATION_ERROR", "VALIDATION_ERROR",
             ads_service.bao_cao, "creative")
    phai_loi("window lạ -> VALIDATION_ERROR", "VALIDATION_ERROR",
             ads_service.hieu_qua, AD1, 45)

    print("== 9. API ADS-002…010 + phân quyền ads.view ==")
    client = TestClient(app)

    def dang_nhap(u: str) -> dict:
        r = client.post("/api/v1/auth/login", json={"username": u, "password": MK})
        assert r.status_code == 200, r.text[:200]
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    hm = dang_nhap(f"{DAU}mkt")
    hs = dang_nhap(f"{DAU}sale")

    r = client.get(f"/api/v1/ad-campaigns?tu={tu}&den={den}", headers=hm)
    ok("ADS-002 Marketing xem chiến dịch kèm hiệu quả", r.status_code == 200
       and any(x["external_id"] == CD for x in r.json()["data"]["items"]), r.text[:200])
    r = client.get("/api/v1/ad-sets?hieu_qua=false", headers=hm)
    ok("ADS-003 xem cây nhóm quảng cáo", r.status_code == 200)
    r = client.get(f"/api/v1/ads?tu={tu}&den={den}", headers=hm)
    ok("ADS-004 danh sách quảng cáo kèm ROAS", r.status_code == 200
       and any(x["external_ad_id"] == AD1 and x["roas"] for x in r.json()["data"]["items"]))
    r = client.get(f"/api/v1/ads/{AD1}/performance?window=7", headers=hm)
    ok("ADS-010 hiệu quả theo cửa sổ 7 ngày",
       r.status_code == 200 and float(r.json()["data"]["chi_phi"]) == 350000, r.text[:200])
    r = client.get(f"/api/v1/ads/{AD1}/performance?window=45", headers=hm)
    ok("ADS-010 window ngoài 7/30/60/90 -> 422", r.status_code == 422)
    r = client.get(f"/api/v1/ads/{AD1}/funnel", headers=hm)
    ok("ADS-006 phễu quảng cáo", r.status_code == 200
       and r.json()["data"]["khach"] == 2)
    r = client.get(f"/api/v1/ads/{AD1}/lost-reasons", headers=hm)
    ok("ADS-008 lý do chưa chốt theo quảng cáo", r.status_code == 200
       and len(r.json()["data"]["items"]) >= 1)
    r = client.get(f"/api/v1/ads/{AD1}/health-report", headers=hm)
    ok("ADS-007 phiếu sức khỏe (phần số liệu)", r.status_code == 200
       and "phieu" in r.json()["data"])
    r = client.get("/api/v1/ads/tong-quan", headers=hm)
    ok("tổng quan quảng cáo (màn 7)", r.status_code == 200)
    r = client.get("/api/v1/ads", headers=hs)
    ok("Sale không có ads.view -> 403", r.status_code == 403)
    r = client.get(f"/api/v1/ads/{AD1}/health-report", headers=hs)
    ok("Sale xem phiếu sức khỏe -> 403", r.status_code == 403)

    r = client.post(f"/api/v1/customers/{kh[1]}/attributions", headers=hs,
                    json={"external_ad_id": AD1, "touch_type": "last"})
    ok("ATTRIBUTION-001 Sale gắn nguồn tay được (customer.edit)",
       r.status_code == 200, r.text[:200])
    r = client.get(f"/api/v1/customers/{kh[1]}/attributions", headers=hs)
    ok("ATTRIBUTION-002 xem nguồn của khách", r.status_code == 200
       and len(r.json()["data"]["items"]) >= 1)

    print("== 10. Màn Nguồn quảng cáo (7 + 53-55 + 56) ==")
    client.post("/dang-nhap", data={"username": f"{DAU}mkt", "password": MK})
    for cap, ten in (("campaign", "Chiến dịch"), ("ad_set", "Nhóm"), ("ad", "Quảng cáo")):
        r = client.get(f"/crm/quang-cao?cap={cap}&tu={tu}&den={den}")
        ok(f"tab {ten} trả HTML 200", r.status_code == 200 and "ROAS" in r.text,
           str(r.status_code))
    r = client.get(f"/crm/quang-cao/{AD1}")
    ok("phiếu sức khỏe 1 quảng cáo mở được",
       r.status_code == 200 and "Phễu quảng cáo" in r.text, str(r.status_code))
    r = client.get(f"/crm/quang-cao?cap=ad&tu={tu}&den={den}")
    ok("màn cảnh báo ad chưa có chi phí", "CHƯA có chi phí" in r.text)
    client.post("/dang-xuat")
    client.post("/dang-nhap", data={"username": f"{DAU}sale", "password": MK})
    r = client.get("/crm/quang-cao")
    ok("Sale mở màn Nguồn quảng cáo -> 403", r.status_code == 403)

    with pool.connection() as conn:
        don_dep(conn)

    print(f"\n=== KẾT QUẢ: {PASS} PASS · {FAIL} FAIL ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
