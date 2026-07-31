"""Nghiệp vụ vai trò / quyền / nhóm (A5 — FR-003). KHÔNG import FastAPI.

Luật FR-003: mọi thay đổi quyền phải có audit log — cài ở đây, một chỗ duy nhất.
"""

from psycopg.errors import UniqueViolation

from app.core.errors import ApiError
from app.db.repositories import audit_repo, org_repo


def _audit(actor: dict | None, ip, ua, **kw) -> None:
    audit_repo.ghi(
        user_id=int(actor["sub"]) if actor else None, ip=ip, user_agent=ua, **kw
    )


def create_role(
    name: str, description: str | None, *, actor: dict, ip=None, user_agent=None
) -> dict:
    try:
        role = org_repo.create_role(name, description)
    except UniqueViolation as err:
        raise ApiError("VALIDATION_ERROR", "Tên vai trò đã tồn tại",
                       errors={"name": "đã tồn tại"}) from err
    _audit(actor, ip, user_agent, action="role_create", object_type="roles",
           object_id=role["id"], new_value={"name": name})
    return role


def update_role(
    role_id: int, name: str, description: str | None,
    *, actor: dict, ip=None, user_agent=None,
) -> dict:
    cu = org_repo.get_role(role_id)
    if not cu:
        raise ApiError("NOT_FOUND", "Không tìm thấy vai trò")
    try:
        org_repo.update_role(role_id, name, description)
    except UniqueViolation as err:
        raise ApiError("VALIDATION_ERROR", "Tên vai trò đã tồn tại",
                       errors={"name": "đã tồn tại"}) from err
    _audit(actor, ip, user_agent, action="role_update", object_type="roles",
           object_id=role_id,
           old_value={"name": cu["name"], "description": cu["description"]},
           new_value={"name": name, "description": description})
    return org_repo.get_role(role_id)


def set_role_permissions(
    role_id: int, perm_codes: list[str], *, actor: dict, ip=None, user_agent=None
) -> list[str]:
    """ROLE-004. Đổi quyền có audit cũ/mới (FR-003); mã quyền lạ -> báo lỗi rõ."""
    role = org_repo.get_role(role_id)
    if not role:
        raise ApiError("NOT_FOUND", "Không tìm thấy vai trò")
    hop_le = {p["code"] for p in org_repo.list_permissions()}
    la = sorted(set(perm_codes) - hop_le)
    if la:
        raise ApiError("VALIDATION_ERROR", f"Mã quyền không tồn tại: {', '.join(la)}",
                       errors={m: "không tồn tại" for m in la})
    cu = next((r["perms"] for r in org_repo.list_roles() if r["id"] == role_id), [])
    moi = org_repo.set_role_permissions(role_id, perm_codes)
    _audit(actor, ip, user_agent, action="role_set_permissions",
           object_type="roles", object_id=role_id,
           old_value={"perms": sorted(cu)}, new_value={"perms": sorted(moi)},
           reason=f"vai trò: {role['name']}")
    # Lưu ý vận hành: quyền nằm trong access token nên người thuộc vai trò này
    # nhận quyền mới ở lần refresh/đăng nhập kế (tối đa 30 phút).
    return moi


def create_team(
    name: str, department: str | None, manager_id: int | None,
    *, actor: dict, ip=None, user_agent=None,
) -> dict:
    try:
        team = org_repo.create_team(name, department, manager_id)
    except UniqueViolation as err:
        raise ApiError("VALIDATION_ERROR", "Tên nhóm đã tồn tại",
                       errors={"name": "đã tồn tại"}) from err
    _audit(actor, ip, user_agent, action="team_create", object_type="teams",
           object_id=team["id"], new_value={"name": name, "department": department})
    return team


def add_team_members(
    team_id: int, user_ids: list[int], *, actor: dict, ip=None, user_agent=None
) -> int:
    so = org_repo.add_team_members(team_id, user_ids)
    if so == 0:
        raise ApiError("NOT_FOUND", "Không nhân viên nào khớp danh sách id")
    _audit(actor, ip, user_agent, action="team_add_members", object_type="teams",
           object_id=team_id, new_value={"user_ids": user_ids, "da_gan": so})
    return so
