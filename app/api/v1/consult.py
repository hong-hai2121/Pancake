"""CONSULT-001…005 · SYMPTOM-001…003 · MEDICAL-001…004 · SAFETY-001…005 (B5).

Route là lớp mỏng — luật FR-050…053 nằm ở services/consult_service.py (kiểm
bằng scripts/thu_b5.py).

Quyền: toàn bộ hồ sơ sức khỏe đọc/ghi = `health.view` (quyền riêng "xem hồ sơ
sức khỏe" — Sale/CSKH/trưởng nhóm/chuyên môn có, Marketing/Kế toán KHÔNG).
Riêng SAFETY-005 (kết luận ca) = `content.approve` — chỉ Người chuyên môn
(+Chủ DN/Admin), đúng FR-062 "không đủ quyền không thể bỏ qua cảnh báo".
"""

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_permission
from app.core.response import ok
from app.db.repositories import consult_repo
from app.schemas.consult import (
    AnswersIn, EscalationIn, ExaminationIn, MedicationIn, PreviousTreatmentIn,
    ResolveIn, ScreeningIn, SessionCreateIn, SymptomSaveIn, SymptomUpdateIn,
)
from app.services import consult_service

router = APIRouter(prefix="/api/v1", tags=["consult"])

_ho_so = Depends(require_permission("health.view"))
_chuyen_mon = Depends(require_permission("content.approve"))


# ------------------------------------------------------------------ CONSULT
@router.post("/consultation-sessions", status_code=201)
async def create_session(body: SessionCreateIn, user: dict = _ho_so):
    """CONSULT-001."""
    return ok(consult_service.create_session(
        customer_id=body.customer_id, lead_id=body.lead_id,
        channel=body.channel, actor=user,
    ), "Đã mở phiên tư vấn")


@router.get("/consultation-sessions/{session_id}")
async def get_session(session_id: int, _user: dict = _ho_so):
    """CONSULT-002 — kèm câu trả lời mới nhất từng mã."""
    return ok(consult_service.get_session(session_id))


@router.post("/consultation-sessions/{session_id}/answers")
async def save_answers(session_id: int, body: AnswersIn, user: dict = _ho_so):
    """CONSULT-003 — trả kèm danh sách còn thiếu để UI nhắc luôn."""
    return ok(consult_service.save_answers(
        session_id, [a.model_dump() for a in body.answers], actor=user,
    ), "Đã lưu câu trả lời")


@router.post("/consultation-sessions/{session_id}/complete")
async def complete_session(session_id: int, user: dict = _ho_so):
    """CONSULT-004 — thiếu câu bắt buộc là bị chặn."""
    return ok(consult_service.complete_session(session_id, actor=user),
              "Đã hoàn tất phiên")


@router.get("/consultation-sessions/{session_id}/missing-fields")
async def missing_fields(session_id: int, _user: dict = _ho_so):
    """CONSULT-005."""
    return ok({"items": consult_service.missing_fields(session_id)})


# ------------------------------------------------------------------ SYMPTOM
@router.get("/symptoms")
async def symptom_catalog(_user: dict = _ho_so):
    """SYMPTOM-001 — danh mục triệu chứng tiêu hoá (seed_danh_muc)."""
    return ok({"items": consult_repo.list_symptom_catalog()})


@router.get("/customers/{customer_id}/symptoms")
async def customer_symptoms(customer_id: int, _user: dict = _ho_so):
    """Phiếu triệu chứng hiện tại của khách (màn 14)."""
    return ok({"items": consult_repo.list_customer_symptoms(customer_id)})


@router.post("/customers/{customer_id}/symptoms", status_code=201)
async def save_symptom(customer_id: int, body: SymptomSaveIn, user: dict = _ho_so):
    """SYMPTOM-002 — khai lại cùng triệu chứng thì cập nhật (1 khách 1 dòng/triệu chứng)."""
    return ok(consult_service.save_symptom(
        customer_id, symptom_id=body.symptom_id,
        data=body.model_dump(exclude={"symptom_id"}), actor=user,
    ), "Đã lưu triệu chứng")


@router.put("/customers/{customer_id}/symptoms/{customer_symptom_id}")
async def update_symptom(
    customer_id: int, customer_symptom_id: int,
    body: SymptomUpdateIn, user: dict = _ho_so,
):
    """SYMPTOM-003."""
    return ok(consult_service.save_symptom(
        customer_id, symptom_id=0, cs_id=customer_symptom_id,
        data={k: v for k, v in body.model_dump().items() if v is not None},
        actor=user,
    ), "Đã cập nhật triệu chứng")


# ------------------------------------------------------------------ MEDICAL
@router.post("/customers/{customer_id}/examinations", status_code=201)
async def add_examination(customer_id: int, body: ExaminationIn, user: dict = _ho_so):
    """MEDICAL-001."""
    return ok(consult_service.add_examination(
        customer_id, body.model_dump(), actor=user,
    ), "Đã lưu kết quả khám")


@router.get("/customers/{customer_id}/examinations")
async def list_examinations(customer_id: int, _user: dict = _ho_so):
    """MEDICAL-002."""
    return ok({"items": consult_repo.list_examinations(customer_id)})


@router.post("/customers/{customer_id}/current-medications", status_code=201)
async def add_medication(customer_id: int, body: MedicationIn, user: dict = _ho_so):
    """MEDICAL-003 — `reaction` có nội dung là tự mở ca chuyên môn (FR-052)."""
    return ok(consult_service.add_medication(
        customer_id, body.model_dump(), actor=user,
    ), "Đã lưu thuốc đang dùng")


@router.post("/customers/{customer_id}/previous-treatments", status_code=201)
async def add_previous_treatment(
    customer_id: int, body: PreviousTreatmentIn, user: dict = _ho_so
):
    """MEDICAL-004."""
    return ok(consult_service.add_previous_treatment(
        customer_id, body.model_dump(), actor=user,
    ), "Đã lưu điều trị trước đây")


# ------------------------------------------------------------------ SAFETY
@router.post("/customers/{customer_id}/safety-screenings", status_code=201)
async def add_screening(customer_id: int, body: ScreeningIn, user: dict = _ho_so):
    """SAFETY-001 — lưu xong chạy rule FR-053 luôn, trả kèm kết luận."""
    return ok(consult_service.add_screening(
        customer_id, screening_type=body.screening_type, value=body.value,
        actor=user,
    ), "Đã lưu phiếu sàng lọc")


@router.post("/customers/{customer_id}/safety-check")
async def safety_check(customer_id: int, user: dict = _ho_so):
    """SAFETY-002 — chạy lại rule trên các phiếu còn hiệu lực."""
    return ok(consult_service.safety_check(customer_id, actor=user))


@router.post("/customers/{customer_id}/clinical-escalations", status_code=201)
async def create_escalation(customer_id: int, body: EscalationIn, user: dict = _ho_so):
    """SAFETY-003 — chuyển chuyên môn chủ động, kèm task cho người chuyên môn."""
    return ok(consult_service.create_escalation(
        customer_id, reason=body.reason, actor=user,
    ), "Đã chuyển chuyên môn")


@router.get("/clinical-escalations")
async def list_escalations(
    status: str = Query("pending", pattern="^(pending|resolved)?$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _user: dict = _ho_so,
):
    """SAFETY-004 — mặc định danh sách ca CHỜ chuyên môn."""
    rows, total = consult_repo.list_escalations(status, limit=limit, offset=offset)
    return ok({"items": rows, "total": total})


@router.post("/clinical-escalations/{escalation_id}/resolve")
async def resolve_escalation(
    escalation_id: int, body: ResolveIn, user: dict = _chuyen_mon
):
    """SAFETY-005 — chỉ người có `content.approve` (Người chuyên môn/Chủ DN/Admin)."""
    return ok(consult_service.resolve_escalation(
        escalation_id, resolution=body.resolution,
        go_canh_bao=body.go_canh_bao, actor=user,
    ), "Đã kết luận ca chuyên môn")
