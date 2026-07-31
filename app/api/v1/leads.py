"""PIPELINE-001…004 + LEAD-001…011 (B3 — docs/B3-LEAD-PIPELINE.md).

Route là lớp mỏng: mọi luật nằm ở services/lead_service.py (đã kiểm 25/25
bằng scripts/thu_b3.py trước khi có API).

Quyền: đọc = `customer.view` · ghi = `customer.edit` (lead là dữ liệu khách).
Riêng SỬA CẤU TRÚC pipeline (POST /pipelines, PUT stages) = `user.manage` —
đổi quy trình bán là việc quản trị, không phải việc của Sale.
"""

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_permission
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.schemas.lead import (
    AssignIn, CloseIn, LeadCreateIn, LeadUpdateIn, LostReasonIn,
    MoveStageIn, PipelineCreateIn, StagesUpdateIn,
)
from app.services import lead_service

router = APIRouter(prefix="/api/v1", tags=["leads"])

_xem = Depends(require_permission("customer.view"))
_sua = Depends(require_permission("customer.edit"))
_quan_tri = Depends(require_permission("user.manage"))


# ------------------------------------------------------------------ pipelines

@router.get("/pipelines")
async def list_pipelines(_user: dict = _xem):
    """PIPELINE-001 — kèm số giai đoạn + số lead đang mở."""
    return ok({"items": lead_service.list_pipelines()})


@router.post("/pipelines", status_code=201)
async def create_pipeline(body: PipelineCreateIn, user: dict = _quan_tri):
    """PIPELINE-002."""
    pl = lead_service.create_pipeline(
        name=body.name, type_=body.type, actor_id=int(user["sub"])
    )
    return ok(pl, "Đã tạo pipeline")


@router.get("/pipelines/{pipeline_id}/stages")
async def list_stages(pipeline_id: int, _user: dict = _xem):
    """PIPELINE-003 — kèm số lead từng giai đoạn (đếm cột Kanban)."""
    return ok({"items": lead_service.list_stages(pipeline_id)})


@router.put("/pipelines/{pipeline_id}/stages")
async def update_stages(
    pipeline_id: int, body: StagesUpdateIn, user: dict = _quan_tri
):
    """PIPELINE-004 — upsert theo code, không xoá giai đoạn cũ."""
    items = lead_service.update_stages(
        pipeline_id=pipeline_id,
        stages=[s.model_dump() for s in body.stages],
        actor_id=int(user["sub"]),
    )
    return ok({"items": items}, "Đã cập nhật giai đoạn")


# ------------------------------------------------------------------ leads
# /leads/overdue và /leads/hot phải khai TRƯỚC /leads/{lead_id} kẻo bị nuốt.

@router.get("/leads/overdue")
async def leads_overdue(limit: int = Query(50, ge=1, le=200), _user: dict = _xem):
    """LEAD-008 — quá SLA mà chưa có tương tác đầu."""
    return ok({"items": lead_service.list_overdue(limit)})


@router.get("/leads/hot")
async def leads_hot(limit: int = Query(50, ge=1, le=200), _user: dict = _xem):
    """LEAD-009 — lead nóng, việc gần hạn trước."""
    return ok({"items": lead_service.list_hot(limit)})


@router.get("/leads/queue")
async def leads_queue(limit: int = Query(50, ge=1, le=200), _user: dict = _xem):
    """FR-032 — hàng đợi chưa có người nhận (ngoài danh sách API nhưng màn 11 cần)."""
    return ok({"items": lead_service.list_queue(limit)})


@router.get("/leads")
async def list_leads(
    customer_id: int | None = Query(None),
    owner_id: int | None = Query(None),
    pipeline_id: int | None = Query(None),
    stage_id: int | None = Query(None),
    temperature: str = Query("", pattern="^(nong|am|lanh)?$"),
    trang_thai: str = Query("open", pattern="^(open|closed|all)$"),
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _xem,
):
    """LEAD-001 — lọc như màn 11 (nhân viên/giai đoạn/nhiệt độ/mở-đóng)."""
    rows, total = lead_service.list_leads(
        customer_id=customer_id, owner_id=owner_id, pipeline_id=pipeline_id,
        stage_id=stage_id, temperature=temperature or None,
        trang_thai=trang_thai, limit=pt.limit, offset=pt.offset,
    )
    return ok(bao_trang(rows, total, pt))


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: int, _user: dict = _xem):
    """LEAD-002."""
    return ok(lead_service.get_lead(lead_id))


@router.post("/leads", status_code=201)
async def create_lead(body: LeadCreateIn, user: dict = _sua):
    """LEAD-003 — không chỉ định owner thì chia vòng tròn theo tải (FR-030)."""
    lead = lead_service.create_lead(**body.model_dump(), actor_id=int(user["sub"]))
    return ok(lead, "Đã tạo lead")


@router.put("/leads/{lead_id}")
async def update_lead(lead_id: int, body: LeadUpdateIn, user: dict = _sua):
    """LEAD-004 — trường phụ; giai đoạn/người giữ đi move-stage/assign."""
    lead = lead_service.update_lead(
        lead_id, body.model_dump(exclude_none=True), actor_id=int(user["sub"])
    )
    return ok(lead, "Đã cập nhật")


@router.post("/leads/{lead_id}/move-stage")
async def move_stage(lead_id: int, body: MoveStageIn, user: dict = _sua):
    """LEAD-005 — đủ luật chặn FR-040, ghi lịch sử FR-041."""
    lead = lead_service.move_stage(
        lead_id=lead_id, to_stage_id=body.stage_id, actor_id=int(user["sub"]),
        reason=body.reason, note=body.note,
        next_action_at=body.next_action_at, lost_reason_id=body.lost_reason_id,
    )
    return ok(lead, "Đã chuyển giai đoạn")


@router.get("/leads/{lead_id}/stage-history")
async def stage_history(lead_id: int, _user: dict = _xem):
    """LEAD-006."""
    return ok({"items": lead_service.stage_history(lead_id)})


@router.post("/leads/{lead_id}/assign")
async def assign(lead_id: int, body: AssignIn, user: dict = _sua):
    """LEAD-007 — chuyển giữa người phải có lý do (FR-031)."""
    lead = lead_service.assign_owner(
        lead_id=lead_id, new_owner_id=body.user_id,
        reason=body.reason, actor_id=int(user["sub"]),
    )
    return ok(lead, "Đã gán")


@router.post("/leads/{lead_id}/lost-reasons", status_code=201)
async def add_lost_reason(lead_id: int, body: LostReasonIn, user: dict = _sua):
    """LEAD-010."""
    row = lead_service.add_lost_reason(
        lead_id=lead_id, lost_reason_id=body.lost_reason_id, note=body.note,
        evidence_type=body.evidence_type, evidence_id=body.evidence_id,
        actor_id=int(user["sub"]),
    )
    return ok(row, "Đã ghi lý do")


@router.post("/leads/{lead_id}/close")
async def close_lead(lead_id: int, body: CloseIn, user: dict = _sua):
    """LEAD-011 — đóng = vào giai đoạn kết thúc, đi qua đủ luật move-stage."""
    lead = lead_service.close_lead(
        lead_id=lead_id, stage_code=body.stage_code, actor_id=int(user["sub"]),
        reason=body.reason, note=body.note, lost_reason_id=body.lost_reason_id,
    )
    return ok(lead, "Đã đóng lead")
