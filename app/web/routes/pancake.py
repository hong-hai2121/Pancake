"""Route Pancake: webview danh sách page + endpoint JSON.

Được include thêm vào app (main.py) — độc lập với route webhook Facebook.
"""

from urllib.parse import parse_qs, urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.integrations.pancake.client import (
    PancakeError,
    get_conversation,
    get_page,
    list_conversations,
    list_pages,
    send_message,
    token_owner,
)
from app.web.views.pancake import (
    render_conversation,
    render_error,
    render_pages,
    render_recent,
    render_recent_list,
    render_thread,
)

router = APIRouter(prefix="/pancake", tags=["pancake"])


@router.get("/pages")
async def pages_json() -> dict:
    """Danh sách page dạng JSON (cho tích hợp/khác dùng)."""
    pages = await list_pages()
    return {"count": len(pages), "pages": pages}


@router.get("/webview", response_class=HTMLResponse)
async def pages_webview() -> HTMLResponse:
    """Webview HTML hiển thị danh sách page có quyền truy cập."""
    try:
        pages = await list_pages()
    except (PancakeError, httpx.HTTPError) as exc:
        return HTMLResponse(render_error(str(exc)), status_code=502)
    return HTMLResponse(render_pages(pages, owner=token_owner()))


@router.get("/pages/{page_id}/recent", response_class=HTMLResponse)
async def recent_messagers(
    page_id: str, limit: int = 5, type: str = "INBOX"
) -> HTMLResponse:
    """Webview: N người nhắn tin (INBOX) mới nhất của 1 page.

    ?limit=5 (mặc định) · ?type=INBOX|COMMENT
    """
    msg_type = type.upper()
    if msg_type not in ("INBOX", "COMMENT"):
        msg_type = "INBOX"
    limit = max(1, min(limit, 50))
    try:
        convs = await list_conversations(page_id, msg_type=msg_type, limit=limit)
        page = await get_page(page_id)
    except (PancakeError, httpx.HTTPError) as exc:
        return HTMLResponse(render_error(str(exc)), status_code=502)
    return HTMLResponse(render_recent(page_id, page, convs, msg_type, limit))


@router.get("/pages/{page_id}/recent/fragment", response_class=HTMLResponse)
async def recent_fragment(
    page_id: str, limit: int = 5, type: str = "INBOX"
) -> HTMLResponse:
    """Chỉ phần danh sách (cho JS auto-refresh gọi định kỳ)."""
    msg_type = type.upper()
    if msg_type not in ("INBOX", "COMMENT"):
        msg_type = "INBOX"
    limit = max(1, min(limit, 50))
    try:
        convs = await list_conversations(page_id, msg_type=msg_type, limit=limit)
    except (PancakeError, httpx.HTTPError):
        # 502 -> JS bỏ qua nhịp này, giữ nguyên dữ liệu đang hiển thị.
        return HTMLResponse("", status_code=502)
    return HTMLResponse(render_recent_list(convs, page_id, msg_type))


@router.get(
    "/pages/{page_id}/conversations/{conv_id}", response_class=HTMLResponse
)
async def conversation_detail(
    page_id: str,
    conv_id: str,
    customer_id: str = "",
    sent: int = 0,
    error: str = "",
) -> HTMLResponse:
    """Webview: xem toàn bộ hội thoại + form trả lời (mô phỏng Pancake)."""
    try:
        convo = await get_conversation(page_id, conv_id, customer_id or None)
        page = await get_page(page_id)
    except (PancakeError, httpx.HTTPError) as exc:
        return HTMLResponse(render_error(str(exc)), status_code=502)
    return HTMLResponse(
        render_conversation(
            page_id, page, conv_id, customer_id, convo,
            sent=bool(sent), error=error,
        )
    )


@router.get(
    "/pages/{page_id}/conversations/{conv_id}/fragment",
    response_class=HTMLResponse,
)
async def conversation_fragment(
    page_id: str, conv_id: str, customer_id: str = ""
) -> HTMLResponse:
    """Chỉ phần bong bóng chat (cho JS auto-refresh gọi định kỳ)."""
    try:
        convo = await get_conversation(page_id, conv_id, customer_id or None)
    except (PancakeError, httpx.HTTPError):
        return HTMLResponse("", status_code=502)
    return HTMLResponse(render_thread(convo.get("messages") or []))


@router.post("/pages/{page_id}/conversations/{conv_id}/reply")
async def reply(page_id: str, conv_id: str, request: Request) -> RedirectResponse:
    """Gửi tin trả lời rồi quay lại trang hội thoại.

    ⚠️ Gửi tin THẬT tới khách qua Pancake (action=reply_inbox).
    """
    form = parse_qs((await request.body()).decode("utf-8"))
    message = (form.get("message", [""])[0]).strip()
    customer_id = form.get("customer_id", [""])[0]

    base = f"/pancake/pages/{page_id}/conversations/{conv_id}"
    params: dict[str, str] = {}
    if customer_id:
        params["customer_id"] = customer_id

    if not message:
        params["error"] = "Tin nhắn trống"
    else:
        try:
            await send_message(page_id, conv_id, message, customer_id or None)
            params["sent"] = "1"
        except (PancakeError, httpx.HTTPError) as exc:
            params["error"] = str(exc)[:150]

    return RedirectResponse(f"{base}?{urlencode(params)}", status_code=303)
