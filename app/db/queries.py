"""Đọc/ghi bảng Supabase — bám theo SCHEMA THẬT của DB (không phải init_db.sql).

Cột thật:
  kich_ban      : ten_kich_ban, buoc(int), noi_dung, dieu_kien, buoc_tiep(int),
                  embedding vector(1536), meta jsonb
  hoi_thoai_mau : cau_hoi, cau_tra_loi, nguon, embedding vector(1536), meta jsonb
                  (KHÔNG có cột noi_dung)
  trang_thai_khach: page_id, psid, kich_ban, buoc_hien_tai(int), ngu_canh jsonb,
                  trang_thai

Cột embedding là pgvector — ghi bằng chuỗi literal '[a,b,c]'.
"""

import json
import math

from app.db.client import get_supabase
from app.rag.embedding import embed


def _pgvector(vec: list[float]) -> str:
    """Định dạng list số -> literal pgvector: [0.1,0.2,...]."""
    return "[" + ",".join(f"{x:.8g}" for x in vec) + "]"


def _parse_vec(value) -> list[float]:
    """pgvector trả về từ PostgREST thường là chuỗi '[...]'; parse về list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return []


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else -1.0


# ---------- kich_ban ----------
async def load_scripts() -> list[dict]:
    """Lấy toàn bộ kịch bản (Bảng 1)."""
    sb = get_supabase()
    res = sb.table("kich_ban").select("*").order("buoc").execute()
    return res.data or []


async def insert_script(
    noi_dung: str,
    ten_kich_ban: str | None = None,
    buoc: int | None = None,
    dieu_kien: str | None = None,
    buoc_tiep: int | None = None,
    meta: dict | None = None,
) -> dict:
    """Tạo embedding cho `noi_dung` rồi thêm 1 bước kịch bản vào kich_ban."""
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
    """Lưu 1 cặp hỏi–đáp kèm embedding vào hoi_thoai_mau.

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


async def search_similar(vector: list[float], k: int = 5) -> list[dict]:
    """Tìm k cặp hỏi–đáp gần nhất theo cosine.

    Tính phía Python (DB chưa có RPC match_documents). Đủ nhanh cho bảng Q&A
    cỡ nhỏ; khi dữ liệu lớn nên thay bằng RPC pgvector (xem README/init_db.sql).
    Trả về list {cau_hoi, cau_tra_loi, similarity}.
    """
    sb = get_supabase()
    res = sb.table("hoi_thoai_mau").select(
        "cau_hoi,cau_tra_loi,embedding"
    ).execute()
    scored = []
    for r in res.data or []:
        emb = _parse_vec(r.get("embedding"))
        if not emb:
            continue
        scored.append(
            {
                "cau_hoi": r.get("cau_hoi"),
                "cau_tra_loi": r.get("cau_tra_loi"),
                "similarity": _cosine(vector, emb),
            }
        )
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:k]


# ---------- trang_thai_khach ----------
# ⚠️ CHÚ Ý: schema THẬT của bảng này là (page_id, psid, kich_ban, buoc_hien_tai,
# ngu_canh, trang_thai) — KHÁC với code session.py hiện dùng (sender_id, du_lieu).
# Giữ nguyên bản cũ để không làm gãy luồng bot webhook; việc căn lại theo schema
# thật là một task riêng (xem tóm tắt / follow-up), không thuộc phần RAG này.
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
