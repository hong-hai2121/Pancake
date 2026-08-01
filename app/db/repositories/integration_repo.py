"""Truy vấn Postgres cho khu Tích hợp (BRD mục 4).

Gom 5 nhóm bảng: `integration_accounts` (kết nối) · `pages` (phần cờ đồng bộ)
· `sync_logs` (nhật ký lượt chạy) · `sync_errors` (hàng đợi lỗi/retry) ·
`staff_mappings` (nhân viên Pancake ↔ nhân viên CRM).

Quy ước như mọi repo CRM: gọi thẳng get_pg_pool() (dict_row, autocommit), viết
tay tiền tố `crm.`, update dựng động qua whitelist. Luật nghiệp vụ + audit nằm ở
app/services/integration_service.py.
"""

import json
from datetime import datetime, timedelta, timezone

from app.db.client import get_pg_pool

PROVIDERS = ("pancake_pages", "pancake_pos")
ENTITIES = ("conversation", "order", "customer", "tag", "page")

# Backoff hàng đợi lỗi: thử lại sau 5' → 15' → 45' → 2h15 → 6h45 (nhân 3),
# quá `RETRY_TOI_DA` lần thì bỏ cuộc (given_up) để người xử lý tay.
RETRY_BACKOFF_PHUT = 5
RETRY_HE_SO = 3
RETRY_TOI_DA = 5

_COT_ACCOUNT = {
    "name", "status", "token_status", "token_hint", "token_checked_at",
    "last_ok_at", "last_error", "last_error_at", "config",
}
_COT_ACCOUNT_JSONB = {"config"}


def _now():
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ kết nối
def upsert_account(
    *, provider: str, name: str, external_id: str = "", config: dict | None = None
) -> dict:
    """Tìm-hoặc-tạo kết nối theo (provider, external_id). Giữ nguyên tình trạng cũ."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.integration_accounts (provider, name, external_id, config)
            values (%s, %s, %s, %s::jsonb)
            on conflict (provider, external_id) do update set name = excluded.name
            returning *
            """,
            (provider, name, external_id, json.dumps(config or {}, ensure_ascii=False)),
        ).fetchone()


def get_account(account_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.integration_accounts where id = %s", (account_id,)
        ).fetchone()


def find_account(provider: str, external_id: str = "") -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.integration_accounts"
            " where provider = %s and external_id = %s",
            (provider, external_id),
        ).fetchone()


def list_accounts() -> list[dict]:
    """Mọi kết nối kèm số page đang gắn — dữ liệu tab Kết nối."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select a.*,
                   (select count(*) from crm.pages p where p.account_id = a.id) as so_page,
                   (select count(*) from crm.pages p
                     where p.account_id = a.id and p.sync_enabled) as so_page_bat
              from crm.integration_accounts a
             order by a.provider, a.name
            """
        ).fetchall()


def update_account(account_id: int, fields: dict) -> dict | None:
    """Cập nhật kết nối (whitelist _COT_ACCOUNT). Không có cột hợp lệ -> trả về nguyên trạng."""
    gan = {k: v for k, v in fields.items() if k in _COT_ACCOUNT}
    if not gan:
        return get_account(account_id)
    dat = ", ".join(
        f"{k} = %s::jsonb" if k in _COT_ACCOUNT_JSONB else f"{k} = %s" for k in gan
    )
    vals = [
        json.dumps(v, ensure_ascii=False) if k in _COT_ACCOUNT_JSONB and not isinstance(v, str) else v
        for k, v in gan.items()
    ]
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"update crm.integration_accounts set {dat} where id = %s returning *",
            (*vals, account_id),
        ).fetchone()


# ------------------------------------------------------------------ page
def list_pages(account_id: int | None = None) -> list[dict]:
    """Page nối vào CRM kèm số hội thoại/khách đã đổ về (tab Kết nối + Ánh xạ)."""
    where, params = "", ()
    if account_id is not None:
        where, params = "where p.account_id = %s", (account_id,)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select p.*, a.name as account_name, a.provider,
                   (select count(*) from crm.conversations c where c.page_id = p.id)
                       as so_hoi_thoai
              from crm.pages p
              left join crm.integration_accounts a on a.id = p.account_id
              {where}
             order by p.name
            """,
            params,
        ).fetchall()


def get_page(page_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute("select * from crm.pages where id = %s", (page_id,)).fetchone()


def find_page(platform: str, external_page_id: str) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.pages where platform = %s and external_page_id = %s",
            (platform, external_page_id),
        ).fetchone()


def set_page_sync(page_id: int, bat: bool) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.pages set sync_enabled = %s where id = %s returning *",
            (bat, page_id),
        ).fetchone()


def set_page_account(page_id: int, account_id: int | None) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.pages set account_id = %s where id = %s returning *",
            (account_id, page_id),
        ).fetchone()


def mark_page_synced(page_id: int, loi: str = "") -> None:
    """Đóng dấu mốc đồng bộ gần nhất của page; `loi` rỗng = xoá lỗi cũ."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            update crm.pages
               set last_synced_at = now(),
                   last_error     = nullif(%s, ''),
                   last_error_at  = case when %s = '' then null else now() end
             where id = %s
            """,
            (loi, loi, page_id),
        )


def pages_tat_dong_bo() -> set[str]:
    """external_page_id của các page bị TẮT đồng bộ — crm_sync tra trước khi ghi."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "select external_page_id from crm.pages where not sync_enabled"
        ).fetchall()
    return {r["external_page_id"] for r in rows}


def hoi_thoai_cua_khach(customer_id: int, limit: int = 20) -> list[dict]:
    """Hội thoại của 1 khách kèm external_page_id — để dựng link mở Pancake.

    Đọc DB, KHÔNG gọi Pancake (luật mục 4: không gọi API mỗi lần mở màn hình).
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select c.id, c.external_conversation_id, c.last_message_at,
                   c.external_updated_at, c.synced_at, c.snippet, c.source,
                   p.external_page_id, p.name as page_name
              from crm.conversations c
              join crm.pages p on p.id = c.page_id
             where c.customer_id = %s
             order by c.last_message_at desc nulls last
             limit %s
            """,
            (customer_id, limit),
        ).fetchall()


# ------------------------------------------------------------------ nhật ký
def bat_dau_log(
    *, provider: str, entity: str, scope: str = "", run_type: str = "poll"
) -> int:
    """Mở một dòng nhật ký trạng thái 'running'. Trả id để đóng lại sau."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.sync_logs (provider, entity, scope, run_type)
            values (%s, %s, %s, %s) returning id
            """,
            (provider, entity, scope or None, run_type),
        ).fetchone()["id"]


def ket_thuc_log(
    log_id: int, *, tao_moi: int = 0, cap_nhat: int = 0, bo_qua: int = 0,
    loi: int = 0, status: str = "", message: str = "",
) -> dict | None:
    """Đóng dòng nhật ký: đếm + thời lượng + trạng thái (tự suy nếu không truyền)."""
    if not status:
        status = "failed" if loi and not (tao_moi or cap_nhat or bo_qua) else \
                 "partial" if loi else "success"
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            update crm.sync_logs
               set finished_at   = now(),
                   duration_ms   = (extract(epoch from (now() - started_at)) * 1000)::int,
                   created_count = %s, updated_count = %s, skipped_count = %s,
                   error_count   = %s, status = %s, message = nullif(%s, '')
             where id = %s
            returning *
            """,
            (tao_moi, cap_nhat, bo_qua, loi, status, message[:1000], log_id),
        ).fetchone()


def list_logs(
    *, provider: str = "", entity: str = "", status: str = "",
    limit: int = 20, offset: int = 0,
) -> tuple[list[dict], int]:
    where, params = [], []
    if provider:
        where.append("provider = %s")
        params.append(provider)
    if entity:
        where.append("entity = %s")
        params.append(entity)
    if status:
        where.append("status = %s")
        params.append(status)
    clause = f"where {' and '.join(where)}" if where else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        total = conn.execute(
            f"select count(*) as n from crm.sync_logs {clause}", tuple(params)
        ).fetchone()["n"]
        rows = conn.execute(
            f"select * from crm.sync_logs {clause}"
            f" order by started_at desc limit %s offset %s",
            (*params, limit, offset),
        ).fetchall()
    return rows, total


def thong_ke_log(so_gio: int = 24) -> list[dict]:
    """Tổng hợp theo nguồn trong N giờ gần nhất — khối "Tình trạng đồng bộ"."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            select provider, entity,
                   count(*)                             as so_luot,
                   coalesce(sum(created_count), 0)      as tao_moi,
                   coalesce(sum(updated_count), 0)      as cap_nhat,
                   coalesce(sum(error_count), 0)        as loi,
                   max(finished_at)                     as lan_cuoi,
                   count(*) filter (where status = 'failed') as so_luot_hong
              from crm.sync_logs
             where started_at > now() - make_interval(hours => %s)
             group by provider, entity
             order by provider, entity
            """,
            (so_gio,),
        ).fetchall()


def don_log_cu(giu_ngay: int = 30) -> int:
    """Xoá nhật ký cũ hơn N ngày (bảng phình theo nhịp worker). Trả số dòng xoá."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "delete from crm.sync_logs where started_at < now() - make_interval(days => %s)",
            (giu_ngay,),
        ).rowcount


# ------------------------------------------------------------------ hàng đợi lỗi
def ghi_loi(
    *, provider: str, entity: str, external_id: str, payload: dict | None = None,
    error_type: str = "", error_message: str = "", scope: str = "",
    sync_log_id: int | None = None,
) -> dict:
    """Đưa một bản ghi hỏng vào hàng đợi. Đã có dòng đang chờ thì CỘNG số lần thử.

    Lịch thử lại giãn dần (backoff nhân 3) để lỗi hệ thống (DB sập, Pancake 429)
    không bị đập liên tục; quá RETRY_TOI_DA lần thì given_up.
    """
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.sync_errors
                (provider, entity, external_id, scope, payload, error_type,
                 error_message, sync_log_id, next_retry_at)
            values (%s, %s, %s, %s, %s::jsonb, %s, %s, %s,
                    now() + make_interval(mins => %s::int))
            on conflict (provider, entity, external_id) where status = 'pending'
            do update set
                retry_count   = crm.sync_errors.retry_count + 1,
                error_type    = excluded.error_type,
                error_message = excluded.error_message,
                payload       = case when excluded.payload = '{}'::jsonb
                                     then crm.sync_errors.payload else excluded.payload end,
                sync_log_id   = excluded.sync_log_id,
                last_tried_at = now(),
                next_retry_at = now() + make_interval(
                    mins => (%s::int * power(%s::int,
                             least(crm.sync_errors.retry_count + 1, 6))::int)::int),
                status        = case when crm.sync_errors.retry_count + 1 >= %s::int
                                     then 'given_up' else 'pending' end
            returning *
            """,
            (
                provider, entity, str(external_id), scope or None,
                json.dumps(payload or {}, ensure_ascii=False, default=str),
                error_type[:100], error_message[:1000], sync_log_id,
                RETRY_BACKOFF_PHUT,
                RETRY_BACKOFF_PHUT, RETRY_HE_SO, RETRY_TOI_DA,
            ),
        ).fetchone()


def lay_loi_toi_han(limit: int = 50, provider: str = "") -> list[dict]:
    """Các dòng lỗi đã tới hạn thử lại (hàng đợi retry của worker)."""
    where = ["status = 'pending'", "next_retry_at <= now()"]
    params: list = []
    if provider:
        where.append("provider = %s")
        params.append(provider)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"select * from crm.sync_errors where {' and '.join(where)}"
            f" order by next_retry_at limit %s",
            (*params, limit),
        ).fetchall()


def get_loi(error_id: int) -> dict | None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select * from crm.sync_errors where id = %s", (error_id,)
        ).fetchone()


def danh_dau_xong(error_id: int) -> dict | None:
    """Thử lại thành công -> đóng dòng lỗi (giữ lại để tra, không xoá)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.sync_errors set status = 'resolved', resolved_at = now(),"
            " last_tried_at = now() where id = %s returning *",
            (error_id,),
        ).fetchone()


def hen_lai(error_id: int, phut: int | None = None) -> dict | None:
    """Đặt lại lịch thử cho 1 dòng (người bấm "Thử lại" -> ngay lập tức)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "update crm.sync_errors set status = 'pending', next_retry_at = %s,"
            " resolved_at = null where id = %s returning *",
            (_now() + timedelta(minutes=phut or 0), error_id),
        ).fetchone()


def list_loi(
    *, provider: str = "", entity: str = "", status: str = "pending",
    limit: int = 20, offset: int = 0,
) -> tuple[list[dict], int]:
    where, params = [], []
    if provider:
        where.append("provider = %s")
        params.append(provider)
    if entity:
        where.append("entity = %s")
        params.append(entity)
    if status:
        where.append("status = %s")
        params.append(status)
    clause = f"where {' and '.join(where)}" if where else ""
    pool = get_pg_pool()
    with pool.connection() as conn:
        total = conn.execute(
            f"select count(*) as n from crm.sync_errors {clause}", tuple(params)
        ).fetchone()["n"]
        rows = conn.execute(
            f"select id, provider, entity, external_id, scope, error_type,"
            f" error_message, retry_count, next_retry_at, last_tried_at, status,"
            f" resolved_at, created_at, updated_at from crm.sync_errors {clause}"
            f" order by updated_at desc limit %s offset %s",
            (*params, limit, offset),
        ).fetchall()
    return rows, total


def dem_loi_dang_cho() -> int:
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            "select count(*) as n from crm.sync_errors where status = 'pending'"
        ).fetchone()["n"]


# ------------------------------------------------------------------ nhân viên
def upsert_staff(
    *, provider: str, external_staff_id: str, external_name: str = "",
    role_hint: str = "",
) -> dict:
    """Ghi nhận một nhân viên Pancake vừa gặp; giữ nguyên ánh xạ user_id đã gán."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.staff_mappings
                (provider, external_staff_id, external_name, role_hint, last_seen_at)
            values (%s, %s, nullif(%s, ''), nullif(%s, ''), now())
            on conflict (provider, external_staff_id) do update set
                external_name = coalesce(nullif(excluded.external_name, ''),
                                         crm.staff_mappings.external_name),
                role_hint     = coalesce(crm.staff_mappings.role_hint, excluded.role_hint),
                last_seen_at  = now()
            returning *
            """,
            (provider, str(external_staff_id), external_name, role_hint),
        ).fetchone()


def gan_staff(provider: str, external_staff_id: str, user_id: int | None) -> dict | None:
    """Admin gán nhân viên Pancake -> tài khoản CRM (user_id None = gỡ ánh xạ)."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            """
            insert into crm.staff_mappings (provider, external_staff_id, user_id)
            values (%s, %s, %s)
            on conflict (provider, external_staff_id)
            do update set user_id = excluded.user_id
            returning *
            """,
            (provider, str(external_staff_id), user_id),
        ).fetchone()


def map_staff(provider: str, external_staff_id: str) -> int | None:
    """external_staff_id -> users.id trong CRM; chưa ánh xạ thì None."""
    pool = get_pg_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "select user_id from crm.staff_mappings"
            " where provider = %s and external_staff_id = %s",
            (provider, str(external_staff_id)),
        ).fetchone()
    return row["user_id"] if row else None


def list_staff(provider: str = "") -> list[dict]:
    where, params = "", ()
    if provider:
        where, params = "where s.provider = %s", (provider,)
    pool = get_pg_pool()
    with pool.connection() as conn:
        return conn.execute(
            f"""
            select s.*, u.name as user_name, u.username
              from crm.staff_mappings s
              left join crm.users u on u.id = s.user_id
              {where}
             order by (s.user_id is not null), s.last_seen_at desc nulls last
            """,
            params,
        ).fetchall()
