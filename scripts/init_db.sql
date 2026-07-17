-- ============================================================
-- Khởi tạo database cho FB Sales Bot
-- Chạy trên Supabase (SQL Editor) hoặc: psql "$DATABASE_URL" -f scripts/init_db.sql
-- ============================================================

-- Bật extension pgvector
create extension if not exists vector;

-- Số chiều embedding: 768 cho Gemini text-embedding-004.
-- Nếu dùng OpenAI text-embedding-3-small thì đổi thành vector(1536).

-- ------------------------------------------------------------
-- Bảng 1: kich_ban  (kịch bản bán hàng có sẵn)
-- ------------------------------------------------------------
create table if not exists kich_ban (
    id          bigserial primary key,
    buoc        text,                 -- tên/khóa của bước
    trang_thai  text,                 -- trạng thái khách áp dụng bước này
    dieu_kien   text,                 -- điều kiện kích hoạt (từ khóa/intent)
    noi_dung    text not null,        -- câu trả lời mẫu
    embedding   vector(768),
    created_at  timestamptz default now()
);

-- ------------------------------------------------------------
-- Bảng 2: hoi_thoai_mau  (cặp hỏi–đáp chưng cất từ chat cũ)
-- ------------------------------------------------------------
create table if not exists hoi_thoai_mau (
    id          bigserial primary key,
    cau_hoi     text not null,
    cau_tra_loi text not null,
    noi_dung    text not null,        -- văn bản dùng để nhúng & so khớp
    embedding   vector(768),
    nguon       text,                 -- nguồn đoạn chat gốc
    created_at  timestamptz default now()
);

-- ------------------------------------------------------------
-- Bảng 3: trang_thai_khach  (phiên hội thoại của từng khách)
-- ------------------------------------------------------------
create table if not exists trang_thai_khach (
    sender_id   text primary key,
    trang_thai  text default 'moi',
    du_lieu     jsonb default '{}'::jsonb,   -- history, biến thu thập được...
    updated_at  timestamptz default now()
);

-- ------------------------------------------------------------
-- Index vector (cosine) cho tìm kiếm tương đồng
-- ------------------------------------------------------------
create index if not exists idx_kich_ban_embedding
    on kich_ban using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create index if not exists idx_hoi_thoai_embedding
    on hoi_thoai_mau using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- ------------------------------------------------------------
-- Hàm RPC tìm k đoạn gần nhất trong hoi_thoai_mau (dùng cho RAG)
-- Gọi từ code: sb.rpc("match_documents", {query_embedding, match_count})
-- ------------------------------------------------------------
create or replace function match_documents(
    query_embedding vector(768),
    match_count int default 5
)
returns table (id bigint, noi_dung text, similarity float)
language sql stable
as $$
    select
        id,
        noi_dung,
        1 - (embedding <=> query_embedding) as similarity
    from hoi_thoai_mau
    where embedding is not null
    order by embedding <=> query_embedding
    limit match_count;
$$;
