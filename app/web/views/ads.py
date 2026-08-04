"""Dựng HTML màn NGUỒN QUẢNG CÁO (BRD mục 4 · màn 7 + 53-55 + phiếu 56).

Ba tab = ba cấp của cây quảng cáo (Chiến dịch · Nhóm · Quảng cáo), cùng một bộ
cột để so ngang được: Chi phí · Khách · Khách tiềm năng · Đơn · Giao TC · Doanh thu ·
ROAS · LTV.

Quy ước hiển thị quan trọng: ad chưa nối tài khoản quảng cáo vào POS thì KHÔNG có
chi phí — cột chi phí/ROAS hiện "—" (chưa biết), tuyệt đối không hiện 0 (biết là
bằng không). Một dải nhắc màu vàng đếm số ad như vậy nằm ngay đầu màn.
"""

from html import escape

from app.web.shell import flash, render_shell, stat, tabs_bar

_TABS = [
    ("/crm/quang-cao?cap=campaign", "Chiến dịch", "campaign"),
    ("/crm/quang-cao?cap=ad_set", "Nhóm quảng cáo", "ad_set"),
    ("/crm/quang-cao?cap=ad", "Quảng cáo", "ad"),
]


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _dt(v) -> str:
    return v.strftime("%d/%m %H:%M") if v else "—"


def _tien(v) -> str:
    """Tiền VND gọn: 1.546.961 -> '1.546.961'. Rỗng = chưa biết -> '—'."""
    if v in (None, ""):
        return "—"
    try:
        return f"{int(float(v)):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _so(v) -> str:
    return "—" if v in (None, "") else f"{int(v):,}".replace(",", ".")


def _roas(v) -> str:
    """ROAS: >=1 xanh (thu > chi), <1 đỏ. Rỗng = chưa có chi phí -> '—' xám."""
    if v in (None, ""):
        return '<span class="note" title="Chưa nối tài khoản quảng cáo vào POS">—</span>'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    lop = "ok" if f >= 1 else "err"
    return f'<span class="pill {lop}">{f:.2f}×</span>'


def render_quang_cao(
    cap: str, rows: list[dict], tong: dict, *, tu: str = "", den: str = "",
    ok: str = "", error: str = "",
) -> str:
    nhac = ""
    if tong.get("thieu_don_pos"):
        nhac += (
            '<div class="flash warn">⚠ Có chi phí nhưng CHƯA có doanh thu quy nguồn: '
            "đơn Pancake POS chưa đổ về CRM"
            + ("" if tong.get("pos_sync_enabled") else
               ' — <b>công tắc "Đổ đơn Pancake POS vào CRM" đang TẮT</b>'
               ' (<a href="/quan-tri/cai-dat">màn Cài đặt</a>)')
            + ". Bật công tắc đó (đơn mới) và chạy "
            "<code>scripts/backfill_don_pos.py</code> (đơn cũ) thì ROAS mới có nghĩa.</div>"
        )
    if tong.get("ad_thieu_chi_phi"):
        nhac = (
            '<div class="flash warn">⚠ '
            f'{tong["ad_thieu_chi_phi"]}/{tong["ad_co_doanh_thu"]} quảng cáo có đơn '
            "nhưng CHƯA có chi phí — tài khoản quảng cáo chạy các ad đó chưa được nối "
            "vào Pancake POS (POS → Ads Manager → thêm tài khoản). ROAS chỉ đúng trên "
            "phần đã nối.</div>"
        )

    o_so = (
        stat("Chi phí quảng cáo", _tien(tong.get("chi_phi")), f"{tu} → {den}")
        + stat("Doanh thu quy nguồn", _tien(tong.get("doanh_thu")),
               "đơn đã giao thành công")
        # ROAS = 0 là MỘT CON SỐ (tiêu tiền, chưa ra doanh thu) — phải hiện 0.00×,
        # khác hẳn "—" nghĩa là chưa biết chi phí. Nên so `is not None`, không so falsy.
        + stat("ROAS",
               f'{float(tong["roas"]):.2f}×' if tong.get("roas") is not None else "—",
               "doanh thu / chi phí",
               tone=("ok" if float(tong["roas"] or 0) >= 1 else "err")
               if tong.get("roas") is not None else "")
        + stat("Khách từ quảng cáo", _so(tong.get("so_khach") or 0),
               f"LTV {_tien(tong.get('ltv'))}")
        + stat("Đơn giao thành công", _so(tong.get("so_don_giao") or 0),
               f"{_so(tong.get('so_don') or 0)} đơn tổng")
        + stat("Quảng cáo đã đồng bộ", _so(tong.get("so_ad") or 0),
               f"{_so(tong.get('so_ad_co_chi_phi') or 0)} ad có chi phí")
    )

    cot_ten = {"campaign": "Chiến dịch", "ad_set": "Nhóm quảng cáo", "ad": "Quảng cáo"}[cap]
    dong = ""
    for r in rows:
        ma = r.get("external_ad_id") or r.get("external_id") or ""
        ten = r.get("name") or ma
        phu = ""
        if cap == "ad":
            phu = (r.get("campaign_name") or "") + \
                  (" · " + r["ad_set_name"] if r.get("ad_set_name") else "")
            if r.get("creative_name"):
                phu = phu or r["creative_name"][:80]
        link = (f'<a href="/crm/quang-cao/{escape(str(ma))}">{escape(str(ten))[:70]}</a>'
                if cap == "ad" else escape(str(ten))[:70])
        dong += (
            "<tr>"
            f"<td><b>{link}</b><div class=\"note\">{escape(str(ma))}"
            f"{' · ' + escape(phu[:70]) if phu else ''}</div></td>"
            f"<td class=\"num\">{_tien(r.get('chi_phi')) if not r.get('thieu_chi_phi') else '—'}</td>"
            f"<td class=\"num\">{_so(r.get('so_khach') or 0)}</td>"
            f"<td class=\"num\">{_so(r.get('so_lead') or 0)}</td>"
            f"<td class=\"num\">{_so(r.get('so_don') or 0)}</td>"
            f"<td class=\"num\">{_so(r.get('so_don_giao') or 0)}</td>"
            f"<td class=\"num\">{_tien(r.get('doanh_thu'))}</td>"
            f"<td class=\"num\">{_roas(r.get('roas'))}</td>"
            f"<td class=\"num\">{_tien(r.get('ltv'))}</td>"
            "</tr>"
        )

    body = f"""
{nhac}
<div class="stats">{o_so}</div>

<form class="card form" method="get" action="/crm/quang-cao" style="margin:14px 0">
  <input type="hidden" name="cap" value="{escape(cap)}">
  <div class="grid2">
    <label>Từ ngày<input type="date" name="tu" value="{escape(tu)}"></label>
    <label>Đến ngày<input type="date" name="den" value="{escape(den)}"></label>
    <label>&nbsp;<button class="btn primary">Xem</button></label>
  </div>
  <p class="note" style="margin-top:6px">Chi phí lọc theo NGÀY chạy quảng cáo, doanh thu
  lọc theo mốc khách được quy nguồn — cùng một kỳ nên ROAS so được.</p>
</form>

<div class="tblwrap card"><table class="tbl">
<thead><tr><th>{cot_ten}</th><th>Chi phí</th><th>Khách</th><th>Khách tiềm năng</th><th>Đơn</th>
<th>Giao TC</th><th>Doanh thu</th><th>ROAS</th><th>LTV</th></tr></thead>
<tbody>{dong or '<tr><td colspan="9">Chưa có dữ liệu trong kỳ — bật POS_SYNC_ENABLED để đơn về, và nối tài khoản quảng cáo vào POS để có chi phí</td></tr>'}</tbody>
</table></div>
"""
    return render_shell(
        "Nguồn quảng cáo", "crm-ads", flash(ok, error) + body,
        heading="Nguồn quảng cáo",
        sub="Màn 7 + 53-55 — đo quảng cáo bằng doanh thu thật (BRD mục 4)",
        tabs=tabs_bar(_TABS, cap),
    )


def render_chi_tiet_ad(data: dict, *, window: int = 30) -> str:
    """Phiếu sức khỏe 1 quảng cáo (màn 56, phần số liệu)."""
    ad = data.get("ad") or {}
    hq = data.get("hieu_qua") or {}
    ph = data.get("phieu") or {}
    ma = hq.get("external_ad_id") or ad.get("external_ad_id") or ""

    o_so = (
        stat(f"Chi phí {window} ngày", _tien(hq.get("chi_phi")))
        + stat("Doanh thu", _tien(hq.get("doanh_thu")), "đơn đã giao thành công")
        + stat("ROAS",
               f'{float(hq["roas"]):.2f}×' if hq.get("roas") is not None else "—",
               tone=("ok" if float(hq["roas"] or 0) >= 1 else "err")
               if hq.get("roas") is not None else "")
        + stat("LTV / khách", _tien(hq.get("ltv")), f'{_so(hq.get("so_khach") or 0)} khách')
    )

    buoc = [("Khách quy nguồn", ph.get("khach")),
            ("Thành khách tiềm năng", ph.get("lead")),
            ("Được tư vấn", ph.get("tu_van")), ("Có đơn", ph.get("co_don")),
            ("Giao thành công", ph.get("giao_thanh_cong")), ("Mua lại", ph.get("mua_lai"))]
    goc = max([b[1] or 0 for b in buoc] + [1])
    phieu_html = "".join(
        f'<tr><td>{escape(ten)}</td><td class="num">{_so(v or 0)}</td>'
        f'<td class="num">{round((v or 0) * 100 / goc)}%</td>'
        f'<td><div class="bar"><span style="width:{round((v or 0) * 100 / goc)}%"></span></div></td></tr>'
        for ten, v in buoc
    )

    ly_do = "".join(
        f"<tr><td>{_e(r['ly_do'])}</td><td>{_e(r['category'])}</td>"
        f'<td class="num">{r["so_lead"]}</td></tr>'
        for r in data.get("ly_do_chua_chot") or []
    )
    khach = "".join(
        f"<tr><td>{_e(k['full_name'])}</td><td>{_e(k['primary_phone'])}</td>"
        f"<td><span class='pill'>{_e(k['status'])}</span></td>"
        f"<td>{_dt(k['attributed_at'])}</td>"
        f'<td class="num">{_tien(k["doanh_thu"])}</td></tr>'
        for k in data.get("khach") or []
    )

    body = f"""
<p><a class="btn sm" href="/crm/quang-cao?cap=ad">← Danh sách quảng cáo</a></p>
<div class="card" style="margin-bottom:14px">
  <h3>{escape(str(ad.get('name') or ma))}</h3>
  <p class="note">Mã {escape(str(ma))}
  {' · ' + escape(str(ad.get('creative_name'))[:120]) if ad.get('creative_name') else ''}
  {' · bài viết ' + escape(str(ad.get('post_id'))) if ad.get('post_id') else ''}</p>
</div>
<div class="stats">{o_so}</div>

<div class="card" style="margin-top:14px">
  <h3>Phễu quảng cáo</h3>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Bước</th><th>Số khách</th><th>Tỷ lệ</th><th></th></tr></thead>
  <tbody>{phieu_html}</tbody></table></div>
</div>

<div class="card" style="margin-top:14px">
  <h3>Lý do chưa chốt</h3>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Lý do</th><th>Nhóm</th><th>Số khách tiềm năng</th></tr></thead>
  <tbody>{ly_do or '<tr><td colspan="3">Chưa có khách tiềm năng nào ghi lý do</td></tr>'}</tbody>
  </table></div>
</div>

<div class="card" style="margin-top:14px">
  <h3>Khách đến từ quảng cáo này</h3>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Khách</th><th>Điện thoại</th><th>Trạng thái</th><th>Quy nguồn lúc</th>
  <th>Doanh thu</th></tr></thead>
  <tbody>{khach or '<tr><td colspan="5">Chưa có khách nào</td></tr>'}</tbody>
  </table></div>
</div>
"""
    return render_shell(
        f"Quảng cáo {ma}", "crm-ads", body,
        heading="Phiếu sức khỏe quảng cáo",
        sub="Màn 56 — phễu, lý do chưa chốt và khách minh chứng",
    )
