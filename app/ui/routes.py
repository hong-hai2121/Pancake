"""Route cho 3 mục menu chung: Bảng điều khiển, Tin nhắn, Khách hàng.

Các màn hình này gọi Pancake API (đọc hội thoại) và Supabase (đếm dữ liệu bot).
Mọi lỗi đều được bắt lại và hiển thị ngay trên trang — không để 500 trắng màn.
"""

from collections import Counter
from urllib.parse import parse_qs, urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import settings
from app.db.queries import _count
from app.pancake.client import (
    PancakeError,
    get_conversation,
    list_conversations,
    list_pages,
    list_tags,
    send_message,
    token_owner,
)
from app.pancake.webview import _relative_time, render_recent_list, render_thread
from app.ui.webview import (
    render_customers,
    render_dashboard,
    render_error,
    render_inbox,
)

router = APIRouter(tags=["ui"])

# Số hội thoại nạp mặc định cho màn Tin nhắn / Khách hàng.
_DEFAULT_LIMIT = 20
_CUSTOMER_LIMIT = 100
# Khi LỌC theo thẻ: nạp một mẻ lớn rồi lọc phía Python (Pancake không lọc thẻ ở
# server), để "gọi ra" gần như toàn bộ hội thoại có gắn thẻ, không chỉ khung 20.
_TAG_FETCH_LIMIT = 200


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
    except Exception as exc:  # lỗi Supabase/cấu hình — không làm hỏng cả trang
        errors["data"] = str(exc)

    config = {
        "pancake_token": bool(settings.pancake_access_token),
        "openai_key": bool(settings.openai_api_key),
        "supabase": bool(settings.supabase_url and settings.supabase_key),
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "top_k": settings.rag_top_k,
        "threshold": settings.rag_match_threshold,
    }
    # `token_owner` chỉ giải mã JWT tại chỗ, không gọi mạng nên không cần try.
    config["owner"] = token_owner().get("name") or ""

    return HTMLResponse(render_dashboard(pancake, data, config, errors))


# ------------------------------------------------------------------ tin nhắn
@router.get("/tin-nhan", response_class=HTMLResponse)
async def inbox(
    request: Request,
    page_id: str = "",
    conv_id: str = "",
    customer_id: str = "",
    limit: int = _DEFAULT_LIMIT,
    tag: str = "",
    sent: int = 0,
    error: str = "",
) -> HTMLResponse:
    """Hộp thư 2 cột: danh sách hội thoại bên trái, khung chat bên phải.

    `tag` (ID số) -> chỉ hiện hội thoại có gắn thẻ đó (lọc trong khung đã nạp).
    Không truyền `page_id` thì dùng lại page gần nhất (cookie) trước khi mặc định.
    """
    limit = max(1, min(limit, 50))
    page_id = _wanted_page_id(request, page_id)
    try:
        pages, page = await _pick_page(page_id)
        if page is None:
            return HTMLResponse(
                render_error("Token Pancake không thấy page nào.", "messages"),
                status_code=502,
            )
        pid = page["id"]
        # Có lọc thẻ -> nạp mẻ lớn để lấy hết hội thoại gắn thẻ; không thì nạp gọn.
        convs = await list_conversations(
            pid, limit=_TAG_FETCH_LIMIT if tag else limit
        )
        # Thanh lọc thẻ dựng từ TẤT CẢ hội thoại đã nạp; danh sách thì lọc theo thẻ.
        facet = _tag_facet(convs)
        # Tên + màu thẻ thật (public API); không có page token thì trả {} -> fallback.
        tags_meta = await list_tags(pid)
        convs = _filter_by_tag(convs, tag)
        # Chỉ nạp thread khi người dùng đã chọn một hội thoại.
        convo = (
            await get_conversation(pid, conv_id, customer_id or None)
            if conv_id else None
        )
    except (PancakeError, httpx.HTTPError) as exc:
        return HTMLResponse(render_error(str(exc), "messages"), status_code=502)

    resp = HTMLResponse(
        render_inbox(
            pages=pages, page_id=pid, page_name=page["name"], convs=convs,
            conv_id=conv_id, customer_id=customer_id, convo=convo, limit=limit,
            sent=bool(sent), error=error, tags_facet=facet, active_tag=tag,
            tags_meta=tags_meta,
        )
    )
    _remember_page(resp, pid)  # nhớ page vừa xem cho lần sau
    return resp


@router.get("/tin-nhan/fragment/list", response_class=HTMLResponse)
async def inbox_list_fragment(
    request: Request,
    page_id: str = "", conv_id: str = "", limit: int = _DEFAULT_LIMIT, tag: str = ""
) -> HTMLResponse:
    """Chỉ cột danh sách hội thoại (JS gọi lại mỗi 10 giây), giữ nguyên lọc thẻ."""
    limit = max(1, min(limit, 50))
    page_id = _wanted_page_id(request, page_id)
    try:
        _pages, page = await _pick_page(page_id)
        if page is None:
            return HTMLResponse("", status_code=502)
        convs = _filter_by_tag(
            await list_conversations(
                page["id"], limit=_TAG_FETCH_LIMIT if tag else limit
            ),
            tag,
        )
    except (PancakeError, httpx.HTTPError):
        # 502 -> JS bỏ qua nhịp này, giữ nguyên nội dung đang hiển thị.
        return HTMLResponse("", status_code=502)
    return HTMLResponse(
        render_recent_list(
            convs, page["id"], "INBOX", mode="inbox", active=conv_id, tag=tag
        )
    )


@router.get("/tin-nhan/fragment/thread", response_class=HTMLResponse)
async def inbox_thread_fragment(
    request: Request,
    page_id: str = "", conv_id: str = "", customer_id: str = ""
) -> HTMLResponse:
    """Chỉ phần bong bóng chat (JS gọi lại mỗi 8 giây)."""
    if not conv_id:
        return HTMLResponse("", status_code=204)
    page_id = _wanted_page_id(request, page_id)
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

    params = {"page_id": page_id, "conv_id": conv_id, "customer_id": customer_id}
    if not message:
        params["error"] = "Tin nhắn trống"
    else:
        try:
            await send_message(page_id, conv_id, message, customer_id or None)
            params["sent"] = "1"
        except (PancakeError, httpx.HTTPError) as exc:
            params["error"] = str(exc)[:150]

    return RedirectResponse(f"/tin-nhan?{urlencode(params)}", status_code=303)


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
