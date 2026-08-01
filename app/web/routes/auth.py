"""Route web đăng nhập/đăng xuất (A2): /dang-nhap (GET+POST) và /dang-xuat.

Khác app/api/v1/auth.py (JSON + Bearer cho máy gọi máy): ở đây là form trình
duyệt, token nằm trong cookie HttpOnly — JS không đọc được, đỡ lộ khi dính XSS.
Cùng gọi chung app/services/auth_service.py nên luật (khoá 5 lần, audit...)
chỉ có MỘT chỗ.
"""

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.core.config import settings
from app.services import auth_service
from app.services.auth_service import AuthError
from app.web.views.auth import THONG_BAO, render_login

router = APIRouter(tags=["web-auth"])


def _an_toan(next_url: str) -> str:
    """Chỉ cho chuyển hướng nội bộ ('/...'); chặn '//evil.com' (open redirect)."""
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/"


def dat_cookie_dang_nhap(resp: Response, data: dict, remember: bool) -> None:
    """Gắn cặp token vào cookie HttpOnly. Không tick 'ghi nhớ' -> cookie phiên
    (đóng trình duyệt là hết); tick -> refresh sống 14 ngày như mô tả A2."""
    chung = {"httponly": True, "samesite": "lax", "secure": settings.cookie_secure}
    resp.set_cookie(
        "access_token", data["access_token"],
        max_age=settings.access_token_ttl_minutes * 60, **chung,
    )
    if data.get("refresh_token"):
        resp.set_cookie(
            "refresh_token", data["refresh_token"],
            max_age=settings.refresh_token_ttl_days * 86400 if remember else None,
            **chung,
        )


@router.get("/dang-nhap", response_class=HTMLResponse)
async def trang_dang_nhap(
    request: Request, next: str = "", thongbao: str = ""
) -> HTMLResponse:
    # Đã đăng nhập rồi mà mở /dang-nhap -> đưa thẳng vào trong
    if getattr(request.state, "user", None):
        return RedirectResponse(_an_toan(next or "/"), status_code=302)
    # Bị middleware đá về đây (có ?next=) thì nói rõ vì sao, đừng để màn trắng trơn
    if not thongbao and next:
        thongbao = "het-phien" if request.cookies.get("refresh_token") else "can-dang-nhap"
    return HTMLResponse(
        render_login(next_url=next, notice=THONG_BAO.get(thongbao, ""))
    )


@router.post("/dang-nhap")
async def dang_nhap(request: Request):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    remember = form.get("remember") == "1"
    next_url = _an_toan(str(form.get("next", "")) or "/")

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")[:300]
    try:
        data = auth_service.login(username, password, ip=ip, user_agent=ua)
    except AuthError as err:
        # 401 (không phải 200) để fail2ban/log bên ngoài còn đếm được
        return HTMLResponse(
            render_login(
                error=err.message, code=err.code,
                next_url=next_url, username=username,
            ),
            status_code=401,
        )

    resp = RedirectResponse(next_url, status_code=303)
    dat_cookie_dang_nhap(resp, data, remember)
    return resp


@router.post("/dang-xuat")
async def dang_xuat(request: Request) -> RedirectResponse:
    user = getattr(request.state, "user", None)
    ip = request.client.host if request.client else None
    auth_service.logout(
        request.cookies.get("refresh_token", ""),
        user_id=int(user["sub"]) if user else None,
        ip=ip,
        user_agent=request.headers.get("user-agent", "")[:300],
    )
    resp = RedirectResponse("/dang-nhap?thongbao=dang-xuat", status_code=303)
    resp.delete_cookie("access_token")
    resp.delete_cookie("refresh_token")
    return resp
