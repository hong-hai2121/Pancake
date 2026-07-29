"""Client gọi Pancake API (pages.fm) bằng access token trong .env."""

import asyncio
import base64
import binascii
import json
import re
import time
from html import unescape
from pathlib import Path

import httpx

from app.config import settings
from app.pancake.switches import is_page_enabled

# Nhãn tiếng Việt cho từng nhóm page mà Pancake trả về trong `categorized`.
# Bỏ qua `activated_page_ids` vì đó là list id, không phải list page.
_GROUPS: list[tuple[str, str]] = [
    ("activated", "Đang hoạt động"),
    ("inactivated", "Chưa kích hoạt"),
    ("hidden", "Đang ẩn"),
    ("nopermission", "Không có quyền"),
]


class PancakeError(RuntimeError):
    """Lỗi khi gọi Pancake API (HTTP lỗi hoặc success=false)."""


def _handle(resp: httpx.Response) -> dict:
    """Kiểm tra response Pancake, trả JSON dict hoặc raise PancakeError."""
    if resp.status_code != 200:
        raise PancakeError(f"Pancake API HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except ValueError as exc:  # trả HTML/không phải JSON -> sai endpoint/token
        raise PancakeError("Pancake API không trả về JSON (kiểm tra base_url/token)") from exc

    if isinstance(data, dict) and data.get("success") is False:
        raise PancakeError(data.get("message") or f"Pancake API báo lỗi: {data}")
    return data


def _url(path: str) -> str:
    """Ghép base_url + path thành URL đầy đủ (chuẩn hóa dấu '/')."""
    return f"{settings.pancake_base_url.rstrip('/')}/{path.lstrip('/')}"


def _with_token(params: dict | None) -> dict:
    """Sao chép params và tự đính kèm access_token; lỗi nếu chưa cấu hình token."""
    if not settings.pancake_access_token:
        raise PancakeError("Chưa cấu hình PANCAKE_ACCESS_TOKEN trong .env")
    query = dict(params or {})
    query["access_token"] = settings.pancake_access_token
    return query


async def _get(path: str, params: dict | None = None) -> dict:
    """GET tới Pancake API, tự đính kèm access_token, trả về JSON dict."""
    query = _with_token(params)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(_url(path), params=query)
    return _handle(resp)


async def _post(path: str, params: dict | None = None) -> dict:
    """POST tới Pancake API (access_token + params ở query string)."""
    query = _with_token(params)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(_url(path), params=query)
    return _handle(resp)


def _normalize(page: dict, group_key: str, group_label: str) -> dict:
    """Rút gọn 1 page về các field cần cho webview."""
    return {
        "id": str(page.get("id", "")),
        "name": page.get("name") or "(không tên)",
        "platform": page.get("platform") or "unknown",
        "username": page.get("username"),
        "shop_id": page.get("shop_id"),
        "role": page.get("role_in_page"),
        "is_activated": bool(page.get("is_activated")),
        "group": group_key,
        "group_label": group_label,
    }


# Bộ nhớ đệm danh sách page. Gần như mọi trang đều cần danh sách này (kể cả các
# lần auto-refresh mỗi 8–10 giây), trong khi nó rất ít thay đổi. Không cache thì
# gọi Pancake dồn dập và bị chặn (HTTP 429/5xx) khi mở nhiều tab cùng lúc.
_PAGES_CACHE: dict = {"at": 0.0, "data": []}
_PAGES_TTL = 60.0  # giây


async def list_pages(force: bool = False) -> list[dict]:
    """Trả về danh sách page mà access token có quyền truy cập.

    Mỗi phần tử là dict đã chuẩn hóa (xem `_normalize`), gắn kèm nhóm
    (đang hoạt động / chưa kích hoạt / ẩn / không quyền).
    Kết quả được nhớ đệm 60 giây; `force=True` để lấy mới ngay.
    """
    now = time.monotonic()
    if not force and _PAGES_CACHE["data"] and now - _PAGES_CACHE["at"] < _PAGES_TTL:
        return _PAGES_CACHE["data"]

    data = await _get("pages")
    categorized = data.get("categorized", {}) or {}

    pages: list[dict] = []
    for key, label in _GROUPS:
        for page in categorized.get(key, []) or []:
            if isinstance(page, dict):
                pages.append(_normalize(page, key, label))

    _PAGES_CACHE["at"], _PAGES_CACHE["data"] = now, pages
    return pages


async def get_page(page_id: str) -> dict | None:
    """Tìm 1 page theo id trong danh sách page token có quyền (best-effort)."""
    for page in await list_pages():
        if page["id"] == str(page_id):
            return page
    return None


# Ghi đè TÊN + MÀU thẻ thủ công. Public API cần token quyền Admin mới lấy được
# tên/màu thẻ; khi chưa có, khai báo tay ở đây để màn Tin nhắn hiện đúng như
# Pancake. Khóa = ID thẻ (chính là số "#id" hiện ở tab hội thoại).
TAG_OVERRIDES: dict[int, dict] = {
    175: {"text": "Đã nhận hàng", "color": "#15AFAF"},
    # Thêm thẻ khác theo mẫu: 171: {"text": "Đã chốt đơn", "color": "#16A34A"},
}


def tag_label(tag_id: int, meta: dict | None = None) -> str:
    """Tên hiển thị của 1 thẻ.

    Ưu tiên: TAG_OVERRIDES (khai báo tay) > public API (`meta`) > "Thẻ #id".
    """
    override = TAG_OVERRIDES.get(tag_id)
    if override and override.get("text"):
        return override["text"]
    if meta and (meta.get(tag_id) or {}).get("text"):
        return meta[tag_id]["text"]
    return "Hệ thống" if tag_id < 0 else f"Thẻ #{tag_id}"


def tag_color_override(tag_id: int) -> str:
    """Màu thẻ khai báo tay (TAG_OVERRIDES); "" nếu không có."""
    return (TAG_OVERRIDES.get(tag_id) or {}).get("color") or ""


# page_access_token sinh trong phiên chạy này (giữ trong RAM để khỏi sinh lại
# nhiều lần); đồng thời được ghi xuống .env để LẦN SAU chạy là có sẵn.
_RUNTIME_PAGE_TOKENS: dict[str, str] = {}


def _parse_page_tokens(raw: str) -> dict[str, str]:
    """Parse chuỗi JSON {page_id: token} -> dict; rỗng/sai -> {}."""
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _page_tokens() -> dict[str, str]:
    """Map {page_id: page_access_token}: gộp .env + token vừa sinh trong phiên."""
    tokens = _parse_page_tokens(settings.pancake_page_tokens)
    tokens.update(_RUNTIME_PAGE_TOKENS)
    return tokens


def _tag_page_ids() -> set[str]:
    """Tập page được phép TỰ SINH page token (từ PANCAKE_TAG_PAGE_IDS)."""
    raw = settings.pancake_tag_page_ids or ""
    return {p.strip() for p in raw.split(",") if p.strip()}


def _env_path() -> Path:
    """Đường dẫn file .env ở gốc project (app/pancake/client.py -> parents[2])."""
    return Path(__file__).resolve().parents[2] / ".env"


def _save_page_token(page_id: str, token: str) -> None:
    """Ghi/cập nhật PANCAKE_PAGE_TOKENS trong .env để lần sau tái dùng.

    Best-effort: lỗi ghi file không được làm hỏng luồng chính (đã có bản trong RAM).
    """
    path = _env_path()
    current = _parse_page_tokens(settings.pancake_page_tokens)
    current.update(_RUNTIME_PAGE_TOKENS)
    current[str(page_id)] = token
    value = json.dumps(current, ensure_ascii=False, separators=(",", ":"))
    new_line = f"PANCAKE_PAGE_TOKENS={value}"
    try:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for i, line in enumerate(lines):
            if line.strip().startswith("PANCAKE_PAGE_TOKENS="):
                lines[i] = new_line
                break
        else:
            lines.append(new_line)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass  # giữ token trong RAM cho phiên này; lần sau sẽ sinh lại


async def generate_page_token(page_id: str) -> str:
    """Gọi Pancake sinh page_access_token cho 1 page.

    ⚠️ Cần token Pancake có quyền Admin trên page; thiếu quyền -> PancakeError
    ("Thiếu quyền Admin"). Trả về chuỗi token nếu thành công.
    """
    data = await _post(f"pages/{page_id}/generate_page_access_token")
    token = data.get("page_access_token")
    if not token:
        raise PancakeError(data.get("message") or "Không tạo được page_access_token")
    return str(token)


async def ensure_page_token(page_id: str) -> str | None:
    """Trả page_access_token của page: ưu tiên có sẵn, thiếu thì tự sinh + lưu.

    Chỉ tự sinh cho page nằm trong PANCAKE_TAG_PAGE_IDS. None nếu không có và
    không sinh được (vd thiếu quyền Admin) — khi đó màn Tin nhắn lùi về 'Thẻ #id'.
    """
    pid = str(page_id)
    existing = _page_tokens().get(pid)
    if existing:
        return existing
    if pid not in _tag_page_ids():
        return None
    try:
        token = await generate_page_token(pid)
    except (PancakeError, httpx.HTTPError):
        return None
    _RUNTIME_PAGE_TOKENS[pid] = token
    _save_page_token(pid, token)
    return token


# Cache tên thẻ theo page (thẻ gần như không đổi; tránh gọi public API mỗi request).
_TAGS_CACHE: dict[str, tuple[float, dict[int, dict]]] = {}
_TAGS_TTL = 300.0  # giây


async def list_tags(page_id: str) -> dict[int, dict]:
    """Định nghĩa thẻ của 1 page qua public API: {tag_id: {'text', 'color'}}.

    Tự lấy (hoặc tự sinh) page_access_token; không có thì trả {}.
    Lỗi mạng/token sai cũng trả {} (để màn Tin nhắn tự lùi về 'Thẻ #id').
    """
    pid = str(page_id)

    now = time.monotonic()
    cached = _TAGS_CACHE.get(pid)
    if cached and now - cached[0] < _TAGS_TTL:
        return cached[1]

    token = await ensure_page_token(pid)
    if not token:
        return {}

    url = f"{settings.pancake_public_base_url.rstrip('/')}/pages/{pid}/tags"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                url, params={"page_access_token": token},
                headers={"Accept": "application/json"},
            )
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("success") is False:
        return {}

    tags: dict[int, dict] = {}
    for t in data.get("tags") or []:
        if not isinstance(t, dict):
            continue
        try:
            tid = int(t.get("id"))
        except (TypeError, ValueError):
            continue
        tags[tid] = {
            "text": t.get("text") or t.get("name") or f"Thẻ #{tid}",
            "color": t.get("color") or t.get("lighten_color") or "",
        }
    _TAGS_CACHE[pid] = (now, tags)
    return tags


def _tag_ids(conv: dict) -> list[int]:
    """Lấy danh sách ID thẻ (số nguyên) của 1 hội thoại; bỏ qua giá trị lạ."""
    ids: list[int] = []
    for t in conv.get("tags") or []:
        try:
            ids.append(int(t))
        except (TypeError, ValueError):
            continue
    return ids


def _normalize_conv(conv: dict) -> dict:
    """Rút gọn 1 conversation về các field cần cho webview 'người nhắn tin'."""
    customer = (conv.get("customers") or [{}])[0]
    frm = conv.get("from") or {}
    return {
        "conv_id": str(conv.get("id", "")),
        "customer_id": str(customer.get("id") or ""),
        "name": customer.get("name") or frm.get("name") or "(không tên)",
        "fb_id": str(customer.get("fb_id") or frm.get("id") or ""),
        "snippet": unescape(conv.get("snippet") or "").strip(),
        "updated_at": conv.get("updated_at") or "",
        "message_count": int(conv.get("message_count") or 0),
        "unread_count": int(conv.get("unread_count") or 0),
        "seen": bool(conv.get("seen")),
        "tags": _tag_ids(conv),
    }


async def _fetch_conversations(
    page_id: str, msg_type: str, limit: int | None
) -> list[dict]:
    """Gọi Pancake THẬT (không cache) lấy danh sách hội thoại đã chuẩn hoá."""
    params: dict = {"type": msg_type}
    if limit is not None:
        params["limit"] = limit
    data = await _get(f"pages/{page_id}/conversations", params)
    convs = data.get("conversations") or []
    items = [_normalize_conv(c) for c in convs if isinstance(c, dict)]
    items.sort(key=lambda c: c["updated_at"], reverse=True)
    if limit is not None:
        items = items[:limit]
    return items


# Cache stale-while-revalidate cho danh sách hội thoại. Mục tiêu: lần đầu vào 1
# trang thì chịu delay gọi Pancake; các lần sau **trả bản cũ NGAY** rồi làm mới
# ngầm — nên chuyển trang không còn khựng. Khoá theo (page, loại, limit) để mỗi
# màn (inbox 20 / khách 100 / dashboard 50 / lọc thẻ 200) có bản riêng, không lẫn.
_CONV_CACHE: dict[tuple, dict] = {}
_CONV_FRESH = 8.0     # <8s: coi là còn mới -> trả luôn, khỏi gọi lại
_CONV_STALE = 600.0   # >10 phút: coi như quá cũ -> gọi đồng bộ lại cho chắc


async def _refresh_conversations(
    key: tuple, page_id: str, msg_type: str, limit: int | None
) -> None:
    """Làm mới cache ngầm (cho SWR). Lỗi thì GIỮ bản cũ, chỉ mở lại khoá refresh."""
    try:
        items = await _fetch_conversations(page_id, msg_type, limit)
        _CONV_CACHE[key] = {"at": time.monotonic(), "data": items, "refreshing": False}
    except Exception:  # best-effort nền: không để bản cũ bị mất vì 1 lần lỗi mạng
        entry = _CONV_CACHE.get(key)
        if entry:
            entry["refreshing"] = False


async def list_conversations(
    page_id: str, msg_type: str = "INBOX", limit: int | None = None
) -> list[dict]:
    """Danh sách hội thoại của 1 page, mới nhất trước (có cache SWR).

    `msg_type` = "INBOX" (tin nhắn riêng) hoặc "COMMENT" (bình luận).
    `limit` được gửi thẳng cho API rồi vẫn cắt lại phía Python cho chắc. Mỗi phần
    tử đã chuẩn hóa (xem `_normalize_conv`).

    Cache: còn mới (<8s) trả ngay; cũ hơn nhưng chưa quá hạn thì **trả bản cũ ngay
    lập tức** và gọi Pancake làm mới NỀN (lần vào sau thấy dữ liệu mới); chưa có
    cache / quá cũ thì gọi đồng bộ (chỉ lần đầu chịu delay).

    Page đang TẮT (xem pancake/switches) -> trả rỗng, KHÔNG gọi Pancake.
    """
    if not is_page_enabled(page_id):
        return []
    key = (str(page_id), msg_type, limit)
    now = time.monotonic()
    entry = _CONV_CACHE.get(key)

    if entry:
        age = now - entry["at"]
        if age < _CONV_FRESH:
            return entry["data"]                     # còn mới -> trả ngay
        if age < _CONV_STALE:
            if not entry.get("refreshing"):          # tránh nhiều refresh chồng nhau
                entry["refreshing"] = True
                asyncio.create_task(
                    _refresh_conversations(key, page_id, msg_type, limit)
                )
            return entry["data"]                      # SWR: trả bản cũ ngay

    # Không có cache hoặc đã quá cũ -> gọi đồng bộ (lần đầu chịu delay).
    items = await _fetch_conversations(page_id, msg_type, limit)
    _CONV_CACHE[key] = {"at": time.monotonic(), "data": items, "refreshing": False}
    return items


# --------------------------------------------- hộp thư GỘP mọi page đang BẬT
# Giá trị `page_id` đặc biệt cho chế độ gộp ở màn Tin nhắn (không phải id thật).
ALL_PAGES = "ALL"

# Gộp N page = N lời gọi Pancake. Hai van giảm áp để không dính 429:
#   - Semaphore: tối đa 5 lời gọi chạy song song, dù bật bao nhiêu page.
#   - Cache SWR riêng cho bản ĐÃ GỘP: nhịp auto-refresh của trình duyệt đọc
#     thẳng bản gộp, chỉ bung ra N lời gọi tối đa 1 lần mỗi _ALL_FRESH giây.
_ALL_CONCURRENCY = 5
_ALL_CACHE: dict[tuple, dict] = {}
_ALL_FRESH = 15.0
_ALL_STALE = 600.0


async def _fetch_all_conversations(msg_type: str, limit: int) -> list[dict]:
    """Lấy song song hội thoại của MỌI page đang BẬT rồi trộn mới -> cũ.

    Mỗi hội thoại được gắn thêm `page_id` + `page_name` vì ở chế độ gộp, giao
    diện không còn suy ra được page từ ngữ cảnh nữa (mở khung chat và gửi trả
    lời đều phải dùng đúng page thật của hội thoại đó).
    """
    pages = [p for p in await list_pages() if is_page_enabled(p["id"])]
    if not pages:
        return []
    sem = asyncio.Semaphore(_ALL_CONCURRENCY)

    async def one(page: dict) -> list[dict]:
        async with sem:
            items = await list_conversations(page["id"], msg_type, limit)
        # Copy từng dict: bản gốc đang nằm trong _CONV_CACHE, gắn thẳng page_id
        # vào đó sẽ rò sang cả chế độ xem 1 page.
        return [
            dict(c, page_id=page["id"], page_name=page.get("name") or "")
            for c in items
        ]

    # 1 page hỏng (mất quyền, 429...) KHÔNG được làm sập cả hộp thư gộp.
    results = await asyncio.gather(
        *(one(p) for p in pages), return_exceptions=True
    )
    merged: list[dict] = []
    for res in results:
        if isinstance(res, list):
            merged.extend(res)
    merged.sort(key=lambda c: c["updated_at"], reverse=True)
    return merged[:limit]


async def _refresh_all_conversations(key: tuple, msg_type: str, limit: int) -> None:
    """Làm mới cache gộp ngầm (SWR). Lỗi thì GIỮ bản cũ, chỉ mở lại khoá."""
    try:
        items = await _fetch_all_conversations(msg_type, limit)
        _ALL_CACHE[key] = {"at": time.monotonic(), "data": items, "refreshing": False}
    except Exception:
        entry = _ALL_CACHE.get(key)
        if entry:
            entry["refreshing"] = False


async def list_all_conversations(
    msg_type: str = "INBOX", limit: int = 20
) -> list[dict]:
    """Hộp thư GỘP: hội thoại của mọi page đang BẬT, mới nhất trước.

    Cùng cơ chế cache SWR như `list_conversations` nhưng ở mức bản đã gộp.
    Page đang TẮT bị bỏ qua hoàn toàn (guard nằm sẵn trong `list_conversations`).
    """
    key = (msg_type, limit)
    now = time.monotonic()
    entry = _ALL_CACHE.get(key)

    if entry:
        age = now - entry["at"]
        if age < _ALL_FRESH:
            return entry["data"]
        if age < _ALL_STALE:
            if not entry.get("refreshing"):
                entry["refreshing"] = True
                asyncio.create_task(_refresh_all_conversations(key, msg_type, limit))
            return entry["data"]

    items = await _fetch_all_conversations(msg_type, limit)
    _ALL_CACHE[key] = {"at": time.monotonic(), "data": items, "refreshing": False}
    return items


async def enabled_pages() -> list[dict]:
    """Danh sách page đang BẬT (dùng để đếm/hiển thị ở ô chọn page)."""
    return [p for p in await list_pages() if is_page_enabled(p["id"])]


# ----------------------------------------------------- gọi API thô (tab Thử API)
def mask_token(value: str) -> str:
    """Che bớt token để chụp màn hình / dán log không lộ khoá."""
    text = str(value or "")
    if len(text) <= 14:
        return "•" * len(text)
    return f"{text[:8]}…{text[-4:]} ({len(text)} ký tự)"


async def raw_call(
    method: str, path: str, params: dict | None = None, public: bool = False
) -> dict:
    """Gọi THẲNG 1 endpoint Pancake, trả về cả request lẫn response chưa xử lý.

    Dành riêng cho tab "Thử API" (/data/thu-api). KHÁC hẳn `_get`/`_post`:
    không chuẩn hoá dữ liệu, không cache, không chặn theo công tắc page, và
    KHÔNG raise khi Pancake trả lỗi — vì mục đích là xem đúng những gì đã gửi
    đi và những gì máy chủ trả về, kể cả khi lỗi.

    `public=True` -> dùng public API (`pancake_public_base_url`) và xác thực
    bằng `page_access_token` do người dùng tự truyền, không đính access_token.
    """
    if public:
        base = settings.pancake_public_base_url
        query = dict(params or {})
    else:
        base = settings.pancake_base_url
        query = _with_token(params)
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"

    started = time.monotonic()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method.upper(), url, params=query,
            headers={"Accept": "application/json"},
        )
    elapsed_ms = (time.monotonic() - started) * 1000

    try:
        body, is_json = resp.json(), True
    except ValueError:                      # trả HTML/text -> vẫn cho xem thô
        body, is_json = resp.text, False

    return {
        "method": method.upper(),
        "url": url,
        "params": query,
        "status": resp.status_code,
        "reason": resp.reason_phrase,
        "elapsed_ms": round(elapsed_ms, 1),
        "size": len(resp.content),
        "is_json": is_json,
        "body": body,
        "resp_headers": dict(resp.headers),
    }


def _plain_text(msg: dict) -> str:
    """Lấy nội dung text sạch: ưu tiên original_message, fallback bỏ tag HTML.

    Giữ lại xuống dòng (<br>, </div>) để hiển thị đúng trong khung chat.
    """
    text = msg.get("original_message")
    if not text:
        html = msg.get("message") or ""
        html = re.sub(r"(?i)<br\s*/?>", "\n", html)
        html = re.sub(r"(?i)</(div|p)>", "\n", html)
        text = unescape(re.sub(r"<[^>]+>", "", html))
    lines = [ln.strip() for ln in (text or "").splitlines()]
    return "\n".join(lines).strip()


def _normalize_msg(msg: dict, page_id: str) -> dict:
    """Rút gọn 1 message trong thread hội thoại."""
    frm = msg.get("from") or {}
    sender_id = str(frm.get("id") or "")
    attachments = []
    for att in msg.get("attachments") or []:
        if isinstance(att, dict):
            url = att.get("url") or att.get("image_url") or att.get("src")
            attachments.append({"type": att.get("type") or "file", "url": url})
    return {
        "id": str(msg.get("id") or ""),
        "sender_id": sender_id,
        "sender_name": frm.get("name") or "",
        "is_page": sender_id == str(page_id),
        "text": _plain_text(msg),
        "inserted_at": msg.get("inserted_at") or "",
        "attachments": attachments,
    }


async def get_conversation(
    page_id: str, conv_id: str, customer_id: str | None = None
) -> dict:
    """Toàn bộ tin nhắn của 1 hội thoại, sắp xếp cũ -> mới.

    Trả về {conv_id, customer_name, messages: [...]}.
    Page đang TẮT -> trả rỗng, KHÔNG gọi Pancake.
    """
    if not is_page_enabled(page_id):
        return {"conv_id": conv_id, "customer_name": "", "messages": []}
    params = {"customer_id": customer_id} if customer_id else None
    data = await _get(f"pages/{page_id}/conversations/{conv_id}/messages", params)
    raw = data.get("messages") or []
    msgs = [_normalize_msg(m, page_id) for m in raw if isinstance(m, dict)]
    msgs.sort(key=lambda m: m["inserted_at"])
    customer_name = next(
        (m["sender_name"] for m in reversed(msgs) if not m["is_page"] and m["sender_name"]),
        "",
    )
    return {"conv_id": conv_id, "customer_name": customer_name, "messages": msgs}


async def send_message(
    page_id: str, conv_id: str, message: str, customer_id: str | None = None
) -> dict:
    """Gửi 1 tin nhắn trả lời vào hội thoại (action=reply_inbox).

    ⚠️ Đây là hành động GỬI THẬT tới khách qua Pancake — không hoàn tác được.
    Page đang TẮT -> CHẶN, không gửi.
    """
    if not is_page_enabled(page_id):
        raise PancakeError("Page đang TẮT — không cho phép gửi tin. Bật lại ở Bảng điều khiển.")
    params = {"action": "reply_inbox", "message": message}
    if customer_id:
        params["customer_id"] = customer_id
    return await _post(f"pages/{page_id}/conversations/{conv_id}/messages", params)


def token_owner() -> dict:
    """Giải mã payload JWT của access token để biết chủ token (không cần mạng).

    Trả về {} nếu không giải mã được — chỉ dùng để hiển thị, không dùng xác thực.
    """
    token = settings.pancake_access_token
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # pad base64url
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (IndexError, ValueError, binascii.Error):
        return {}
    return {
        "name": payload.get("fb_name") or payload.get("name"),
        "fb_id": payload.get("fb_id"),
        "exp": payload.get("exp"),
    }
