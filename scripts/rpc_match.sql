-- ============================================================
-- Hàm RPC tìm kiếm vector (chạy TRONG Postgres, dùng index HNSW)
--
-- Vì PostgREST không hỗ trợ toán tử pgvector (<=>) trực tiếp, phải bọc trong
-- hàm SQL rồi gọi qua RPC. Code Python chỉ gửi vector + tham số, Postgres lo
-- phần so sánh và xếp hạng.
--
-- Chạy file này trong: Supabase Dashboard -> SQL Editor -> New query -> Run
-- ============================================================

-- ------------------------------------------------------------
-- 1) Tìm cặp hỏi–đáp gần nhất trong hoi_thoai_mau  (dùng cho RAG)
--    <=> là khoảng cách cosine; similarity = 1 - khoảng cách (1.0 = trùng khớp)
--    match_threshold: chỉ trả dòng có điểm >= ngưỡng (0 = không lọc)
-- ------------------------------------------------------------
create or replace function match_documents(
    query_embedding vector(1536),
    match_count     int   default 5,
    match_threshold float default 0.0
)
returns table (
    id          bigint,
    cau_hoi     text,
    cau_tra_loi text,
    nguon       text,
    similarity  float
)
language sql stable
as $$
    select
        id,
        cau_hoi,
        cau_tra_loi,
        nguon,
        1 - (embedding <=> query_embedding) as similarity
    from hoi_thoai_mau
    where embedding is not null
      and 1 - (embedding <=> query_embedding) >= match_threshold
    order by embedding <=> query_embedding   -- dùng index HNSW vector_cosine_ops
    limit match_count;
$$;

-- ------------------------------------------------------------
-- 2) Tìm bước kịch bản gần nhất trong kich_ban
-- ------------------------------------------------------------
create or replace function match_kich_ban(
    query_embedding vector(1536),
    match_count     int   default 5,
    match_threshold float default 0.0
)
returns table (
    id           bigint,
    ten_kich_ban text,
    buoc         int,
    noi_dung     text,
    similarity   float
)
language sql stable
as $$
    select
        id,
        ten_kich_ban,
        buoc,
        noi_dung,
        1 - (embedding <=> query_embedding) as similarity
    from kich_ban
    where embedding is not null
      and 1 - (embedding <=> query_embedding) >= match_threshold
    order by embedding <=> query_embedding
    limit match_count;
$$;
