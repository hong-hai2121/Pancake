"""Route giao diện quản lý dữ liệu bot: kịch bản + hội thoại mẫu.

Gắn ở prefix /data. Mỗi lần thêm sẽ tự tạo embedding (gọi OpenAI) rồi ghi
Supabase; xong thì redirect 303 về lại trang kèm thông báo ok/error.
"""

from urllib.parse import parse_qs, urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.config import settings

from app.db.repositories.queries import (
    debug_search,
    delete_qa,
    delete_script,
    insert_qa,
    insert_script,
    list_qa_pairs,
    list_scripts,
)
from app.ai.brain import choose_reply
from app.ai.prompt import build_prompt
from app.ai.embedding import embed
from app.ai.llm import complete
from app.integrations.pancake.client import PancakeError, list_pages, raw_call
from app.web.views.data import (
    render_api_test,
    render_error,
    render_qa,
    render_scripts,
    render_simulate,
)

router = APIRouter(prefix="/data", tags=["data"])


async def _form(request: Request) -> dict[str, str]:
    """Đọc body form (application/x-www-form-urlencoded) -> dict giá trị đầu tiên."""
    raw = parse_qs((await request.body()).decode("utf-8"))
    return {k: (v[0] if v else "").strip() for k, v in raw.items()}


def _back(path: str, ok: str = "", error: str = "") -> RedirectResponse:
    """Redirect 303 về `path` kèm thông báo (tránh gửi lại form khi F5)."""
    params = {}
    if ok:
        params["ok"] = ok
    if error:
        params["error"] = error
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"{path}{query}", status_code=303)


def _to_int(value: str, field: str, required: bool) -> int | None:
    """Ép chuỗi form -> int; ném ValueError với thông báo tiếng Việt nếu sai."""
    if not value:
        if required:
            raise ValueError(f"Thiếu {field}")
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{field} phải là số nguyên") from None


@router.get("", response_class=HTMLResponse)
async def index() -> RedirectResponse:
    """Vào /data thì chuyển thẳng sang màn hình Kịch bản."""
    return RedirectResponse("/data/kich-ban", status_code=307)


# ---------------------------------------------------------------- kịch bản
@router.get("/kich-ban", response_class=HTMLResponse)
async def scripts_page(ok: str = "", error: str = "") -> HTMLResponse:
    """Màn hình Kịch bản: form thêm bước + danh sách các bước hiện có."""
    try:
        rows = await list_scripts()
    except Exception as exc:  # lỗi Supabase/cấu hình -> hiện trang lỗi
        return HTMLResponse(render_error(str(exc)[:300]), status_code=502)
    return HTMLResponse(render_scripts(rows, ok=ok, error=error))


@router.post("/kich-ban")
async def add_script(request: Request) -> RedirectResponse:
    """Thêm 1 bước kịch bản: kiểm tra dữ liệu -> tạo embedding -> ghi DB."""
    f = await _form(request)
    try:
        ten = f.get("ten_kich_ban") or ""
        noi_dung = f.get("noi_dung") or ""
        if not ten:
            raise ValueError("Thiếu tên kịch bản")
        if not noi_dung:
            raise ValueError("Thiếu nội dung")
        buoc = _to_int(f.get("buoc", ""), "bước", required=True)
        buoc_tiep = _to_int(f.get("buoc_tiep", ""), "bước tiếp", required=False)

        await insert_script(
            noi_dung=noi_dung,
            ten_kich_ban=ten,
            buoc=buoc,
            dieu_kien=f.get("dieu_kien") or None,
            buoc_tiep=buoc_tiep,
        )
    except ValueError as exc:                 # lỗi nhập liệu
        return _back("/data/kich-ban", error=str(exc))
    except Exception as exc:                  # lỗi embedding/DB (vd trùng bước)
        msg = str(exc)
        if "duplicate key" in msg or "unique" in msg.lower():
            msg = "Bước này đã tồn tại trong kịch bản (trùng tên + bước)"
        return _back("/data/kich-ban", error=msg[:200])
    return _back("/data/kich-ban", ok=f"Đã thêm bước {buoc} vào '{ten}'")


@router.post("/kich-ban/{row_id}/xoa")
async def remove_script(row_id: int) -> RedirectResponse:
    """Xoá 1 bước kịch bản theo id."""
    try:
        await delete_script(row_id)
    except Exception as exc:
        return _back("/data/kich-ban", error=str(exc)[:200])
    return _back("/data/kich-ban", ok="Đã xoá 1 bước kịch bản")


# ------------------------------------------------------------ hội thoại mẫu
@router.get("/hoi-thoai", response_class=HTMLResponse)
async def qa_page(ok: str = "", error: str = "") -> HTMLResponse:
    """Màn hình Hội thoại mẫu: form thêm cặp hỏi–đáp + danh sách hiện có."""
    try:
        rows = await list_qa_pairs()
    except Exception as exc:
        return HTMLResponse(render_error(str(exc)[:300]), status_code=502)
    return HTMLResponse(render_qa(rows, ok=ok, error=error))


@router.post("/hoi-thoai")
async def add_qa(request: Request) -> RedirectResponse:
    """Thêm 1 cặp hỏi–đáp: kiểm tra -> tạo embedding cho câu hỏi -> ghi DB."""
    f = await _form(request)
    try:
        cau_hoi = f.get("cau_hoi") or ""
        cau_tra_loi = f.get("cau_tra_loi") or ""
        if not cau_hoi:
            raise ValueError("Thiếu câu hỏi")
        if not cau_tra_loi:
            raise ValueError("Thiếu câu trả lời")

        await insert_qa(
            cau_hoi=cau_hoi,
            cau_tra_loi=cau_tra_loi,
            nguon=f.get("nguon") or None,
        )
    except ValueError as exc:
        return _back("/data/hoi-thoai", error=str(exc))
    except Exception as exc:
        return _back("/data/hoi-thoai", error=str(exc)[:200])
    return _back("/data/hoi-thoai", ok="Đã thêm 1 cặp hỏi–đáp (kèm embedding)")


@router.post("/hoi-thoai/{row_id}/xoa")
async def remove_qa(row_id: int) -> RedirectResponse:
    """Xoá 1 cặp hỏi–đáp theo id."""
    try:
        await delete_qa(row_id)
    except Exception as exc:
        return _back("/data/hoi-thoai", error=str(exc)[:200])
    return _back("/data/hoi-thoai", ok="Đã xoá 1 cặp hỏi–đáp")


# ------------------------------------------------------------ thử tin nhắn
@router.get("/thu-tin-nhan", response_class=HTMLResponse)
async def simulate_page(
    q: str = "", k: int = 5, threshold: float | None = None, tra_loi: int = 0
) -> HTMLResponse:
    """Mô phỏng tin khách: embed câu hỏi -> gọi RPC để Postgres chấm điểm.

    Không ghi gì (chỉ ĐỌC). Mặc định KHÔNG gọi LLM; nếu `tra_loi=1` thì ghép
    ngữ cảnh tìm được thành prompt rồi gọi gpt-4o-mini để xem câu trả lời thật.
    Dùng GET (?q=&k=&threshold=&tra_loi=) để tải lại / chia sẻ link kết quả.
    """
    q = (q or "").strip()
    k = max(1, min(k, 20))
    # Không truyền ngưỡng -> lấy mặc định trong .env (RAG_MATCH_THRESHOLD).
    thr = settings.rag_match_threshold if threshold is None else threshold
    thr = max(0.0, min(thr, 1.0))
    want_answer = bool(tra_loi)

    if not q:
        # Chưa nhập gì -> chỉ hiện form trống.
        return HTMLResponse(
            render_simulate(q="", k=k, threshold=thr, tra_loi=want_answer)
        )
    try:
        vector = await embed(q)                              # OpenAI -> vector
        result = await debug_search(vector, k=k, threshold=thr)  # RPC -> Postgres tính
    except Exception as exc:
        return HTMLResponse(
            render_simulate(
                q=q, k=k, threshold=thr, tra_loi=want_answer, error=str(exc)[:300]
            ),
            status_code=502,
        )

    # Tuỳ chọn: gọi LLM. Hai ô độc lập để đối chiếu:
    #  - Bước 4 (cũ): trả lời TỰ DO — ghép toàn bộ ngữ cảnh rồi để LLM tự viết.
    #  - Bước 5 (mới): GIỐNG nút "Gợi ý trả lời" — GPT CHỌN từ top 3 câu mẫu, không
    #    hợp thì trả NO_MATCH -> không gợi ý (dùng chung hàm choose_reply).
    prompt = answer = answer_error = ""
    suggest: dict | None = None
    suggest_error = ""
    if want_answer:
        # Cùng định dạng ngữ cảnh mà retriever dùng cho bot thật.
        context = [
            f"Hỏi: {r.get('cau_hoi')} → Đáp: {r.get('cau_tra_loi')}"
            for r in result["qa"]
            if r.get("cau_tra_loi")
        ]
        prompt = build_prompt({"trang_thai": "moi"}, context, q)
        try:
            answer = await complete(prompt)
        except Exception as exc:
            # Lỗi LLM không làm hỏng cả trang — vẫn xem được phần truy xuất.
            answer_error = str(exc)[:300]

        # Logic mới, xét trên chính các câu mẫu vừa truy xuất được (Bước 3).
        try:
            suggest = await choose_reply(q, result["qa"])
        except Exception as exc:
            suggest_error = str(exc)[:300]

    return HTMLResponse(
        render_simulate(
            q=q, k=k, threshold=thr, tra_loi=want_answer,
            vector=vector, result=result,
            prompt=prompt, answer=answer, answer_error=answer_error,
            suggest=suggest, suggest_error=suggest_error,
        )
    )


# ----------------------------------------------------------------- thử API
@router.get("/thu-api", response_class=HTMLResponse)
async def api_test_page(request: Request) -> HTMLResponse:
    """Gọi thẳng 1 endpoint Pancake rồi hiện request đã gửi + JSON gốc trả về.

    Thay cho Postman. Đọc tham số dạng cặp `pk`/`pv` lặp lại (bảng key/value ở
    giao diện) nên phải lấy trực tiếp từ `request.query_params`, không dùng
    tham số hàm được. Chỉ chạm Pancake — không đụng Supabase/OpenAI.
    """
    qp = request.query_params
    # Ô chọn tên là `http_method` chứ KHÔNG phải `method`: <select name="method">
    # sẽ che property `form.method` của DOM và làm gãy _NAV_JS (xem shell.py).
    method = (qp.get("http_method") or "GET").upper()
    if method not in ("GET", "POST"):
        method = "GET"
    path = (qp.get("path") or "").strip()
    public = qp.get("public") == "1"
    # Trang TEST -> mặc định HIỆN token; tick "Che bớt" mới giấu đi.
    show_token = qp.get("che_token") != "1"

    # Bảng tra cứu page ID. Lỗi Pancake chỉ làm hỏng đúng bảng này, tab vẫn dùng được.
    pages: list[dict] = []
    pages_error = ""
    try:
        pages = await list_pages()
    except (PancakeError, httpx.HTTPError) as exc:
        pages_error = str(exc)[:200]

    # Ghép 2 danh sách song song thành cặp; bỏ dòng chưa đặt tên tham số.
    keys, values = qp.getlist("pk"), qp.getlist("pv")
    pairs = [
        (k.strip(), (values[i] if i < len(values) else "").strip())
        for i, k in enumerate(keys)
        if k.strip()
    ]

    common = {
        "method": method, "path": path, "pairs": pairs or None,
        "public": public, "show_token": show_token,
        "pages": pages, "pages_error": pages_error,
    }
    if not path:
        # Chưa gõ gì -> chỉ hiện form (giữ lại lựa chọn đang có trên URL).
        return HTMLResponse(render_api_test(**common))

    try:
        result = await raw_call(method, path, dict(pairs), public=public)
    except (PancakeError, httpx.HTTPError) as exc:
        return HTMLResponse(
            render_api_test(**common, error=str(exc)[:300]), status_code=502
        )
    return HTMLResponse(render_api_test(**common, result=result))
