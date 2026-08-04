"""Kho ĐỊNH NGHĨA THẺ của Pancake — bảng `watcher.the_pancake`.

VÌ SAO CẦN KHO NÀY: tên + màu thẻ chỉ lấy được qua public API, mà đường đó có
hai chỗ đứt:

  * Cần `page_access_token` (chỉ page có quyền Admin mới sinh được). Mất quyền,
    token bị thu hồi hay Pancake lỗi mạng là `list_tags` trả {} — màn Tin nhắn
    tụt về "Thẻ #175", người dùng thấy tên thẻ **nhảy thành số** giữa chừng.
  * Hộp thư GỘP đọc hội thoại từ kho chứ không gọi Pancake, nên nếu chỉ dựa vào
    lời gọi lúc render thì chế độ gộp chẳng bao giờ có tên thẻ để hiện.

Lưu lại một bản trong Postgres giải quyết cả hai: API hỏng thì đọc kho, và mọi
page từng lấy được thẻ đều tra cứu được ngay không tốn lời gọi nào.

Kho này là BẢN SAO, không phải nguồn sự thật: mỗi lần gọi public API thành công
là ghi đè lại (xem `list_tags` trong app/pancake/client.py). Nhờ vậy đổi tên thẻ
trên Pancake thì chậm nhất một nhịp cache là hiện đúng — khác hẳn cách khai báo
tay `TAG_OVERRIDES`, càng dùng càng lệch.

KHÔNG xoá dòng của thẻ đã bị xoá trên Pancake: hội thoại cũ vẫn còn gắn ID đó,
giữ lại thì nhìn vào còn biết thẻ ấy tên gì, xoá đi là mất luôn.

Khoá chính `(page_id, tag_id)` — thẻ là dữ liệu RIÊNG của từng page, cùng số ID
ở 2 page là 2 thẻ khác nhau, nên không bao giờ được tra cứu bằng mỗi `tag_id`.
"""

from app.db.client import get_pg_pool

SCHEMA = "watcher"
TABLE = f"{SCHEMA}.the_pancake"
# Bảng MỐC ĐỒNG BỘ, tách khỏi bảng thẻ vì hai câu hỏi khác nhau:
#   `the_pancake.updated_at`  = "thẻ này đổi tên lúc nào" (chỉ nhích khi tên đổi)
#   `the_pancake_dong_bo.luc` = "lần cuối mình HỎI Pancake page này là lúc nào"
# Không có bảng dưới thì không cách nào biết đã hỏi chưa — lịch "1 ngày 1 lần"
# nằm trong RAM sẽ reset mỗi lần restart, chạy --reload là gọi API liên tục.
SYNC = f"{SCHEMA}.the_pancake_dong_bo"

_ready = False


def _conn():
    """Mượn connection từ pool dùng chung, tạo bảng ở lần dùng đầu của tiến trình."""
    global _ready
    pool = get_pg_pool()
    if not _ready:
        with pool.connection() as conn:
            conn.execute(f"create schema if not exists {SCHEMA}")
            conn.execute(
                f"""
                create table if not exists {TABLE} (
                    page_id       text        not null,
                    tag_id        integer     not null,
                    ten           text        not null,
                    mau           text        not null default '',
                    first_seen_at timestamptz not null default now(),
                    updated_at    timestamptz not null default now(),
                    primary key (page_id, tag_id)
                )
                """
            )
            conn.execute(
                f"""
                create table if not exists {SYNC} (
                    page_id text        not null primary key,
                    luc     timestamptz not null default now(),
                    so_the  integer     not null default 0,
                    nguon   text        not null default '',
                    loi     text        not null default ''
                )
                """
            )
        _ready = True
    return pool.connection()


def ghi_moc(page_id: str, so_the: int, nguon: str = "", loi: str = "") -> None:
    """Đánh dấu vừa HỎI Pancake page này — kể cả khi hỏi hụt (`loi`).

    Ghi cả lượt hụt là cố ý: page thiếu quyền mà không đánh dấu thì cứ mỗi vòng
    poller lại hỏi lại, đúng thứ đang muốn tránh. Có mốc thì nó cũng phải chờ
    tới hạn như page thành công.
    """
    with _conn() as conn:
        conn.execute(
            f"""
            insert into {SYNC} (page_id, luc, so_the, nguon, loi)
            values (%s, now(), %s, %s, %s)
            on conflict (page_id) do update set
                luc = now(), so_the = excluded.so_the,
                nguon = excluded.nguon, loi = excluded.loi
            """,
            (str(page_id), int(so_the), nguon[:40], loi[:200]),
        )


def doc_moc() -> dict[str, dict]:
    """Mốc đồng bộ của mọi page -> {page_id: {luc, so_the, nguon, loi}}."""
    with _conn() as conn:
        rows = conn.execute(
            f"select page_id, luc, so_the, nguon, loi from {SYNC}"
        ).fetchall()
    return {r["page_id"]: dict(r) for r in rows}


def qua_han(page_id: str, giay: float) -> bool:
    """Page này đã tới hạn hỏi lại chưa? Chưa từng hỏi -> True."""
    with _conn() as conn:
        row = conn.execute(
            f"select extract(epoch from (now() - luc)) as tuoi from {SYNC}"
            " where page_id = %s",
            (str(page_id),),
        ).fetchone()
    return not row or float(row["tuoi"] or 0) >= giay


def upsert_tags(page_id: str, tags: dict[int, dict]) -> int:
    """Ghi/cập nhật định nghĩa thẻ của 1 page. Trả về số thẻ đã gửi xuống DB.

    `tags` = {tag_id: {'text', 'color'}} — đúng shape `list_tags` trả về.

    `updated_at` chỉ nhích khi tên/màu THẬT SỰ đổi (nhờ mệnh đề `where` ở cuối):
    nhìn cột đó là biết thẻ nào vừa được đổi tên trên Pancake, chứ không phải
    dấu vết của lần đồng bộ gần nhất — lần đồng bộ nào cũng có nên vô nghĩa.
    """
    rows = [
        (
            str(page_id), int(tid),
            (meta.get("text") or "").strip() or f"Thẻ #{tid}",
            meta.get("color") or "",
        )
        for tid, meta in (tags or {}).items()
    ]
    if not rows:
        return 0
    with _conn() as conn, conn.cursor() as cur:
        cur.executemany(
            f"""
            insert into {TABLE} (page_id, tag_id, ten, mau)
            values (%s, %s, %s, %s)
            on conflict (page_id, tag_id) do update set
                ten        = excluded.ten,
                mau        = excluded.mau,
                updated_at = now()
            where {TABLE}.ten is distinct from excluded.ten
               or {TABLE}.mau is distinct from excluded.mau
            """,
            rows,
        )
    return len(rows)


def load_tags(page_id: str) -> dict[int, dict]:
    """Thẻ đã lưu của 1 page -> {tag_id: {'text', 'color'}} (shape của `list_tags`)."""
    with _conn() as conn:
        rows = conn.execute(
            f"select tag_id, ten, mau from {TABLE} where page_id = %s",
            (str(page_id),),
        ).fetchall()
    return {r["tag_id"]: {"text": r["ten"], "color": r["mau"] or ""} for r in rows}


def load_all_tags() -> dict[str, dict[int, dict]]:
    """Thẻ của MỌI page -> {page_id: {tag_id: {'text','color'}}}.

    Hộp thư GỘP dùng cái này: mỗi hội thoại tra thẻ theo ĐÚNG page của nó, nên
    hai page có cùng số ID thẻ vẫn hiện đúng tên của từng bên.
    """
    with _conn() as conn:
        rows = conn.execute(
            f"select page_id, tag_id, ten, mau from {TABLE}"
        ).fetchall()
    out: dict[str, dict[int, dict]] = {}
    for r in rows:
        out.setdefault(r["page_id"], {})[r["tag_id"]] = {
            "text": r["ten"], "color": r["mau"] or "",
        }
    return out


def stats() -> dict:
    """Số thẻ đang lưu + số page có thẻ + lần đổi tên gần nhất (cho Bảng điều khiển)."""
    with _conn() as conn:
        row = conn.execute(
            f"""
            select count(*)                as tong,
                   count(distinct page_id) as so_page,
                   max(updated_at)         as lan_cuoi
            from {TABLE}
            """
        ).fetchone()
    return dict(row or {"tong": 0, "so_page": 0, "lan_cuoi": None})
