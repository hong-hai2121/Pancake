"""Luật bàn giao Sale → CSKH (B8 — FR-090/091, HANDOVER-001…006, màn 24-25).

FR-090 — TỰ ĐỘNG khi đơn giao thành công (hook trong order_service):
    gán CSKH (vòng tròn theo tải) · tạo vỏ hồ sơ chăm (care_plans, mốc CS01-11
    do B9 sinh) · chép thông tin liệu trình + hồ sơ tư vấn B5 vào phiếu ·
    tạo việc onboarding cho CSKH · tính ngày dự kiến bắt đầu (giao + 2 ngày,
    theo nhịp CS03 mục 14 BRD) · ghi Sale chốt. Idempotent: một đơn một phiếu
    (uq_handovers_order) — automation chạy lại không tạo trùng.

FR-091 — hồ sơ ĐỦ mới nhận: 8 trường bắt buộc (xem BAT_BUOC); thiếu trường
    nào ghi vào missing_fields + is_complete=false; CSKH trả lại Sale kèm lý
    do (sinh việc cho Sale bổ sung); Sale bổ sung đủ thì phiếu tự quay lại
    trạng thái 'assigned' chờ CSKH nhận.

Vòng đời phiếu: pending (chưa có CSKH) → assigned → accepted (CSKH đã nhận,
khách được phân công CSKH thật sự) · returned (trả lại Sale) → assigned.
'completed' để dành cho B9 (khi bắt đầu chăm thật).
"""

import sys
from datetime import datetime, timedelta, timezone

from app.core.errors import ApiError
from app.db.repositories import (
    audit_repo,
    customer_repo,
    handover_repo,
    order_repo,
    user_repo,
)

# Trạng thái đơn kích hoạt bàn giao. 'collected' (đã thu tiền COD) đứng SAU
# giao thành công trong đời đơn POS nên cũng tính — đơn nhảy thẳng tới đó
# (poll thưa) mà chỉ nghe 'delivered' là lọt phiếu.
KICH_HOAT = {"delivered", "collected"}

# FR-091 — 8 trường bắt buộc của phiếu (đúng thứ tự đặc tả):
# tình trạng khách · liệu trình · cách dùng · lưu ý · bệnh nền · thuốc đang
# dùng · băn khoăn · điều cần theo dõi
BAT_BUOC: dict[str, str] = {
    "customer_condition":  "Tình trạng khách",
    "treatment_summary":   "Liệu trình",
    "dose_text":           "Cách dùng",
    "notes":               "Lưu ý",
    "comorbidities":       "Bệnh nền",
    "current_medications": "Thuốc đang dùng",
    "concerns":            "Băn khoăn",
    "cskh_watch_points":   "Vấn đề CSKH cần theo dõi",
}

# Trường phiếu Sale/CSKH được sửa tay (màn 25) — ngoài 8 trường trên còn các
# trường kể-thêm không bắt buộc
SUA_DUOC = tuple(BAT_BUOC) + (
    "main_symptoms", "sale_discussed", "promises_made", "expected_start_date",
)


def _actor_id(actor: dict | None) -> int | None:
    try:
        return int((actor or {}).get("sub") or 0) or None
    except (TypeError, ValueError):
        return None


def _audit(actor, **kw) -> None:
    audit_repo.ghi(user_id=_actor_id(actor), object_type="handovers", **kw)


def _lay(handover_id: int) -> dict:
    row = handover_repo.get(handover_id)
    if not row:
        raise ApiError("NOT_FOUND", "Không tìm thấy phiếu bàn giao")
    return row


def _tinh_thieu(row: dict) -> list[str]:
    """Danh sách NHÃN trường còn trống (FR-091) — bày thẳng lên màn/API."""
    return [nhan for cot, nhan in BAT_BUOC.items()
            if not str(row.get(cot) or "").strip()]


def _cap_nhat_du_thieu(handover_id: int, row: dict) -> dict:
    thieu = _tinh_thieu(row)
    return handover_repo.update(handover_id, {
        "is_complete": not thieu, "missing_fields": thieu,
    })


# ------------------------------------------------------------------ FR-090
def tao_tu_don(order_id: int, *, actor: dict | None = None) -> dict:
    """HANDOVER-002 + automation FR-090. Idempotent — đơn đã có phiếu thì trả
    phiếu cũ, không tạo trùng, không đè dữ liệu ai đó đã sửa."""
    cu = handover_repo.get_by_order(order_id)
    if cu:
        return cu
    don = order_repo.get_order(order_id)
    if not don:
        raise ApiError("NOT_FOUND", "Không tìm thấy đơn hàng")
    if don["status"] not in KICH_HOAT:
        raise ApiError("CONFLICT",
                       f"Đơn đang '{don['status']}' — chỉ tạo bàn giao khi giao "
                       f"thành công ({'/'.join(sorted(KICH_HOAT))})")

    customer_id = don["customer_id"]

    # Sale chốt: người đang giữ vai sale của khách; không có thì chủ đơn.
    phu_trach = {a["assignment_type"]: a["user_id"]
                 for a in customer_repo.assignment_history(customer_id)
                 if a.get("end_at") is None}
    sale_id = phu_trach.get("sale") or don.get("sale_owner_id")

    # CSKH: đang có người giữ vai thì giữ nguyên; chưa có thì chia vòng tròn
    # theo tải. Không tìm được ai -> phiếu 'pending' chờ gán tay (HANDOVER-006).
    cskh_id = phu_trach.get("cskh")
    if not cskh_id:
        it_viec = handover_repo.cskh_it_viec()
        cskh_id = it_viec["id"] if it_viec else None

    # Chép thông tin liệu trình (FR-090) + mồi từ hồ sơ tư vấn B5
    lt = handover_repo.lieu_trinh_cua_don(order_id, customer_id)
    tu_van = handover_repo.du_lieu_tu_van(customer_id)
    moc_giao = don.get("delivered_at")

    care_plan = handover_repo.create_care_plan(
        customer_id=customer_id,
        customer_treatment_id=lt["id"] if lt else None,
        owner_id=cskh_id,
    )
    # B9 (AU03): sinh mốc mở màn CS01 + CS02 cho kế hoạch vừa tạo — luồng bồi,
    # lỗi không được phá bàn giao (mốc thiếu thì CARE-004 sinh lại được)
    try:
        from app.services import care_service

        care_service.khoi_tao_moc(care_plan["id"])
    except Exception:  # noqa: BLE001
        pass
    phieu = handover_repo.create({
        "customer_id": customer_id,
        "order_id": order_id,
        "customer_treatment_id": lt["id"] if lt else None,
        "care_plan_id": care_plan["id"],
        "sale_user_id": sale_id,
        "cskh_user_id": cskh_id,
        "status": "assigned" if cskh_id else "pending",
        "treatment_summary": (lt or {}).get("template_name"),
        "dose_text": handover_repo.cach_dung_lieu_trinh(lt["id"]) if lt else None,
        "main_symptoms": tu_van["main_symptoms"] or None,
        "current_medications": tu_van["current_medications"] or None,
        "comorbidities": tu_van["comorbidities"] or None,
        # ngày dự kiến bắt đầu = giao + 2 ngày (CS03 mục 14 BRD); chưa có mốc
        # giao thật (đơn tay vừa chuyển) thì để trống, Sale/CSKH điền
        "expected_start_date": (moc_giao + timedelta(days=2)).date()
                               if moc_giao else None,
    })
    if phieu is None:   # automation đua nhau — dòng kia thắng, dùng của họ
        return handover_repo.get_by_order(order_id)
    phieu = _cap_nhat_du_thieu(phieu["id"], phieu)

    # Việc onboarding cho CSKH (FR-090) — task engine B4, đủ owner + hạn
    if cskh_id:
        try:
            from app.services import task_service

            task_service.create_task({
                "title": f"Onboarding khách mới bàn giao (đơn #{order_id})",
                "task_type": "cham_soc",
                "assigned_to": cskh_id,
                "due_at": (moc_giao + timedelta(days=1)) if moc_giao else None,
                "customer_id": customer_id,
                "related_type": "order", "related_id": order_id,
            }, actor=actor)
        except Exception as err:  # noqa: BLE001 — thiếu việc không được chặn phiếu
            print(f"[handover] không tạo được việc onboarding: {err}",
                  file=sys.stderr)

    _audit(actor, action="handover_create", object_id=phieu["id"],
           new_value={"order_id": order_id, "cskh_user_id": cskh_id,
                      "status": phieu["status"],
                      "is_complete": phieu["is_complete"]})
    return phieu


def hook_giao_thanh_cong(order_id: int) -> None:
    """Gọi từ order_service.change_status — TỰ NUỐT lỗi: bàn giao là luồng
    bồi, không được làm vỡ chuyển trạng thái đơn/đồng bộ POS."""
    try:
        tao_tu_don(order_id)
    except ApiError as err:
        # CONFLICT khi automation chạy 2 lần là chuyện thường — im lặng
        if err.code != "CONFLICT":
            print(f"[handover] hook đơn {order_id}: {err.message}", file=sys.stderr)
    except Exception as err:  # noqa: BLE001
        print(f"[handover] hook đơn {order_id}: {type(err).__name__}: {err}",
              file=sys.stderr)


# ------------------------------------------------------------------ đọc
def danh_sach(**kw) -> tuple[list[dict], int]:
    """HANDOVER-001 / màn 24."""
    return handover_repo.list_handovers(**kw)


def chi_tiet(handover_id: int) -> dict:
    """HANDOVER-003 / màn 25 — kèm nhãn trường thiếu để màn tô đỏ."""
    row = _lay(handover_id)
    row["thieu"] = _tinh_thieu(row)
    return row


# ------------------------------------------------------------------ FR-091
def cap_nhat_phieu(handover_id: int, data: dict,
                   *, actor: dict | None = None) -> dict:
    """Sale (bổ sung) / CSKH (ghi nhận thêm) sửa nội dung phiếu — màn 25.

    Phiếu 'returned' mà bổ sung ĐỦ 8 trường thì tự quay lại 'assigned' chờ
    CSKH nhận — Sale khỏi cần thao tác riêng."""
    phieu = _lay(handover_id)
    doi = {k: v for k, v in data.items()
           if k in SUA_DUOC and v is not None}
    if not doi:
        raise ApiError("VALIDATION_ERROR",
                       "Không có trường hợp lệ nào để sửa",
                       errors={"fields": f"chỉ nhận: {', '.join(SUA_DUOC)}"})
    moi = handover_repo.update(handover_id, doi)
    moi = _cap_nhat_du_thieu(handover_id, moi)
    if phieu["status"] == "returned" and moi["is_complete"]:
        moi = handover_repo.update(handover_id, {"status": "assigned"})
    _audit(actor, action="handover_update", object_id=handover_id,
           old_value={k: phieu.get(k) for k in doi},
           new_value={**doi, "is_complete": moi["is_complete"]})
    return moi


def nhan(handover_id: int, *, actor: dict | None = None) -> dict:
    """HANDOVER-004 — CSKH nhận bàn giao. Luật FR-091: hồ sơ THIẾU không nhận
    được (trả lại Sale hoặc chờ bổ sung). Nhận xong khách chính thức thuộc
    CSKH này (customer_assignments vai 'cskh', giữ lịch sử)."""
    phieu = _lay(handover_id)
    if phieu["status"] not in ("pending", "assigned"):
        raise ApiError("CONFLICT", f"Phiếu đang '{phieu['status']}' — không nhận được")
    if not phieu.get("cskh_user_id"):
        raise ApiError("MISSING_REQUIRED_DATA",
                       "Phiếu chưa có CSKH — gán trước (HANDOVER-006)")
    thieu = _tinh_thieu(phieu)
    if thieu:
        raise ApiError("MISSING_REQUIRED_DATA",
                       "Hồ sơ bàn giao còn thiếu — bổ sung hoặc trả lại Sale",
                       errors={"thieu": thieu})

    nguoi_nhan = _actor_id(actor)
    # Người bấm nhận chính là CSKH trên phiếu (hoặc quản trị nhận hộ) — nếu
    # người khác bấm thì phiếu về tay người bấm, có audit.
    cskh_id = phieu["cskh_user_id"]
    if nguoi_nhan and nguoi_nhan != cskh_id and _la_cskh(nguoi_nhan):
        cskh_id = nguoi_nhan

    moi = handover_repo.update(handover_id, {
        "status": "accepted", "cskh_user_id": cskh_id,
        "accepted_at": datetime.now(timezone.utc),
    })
    customer_repo.assign(customer_id=phieu["customer_id"], user_id=cskh_id,
                         assignment_type="cskh")
    if phieu.get("care_plan_id"):
        handover_repo.set_care_plan_owner(phieu["care_plan_id"], cskh_id)
    _audit(actor, action="handover_accept", object_id=handover_id,
           old_value={"status": phieu["status"]},
           new_value={"status": "accepted", "cskh_user_id": cskh_id})
    return moi


def tra_lai(handover_id: int, reason: str, *, actor: dict | None = None) -> dict:
    """HANDOVER-005 — CSKH trả lại Sale bổ sung (FR-091), bắt buộc lý do;
    sinh việc cho Sale kèm danh sách trường thiếu."""
    if not (reason or "").strip():
        raise ApiError("MISSING_REQUIRED_DATA", "Trả lại phải ghi lý do")
    phieu = _lay(handover_id)
    if phieu["status"] not in ("pending", "assigned"):
        raise ApiError("CONFLICT", f"Phiếu đang '{phieu['status']}' — không trả được")
    moi = handover_repo.update(handover_id, {
        "status": "returned", "returned_reason": reason.strip(),
        "returned_at": datetime.now(timezone.utc),
    })
    if phieu.get("sale_user_id"):
        try:
            from app.services import task_service

            thieu = ", ".join(_tinh_thieu(phieu)) or "xem lý do"
            task_service.create_task({
                "title": f"Bổ sung phiếu bàn giao #{handover_id} (thiếu: {thieu})",
                "task_type": "xu_ly_su_co",
                "assigned_to": phieu["sale_user_id"],
                "due_at": datetime.now(timezone.utc) + timedelta(days=1),
                "customer_id": phieu["customer_id"],
            }, actor=actor)
        except Exception as err:  # noqa: BLE001
            print(f"[handover] không tạo được việc bổ sung: {err}", file=sys.stderr)
    _audit(actor, action="handover_return", object_id=handover_id,
           old_value={"status": phieu["status"]},
           new_value={"status": "returned"}, reason=reason.strip())
    return moi


def gan_cskh(handover_id: int, user_id: int, *, actor: dict | None = None) -> dict:
    """HANDOVER-006 — gán/đổi CSKH cho phiếu (trưởng nhóm dùng khi vòng tròn
    chia không hợp: nghỉ phép, quá tải...)."""
    phieu = _lay(handover_id)
    if phieu["status"] == "accepted":
        raise ApiError("CONFLICT",
                       "Phiếu đã nhận xong — đổi người phụ trách khách thì dùng "
                       "chuyển khách (A5), không sửa phiếu cũ")
    nv = user_repo.get_user(user_id)
    if not nv:
        raise ApiError("NOT_FOUND", "Không tìm thấy nhân viên")
    if nv.get("status") != "active":
        raise ApiError("CONFLICT", "Nhân viên không còn hoạt động — không gán được")
    moi = handover_repo.update(handover_id, {
        "cskh_user_id": user_id,
        "status": "assigned" if phieu["status"] == "pending" else phieu["status"],
    })
    if phieu.get("care_plan_id"):
        handover_repo.set_care_plan_owner(phieu["care_plan_id"], user_id)
    _audit(actor, action="handover_assign", object_id=handover_id,
           old_value={"cskh_user_id": phieu.get("cskh_user_id")},
           new_value={"cskh_user_id": user_id})
    return moi


def _la_cskh(user_id: int) -> bool:
    nv = user_repo.get_user(user_id)
    return bool(nv) and (nv.get("role_name") or "") == "CSKH"
