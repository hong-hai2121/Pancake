"""Nghiệp vụ mẫu liệu trình + RULE ENGINE đề xuất (B6 — FR-061/062).

Luật trọng yếu:
  * Điều kiện phù hợp/loại trừ nằm TRONG DB (`treatment_rules`) — mục 10 BRD,
    không hardcode; engine ở đây chỉ BIẾT CÁCH ĐỌC điều kiện.
  * FR-062: đọc hồ sơ -> kiểm thông tin bắt buộc -> kiểm CỜ ĐỎ
    (consult_service.kiem_duoc_de_xuat — B5) -> chạy rule -> hiển thị kèm
    lý do/cảnh báo/thiếu gì. AI không tự tạo liệu trình; rule engine quyết
    liệu trình nào được hiện; có cảnh báo thì đề xuất PHẢI chuyên môn duyệt
    (không đủ quyền không bỏ qua được cảnh báo).

Định dạng condition_json (mỗi rule MỘT điều kiện — nhiều điều kiện = nhiều rule):
  {"type": "screening",     "code": "thai_ky"}                — khách có phiếu sàng lọc CÒN HIỆU LỰC
  {"type": "symptom",       "code": "o_chua", "min_severity": 5}
  {"type": "symptom_group", "group": "dạ dày"}
  {"type": "safety_flag",   "flag": "yellow"}                 — cờ an toàn hiện tại
action_json: {"message": "..."} — câu hiển thị cho Sale (lý do/cảnh báo).

rule_type: `exclusion` (dính là LOẠI) · `suitable` (template có luật loại này
thì phải khớp >= 1 mới hiện) · `warning` (hiện kèm cảnh báo + ép duyệt).
"""

from datetime import date, timedelta

from psycopg.errors import ForeignKeyViolation, UniqueViolation

from app.core.errors import ApiError
from app.db.repositories import audit_repo, catalog_repo, consult_repo
from app.services import consult_service

RULE_TYPES = ("exclusion", "suitable", "warning")
_COND_TYPES = ("screening", "symptom", "symptom_group", "safety_flag")


def _audit(actor: dict | None, **kw) -> None:
    audit_repo.ghi(user_id=int(actor["sub"]) if actor else None, **kw)


def _actor_id(actor: dict | None) -> int | None:
    return int(actor["sub"]) if actor else None


# ================================================================== FR-061
def create_template(data: dict, *, actor: dict | None = None) -> dict:
    try:
        tpl = catalog_repo.create_template(data)
    except UniqueViolation as err:
        raise ApiError("VALIDATION_ERROR", "Mã mẫu liệu trình (+version) đã tồn tại",
                       errors={"template_code": "đã tồn tại"}) from err
    _audit(actor, action="treatment_template_create",
           object_type="treatment_templates", object_id=tpl["id"],
           new_value={"template_code": tpl["template_code"], "name": tpl["name"]})
    return tpl


def update_template(
    template_id: int, data: dict, *, actor: dict | None = None
) -> dict:
    tpl = catalog_repo.get_template(template_id)
    if not tpl:
        raise ApiError("NOT_FOUND", "Không tìm thấy mẫu liệu trình")
    data = {k: v for k, v in data.items() if v is not None}
    truoc = {k: tpl.get(k) for k in data if tpl.get(k) != data[k]}
    sau = {k: data[k] for k in truoc}
    if sau:
        catalog_repo.update_template(template_id, sau)
        _audit(actor, action="treatment_template_update",
               object_type="treatment_templates", object_id=template_id,
               old_value={k: str(v) for k, v in truoc.items()},
               new_value={k: str(v) for k, v in sau.items()})
    return catalog_repo.get_template(template_id)


def add_item(template_id: int, data: dict, *, actor: dict | None = None) -> dict:
    if not catalog_repo.get_template(template_id):
        raise ApiError("NOT_FOUND", "Không tìm thấy mẫu liệu trình")
    sp = catalog_repo.get_product(data["product_id"])
    if not sp:
        raise ApiError("NOT_FOUND", "Không tìm thấy sản phẩm để thêm")
    if sp["status"] != "active":
        raise ApiError("CONFLICT", "Sản phẩm đang khoá/ngừng bán — không thêm vào mẫu")
    item = catalog_repo.add_template_item(template_id, data)
    _audit(actor, action="treatment_template_item_add",
           object_type="treatment_templates", object_id=template_id,
           new_value={"product_id": data["product_id"],
                      "quantity": str(data["quantity"])})
    return item


def update_item(
    template_id: int, item_id: int, data: dict, *, actor: dict | None = None
) -> dict:
    item = catalog_repo.update_template_item(item_id, template_id, data)
    if not item:
        raise ApiError("NOT_FOUND", "Không tìm thấy sản phẩm trong mẫu này")
    _audit(actor, action="treatment_template_item_update",
           object_type="treatment_templates", object_id=template_id,
           new_value={k: str(v) for k, v in data.items() if v is not None})
    return item


def add_rule(template_id: int, data: dict, *, actor: dict | None = None) -> dict:
    """TREATMENT-007 — luật nằm trong DB; ở đây chỉ kiểm ĐỊNH DẠNG điều kiện
    để engine về sau đọc được chắc chắn."""
    if not catalog_repo.get_template(template_id):
        raise ApiError("NOT_FOUND", "Không tìm thấy mẫu liệu trình")
    if data.get("rule_type") not in RULE_TYPES:
        raise ApiError("VALIDATION_ERROR",
                       "rule_type phải là exclusion / suitable / warning")
    cond = data.get("condition") or {}
    if cond.get("type") not in _COND_TYPES:
        raise ApiError(
            "VALIDATION_ERROR",
            "condition.type phải là một trong: " + ", ".join(_COND_TYPES),
        )
    if cond["type"] in ("screening", "symptom") and not cond.get("code"):
        raise ApiError("VALIDATION_ERROR", "condition thiếu 'code'")
    if cond["type"] == "symptom_group" and not cond.get("group"):
        raise ApiError("VALIDATION_ERROR", "condition thiếu 'group'")
    if not (data.get("action") or {}).get("message"):
        raise ApiError("VALIDATION_ERROR",
                       "action.message (câu hiển thị cho Sale) là bắt buộc")
    rule = catalog_repo.add_rule(template_id, data)
    _audit(actor, action="treatment_rule_add", object_type="treatment_rules",
           object_id=rule["id"],
           new_value={"template_id": template_id, "rule_type": data["rule_type"],
                      "condition": cond})
    return rule


# ================================================================== rule engine
def _ho_so_khach(customer_id: int) -> dict:
    """Đọc 1 lần toàn bộ dữ kiện hồ sơ mà điều kiện rule có thể hỏi tới."""
    khach = consult_repo.get_customer_flag(customer_id)
    if not khach:
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    trieu_chung = consult_repo.list_customer_symptoms(customer_id)
    phieu = consult_repo.list_active_screenings(customer_id)
    return {
        "khach": khach,
        "symptom_by_code": {t["symptom_code"]: t for t in trieu_chung},
        "symptom_groups": {t["group_name"] for t in trieu_chung if t["group_name"]},
        "screenings": {p["screening_type"] for p in phieu},
        "safety_flag": khach.get("safety_flag"),
    }


def _khop(cond: dict, ho_so: dict) -> bool:
    """Một điều kiện có đúng với hồ sơ khách không — trái tim của engine."""
    loai = cond.get("type")
    if loai == "screening":
        return cond.get("code") in ho_so["screenings"]
    if loai == "symptom":
        tc = ho_so["symptom_by_code"].get(cond.get("code"))
        if not tc:
            return False
        muc = cond.get("min_severity")
        return muc is None or (tc["severity"] is not None and tc["severity"] >= muc)
    if loai == "symptom_group":
        return cond.get("group") in ho_so["symptom_groups"]
    if loai == "safety_flag":
        return ho_so["safety_flag"] == cond.get("flag")
    return False


def _cham_template(tpl: dict, ho_so: dict) -> dict:
    """Chấm 1 template với hồ sơ: {hien, ly_do[], canh_bao[], loai_vi}."""
    ly_do, canh_bao = [], []
    co_suitable = False
    khop_suitable = False
    for r in tpl["rules"]:
        cond, msg = r["condition_json"], (r["action_json"] or {}).get("message", "")
        if r["rule_type"] == "exclusion" and _khop(cond, ho_so):
            return {"hien": False, "loai_vi": msg or "dính điều kiện loại trừ",
                    "ly_do": [], "canh_bao": []}
        if r["rule_type"] == "suitable":
            co_suitable = True
            if _khop(cond, ho_so):
                khop_suitable = True
                ly_do.append(msg)
        if r["rule_type"] == "warning" and _khop(cond, ho_so):
            canh_bao.append(msg)
    if co_suitable and not khop_suitable:
        return {"hien": False, "loai_vi": "không khớp điều kiện phù hợp nào",
                "ly_do": [], "canh_bao": []}
    return {"hien": True, "loai_vi": None, "ly_do": ly_do, "canh_bao": canh_bao}


def eligibility_check(template_id: int, customer_id: int) -> dict:
    """TREATMENT-009 — chấm MỘT template cho khách (không cần khách đã khai đủ)."""
    tpl = catalog_repo.get_template(template_id)
    if not tpl:
        raise ApiError("NOT_FOUND", "Không tìm thấy mẫu liệu trình")
    ho_so = _ho_so_khach(customer_id)
    kq = _cham_template(
        {**tpl, "rules": [r for r in tpl["rules"] if r["status"] == "active"]},
        ho_so,
    )
    return {"template_id": template_id, "customer_id": customer_id,
            "eligible": kq["hien"] and ho_so["safety_flag"] != "red",
            "loai_vi": kq["loai_vi"] if not kq["hien"] else (
                "khách đang cờ đỏ an toàn" if ho_so["safety_flag"] == "red" else None),
            "ly_do": kq["ly_do"], "canh_bao": kq["canh_bao"]}


def recommend(
    customer_id: int, *, template_id: int | None = None, note: str | None = None,
    actor: dict | None = None,
) -> dict:
    """TREATMENT-010 — FR-062 trọn luồng.

    Không có `template_id`: chạy engine trả danh sách cân nhắc (KHÔNG lưu).
    Có `template_id`: Sale đã CHỌN — kiểm lại rồi LƯU phiên bản đề xuất;
    có cảnh báo -> needs_approval, chờ chuyên môn duyệt mới tạo liệu trình được.
    """
    consult_service.kiem_duoc_de_xuat(customer_id)          # cờ đỏ là dừng (B5)
    ho_so = _ho_so_khach(customer_id)
    if not ho_so["symptom_by_code"]:
        raise ApiError(
            "MISSING_REQUIRED_DATA",
            "Khách chưa khai phiếu triệu chứng — khai thác trước rồi mới đề xuất "
            "(FR-062 bước kiểm thông tin bắt buộc)",
        )
    thieu = []
    if not ho_so["screenings"] and ho_so["safety_flag"] is None:
        thieu.append("chưa có phiếu sàng lọc an toàn nào")

    hien, loai_tru = [], []
    for tpl in catalog_repo.list_active_templates_with_rules():
        kq = _cham_template(tpl, ho_so)
        gon = {"template_id": tpl["id"], "template_code": tpl["template_code"],
               "name": tpl["name"], "problem_group": tpl["problem_group"],
               "base_price": tpl["base_price"], "duration_days": tpl["duration_days"]}
        if kq["hien"]:
            hien.append({**gon, "ly_do": kq["ly_do"], "canh_bao": kq["canh_bao"]})
        else:
            loai_tru.append({**gon, "loai_vi": kq["loai_vi"]})

    canh_bao_chung = []
    if ho_so["safety_flag"] == "yellow":
        canh_bao_chung.append(
            "Khách có mục sàng lọc thận trọng (" + ", ".join(sorted(ho_so["screenings"]))
            + ") — đề xuất sẽ cần chuyên môn duyệt"
        )

    if template_id is None:
        return {"customer_id": customer_id, "items": hien, "loai_tru": loai_tru,
                "canh_bao_chung": canh_bao_chung, "missing_info": thieu}

    chon = next((x for x in hien if x["template_id"] == template_id), None)
    if not chon:
        raise ApiError(
            "CONFLICT",
            "Mẫu này không nằm trong danh sách rule engine cho phép — "
            "không lưu đề xuất (FR-062: rule engine quyết)",
        )
    can_duyet = bool(chon["canh_bao"] or canh_bao_chung)
    rec = catalog_repo.create_recommendation(
        customer_id=customer_id, template_id=template_id,
        recommended_by=_actor_id(actor),
        status="pending_approval" if can_duyet else "proposed",
        needs_approval=can_duyet,
        reasons=chon["ly_do"], warnings=chon["canh_bao"] + canh_bao_chung,
        missing_info=thieu, note=note,
    )
    _audit(actor, action="treatment_recommend",
           object_type="treatment_recommendations", object_id=rec["id"],
           new_value={"customer_id": customer_id, "template_id": template_id,
                      "needs_approval": can_duyet})
    return rec


def approve_recommendation(
    rec_id: int, *, approve: bool = True, note: str | None = None,
    actor: dict | None = None,
) -> dict:
    """TREATMENT-011 — chuyên môn duyệt/từ chối đề xuất có cảnh báo."""
    rec = catalog_repo.get_recommendation(rec_id)
    if not rec:
        raise ApiError("NOT_FOUND", "Không tìm thấy đề xuất")
    if rec["status"] != "pending_approval":
        raise ApiError("CONFLICT",
                       f"Đề xuất đang '{rec['status']}' — chỉ duyệt được khi chờ duyệt")
    trang_thai = "approved" if approve else "rejected"
    catalog_repo.set_recommendation_status(
        rec_id, status=trang_thai, approved_by=_actor_id(actor), note=note,
    )
    _audit(actor, action="treatment_recommendation_" + trang_thai,
           object_type="treatment_recommendations", object_id=rec_id,
           reason=note)
    return catalog_repo.get_recommendation(rec_id)


# ================================================================== liệu trình khách
def create_customer_treatment(
    customer_id: int, *, template_id: int | None = None,
    recommendation_id: int | None = None, order_id: int | None = None,
    start_date: date | None = None, actor: dict | None = None,
) -> dict:
    """TREATMENT-012 — tạo liệu trình THẬT. Cờ đỏ chặn; đề xuất có cảnh báo
    phải được duyệt trước; template phải active."""
    consult_service.kiem_duoc_de_xuat(customer_id)
    approved_by = None
    if recommendation_id:
        rec = catalog_repo.get_recommendation(recommendation_id)
        if not rec or rec["customer_id"] != customer_id:
            raise ApiError("NOT_FOUND", "Không tìm thấy đề xuất của khách này")
        if rec["status"] == "pending_approval":
            raise ApiError("CONFLICT",
                           "Đề xuất đang CHỜ CHUYÊN MÔN DUYỆT — chưa tạo được "
                           "liệu trình (FR-062)")
        if rec["status"] == "rejected":
            raise ApiError("CONFLICT", "Đề xuất đã bị chuyên môn từ chối")
        template_id = rec["template_id"]
        approved_by = rec["approved_by"]
    if not template_id:
        raise ApiError("VALIDATION_ERROR",
                       "Cần template_id hoặc recommendation_id")
    tpl = catalog_repo.get_template(template_id)
    if not tpl:
        raise ApiError("NOT_FOUND", "Không tìm thấy mẫu liệu trình")
    if tpl["status"] != "active":
        raise ApiError("CONFLICT", "Mẫu liệu trình chưa active — không tạo được")

    het_du_kien = (
        start_date + timedelta(days=tpl["duration_days"])
        if start_date and tpl["duration_days"] else None
    )
    try:
        ct = catalog_repo.create_customer_treatment(
            customer_id=customer_id, template_id=template_id, order_id=order_id,
            approved_by=approved_by, start_date=start_date,
            expected_end_date=het_du_kien,
        )
    except ForeignKeyViolation as err:
        raise ApiError("NOT_FOUND", "order_id không tồn tại") from err
    _audit(actor, action="customer_treatment_create",
           object_type="customer_treatments", object_id=ct["id"],
           new_value={"customer_id": customer_id, "template_id": template_id,
                      "recommendation_id": recommendation_id})
    return catalog_repo.get_customer_treatment(ct["id"])


def get_customer_treatment(ct_id: int) -> dict:
    ct = catalog_repo.get_customer_treatment(ct_id)
    if not ct:
        raise ApiError("NOT_FOUND", "Không tìm thấy liệu trình của khách")
    return ct


def adjust_customer_treatment(
    ct_id: int, data: dict, *, reason: str = "", actor: dict | None = None,
) -> dict:
    """TREATMENT-014 — điều chỉnh (ngày bắt đầu/kết thúc dự kiến/trạng thái)
    LUÔN kèm lý do, ghi audit cũ→mới; liệu trình đã kết thúc thì thôi."""
    ct = catalog_repo.get_customer_treatment(ct_id)
    if not ct:
        raise ApiError("NOT_FOUND", "Không tìm thấy liệu trình của khách")
    if ct["status"] in ("completed", "stopped"):
        raise ApiError("CONFLICT", "Liệu trình đã kết thúc — không điều chỉnh nữa")
    if not (reason or "").strip():
        raise ApiError("MISSING_REQUIRED_DATA", "Điều chỉnh liệu trình phải ghi lý do")
    data = {k: v for k, v in data.items() if v is not None}
    truoc = {k: ct.get(k) for k in data if ct.get(k) != data[k]}
    sau = {k: data[k] for k in truoc}
    if not sau:
        return ct
    catalog_repo.update_customer_treatment(ct_id, sau)
    _audit(actor, action="customer_treatment_adjust",
           object_type="customer_treatments", object_id=ct_id,
           old_value={k: str(v) for k, v in truoc.items()},
           new_value={k: str(v) for k, v in sau.items()}, reason=reason.strip())
    return catalog_repo.get_customer_treatment(ct_id)
