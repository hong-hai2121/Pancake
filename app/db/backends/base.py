"""Giao diện chung mà mọi backend lưu trữ phải cài đặt.

`app/db/repositories/queries.py` chỉ nói chuyện qua giao diện này, nên đổi nơi lưu dữ liệu
(Supabase cloud <-> SQLite trên máy) KHÔNG phải sửa một dòng nào ở brain / flow /
ui / ingestion.

Quy ước chung cho MỌI backend — cài đặt mới phải tuân thủ để hoán đổi được:

  * Vector embedding đi vào/ra dưới dạng `list[float]` Python thuần. Chuyện lưu
    thế nào (pgvector, BLOB…) là việc riêng của từng backend.
  * Cột JSON (`meta`, `ngu_canh`) đi vào/ra dưới dạng `dict` Python. Backend nào
    lưu bằng TEXT thì tự encode/decode, KHÔNG để lộ chuỗi JSON ra ngoài.
  * Hàm `match_*` trả về list dict đã XẾP HẠNG sẵn (giống nhất trước), mỗi dòng
    có thêm khoá `similarity` (0..1, càng cao càng giống), đã lọc bỏ dòng dưới
    `threshold`. Dòng chưa có embedding bị bỏ qua.
  * Toàn bộ phương thức là ĐỒNG BỘ (blocking). Lớp facade async ở queries.py chỉ
    bọc lại — giữ đúng hành vi vốn có của bản Supabase, không đổi mô hình chạy.
"""

from typing import Protocol


class Backend(Protocol):
    """Hợp đồng của một nơi lưu dữ liệu bot (3 bảng + tìm kiếm tương đồng)."""

    # ---------- chung ----------
    def count(self, table: str, only_with_embedding: bool = False) -> int:
        """Đếm số dòng của bảng (tuỳ chọn: chỉ đếm dòng đã có embedding)."""
        ...

    # ---------- kich_ban ----------
    def load_scripts(self) -> list[dict]:
        """Toàn bộ kịch bản, sắp theo `buoc`."""
        ...

    def list_scripts(self, limit: int) -> list[dict]:
        """Kịch bản cho màn quản lý — KHÔNG kèm cột embedding cho nhẹ."""
        ...

    def insert_script(self, row: dict) -> dict:
        """Thêm 1 bước kịch bản. `row['embedding']` là list[float] (có thể None)."""
        ...

    def delete_script(self, row_id: int) -> None:
        """Xoá 1 bước kịch bản theo id."""
        ...

    # ---------- hoi_thoai_mau ----------
    def insert_qa(self, row: dict) -> dict:
        """Thêm 1 cặp hỏi–đáp. `row['embedding']` là list[float] (có thể None)."""
        ...

    def list_qa_pairs(self, limit: int) -> list[dict]:
        """Cặp hỏi–đáp cho màn quản lý (mới nhất trước), không kèm embedding."""
        ...

    def delete_qa(self, row_id: int) -> None:
        """Xoá 1 cặp hỏi–đáp theo id."""
        ...

    # ---------- tìm kiếm tương đồng ----------
    def match_documents(
        self, vector: list[float], k: int, threshold: float
    ) -> list[dict]:
        """Top-k cặp hỏi–đáp gần nhất: {id, cau_hoi, cau_tra_loi, nguon, similarity}."""
        ...

    def match_scripts(
        self, vector: list[float], k: int, threshold: float
    ) -> list[dict]:
        """Top-k bước kịch bản gần nhất: {id, ten_kich_ban, buoc, noi_dung, similarity}."""
        ...

    # ---------- trang_thai_khach ----------
    def load_customer_state(self, page_id: str, psid: str) -> dict | None:
        """Phiên của 1 khách theo (page_id, psid); None nếu chưa có."""
        ...

    def upsert_customer_state(self, page_id: str, psid: str, state: dict) -> None:
        """Tạo/cập nhật phiên khách. Khoá xung đột = (page_id, psid)."""
        ...
