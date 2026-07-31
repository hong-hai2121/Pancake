"""Nghiệp vụ quản lý nhân viên (A5 — FR-002). KHÔNG import FastAPI.

Luật FR-002 cài ở đây:
  * Không xoá cứng tài khoản — chỉ đổi status (không có hàm delete).
  * Nhân viên nghỉ việc PHẢI chuyển hết khách/việc trước khi khoá.
  * Mọi thay đổi đều ghi audit kèm giá trị cũ/mới (A4).
  * Phạm vi 2 tầng: `user.manage` (Chủ DN/Admin) đụng được mọi tài khoản;
    `user.manage_team` (trưởng nhóm Sale/CSKH) chỉ TẠO + reset mật khẩu cho
    THÀNH VIÊN đội mình — xem `pham_vi_doi()`.

`actor` = payload token của người đang thao tác (dict, có sub/name/perms);
`ip`/`user_agent` đi kèm để audit — cùng nếp với auth_service.
"""

import secrets

from psycopg.errors import UniqueViolation

from app.core import security
from app.core.errors import ApiError
from app.db.repositories import audit_repo, auth_repo, org_repo, user_repo

# Trưởng nhóm của bộ phận nào chỉ tạo/quản được vai trò THÀNH VIÊN bộ phận đó
_VAI_THANH_VIEN = {"sale": "Sale", "cskh": "CSKH"}


def pham_vi_doi(actor: dict) -> dict | None:
    """Xác định phạm vi quản lý tài khoản của người thao tác.

    * Có `user.manage`      -> None (toàn quyền, mọi cấp).
    * Có `user.manage_team` -> dict {team_id, team_name, role_id, role_name}:
      phải LÀ TRƯỞNG NHÓM (teams.manager_id trỏ về mình) và đội phải gắn bộ
      phận sale/cskh; chỉ được đụng tài khoản vai trò thành viên tương ứng.
    * Không có gì -> FORBIDDEN — chặn ở service để API lẫn web không lọt.

    Tra DB chứ không tin team_id trong token: đổi đội/trưởng nhóm ăn ngay,
    không phải chờ refresh token.
    """
    perms = actor.get("perms") or []
    if "user.manage" in perms:
        return None
    if "user.manage_team" not in perms:
        raise ApiError("FORBIDDEN", "Bạn không có quyền quản lý tài khoản")
    nguoi = user_repo.get_user(int(actor["sub"]))
    doi = org_repo.get_team(nguoi["team_id"]) if nguoi and nguoi.get("team_id") else None
    if not doi or doi.get("manager_id") != nguoi["id"]:
        raise ApiError(
            "FORBIDDEN",
            "Bạn chưa được gán làm trưởng nhóm của đội nào — liên hệ Admin",
        )
    ten_vai = _VAI_THANH_VIEN.get(doi.get("department") or "")
    vai = org_repo.get_role_by_name(ten_vai) if ten_vai else None
    if not vai:
        raise ApiError(
            "CONFLICT",
            f"Đội {doi['name']} chưa gắn bộ phận sale/cskh — "
            "Admin sửa ở màn Vai trò & quyền",
        )
    return {"team_id": doi["id"], "team_name": doi["name"],
            "role_id": vai["id"], "role_name": vai["name"]}


def _audit(actor: dict | None, ip, ua, **kw) -> None:
    audit_repo.ghi(
        user_id=int(actor["sub"]) if actor else None, ip=ip, user_agent=ua, **kw
    )


def _khac_nhau(cu: dict, moi: dict) -> tuple[dict, dict]:
    """Chỉ giữ các trường THAY ĐỔI thật — audit gọn, đọc là thấy ngay ai sửa gì."""
    truoc, sau = {}, {}
    for k, v in moi.items():
        if cu.get(k) != v:
            truoc[k] = cu.get(k)
            sau[k] = v
    return truoc, sau


def create_user(
    data: dict, *, actor: dict, ip=None, user_agent=None
) -> dict:
    """USER-003. `data` đã qua Pydantic; mật khẩu đầu do Admin đặt hoặc tự sinh.

    Trưởng nhóm (`user.manage_team`): vai trò + đội bị ÉP theo phạm vi ở
    server — form có gửi gì khác cũng không ăn; xin vai trò khác thì báo thẳng.
    """
    pham_vi = pham_vi_doi(actor)
    if pham_vi:
        if data.get("role_id") and data["role_id"] != pham_vi["role_id"]:
            raise ApiError(
                "FORBIDDEN",
                f"Trưởng nhóm chỉ tạo được tài khoản {pham_vi['role_name']} "
                "trong đội mình",
            )
        data["role_id"] = pham_vi["role_id"]
        data["team_id"] = pham_vi["team_id"]
    mat_khau = data.get("password") or ("Nv-" + secrets.token_urlsafe(9))
    if len(mat_khau) < 8:
        raise ApiError("VALIDATION_ERROR", "Mật khẩu phải từ 8 ký tự",
                       errors={"password": "tối thiểu 8 ký tự"})
    try:
        user = user_repo.create_user(
            name=data["name"], email=data["email"], username=data["username"],
            password_hash=security.hash_password(mat_khau),
            phone=data.get("phone"), role_id=data.get("role_id"),
            team_id=data.get("team_id"),
        )
    except UniqueViolation as err:
        truong = "email" if "email" in str(err) else "username"
        raise ApiError("VALIDATION_ERROR", f"{truong} đã tồn tại",
                       errors={truong: "đã tồn tại"}) from err
    _audit(actor, ip, user_agent, action="user_create", object_type="users",
           object_id=user["id"],
           new_value={k: user[k] for k in ("name", "email", "username", "role_id", "team_id")})
    # Trả kèm mật khẩu ĐÚNG MỘT LẦN này để Admin đưa cho nhân viên — không lưu đâu khác
    return {**user, "initial_password": mat_khau}


def update_user(
    user_id: int, data: dict, *, actor: dict, ip=None, user_agent=None
) -> dict:
    """USER-004: sửa thông tin/vai trò/nhóm (không đổi status hay mật khẩu ở đây)."""
    cu = user_repo.get_user(user_id)
    if not cu:
        raise ApiError("NOT_FOUND", "Không tìm thấy nhân viên")
    data = {k: v for k, v in data.items() if v is not None}
    truoc, sau = _khac_nhau(cu, data)
    if not sau:
        return cu
    try:
        user_repo.update_user(user_id, sau)
    except UniqueViolation as err:
        truong = "email" if "email" in str(err) else "username"
        raise ApiError("VALIDATION_ERROR", f"{truong} đã tồn tại",
                       errors={truong: "đã tồn tại"}) from err
    _audit(actor, ip, user_agent, action="user_update", object_type="users",
           object_id=user_id, old_value=truoc, new_value=sau)
    return user_repo.get_user(user_id)


def set_status(
    user_id: int, status: str, *, actor: dict, ip=None, user_agent=None,
    reason: str = "",
) -> dict:
    """USER-005: khoá/mở tài khoản. Khoá thì thu hồi mọi phiên đăng nhập ngay.

    FR-002: nhân viên nghỉ việc phải CHUYỂN KHÁCH trước khi khoá — còn giữ
    khách/việc thì trả CONFLICT kèm số liệu để UI chỉ chỗ.
    """
    user = user_repo.get_user(user_id)
    if not user:
        raise ApiError("NOT_FOUND", "Không tìm thấy nhân viên")
    if status == user["status"]:
        return user
    if int(actor["sub"]) == user_id and status != "active":
        raise ApiError("CONFLICT", "Không thể tự khoá tài khoản của chính mình")

    if status in ("inactive", "suspended"):
        so_huu = user_repo.dem_so_huu(user_id)
        con = {k: v for k, v in so_huu.items() if v}
        if con:
            raise ApiError(
                "CONFLICT",
                "Nhân viên còn phụ trách dữ liệu — chuyển hết cho người khác "
                "trước khi khoá (FR-002)",
                errors={k: f"còn {v}" for k, v in con.items()},
            )
        auth_repo.revoke_all_sessions(user_id)

    user_repo.set_status(user_id, status)
    _audit(actor, ip, user_agent, action="user_status", object_type="users",
           object_id=user_id, old_value={"status": user["status"]},
           new_value={"status": status}, reason=reason or None)
    return user_repo.get_user(user_id)


def reset_password(
    user_id: int, *, actor: dict, ip=None, user_agent=None
) -> dict:
    """FR-002 'Đặt lại mật khẩu': sinh mật khẩu mới + thu hồi mọi phiên của user đó.

    Trưởng nhóm chỉ reset được cho THÀNH VIÊN đội mình (không reset được
    trưởng nhóm khác hay người ngoài đội).
    """
    user = user_repo.get_user(user_id)
    if not user:
        raise ApiError("NOT_FOUND", "Không tìm thấy nhân viên")
    pham_vi = pham_vi_doi(actor)
    if pham_vi and (user["team_id"] != pham_vi["team_id"]
                    or user["role_id"] != pham_vi["role_id"]):
        raise ApiError(
            "FORBIDDEN",
            f"Chỉ đặt lại được mật khẩu của {pham_vi['role_name']} trong đội mình",
        )
    mat_khau = "Nv-" + secrets.token_urlsafe(9)
    auth_repo.update_password(user_id, security.hash_password(mat_khau))
    auth_repo.revoke_all_sessions(user_id)
    _audit(actor, ip, user_agent, action="user_reset_password",
           object_type="users", object_id=user_id,
           reason="admin cấp lại mật khẩu, thu hồi mọi phiên")
    # Mật khẩu mới chỉ trả MỘT lần ở đây — audit không lưu (xem audit_repo docstring)
    return {"id": user_id, "new_password": mat_khau}


def transfer_customers(
    tu_user: int, body: dict, *, actor: dict, ip=None, user_agent=None
) -> dict:
    """USER-006: chuyển toàn bộ khách/lead/kế hoạch chăm/việc sang người khác."""
    sang_user = body["new_owner_id"]
    if tu_user == sang_user:
        raise ApiError("VALIDATION_ERROR", "Người nhận phải khác người chuyển")
    nguoi_cu = user_repo.get_user(tu_user)
    nguoi_moi = user_repo.get_user(sang_user)
    if not nguoi_cu or not nguoi_moi:
        raise ApiError("NOT_FOUND", "Không tìm thấy nhân viên")
    if nguoi_moi["status"] != "active":
        raise ApiError("CONFLICT", "Người nhận đang bị khoá — chọn người khác")

    ket_qua = user_repo.chuyen_so_huu(
        tu_user, sang_user,
        transfer_leads=body.get("transfer_leads", True),
        transfer_care_plans=body.get("transfer_care_plans", True),
        transfer_open_tasks=body.get("transfer_open_tasks", True),
    )
    _audit(actor, ip, user_agent, action="user_transfer_customers",
           object_type="users", object_id=tu_user,
           old_value={"owner": nguoi_cu["name"]},
           new_value={"owner": nguoi_moi["name"], **ket_qua})
    return {"from": nguoi_cu["name"], "to": nguoi_moi["name"], **ket_qua}
