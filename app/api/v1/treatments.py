"""TREATMENT-001…014 (B6 — FR-061/062). Luật + rule engine ở
services/treatment_service.py.

Quyền: đọc = `customer.view` · sửa danh mục mẫu + luật = `user.manage` ·
đề xuất / eligibility / tạo + điều chỉnh liệu trình khách = `treatment.edit`
(Sale, chuyên môn) · duyệt đề xuất = `content.approve` (FR-062: người không
đủ quyền không bỏ qua được cảnh báo).
"""

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_permission
from app.core.errors import ApiError
from app.core.response import PhanTrang, bao_trang, ok, phan_trang
from app.db.repositories import catalog_repo
from app.schemas.catalog import (
    CustomerTreatmentIn, EligibilityIn, RecommendationApproveIn, RecommendIn,
    RuleIn, TemplateCreateIn, TemplateItemIn, TemplateItemUpdateIn,
    TemplateUpdateIn, TreatmentAdjustIn,
)
from app.services import treatment_service

router = APIRouter(prefix="/api/v1", tags=["treatments"])

_xem = Depends(require_permission("customer.view"))
_danh_muc = Depends(require_permission("user.manage"))
_lieu_trinh = Depends(require_permission("treatment.edit"))
_duyet = Depends(require_permission("content.approve"))


# ------------------------------------------------------------------ mẫu liệu trình
@router.get("/treatment-templates")
async def list_templates(
    q: str = "",
    status: str = Query("", pattern="^(draft|active|archived)?$"),
    problem_group: str = "",
    pt: PhanTrang = Depends(phan_trang),
    _user: dict = _xem,
):
    """TREATMENT-001."""
    rows, total = catalog_repo.list_templates(
        q=q, status=status, problem_group=problem_group,
        limit=pt.limit, offset=pt.offset,
    )
    return ok(bao_trang(rows, total, pt))


@router.get("/treatment-templates/{template_id}")
async def get_template(template_id: int, _user: dict = _xem):
    """TREATMENT-002 — kèm sản phẩm + luật."""
    tpl = catalog_repo.get_template(template_id)
    if not tpl:
        raise ApiError("NOT_FOUND", "Không tìm thấy mẫu liệu trình")
    return ok(tpl)


@router.post("/treatment-templates", status_code=201)
async def create_template(body: TemplateCreateIn, user: dict = _danh_muc):
    """TREATMENT-003."""
    return ok(treatment_service.create_template(body.model_dump(), actor=user),
              "Đã tạo mẫu liệu trình")


@router.put("/treatment-templates/{template_id}")
async def update_template(
    template_id: int, body: TemplateUpdateIn, user: dict = _danh_muc
):
    """TREATMENT-004."""
    return ok(treatment_service.update_template(
        template_id, body.model_dump(), actor=user), "Đã cập nhật")


@router.post("/treatment-templates/{template_id}/items", status_code=201)
async def add_item(template_id: int, body: TemplateItemIn, user: dict = _danh_muc):
    """TREATMENT-005 — sản phẩm phải đang bán."""
    return ok(treatment_service.add_item(template_id, body.model_dump(), actor=user),
              "Đã thêm sản phẩm vào mẫu")


@router.put("/treatment-templates/{template_id}/items/{item_id}")
async def update_item(
    template_id: int, item_id: int, body: TemplateItemUpdateIn,
    user: dict = _danh_muc,
):
    """TREATMENT-006."""
    return ok(treatment_service.update_item(
        template_id, item_id, body.model_dump(), actor=user), "Đã cập nhật")


@router.post("/treatment-templates/{template_id}/rules", status_code=201)
async def add_rule(template_id: int, body: RuleIn, user: dict = _danh_muc):
    """TREATMENT-007 — luật nằm trong DB, engine chỉ đọc (mục 10 BRD)."""
    return ok(treatment_service.add_rule(template_id, body.model_dump(), actor=user),
              "Đã thêm luật")


@router.get("/treatment-templates/{template_id}/rules")
async def list_rules(template_id: int, _user: dict = _xem):
    """TREATMENT-008."""
    if not catalog_repo.get_template(template_id):
        raise ApiError("NOT_FOUND", "Không tìm thấy mẫu liệu trình")
    return ok({"items": catalog_repo.list_rules(template_id)})


@router.post("/treatment-templates/{template_id}/eligibility-check")
async def eligibility_check(
    template_id: int, body: EligibilityIn, _user: dict = _lieu_trinh
):
    """TREATMENT-009 — chấm MỘT mẫu cho khách."""
    return ok(treatment_service.eligibility_check(template_id, body.customer_id))


# ------------------------------------------------------------------ đề xuất
@router.post("/customers/{customer_id}/treatment-recommendations", status_code=201)
async def recommend(customer_id: int, body: RecommendIn, user: dict = _lieu_trinh):
    """TREATMENT-010 — FR-062: không template_id = xem danh sách; có = LƯU đề xuất."""
    kq = treatment_service.recommend(
        customer_id, template_id=body.template_id, note=body.note, actor=user,
    )
    return ok(kq, "Đã lưu đề xuất" if body.template_id else "")


@router.post("/treatment-recommendations/{recommendation_id}/approve")
async def approve_recommendation(
    recommendation_id: int, body: RecommendationApproveIn, user: dict = _duyet
):
    """TREATMENT-011 — chỉ `content.approve`."""
    return ok(treatment_service.approve_recommendation(
        recommendation_id, approve=body.approve, note=body.note, actor=user,
    ), "Đã duyệt đề xuất" if body.approve else "Đã từ chối đề xuất")


# ------------------------------------------------------------------ liệu trình khách
@router.post("/customers/{customer_id}/treatments", status_code=201)
async def create_customer_treatment(
    customer_id: int, body: CustomerTreatmentIn, user: dict = _lieu_trinh
):
    """TREATMENT-012 — cờ đỏ chặn; đề xuất chờ duyệt/bị từ chối chặn."""
    return ok(treatment_service.create_customer_treatment(
        customer_id, template_id=body.template_id,
        recommendation_id=body.recommendation_id, order_id=body.order_id,
        start_date=body.start_date, actor=user,
    ), "Đã tạo liệu trình cho khách")


@router.get("/customer-treatments/{customer_treatment_id}")
async def get_customer_treatment(customer_treatment_id: int, _user: dict = _xem):
    """TREATMENT-013 — kèm items snapshot."""
    return ok(treatment_service.get_customer_treatment(customer_treatment_id))


@router.post("/customer-treatments/{customer_treatment_id}/adjustments")
async def adjust_customer_treatment(
    customer_treatment_id: int, body: TreatmentAdjustIn, user: dict = _lieu_trinh
):
    """TREATMENT-014 — điều chỉnh kèm lý do, audit cũ→mới."""
    return ok(treatment_service.adjust_customer_treatment(
        customer_treatment_id,
        {"start_date": body.start_date, "expected_end_date": body.expected_end_date,
         "status": body.status},
        reason=body.reason, actor=user,
    ), "Đã điều chỉnh liệu trình")
