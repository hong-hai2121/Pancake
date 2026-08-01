"""Nghiệp vụ báo cáo B11 — REPORT-001…011 (FR-170…173).

Luật xương sống FR-173:
  * MỌI con số trả ra đều kèm `metric` — bấm vào là gọi REPORT-010
    /reports/drill-down?metric=...&tu=...&den=...&user_id=... và danh sách
    chi tiết chạy trên CÙNG điều kiện lọc (sổ METRICS của report_repo).
  * Quyền theo vai trò: từng metric mang quyền riêng (doanh thu = revenue.view,
    quảng cáo = ads.view, còn lại customer.view) — drill-down kiểm từng cái.
  * REPORT-011 xuất Excel: thêm quyền `data.export` + audit (FR-181).

Kỳ mặc định: 30 ngày gần nhất; nhận `tu`/`den` dạng YYYY-MM-DD.
"""

import csv
import io
from datetime import date, datetime, time, timedelta

from app.core.errors import ApiError
from app.db.repositories import audit_repo, report_repo
from app.db.repositories.report_repo import METRICS


def _ky(tu: str = "", den: str = "") -> dict:
    """Chuẩn hoá kỳ lọc: [00:00 ngày `tu` … 23:59:59 ngày `den`]."""
    try:
        d_den = date.fromisoformat(den) if den else date.today()
        d_tu = date.fromisoformat(tu) if tu else d_den - timedelta(days=29)
    except ValueError as err:
        raise ApiError("VALIDATION_ERROR",
                       "tu/den phải dạng YYYY-MM-DD") from err
    if d_tu > d_den:
        raise ApiError("VALIDATION_ERROR", "Khoảng lọc ngược (tu > den)")
    return {
        "tu": datetime.combine(d_tu, time.min).astimezone(),
        "den": datetime.combine(d_den, time.max).astimezone(),
        "tu_str": str(d_tu), "den_str": str(d_den),
    }


def _co_quyen(user: dict | None, ma: str) -> bool:
    return bool(user) and ma in (user.get("perms") or [])


def _so(metric_code: str, ts: dict) -> float:
    return report_repo.tinh(METRICS[metric_code], ts)


def _ti_le(tu_so: float, mau_so: float) -> float | None:
    return round(tu_so * 100 / mau_so, 1) if mau_so else None


# ============================================================ REPORT-001
def dashboard(tu: str = "", den: str = "", *, user: dict | None = None) -> dict:
    """Màn 4 — chỉ số toàn công ty; ô doanh thu/chi phí chỉ trả cho người có
    quyền tương ứng (FR-173 'có quyền xem dữ liệu theo vai trò')."""
    ky = _ky(tu, den)
    ts = {"tu": ky["tu"], "den": ky["den"], "uid": None}
    so = {m: _so(m, ts) for m in (
        "lead_moi", "lead_chua_lien_he", "lead_qua_sla", "lead_tu_van",
        "lead_bao_gia", "lead_chot", "don_tao", "don_giao", "don_hoan",
        "viec_qua_han", "moc_den_han", "khach_phan_ung", "ban_giao_moi",
        "co_hoi_mo", "khach_moi", "hoi_thoai_moi",
    )}
    if _co_quyen(user, "revenue.view"):
        so["doanh_thu_giao"] = _so("doanh_thu_giao", ts)
        so["doanh_thu_mua_lai"] = _so("doanh_thu_mua_lai", ts)
    if _co_quyen(user, "ads.view"):
        so["chi_phi_qc"] = _so("chi_phi_qc", ts)
        if so.get("doanh_thu_giao") is not None and so["chi_phi_qc"]:
            so["roas"] = round(so["doanh_thu_giao"] / so["chi_phi_qc"], 2)
    ti_le = {
        "chot": _ti_le(so["lead_chot"], so["lead_moi"]),
        "giao_tc": _ti_le(so["don_giao"], so["don_tao"]),
        "lien_he": _ti_le(_so("lead_lien_he", ts), so["lead_moi"]),
    }
    return {"ky": {"tu": ky["tu_str"], "den": ky["den_str"]},
            "so": so, "ti_le": ti_le,
            "doanh_thu_theo_ngay": (report_repo.doanh_thu_theo_ngay(ts)
                                    if _co_quyen(user, "revenue.view") else []),
            "pheu": [{"buoc": b, "metric": m, "n": so.get(m, _so(m, ts))}
                     for b, m in (("Lead mới", "lead_moi"),
                                  ("Liên hệ được", "lead_lien_he"),
                                  ("Đã tư vấn", "lead_tu_van"),
                                  ("Đã báo giá", "lead_bao_gia"),
                                  ("Đã chốt", "lead_chot"),
                                  ("Giao thành công", "don_giao"))]}


# ============================================================ REPORT-002/003
def bao_cao_sale(tu: str = "", den: str = "") -> dict:
    """Màn 60 — mỗi Sale một dòng, tỷ lệ tính sẵn (FR-170)."""
    ky = _ky(tu, den)
    ts = {"tu": ky["tu"], "den": ky["den"]}
    rows = report_repo.theo_nhan_vien_sale(ts)
    for r in rows:
        r["tl_lien_he"] = _ti_le(r["lien_he"], r["lead_moi"])
        r["tl_tu_van"] = _ti_le(r["tu_van"], r["lead_moi"])
        r["tl_bao_gia"] = _ti_le(r["bao_gia"], r["lead_moi"])
        r["tl_chot"] = _ti_le(r["chot"], r["lead_moi"])
    return {"ky": {"tu": ky["tu_str"], "den": ky["den_str"]}, "rows": rows}


def bao_cao_cskh(tu: str = "", den: str = "") -> dict:
    """Màn 61 — mỗi CSKH một dòng (FR-171)."""
    ky = _ky(tu, den)
    ts = {"tu": ky["tu"], "den": ky["den"]}
    rows = report_repo.theo_nhan_vien_cskh(ts)
    for r in rows:
        r["tl_dung_han"] = _ti_le(r["moc_dung_han"], r["moc_xong"])
    return {"ky": {"tu": ky["tu_str"], "den": ky["den_str"]}, "rows": rows}


# ============================================================ REPORT-004…007
def bao_cao_marketing(tu: str = "", den: str = "") -> dict:
    """Màn 62 + FR-172 — chi phí · phễu · ROAS/LTV · lý do chưa chốt."""
    ky = _ky(tu, den)
    ts = {"tu": ky["tu"], "den": ky["den"], "uid": None}
    chi_phi = _so("chi_phi_qc", ts)
    doanh_thu = _so("doanh_thu_giao", ts)
    khach_mua = _khach_mua_trong_ky(ts)
    return {
        "ky": {"tu": ky["tu_str"], "den": ky["den_str"]},
        "so": {
            "chi_phi_qc": chi_phi,
            "hoi_thoai_moi": _so("hoi_thoai_moi", ts),
            "khach_moi": _so("khach_moi", ts),
            "lead_moi": _so("lead_moi", ts),
            "lead_chot": _so("lead_chot", ts),
            "don_giao": _so("don_giao", ts),
            "don_hoan": _so("don_hoan", ts),
            "doanh_thu_giao": doanh_thu,
            "roas": round(doanh_thu / chi_phi, 2) if chi_phi else None,
            "ltv": round(doanh_thu / khach_mua, 0) if khach_mua else None,
        },
        "ly_do_chua_chot": report_repo.ly_do_chua_chot(ts),
    }


def _khach_mua_trong_ky(ts: dict) -> int:
    from app.db.client import get_pg_pool

    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select count(distinct customer_id) as n from crm.orders "
            "where status = 'delivered' and delivered_at between %(tu)s and %(den)s",
            ts,
        ).fetchone()["n"]


def bao_cao_don_hang(tu: str = "", den: str = "") -> dict:
    """REPORT-005."""
    ky = _ky(tu, den)
    ts = {"tu": ky["tu"], "den": ky["den"]}
    return {"ky": {"tu": ky["tu_str"], "den": ky["den_str"]},
            "theo_trang_thai": report_repo.don_theo_trang_thai(ts)}


def bao_cao_doanh_thu(tu: str = "", den: str = "") -> dict:
    """REPORT-006 — chuỗi ngày + tổng, tách bán mới / mua lại."""
    ky = _ky(tu, den)
    ts = {"tu": ky["tu"], "den": ky["den"]}
    ngay = report_repo.doanh_thu_theo_ngay(ts)
    tong = sum(float(r["tong"]) for r in ngay)
    mua_lai = sum(float(r["mua_lai"]) for r in ngay)
    return {"ky": {"tu": ky["tu_str"], "den": ky["den_str"]},
            "theo_ngay": ngay,
            "tong": tong, "mua_lai": mua_lai, "ban_moi": tong - mua_lai}


def bao_cao_mua_lai(tu: str = "", den: str = "") -> dict:
    """REPORT-007 — cơ hội trong kỳ + chiến dịch tái kích hoạt."""
    from app.services import repurchase_service

    ky = _ky(tu, den)
    ts = {"tu": ky["tu"], "den": ky["den"], "uid": None}
    won = _so("co_hoi_won", ts)
    mo = _so("co_hoi_mo", ts)
    return {"ky": {"tu": ky["tu_str"], "den": ky["den_str"]},
            "so": {"co_hoi_mo": mo, "co_hoi_won": won,
                   "doanh_thu_mua_lai": _so("doanh_thu_mua_lai", ts),
                   "sap_den_han": len(repurchase_service.sap_den_han(7)),
                   "qua_han": len(repurchase_service.qua_han())},
            "chien_dich": repurchase_service.bao_cao_chien_dich()}


def bao_cao_cuoc_goi() -> dict:
    """REPORT-008 — tổng đài thuộc C-MVP3: trả khung trung thực, KHÔNG số ảo."""
    return {"available": False,
            "message": "Chưa nối tổng đài (C-MVP3) — có dữ liệu cuộc gọi "
                       "báo cáo này tự sống, endpoint giữ đúng đặc tả"}


def bao_cao_cong_viec(tu: str = "", den: str = "") -> dict:
    """REPORT-009 — việc theo loại (B4)."""
    ky = _ky(tu, den)
    ts = {"tu": ky["tu"], "den": ky["den"]}
    return {"ky": {"tu": ky["tu_str"], "den": ky["den_str"]},
            "theo_loai": report_repo.viec_theo_loai(ts)}


# ============================================================ REPORT-010/011
def drill_down(
    metric: str, tu: str = "", den: str = "", user_id: int | None = None,
    *, user: dict | None = None, limit: int = 200,
) -> dict:
    """FR-173 — mọi số bấm ra danh sách; CÙNG điều kiện với số tổng."""
    m = METRICS.get(metric)
    if not m:
        raise ApiError("VALIDATION_ERROR",
                       f"Không có metric '{metric}'. Có: " +
                       ", ".join(sorted(METRICS)))
    if not _co_quyen(user, m.quyen):
        raise ApiError("FORBIDDEN",
                       f"Metric này cần quyền {m.quyen} — liên hệ Admin")
    ky = _ky(tu, den)
    ts = {"tu": ky["tu"], "den": ky["den"], "uid": user_id}
    return {"metric": metric, "ten": m.ten,
            "ky": {"tu": ky["tu_str"], "den": ky["den_str"]},
            "user_id": user_id,
            "tong": report_repo.tinh(m, ts),
            "cot": m.cot,
            "rows": report_repo.rows(m, ts, limit=limit)}


def xuat_csv(
    metric: str, tu: str = "", den: str = "", user_id: int | None = None,
    *, user: dict | None = None,
) -> tuple[str, str]:
    """REPORT-011 — CSV BOM UTF-8 + chấm phẩy (Excel VN mở thẳng, cùng nếp
    xuất nhân viên A5); đòi thêm `data.export` + ghi audit (FR-181)."""
    if not _co_quyen(user, "data.export"):
        raise ApiError("FORBIDDEN", "Xuất dữ liệu cần quyền data.export (FR-181)")
    kq = drill_down(metric, tu, den, user_id, user=user, limit=5000)
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    if kq["rows"]:
        w.writerow(list(kq["rows"][0].keys()))
        for r in kq["rows"]:
            w.writerow([("" if v is None else v) for v in r.values()])
    else:
        w.writerow(["(không có dữ liệu trong kỳ)"])
    audit_repo.ghi(
        user_id=int(user["sub"]) if user and user.get("sub") else None,
        action="report_export", object_type="reports",
        new_value={"metric": metric, "tu": kq["ky"]["tu"], "den": kq["ky"]["den"],
                   "so_dong": len(kq["rows"])},
    )
    ten_file = f"bao-cao-{metric}-{kq['ky']['tu']}-{kq['ky']['den']}.csv"
    return "﻿" + out.getvalue(), ten_file


# ============================================================ dashboard Sale/CSKH (màn 5-6)
def dashboard_sale(user_id: int, tu: str = "", den: str = "") -> dict:
    """Màn 5 — số CỦA MỘT Sale (drill-down giữ user_id)."""
    ky = _ky(tu, den)
    ts = {"tu": ky["tu"], "den": ky["den"], "uid": user_id}
    so = {m: _so(m, ts) for m in (
        "lead_moi", "lead_chua_lien_he", "lead_nong", "lead_qua_sla",
        "lead_lien_he", "lead_tu_van", "lead_bao_gia", "lead_chot",
        "don_giao", "doanh_thu_giao", "viec_qua_han",
    )}
    return {"ky": {"tu": ky["tu_str"], "den": ky["den_str"]},
            "user_id": user_id, "so": so,
            "ti_le": {"lien_he": _ti_le(so["lead_lien_he"], so["lead_moi"]),
                      "tu_van": _ti_le(so["lead_tu_van"], so["lead_moi"]),
                      "bao_gia": _ti_le(so["lead_bao_gia"], so["lead_moi"]),
                      "chot": _ti_le(so["lead_chot"], so["lead_moi"])}}


def dashboard_cskh(user_id: int, tu: str = "", den: str = "") -> dict:
    """Màn 6 — số CỦA MỘT CSKH."""
    ky = _ky(tu, den)
    ts = {"tu": ky["tu"], "den": ky["den"], "uid": user_id}
    so = {m: _so(m, ts) for m in (
        "ban_giao_moi", "moc_den_han", "moc_hoan_thanh", "moc_dung_han",
        "khach_phan_ung", "viec_qua_han", "co_hoi_mo", "co_hoi_won",
        "doanh_thu_mua_lai",
    )}
    return {"ky": {"tu": ky["tu_str"], "den": ky["den_str"]},
            "user_id": user_id, "so": so,
            "ti_le": {"moc_dung_han": _ti_le(so["moc_dung_han"],
                                             so["moc_hoan_thanh"])}}
