"""Nghiệp vụ hồ sơ tư vấn + sàng lọc an toàn (B5 — FR-050…053). KHÔNG import FastAPI.

Luật trọng yếu cài ở đây:
  * FR-050: ghi chú tự do KHÔNG thay được dữ liệu cấu trúc — khai triệu chứng
    phải có severity hoặc frequency, note chỉ bổ sung.
  * FR-052: thuốc đang dùng có PHẢN ỨNG bất thường -> tự mở ca chuyển chuyên môn.
  * FR-053: 11 mục sàng lọc; dính RED FLAG (nôn máu, phân đen, nuốt nghẹn, đau
    ngực, khó thở, sụt cân) -> gắn cờ ĐỎ hồ sơ + CHẶN đề xuất liệu trình + tạo
    việc `duyet_chuyen_mon` (task engine B4) giao Người chuyên môn.
  * Gỡ cờ chỉ có MỘT đường: Người chuyên môn resolve ca (SAFETY-005) — phiếu
    sàng lọc được cleared_at chứ không xoá, giữ vết.

B6 (đề xuất liệu trình) BẮT BUỘC gọi `kiem_duoc_de_xuat()` trước khi chạy rule
engine — cờ đỏ là dừng.
"""

from app.core.errors import ApiError
from app.db.repositories import audit_repo, consult_repo, task_repo

# ------------------------------------------------------------------ danh mục FR-053
# 11 mục sàng lọc: RED = báo động tiêu hoá (chặn đề xuất, chuyển chuyên môn NGAY);
# YELLOW = thận trọng (cần chuyên môn để mắt, chưa chặn).
SANG_LOC: dict[str, tuple[str, str]] = {
    "non_mau":           ("Nôn máu", "red"),
    "phan_den":          ("Phân đen", "red"),
    "nuot_nghen":        ("Nuốt nghẹn", "red"),
    "dau_nguc":          ("Đau ngực", "red"),
    "kho_tho":           ("Khó thở", "red"),
    "sut_can":           ("Sụt cân không chủ ý", "red"),
    "benh_nen":          ("Bệnh nền", "yellow"),
    "di_ung":            ("Dị ứng", "yellow"),
    "thai_ky":           ("Thai kỳ / cho con bú", "yellow"),
    "thuoc_chong_dong":  ("Thuốc chống đông", "yellow"),
    "gan_than":          ("Bệnh gan / thận", "yellow"),
}

# CONSULT-005: bộ câu bắt buộc của phiếu khai thác (màn 14) — thiếu là chưa
# được hoàn tất phiên.
CAU_HOI_BAT_BUOC: dict[str, str] = {
    "trieu_chung_chinh": "Triệu chứng chính",
    "muc_do":            "Mức độ 0-10",
    "tan_suat":          "Tần suất",
    "thoi_gian_mac":     "Mắc bao lâu",
    "lien_quan_bua_an":  "Liên quan bữa ăn",
    "benh_nen":          "Bệnh nền",
    "thuoc_dang_dung":   "Thuốc đang dùng",
}


def _audit(actor: dict | None, **kw) -> None:
    audit_repo.ghi(user_id=int(actor["sub"]) if actor else None, **kw)


def _actor_id(actor: dict | None) -> int | None:
    return int(actor["sub"]) if actor else None


def _kiem_khach(customer_id: int) -> dict:
    khach = consult_repo.get_customer_flag(customer_id)
    if not khach:
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    return khach


# ================================================================== FR-053
def kiem_duoc_de_xuat(customer_id: int) -> None:
    """Chốt chặn cho B6: khách đang cờ ĐỎ thì KHÔNG đề xuất liệu trình.
    (FR-053 'chặn đề xuất tự động' + FR-062 'không đủ quyền không bỏ qua
    cảnh báo' — gỡ cờ phải qua Người chuyên môn resolve.)"""
    khach = _kiem_khach(customer_id)
    if khach.get("safety_flag") == "red":
        raise ApiError(
            "FORBIDDEN",
            "Hồ sơ đang CẢNH BÁO ĐỎ (sàng lọc an toàn FR-053) — không đề xuất "
            "liệu trình; chờ Người chuyên môn xử lý ca đang mở",
        )


def safety_check(customer_id: int, *, actor: dict | None = None) -> dict:
    """SAFETY-002 — rule engine FR-053 trên các phiếu CÒN HIỆU LỰC:
    red -> cờ đỏ + (nếu chưa có) mở ca chuyển chuyên môn kèm task;
    yellow -> cờ vàng; sạch -> xoá cờ. Trả về kết luận đầy đủ cho UI."""
    khach = _kiem_khach(customer_id)
    phieu = consult_repo.list_active_screenings(customer_id)
    do = [p for p in phieu if SANG_LOC.get(p["screening_type"], ("", ""))[1] == "red"]
    vang = [p for p in phieu if SANG_LOC.get(p["screening_type"], ("", ""))[1] == "yellow"]

    co = "red" if do else ("yellow" if vang else None)
    if co != khach.get("safety_flag"):
        consult_repo.set_customer_flag(customer_id, co)
        _audit(actor, action="safety_flag", object_type="customers",
               object_id=customer_id,
               old_value={"safety_flag": khach.get("safety_flag")},
               new_value={"safety_flag": co})

    escalation_id = None
    if do and not consult_repo.has_pending_escalation(customer_id):
        ly_do = "Red flag sàng lọc: " + ", ".join(
            SANG_LOC[p["screening_type"]][0] for p in do
        )
        escalation_id = _mo_ca(
            customer_id, source="safety_check", reason=ly_do,
            risk_level="critical", actor=actor,
        )["id"]

    return {
        "customer_id": customer_id,
        "safety_flag": co,
        "red": [p["screening_type"] for p in do],
        "yellow": [p["screening_type"] for p in vang],
        "escalation_id": escalation_id,
        "de_xuat_duoc": co != "red",
    }


def add_screening(
    customer_id: int, *, screening_type: str, value: str | None = None,
    actor: dict | None = None,
) -> dict:
    """SAFETY-001 — lưu phiếu rồi CHẠY LUÔN rule (luồng FR-053: nhập -> kiểm)."""
    if screening_type not in SANG_LOC:
        raise ApiError(
            "VALIDATION_ERROR",
            "Mục sàng lọc không hợp lệ — dùng một trong: " + ", ".join(SANG_LOC),
            errors={"screening_type": "không hợp lệ"},
        )
    _kiem_khach(customer_id)
    ten, muc = SANG_LOC[screening_type]
    phieu = consult_repo.add_screening(
        customer_id, screening_type=screening_type, value=value,
        risk_level="critical" if muc == "red" else "medium",
        requires_review=True,
    )
    _audit(actor, action="safety_screening_add", object_type="safety_screenings",
           object_id=phieu["id"],
           new_value={"customer_id": customer_id, "type": screening_type,
                      "muc": muc, "value": (value or "")[:200]})
    ket_qua = safety_check(customer_id, actor=actor)
    return {**phieu, "safety_check": ket_qua}


def _mo_ca(
    customer_id: int, *, source: str, reason: str, risk_level: str | None,
    actor: dict | None,
) -> dict:
    """Mở ca chuyển chuyên môn + task `duyet_chuyen_mon` (B4) cho người chuyên
    môn — FR-053 'tạo việc chuyển chuyên môn, lưu người xử lý'."""
    from datetime import datetime, timedelta, timezone

    from app.services import task_service

    nguoi = consult_repo.nguoi_chuyen_mon()
    task_id = None
    if nguoi:
        task = task_service.create_task(
            {
                "title": f"[Chuyển chuyên môn] {reason[:150]}",
                "task_type": "duyet_chuyen_mon",
                "assigned_to": nguoi["id"],
                "due_at": datetime.now(timezone.utc) + timedelta(hours=24),
                "priority": "urgent" if risk_level == "critical" else "high",
                "customer_id": customer_id,
            },
            actor=actor,
        )
        task_id = task["id"]
    ca = consult_repo.create_escalation(
        customer_id=customer_id, source=source, reason=reason,
        risk_level=risk_level, task_id=task_id,
        created_by=_actor_id(actor), assigned_to=nguoi["id"] if nguoi else None,
    )
    _audit(actor, action="clinical_escalation_open",
           object_type="clinical_escalations", object_id=ca["id"],
           new_value={"customer_id": customer_id, "source": source,
                      "reason": reason[:300], "task_id": task_id})
    return ca


def create_escalation(
    customer_id: int, *, reason: str, actor: dict | None = None,
) -> dict:
    """SAFETY-003 — nhân viên chủ động chuyển chuyên môn (FR-052: thấy rủi ro
    là chuyển, không tự khuyên dừng/đổi thuốc)."""
    if not (reason or "").strip():
        raise ApiError("MISSING_REQUIRED_DATA", "Chuyển chuyên môn phải ghi lý do")
    _kiem_khach(customer_id)
    return _mo_ca(customer_id, source="manual", reason=reason.strip(),
                  risk_level="high", actor=actor)


def resolve_escalation(
    escalation_id: int, *, resolution: str, go_canh_bao: bool = False,
    actor: dict | None = None,
) -> dict:
    """SAFETY-005 — Người chuyên môn kết luận ca. `go_canh_bao=True` = kết luận
    an toàn: gỡ phiếu sàng lọc (giữ vết cleared_at) + tính lại cờ; False = giữ
    nguyên cờ (vd khuyên đi khám). Task đi kèm được đóng với result=kết luận."""
    if not (resolution or "").strip():
        raise ApiError("MISSING_REQUIRED_DATA",
                       "Kết luận chuyên môn là bắt buộc (không đóng ca suông)")
    ca = consult_repo.get_escalation(escalation_id)
    if not ca:
        raise ApiError("NOT_FOUND", "Không tìm thấy ca chuyển chuyên môn")
    if ca["status"] == "resolved":
        raise ApiError("CONFLICT", "Ca này đã được xử lý rồi")

    consult_repo.resolve_escalation(
        escalation_id, resolution=resolution.strip(), resolved_by=_actor_id(actor)
    )
    if ca.get("task_id"):
        from app.services import task_service

        try:
            task_service.complete_task(
                ca["task_id"], f"Kết luận chuyên môn: {resolution.strip()}",
                actor=actor,
            )
        except ApiError:  # task đã bị đóng/huỷ tay trước đó — ca vẫn resolve
            pass
    if go_canh_bao:
        consult_repo.clear_screenings(ca["customer_id"], _actor_id(actor))
    ket_qua = safety_check(ca["customer_id"], actor=actor)
    _audit(actor, action="clinical_escalation_resolve",
           object_type="clinical_escalations", object_id=escalation_id,
           new_value={"resolution": resolution.strip()[:300],
                      "go_canh_bao": go_canh_bao,
                      "safety_flag_sau": ket_qua["safety_flag"]})
    return {**consult_repo.get_escalation(escalation_id), "safety_check": ket_qua}


# ================================================================== FR-050
def save_symptom(
    customer_id: int, *, symptom_id: int, data: dict, cs_id: int | None = None,
    actor: dict | None = None,
) -> dict:
    """SYMPTOM-002/003 — luật FR-050: KHÔNG dùng ghi chú tự do thay dữ liệu
    cấu trúc; phải có ít nhất mức độ hoặc tần suất."""
    _kiem_khach(customer_id)
    if data.get("severity") is None and not data.get("frequency"):
        raise ApiError(
            "MISSING_REQUIRED_DATA",
            "Phải nhập dữ liệu cấu trúc (mức độ 0-10 hoặc tần suất) — "
            "ghi chú chỉ để bổ sung (FR-050)",
        )
    if cs_id:
        cu = consult_repo.get_customer_symptom(customer_id, cs_id)
        if not cu:
            raise ApiError("NOT_FOUND", "Không tìm thấy dòng triệu chứng của khách")
        consult_repo.update_customer_symptom(cs_id, data)
        moi = consult_repo.get_customer_symptom(customer_id, cs_id)
    else:
        moi = consult_repo.upsert_customer_symptom(customer_id, symptom_id, data)
    _audit(actor, action="customer_symptom_save", object_type="customer_symptoms",
           object_id=moi["id"],
           new_value={k: str(moi[k]) for k in
                      ("symptom_id", "severity", "frequency", "is_primary")})
    return moi


# ================================================================== FR-051/052
def add_examination(
    customer_id: int, data: dict, *, actor: dict | None = None
) -> dict:
    _kiem_khach(customer_id)
    kham = consult_repo.add_examination(customer_id, data, _actor_id(actor))
    _audit(actor, action="examination_add", object_type="examinations",
           object_id=kham["id"],
           new_value={"customer_id": customer_id, "exam_type": data["exam_type"]})
    return kham


def add_medication(
    customer_id: int, data: dict, *, actor: dict | None = None
) -> dict:
    """MEDICAL-003 — FR-052: có PHẢN ỨNG bất thường là mở ca chuyên môn luôn,
    nhân viên không tự xử."""
    _kiem_khach(customer_id)
    thuoc = consult_repo.add_medication(customer_id, data, _actor_id(actor))
    _audit(actor, action="medication_add", object_type="current_medications",
           object_id=thuoc["id"],
           new_value={"customer_id": customer_id, "name": data["name"]})
    ca = None
    if (data.get("reaction") or "").strip():
        if not consult_repo.has_pending_escalation(customer_id):
            ca = _mo_ca(
                customer_id, source="medication_risk",
                reason=f"Phản ứng khi dùng {data['name']}: {data['reaction'][:200]}",
                risk_level="high", actor=actor,
            )
    return {**thuoc, "escalation_id": ca["id"] if ca else None}


def add_previous_treatment(
    customer_id: int, data: dict, *, actor: dict | None = None
) -> dict:
    _kiem_khach(customer_id)
    dt = consult_repo.add_previous_treatment(customer_id, data, _actor_id(actor))
    _audit(actor, action="previous_treatment_add",
           object_type="previous_treatments", object_id=dt["id"],
           new_value={"customer_id": customer_id, "name": data["name"]})
    return dt


# ================================================================== CONSULT
def create_session(
    *, customer_id: int, lead_id: int | None = None, channel: str | None = None,
    actor: dict | None = None,
) -> dict:
    _kiem_khach(customer_id)
    phien = consult_repo.create_session(
        customer_id=customer_id, lead_id=lead_id,
        user_id=_actor_id(actor), channel=channel,
    )
    _audit(actor, action="consultation_start",
           object_type="consultation_sessions", object_id=phien["id"],
           new_value={"customer_id": customer_id, "channel": channel})
    return phien


def get_session(session_id: int) -> dict:
    phien = consult_repo.get_session(session_id)
    if not phien:
        raise ApiError("NOT_FOUND", "Không tìm thấy phiên tư vấn")
    return {**phien, "answers": consult_repo.list_answers(session_id)}


def save_answers(
    session_id: int, answers: list[dict], *, actor: dict | None = None
) -> dict:
    phien = consult_repo.get_session(session_id)
    if not phien:
        raise ApiError("NOT_FOUND", "Không tìm thấy phiên tư vấn")
    if phien["completed_at"]:
        raise ApiError("CONFLICT", "Phiên đã hoàn tất — mở phiên mới nếu cần khai thêm")
    if not answers:
        raise ApiError("VALIDATION_ERROR", "Chưa có câu trả lời nào để lưu")
    so = consult_repo.save_answers(session_id, answers)
    return {"session_id": session_id, "saved": so,
            "missing_fields": missing_fields(session_id)}


def missing_fields(session_id: int) -> list[dict]:
    """CONSULT-005 — mã câu bắt buộc chưa có câu trả lời."""
    phien = consult_repo.get_session(session_id)
    if not phien:
        raise ApiError("NOT_FOUND", "Không tìm thấy phiên tư vấn")
    da_co = {a["question_code"] for a in consult_repo.list_answers(session_id)
             if (a["answer_text"] or "").strip() or a["answer_value"] is not None}
    return [{"code": code, "name": ten}
            for code, ten in CAU_HOI_BAT_BUOC.items() if code not in da_co]


def complete_session(session_id: int, *, actor: dict | None = None) -> dict:
    """CONSULT-004 — chưa khai đủ câu bắt buộc thì KHÔNG hoàn tất; risk_level
    phiên chốt theo cờ an toàn hiện tại của khách."""
    phien = consult_repo.get_session(session_id)
    if not phien:
        raise ApiError("NOT_FOUND", "Không tìm thấy phiên tư vấn")
    if phien["completed_at"]:
        raise ApiError("CONFLICT", "Phiên đã hoàn tất rồi")
    thieu = missing_fields(session_id)
    if thieu:
        raise ApiError(
            "MISSING_REQUIRED_DATA",
            "Chưa khai đủ phiếu bắt buộc: " + ", ".join(t["name"] for t in thieu),
            errors={t["code"]: "chưa khai" for t in thieu},
        )
    co = _kiem_khach(phien["customer_id"]).get("safety_flag")
    risk = {"red": "critical", "yellow": "medium"}.get(co, "low")
    consult_repo.complete_session(session_id, risk)
    _audit(actor, action="consultation_complete",
           object_type="consultation_sessions", object_id=session_id,
           new_value={"risk_level": risk})
    return get_session(session_id)
