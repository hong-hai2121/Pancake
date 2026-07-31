"""Xử lý kịch bản Bảng 1 và chuyển tới bước tiếp theo.

Đây là nhánh "trả lời theo kịch bản có sẵn" — chạy TRƯỚC RAG/LLM trong brain.
Hiện là khung (chưa cài logic so khớp thật).
"""


def next_step(session: dict, text: str) -> str | None:
    """Trả về câu trả lời theo kịch bản, hoặc None nếu không khớp.

    Ý tưởng khi cài đặt đầy đủ (đọc/ghi phiên qua bot/session — schema đã căn):
      - Khách đang trong luồng: `session["kich_ban"]` + `session["buoc_hien_tai"]`
        cho biết đang ở bước nào; gom dữ liệu vào `session["ngu_canh"]`.
      - Chưa vào luồng: nhận diện ý định mở luồng từ `text` (từ khoá/intent), rồi
        set `kich_ban` + `buoc_hien_tai` = bước đầu.
      - Khớp `text` với điều kiện bước trong bảng `kich_ban` -> sang bước kế (cập
        nhật `buoc_hien_tai`) và trả `noi_dung` của bước đó. Không khớp -> None để
        brain nhường cho RAG.

    TODO: nạp kịch bản từ DB (app.db.repositories.queries.load_scripts) và cài logic so khớp.
    """
    return None
