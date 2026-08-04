"""Nghiệp vụ lead & pipeline Sale (B3 — docs/B3-LEAD-PIPELINE.md).

KHÔNG import FastAPI — nhận giá trị vào, trả dict/raise ApiError, test được chay.
Luật lấy từ FR-030/031/032 (chia lead, chuyển người, hàng đợi) và FR-040/041/042
(luật chặn chuyển giai đoạn, lịch sử, SLA) + BRD mục 6-7.

LUẬT CHẶN CHUYỂN GIAI ĐOẠN (FR-040 "Luật bắt buộc") — bảng RULES bên dưới:
    dang_can_nhac   cần lý do + lịch hẹn (next_action_at)
    da_chot         khách phải có đơn (orders, không tính đơn huỷ)
    tu_choi / khong_phu_hop / mat_lien_lac
                    phải có lý do chuẩn trong lead_lost_reasons
    da_bao_gia      đặc tả đòi "có liệu trình và giá" — CHƯA kiểm được vì dữ liệu
                    liệu trình/báo giá thuộc B5/B6; tạm chỉ bắt buộc lý do,
                    sẽ siết khi B5/B6 xong (ghi trong mô tả B3 mục 'hoãn')
"""

from datetime import datetime, timedelta, timezone

from app.core.errors import ApiError
from app.db.repositories import audit_repo, lead_repo

# SLA (FR-042, ví dụ trong đặc tả). Sau này chuyển vào cấu hình công ty (màn 78).
SLA_NHAN_LEAD_PHUT = 5          # lead mới phải có người nhận trong 5 phút
SLA_TUONG_TAC_DAU_PHUT = 15     # phải có tương tác đầu trong 15 phút

PIPELINE_BAN_MOI = "Bán mới"    # seed ở scripts/seed_danh_muc.py

# Giai đoạn kết thúc kiểu THUA — đóng phải có lý do chuẩn (BRD mục 7)
_STAGE_THUA = {"tu_choi", "khong_phu_hop", "mat_lien_lac"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ tạo & chia

def create_lead(
    *,
    customer_id: int,
    pipeline_id: int | None = None,
    source: str | None = None,
    temperature: str | None = None,
    priority: str = "normal",
    owner_id: int | None = None,
    auto_assign: bool = True,
    actor_id: int | None = None,
) -> dict:
    """Tạo lead ở giai đoạn mở đầu; không chỉ định owner thì chia tự động (FR-030).

    Không có Sale nào đủ điều kiện → owner rỗng, lead nằm ở hàng đợi (FR-032),
    vẫn có sla_due_at để màn hàng đợi cảnh báo tồn lâu.
    """
    if pipeline_id is None:
        pl = lead_repo.get_pipeline_by_name(PIPELINE_BAN_MOI)
        if pl is None:
            raise ApiError(
                "MISSING_REQUIRED_DATA",
                f"Chưa có pipeline '{PIPELINE_BAN_MOI}' — chạy scripts/seed_danh_muc.py trước",
            )
        pipeline_id = pl["id"]

    stage = lead_repo.first_stage(pipeline_id)
    if stage is None:
        raise ApiError("MISSING_REQUIRED_DATA", "Pipeline chưa có giai đoạn nào")

    if owner_id is None and auto_assign:
        sale = lead_repo.pick_sale_round_robin()
        owner_id = sale["id"] if sale else None

    lead = lead_repo.create_lead(
        customer_id=customer_id,
        pipeline_id=pipeline_id,
        stage_id=stage["id"],
        owner_id=owner_id,
        source=source,
        temperature=temperature,
        priority=priority,
        sla_due_at=_now() + timedelta(minutes=SLA_NHAN_LEAD_PHUT),
    )
    audit_repo.ghi(
        action="create", object_type="leads", object_id=lead["id"],
        user_id=actor_id,
        new_value={"customer_id": customer_id, "owner_id": owner_id,
                   "stage": stage["code"], "source": source},
    )
    return lead


def assign_owner(
    *, lead_id: int, new_owner_id: int, reason: str | None,
    actor_id: int | None = None,
) -> dict:
    """Gán/chuyển Sale (LEAD-007). FR-031: ĐÃ có người giữ thì bắt buộc lý do;
    nhận lead từ hàng đợi (chưa ai giữ) thì không cần."""
    lead = _get_or_404(lead_id)
    if lead["owner_id"] is not None and lead["owner_id"] != new_owner_id:
        if not (reason or "").strip():
            raise ApiError(
                "MISSING_REQUIRED_DATA",
                "Chuyển khách tiềm năng giữa nhân viên phải có lý do (FR-031)",
            )
    # Nhận mới thì đặt lại đồng hồ SLA tương tác đầu
    sla = _now() + timedelta(minutes=SLA_TUONG_TAC_DAU_PHUT)
    lead_repo.set_owner(lead_id, new_owner_id, sla)
    audit_repo.ghi(
        action="assign", object_type="leads", object_id=lead_id, user_id=actor_id,
        old_value={"owner_id": lead["owner_id"]},
        new_value={"owner_id": new_owner_id}, reason=reason,
    )
    return lead_repo.get_lead(lead_id)


# ------------------------------------------------------------------ chuyển giai đoạn

def move_stage(
    *,
    lead_id: int,
    to_stage_id: int,
    actor_id: int | None = None,
    reason: str | None = None,
    note: str | None = None,
    next_action_at: datetime | None = None,
    lost_reason_id: int | None = None,
) -> dict:
    """Chuyển giai đoạn có luật chặn (LEAD-005, FR-040/041).

    `lost_reason_id`: tiện tay — chuyển sang giai đoạn thua thì ghi lý do chuẩn
    luôn trong cùng lời gọi, khỏi phải gọi LEAD-010 trước.
    """
    lead = _get_or_404(lead_id)
    to_stage = lead_repo.get_stage(to_stage_id)
    if to_stage is None:
        raise ApiError("NOT_FOUND", "Không tìm thấy giai đoạn đích")
    if to_stage["pipeline_id"] != lead["pipeline_id"]:
        raise ApiError(
            "INVALID_STAGE_TRANSITION",
            "Giai đoạn đích không thuộc pipeline của khách tiềm năng",
        )
    if to_stage_id == lead["stage_id"]:
        return lead  # đứng yên — không ghi lịch sử rác

    code = to_stage["code"]

    # --- luật chặn theo giai đoạn đích (FR-040) ---
    if code == "dang_can_nhac":
        if not (reason or "").strip():
            raise ApiError(
                "MISSING_REQUIRED_DATA",
                "Chuyển 'Đang cân nhắc' phải có lý do (FR-040)",
            )
        if next_action_at is None and lead["next_action_at"] is None:
            raise ApiError(
                "MISSING_REQUIRED_DATA",
                "Chuyển 'Đang cân nhắc' phải có lịch hẹn tiếp theo (FR-040)",
            )
    elif code == "da_bao_gia":
        # Đặc tả đòi "có liệu trình và giá" — chưa kiểm được (B5/B6), tạm bắt lý do
        if not (reason or "").strip():
            raise ApiError(
                "MISSING_REQUIRED_DATA",
                "Chuyển 'Đã báo giá' phải ghi liệu trình + giá đã báo vào lý do "
                "(sẽ kiểm tự động khi có dữ liệu liệu trình)",
            )
    elif code == "da_chot":
        if not lead_repo.customer_has_order(lead["customer_id"]):
            raise ApiError(
                "INVALID_STAGE_TRANSITION",
                "Chuyển 'Đã chốt' phải có đơn hàng của khách (FR-040)",
            )
    elif code in _STAGE_THUA:
        if lost_reason_id is not None:
            lead_repo.add_lost_reason(
                lead_id=lead_id, lost_reason_id=lost_reason_id, note=note,
            )
        if lead_repo.count_lost_reasons(lead_id) == 0:
            raise ApiError(
                "MISSING_REQUIRED_DATA",
                f"Đóng hồ sơ ở '{to_stage['name']}' phải có lý do chuẩn "
                "(lead_lost_reasons — FR-040, LEAD-010)",
            )

    if next_action_at is not None:
        lead_repo.set_next_action(lead_id, next_action_at)

    # Sang 'Đã kết nối' = đã chạm được khách → tính là tương tác đầu (FR-042)
    if code == "da_ket_noi":
        lead_repo.set_first_contact(lead_id)

    lead_repo.move_stage(
        lead_id=lead_id,
        from_stage_id=lead["stage_id"],
        to_stage_id=to_stage_id,
        changed_by=actor_id,
        reason=reason,
        note=note,
        closed=to_stage["is_closed"],
    )
    audit_repo.ghi(
        action="move_stage", object_type="leads", object_id=lead_id,
        user_id=actor_id,
        old_value={"stage": lead["stage_code"]},
        new_value={"stage": code}, reason=reason,
    )
    return lead_repo.get_lead(lead_id)


def record_first_contact(lead_id: int) -> None:
    """B2 gọi khi có tin nhắn/cuộc gọi đầu tiên chạm được khách (FR-042)."""
    _get_or_404(lead_id)
    lead_repo.set_first_contact(lead_id)


def add_lost_reason(
    *, lead_id: int, lost_reason_id: int, note: str | None = None,
    evidence_type: str | None = None, evidence_id: int | None = None,
    actor_id: int | None = None,
) -> dict:
    """LEAD-010 — ghi lý do chưa mua, evidence đa hình kiểm tay (message/call/note)."""
    _get_or_404(lead_id)
    if evidence_type is not None and evidence_type not in ("message", "call", "note"):
        raise ApiError("VALIDATION_ERROR", "evidence_type phải là message/call/note")
    row = lead_repo.add_lost_reason(
        lead_id=lead_id, lost_reason_id=lost_reason_id, note=note,
        evidence_type=evidence_type, evidence_id=evidence_id,
    )
    audit_repo.ghi(
        action="add_lost_reason", object_type="leads", object_id=lead_id,
        user_id=actor_id, new_value={"lost_reason_id": lost_reason_id},
    )
    return row


# ------------------------------------------------------------------ cập nhật & đóng

_UPDATE_WHITELIST = {"source", "temperature", "priority", "next_action_at"}


def update_lead(lead_id: int, data: dict, *, actor_id: int | None = None) -> dict:
    """LEAD-004 — chỉ sửa được trường phụ (nguồn/nhiệt độ/ưu tiên/lịch hẹn).

    Giai đoạn đi đường move_stage (có luật), người giữ đi đường assign_owner
    (có lý do) — không cho sửa tắt qua đây để khỏi lách luật.
    """
    lead = _get_or_404(lead_id)
    fields = {k: v for k, v in data.items() if k in _UPDATE_WHITELIST and v is not None}
    if not fields:
        return lead
    # Audit CHỈ trường đổi (nếp A4)
    doi_cu = {k: str(lead.get(k)) for k in fields if str(lead.get(k)) != str(fields[k])}
    out = lead_repo.update_lead(lead_id, fields)
    if doi_cu:
        audit_repo.ghi(
            action="update", object_type="leads", object_id=lead_id, user_id=actor_id,
            old_value=doi_cu, new_value={k: str(fields[k]) for k in doi_cu},
        )
    return out


def close_lead(
    *, lead_id: int, stage_code: str, actor_id: int | None = None,
    reason: str | None = None, note: str | None = None,
    lost_reason_id: int | None = None,
) -> dict:
    """LEAD-011 — đóng lead = chuyển vào một giai đoạn kết thúc, đi qua đủ luật
    của move_stage (Đã chốt cần đơn; nhóm thua cần lý do chuẩn)."""
    lead = _get_or_404(lead_id)
    stage = lead_repo.get_stage_by_code(lead["pipeline_id"], stage_code)
    if stage is None or not stage["is_closed"]:
        raise ApiError(
            "VALIDATION_ERROR",
            "stage_code phải là một giai đoạn kết thúc của pipeline này",
        )
    return move_stage(
        lead_id=lead_id, to_stage_id=stage["id"], actor_id=actor_id,
        reason=reason, note=note, lost_reason_id=lost_reason_id,
    )


# ------------------------------------------------------------------ pipeline (PIPELINE-001…004)

def list_pipelines() -> list[dict]:
    return lead_repo.list_pipelines()


def create_pipeline(*, name: str, type_: str | None, actor_id: int | None = None) -> dict:
    if not (name or "").strip():
        raise ApiError("VALIDATION_ERROR", "Tên pipeline không được rỗng")
    if lead_repo.get_pipeline_by_name(name.strip()):
        raise ApiError("VALIDATION_ERROR", "Tên pipeline đã tồn tại",
                       errors={"name": "trùng"})
    pl = lead_repo.create_pipeline(name.strip(), type_)
    audit_repo.ghi(action="create", object_type="pipelines", object_id=pl["id"],
                   user_id=actor_id, new_value={"name": pl["name"], "type": type_})
    return pl


def list_stages(pipeline_id: int) -> list[dict]:
    if lead_repo.get_pipeline(pipeline_id) is None:
        raise ApiError("NOT_FOUND", "Không tìm thấy pipeline")
    return lead_repo.list_stages(pipeline_id)


def update_stages(
    *, pipeline_id: int, stages: list[dict], actor_id: int | None = None
) -> list[dict]:
    """PIPELINE-004 — upsert theo code; KHÔNG xoá giai đoạn cũ (lead còn trỏ vào)."""
    if lead_repo.get_pipeline(pipeline_id) is None:
        raise ApiError("NOT_FOUND", "Không tìm thấy pipeline")
    if not stages:
        raise ApiError("VALIDATION_ERROR", "Danh sách giai đoạn rỗng")
    for st in stages:
        lead_repo.upsert_stage(
            pipeline_id=pipeline_id, code=st["code"], name=st["name"],
            sort_order=st.get("sort_order", 0), is_closed=st.get("is_closed", False),
        )
    audit_repo.ghi(
        action="update", object_type="pipelines", object_id=pipeline_id,
        user_id=actor_id, new_value={"stages": [st["code"] for st in stages]},
    )
    return lead_repo.list_stages(pipeline_id)


def list_leads(**kw) -> tuple[list[dict], int]:
    return lead_repo.list_leads(**kw)


# ------------------------------------------------------------------ tra cứu

def _get_or_404(lead_id: int) -> dict:
    lead = lead_repo.get_lead(lead_id)
    if lead is None:
        raise ApiError("NOT_FOUND", "Không tìm thấy lead")
    return lead


get_lead = _get_or_404


def stage_history(lead_id: int) -> list[dict]:
    _get_or_404(lead_id)
    return lead_repo.stage_history(lead_id)


def list_queue(limit: int = 50) -> list[dict]:
    return lead_repo.list_queue(limit)


def list_overdue(limit: int = 50) -> list[dict]:
    return lead_repo.list_overdue(limit)


def list_hot(limit: int = 50) -> list[dict]:
    return lead_repo.list_hot(limit)
