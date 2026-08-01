"""Nghiệp vụ chăm sóc sau bán 11 bước (B9 — FR-100…110, BRD mục 14.3).

Xương sống:
  * Kế hoạch chăm (care_plans) do B8 tạo VỎ khi đơn giao thành công;
    ở đây sinh MỐC (care_plan_steps) và giữ luật từng bước CS01-CS11.
  * FR-102 — luật quan trọng nhất: mốc ngày 4/10/15/20/25 tính từ
    `actual_start_date` (ngày bắt đầu DÙNG THẬT, CS03 ghi), KHÔNG phải ngày
    giao. Chưa có ngày bắt đầu = CHƯA sinh mốc đánh giá.
  * Phiếu chăm (CARE-STEP-001…011): trường bắt buộc đọc từ ref_codes nhóm
    `care_step` (BRD bảng 18), giá trị chuẩn theo 7 bộ giá trị (bảng 19) —
    thêm/bớt trường là việc SEED danh mục, không phải sửa code.
  * Không gặp khách: phiếu gửi `contact_result` ≠ "Kết nối" chỉ ghi tương tác
    (contacted=false), KHÔNG bắt dữ liệu, KHÔNG đóng mốc; CS01 dồn 3 lần
    không gặp → báo Sale + quản lý (ngoại lệ FR-100 / AU02).
  * Khách yêu cầu ngừng liên hệ (NORESPONSE-004, AU11): cờ do_not_contact —
    mọi phiếu/worker/chuỗi bám đuổi phải dừng; pipeline về C09.

Pipeline CSKH C01-C09 (màn 27): C01 mới bàn giao → CS01 xong = C02 →
CS02 nhận đủ = C03 → CS03 bắt đầu dùng = C04 → phản ứng/nặng = C05 →
ngày 20 = C06 → mua lại = C07 → 4 lần không phản hồi = C08 → dừng = C09.
"""

from datetime import date, datetime, time, timedelta, timezone

from app.core.errors import ApiError
from app.db.repositories import audit_repo, care_repo

# Mốc theo NGÀY DÙNG THẬT (FR-102). CS09 = ngày 28, chỉ sinh khi CS08 chưa chốt.
MOC_NGAY: dict[str, int] = {"CS04": 4, "CS05": 10, "CS06": 15, "CS07": 20, "CS08": 25}
_GIO_HEN = 9  # mốc hẹn 9h sáng giờ máy chủ

# 7 bộ giá trị phiếu chăm (BRD bảng 19) — key trùng tên trường là validate
_BO_GIA_TRI = ("adherence_level", "diet_compliance", "adverse_event",
               "bowel_status", "repurchase_readiness", "contact_result",
               "next_action")

# Giá trị chuẩn vài trường phiếu KHÔNG nằm trong 7 bộ (mã ASCII cho form web)
RECEIVED_STATUS = {"du_hang": "Đủ hàng", "thieu_loi": "Thiếu/lỗi hàng",
                   "chua_nhan": "Chưa nhận"}
REPURCHASE_STATUS = {"da_mua": "Đã mua", "hen_mua": "Hẹn mua",
                     "chua_mua": "Chưa mua", "tu_choi": "Từ chối"}
# Thứ tự kênh chuỗi không phản hồi (FR-110): nhắn → gọi → nhắn → gọi
_KENH_CHUOI = {1: "message", 2: "call", 3: "message", 4: "call"}

_DA_XONG = ("done", "skipped")


def _actor_id(actor: dict | None) -> int | None:
    return int(actor["sub"]) if actor and actor.get("sub") else None


def _audit(actor: dict | None, **kw) -> None:
    audit_repo.ghi(user_id=_actor_id(actor), **kw)


def _hen(ngay: date) -> datetime:
    """date → mốc hẹn 9h sáng (timezone máy chủ, tsvới DB timestamptz)."""
    return datetime.combine(ngay, time(_GIO_HEN)).astimezone()


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


def _lay_plan(plan_id: int) -> dict:
    plan = care_repo.get_plan(plan_id)
    if not plan:
        raise ApiError("NOT_FOUND", "Không tìm thấy kế hoạch chăm")
    return plan


def _lay_moc(step_id: int) -> dict:
    step = care_repo.get_step(step_id)
    if not step:
        raise ApiError("NOT_FOUND", "Không tìm thấy mốc chăm")
    return step


def _doi_state(plan_id: int, state: str) -> None:
    """Đổi cột pipeline CSKH — chỉ nhận mã có trong danh mục cskh_state."""
    if state in care_repo.ma_hop_le("cskh_state"):
        care_repo.update_plan(plan_id, cskh_state=state)


# ============================================================ kế hoạch (CARE-001…005)
def danh_sach(**loc) -> tuple[list[dict], int]:
    """CARE-001."""
    return care_repo.list_plans(**loc)


def chi_tiet(plan_id: int) -> dict:
    """CARE-002 — kèm danh sách mốc."""
    plan = _lay_plan(plan_id)
    plan["steps"] = care_repo.list_steps(plan_id)
    return plan


def tao_ke_hoach(data: dict, *, actor: dict | None = None) -> dict:
    """CARE-003 — tạo tay (đường thường là B8 tự tạo khi giao thành công).
    Luật: 1 khách chỉ 1 kế hoạch đang chạy."""
    customer_id = int(data.get("customer_id") or 0)
    khach = care_repo.get_customer(customer_id)
    if not khach:
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    if care_repo.plan_dang_chay_cua_khach(customer_id):
        raise ApiError("CONFLICT",
                       "Khách đã có kế hoạch chăm đang chạy — không tạo trùng")
    plan = care_repo.create_plan(
        customer_id=customer_id,
        customer_treatment_id=data.get("customer_treatment_id"),
        owner_id=data.get("owner_id"),
    )
    khoi_tao_moc(plan["id"])
    _audit(actor, action="care_plan_create", object_type="care_plans",
           object_id=plan["id"], new_value={"customer_id": customer_id})
    return care_repo.get_plan(plan["id"])


def khoi_tao_moc(plan_id: int) -> list[dict]:
    """Sinh mốc MỞ MÀN cho kế hoạch mới: CS01 (xác nhận đơn — ngay) và CS02
    (nhận hàng & onboarding — ngay, vì plan sinh lúc đơn ĐÃ giao thành công).
    CS03 KHÔNG sinh ở đây — chỉ sinh khi CS02 xác nhận đã nhận hàng (AU04).
    B8 gọi hàm này ngay sau khi tạo vỏ care_plans. Idempotent."""
    plan = _lay_plan(plan_id)
    gio = datetime.now(timezone.utc)
    ra = []
    for code in ("CS01", "CS02"):
        moc = care_repo.them_moc(plan_id, code, gio)
        if moc:
            ra.append(moc)
    # chu kỳ liệu trình = thứ tự kế hoạch của khách (LT2/LT3 — FR-109)
    if plan.get("cycle_no") == 1:
        _, tong = care_repo.list_plans(customer_id=plan["customer_id"], limit=1)
        if tong > 1:
            care_repo.update_plan(plan_id, cycle_no=min(tong, 9))
    return ra


def sinh_moc(plan_id: int, *, actor: dict | None = None) -> list[dict]:
    """CARE-004 generate-steps — idempotent, KHÔNG đè mốc đã dời lịch.

    FR-102: có actual_start_date mới sinh CS04-CS08 (ngày 4/10/15/20/25);
    chưa bắt đầu dùng thì chỉ có mốc mở màn."""
    plan = _lay_plan(plan_id)
    ra = khoi_tao_moc(plan_id)
    if plan.get("actual_start_date"):
        bat_dau = _ep_date(plan["actual_start_date"])
        for code, ngay in MOC_NGAY.items():
            moc = care_repo.them_moc(plan_id, code, _hen(bat_dau + timedelta(days=ngay)))
            if moc:
                ra.append(moc)
    if ra:
        _audit(actor, action="care_steps_generate", object_type="care_plans",
               object_id=plan_id, new_value={"sinh": [m["step_code"] for m in ra]})
    return care_repo.list_steps(plan_id)


def moc_cua_ke_hoach(plan_id: int) -> list[dict]:
    """CARE-005."""
    _lay_plan(plan_id)
    return care_repo.list_steps(plan_id)


# ============================================================ mốc (CARE-006…008)
def hoan_thanh_moc(
    step_id: int, *, result_code: str = "", note: str = "",
    actor: dict | None = None,
) -> dict:
    """CARE-006 — đóng mốc KHÔNG qua phiếu. Chỉ cho mốc không đòi phiếu
    ('khac' hoặc CS01-03 đã đủ dữ liệu); mốc đánh giá CS04-CS11 phải đi đường
    phiếu CARE-STEP (không cho lách luật dữ liệu bắt buộc — cùng tinh thần
    'không đóng việc thiếu kết quả' mục 19)."""
    step = _lay_moc(step_id)
    if step["status"] in _DA_XONG:
        raise ApiError("CONFLICT", "Mốc này đã đóng rồi")
    can_phieu = care_repo.buoc_chuan().get(step["step_code"] or "", {})
    if can_phieu.get("du_lieu_bat_buoc") and not (step.get("data") or {}) \
            and step["step_code"] not in ("CS01", "CS02", "CS03"):
        raise ApiError(
            "MISSING_REQUIRED_DATA",
            f"Mốc {step['step_code']} phải ghi qua phiếu chăm "
            "(POST /care/customers/{id}/...) — không đóng suông được",
        )
    if result_code and result_code not in care_repo.ma_hop_le("care_result"):
        raise ApiError("VALIDATION_ERROR",
                       "result_code phải thuộc danh mục RS01-RS12")
    moc = care_repo.cap_nhat_moc(
        step_id, status="done", completed_at=datetime.now(timezone.utc),
        completed_by=_actor_id(actor), result_code=result_code or None,
        note=note or None,
    )
    _dong_task_moc(step_id, result_code or "hoan_thanh")
    _audit(actor, action="care_step_complete", object_type="care_plan_steps",
           object_id=step_id, new_value={"step": step["step_code"],
                                         "result": result_code})
    return moc


def doi_lich_moc(
    step_id: int, *, planned_at, reason: str, actor: dict | None = None,
) -> dict:
    """CARE-007 — dời lịch phải có lý do + mốc mới."""
    step = _lay_moc(step_id)
    if step["status"] in _DA_XONG:
        raise ApiError("CONFLICT", "Mốc đã đóng — không dời được")
    if not (reason or "").strip():
        raise ApiError("MISSING_REQUIRED_DATA", "Dời lịch phải ghi lý do")
    if not planned_at:
        raise ApiError("MISSING_REQUIRED_DATA", "Thiếu lịch mới planned_at")
    moc = care_repo.cap_nhat_moc(
        step_id, planned_at=planned_at, status="pending",
        note=f"Dời lịch: {reason.strip()}",
    )
    _audit(actor, action="care_step_reschedule", object_type="care_plan_steps",
           object_id=step_id, reason=reason.strip(),
           new_value={"planned_at": str(planned_at)})
    return moc


def bo_qua_moc(step_id: int, *, reason: str, actor: dict | None = None) -> dict:
    """CARE-008 — 'Phải có lý do' (nguyên văn đặc tả)."""
    step = _lay_moc(step_id)
    if step["status"] in _DA_XONG:
        raise ApiError("CONFLICT", "Mốc đã đóng rồi")
    if not (reason or "").strip():
        raise ApiError("MISSING_REQUIRED_DATA", "Bỏ qua mốc phải ghi lý do")
    moc = care_repo.cap_nhat_moc(step_id, status="skipped",
                                 note=f"Bỏ qua: {reason.strip()}")
    _dong_task_moc(step_id, "bo_qua")
    _audit(actor, action="care_step_skip", object_type="care_plan_steps",
           object_id=step_id, reason=reason.strip())
    return moc


def viec_hom_nay(owner_id: int | None = None) -> list[dict]:
    """CARE-009."""
    return care_repo.moc_den_han(qua_han=False, owner_id=owner_id)


def viec_qua_han(owner_id: int | None = None) -> list[dict]:
    """CARE-010."""
    return care_repo.moc_den_han(qua_han=True, owner_id=owner_id)


def _dong_task_moc(step_id: int, ket_qua: str) -> None:
    """Mốc đóng thì việc nhắc (worker tạo) cũng đóng theo — nuốt lỗi, không
    để vòng phụ làm vỡ luồng chính."""
    try:
        from app.db.client import get_pg_pool

        pool = get_pg_pool()
        with pool.connection() as conn:
            conn.execute(
                "update crm.tasks set status = 'done', result = %s, "
                "completed_at = now() where related_type = 'care_plan_step' "
                "and related_id = %s and status in ('open','in_progress')",
                (f"moc: {ket_qua}", step_id),
            )
    except Exception:  # noqa: BLE001
        pass


# ============================================================ phiếu CARE-STEP-001…011
_PHIEU_MOC = {  # đường API → mã mốc
    "order-confirmation": "CS01", "onboarding": "CS02", "start-usage": "CS03",
    "day-4": "CS04", "day-10": "CS05", "day-15": "CS06", "day-20": "CS07",
    "day-25": "CS08", "day-28": "CS09", "treatment-2": "CS10",
    "treatment-3": "CS11",
}


def ghi_phieu(
    duong: str, customer_id: int, data: dict, *, actor: dict | None = None,
) -> dict:
    """CARE-STEP-001…011 — MỘT cửa cho 11 phiếu; luật riêng từng bước ở
    `_sau_phieu_*`. Trả {step, interaction, plan, canh_bao[]}."""
    step_code = _PHIEU_MOC.get(duong)
    if not step_code:
        raise ApiError("NOT_FOUND", f"Không có phiếu '{duong}'")
    khach = care_repo.get_customer(customer_id)
    if not khach:
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    if khach.get("do_not_contact"):
        raise ApiError("CONFLICT",
                       "Khách đã yêu cầu NGỪNG liên hệ (C09) — không ghi phiếu "
                       "chăm mới; chỉ mở lại khi khách đồng ý lại (AU11)")
    plan = care_repo.plan_dang_chay_cua_khach(customer_id)
    if not plan:
        raise ApiError("NOT_FOUND",
                       "Khách chưa có kế hoạch chăm đang chạy — kế hoạch sinh "
                       "tự động khi đơn giao thành công (B8), hoặc tạo qua "
                       "POST /care-plans")
    data = dict(data or {})
    _kiem_bo_gia_tri(data)

    # mốc của phiếu — chưa sinh thì sinh tại chỗ (phiếu ghi sớm vẫn hợp lệ)
    step = care_repo.moc_theo_ma(plan["id"], step_code) or care_repo.them_moc(
        plan["id"], step_code, datetime.now(timezone.utc)
    ) or care_repo.moc_theo_ma(plan["id"], step_code)
    if step["status"] in _DA_XONG:
        raise ApiError("CONFLICT", f"Mốc {step_code} đã đóng rồi — sửa số liệu "
                                   "cần quản lý mở lại (dời lịch)")

    # KHÔNG GẶP KHÁCH: chỉ ghi tương tác, không bắt dữ liệu, mốc giữ nguyên
    ket_noi = data.get("contact_result")
    if ket_noi and ket_noi != "Kết nối":
        inter = care_repo.tao_interaction(
            step_id=step["id"], customer_id=customer_id, user_id=_actor_id(actor),
            channel=data.get("channel") or "call", contacted=False,
            summary=f"{ket_noi}" + (f" — {data['note']}" if data.get("note") else ""),
        )
        canh_bao = _khong_gap(step, plan, actor=actor)
        _audit(actor, action="care_step_no_contact", object_type="care_plan_steps",
               object_id=step["id"], new_value={"step": step_code, "kq": ket_noi})
        return {"step": care_repo.get_step(step["id"]), "interaction": inter,
                "plan": plan, "canh_bao": canh_bao}

    # GẶP KHÁCH: kiểm trường bắt buộc (danh mục ref_codes + luật riêng CS03/08)
    thieu = _truong_thieu(step_code, data, plan)
    if thieu:
        raise ApiError(
            "MISSING_REQUIRED_DATA",
            f"Phiếu {step_code} thiếu dữ liệu bắt buộc: " + ", ".join(thieu),
            errors={t: "bắt buộc" for t in thieu},
        )

    inter = care_repo.tao_interaction(
        step_id=step["id"], customer_id=customer_id, user_id=_actor_id(actor),
        channel=data.get("channel") or "call", contacted=True,
        summary=data.get("note") or data.get("response_summary"),
        next_action_at=data.get("followup_at") or data.get("next_contact_at"),
    )
    ket_qua = data.get("result_code") or ""
    if ket_qua and ket_qua not in care_repo.ma_hop_le("care_result"):
        raise ApiError("VALIDATION_ERROR", "result_code phải thuộc RS01-RS12")

    canh_bao = _sau_phieu(step_code, plan, step, data, actor=actor)

    dong_moc = data.get("_giu_mo") not in (True, "true", "1")  # CS03 chưa dùng → giữ mở
    if dong_moc:
        care_repo.cap_nhat_moc(
            step["id"], status="done", completed_at=datetime.now(timezone.utc),
            completed_by=_actor_id(actor), data=data,
            result_code=ket_qua or data.get("response_level") or None,
        )
        _dong_task_moc(step["id"], ket_qua or "phieu")
    else:
        care_repo.cap_nhat_moc(step["id"], data=data)

    _audit(actor, action=f"care_step_{step_code.lower()}",
           object_type="care_plan_steps", object_id=step["id"],
           new_value={k: str(v)[:120] for k, v in data.items()
                      if not k.startswith("_")})
    return {"step": care_repo.get_step(step["id"]), "interaction": inter,
            "plan": care_repo.get_plan(plan["id"]), "canh_bao": canh_bao}


def _kiem_bo_gia_tri(data: dict) -> None:
    """Trường trùng tên 1 trong 7 bộ giá trị → giá trị phải thuộc bộ (bảng 19)."""
    for truong in _BO_GIA_TRI:
        if truong in data and data[truong] not in (None, ""):
            hop_le = care_repo.bo_gia_tri(truong)
            if hop_le and data[truong] not in hop_le:
                raise ApiError(
                    "VALIDATION_ERROR",
                    f"{truong} = '{data[truong]}' không thuộc bộ giá trị chuẩn: "
                    + " · ".join(hop_le),
                    errors={truong: "ngoài bộ giá trị"},
                )
    if "received_status" in data and data["received_status"] not in (None, "") \
            and data["received_status"] not in RECEIVED_STATUS:
        raise ApiError("VALIDATION_ERROR",
                       "received_status dùng mã: " + ", ".join(RECEIVED_STATUS))
    if "repurchase_status" in data and data["repurchase_status"] not in (None, "") \
            and data["repurchase_status"] not in REPURCHASE_STATUS:
        raise ApiError("VALIDATION_ERROR",
                       "repurchase_status dùng mã: " + ", ".join(REPURCHASE_STATUS))


def _truong_thieu(step_code: str, data: dict, plan: dict) -> list[str]:
    """Danh sách trường bắt buộc còn thiếu — nền là ref_codes care_step
    (du_lieu_bat_buoc, BRD bảng 18) + luật riêng vài bước."""
    bat_buoc = list(care_repo.buoc_chuan().get(step_code, {})
                    .get("du_lieu_bat_buoc") or [])
    if step_code == "CS02" and plan.get("owner_id"):
        # người chăm đã có từ B8 — không bắt nhập lại
        bat_buoc = [t for t in bat_buoc if t != "care_owner_id"]
    if step_code == "CS03":
        # FR-102: chưa dùng thì KHÔNG có actual_start_date, thay bằng lý do
        bat_buoc = ["actual_start_date"] if _bool(data.get("started")) \
            else ["not_started_reason"]
    if step_code == "CS08":
        bat_buoc = [t for t in bat_buoc if t != "recommendation_id"]
        if data.get("repurchase_status") == "chua_mua":
            bat_buoc.append("lost_reason")        # FR-107: chưa mua → bắt lý do
        if data.get("repurchase_status") == "hen_mua":
            bat_buoc.append("followup_at")        # RS09: hẹn mua → có ngày
    if step_code == "CS09":
        bat_buoc = [t for t in bat_buoc if t != "do_not_contact"]
    return [t for t in bat_buoc if data.get(t) in (None, "", [])]


def _bool(v) -> bool:
    return v is True or str(v).lower() in ("true", "1", "co", "yes")


def _khong_gap(step: dict, plan: dict, *, actor) -> list[str]:
    """AU02: CS01 dồn đủ 3 lần không gặp → việc khẩn báo Sale (+ audit để
    trưởng nhóm thấy trên màn Nhật ký)."""
    if step["step_code"] != "CS01":
        return []
    so_lan = care_repo.dem_lan_khong_ket_noi(step["id"])
    if so_lan < 3:
        return [f"Lần {so_lan}/3 chưa gặp được khách"]
    sale_id = _sale_cua_plan(plan["id"])
    if sale_id:
        _tao_viec_nuot_loi(
            task_type="xu_ly_su_co", assigned_to=sale_id,
            customer_id=plan["customer_id"],
            title=f"CS01 gọi {so_lan} lần không được — Sale liên hệ lại khách",
            due_at=datetime.now(timezone.utc) + timedelta(days=1),
            priority="high", related=("care_plan_step", step["id"]), actor=actor,
        )
    _audit(actor, action="care_cs01_khong_gap", object_type="care_plan_steps",
           object_id=step["id"], new_value={"so_lan": so_lan})
    return [f"Đã {so_lan} lần không gặp → báo Sale và quản lý (AU02)"]


def _sau_phieu(
    step_code: str, plan: dict, step: dict, data: dict, *, actor,
) -> list[str]:
    """Automation cứng sau từng phiếu (AU03…AU09) — trả cảnh báo cho UI."""
    canh_bao: list[str] = []
    plan_id, customer_id = plan["id"], plan["customer_id"]

    if step_code == "CS01":                       # FR-100 → chờ nhận hàng
        _doi_state(plan_id, "C02")

    elif step_code == "CS02":                     # FR-101
        tt = data.get("received_status")
        if tt == "chua_nhan":
            data["_giu_mo"] = True                # chưa nhận → mốc còn mở
            canh_bao.append("Khách chưa nhận hàng — mốc CS02 giữ mở")
        elif tt == "thieu_loi":
            _tao_viec_nuot_loi(
                task_type="xu_ly_su_co", assigned_to=plan.get("owner_id"),
                customer_id=customer_id,
                title="CS02: thiếu/lỗi hàng — mở ticket sự cố",
                due_at=datetime.now(timezone.utc) + timedelta(days=1),
                priority="high", related=("care_plan_step", step["id"]),
                actor=actor,
            )
            canh_bao.append("Thiếu/lỗi hàng → đã mở việc xử lý sự cố")
        else:                                     # đủ hàng → AU04: CS03 sau 2 ngày
            care_repo.them_moc(plan_id, "CS03",
                               datetime.now(timezone.utc) + timedelta(days=2))
            _doi_state(plan_id, "C03")

    elif step_code == "CS03":                     # FR-102 — trục thời gian THẬT
        if _bool(data.get("started")):
            ngay = _ep_date(data["actual_start_date"])
            care_repo.update_plan(plan_id, actual_start_date=ngay,
                                  started_at=datetime.now(timezone.utc))
            for code, n in MOC_NGAY.items():      # AU05: sinh 4/10/15/20/25
                care_repo.them_moc(plan_id, code, _hen(ngay + timedelta(days=n)))
            _doi_state(plan_id, "C04")
            canh_bao.append("Đã sinh mốc CS04-CS08 theo ngày bắt đầu thật")
        else:
            data["_giu_mo"] = True
            hen_lai = data.get("rescheduled_start_date")
            if hen_lai:
                care_repo.cap_nhat_moc(step["id"],
                                       planned_at=_hen(_ep_date(hen_lai)),
                                       status="pending")
                canh_bao.append("Chưa dùng — CS03 dời tới ngày hẹn bắt đầu")
            else:
                canh_bao.append("Chưa dùng, chưa hẹn ngày — CS03 giữ mở")

    elif step_code in ("CS04", "CS05"):           # FR-103/104 — AU06
        if data.get("adverse_event") in ("Vừa", "Nặng"):
            _chuyen_chuyen_mon(
                customer_id,
                f"{step_code}: phản ứng mức {data['adverse_event']} — "
                f"{data.get('note') or data.get('symptom_snapshot') or ''}",
                actor=actor,
            )
            _doi_state(plan_id, "C05")
            canh_bao.append("Phản ứng đáng kể → đã mở ca chuyên môn, khóa đề xuất")
        elif data.get("adverse_event") == "Nhẹ":
            canh_bao.append("Phản ứng nhẹ — ghi nhận, theo dõi tiếp (chưa chuyển ca)")

    elif step_code == "CS06":                     # FR-105 — AU07
        muc = data.get("response_level") or ""
        if muc in ("RS05", "RS06"):
            _chuyen_chuyen_mon(customer_id,
                               f"CS06 ngày 15: kết quả {muc} (nặng hơn/có phản ứng)",
                               actor=actor)
            _doi_state(plan_id, "C05")
            canh_bao.append("Nặng hơn/có phản ứng → ca chuyên môn")
        elif muc == "RS04" and data.get("adherence_level") == "Đúng đủ":
            _chuyen_chuyen_mon(customer_id,
                               "CS06 ngày 15: dùng đúng đủ mà KHÔNG cải thiện (AU07)",
                               actor=actor)
            _doi_state(plan_id, "C05")
            canh_bao.append("Dùng đúng không cải thiện → ca chuyên môn (AU07)")

    elif step_code == "CS07":                     # FR-106 — AU08
        if not care_repo.co_hoi_dang_mo(customer_id):
            care_repo.tao_co_hoi_mua_lai(
                customer_id=customer_id,
                current_treatment_id=plan.get("customer_treatment_id"),
                owner_id=plan.get("owner_id"),
                expected_close_date=_ep_date(data["estimated_end_date"]),
                expected_value=data.get("expected_value"),
            )
            canh_bao.append("Đã tạo cơ hội mua lại (AU08)")
        if plan.get("cskh_state") != "C05":
            _doi_state(plan_id, "C06")

    elif step_code == "CS08":                     # FR-107 — AU09
        tt = data.get("repurchase_status")
        co_hoi = care_repo.co_hoi_dang_mo(customer_id)
        if tt == "da_mua":
            if co_hoi:
                care_repo.cap_nhat_co_hoi(co_hoi["id"], stage="won")
            _doi_state(plan_id, "C07")
        elif tt in ("chua_mua", "tu_choi"):
            ngay28 = None
            if plan.get("actual_start_date"):
                ngay28 = _hen(_ep_date(plan["actual_start_date"]) + timedelta(days=28))
            care_repo.them_moc(plan_id, "CS09",
                               ngay28 or datetime.now(timezone.utc) + timedelta(days=3))
            canh_bao.append("Chưa chốt → đã tạo mốc CS09 ngày 28 (AU09)")
        elif tt == "hen_mua":
            _tao_viec_nuot_loi(
                task_type="mua_lai", assigned_to=plan.get("owner_id"),
                customer_id=customer_id,
                title="Khách hẹn mua — gọi đúng hẹn (RS09)",
                due_at=data.get("followup_at"), priority="high",
                related=("care_plan_step", step["id"]), actor=actor,
            )

    elif step_code == "CS09":                     # FR-108
        if _bool(data.get("do_not_contact")):
            ngung_lien_he(customer_id,
                          reason=data.get("lost_reason") or "Khách yêu cầu dừng (CS09)",
                          actor=actor)
            canh_bao.append("Khách yêu cầu dừng — đã bật ngừng liên hệ (AU11)")
        elif (data.get("next_action") or "") == "Kết thúc":
            co_hoi = care_repo.co_hoi_dang_mo(customer_id)
            if co_hoi:
                care_repo.cap_nhat_co_hoi(co_hoi["id"], stage="lost")
            canh_bao.append("Kết thúc có kiểm soát — cơ hội đóng 'lost'")

    elif step_code in ("CS10", "CS11"):           # FR-109 — chu kỳ 2/3
        hen = data.get("next_repurchase_date") or data.get("next_review_at")
        if hen:
            _tao_viec_nuot_loi(
                task_type="mua_lai", assigned_to=plan.get("owner_id"),
                customer_id=customer_id,
                title=f"{step_code}: hẹn mua tiếp/duy trì",
                due_at=hen, priority="normal",
                related=("care_plan_step", step["id"]), actor=actor,
            )
        _doi_state(plan_id, "C07")
    return canh_bao


def _sale_cua_plan(plan_id: int) -> int | None:
    from app.db.client import get_pg_pool

    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            "select sale_user_id from crm.handovers where care_plan_id = %s "
            "order by id desc limit 1",
            (plan_id,),
        ).fetchone()
    return r["sale_user_id"] if r else None


def _tao_viec_nuot_loi(*, task_type, assigned_to, customer_id, title, due_at,
                       priority, related, actor) -> None:
    """Việc sinh tự động là luồng BỒI — thiếu người nhận/lỗi thì bỏ qua,
    không được làm vỡ phiếu chăm."""
    if not (assigned_to and due_at):
        return
    try:
        from app.services import task_service

        task_service.create_task(
            {"task_type": task_type, "assigned_to": assigned_to,
             "customer_id": customer_id, "title": title, "due_at": due_at,
             "priority": priority, "related_type": related[0],
             "related_id": related[1]},
            actor=actor,
        )
    except Exception:  # noqa: BLE001
        pass


def _chuyen_chuyen_mon(customer_id: int, reason: str, *, actor) -> None:
    """AU06/AU07 — mở ca clinical_escalations (B5 lo chống trùng ca + tạo việc
    duyệt chuyên môn + chặn đề xuất). Nuốt lỗi: cảnh báo phụ không phá phiếu."""
    try:
        from app.services import consult_service

        consult_service.create_escalation(customer_id, reason=reason, actor=actor)
    except Exception:  # noqa: BLE001
        pass


# ============================================================ ASSESSMENT-001…003
def tao_danh_gia(
    interaction_id: int, items: list[dict], *, actor: dict | None = None,
) -> list[dict]:
    """ASSESSMENT-001 — điểm 0-10 từng triệu chứng tại 1 lần tương tác.
    before_score bỏ trống thì lấy điểm NỀN khách khai lúc tư vấn (B5)."""
    inter = care_repo.get_interaction(interaction_id)
    if not inter:
        raise ApiError("NOT_FOUND", "Không tìm thấy lần tương tác chăm")
    if not items:
        raise ApiError("MISSING_REQUIRED_DATA", "Danh sách đánh giá trống")
    nen = care_repo.diem_nen_cua_khach(inter["customer_id"])
    ra = []
    for it in items:
        sid = int(it.get("symptom_id") or 0)
        cur = it.get("current_score")
        if not sid or cur is None:
            raise ApiError("VALIDATION_ERROR",
                           "Mỗi dòng cần symptom_id + current_score (0-10)")
        truoc = it.get("before_score", nen.get(sid))
        if not (0 <= float(cur) <= 10) or (
                truoc is not None and not (0 <= float(truoc) <= 10)):
            raise ApiError("VALIDATION_ERROR", "Điểm phải trong thang 0-10")
        try:
            ra.append(care_repo.tao_assessment(
                interaction_id=interaction_id, symptom_id=sid,
                before_score=truoc, current_score=cur,
            ))
        except Exception as err:  # symptom_id lạ → FK vỡ
            raise ApiError("NOT_FOUND",
                           f"symptom_id {sid} không có trong danh mục") from err
    _audit(actor, action="symptom_assess", object_type="care_interactions",
           object_id=interaction_id, new_value={"so_dong": len(ra)})
    return ra


def lich_su_diem(customer_id: int) -> list[dict]:
    """ASSESSMENT-002."""
    if not care_repo.get_customer(customer_id):
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    return care_repo.assessments_cua_khach(customer_id)


def so_sanh_truoc_sau(customer_id: int) -> dict:
    """ASSESSMENT-003 — nền B5 vs mới nhất; DƯƠNG = cải thiện."""
    if not care_repo.get_customer(customer_id):
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    dong = care_repo.tien_trien(customer_id)
    for d in dong:
        if d["baseline"] is not None and d["latest"] is not None:
            d["change"] = float(d["baseline"]) - float(d["latest"])
        else:
            d["change"] = None
    co_so = [d["change"] for d in dong if d["change"] is not None]
    return {
        "items": dong,
        "avg_change": round(sum(co_so) / len(co_so), 2) if co_so else None,
        "assessed": len(co_so),
        "total_symptoms": len(dong),
    }


# ============================================================ NORESPONSE-001…004
def mo_chuoi(
    customer_id: int, *, care_plan_step_id: int | None = None,
    actor: dict | None = None,
) -> dict:
    """NORESPONSE-001 — mỗi khách 1 chuỗi đang chạy."""
    khach = care_repo.get_customer(customer_id)
    if not khach:
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    if khach.get("do_not_contact"):
        raise ApiError("CONFLICT", "Khách đã yêu cầu ngừng liên hệ — không mở chuỗi")
    if care_repo.chuoi_dang_chay(customer_id):
        raise ApiError("CONFLICT", "Khách đang có chuỗi không phản hồi chưa đóng")
    seq = care_repo.tao_chuoi(customer_id=customer_id,
                              step_id=care_plan_step_id,
                              started_by=_actor_id(actor))
    _audit(actor, action="noresponse_open", object_type="no_response_sequences",
           object_id=seq["id"], new_value={"customer_id": customer_id})
    return seq


def ghi_lan_cham(
    sequence_id: int, *, channel: str, result: str = "", note: str = "",
    actor: dict | None = None,
) -> dict:
    """NORESPONSE-002 — FR-110: thứ tự CHUẨN nhắn→gọi→nhắn→gọi; khách bắt máy
    (Kết nối) → chuỗi đóng 'responded'; đủ 4 lần vẫn im → 'lost_contact' +
    pipeline C08 (tạm mất liên lạc, B10 tái kích hoạt)."""
    seq = care_repo.get_chuoi(sequence_id)
    if not seq:
        raise ApiError("NOT_FOUND", "Không tìm thấy chuỗi")
    if seq["status"] != "active":
        raise ApiError("CONFLICT", "Chuỗi đã đóng")
    lan = len(seq["attempts"]) + 1
    if lan > 4:
        raise ApiError("CONFLICT", "Chuỗi đã đủ 4 lần chạm — phải đóng chuỗi")
    kenh_chuan = _KENH_CHUOI[lan]
    if channel != kenh_chuan:
        nhan = "nhắn tin" if kenh_chuan == "message" else "gọi điện"
        raise ApiError("VALIDATION_ERROR",
                       f"Lần {lan} theo chuỗi chuẩn phải là {nhan} "
                       "(nhắn → gọi → nhắn → gọi)")
    if result:
        hop_le = care_repo.bo_gia_tri("contact_result")
        if hop_le and result not in hop_le:
            raise ApiError("VALIDATION_ERROR",
                           "result thuộc bộ contact_result: " + " · ".join(hop_le))
    care_repo.them_lan_cham(sequence_id=sequence_id, attempt_no=lan,
                            channel=channel, result=result or None,
                            note=note or None, attempted_by=_actor_id(actor))
    if result == "Kết nối":
        care_repo.dong_chuoi(sequence_id, outcome="responded",
                             close_reason="Khách phản hồi", closed_by=_actor_id(actor))
    elif lan == 4:
        care_repo.dong_chuoi(sequence_id, outcome="lost_contact",
                             close_reason="Đủ 4 lần không phản hồi",
                             closed_by=_actor_id(actor))
        plan = care_repo.plan_dang_chay_cua_khach(seq["customer_id"])
        if plan:
            _doi_state(plan["id"], "C08")
        _audit(actor, action="noresponse_lost_contact",
               object_type="no_response_sequences", object_id=sequence_id,
               new_value={"customer_id": seq["customer_id"]})
    return care_repo.get_chuoi(sequence_id)


def dong_chuoi(
    sequence_id: int, *, outcome: str, reason: str = "",
    actor: dict | None = None,
) -> dict:
    """NORESPONSE-003."""
    seq = care_repo.get_chuoi(sequence_id)
    if not seq:
        raise ApiError("NOT_FOUND", "Không tìm thấy chuỗi")
    if seq["status"] != "active":
        raise ApiError("CONFLICT", "Chuỗi đã đóng rồi")
    if outcome not in ("responded", "lost_contact", "do_not_contact"):
        raise ApiError("VALIDATION_ERROR",
                       "outcome: responded | lost_contact | do_not_contact")
    ra = care_repo.dong_chuoi(sequence_id, outcome=outcome,
                              close_reason=reason or None,
                              closed_by=_actor_id(actor))
    if outcome == "lost_contact":
        plan = care_repo.plan_dang_chay_cua_khach(seq["customer_id"])
        if plan:
            _doi_state(plan["id"], "C08")
    if outcome == "do_not_contact":
        ngung_lien_he(seq["customer_id"], reason=reason or "Đóng chuỗi: khách yêu cầu",
                      actor=actor)
    _audit(actor, action="noresponse_close", object_type="no_response_sequences",
           object_id=sequence_id, new_value={"outcome": outcome})
    return ra


def ngung_lien_he(
    customer_id: int, *, reason: str, actor: dict | None = None,
) -> dict:
    """NORESPONSE-004 + AU11 — 'dừng mọi automation': bật cờ khách, pipeline
    về C09, mốc đang chờ chuyển skipped, chuỗi đang chạy đóng lại. Việc (tasks)
    đang mở GIỮ NGUYÊN cho người phụ trách tự đóng có kết quả (mục 19)."""
    khach = care_repo.get_customer(customer_id)
    if not khach:
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    if not (reason or "").strip():
        raise ApiError("MISSING_REQUIRED_DATA", "Ngừng liên hệ phải ghi lý do")
    care_repo.set_do_not_contact(customer_id, flag=True, reason=reason.strip())
    plan = care_repo.plan_dang_chay_cua_khach(customer_id)
    if plan:
        _doi_state(plan["id"], "C09")
        for s in care_repo.list_steps(plan["id"]):
            if s["status"] in ("pending", "due"):
                care_repo.cap_nhat_moc(s["id"], status="skipped",
                                       note="Khách yêu cầu ngừng liên hệ (AU11)")
                _dong_task_moc(s["id"], "khach_dung_lien_he")
    seq = care_repo.chuoi_dang_chay(customer_id)
    if seq:
        care_repo.dong_chuoi(seq["id"], outcome="do_not_contact",
                             close_reason=reason.strip(),
                             closed_by=_actor_id(actor))
    _audit(actor, action="customer_do_not_contact", object_type="customers",
           object_id=customer_id, reason=reason.strip())
    return {"customer_id": customer_id, "do_not_contact": True}


# ============================================================ worker (AU cứng)
def quet_moc() -> dict:
    """Worker 5'/lần: (1) mốc tới lịch → 'due'; (2) mốc due có người phụ trách
    mà chưa có việc nhắc → tạo việc 'cham_soc' đúng người, hạn = lịch mốc
    (idempotent — mốc còn task đang mở thì thôi). Khách do_not_contact được
    lọc từ trong SQL (AU11)."""
    so_due = care_repo.danh_dau_due()
    so_viec = 0
    ten_buoc = None
    for moc in care_repo.moc_can_tao_viec():
        if ten_buoc is None:
            ten_buoc = {c: v["name"] for c, v in care_repo.buoc_chuan().items()}
        try:
            from app.services import task_service

            task_service.create_task({
                "task_type": "cham_soc",
                "assigned_to": moc["owner_id"],
                "customer_id": moc["customer_id"],
                "title": f"Mốc {moc['step_code']} — "
                         f"{ten_buoc.get(moc['step_code'], 'chăm sóc')}"
                         f" · {moc['customer_name']}",
                "due_at": moc["planned_at"],
                "priority": "high" if moc["step_code"] in ("CS01", "CS09") else "normal",
                "related_type": "care_plan_step",
                "related_id": moc["id"],
            })
            so_viec += 1
        except Exception:  # noqa: BLE001 — 1 mốc lỗi không chặn cả mẻ
            continue
    return {"due": so_due, "viec_moi": so_viec}
