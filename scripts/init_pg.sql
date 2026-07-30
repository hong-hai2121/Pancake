-- ============================================================
-- Schema DB bot cho Postgres cài ở máy (DB_BACKEND=postgres)
--
-- KHÔNG BẮT BUỘC chạy: app tự tạo y hệt những thứ dưới đây ở lần chạy đầu
-- (xem `_schema()` trong app/db/backends/postgres_be.py). File này để:
--   * đọc nhanh xem DB gồm những gì,
--   * hoặc tạo tay trước bằng psql khi user của app không có quyền tạo extension:
--
--       docker compose exec -T db psql -U postgres -d pancakebot < scripts/init_pg.sql
--       psql "postgresql://postgres:postgres@localhost:5432/pancakebot" -f scripts/init_pg.sql
--
-- Số chiều vector = 1536 (OpenAI text-embedding-3-small) — PHẢI khớp
-- EMBEDDING_DIM trong .env. Đổi model embedding thì sửa cả hai.
--
-- Không có hàm RPC match_* ở đây: backend postgres nối thẳng nên chạy được
-- toán tử `<=>` trong câu SELECT (rpc_match.sql chỉ dành cho Supabase/PostgREST).
-- ============================================================

create extension if not exists vector;

-- Hàm tự cập nhật updated_at
create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

-- ------------------------------------------------------------
-- Bảng 1: kich_ban  (kịch bản bán hàng nhiều bước)
-- ------------------------------------------------------------
create table if not exists kich_ban (
    id           bigint generated always as identity primary key,
    ten_kich_ban text,
    buoc         int,
    noi_dung     text        not null,
    dieu_kien    text,
    buoc_tiep    int,
    embedding    vector(1536),
    meta         jsonb       not null default '{}'::jsonb,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

-- ------------------------------------------------------------
-- Bảng 2: hoi_thoai_mau  (cặp hỏi–đáp dùng cho RAG; KHÔNG có cột noi_dung)
-- ------------------------------------------------------------
create table if not exists hoi_thoai_mau (
    id          bigint generated always as identity primary key,
    cau_hoi     text        not null,
    cau_tra_loi text        not null,
    nguon       text,
    embedding   vector(1536),
    meta        jsonb       not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);

-- ------------------------------------------------------------
-- Bảng 3: trang_thai_khach  (phiên của từng khách, khoá = page_id + psid)
-- ------------------------------------------------------------
create table if not exists trang_thai_khach (
    id            bigint generated always as identity primary key,
    page_id       text        not null,
    psid          text        not null,
    kich_ban      text,
    buoc_hien_tai int,
    ngu_canh      jsonb       not null default '{}'::jsonb,
    trang_thai    text        not null default 'active',
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (page_id, psid)
);

-- ------------------------------------------------------------
-- Index
-- ------------------------------------------------------------
create index if not exists idx_kich_ban_flow on kich_ban (ten_kich_ban, buoc);
create index if not exists idx_trang_thai_khach_lookup
    on trang_thai_khach (page_id, psid);

-- HNSW (cosine): Postgres dùng khi câu lệnh có `order by embedding <=> $1`.
create index if not exists idx_kich_ban_embedding
    on kich_ban using hnsw (embedding vector_cosine_ops);
create index if not exists idx_hoi_thoai_mau_embedding
    on hoi_thoai_mau using hnsw (embedding vector_cosine_ops);

-- ------------------------------------------------------------
-- Trigger updated_at
-- ------------------------------------------------------------
drop trigger if exists trg_kich_ban_updated on kich_ban;
create trigger trg_kich_ban_updated
    before update on kich_ban
    for each row execute function set_updated_at();

drop trigger if exists trg_trang_thai_khach_updated on trang_thai_khach;
create trigger trg_trang_thai_khach_updated
    before update on trang_thai_khach
    for each row execute function set_updated_at();
