"""Backend Postgres + pgvector — DB chạy ngay trên máy này (hoặc trong Docker).

Khác backend Supabase ở chỗ nối THẲNG tới Postgres bằng psycopg (không qua REST),
nên chạy được SQL tuỳ ý — kể cả toán tử pgvector `<=>`. Nhờ vậy KHÔNG cần hàm RPC
(`scripts/rpc_match.sql` chỉ còn cần cho Supabase): câu truy vấn tìm kiếm nằm luôn
trong file này, Postgres tự so sánh + xếp hạng + dùng index HNSW.

Những điểm cần biết:

  * Bảng TỰ TẠO ở lần dùng đầu tiên của tiến trình (xem `SCHEMA`) — cài Postgres
    xong, tạo database rỗng là chạy được, không phải chạy tay file SQL nào.
    Muốn xem/chạy tay thì dùng `scripts/init_pg.sql` (nội dung tương đương).
  * `embedding` là cột `vector(1536)`. Ghi: đổi `list[float]` -> chuỗi literal
    `'[a,b,c]'` rồi ép kiểu `%s::vector` (không cần gói `pgvector`). Đọc: chuỗi
    literal được parse ngược về `list[float]` để bên ngoài chỉ thấy list số,
    đúng hợp đồng ở `base.Backend`.
  * `meta` / `ngu_canh` là `jsonb`. psycopg 3 KHÔNG tự đổi dict -> jsonb nên phải
    bọc `Jsonb(...)` khi ghi; chiều đọc thì psycopg tự trả về `dict`.
  * Số chiều vector lấy từ `EMBEDDING_DIM` (mặc định 1536) — đổi model embedding
    thì đổi biến này TRƯỚC khi tạo bảng lần đầu.

Schema (giống hệt tên cột ở backend Supabase):
  kich_ban        : ten_kich_ban, buoc(int), noi_dung, dieu_kien, buoc_tiep(int),
                    embedding vector(dim), meta jsonb
  hoi_thoai_mau   : cau_hoi, cau_tra_loi, nguon, embedding vector(dim), meta jsonb
                    (KHÔNG có cột noi_dung)
  trang_thai_khach: page_id, psid, kich_ban, buoc_hien_tai(int), ngu_canh jsonb,
                    trang_thai — khoá duy nhất (page_id, psid)
"""

from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit

from psycopg_pool import PoolTimeout

from app.config import settings
from app.db.client import get_pg_pool

# Bảng hợp lệ cho count() — chặn tên bảng lạ ghép thẳng vào SQL.
_TABLES = ("kich_ban", "hoi_thoai_mau", "trang_thai_khach")

# Cột có kiểu vector: đọc lên phải parse chuỗi '[...]' -> list[float].
_VECTOR_COLS = ("embedding",)


def _schema(dim: int) -> str:
    """Sinh câu lệnh tạo bảng theo số chiều embedding đang cấu hình.

    Toàn bộ đều `if not exists` nên chạy lại nhiều lần vô hại. Trigger dùng
    `drop ... if exists` rồi tạo lại (`create or replace trigger` chỉ có từ PG 14).
    """
    return f"""
create extension if not exists vector;

create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create table if not exists kich_ban (
    id           bigint generated always as identity primary key,
    ten_kich_ban text,
    buoc         int,
    noi_dung     text        not null,
    dieu_kien    text,
    buoc_tiep    int,
    embedding    vector({dim}),
    meta         jsonb       not null default '{{}}'::jsonb,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create table if not exists hoi_thoai_mau (
    id          bigint generated always as identity primary key,
    cau_hoi     text        not null,
    cau_tra_loi text        not null,
    nguon       text,
    embedding   vector({dim}),
    meta        jsonb       not null default '{{}}'::jsonb,
    created_at  timestamptz not null default now()
);

create table if not exists trang_thai_khach (
    id            bigint generated always as identity primary key,
    page_id       text        not null,
    psid          text        not null,
    kich_ban      text,
    buoc_hien_tai int,
    ngu_canh      jsonb       not null default '{{}}'::jsonb,
    trang_thai    text        not null default 'active',
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (page_id, psid)
);

create index if not exists idx_kich_ban_flow on kich_ban (ten_kich_ban, buoc);
create index if not exists idx_trang_thai_khach_lookup
    on trang_thai_khach (page_id, psid);

-- Index HNSW cho cosine: Postgres dùng nó khi order by `embedding <=> $1`.
create index if not exists idx_kich_ban_embedding
    on kich_ban using hnsw (embedding vector_cosine_ops);
create index if not exists idx_hoi_thoai_mau_embedding
    on hoi_thoai_mau using hnsw (embedding vector_cosine_ops);

drop trigger if exists trg_kich_ban_updated on kich_ban;
create trigger trg_kich_ban_updated
    before update on kich_ban
    for each row execute function set_updated_at();

drop trigger if exists trg_trang_thai_khach_updated on trang_thai_khach;
create trigger trg_trang_thai_khach_updated
    before update on trang_thai_khach
    for each row execute function set_updated_at();
"""


def _pgvector(vec: list[float] | None) -> str | None:
    """list số -> literal pgvector `[a,b,c]` (None giữ nguyên None)."""
    if vec is None:
        return None
    return "[" + ",".join(f"{x:.8g}" for x in vec) + "]"


def _to_list(raw) -> list[float] | None:
    """Chiều ngược lại: literal `[a,b,c]` (hoặc list sẵn) -> list[float]."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return [float(x) for x in raw.strip("[]").split(",") if x.strip()]
    return [float(x) for x in raw]


def _offline_msg() -> str:
    """Thông báo khi không nối được Postgres — kèm việc cần làm."""
    return (
        f"Không nối được Postgres ({dsn_summary()}). Bật DB bằng "
        f"`docker compose up -d` rồi kiểm tra `docker compose ps` (phải thấy "
        f"healthy); nếu dùng Postgres cài tay thì sửa DATABASE_URL trong .env."
    )


def _clean(row: dict | None) -> dict | None:
    """Chuẩn hoá 1 dòng đọc từ DB: cột vector -> list[float].

    `jsonb` đã được psycopg trả về dạng dict nên không phải đụng tới.
    """
    if row is None:
        return None
    for col in _VECTOR_COLS:
        if col in row:
            row[col] = _to_list(row[col])
    return row


class PostgresBackend:
    """Cài đặt `Backend` trên Postgres + pgvector (kết nối trực tiếp)."""

    name = "postgres"

    def __init__(self) -> None:
        self._ready = False

    # ---------- hạ tầng ----------
    @contextmanager
    def _conn(self):
        """Mượn 1 connection từ pool, tạo bảng ở lần dùng đầu của tiến trình.

        Đổi `PoolTimeout` (xin connection quá lâu vì DB chưa bật) thành thông báo
        nói rõ phải làm gì — nếu không người dùng chỉ thấy "couldn't get a
        connection after 10.00 sec".
        """
        pool = get_pg_pool()
        if not self._ready:
            self._ensure_schema(pool)
            self._ready = True
        try:
            with pool.connection() as conn:
                yield conn
        except PoolTimeout as exc:
            raise RuntimeError(_offline_msg()) from exc

    def _ensure_schema(self, pool) -> None:
        """Chạy `SCHEMA` một lần; dịch lỗi hay gặp sang thông báo tiếng Việt."""
        sql = _schema(settings.embedding_dim)
        try:
            with pool.connection() as conn:
                conn.execute(sql)
        except PoolTimeout as exc:
            raise RuntimeError(_offline_msg()) from exc
        except Exception as exc:
            msg = str(exc)
            if "vector" in msg and ("extension" in msg or "not available" in msg):
                raise RuntimeError(
                    "Postgres đang chạy nhưng KHÔNG có extension pgvector. Dùng "
                    "image `pgvector/pgvector:pg17` (đã cài sẵn) — hoặc cài "
                    "pgvector cho bản Postgres hiện tại rồi thử lại."
                ) from exc
            raise

    def _all(self, sql: str, params: tuple | dict = ()) -> list[dict]:
        """Chạy 1 câu SELECT, trả về list dict đã chuẩn hoá."""
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_clean(r) for r in rows]

    def _one(self, sql: str, params: tuple | dict = ()) -> dict | None:
        """Chạy 1 câu SELECT/RETURNING, trả về dòng đầu (None nếu rỗng)."""
        with self._conn() as conn:
            row = conn.execute(sql, params).fetchone()
        return _clean(row)

    def _exec(self, sql: str, params: tuple | dict = ()) -> None:
        """Chạy 1 câu không cần lấy dữ liệu về (delete/upsert)."""
        with self._conn() as conn:
            conn.execute(sql, params)

    def _insert(self, table: str, row: dict) -> dict:
        """Insert 1 dòng: embedding -> `%s::vector`, cột dict -> `Jsonb`."""
        from psycopg.types.json import Jsonb

        cols, marks, vals = [], [], []
        for col, val in row.items():
            cols.append(col)
            if col == "embedding":
                marks.append("%s::vector")
                vals.append(_pgvector(val))
            elif isinstance(val, (dict, list)):
                marks.append("%s")
                vals.append(Jsonb(val))
            else:
                marks.append("%s")
                vals.append(val)

        sql = (
            f"insert into {table} ({', '.join(cols)})"
            f" values ({', '.join(marks)}) returning *"
        )
        return self._one(sql, tuple(vals)) or {}

    def _match(self, cols: str, table: str, vector, k: int, threshold: float):
        """Thân chung của 2 hàm match — chỉ khác danh sách cột + tên bảng.

        Postgres tính `1 - (embedding <=> q)` = cosine similarity, lọc theo
        ngưỡng rồi `order by embedding <=> q` (đường vào index HNSW). Dùng tham
        số theo TÊN vì vector xuất hiện 3 lần trong câu lệnh.
        """
        return self._all(
            f"""
            select {cols},
                   1 - (embedding <=> %(q)s::vector) as similarity
            from {table}
            where embedding is not null
              and 1 - (embedding <=> %(q)s::vector) >= %(th)s
            order by embedding <=> %(q)s::vector
            limit %(k)s
            """,
            {"q": _pgvector(vector), "th": threshold, "k": max(k, 0)},
        )

    # ---------- chung ----------
    def count(self, table: str, only_with_embedding: bool = False) -> int:
        if table not in _TABLES:
            raise ValueError(f"Bảng không hợp lệ: {table!r}")
        sql = f"select count(*) as n from {table}"
        if only_with_embedding:
            sql += " where embedding is not null"
        row = self._one(sql)
        return int(row["n"]) if row else 0

    # ---------- kich_ban ----------
    def load_scripts(self) -> list[dict]:
        return self._all("select * from kich_ban order by buoc")

    def list_scripts(self, limit: int) -> list[dict]:
        return self._all(
            "select id, ten_kich_ban, buoc, noi_dung, dieu_kien, buoc_tiep,"
            " created_at from kich_ban order by ten_kich_ban, buoc limit %s",
            (limit,),
        )

    def insert_script(self, row: dict) -> dict:
        return self._insert("kich_ban", row)

    def delete_script(self, row_id: int) -> None:
        self._exec("delete from kich_ban where id = %s", (row_id,))

    # ---------- hoi_thoai_mau ----------
    def insert_qa(self, row: dict) -> dict:
        return self._insert("hoi_thoai_mau", row)

    def list_qa_pairs(self, limit: int) -> list[dict]:
        return self._all(
            "select id, cau_hoi, cau_tra_loi, nguon, created_at"
            " from hoi_thoai_mau order by id desc limit %s",
            (limit,),
        )

    def delete_qa(self, row_id: int) -> None:
        self._exec("delete from hoi_thoai_mau where id = %s", (row_id,))

    # ---------- tìm kiếm tương đồng ----------
    def match_documents(self, vector, k: int, threshold: float) -> list[dict]:
        return self._match(
            "id, cau_hoi, cau_tra_loi, nguon", "hoi_thoai_mau", vector, k, threshold
        )

    def match_scripts(self, vector, k: int, threshold: float) -> list[dict]:
        return self._match(
            "id, ten_kich_ban, buoc, noi_dung", "kich_ban", vector, k, threshold
        )

    # ---------- trang_thai_khach ----------
    def load_customer_state(self, page_id: str, psid: str) -> dict | None:
        return self._one(
            "select * from trang_thai_khach where page_id = %s and psid = %s",
            (str(page_id), str(psid)),
        )

    def upsert_customer_state(self, page_id: str, psid: str, state: dict) -> None:
        from psycopg.types.json import Jsonb

        self._exec(
            """
            insert into trang_thai_khach
                (page_id, psid, kich_ban, buoc_hien_tai, ngu_canh, trang_thai)
            values (%s, %s, %s, %s, %s, %s)
            on conflict (page_id, psid) do update set
                kich_ban      = excluded.kich_ban,
                buoc_hien_tai = excluded.buoc_hien_tai,
                ngu_canh      = excluded.ngu_canh,
                trang_thai    = excluded.trang_thai,
                updated_at    = now()
            """,
            (
                str(page_id),
                str(psid),
                state.get("kich_ban"),
                state.get("buoc_hien_tai"),
                Jsonb(state.get("ngu_canh") or {}),
                state.get("trang_thai", "active"),
            ),
        )


def dsn_summary() -> str:
    """Chuỗi kết nối đã CHE mật khẩu — để hiện trên trang cấu hình."""
    url = settings.database_url
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "postgres"
    netloc = parts.netloc
    if "@" in netloc:
        userinfo, host = netloc.rsplit("@", 1)
        user = userinfo.split(":", 1)[0]
        netloc = f"{user}:***@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
