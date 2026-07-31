"""Điểm khởi động ứng dụng: tạo FastAPI app và gắn các route.

Luồng hiện tại dùng POLLING qua Pancake (app/integrations/pancake) để nhận/ trả lời tin nhắn,
KHÔNG dùng webhook Facebook nữa — nên chỉ đăng ký `pancake_router`.
(Thư mục app/webhook đã bị bỏ; nếu sau này muốn dùng lại webhook Graph thì thêm
router tương ứng vào đây.)
"""

import asyncio
from contextlib import asynccontextmanager
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.api.v1.auth import router as auth_api_router
from app.core.config import settings
from app.core.request_context import current_user
from app.core.security import decode_access_token
from app.integrations.pancake.client import close_http
from app.web.routes.auth import dat_cookie_dang_nhap
from app.web.routes.auth import router as web_auth_router
from app.web.routes.data import router as data_router
from app.web.routes.main import router as ui_router
from app.web.routes.pancake import router as pancake_router
from app.web.routes.sentiment import router as cam_xuc_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Bật 2 worker nền lúc khởi động, dọn tài nguyên khi tắt server.

    Worker (xem app/workers/) chạy suốt vòng đời server — poll hội thoại về kho
    và quét cảm xúc — nên hoạt động cả khi KHÔNG ai mở trình duyệt. Tắt từng cái
    bằng `INBOX_POLL_ENABLED` / `SENTIMENT_ENABLED` trong .env.

    Client HTTP tới Pancake được dùng CHUNG cho cả vòng đời app (giữ keep-alive,
    đỡ bắt tay TLS mỗi request — xem app/integrations/pancake/client.py) nên phải tự đóng lại
    ở đây, không còn `async with` tự đóng sau mỗi lời gọi nữa.
    """
    tasks: list[asyncio.Task] = []
    if settings.inbox_poll_enabled:
        from app.workers import poll_loop

        tasks.append(asyncio.create_task(poll_loop(), name="inbox-poller"))
    # Worker cảm xúc LUÔN được tạo; quét hay không do công tắc ở trang /cam-xuc
    # quyết định (mặc định lấy theo SENTIMENT_ENABLED trong .env). Nhờ vậy bật
    # lại từ giao diện là chạy ngay, không phải khởi động lại server.
    from app.workers import sentiment_loop, task_escalation_loop

    tasks.append(asyncio.create_task(sentiment_loop(), name="sentiment"))
    # B4: 5 phút một lần đánh dấu việc quá hạn + audit "báo quản lý" (mục 19).
    tasks.append(asyncio.create_task(task_escalation_loop(), name="tasks-qua-han"))

    yield

    # Huỷ gọn gàng, nếu không uvicorn --reload sẽ để lại vòng lặp mồ côi.
    for t in tasks:
        t.cancel()
    for t in tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):  # noqa: B014 — tắt máy, nuốt hết
            pass
    await close_http()


# Khởi tạo ứng dụng FastAPI. /docs /redoc TẮT từ A2: bản đồ endpoint là thông
# tin nội bộ, không bày cho người chưa đăng nhập (khớp "việc lẻ" TIEN-DO.md).
app = FastAPI(title="FB Sales Bot", lifespan=lifespan, docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# EXCEPTION HANDLER CHUNG (A3): mọi ApiError (kể cả AuthError của A2) từ bất kỳ
# tầng nào đều thành JSON envelope đúng khuôn — route không phải try/except.
# Lỗi validate body của Pydantic cũng quy về VALIDATION_ERROR cho API.
# ---------------------------------------------------------------------------
from fastapi.exceptions import RequestValidationError  # noqa: E402

from app.core.errors import ApiError  # noqa: E402
from app.core.response import err_response  # noqa: E402


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, err: ApiError):
    # Web form (không phải /api/) dính ApiError -> để route web tự xử đẹp hơn;
    # rơi tới đây nghĩa là chưa xử -> vẫn trả envelope cho khỏi lộ traceback.
    return err_response(err.code, err.message, err.errors)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, err: RequestValidationError):
    if not request.url.path.startswith("/api/"):
        # giữ hành vi mặc định dạng 422 đơn giản cho form web
        return err_response("VALIDATION_ERROR", "Dữ liệu không hợp lệ")
    loi: dict[str, str] = {}
    for e in err.errors():
        truong = ".".join(str(p) for p in e.get("loc", []) if p != "body") or "body"
        loi.setdefault(truong, e.get("msg", "không hợp lệ"))
    return err_response("VALIDATION_ERROR", "Dữ liệu không hợp lệ", loi)


# ---------------------------------------------------------------------------
# CỔNG ĐĂNG NHẬP (A2 — docs/A2-DANG-NHAP.md mục 3.1)
# MỘT middleware khoá tất cả: web chưa đăng nhập -> 302 về /dang-nhap;
# API không token -> 401 JSON. Không phải sửa từng route.
# ---------------------------------------------------------------------------

# Miễn kiểm tra: đường vào cửa + kiểm tra sống. /forgot-password cũng miễn vì
# người quên mật khẩu thì đương nhiên chưa đăng nhập được.
_MIEN_DANG_NHAP: frozenset[str] = frozenset({
    "/dang-nhap",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/forgot-password",
    "/health",
    "/favicon.ico",
})

# Khu Bot Pancake (nhóm menu 2) — chỉ tài khoản cấp toàn hệ thống (quyền
# `bot.view`, seed chỉ gán qua _ALL cho Chủ DN + Admin) mới được vào. Chặn
# theo TIỀN TỐ ở middleware để ăn trọn mọi route con (fragment, form post...);
# /khach-hang là màn bot cũ — KH của CRM nằm ở /crm/khach-hang không dính.
_KHU_BOT: tuple[str, ...] = (
    "/bang-dieu-khien", "/tin-nhan", "/khach-hang", "/cam-xuc", "/data", "/pancake",
)


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    """Chặn từ ngoài cửa + tự làm mới access token cho web.

    Access token (30') hết hạn nhưng cookie refresh còn sống -> lặng lẽ phát
    access mới và gắn lại vào cookie của response, người dùng không bị đá ra
    giữa chừng. Payload token đặt vào request.state.user + contextvar để
    route/dependency/shell cùng đọc.
    """
    if request.url.path in _MIEN_DANG_NHAP:
        return await call_next(request)

    # 1) Access token: header Bearer (API) trước, cookie (web) sau
    auth_header = request.headers.get("authorization", "")
    token = (
        auth_header[7:].strip()
        if auth_header.lower().startswith("bearer ")
        else request.cookies.get("access_token", "")
    )
    user = decode_access_token(token)

    # 2) Web: access hết hạn nhưng còn refresh -> làm mới ngầm
    lam_moi: dict | None = None
    if not user and request.cookies.get("refresh_token"):
        from app.services import auth_service
        from app.services.auth_service import AuthError

        try:
            lam_moi = auth_service.refresh(
                request.cookies["refresh_token"],
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent", "")[:300],
            )
            user = decode_access_token(lam_moi["access_token"])
        except AuthError:
            lam_moi = None

    if not user:
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error_code": "UNAUTHORIZED",
                    "message": "Chưa đăng nhập hoặc phiên đã hết hạn",
                    "errors": {},
                },
            )
        duong_cu = request.url.path + (
            f"?{request.url.query}" if request.url.query else ""
        )
        return RedirectResponse(
            f"/dang-nhap?next={quote(duong_cu, safe='')}", status_code=302
        )

    request.state.user = user
    ctx_token = current_user.set(user)   # cho render_shell hiện tên + nút đăng xuất
    try:
        if (request.url.path.startswith(_KHU_BOT)
                and "bot.view" not in (user.get("perms") or [])):
            from app.web.views.admin import render_403

            response = HTMLResponse(render_403(
                "Khu Bot Pancake chỉ dành cho tài khoản cấp toàn hệ thống "
                "(Chủ doanh nghiệp / Admin).", heading="Bot Pancake",
            ), status_code=403)
        else:
            response = await call_next(request)
    finally:
        current_user.reset(ctx_token)
    if lam_moi:  # gắn access mới phát vào cookie
        dat_cookie_dang_nhap(response, lam_moi, remember=False)
    # Nội dung sau đăng nhập cấm cache (no-store loại trang khỏi cả bfcache):
    # đăng xuất xong bấm Back/mở lại phải ra màn đăng nhập, không moi bản cũ.
    response.headers.setdefault("Cache-Control", "no-store")
    return response


# Đăng nhập/đăng xuất: màn /dang-nhap (web) + 6 API /api/v1/auth/* (A2).
app.include_router(web_auth_router)
app.include_router(auth_api_router)

# A4 + A5: API nhân viên / vai trò / nhóm / nhật ký + khu web Quản trị.
from app.api.v1.audit import router as audit_api_router  # noqa: E402
from app.api.v1.roles import router as roles_api_router  # noqa: E402
from app.api.v1.users import router as users_api_router  # noqa: E402
from app.web.routes.admin import router as web_admin_router  # noqa: E402

app.include_router(users_api_router)
app.include_router(roles_api_router)
app.include_router(audit_api_router)
app.include_router(web_admin_router)

# B3: API lead & pipeline Sale (PIPELINE-001…004, LEAD-001…011) — luật nằm ở
# services/lead_service.py, route chỉ là lớp mỏng.
from app.api.v1.leads import router as leads_api_router  # noqa: E402

app.include_router(leads_api_router)

# B1: API khách hàng 360° (CUSTOMER-001…012, IDENTITY-001/002).
from app.api.v1.customers import router as customers_api_router  # noqa: E402

app.include_router(customers_api_router)

# B4: API công việc (TASK-001…009) — task engine chung Sale/CSKH, luật mục 19
# BRD nằm ở services/task_service.py.
from app.api.v1.tasks import router as tasks_api_router  # noqa: E402

app.include_router(tasks_api_router)

# B5: API hồ sơ tư vấn + sàng lọc an toàn (CONSULT/SYMPTOM/MEDICAL/SAFETY) —
# luật FR-050…053 nằm ở services/consult_service.py; cờ đỏ chặn đề xuất (B6).
from app.api.v1.consult import router as consult_api_router  # noqa: E402

app.include_router(consult_api_router)

# B6: API sản phẩm & liệu trình (PRODUCT-001…008 · TREATMENT-001…014) — rule
# engine đề xuất trong services/treatment_service.py, luật nằm ở DB (mục 10 BRD).
from app.api.v1.products import router as products_api_router  # noqa: E402
from app.api.v1.treatments import router as treatments_api_router  # noqa: E402

app.include_router(products_api_router)
app.include_router(treatments_api_router)

# Bộ màn CRM tạm (khung): /crm/* — cấu trúc theo danh sách màn hình, số liệu
# thật từ schema crm; lát cắt B1…B11 làm đầy dần (xem app/web/views/crm.py).
from app.web.routes.crm import router as web_crm_router  # noqa: E402

app.include_router(web_crm_router)

# Giao diện chính (menu trái): / , Bảng điều khiển, Tin nhắn, Khách hàng.
app.include_router(ui_router)

# Gắn toàn bộ route Pancake: webview danh sách page, xem hội thoại, trả lời,
# auto-refresh fragment, poll... (xem app/web/routes/pancake.py).
app.include_router(pancake_router)

# Giao diện quản lý dữ liệu bot: thêm/xem/xoá kịch bản & hội thoại mẫu (/data).
app.include_router(data_router)

# Màn hình Cảm xúc: xem hội thoại tiêu cực + BẬT/TẮT worker quét (/cam-xuc).
app.include_router(cam_xuc_router)


@app.get("/health")
def health() -> dict:
    """Endpoint kiểm tra 'sống': trả {"status": "ok"} để biết server còn chạy."""
    return {"status": "ok"}


@app.get("/poller")
def poller_status(limit: int = 20) -> dict:
    """Soi 2 worker nền: vòng chạy gần nhất, tin MỚI, page LỖI, số liệu kho.

    Mở thẳng trên trình duyệt (http://127.0.0.1:8000/poller) — tiện hơn phải
    ngồi canh log console, và xem được cả khi server chạy nền không có console.
    `limit` = số hội thoại tiêu cực gần nhất lấy từ kho.
    """
    from app.db.repositories import inbox_store

    out: dict = {}
    try:
        from app.workers import poller

        out["poller"] = poller.last_run
        out["nhip_tung_page"] = poller.trang_thai_page()
    except Exception as err:  # noqa: BLE001 — worker bị tắt trong .env
        out["poller"] = {"tat": True, "ly_do": str(err)}
    try:
        from app.workers import sentiment as sentiment_worker

        out["sentiment"] = sentiment_worker.last_run
    except Exception as err:  # noqa: BLE001
        out["sentiment"] = {"tat": True, "ly_do": str(err)}

    try:
        out["kho"] = inbox_store.stats()
        out["tieu_cuc_trong_kho"] = [
            {
                "page": r.get("page_name"), "khach": r.get("name"),
                "snippet": r.get("snippet"), "luc": r.get("updated_at"),
                "cach_quet": r.get("sentiment_method"),
            }
            for r in inbox_store.list_recent(limit, only_negative=True)
        ]
    except Exception as err:  # noqa: BLE001 — Postgres chưa bật
        out["kho"] = {"loi": str(err)}
    return out


if __name__ == "__main__":
    # Chạy trực tiếp `python app/main.py`: bật uvicorn kèm auto-reload khi sửa code.
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
