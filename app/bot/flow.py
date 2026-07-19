"""Xử lý kịch bản Bảng 1 và chuyển tới bước tiếp theo.

Đây là nhánh "trả lời theo kịch bản có sẵn" — chạy TRƯỚC RAG/LLM trong brain.
Hiện là khung (chưa cài logic so khớp thật).
"""


def next_step(session: dict, text: str) -> str | None:
    """Trả về câu trả lời theo kịch bản, hoặc None nếu không khớp.

    Ý tưởng khi cài đặt đầy đủ:
      - Dựa vào `session["trang_thai"]` để biết khách đang ở bước nào.
      - So khớp `text` với điều kiện (từ khóa/intent) của các bước trong bảng
        `kich_ban`.
      - Nếu khớp: cập nhật `session["trang_thai"]` sang bước kế tiếp và trả về
        `noi_dung` của bước đó. Nếu không khớp: trả None để brain nhường cho RAG.

    TODO: nạp kịch bản từ DB (app.db.queries.load_scripts) và cài logic so khớp.
    """
    return None
