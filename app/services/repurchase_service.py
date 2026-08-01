"""Nghiệp vụ mua lại & khách ngủ (B10 — FR-120…123, BRD mục 13).

Chốt thiết kế:
  * FR-122 kể 9 trạng thái nhưng phần lớn là TRẠNG THÁI THEO THỜI GIAN
    (chưa/sắp/đến hạn/quá hạn/khách ngủ) — suy từ `expected_close_date` lúc
    đọc chứ KHÔNG lưu cột, khỏi cần job chạy đêm; cột `stage` chỉ giữ bước
    do NGƯỜI làm (identified → contacted → negotiating → won/lost/postponed).
  * FR-120 — ngày dự kiến hết = ngày bắt đầu THẬT (care plan B9, rớt xuống
    start_date/ngày giao) + số ngày dùng (mẫu liệu trình hoặc số lượng × ngày
    mỗi đơn vị) × hệ số tuân thủ (thiếu liều kéo dài) + tạm dừng + hàng cũ.
  * Cơ hội sinh TỰ ĐỘNG từ phiếu ngày 20 (B9/AU08); ở đây thêm tạo tay,
    và đơn GIAO THÀNH CÔNG tự chốt won + đánh dấu chuyển đổi chiến dịch
    (đo doanh thu tái kích hoạt không chờ tay).
  * Khách ngủ (FR-123): từng mua mà im ắng ≥ 30/60/90/180 ngày, lọc theo
    tổng giá trị mua; loại khách do_not_contact (AU11).
"""

from datetime import date, datetime, timedelta

from app.core.errors import ApiError
from app.db.repositories import audit_repo, care_repo, repurchase_repo

# Bước do người làm (stage DB). Đóng: won / lost.
TRANSITIONS: dict[str, set[str]] = {
    "identified":  {"contacted", "negotiating", "won", "lost", "postponed"},
    "contacted":   {"negotiating", "won", "lost", "postponed"},
    "negotiating": {"won", "lost", "postponed"},
    "postponed":   {"contacted", "negotiating", "won", "lost"},
}

# Hệ số kéo dài theo mức tuân thủ (FR-120 "dùng thiếu liều")
_HE_SO_TUAN_THU = {"Đúng đủ": 1.0, "Thiếu liều": 1.25, "Ngắt quãng": 1.5}

# Nhãn 9 trạng thái hiển thị (FR-122) — thứ tự này cũng là thứ tự cột màn 40
NHAN_HIEN_THI = [
    ("chua_den_han", "Chưa đến hạn"), ("sap_den_han", "Sắp đến hạn"),
    ("den_han", "Đến hạn"), ("dang_tu_van", "Đang tư vấn"),
    ("cho_quyet_dinh", "Chờ quyết định"), ("qua_han", "Quá hạn"),
    ("khach_ngu", "Khách ngủ"), ("da_mua", "Đã mua"), ("chua_mua", "Chưa mua"),
]
_TEN_NHAN = dict(NHAN_HIEN_THI)


def _actor_id(actor: dict | None) -> int | None:
    return int(actor["sub"]) if actor and actor.get("sub") else None


def _audit(actor, **kw) -> None:
    kw.setdefault("object_type", "repurchase_opportunities")
    audit_repo.ghi(user_id=_actor_id(actor), **kw)


def _ep_date(v) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError as err:
        raise ApiError("VALIDATION_ERROR",
                       f"Ngày không hợp lệ: {v} (cần YYYY-MM-DD)") from err


def _lay(opportunity_id: int) -> dict:
    opp = repurchase_repo.get(opportunity_id)
    if not opp:
        raise ApiError("NOT_FOUND", "Không tìm thấy cơ hội mua lại")
    return opp


def trang_thai_hien_thi(opp: dict) -> tuple[str, str]:
    """FR-122 — nhãn suy từ stage + expected_close_date (không lưu cột)."""
    stage = opp["stage"]
    if stage == "won":
        return "da_mua", _TEN_NHAN["da_mua"]
    if stage == "lost":
        return "chua_mua", _TEN_NHAN["chua_mua"]
    if stage == "contacted":
        return "dang_tu_van", _TEN_NHAN["dang_tu_van"]
    if stage == "negotiating":
        return "cho_quyet_dinh", _TEN_NHAN["cho_quyet_dinh"]
    # identified / postponed — nhìn theo lịch
    d = opp.get("expected_close_date")
    if not d:
        return "chua_den_han", _TEN_NHAN["chua_den_han"]
    lech = (_ep_date(d) - date.today()).days
    if lech > 7:
        return "chua_den_han", _TEN_NHAN["chua_den_han"]
    if lech > 0:
        return "sap_den_han", _TEN_NHAN["sap_den_han"]
    if lech == 0:
        return "den_han", _TEN_NHAN["den_han"]
    if lech >= -30:
        return "qua_han", _TEN_NHAN["qua_han"]
    return "khach_ngu", _TEN_NHAN["khach_ngu"]


def _gan_nhan(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["display_state"], r["display_label"] = trang_thai_hien_thi(r)
    return rows


# ============================================================ REPURCHASE-001…006
def danh_sach(**loc) -> tuple[list[dict], int]:
    """REPURCHASE-001 — mỗi dòng kèm nhãn hiển thị FR-122."""
    nhan = loc.pop("nhan", "")
    rows, total = repurchase_repo.list_opps(**loc)
    rows = _gan_nhan(rows)
    if nhan:                       # lọc theo nhãn suy ra — lọc sau khi gắn
        rows = [r for r in rows if r["display_state"] == nhan]
        total = len(rows)
    return rows, total


def chi_tiet(opportunity_id: int) -> dict:
    """REPURCHASE-002."""
    return _gan_nhan([_lay(opportunity_id)])[0]


def tao(data: dict, *, actor: dict | None = None) -> dict:
    """REPURCHASE-003 — FR-121. Luật: khách ngừng liên hệ không mở cơ hội;
    1 khách chỉ 1 cơ hội đang mở (đường tự động CS07 cũng giữ luật này)."""
    customer_id = int(data.get("customer_id") or 0)
    khach = care_repo.get_customer(customer_id)
    if not khach:
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    if khach.get("do_not_contact"):
        raise ApiError("CONFLICT",
                       "Khách đã yêu cầu ngừng liên hệ — không mở cơ hội (AU11)")
    if care_repo.co_hoi_dang_mo(customer_id):
        raise ApiError("CONFLICT", "Khách đang có cơ hội mua lại chưa đóng")
    _kiem_readiness(data.get("readiness"))
    if data.get("expected_value") is not None and float(data["expected_value"]) < 0:
        raise ApiError("VALIDATION_ERROR", "Giá trị dự kiến không âm")
    opp = repurchase_repo.create(data)
    _audit(actor, action="repurchase_create", object_id=opp["id"],
           new_value={"customer_id": customer_id})
    return chi_tiet(opp["id"])


def cap_nhat(opportunity_id: int, data: dict, *, actor: dict | None = None) -> dict:
    """REPURCHASE-004 — sửa phiếu FR-121 (liệu trình tiếp, giá trị, sẵn sàng,
    người phụ trách); ĐÓNG rồi thì khoá."""
    opp = _lay(opportunity_id)
    if opp["stage"] in ("won", "lost"):
        raise ApiError("CONFLICT", "Cơ hội đã đóng — không sửa được")
    _kiem_readiness(data.get("readiness"))
    repurchase_repo.update(opportunity_id,
                           **{k: v for k, v in data.items() if v is not None})
    _audit(actor, action="repurchase_update", object_id=opportunity_id,
           new_value={k: str(v)[:80] for k, v in data.items() if v is not None})
    return chi_tiet(opportunity_id)


def chuyen_stage(
    opportunity_id: int, stage: str, *, reason: str = "",
    actor: dict | None = None,
) -> dict:
    """REPURCHASE-005 — theo TRANSITIONS; 'lost' bắt buộc lý do (FR-122/
    tiêu chí 'ngày 25 chưa mua bắt buộc có lý do' áp cả pipeline này)."""
    opp = _lay(opportunity_id)
    duoc = TRANSITIONS.get(opp["stage"], set())
    if stage not in duoc:
        raise ApiError(
            "CONFLICT",
            f"Không chuyển được {opp['stage']} → {stage}; hợp lệ: "
            + (", ".join(sorted(duoc)) or "không còn (đã đóng)"),
        )
    if stage == "lost" and not (reason or "").strip() \
            and not opp.get("lost_reason_id") and not opp.get("lost_note"):
        raise ApiError("MISSING_REQUIRED_DATA",
                       "Chuyển 'Chưa mua/mất' phải kèm lý do (REPURCHASE-006)")
    if stage == "lost" and (reason or "").strip():
        _ghi_ly_do_tho(opportunity_id, reason.strip())
    kq = repurchase_repo.move_stage(opportunity_id, stage)
    if stage == "won":
        repurchase_repo.danh_dau_chuyen_doi(opp["customer_id"])
    _audit(actor, action="repurchase_move_stage", object_id=opportunity_id,
           old_value={"stage": opp["stage"]}, new_value={"stage": stage},
           reason=reason or None)
    return _gan_nhan([repurchase_repo.get(opportunity_id) or kq])[0]


def ghi_ly_do(
    opportunity_id: int, *, ma_ly_do: str = "", note: str = "",
    actor: dict | None = None,
) -> dict:
    """REPURCHASE-006 — lý do CHUẨN theo 9 mã BRD (lead_reasons) + diễn giải;
    cơ hội đang mở thì tự chuyển 'lost' luôn."""
    opp = _lay(opportunity_id)
    if not (ma_ly_do or "").strip() and not (note or "").strip():
        raise ApiError("MISSING_REQUIRED_DATA",
                       "Cần mã lý do chuẩn (ma_ly_do) hoặc diễn giải (note)")
    ly_do_id = None
    if ma_ly_do:
        ly_do = repurchase_repo.ly_do_chuan(ma_ly_do.strip())
        if not ly_do:
            raise ApiError("VALIDATION_ERROR",
                           f"Mã lý do '{ma_ly_do}' không có trong danh mục "
                           "(lead_reasons — 9 lý do BRD)")
        ly_do_id = ly_do["id"]
    repurchase_repo.update(opportunity_id, lost_reason_id=ly_do_id,
                           lost_note=note.strip() or None)
    if opp["stage"] not in ("won", "lost"):
        repurchase_repo.move_stage(opportunity_id, "lost")
    _audit(actor, action="repurchase_lost_reason", object_id=opportunity_id,
           new_value={"ma_ly_do": ma_ly_do or None, "note": note[:120] or None})
    return chi_tiet(opportunity_id)


def _ghi_ly_do_tho(opportunity_id: int, reason: str) -> None:
    ly_do = repurchase_repo.ly_do_chuan(reason)
    repurchase_repo.update(
        opportunity_id,
        lost_reason_id=ly_do["id"] if ly_do else None,
        lost_note=None if ly_do else reason,
    )


def _kiem_readiness(v) -> None:
    if v in (None, ""):
        return
    hop_le = care_repo.bo_gia_tri("repurchase_readiness")
    if hop_le and v not in hop_le:
        raise ApiError("VALIDATION_ERROR",
                       "readiness thuộc bộ: " + " · ".join(hop_le))


# ============================================================ REPURCHASE-007 (FR-120)
def tinh_ngay_het(
    customer_treatment_id: int, dieu_chinh: dict | None = None,
    *, actor: dict | None = None,
) -> dict:
    """FR-120 — ngày dự kiến hết, minh bạch từng khoản cộng/trừ:

        bắt đầu  = ngày bắt đầu THẬT (care plan B9) → start_date → ngày giao
        số ngày  = so_luong × so_ngay_moi_don_vi (nếu đưa) → duration_days mẫu
        hệ số    = tuân thủ mới nhất từ phiếu chăm (Thiếu liều ×1.25 · Ngắt
                   quãng ×1.5) — ghi đè bằng dieu_chinh['adherence_level']
        cộng     = tạm dừng (ngày) + còn hàng cũ (ngày)

    Kết quả LƯU vào customer_treatments.expected_end_date và đồng bộ sang
    cơ hội đang mở của khách (nguồn số màn 39-40 + thông báo đến hạn)."""
    dc = dieu_chinh or {}
    lt = repurchase_repo.lieu_trinh(customer_treatment_id)
    if not lt:
        raise ApiError("NOT_FOUND", "Không tìm thấy liệu trình của khách")

    bat_dau = (dc.get("start_date") or lt.get("care_start_date")
               or lt.get("start_date") or lt.get("delivered_at"))
    if not bat_dau:
        raise ApiError("MISSING_REQUIRED_DATA",
                       "Chưa biết ngày bắt đầu — ghi phiếu CS03 (B9) hoặc "
                       "truyền start_date")
    bat_dau = _ep_date(bat_dau)

    if dc.get("so_luong") and dc.get("so_ngay_moi_don_vi"):
        so_ngay = float(dc["so_luong"]) * float(dc["so_ngay_moi_don_vi"])
    elif dc.get("so_ngay"):
        so_ngay = float(dc["so_ngay"])
    elif lt.get("duration_days"):
        so_ngay = float(lt["duration_days"])
    else:
        raise ApiError("MISSING_REQUIRED_DATA",
                       "Mẫu liệu trình chưa có số ngày — truyền so_ngay hoặc "
                       "so_luong + so_ngay_moi_don_vi")

    tuan_thu = dc.get("adherence_level") \
        or repurchase_repo.adherence_gan_nhat(lt["customer_id"])
    if tuan_thu == "Chưa dùng":
        raise ApiError("CONFLICT",
                       "Khách CHƯA dùng — chưa có gì để tính ngày hết "
                       "(xử lý ở phiếu CS03 trước)")
    he_so = _HE_SO_TUAN_THU.get(tuan_thu or "Đúng đủ", 1.0)

    tam_dung = int(dc.get("tam_dung_ngay") or 0)
    hang_cu = int(dc.get("con_hang_cu_ngay") or 0)
    tong_ngay = round(so_ngay * he_so) + tam_dung + hang_cu
    ngay_het = bat_dau + timedelta(days=tong_ngay)

    repurchase_repo.luu_ngay_het(customer_treatment_id, ngay_het)
    repurchase_repo.dong_bo_ngay_het_sang_co_hoi(lt["customer_id"], ngay_het)
    _audit(actor, action="repurchase_calc_end_date",
           object_type="customer_treatments", object_id=customer_treatment_id,
           new_value={"ngay_het": str(ngay_het), "so_ngay": so_ngay,
                      "he_so": he_so, "tam_dung": tam_dung, "hang_cu": hang_cu})
    return {
        "customer_treatment_id": customer_treatment_id,
        "start_date": str(bat_dau), "base_days": so_ngay,
        "adherence_level": tuan_thu or "Đúng đủ", "factor": he_so,
        "paused_days": tam_dung, "leftover_days": hang_cu,
        "expected_end_date": str(ngay_het),
    }


# ============================================================ REPURCHASE-008…010
def sap_den_han(trong_ngay: int = 7, owner_id: int | None = None) -> list[dict]:
    """REPURCHASE-008 — mặc định cửa sổ 7 ngày."""
    return _gan_nhan(repurchase_repo.sap_den_han(trong_ngay, owner_id))


def qua_han(owner_id: int | None = None) -> list[dict]:
    """REPURCHASE-009."""
    return _gan_nhan(repurchase_repo.qua_han(owner_id))


NGUONG_NGU = (30, 60, 90, 180)   # FR-123 — luật cấu hình chuẩn BRD


def khach_ngu(tu_ngay: int = 30, gia_tri_tu=None) -> dict:
    """REPURCHASE-010 — trả kèm chia RỔ 30-59 / 60-89 / 90-179 / 180+ để màn
    41 vẽ thẳng, khỏi query 4 lần."""
    if tu_ngay < 1:
        raise ApiError("VALIDATION_ERROR", "tu_ngay phải >= 1")
    rows = repurchase_repo.khach_ngu(tu_ngay, gia_tri_tu=gia_tri_tu)
    ro: dict[str, list] = {"30": [], "60": [], "90": [], "180": []}
    for r in rows:
        n = r["ngay_ngu"]
        if n >= 180:
            ro["180"].append(r)
        elif n >= 90:
            ro["90"].append(r)
        elif n >= 60:
            ro["60"].append(r)
        else:
            ro["30"].append(r)
    return {"items": rows, "buckets": {k: len(v) for k, v in ro.items()},
            "ro": ro}


# ============================================================ chiến dịch (FR-123)
def gan_chien_dich(
    *, campaign_id: int | None = None, ten_moi: str = "",
    customer_ids: list[int], assigned_to: int | None = None,
    tao_viec: bool = True, actor: dict | None = None,
) -> dict:
    """FR-123 'gán chiến dịch + tạo nhiệm vụ': đưa khách ngủ vào chiến dịch
    (chọn sẵn hoặc đặt tên tạo mới), mỗi khách một việc `mua_lai` cho người
    được giao. Khách do_not_contact bị loại từng người, không vỡ cả mẻ."""
    if not customer_ids:
        raise ApiError("MISSING_REQUIRED_DATA", "Chưa chọn khách nào")
    if campaign_id:
        cd = repurchase_repo.get_chien_dich(campaign_id)
        if not cd:
            raise ApiError("NOT_FOUND", "Không tìm thấy chiến dịch")
    elif (ten_moi or "").strip():
        cd = repurchase_repo.tao_chien_dich(
            name=ten_moi.strip(),
            segment_rule={"nguon": "khach_ngu", "chon_tay": True})
    else:
        raise ApiError("MISSING_REQUIRED_DATA",
                       "Chọn chiến dịch có sẵn hoặc đặt tên chiến dịch mới")

    them, bo_qua = 0, 0
    for kh_id in customer_ids:
        khach = care_repo.get_customer(int(kh_id))
        if not khach or khach.get("do_not_contact"):
            bo_qua += 1
            continue
        dong = repurchase_repo.them_thanh_vien(cd["id"], int(kh_id), assigned_to)
        if dong is None:            # đã nằm trong chiến dịch từ trước
            bo_qua += 1
            continue
        them += 1
        if tao_viec and assigned_to:
            _tao_viec_nuot_loi(assigned_to, int(kh_id), cd, actor)
    _audit(actor, action="reactivation_assign",
           object_type="reactivation_campaigns", object_id=cd["id"],
           new_value={"them": them, "bo_qua": bo_qua})
    return {"campaign": cd, "them": them, "bo_qua": bo_qua}


def _tao_viec_nuot_loi(assigned_to, customer_id, cd, actor) -> None:
    try:
        from app.services import task_service

        task_service.create_task({
            "task_type": "mua_lai", "assigned_to": assigned_to,
            "customer_id": customer_id,
            "title": f"Tái kích hoạt khách ngủ — chiến dịch {cd['name']}",
            "due_at": datetime.now().astimezone() + timedelta(days=2),
            "priority": "normal",
        }, actor=actor)
    except Exception:  # noqa: BLE001 — việc là luồng bồi
        pass


def bao_cao_chien_dich() -> list[dict]:
    """FR-123 'đo doanh thu tái kích hoạt' — mỗi chiến dịch: số khách, số đã
    chuyển đổi, doanh thu (đơn giao TC tạo SAU khi khách vào chiến dịch)."""
    return repurchase_repo.bao_cao_chien_dich()


# ============================================================ hook từ đơn hàng
def hook_don_giao_thanh_cong(customer_id: int) -> None:
    """Gọi từ order_service khi đơn giao thành công (cạnh hook bàn giao B8):
    (1) cơ hội đang mở của khách → 'won' (FR-122 'Đã mua' = có đơn mới);
    (2) khách thuộc chiến dịch tái kích hoạt đang chạy → member 'converted'.
    Nuốt lỗi — luồng bồi không được phá đồng bộ đơn."""
    try:
        opp = care_repo.co_hoi_dang_mo(customer_id)
        if opp:
            repurchase_repo.move_stage(opp["id"], "won")
            audit_repo.ghi(user_id=None, action="repurchase_won_auto",
                           object_type="repurchase_opportunities",
                           object_id=opp["id"],
                           reason="don giao thanh cong")
        repurchase_repo.danh_dau_chuyen_doi(customer_id)
    except Exception:  # noqa: BLE001
        pass
