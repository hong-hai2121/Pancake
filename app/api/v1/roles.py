"""ROLE-001…004 + PERMISSION-001 + TEAM-001…003 (A5) — quyền `user.manage`."""

from fastapi import APIRouter, Depends, Request

from app.core.deps import require_permission
from app.core.response import ok
from app.db.repositories import org_repo
from app.schemas.user import RoleIn, RolePermissionsIn, TeamIn, TeamMembersIn
from app.services import org_service

router = APIRouter(prefix="/api/v1", tags=["roles-teams"])

_can_quyen = Depends(require_permission("user.manage"))


def _ip_ua(request: Request) -> dict:
    return {
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:300],
    }


# ------------------------------------------------------------------ vai trò
@router.get("/roles")
async def list_roles(_user: dict = _can_quyen):
    """ROLE-001 — kèm số người và danh sách quyền (đủ vẽ ma trận màn 67)."""
    return ok({"items": org_repo.list_roles()})


@router.post("/roles", status_code=201)
async def create_role(body: RoleIn, request: Request, user: dict = _can_quyen):
    """ROLE-002."""
    return ok(
        org_service.create_role(body.name, body.description, actor=user, **_ip_ua(request)),
        "Đã tạo vai trò",
    )


@router.put("/roles/{role_id}")
async def update_role(
    role_id: int, body: RoleIn, request: Request, user: dict = _can_quyen
):
    """ROLE-003."""
    return ok(
        org_service.update_role(role_id, body.name, body.description,
                                actor=user, **_ip_ua(request)),
        "Đã cập nhật vai trò",
    )


@router.put("/roles/{role_id}/permissions")
async def set_role_permissions(
    role_id: int, body: RolePermissionsIn, request: Request, user: dict = _can_quyen
):
    """ROLE-004 — THAY toàn bộ quyền; người trong vai trò nhận quyền mới ở lần
    refresh token kế (tối đa 30 phút)."""
    perms = org_service.set_role_permissions(
        role_id, body.permissions, actor=user, **_ip_ua(request)
    )
    return ok({"role_id": role_id, "permissions": perms}, "Đã gán quyền")


# ------------------------------------------------------------------ quyền
@router.get("/permissions")
async def list_permissions(_user: dict = _can_quyen):
    """PERMISSION-001."""
    return ok({"items": org_repo.list_permissions()})


# ------------------------------------------------------------------ nhóm
@router.get("/teams")
async def list_teams(_user: dict = _can_quyen):
    """TEAM-001 — kèm trưởng nhóm + số người."""
    return ok({"items": org_repo.list_teams()})


@router.post("/teams", status_code=201)
async def create_team(body: TeamIn, request: Request, user: dict = _can_quyen):
    """TEAM-002."""
    return ok(
        org_service.create_team(body.name, body.department, body.manager_id,
                                actor=user, **_ip_ua(request)),
        "Đã tạo nhóm",
    )


@router.post("/teams/{team_id}/members")
async def add_team_members(
    team_id: int, body: TeamMembersIn, request: Request, user: dict = _can_quyen
):
    """TEAM-003 — gán nhân viên vào nhóm."""
    so = org_service.add_team_members(team_id, body.user_ids, actor=user, **_ip_ua(request))
    return ok({"team_id": team_id, "da_gan": so}, f"Đã gán {so} nhân viên vào nhóm")
