"""Đọc/ghi bảng Supabase — bám theo SCHEMA THẬT của DB (không phải init_db.sql).

Cột thật:
  kich_ban      : ten_kich_ban, buoc(int), noi_dung, dieu_kien, buoc_tiep(int),
                  embedding vector(1536), meta jsonb
  hoi_thoai_mau : cau_hoi, cau_tra_loi, nguon, embedding vector(1536), meta jsonb
                  (KHÔNG có cột noi_dung)
  trang_thai_khach: page_id, psid, kich_ban, buoc_hien_tai(int), ngu_canh jsonb,
                  trang_thai

Cột embedding là pgvector — ghi bằng chuỗi literal '[a,b,c]'.

Tìm kiếm tương đồng chạy TRONG Postgres qua RPC (`match_documents`,
`match_kich_ban` — xem scripts/rpc_match.sql), vì PostgREST không hỗ trợ toán tử
pgvector `<=>` trực tiếp. Nhờ vậy dùng được index HNSW thay vì kéo cả bảng về.
"""

from app.config import settings
from app.db.client import get_supabase
from app.rag.embedding import embed


def _pgvector(vec: list[float]) -> str:
    """Định dạng list số -> literal pgvector: [0.1,0.2,...]."""
    return "[" + ",".join(f"{x:.8g}" for x in vec) + "]"


def _rpc(name: str, params: dict) -> list[dict]:
    """Gọi 1 hàm RPC trong Postgres; báo lỗi rõ ràng nếu hàm chưa được tạo."""
    sb = get_supabase()
    try:
        res = sb.rpc(name, params).execute()
    except Exception as exc:
        msg = str(exc)
        if "PGRST202" in msg or "Could not find the function" in msg:
            raise RuntimeError(
                f"Chưa có hàm RPC '{name}' trong Supabase. Hãy mở Supabase → "
                f"SQL Editor và chạy file scripts/rpc_match.sql rồi thử lại."
            ) from exc
        raise
    return res.data or []


def _count(table: str, only_with_embedding: bool = False) -> int:
    """Đếm số dòng của bảng (tuỳ chọn: chỉ đếm dòng đã có embedding)."""
    sb = get_supabase()
    q = sb.table(table).select("id", count="exact").limit(1)
    if only_with_embedding:
        q = q.not_.is_("embedding", "null")
    return q.execute().count or 0


# ---------- kich_ban ----------
async def load_scripts() -> list[dict]:
    """Lấy toàn bộ kịch bản (Bảng 1)."""
    sb = get_supabase()
    res = sb.table("kich_ban").select("*").order("buoc").execute()
    return res.data or []


async def list_scripts(limit: int = 200) -> list[dict]:
    """Danh sách kịch bản cho giao diện quản lý.

    KHÔNG lấy cột `embedding` (1536 số/dòng) cho nhẹ. Sắp xếp theo
    (tên kịch bản, bước) phía Python để không phụ thuộc cú pháp order nhiều cột.
    """
    sb = get_supabase()
    res = (
        sb.table("kich_ban")
        .select("id,ten_kich_ban,buoc,noi_dung,dieu_kien,buoc_tiep,created_at")
        .limit(limit)
        .execute()
    )
    rows = res.data or []
    rows.sort(key=lambda r: (r.get("ten_kich_ban") or "", r.get("buoc") or 0))
    return rows


async def delete_script(row_id: int) -> None:
    """Xoá 1 bước kịch bản theo id."""
    sb = get_supabase()
    sb.table("kich_ban").delete().eq("id", row_id).execute()


async def insert_script(
    noi_dung: str,
    ten_kich_ban: str | None = None,
    buoc: int | None = None,
    dieu_kien: str | None = None,
    buoc_tiep: int | None = None,
    meta: dict | None = None,
) -> dict:
    """Tạo embedding cho `noi_dung` rồi thêm 1 bước kịch bản vào kich_ban.

    Embedding do Python gọi OpenAI (chạy ngay trên máy chạy app), sau đó ghi
    thẳng vào bảng qua PostgREST.
    """
    vector = await embed(noi_dung)
    sb = get_supabase()
    row = {
        "ten_kich_ban": ten_kich_ban,
        "buoc": buoc,
        "noi_dung": noi_dung,
        "dieu_kien": dieu_kien,
        "buoc_tiep": buoc_tiep,
        "embedding": _pgvector(vector),
        "meta": meta or {},
    }
    res = sb.table("kich_ban").insert(row).execute()
    return (res.data or [{}])[0]


# ---------- hoi_thoai_mau (RAG) ----------
async def insert_qa(
    cau_hoi: str,
    cau_tra_loi: str,
    nguon: str | None = None,
    embed_text: str | None = None,
    meta: dict | None = None,
) -> dict:
    """Tạo embedding rồi lưu 1 cặp hỏi–đáp vào hoi_thoai_mau.

    `embed_text` = văn bản đem đi nhúng (mặc định = câu hỏi, để khớp với tin
    nhắn khách gửi tới). Bảng không có cột noi_dung nên lưu text này vào meta.
    """
    embed_text = (embed_text or cau_hoi).strip()
    vector = await embed(embed_text)
    sb = get_supabase()
    row = {
        "cau_hoi": cau_hoi,
        "cau_tra_loi": cau_tra_loi,
        "nguon": nguon,
        "embedding": _pgvector(vector),
        "meta": {**(meta or {}), "embed_text": embed_text},
    }
    res = sb.table("hoi_thoai_mau").insert(row).execute()
    return (res.data or [{}])[0]


async def list_qa_pairs(limit: int = 200) -> list[dict]:
    """Danh sách cặp hỏi–đáp cho giao diện quản lý (mới nhất trước).

    KHÔNG lấy cột `embedding` cho nhẹ.
    """
    sb = get_supabase()
    res = (
        sb.table("hoi_thoai_mau")
        .select("id,cau_hoi,cau_tra_loi,nguon,created_at")
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


async def delete_qa(row_id: int) -> None:
    """Xoá 1 cặp hỏi–đáp theo id."""
    sb = get_supabase()
    sb.table("hoi_thoai_mau").delete().eq("id", row_id).execute()


async def search_similar_scripts(
    vector: list[float], k: int | None = None, threshold: float | None = None
) -> list[dict]:
    """Tìm k bước kịch bản gần nhất — RPC `match_kich_ban` chạy trong Postgres.

    Trả về list {id, ten_kich_ban, buoc, noi_dung, similarity} (đã xếp hạng sẵn).
    """
    return _rpc(
        "match_kich_ban",
        {
            "query_embedding": _pgvector(vector),
            "match_count": k if k is not None else settings.rag_top_k,
            "match_threshold": (
                threshold if threshold is not None else settings.rag_match_threshold
            ),
        },
    )


async def search_similar(
    vector: list[float], k: int | None = None, threshold: float | None = None
) -> list[dict]:
    """Tìm k cặp hỏi–đáp gần nhất — RPC `match_documents` chạy trong Postgres.

    Postgres so sánh bằng toán tử cosine `<=>` và dùng index HNSW, rồi trả về
    list {id, cau_hoi, cau_tra_loi, nguon, similarity} đã xếp hạng.
    Dòng có similarity < `threshold` bị loại (ngưỡng 0 = không lọc).
    """
    return _rpc(
        "match_documents",
        {
            "query_embedding": _pgvector(vector),
            "match_count": k if k is not None else settings.rag_top_k,
            "match_threshold": (
                threshold if threshold is not None else settings.rag_match_threshold
            ),
        },
    )


async def debug_search(
    vector: list[float], k: int = 5, threshold: float = 0.0
) -> dict:
    """Tìm ở CẢ 2 bảng + số liệu chẩn đoán — dùng cho màn hình 'Thử tin nhắn'.

    Gọi 2 RPC (Postgres tự so sánh & xếp hạng), kèm đếm số dòng trong bảng và số
    dòng đã có embedding (dòng thiếu embedding bị hàm SQL bỏ qua).
    """
    return {
        "qa": await search_similar(vector, k=k, threshold=threshold),
        "scripts": await search_similar_scripts(vector, k=k, threshold=threshold),
        "qa_total": _count("hoi_thoai_mau"),
        "qa_with_emb": _count("hoi_thoai_mau", only_with_embedding=True),
        "kb_total": _count("kich_ban"),
        "kb_with_emb": _count("kich_ban", only_with_embedding=True),
        "threshold": threshold,
    }


# ---------- trang_thai_khach (phiên khách cho LUỒNG nhiều bước) ----------
# Schema thật: (page_id, psid, kich_ban, buoc_hien_tai int, ngu_canh jsonb,
# trang_thai) — khoá duy nhất (page_id, psid). Một khách = 1 dòng: nhớ đang ở kịch
# bản/bước nào + ngữ cảnh gom được. Dùng cho động cơ luồng (bot/flow) + bot tự động
# Tầng 2; nút "Gợi ý trả lời" hiện KHÔNG dùng bảng này (stateless).
async def load_customer_state(page_id: str, psid: str) -> dict | None:
    """Đọc trạng thái phiên của 1 khách theo (page_id, psid); None nếu chưa có."""
    sb = get_supabase()
    res = (
        sb.table("trang_thai_khach")
        .select("*")
        .eq("page_id", str(page_id))
        .eq("psid", str(psid))
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None


async def upsert_customer_state(page_id: str, psid: str, state: dict) -> None:
    """Tạo/cập nhật phiên của 1 khách. Khoá xung đột = (page_id, psid)."""
    sb = get_supabase()
    sb.table("trang_thai_khach").upsert(
        {
            "page_id": str(page_id),
            "psid": str(psid),
            "kich_ban": state.get("kich_ban"),
            "buoc_hien_tai": state.get("buoc_hien_tai"),
            "ngu_canh": state.get("ngu_canh") or {},
            "trang_thai": state.get("trang_thai", "active"),
        },
        on_conflict="page_id,psid",
    ).execute()
