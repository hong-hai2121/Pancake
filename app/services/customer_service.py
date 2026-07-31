"""Nghiệp vụ khách hàng 360° (B1 — FR-011/020/021/022/023, BRD mục 5-6).

KHÔNG import FastAPI. Luật chính:

CHỐNG TRÙNG (FR-011) — thứ tự ưu tiên bất di bất dịch:
    1. external_customer_id (theo platform)
    2. PSID (theo page)
    3. số điện thoại ĐÃ CHUẨN HOÁ
    4. page + external_conversation_id
Số điện thoại KHÔNG kết luận một mình được (nhà dùng chung số) — tra ra đúng
1 khách sống thì nhận, ra nhiều khách thì coi như KHÔNG khớp (tạo mới + để
màn nghi trùng xử lý sau), tránh gộp bừa hai người nhà.
"""

from app.core.errors import ApiError
from app.db.repositories import audit_repo, customer_repo, lead_repo, user_repo
from app.services import lead_service
from app.services.phone import normalize_phone

_ASSIGNMENT_TYPES = ("sale", "cskh", "chuyen_mon")


def _get_or_404(customer_id: int) -> dict:
    kh = customer_repo.get_customer(customer_id)
    if kh is None or kh.get("deleted_at"):
        raise ApiError("NOT_FOUND", "Không tìm thấy khách hàng")
    return kh


get_customer = _get_or_404


# ------------------------------------------------------------------ tạo thủ công (FR-020)

def create_customer(
    data: dict, *, force: bool = False, actor_id: int | None = None
) -> dict:
    """FR-020: bắt buộc tên + (SĐT hoặc định danh MXH) + nguồn; nghi trùng thì
    chặn bằng DUPLICATE_CUSTOMER kèm danh sách ứng viên — gửi lại force=true
    nếu người dùng chọn 'vẫn tạo mới'."""
    ten = (data.get("full_name") or "").strip()
    if not ten:
        raise ApiError("MISSING_REQUIRED_DATA", "Thiếu họ tên khách")
    phone = normalize_phone(data.get("primary_phone"))
    if data.get("primary_phone") and phone is None:
        raise ApiError("VALIDATION_ERROR", "Số điện thoại không hợp lệ",
                       errors={"primary_phone": "sai định dạng"})
    co_dinh_danh = data.get("external_customer_id") or data.get("psid")
    if not phone and not co_dinh_danh:
        raise ApiError(
            "MISSING_REQUIRED_DATA",
            "Phải có số điện thoại hoặc định danh mạng xã hội (FR-020)",
        )
    if not (data.get("source") or "").strip():
        raise ApiError("MISSING_REQUIRED_DATA", "Thiếu nguồn khách (FR-020)")

    # nghi trùng theo SĐT
    if phone and not force:
        trung = customer_repo.find_by_phone(phone)
        if trung:
            raise ApiError(
                "DUPLICATE_CUSTOMER",
                "Có hồ sơ trùng số điện thoại — chọn dùng hồ sơ cũ hoặc gửi force=true",
                errors={"candidates": [
                    {"id": t["id"], "full_name": t["full_name"], "status": t["status"]}
                    for t in trung
                ]},
            )

    kh = customer_repo.create_customer({
        "full_name": ten,
        "primary_phone": phone,
        "gender": data.get("gender"),
        "province": data.get("province"),
        "source": data["source"].strip(),
    })
    # định danh MXH đi kèm (nếu có)
    if co_dinh_danh:
        customer_repo.add_identity(
            customer_id=kh["id"], platform=data.get("platform"),
            external_customer_id=data.get("external_customer_id"),
            psid=data.get("psid"), page_id=data.get("page_id"),
        )
    # người phụ trách (FR-020 bắt buộc)
    if data.get("owner_id"):
        assign(customer_id=kh["id"], user_id=data["owner_id"],
               assignment_type=data.get("assignment_type", "sale"),
               reason="tạo khách", actor_id=actor_id)
    audit_repo.ghi(action="create", object_type="customers", object_id=kh["id"],
                   user_id=actor_id,
                   new_value={"full_name": ten, "phone": phone, "source": data["source"]})
    return customer_repo.get_customer(kh["id"])


# ------------------------------------------------------------------ đồng bộ Pancake (FR-011)

def upsert_from_source(
    *,
    platform: str,
    name: str | None = None,
    phone: str | None = None,
    external_customer_id: str | None = None,
    psid: str | None = None,
    page_id: int | None = None,
    external_conversation_id: str | None = None,
    source: str = "pancake",
    create_lead: bool = True,
) -> tuple[dict, bool]:
    """FR-011 — B2 gọi hàm này cho từng hội thoại. Trả (khách, vừa_tạo?).

    Chạy lại bao nhiêu lần cũng không tạo trùng (tiêu chí nghiệm thu FR-011).
    """
    phone_chuan = normalize_phone(phone)
    kh = None
    # 1-2-3-4 đúng thứ tự đặc tả
    if external_customer_id:
        kh = customer_repo.find_by_external_id(platform, external_customer_id)
    if kh is None and psid and page_id:
        kh = customer_repo.find_by_psid(page_id, psid)
    if kh is None and phone_chuan:
        ung_vien = customer_repo.find_by_phone(phone_chuan)
        if len(ung_vien) == 1:      # nhiều khách chung số -> KHÔNG tự nhận
            kh = ung_vien[0]
    if kh is None and page_id and external_conversation_id:
        kh = customer_repo.find_by_conversation(page_id, external_conversation_id)

    vua_tao = kh is None
    if vua_tao:
        kh = customer_repo.create_customer({
            "full_name": (name or "").strip() or "Khách chưa rõ tên",
            "primary_phone": phone_chuan,
            "source": source,
        })
        audit_repo.ghi(action="create", object_type="customers", object_id=kh["id"],
                       new_value={"nguon": source, "platform": platform})
    else:
        # bồi thông tin còn thiếu, KHÔNG đè thông tin đã có
        boi: dict = {}
        if phone_chuan and not kh.get("primary_phone"):
            boi["primary_phone"] = phone_chuan
        if name and kh.get("full_name") == "Khách chưa rõ tên":
            boi["full_name"] = name.strip()
        if boi:
            customer_repo.update_customer(kh["id"], boi)

    # bảo đảm có dòng định danh cho nguồn này
    if external_customer_id or psid:
        da_co = any(
            i.get("external_customer_id") == external_customer_id
            and i.get("psid") == psid and i.get("page_id") == page_id
            for i in customer_repo.list_identities(kh["id"])
        )
        if not da_co:
            try:
                customer_repo.add_identity(
                    customer_id=kh["id"], platform=platform,
                    external_customer_id=external_customer_id,
                    psid=psid, page_id=page_id,
                )
            except Exception:  # noqa: BLE001 — đụng unique = định danh đã thuộc khách khác, bỏ qua
                pass

    # "Tạo lead nếu khách chưa có pipeline" (FR-011)
    if create_lead:
        mo, _ = lead_repo.list_leads(
            customer_id=kh["id"], trang_thai="open", limit=1, offset=0,
        )
        if not mo:
            lead_service.create_lead(customer_id=kh["id"], source=source)

    return customer_repo.get_customer(kh["id"]), vua_tao


# ------------------------------------------------------------------ sửa / xoá mềm

_UPDATE_WHITELIST = {
    "full_name", "primary_phone", "gender", "birth_date", "province",
    "source", "status", "customer_code",
}
_STATUS_HOP_LE = ("new", "consulting", "customer", "treating",
                  "completed", "churned", "blocked")


def update_customer(customer_id: int, data: dict, *, actor_id: int | None = None) -> dict:
    kh = _get_or_404(customer_id)
    fields = {k: v for k, v in data.items() if k in _UPDATE_WHITELIST and v is not None}
    if "primary_phone" in fields:
        p = normalize_phone(fields["primary_phone"])
        if p is None:
            raise ApiError("VALIDATION_ERROR", "Số điện thoại không hợp lệ",
                           errors={"primary_phone": "sai định dạng"})
        fields["primary_phone"] = p
    if "status" in fields and fields["status"] not in _STATUS_HOP_LE:
        raise ApiError("VALIDATION_ERROR", "Trạng thái không hợp lệ",
                       errors={"status": f"chỉ nhận {'/'.join(_STATUS_HOP_LE)}"})
    if not fields:
        return kh
    doi = {k: str(kh.get(k)) for k in fields if str(kh.get(k)) != str(fields[k])}
    out = customer_repo.update_customer(customer_id, fields)
    if doi:
        audit_repo.ghi(action="update", object_type="customers",
                       object_id=customer_id, user_id=actor_id,
                       old_value=doi, new_value={k: str(fields[k]) for k in doi})
    return out


def delete_customer(customer_id: int, *, actor_id: int | None = None,
                    reason: str | None = None) -> None:
    """CUSTOMER-005 — xoá MỀM (đặc tả cấm xoá cứng dữ liệu nghiệp vụ)."""
    _get_or_404(customer_id)
    customer_repo.soft_delete(customer_id)
    audit_repo.ghi(action="delete", object_type="customers",
                   object_id=customer_id, user_id=actor_id, reason=reason)


# ------------------------------------------------------------------ gộp (FR-022)

def merge_customers(
    *, primary_id: int, duplicate_ids: list[int], actor_id: int | None = None
) -> dict:
    """CUSTOMER-007. Hồ sơ phụ giữ nguyên (status=merged) — không mất lịch sử."""
    if primary_id in duplicate_ids:
        raise ApiError("VALIDATION_ERROR", "Hồ sơ chính không thể nằm trong danh sách gộp")
    if not duplicate_ids:
        raise ApiError("VALIDATION_ERROR", "Chưa chọn hồ sơ để gộp")
    _get_or_404(primary_id)

    tong: dict[str, int] = {}
    for dup_id in duplicate_ids:
        dup = customer_repo.get_customer(dup_id)
        if dup is None or dup.get("deleted_at"):
            raise ApiError("NOT_FOUND", f"Không tìm thấy khách #{dup_id}")
        if dup["status"] == "merged":
            raise ApiError("VALIDATION_ERROR", f"Khách #{dup_id} đã được gộp trước đó")
        so = customer_repo.merge_into(primary_id, dup_id)
        tong = {k: tong.get(k, 0) + v for k, v in so.items()}
        audit_repo.ghi(action="merge", object_type="customers", object_id=dup_id,
                       user_id=actor_id,
                       old_value={"status": dup["status"]},
                       new_value={"merged_into_id": primary_id, "da_don": so})
    return {"primary": customer_repo.get_customer(primary_id), "da_don": tong}


def find_duplicates(limit: int = 50) -> list[dict]:
    return customer_repo.find_duplicate_groups(limit)


# ------------------------------------------------------------------ tag (FR-023)

def add_tag(
    *, customer_id: int, tag_id: int | None = None,
    name: str | None = None, type_: str | None = None,
    actor_id: int | None = None,
) -> dict:
    """CUSTOMER-009 — nhận tag_id có sẵn, hoặc name(+type) thì tìm-hoặc-tạo."""
    _get_or_404(customer_id)
    if tag_id is None:
        if not (name or "").strip():
            raise ApiError("MISSING_REQUIRED_DATA", "Cần tag_id hoặc name")
        tag = customer_repo.find_or_create_tag(name.strip(), type_)
        tag_id = tag["id"]
    elif customer_repo.get_tag(tag_id) is None:
        raise ApiError("NOT_FOUND", "Không tìm thấy tag")
    customer_repo.add_tag(customer_id, tag_id)
    audit_repo.ghi(action="add_tag", object_type="customers",
                   object_id=customer_id, user_id=actor_id,
                   new_value={"tag_id": tag_id})
    return {"tag_id": tag_id}


def remove_tag(*, customer_id: int, tag_id: int, actor_id: int | None = None) -> None:
    _get_or_404(customer_id)
    if customer_repo.remove_tag(customer_id, tag_id) == 0:
        raise ApiError("NOT_FOUND", "Khách không gắn tag này")
    audit_repo.ghi(action="remove_tag", object_type="customers",
                   object_id=customer_id, user_id=actor_id,
                   old_value={"tag_id": tag_id})


# ------------------------------------------------------------------ phân công (CUSTOMER-011)

def assign(
    *, customer_id: int, user_id: int, assignment_type: str,
    reason: str | None = None, actor_id: int | None = None,
) -> dict:
    """BRD mục 6: Sale và CSKH là hai ownership RIÊNG; thay người đang giữ
    phải có lý do; người cũ nằm lại trong lịch sử."""
    _get_or_404(customer_id)
    if assignment_type not in _ASSIGNMENT_TYPES:
        raise ApiError("VALIDATION_ERROR",
                       f"assignment_type chỉ nhận {'/'.join(_ASSIGNMENT_TYPES)}")
    nguoi = user_repo.get_user(user_id)
    if not nguoi or nguoi["status"] != "active":
        raise ApiError("VALIDATION_ERROR", "Người nhận không tồn tại hoặc không active")
    dang_giu = [a for a in (customer_repo.get_customer(customer_id).get("nguoi_phu_trach") or [])
                if a["assignment_type"] == assignment_type]
    if dang_giu and dang_giu[0]["user_id"] != user_id and not (reason or "").strip():
        raise ApiError("MISSING_REQUIRED_DATA",
                       "Chuyển khách giữa nhân viên phải có lý do (BRD mục 6)")
    row = customer_repo.assign(
        customer_id=customer_id, user_id=user_id, assignment_type=assignment_type,
    )
    audit_repo.ghi(action="assign", object_type="customers",
                   object_id=customer_id, user_id=actor_id,
                   old_value={"user_id": row.get("nguoi_cu_id")},
                   new_value={"user_id": user_id, "vai": assignment_type},
                   reason=reason)
    return row


# ------------------------------------------------------------------ tra cứu

def list_customers(**kw) -> tuple[list[dict], int]:
    return customer_repo.list_customers(**kw)


def timeline(customer_id: int, limit: int = 100) -> list[dict]:
    _get_or_404(customer_id)
    return customer_repo.timeline(customer_id, limit)


def list_identities(customer_id: int) -> list[dict]:
    _get_or_404(customer_id)
    return customer_repo.list_identities(customer_id)


def add_identity(
    *, customer_id: int, platform: str | None,
    external_customer_id: str | None = None, psid: str | None = None,
    page_id: int | None = None, actor_id: int | None = None,
) -> dict:
    _get_or_404(customer_id)
    if not external_customer_id and not psid:
        raise ApiError("MISSING_REQUIRED_DATA", "Cần external_customer_id hoặc psid")
    try:
        row = customer_repo.add_identity(
            customer_id=customer_id, platform=platform,
            external_customer_id=external_customer_id, psid=psid, page_id=page_id,
        )
    except Exception as err:  # unique -> định danh đã thuộc khách khác
        raise ApiError("DUPLICATE_CUSTOMER",
                       "Định danh này đã thuộc một khách khác") from err
    audit_repo.ghi(action="add_identity", object_type="customers",
                   object_id=customer_id, user_id=actor_id,
                   new_value={"platform": platform,
                              "external_customer_id": external_customer_id,
                              "psid": psid})
    return row


def assignment_history(customer_id: int) -> list[dict]:
    _get_or_404(customer_id)
    return customer_repo.assignment_history(customer_id)
