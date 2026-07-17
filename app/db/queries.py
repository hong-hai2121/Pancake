"""Đọc/ghi 3 bảng: kich_ban, hoi_thoai_mau, trang_thai_khach."""

from app.db.client import get_supabase


# ---------- trang_thai_khach ----------
async def load_customer_state(sender_id: str) -> dict | None:
    """Đọc phiên hội thoại của một khách; None nếu chưa có."""
    sb = get_supabase()
    res = (
        sb.table("trang_thai_khach")
        .select("*")
        .eq("sender_id", sender_id)
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None


async def upsert_customer_state(sender_id: str, state: dict) -> None:
    """Tạo/ cập nhật phiên hội thoại của một khách."""
    sb = get_supabase()
    sb.table("trang_thai_khach").upsert(
        {
            "sender_id": sender_id,
            "trang_thai": state.get("trang_thai", "moi"),
            "du_lieu": {"history": state.get("history", [])},
        }
    ).execute()


# ---------- kich_ban ----------
async def load_scripts() -> list[dict]:
    """Lấy toàn bộ kịch bản (Bảng 1)."""
    sb = get_supabase()
    res = sb.table("kich_ban").select("*").execute()
    return res.data or []


# ---------- hoi_thoai_mau (RAG) ----------
async def search_similar(vector: list[float], k: int = 5) -> list[dict]:
    """Tìm k đoạn gần nhất theo cosine.

    TODO: tạo RPC `match_documents` trong Postgres rồi gọi:
        sb.rpc("match_documents", {"query_embedding": vector, "match_count": k})
    Xem gợi ý hàm SQL trong scripts/init_db.sql.
    """
    raise NotImplementedError("Tạo RPC match_documents rồi gọi ở đây")
