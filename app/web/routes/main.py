"""Route cho 3 mục menu chung: Bảng điều khiển, Tin nhắn, Khách hàng.

Các màn hình này gọi Pancake API (đọc hội thoại) và Supabase (đếm dữ liệu bot).
Mọi lỗi đều được bắt lại và hiển thị ngay trên trang — không để 500 trắng màn.
"""

import asyncio
import json
from collections import Counter
from urllib.parse import parse_qs, urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.ai.brain import extract_qa_candidates, suggest_reply
from app.core.config import settings
from app.db.repositories import inbox_store, tag_store
from app.db.backends import backend_name
from app.db.repositories.queries import _count, insert_qa
from app.integrations.pancake.client import (
    ALL_PAGES,
    PancakeError,
    enabled_pages,
    get_conversation,
    list_all_conversations,
    list_conversations,
    list_pages,
    list_tags,
    pages_cache_luc,
    send_message,
    token_owner,
)
from app.integrations.pancake.switches import disable_all, enable_all, toggle_page
from app.web.views.pancake import _relative_time, render_recent_list, render_thread
from app.web.views.main import (
    quyen_page,
    render_customers,
    render_dashboard,
    render_error,
    render_inbox,
)
from app.workers import poller

router = APIRouter(tags=["ui"])

# Số hội thoại nạp mặc định cho màn Tin nhắn / Khách hàng.
_DEFAULT_LIMIT = 20
_CUSTOMER_LIMIT = 100
# Khi LỌC theo thẻ: nạp một mẻ lớn rồi lọc phía Python (Pancake không lọc thẻ ở
# server), để "gọi ra" gần như toàn bộ hội thoại có gắn thẻ, không chỉ khung 20.
_TAG_FETCH_LIMIT = 200
# Hộp thư GỘP đọc từ kho `watcher.hoi_thoai` (worker nền đổ về) nên không còn bị
# giới hạn bởi 1 lời gọi Pancake -> cho phép hiện nhiều hơn hẳn chế độ 1 page.
_MERGED_DEFAULT_LIMIT = 100
_MERGED_MAX_LIMIT = 500
# "Kéo xuống nạp thêm": mỗi lượt lấy thêm bấy nhiêu hội thoại CŨ HƠN từ kho
# `watcher.hoi_thoai`. Không có trần tổng — cuộn tới đâu nạp tới đó, hết kho thì
# thôi. Mẻ nhỏ để cuộn thấy mượt (truy vấn kho ~vài ms, không tốn quota Pancake).
_MORE_LIMIT = 20
_MORE_MAX_LIMIT = 200


async def _merged_convs(limit: int) -> list[dict]:
    """Hội thoại gộp mọi page: ưu tiên ĐỌC KHO, kho rỗng mới gọi Pancake.

    Kho do worker nền (app/workers/poller.py) đổ về nên: hiện đủ mọi page, không
    sót hội thoại rơi khỏi top-N giữa 2 vòng, và render không tốn lời gọi nào.
    Kho rỗng = worker vừa bật lần đầu (hoặc bị TẮT trong .env) -> quay về cách cũ
    để trang không bao giờ trống trơn.
    """
    convs = await asyncio.to_thread(inbox_store.list_recent, limit)
    if convs:
        return convs
    return await list_all_conversations(limit=min(limit, 50))


# Nhớ page đang chọn qua cookie: vào lại /tin-nhan, /khach-hang (kể cả bấm menu,
# không kèm ?page_id) sẽ dùng lại page gần nhất thay vì nhảy về page đầu.
_PAGE_COOKIE = "last_page_id"
_PAGE_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 ngày


def _wanted_page_id(request: Request, page_id: str) -> str:
    """page_id từ URL; trống thì lấy 'page gần nhất' đã lưu trong cookie."""
    return page_id or request.cookies.get(_PAGE_COOKIE, "")


def _remember_page(resp, page_id: str) -> None:
    """Ghi nhớ page vừa xem vào cookie (để lần sau vào không mất)."""
    if page_id:
        resp.set_cookie(
            _PAGE_COOKIE, str(page_id),
            max_age=_PAGE_COOKIE_MAX_AGE, samesite="lax", path="/",
        )


async def _tags_by_page(page_id: str) -> dict[str, dict[int, dict]]:
    """Tên/màu thẻ để dán lên pill của từng hội thoại -> {page_id: {tag_id: {...}}}.

    Hộp thư GỘP đọc thẳng KHO: mỗi dòng một page, gọi public API cho cả 22 page
    mỗi lượt render là chắc chắn dính 429. Kho luôn có sẵn vì `list_tags` ghi
    xuống mỗi lần lấy được, và worker nền cũng làm tươi định kỳ.

    Xem 1 page thì đi đường 3 tầng của `list_tags` (RAM -> API -> kho).
    """
    if page_id == ALL_PAGES:
        try:
            return await asyncio.to_thread(tag_store.load_all_tags)
        except Exception:  # noqa: BLE001 — kho hỏng thì pill lùi về "Thẻ #id"
            return {}
    return {str(page_id): await list_tags(page_id)}


def _tag_facet(convs: list[dict]) -> list[tuple[int, int]]:
    """Đếm số hội thoại theo từng thẻ -> [(tag_id, số hội thoại)], nhiều nhất trước."""
    counter: Counter[int] = Counter()
    for c in convs:
        for t in c.get("tags", []):
            counter[t] += 1
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))


def _filter_by_tag(convs: list[dict], tag: str) -> list[dict]:
    """Lọc hội thoại có chứa thẻ `tag` (ID số dạng chuỗi). Rỗng/sai -> giữ nguyên."""
    if not tag:
        return convs
    try:
        tid = int(tag)
    except ValueError:
        return convs
    return [c for c in convs if tid in c.get("tags", [])]


async def _pick_page(page_id: str) -> tuple[list[dict], dict | None]:
    """Trả (danh sách page, page đang chọn).

    Không truyền page_id -> tự lấy page đang hoạt động đầu tiên, để vào thẳng
    /tin-nhan là dùng được ngay mà không phải chọn tay.
    """
    pages = await list_pages()
    if not pages:
        return [], None
    if page_id:
        for p in pages:
            if p["id"] == str(page_id):
                return pages, p
    active = [p for p in pages if p.get("is_activated")]
    return pages, (active or pages)[0]


@router.get("/")
async def home() -> RedirectResponse:
    """Vào gốc site thì chuyển sang Bảng điều khiển."""
    return RedirectResponse("/bang-dieu-khien", status_code=307)


# ------------------------------------------------------------ bảng điều khiển
@router.get("/bang-dieu-khien", response_class=HTMLResponse)
async def dashboard(page_id: str = "") -> HTMLResponse:
    """Tổng quan: số liệu Pancake, kho dữ liệu bot và cấu hình đang chạy.

    Ba khối dữ liệu được lấy độc lập: Pancake hỏng thì phần Supabase vẫn hiện
    (và ngược lại) — lỗi chỉ hiện trong đúng khối của nó.
    """
    errors: dict[str, str] = {}

    pancake: dict = {}
    pages: list[dict] = []       # để render danh sách page ngay trên bảng điều khiển
    try:
        pages, page = await _pick_page(page_id)
        convs = await list_conversations(page["id"], limit=50) if page else []
        newest = convs[0] if convs else {}
        pancake = {
            "total_pages": len(pages),
            "active_pages": sum(1 for p in pages if p.get("is_activated")),
            "page_name": (page or {}).get("name", "—"),
            "conv_count": len(convs),
            "unread": sum(c.get("unread_count", 0) for c in convs),
            "last_name": newest.get("name", ""),
            "last_rel": _relative_time(newest.get("updated_at", "")),
        }
    except (PancakeError, httpx.HTTPError, KeyError) as exc:
        errors["pancake"] = str(exc)

    data: dict = {}
    try:
        data = {
            "qa_total": _count("hoi_thoai_mau"),
            "qa_emb": _count("hoi_thoai_mau", only_with_embedding=True),
            "kb_total": _count("kich_ban"),
            "kb_emb": _count("kich_ban", only_with_embedding=True),
        }
    except Exception as exc:  # lỗi DB/cấu hình — không làm hỏng cả trang
        errors["data"] = str(exc)

    # Nơi lưu dữ liệu: postgres = DB trên máy, supabase = Postgres cloud.
    backend = backend_name()
    if backend == "postgres":
        from app.db.backends.postgres_be import dsn_summary

        db_ready, db_target = bool(settings.database_url), dsn_summary()
    else:
        db_ready = bool(settings.supabase_url and settings.supabase_key)
        db_target = settings.supabase_url

    config = {
        "pancake_token": bool(settings.pancake_access_token),
        "openai_key": bool(settings.openai_api_key),
        "db_backend": backend,
        "db_ready": db_ready,
        "db_target": db_target,
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "top_k": settings.rag_top_k,
        "threshold": settings.rag_match_threshold,
    }
    # `token_owner` chỉ giải mã JWT tại chỗ, không gọi mạng nên không cần try.
    config["owner"] = token_owner().get("name") or ""

    # Page nào poller đang gọi lỗi -> tô vàng cảnh báo trong danh sách page.
    return HTMLResponse(
        render_dashboard(pancake, data, config, errors, pages, poller.page_loi())
    )


def _switch_response(request: Request, payload: dict):
    """Gọi ngầm (có header X-Requested-With) -> JSON (không reload); còn lại -> redirect."""
    if request.headers.get("x-requested-with"):
        return JSONResponse(payload)
    return RedirectResponse("/bang-dieu-khien#ds-page", status_code=303)


@router.post("/bang-dieu-khien/page-switch")
async def dashboard_page_switch(request: Request):
    """Lật công tắc BẬT/TẮT 1 page.

    TẮT = chặn lấy/gửi tin của page đó ở MỌI nơi (guard trong pancake/client).
    Bản thân thao tác chỉ ghi file JSON, KHÔNG gọi Pancake/OpenAI. Gọi ngầm (AJAX)
    thì trả JSON để trình duyệt cập nhật nút tại chỗ, không tải lại trang.
    """
    form = parse_qs((await request.body()).decode("utf-8"))
    page_id = (form.get("page_id", [""])[0]).strip()
    enabled = True
    if page_id:
        enabled = toggle_page(page_id)
    return _switch_response(request, {"page_id": page_id, "enabled": enabled})


@router.post("/bang-dieu-khien/page-switch-all")
async def dashboard_page_switch_all(request: Request):
    """BẬT/TẮT tất cả page cùng lúc (nút 'Bật tất cả' / 'Tắt tất cả')."""
    form = parse_qs((await request.body()).decode("utf-8"))
    action = (form.get("action", [""])[0]).strip()
    if action == "on":
        enable_all()
    elif action == "off":
        try:
            pages = await list_pages()
        except (PancakeError, httpx.HTTPError):
            pages = []
        disable_all([p["id"] for p in pages])
    return _switch_response(request, {"action": action})


@router.post("/bang-dieu-khien/lam-moi-page")
async def dashboard_lam_moi_page() -> JSONResponse:
    """Hỏi lại Pancake danh sách page NGAY (bỏ qua cache) — nút bấm tay.

    Danh sách page + vai trò (`role_in_page`) gần như không đổi nên cache để 15
    phút cho đỡ tốn lượt gọi; nút này dành cho lúc vừa đổi thật (được nâng quyền
    Admin, thêm/bớt page) mà không muốn ngồi chờ hết cache.
    """
    try:
        pages = await list_pages(force=True)
    except (PancakeError, httpx.HTTPError) as exc:
        return JSONResponse({"ok": False, "loi": str(exc)}, status_code=502)
    dem = Counter(quyen_page(p)[0] for p in pages)
    luc = pages_cache_luc()
    return JSONResponse({
        "ok": True,
        "tong": len(pages),
        "du": dem["du"],
        "thieu": dem["thieu"],
        "vo_hieu": dem["vo_hieu"],
        "luc": luc.strftime("%H:%M:%S %d/%m") if luc else "",
    })


# ------------------------------------------------------------------ tin nhắn
@router.get("/tin-nhan", response_class=HTMLResponse)
async def inbox(
    request: Request,
    page_id: str = "",
    conv_id: str = "",
    customer_id: str = "",
    conv_page_id: str = "",
    limit: int = _DEFAULT_LIMIT,
    tag: str = "",
    sent: int = 0,
    error: str = "",
) -> HTMLResponse:
    """Hộp thư 2 cột: danh sách hội thoại bên trái, khung chat bên phải.

    `page_id` = ALL -> hộp thư GỘP mọi page đang BẬT; khi đó `conv_page_id` cho
    biết hội thoại đang mở bên phải thuộc page nào.
    `tag` (ID số) -> chỉ hiện hội thoại có gắn thẻ đó (lọc trong khung đã nạp).
    Không truyền `page_id` thì dùng lại page gần nhất (cookie) trước khi mặc định.
    """
    page_id = _wanted_page_id(request, page_id)
    merged = page_id == ALL_PAGES
    # Gộp: đọc kho nên cho hiện nhiều (mặc định 100, trần 500). Xem 1 page: vẫn
    # là 1 lời gọi Pancake nên giữ trần 50 như cũ.
    limit = (
        max(1, min(limit if limit != _DEFAULT_LIMIT else _MERGED_DEFAULT_LIMIT,
                   _MERGED_MAX_LIMIT))
        if merged else max(1, min(limit, 50))
    )
    try:
        pages = await list_pages()
        on_count = len(await enabled_pages())
        if merged:
            pid, page_name = ALL_PAGES, f"Tất cả page ({on_count} đang BẬT)"
            convs = await _merged_convs(limit)
            # Không có thanh lọc thẻ ở chế độ gộp, nhưng pill trên từng hội
            # thoại vẫn hiện tên thật nhờ bản thẻ theo page đọc từ kho.
            facet, tags_meta = [], {}
            tags_by_page = await _tags_by_page(ALL_PAGES)
            # Page thật của hội thoại đang mở (đến từ link ở cột trái).
            thread_pid = conv_page_id
        else:
            _pages, page = await _pick_page(page_id)
            if page is None:
                return HTMLResponse(
                    render_error("Token Pancake không thấy page nào.", "messages"),
                    status_code=502,
                )
            pid, page_name = page["id"], page["name"]
            # Có lọc thẻ -> nạp mẻ lớn để lấy hết hội thoại gắn thẻ; không thì nạp gọn.
            convs = await list_conversations(
                pid, limit=_TAG_FETCH_LIMIT if tag else limit
            )
            # Thanh lọc thẻ dựng từ TẤT CẢ hội thoại đã nạp; danh sách lọc theo thẻ.
            facet = _tag_facet(convs)
            # Tên + màu thẻ thật (public API); không có page token -> {} -> fallback.
            tags_meta = await list_tags(pid)
            tags_by_page = {str(pid): tags_meta}
            convs = _filter_by_tag(convs, tag)
            thread_pid = pid
        # Chỉ nạp thread khi đã chọn một hội thoại VÀ biết page thật của nó.
        convo = (
            await get_conversation(thread_pid, conv_id, customer_id or None)
            if conv_id and thread_pid and thread_pid != ALL_PAGES else None
        )
    except (PancakeError, httpx.HTTPError) as exc:
        return HTMLResponse(render_error(str(exc), "messages"), status_code=502)

    thread_page_name = next(
        (p["name"] for p in pages if p["id"] == str(thread_pid)), ""
    ) if merged else ""

    resp = HTMLResponse(
        render_inbox(
            pages=pages, page_id=pid, page_name=page_name, convs=convs,
            conv_id=conv_id, customer_id=customer_id, convo=convo, limit=limit,
            sent=bool(sent), error=error, tags_facet=facet, active_tag=tag,
            tags_meta=tags_meta, merged=merged, enabled_count=on_count,
            thread_page_id=thread_pid, thread_page_name=thread_page_name,
            tags_by_page=tags_by_page,
        )
    )
    _remember_page(resp, pid)  # nhớ page vừa xem cho lần sau
    return resp


@router.get("/tin-nhan/fragment/list", response_class=HTMLResponse)
async def inbox_list_fragment(
    request: Request,
    page_id: str = "", conv_id: str = "", limit: int = _DEFAULT_LIMIT, tag: str = ""
) -> HTMLResponse:
    """Chỉ cột danh sách hội thoại (JS gọi lại mỗi 10-15 giây), giữ nguyên lọc thẻ."""
    page_id = _wanted_page_id(request, page_id)
    limit = (
        max(1, min(limit if limit != _DEFAULT_LIMIT else _MERGED_DEFAULT_LIMIT,
                   _MERGED_MAX_LIMIT))
        if page_id == ALL_PAGES else max(1, min(limit, 50))
    )
    try:
        if page_id == ALL_PAGES:
            pid = ALL_PAGES
            convs = await _merged_convs(limit)
        else:
            _pages, page = await _pick_page(page_id)
            if page is None:
                return HTMLResponse("", status_code=502)
            pid = page["id"]
            convs = _filter_by_tag(
                await list_conversations(
                    pid, limit=_TAG_FETCH_LIMIT if tag else limit
                ),
                tag,
            )
    except (PancakeError, httpx.HTTPError):
        # 502 -> JS bỏ qua nhịp này, giữ nguyên nội dung đang hiển thị.
        return HTMLResponse("", status_code=502)
    return HTMLResponse(
        render_recent_list(
            convs, pid, "INBOX", mode="inbox", active=conv_id, tag=tag,
            tags_by_page=await _tags_by_page(pid),
        )
    )


@router.get("/tin-nhan/fragment/more", response_class=HTMLResponse)
async def inbox_more_fragment(
    request: Request,
    page_id: str = "", conv_id: str = "", tag: str = "",
    before_upd: str = "", before_cid: str = "", limit: int = _MORE_LIMIT,
) -> HTMLResponse:
    """Nạp thêm hội thoại CŨ HƠN mốc `before_*` — đọc KHO, không gọi Pancake.

    Vì sao đọc kho: 1 lời gọi Pancake chỉ trả về khung N hội thoại mới nhất, xin
    càng nhiều càng dễ dính 429, và không có cách xin "trang tiếp theo". Kho
    `watcher.hoi_thoai` thì worker nền bồi liên tục và chỉ thêm chứ không xoá,
    nên cuộn ngược về quá khứ được bao xa tuỳ kho đã tích được bấy nhiêu — không
    còn trần 50 như đường gọi thẳng.

    Trả về các `<li>` trần để JS nối vào cuối danh sách; rỗng = đã hết.
    """
    page_id = _wanted_page_id(request, page_id)
    if not before_upd:      # thiếu mốc thì không biết cắt từ đâu -> đừng trả trùng
        return HTMLResponse("")
    limit = max(1, min(limit, _MORE_MAX_LIMIT))
    tag_id = int(tag) if tag.lstrip("-").isdigit() else None
    convs = await asyncio.to_thread(
        inbox_store.list_recent,
        limit=limit,
        # Hộp thư gộp: không lọc page. Xem 1 page: chỉ hội thoại của page đó.
        page_id=None if page_id == ALL_PAGES else page_id,
        before=(before_upd, before_cid),
        tag=tag_id,
    )
    return HTMLResponse(
        render_recent_list(
            convs, page_id, "INBOX", mode="inbox", active=conv_id, tag=tag,
            items_only=True, tags_by_page=await _tags_by_page(page_id),
        )
    )


@router.get("/tin-nhan/fragment/thread", response_class=HTMLResponse)
async def inbox_thread_fragment(
    request: Request,
    page_id: str = "", conv_id: str = "", customer_id: str = "",
    conv_page_id: str = "",
) -> HTMLResponse:
    """Chỉ phần bong bóng chat (JS gọi lại mỗi 8 giây).

    Ở hộp thư gộp, `page_id` là ALL nên page thật phải lấy từ `conv_page_id`.
    """
    if not conv_id:
        return HTMLResponse("", status_code=204)
    page_id = conv_page_id or _wanted_page_id(request, page_id)
    if page_id == ALL_PAGES:
        return HTMLResponse("", status_code=204)   # chưa biết page thật -> bỏ nhịp
    try:
        _pages, page = await _pick_page(page_id)
        if page is None:
            return HTMLResponse("", status_code=502)
        convo = await get_conversation(page["id"], conv_id, customer_id or None)
    except (PancakeError, httpx.HTTPError):
        return HTMLResponse("", status_code=502)
    return HTMLResponse(render_thread(convo.get("messages") or []))


@router.post("/tin-nhan/tra-loi")
async def inbox_reply(request: Request) -> RedirectResponse:
    """Gửi tin trả lời từ màn 2 cột rồi quay lại đúng hội thoại đó.

    ⚠️ Gửi tin THẬT tới khách qua Pancake (action=reply_inbox).
    """
    form = parse_qs((await request.body()).decode("utf-8"))
    get = lambda k: (form.get(k, [""])[0]).strip()  # noqa: E731

    page_id, conv_id = get("page_id"), get("conv_id")
    customer_id, message = get("customer_id"), get("message")
    # `page_id` là page THẬT (để gửi đúng chỗ); `list_page_id` là cột trái đang
    # xem — có thể là ALL, cần giữ để gửi xong không rơi khỏi hộp thư gộp.
    list_page_id = get("list_page_id") or page_id

    params = {"page_id": list_page_id, "conv_id": conv_id, "customer_id": customer_id}
    if list_page_id != page_id:
        params["conv_page_id"] = page_id
    if not message:
        params["error"] = "Tin nhắn trống"
    else:
        try:
            await send_message(page_id, conv_id, message, customer_id or None)
            params["sent"] = "1"
        except (PancakeError, httpx.HTTPError) as exc:
            params["error"] = str(exc)[:150]

    return RedirectResponse(f"/tin-nhan?{urlencode(params)}", status_code=303)


def _last_customer_text(convo: dict) -> str:
    """Nội dung tin gần nhất CỦA KHÁCH (bỏ tin của shop, bỏ tin không có chữ).

    Tin chỉ có ảnh/tệp (text rỗng) bị bỏ qua vì không nhúng/tra cứu được — lùi
    về tin có chữ gần nhất của khách.
    """
    for m in reversed(convo.get("messages") or []):
        if not m.get("is_page") and (m.get("text") or "").strip():
            return m["text"].strip()
    return ""


@router.post("/tin-nhan/goi-y")
async def inbox_suggest(request: Request) -> JSONResponse:
    """Soạn GỢI Ý trả lời (RAG + LLM) cho tin cuối của khách — KHÔNG gửi đi.

    Bước 1 của lộ trình (xem README → "Gợi ý lộ trình"): người bấm nút, câu gợi
    ý được trả về JSON để JS đổ vào ô trả lời cho người sửa rồi TỰ bấm Gửi.
    Không đọc/ghi phiên, không gọi Pancake gửi tin.
    """
    form = parse_qs((await request.body()).decode("utf-8"))
    get = lambda k: (form.get(k, [""])[0]).strip()  # noqa: E731
    page_id, conv_id, customer_id = get("page_id"), get("conv_id"), get("customer_id")

    if not (page_id and conv_id):
        return JSONResponse({"error": "Thiếu page_id/conv_id."}, status_code=400)

    try:
        convo = await get_conversation(page_id, conv_id, customer_id or None)
    except (PancakeError, httpx.HTTPError) as exc:
        return JSONResponse(
            {"error": f"Không tải được hội thoại: {exc}"}, status_code=502
        )

    question = _last_customer_text(convo)
    if not question:
        return JSONResponse({"error": "Chưa thấy tin nhắn chữ nào của khách để gợi ý."})

    try:
        result = await suggest_reply(question)
    except Exception as exc:  # thiếu OPENAI_API_KEY / chưa tạo RPC / lỗi mạng...
        return JSONResponse({"error": str(exc)[:200]})

    # Không có câu mẫu nào đủ giống -> câu hỏi chưa có trong tri thức: KHÔNG gợi ý.
    if result.get("no_match") or not (result.get("reply") or "").strip():
        return JSONResponse(
            {
                "no_match": True,
                "question": question,
                "nguon_text": "Câu hỏi này chưa có trong tri thức — không gợi ý.",
            }
        )

    rows = result.get("nguon") or []
    scored = [r for r in rows if r.get("similarity") is not None]
    top = max((r["similarity"] for r in scored), default=None)
    nguon_text = (
        f"Dựa trên {len(scored)} câu mẫu · gần nhất {top:.2f}"
        if top is not None else ""
    )
    return JSONResponse(
        {"reply": result["reply"], "question": question, "nguon_text": nguon_text}
    )


# Chặn trên độ dài transcript gửi cho LLM (ký tự) — phòng hội thoại quá dài
# tốn prompt/tiền; giữ lại đoạn GẦN NHẤT (thường chứa nội dung tư vấn thật sự).
_TRANSCRIPT_MAX_CHARS = 12000


def _transcript(messages: list[dict]) -> str:
    """Chuyển list tin nhắn Pancake -> văn bản 'Khách: ...\\nNhân viên: ...' cho LLM đọc.

    Chỉ lấy tin có chữ (ảnh/tệp không có text bị bỏ qua, LLM không đọc được).
    """
    lines = [
        f'{"Nhân viên" if m.get("is_page") else "Khách"}: {text}'
        for m in (messages or [])
        if (text := (m.get("text") or "").strip())
    ]
    return "\n".join(lines)[-_TRANSCRIPT_MAX_CHARS:]


@router.post("/tin-nhan/trich-tri-thuc")
async def inbox_extract(request: Request) -> JSONResponse:
    """Trích ĐỀ XUẤT cặp hỏi-đáp từ TOÀN BỘ hội thoại — CHỈ đề xuất, KHÔNG ghi DB.

    Người dùng xem/sửa/bỏ ở màn hình (JS) rồi mới bấm Lưu (route .../luu bên
    dưới) — human-in-the-loop, tri thức không tự động vào DB khi chưa ai duyệt.
    """
    form = parse_qs((await request.body()).decode("utf-8"))
    get = lambda k: (form.get(k, [""])[0]).strip()  # noqa: E731
    page_id, conv_id, customer_id = get("page_id"), get("conv_id"), get("customer_id")

    if not (page_id and conv_id):
        return JSONResponse({"error": "Thiếu page_id/conv_id."}, status_code=400)

    try:
        convo = await get_conversation(page_id, conv_id, customer_id or None)
    except (PancakeError, httpx.HTTPError) as exc:
        return JSONResponse(
            {"error": f"Không tải được hội thoại: {exc}"}, status_code=502
        )

    transcript = _transcript(convo.get("messages") or [])
    if not transcript:
        return JSONResponse({"error": "Hội thoại chưa có tin nhắn nào có chữ."})

    try:
        items = await extract_qa_candidates(transcript)
    except Exception as exc:  # thiếu OPENAI_API_KEY / lỗi mạng...
        return JSONResponse({"error": str(exc)[:200]})

    if not items:
        return JSONResponse(
            {"items": [],
             "note": "Không thấy cặp hỏi-đáp nào đáng trích trong hội thoại này."}
        )
    return JSONResponse({"items": items})


@router.post("/tin-nhan/trich-tri-thuc/luu")
async def inbox_extract_save(request: Request) -> JSONResponse:
    """Lưu các cặp hỏi-đáp NGƯỜI DÙNG ĐÃ DUYỆT (có thể đã sửa) vào hoi_thoai_mau.

    `items` = chuỗi JSON [{"cau_hoi":..,"cau_tra_loi":..,"nguon":..}, ...] — chỉ
    gồm những dòng người dùng còn tick + đã điền đủ 2 trường. Từng dòng lỗi (vd
    Supabase từ chối) bị bỏ qua riêng, không làm hỏng cả lượt lưu.
    """
    form = parse_qs((await request.body()).decode("utf-8"))
    try:
        items = json.loads((form.get("items", ["[]"])[0]))
    except (ValueError, TypeError):
        items = None
    if not isinstance(items, list):
        return JSONResponse({"error": "Dữ liệu gửi lên không hợp lệ."}, status_code=400)

    saved, errors = 0, []
    for it in items:
        if not isinstance(it, dict):
            continue
        cau_hoi = str(it.get("cau_hoi") or "").strip()
        cau_tra_loi = str(it.get("cau_tra_loi") or "").strip()
        if not (cau_hoi and cau_tra_loi):
            continue
        nguon = str(it.get("nguon") or "").strip() or None
        try:
            await insert_qa(cau_hoi=cau_hoi, cau_tra_loi=cau_tra_loi, nguon=nguon)
            saved += 1
        except Exception as exc:
            errors.append(str(exc)[:150])

    return JSONResponse({"saved": saved, "errors": errors})


# ---------------------------------------------------------------- khách hàng
@router.get("/khach-hang", response_class=HTMLResponse)
async def customers(request: Request, page_id: str = "") -> HTMLResponse:
    """Bảng khách đã nhắn tin vào page (nguồn: hội thoại INBOX của Pancake)."""
    page_id = _wanted_page_id(request, page_id)
    try:
        pages, page = await _pick_page(page_id)
        if page is None:
            return HTMLResponse(
                render_error("Token Pancake không thấy page nào.", "customers"),
                status_code=502,
            )
        convs = await list_conversations(page["id"], limit=_CUSTOMER_LIMIT)
    except (PancakeError, httpx.HTTPError) as exc:
        return HTMLResponse(render_error(str(exc), "customers"), status_code=502)

    resp = HTMLResponse(render_customers(pages, page["id"], page["name"], convs))
    _remember_page(resp, page["id"])
    return resp
