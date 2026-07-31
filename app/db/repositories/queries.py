"""Đọc/ghi dữ liệu bot — lớp DÙNG CHUNG cho mọi backend.

File này KHÔNG biết dữ liệu nằm ở đâu. Nó chỉ:
  1. chuẩn hoá tham số + gọi embedding (OpenAI) khi cần,
  2. đẩy phần lưu trữ xuống backend do `DB_BACKEND` chọn (xem app/db/backends/).

Nhờ vậy đổi Postgres local <-> Supabase cloud chỉ là đổi 1 dòng .env, mọi nơi
import từ đây (brain, flow, session, ui, ingestion) giữ nguyên không sửa gì.

Ba bảng (tên cột giống hệt nhau ở mọi backend):
  kich_ban        : ten_kich_ban, buoc(int), noi_dung, dieu_kien, buoc_tiep(int),
                    embedding, meta(json)
  hoi_thoai_mau   : cau_hoi, cau_tra_loi, nguon, embedding, meta(json)
                    (KHÔNG có cột noi_dung)
  trang_thai_khach: page_id, psid, kich_ban, buoc_hien_tai(int), ngu_canh(json),
                    trang_thai — khoá duy nhất (page_id, psid)

Các hàm là `async` để gọi được từ handler FastAPI và vì `embed()` là async;
riêng phần chạm DB vẫn đồng bộ (blocking) đúng như hành vi vốn có.
"""

from app.core.config import settings
from app.db.backends import get_backend
from app.ai.embedding import embed


def _count(table: str, only_with_embedding: bool = False) -> int:
    """Đếm số dòng của bảng (tuỳ chọn: chỉ đếm dòng đã có embedding)."""
    return get_backend().count(table, only_with_embedding)


# ---------- kich_ban ----------
async def load_scripts() -> list[dict]:
    """Lấy toàn bộ kịch bản (Bảng 1)."""
    return get_backend().load_scripts()


async def list_scripts(limit: int = 200) -> list[dict]:
    """Danh sách kịch bản cho giao diện quản lý.

    KHÔNG lấy cột `embedding` (1536 số/dòng) cho nhẹ; sắp theo (tên kịch bản, bước).
    """
    return get_backend().list_scripts(limit)


async def delete_script(row_id: int) -> None:
    """Xoá 1 bước kịch bản theo id."""
    get_backend().delete_script(row_id)


async def insert_script(
    noi_dung: str,
    ten_kich_ban: str | None = None,
    buoc: int | None = None,
    dieu_kien: str | None = None,
    buoc_tiep: int | None = None,
    meta: dict | None = None,
) -> dict:
    """Tạo embedding cho `noi_dung` rồi thêm 1 bước kịch bản vào kich_ban.

    Embedding do Python gọi OpenAI (chạy ngay trên máy chạy app) — không đổi
    theo backend, nên nằm ở đây chứ không nằm trong backend.
    """
    vector = await embed(noi_dung)
    return get_backend().insert_script(
        {
            "ten_kich_ban": ten_kich_ban,
            "buoc": buoc,
            "noi_dung": noi_dung,
            "dieu_kien": dieu_kien,
            "buoc_tiep": buoc_tiep,
            "embedding": vector,
            "meta": meta or {},
        }
    )


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
    return get_backend().insert_qa(
        {
            "cau_hoi": cau_hoi,
            "cau_tra_loi": cau_tra_loi,
            "nguon": nguon,
            "embedding": vector,
            "meta": {**(meta or {}), "embed_text": embed_text},
        }
    )


async def list_qa_pairs(limit: int = 200) -> list[dict]:
    """Danh sách cặp hỏi–đáp cho giao diện quản lý (mới nhất trước).

    KHÔNG lấy cột `embedding` cho nhẹ.
    """
    return get_backend().list_qa_pairs(limit)


async def delete_qa(row_id: int) -> None:
    """Xoá 1 cặp hỏi–đáp theo id."""
    get_backend().delete_qa(row_id)


def _k_and_threshold(k: int | None, threshold: float | None) -> tuple[int, float]:
    """Điền giá trị mặc định từ settings cho 2 tham số tìm kiếm."""
    return (
        k if k is not None else settings.rag_top_k,
        threshold if threshold is not None else settings.rag_match_threshold,
    )


async def search_similar_scripts(
    vector: list[float], k: int | None = None, threshold: float | None = None
) -> list[dict]:
    """Tìm k bước kịch bản gần nhất.

    Trả về list {id, ten_kich_ban, buoc, noi_dung, similarity} đã xếp hạng sẵn.
    """
    k, threshold = _k_and_threshold(k, threshold)
    return get_backend().match_scripts(vector, k, threshold)


async def search_similar(
    vector: list[float], k: int | None = None, threshold: float | None = None
) -> list[dict]:
    """Tìm k cặp hỏi–đáp gần nhất.

    Trả về list {id, cau_hoi, cau_tra_loi, nguon, similarity} đã xếp hạng theo
    độ tương đồng cosine (1.0 = trùng khớp). Dòng có similarity < `threshold`
    bị loại (ngưỡng 0 = không lọc).
    """
    k, threshold = _k_and_threshold(k, threshold)
    return get_backend().match_documents(vector, k, threshold)


async def debug_search(
    vector: list[float], k: int = 5, threshold: float = 0.0
) -> dict:
    """Tìm ở CẢ 2 bảng + số liệu chẩn đoán — dùng cho màn hình 'Thử tin nhắn'.

    Kèm đếm số dòng trong bảng và số dòng đã có embedding (dòng thiếu embedding
    bị bỏ qua khi tìm kiếm).
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
# Một khách = 1 dòng: nhớ đang ở kịch bản/bước nào + ngữ cảnh gom được. Dùng cho
# động cơ luồng (bot/flow) + bot tự động Tầng 2; nút "Gợi ý trả lời" hiện KHÔNG
# dùng bảng này (stateless).
async def load_customer_state(page_id: str, psid: str) -> dict | None:
    """Đọc trạng thái phiên của 1 khách theo (page_id, psid); None nếu chưa có."""
    return get_backend().load_customer_state(page_id, psid)


async def upsert_customer_state(page_id: str, psid: str, state: dict) -> None:
    """Tạo/cập nhật phiên của 1 khách. Khoá xung đột = (page_id, psid)."""
    get_backend().upsert_customer_state(page_id, psid, state)
