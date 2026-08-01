"""API chăm sóc sau bán — CARE-001…010 · CARE-STEP-001…011 ·
ASSESSMENT-001…003 · NORESPONSE-001…004 (B9, FR-100…110).

Route là lớp mỏng: mọi luật (mốc theo ngày bắt đầu THẬT, trường bắt buộc
từng phiếu, chuỗi nhắn→gọi→nhắn→gọi, AU02…AU11) ở services/care_service.py.

Quyền: đọc = `customer.view`; ghi phiếu/mốc/chuỗi = `customer.edit`
(CSKH có cả hai); riêng ĐIỂM TRIỆU CHỨNG là dữ liệu sức khỏe → `health.view`.
"""

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import require_permission
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.schemas.care import (
    AssessmentsIn,
    CarePlanCreateIn,
    DoNotContactIn,
    NoResponseAttemptIn,
    NoResponseCloseIn,
    NoResponseOpenIn,
    StepCompleteIn,
    StepRescheduleIn,
    StepSkipIn,
)
from app.services import care_service

router = APIRouter(prefix="/api/v1", tags=["care"])

_xem = Depends(require_permission("customer.view"))
_sua = Depends(require_permission("customer.edit"))
_suc_khoe = Depends(require_permission("health.view"))


# ------------------------------------------------------------ CARE-001…005
@router.get("/care-plans")
async def list_care_plans(
    cskh_state: str = "",
    owner_id: int | None = Query(None, gt=0),
    customer_id: int | None = Query(None, gt=0),
    status: str = "",
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _xem,
):
    """CARE-001 — danh sách kế hoạch chăm (lọc cột C01-C09 / người phụ trách)."""
    rows, total = care_service.danh_sach(
        cskh_state=cskh_state, owner_id=owner_id, customer_id=customer_id,
        status=status, limit=pt.limit, offset=pt.offset)
    return ok(bao_trang(rows, total, pt))


@router.post("/care-plans", status_code=201)
async def create_care_plan(body: CarePlanCreateIn, user: dict = _sua):
    """CARE-003 — tạo tay (đường thường: B8 tự tạo khi đơn giao thành công).
    Luật: 1 khách 1 kế hoạch đang chạy."""
    return ok(care_service.tao_ke_hoach(body.model_dump(), actor=user),
              "Đã tạo kế hoạch chăm")


@router.get("/care-plans/{care_plan_id}")
async def get_care_plan(care_plan_id: int, _user: dict = _xem):
    """CARE-002 — chi tiết + toàn bộ mốc."""
    return ok(care_service.chi_tiet(care_plan_id))


@router.post("/care-plans/{care_plan_id}/generate-steps")
async def generate_steps(care_plan_id: int, user: dict = _sua):
    """CARE-004 — sinh mốc idempotent. FR-102: CÓ actual_start_date mới sinh
    CS04-CS08 (ngày 4/10/15/20/25); không đè mốc đã dời lịch."""
    return ok(care_service.sinh_moc(care_plan_id, actor=user), "Đã sinh mốc")


@router.get("/care-plans/{care_plan_id}/steps")
async def list_steps(care_plan_id: int, _user: dict = _xem):
    """CARE-005."""
    return ok(care_service.moc_cua_ke_hoach(care_plan_id))


# ------------------------------------------------------------ CARE-006…010
@router.post("/care-plan-steps/{step_id}/complete")
async def complete_step(step_id: int, body: StepCompleteIn, user: dict = _sua):
    """CARE-006 — mốc đánh giá (CS04+) phải đi đường PHIẾU, không đóng suông."""
    return ok(care_service.hoan_thanh_moc(
        step_id, result_code=body.result_code, note=body.note, actor=user),
        "Đã hoàn thành mốc")


@router.post("/care-plan-steps/{step_id}/reschedule")
async def reschedule_step(step_id: int, body: StepRescheduleIn, user: dict = _sua):
    """CARE-007 — dời lịch phải có lý do."""
    return ok(care_service.doi_lich_moc(
        step_id, planned_at=body.planned_at, reason=body.reason, actor=user),
        "Đã dời lịch mốc")


@router.post("/care-plan-steps/{step_id}/skip")
async def skip_step(step_id: int, body: StepSkipIn, user: dict = _sua):
    """CARE-008 — 'Phải có lý do' (nguyên văn đặc tả)."""
    return ok(care_service.bo_qua_moc(step_id, reason=body.reason, actor=user),
              "Đã bỏ qua mốc")


@router.get("/care-tasks/today")
async def care_today(request: Request, pham_vi: str = "minh", _user: dict = _xem):
    """CARE-009 — mốc chăm hôm nay; mặc định CỦA TÔI, `?pham_vi=tatca` cả đội."""
    user = getattr(request.state, "user", None) or {}
    owner = None if pham_vi == "tatca" else int(user.get("sub", 0)) or None
    return ok(care_service.viec_hom_nay(owner_id=owner))


@router.get("/care-tasks/overdue")
async def care_overdue(request: Request, pham_vi: str = "minh", _user: dict = _xem):
    """CARE-010 — mốc chăm QUÁ HẠN (khách ngừng liên hệ đã được lọc)."""
    user = getattr(request.state, "user", None) or {}
    owner = None if pham_vi == "tatca" else int(user.get("sub", 0)) or None
    return ok(care_service.viec_qua_han(owner_id=owner))


# ------------------------------------------------------------ CARE-STEP-001…011
@router.post("/care/customers/{customer_id}/{phieu}")
async def ghi_phieu_cham(
    customer_id: int, phieu: str, body: dict, user: dict = _sua,
):
    """CARE-STEP-001…011 — MỘT cửa cho 11 phiếu chăm:

    order-confirmation (CS01) · onboarding (CS02) · start-usage (CS03) ·
    day-4/10/15/20/25/28 (CS04…CS09) · treatment-2/3 (CS10/CS11).

    Trường bắt buộc từng phiếu đọc từ ref_codes `care_step` (BRD bảng 18);
    giá trị chuẩn theo 7 bộ giá trị (bảng 19). Gửi `contact_result` ≠
    "Kết nối" = không gặp khách: chỉ ghi tương tác, mốc giữ nguyên."""
    kq = care_service.ghi_phieu(phieu, customer_id, body, actor=user)
    return ok(kq, "Đã ghi phiếu chăm")


# ------------------------------------------------------------ ASSESSMENT-001…003
@router.post("/care-interactions/{interaction_id}/symptom-assessments",
             status_code=201)
async def create_assessments(
    interaction_id: int, body: AssessmentsIn, user: dict = _sua,
):
    """ASSESSMENT-001 — điểm 0-10 từng triệu chứng; before bỏ trống lấy điểm
    nền khách khai lúc tư vấn (B5)."""
    return ok(care_service.tao_danh_gia(
        interaction_id, [i.model_dump() for i in body.items], actor=user),
        "Đã ghi đánh giá triệu chứng")


@router.get("/customers/{customer_id}/symptom-assessments")
async def list_assessments(customer_id: int, _user: dict = _suc_khoe):
    """ASSESSMENT-002 — lịch sử điểm (dữ liệu sức khỏe → quyền health.view)."""
    return ok(care_service.lich_su_diem(customer_id))


@router.get("/customers/{customer_id}/symptom-progress")
async def symptom_progress(customer_id: int, _user: dict = _suc_khoe):
    """ASSESSMENT-003 — nền B5 vs mới nhất từng triệu chứng; DƯƠNG = cải thiện."""
    return ok(care_service.so_sanh_truoc_sau(customer_id))


# ------------------------------------------------------------ NORESPONSE-001…004
@router.post("/customers/{customer_id}/no-response-sequence", status_code=201)
async def open_sequence(
    customer_id: int, body: NoResponseOpenIn, user: dict = _sua,
):
    """NORESPONSE-001 — mỗi khách 1 chuỗi đang chạy."""
    return ok(care_service.mo_chuoi(
        customer_id, care_plan_step_id=body.care_plan_step_id, actor=user),
        "Đã mở chuỗi không phản hồi")


@router.post("/no-response-sequences/{sequence_id}/attempts")
async def add_attempt(
    sequence_id: int, body: NoResponseAttemptIn, user: dict = _sua,
):
    """NORESPONSE-002 — FR-110 thứ tự CHUẨN nhắn→gọi→nhắn→gọi; 'Kết nối' đóng
    'responded'; đủ 4 lần im lặng → 'lost_contact' + pipeline C08."""
    return ok(care_service.ghi_lan_cham(
        sequence_id, channel=body.channel, result=body.result, note=body.note,
        actor=user), "Đã ghi lần liên hệ")


@router.post("/no-response-sequences/{sequence_id}/close")
async def close_sequence(
    sequence_id: int, body: NoResponseCloseIn, user: dict = _sua,
):
    """NORESPONSE-003."""
    return ok(care_service.dong_chuoi(
        sequence_id, outcome=body.outcome, reason=body.reason, actor=user),
        "Đã đóng chuỗi")


@router.post("/customers/{customer_id}/do-not-contact")
async def do_not_contact(
    customer_id: int, body: DoNotContactIn, user: dict = _sua,
):
    """NORESPONSE-004 + AU11 — dừng MỌI automation với khách này (pipeline C09,
    mốc chờ → bỏ qua, chuỗi đang chạy đóng); chỉ mở lại khi khách đồng ý mới."""
    return ok(care_service.ngung_lien_he(customer_id, reason=body.reason,
                                         actor=user),
              "Đã bật ngừng liên hệ")
