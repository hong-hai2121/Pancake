"""Xử lý kịch bản Bảng 1 và chuyển tới bước tiếp theo."""


def next_step(session: dict, text: str) -> str | None:
    """Trả về câu trả lời theo kịch bản, hoặc None nếu không khớp.

    Ý tưởng:
      - Dựa vào `session["trang_thai"]` để biết khách đang ở bước nào.
      - So khớp `text` với điều kiện của các bước trong bảng `kich_ban`.
      - Nếu khớp: cập nhật `session["trang_thai"]` sang bước kế tiếp và
        trả về nội dung trả lời. Nếu không: trả None để nhường cho RAG.

    TODO: nạp kịch bản từ DB (app.db.queries) và cài logic so khớp.
    """
    return None
