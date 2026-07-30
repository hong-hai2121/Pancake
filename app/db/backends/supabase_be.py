"""Backend Supabase — Postgres trên cloud, nói chuyện qua REST (PostgREST).

Đây là backend GỐC của dự án, hành vi giữ nguyên 100% so với trước khi tách lớp.

Đặc thù cần biết:
  * Cột `embedding` là pgvector -> ghi bằng chuỗi literal '[a,b,c]'.
  * PostgREST KHÔNG hỗ trợ toán tử pgvector `<=>`, nên tìm kiếm tương đồng phải
    bọc trong hàm SQL rồi gọi qua RPC (`match_documents`, `match_kich_ban` —
    xem scripts/rpc_match.sql). Nhờ vậy Postgres tự so sánh + xếp hạng và dùng
    được index HNSW, thay vì kéo cả bảng về máy.
  * Cột `meta` / `ngu_canh` là jsonb -> PostgREST tự trả về dict, không phải
    decode thêm.

Schema THẬT của DB (không phải scripts/init_db.sql):
  kich_ban        : ten_kich_ban, buoc(int), noi_dung, dieu_kien, buoc_tiep(int),
                    embedding vector(1536), meta jsonb
  hoi_thoai_mau   : cau_hoi, cau_tra_loi, nguon, embedding vector(1536), meta jsonb
                    (KHÔNG có cột noi_dung)
  trang_thai_khach: page_id, psid, kich_ban, buoc_hien_tai(int), ngu_canh jsonb,
                    trang_thai
"""

from app.db.client import get_supabase


def _pgvector(vec: list[float] | None) -> str | None:
    """Định dạng list số -> literal pgvector: [0.1,0.2,...]."""
    if vec is None:
        return None
    return "[" + ",".join(f"{x:.8g}" for x in vec) + "]"


class SupabaseBackend:
    """Cài đặt `Backend` trên Supabase REST."""

    name = "supabase"

    # ---------- hạ tầng ----------
    def _rpc(self, name: str, params: dict) -> list[dict]:
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

    def _match(self, rpc_name: str, vector, k: int, threshold: float) -> list[dict]:
        """Thân chung của 2 hàm match — chỉ khác tên RPC."""
        return self._rpc(
            rpc_name,
            {
                "query_embedding": _pgvector(vector),
                "match_count": k,
                "match_threshold": threshold,
            },
        )

    # ---------- chung ----------
    def count(self, table: str, only_with_embedding: bool = False) -> int:
        sb = get_supabase()
        q = sb.table(table).select("id", count="exact").limit(1)
        if only_with_embedding:
            q = q.not_.is_("embedding", "null")
        return q.execute().count or 0

    # ---------- kich_ban ----------
    def load_scripts(self) -> list[dict]:
        sb = get_supabase()
        res = sb.table("kich_ban").select("*").order("buoc").execute()
        return res.data or []

    def list_scripts(self, limit: int) -> list[dict]:
        # Sắp xếp theo (tên kịch bản, bước) phía Python để không phụ thuộc cú
        # pháp order nhiều cột của PostgREST.
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

    def insert_script(self, row: dict) -> dict:
        sb = get_supabase()
        payload = {**row, "embedding": _pgvector(row.get("embedding"))}
        res = sb.table("kich_ban").insert(payload).execute()
        return (res.data or [{}])[0]

    def delete_script(self, row_id: int) -> None:
        sb = get_supabase()
        sb.table("kich_ban").delete().eq("id", row_id).execute()

    # ---------- hoi_thoai_mau ----------
    def insert_qa(self, row: dict) -> dict:
        sb = get_supabase()
        payload = {**row, "embedding": _pgvector(row.get("embedding"))}
        res = sb.table("hoi_thoai_mau").insert(payload).execute()
        return (res.data or [{}])[0]

    def list_qa_pairs(self, limit: int) -> list[dict]:
        sb = get_supabase()
        res = (
            sb.table("hoi_thoai_mau")
            .select("id,cau_hoi,cau_tra_loi,nguon,created_at")
            .order("id", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    def delete_qa(self, row_id: int) -> None:
        sb = get_supabase()
        sb.table("hoi_thoai_mau").delete().eq("id", row_id).execute()

    # ---------- tìm kiếm tương đồng ----------
    def match_documents(self, vector, k: int, threshold: float) -> list[dict]:
        return self._match("match_documents", vector, k, threshold)

    def match_scripts(self, vector, k: int, threshold: float) -> list[dict]:
        return self._match("match_kich_ban", vector, k, threshold)

    # ---------- trang_thai_khach ----------
    def load_customer_state(self, page_id: str, psid: str) -> dict | None:
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

    def upsert_customer_state(self, page_id: str, psid: str, state: dict) -> None:
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
