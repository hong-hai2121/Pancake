"""Route Pancake: webview danh sách page + endpoint JSON.

Được include thêm vào app (main.py) — độc lập với route webhook Facebook.
"""

import httpx
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.pancake.client import PancakeError, list_pages, token_owner
from app.pancake.webview import render_error, render_pages

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
