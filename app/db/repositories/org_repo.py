"""SQL vai trò / quyền / nhóm (A5 — ROLE-001…004, PERMISSION-001, TEAM-001…003)."""

from app.db.client import get_pg_pool


# ------------------------------------------------------------------ vai trò
def list_roles() -> list[dict]:
    """Kèm số người dùng + danh sách mã quyền của từng vai trò (cho ma trận màn 67)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select r.id, r.name, r.description,
                   (select count(*) from crm.users u where u.role_id = r.id) as so_nguoi,
                   coalesce((select array_agg(p.code order by p.code)
                               from crm.role_permissions rp
                               join crm.permissions p on p.id = rp.permission_id
                              where rp.role_id = r.id), '{}') as perms
              from crm.roles r
             order by r.id
            """
        ).fetchall()


def get_role(role_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select id, name, description from crm.roles where id = %s", (role_id,)
        ).fetchone()


def create_role(name: str, description: str | None) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.roles (name, description) values (%s, %s) "
            "returning id, name, description",
            (name, description),
        ).fetchone()


def update_role(role_id: int, name: str, description: str | None) -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.roles set name = %s, description = %s where id = %s",
            (name, description, role_id),
        )


def set_role_permissions(role_id: int, perm_codes: list[str]) -> list[str]:
    """ROLE-004: thay TOÀN BỘ quyền của vai trò = danh sách đưa vào.

    Xoá hết rồi chèn lại trong 1 transaction — đơn giản và không để sót; trả về
    danh sách mã đã gán thật (mã lạ bị bỏ qua im lặng thì nguy hiểm nên trả ra
    cho service đối chiếu).
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute(
                "delete from crm.role_permissions where role_id = %s", (role_id,)
            )
            rows = conn.execute(
                """
                insert into crm.role_permissions (role_id, permission_id)
                select %s, p.id from crm.permissions p where p.code = any(%s)
                returning (select code from crm.permissions where id = permission_id)
                """,
                (role_id, perm_codes),
            ).fetchall()
    return [r["code"] for r in rows]


# ------------------------------------------------------------------ quyền
def list_permissions() -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select id, code, name from crm.permissions order by code"
        ).fetchall()


# ------------------------------------------------------------------ nhóm
def list_teams() -> list[dict]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select t.id, t.name, t.department, t.manager_id, m.name as manager_name,
                   (select count(*) from crm.users u where u.team_id = t.id) as so_nguoi
              from crm.teams t
              left join crm.users m on m.id = t.manager_id
             order by t.name
            """
        ).fetchall()


def create_team(name: str, department: str | None, manager_id: int | None) -> dict:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "insert into crm.teams (name, department, manager_id) values (%s, %s, %s) "
            "returning id, name, department, manager_id",
            (name, department, manager_id),
        ).fetchone()


def add_team_members(team_id: int, user_ids: list[int]) -> int:
    """TEAM-003: gán nhân viên vào nhóm (users.team_id). Trả số người đã gán."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.users set team_id = %s where id = any(%s)",
            (team_id, user_ids),
        ).rowcount
