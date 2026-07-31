"""Client gọi Pancake API (pages.fm) bằng access token trong .env."""

import asyncio
import base64
import binascii
import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.paths import ENV_FILE
from app.integrations.pancake.switches import is_page_enabled

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


# --------------------------------------------------- kết nối HTTP dùng chung
# Trước đây mỗi lời gọi tự `async with httpx.AsyncClient(...)` -> mở kết nối và
# BẮT TAY TLS LẠI TỪ ĐẦU mỗi request. Hộp thư gộp bật N page thì mỗi nhịp
# auto-refresh là N lần bắt tay. Dùng chung 1 client để giữ keep-alive.
#
# KHÔNG đặt header mặc định `Accept: application/json` ở đây: Pancake đổi hành
# vi theo header đó (route không phải API trả 406 thay vì HTML), giữ nguyên như
# cũ để không đổi ngầm kết quả của các endpoint đang chạy.
_HTTP: httpx.AsyncClient | None = None

# Task refresh nền (SWR). Phải GIỮ tham chiếu: asyncio chỉ giữ weak reference
# tới task đang chạy, không giữ thì có thể bị GC dọn giữa chừng -> mất lượt
# làm mới mà không báo lỗi gì.
_BG_TASKS: set[asyncio.Task] = set()


def http() -> httpx.AsyncClient:
    """Client HTTP dùng chung; tạo lười ở lần gọi đầu (trong event loop)."""
    global _HTTP
    if _HTTP is None or _HTTP.is_closed:
        _HTTP = httpx.AsyncClient(
            timeout=20,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _HTTP


async def close_http() -> None:
    """Đóng client dùng chung (app gọi lúc shutdown — xem app/main.py)."""
    global _HTTP
    if _HTTP is not None and not _HTTP.is_closed:
        await _HTTP.aclose()
    _HTTP = None


def _spawn(coro) -> None:
    """Chạy 1 coroutine nền và GIỮ tham chiếu tới khi nó xong."""
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


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
    resp = await http().get(_url(path), params=query)
    return _handle(resp)


async def _post(path: str, params: dict | None = None) -> dict:
    """POST tới Pancake API (access_token + params ở query string)."""
    query = _with_token(params)
    resp = await http().post(_url(path), params=query)
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
#
# TTL để DÀI (15 phút) chứ không phải 1 phút: danh sách page, vai trò
# (`role_in_page`) và trạng thái kích hoạt hầu như không đổi trong ngày, mà nhịp
# tự cập nhật của màn Tin nhắn thì gọi hàm này liên tục — TTL 1 phút nghĩa là
# đều đặn 60 lượt gọi Pancake mỗi giờ chỉ để nhận lại y hệt dữ liệu cũ. Khi cần
# mới ngay (vừa nâng quyền Admin, vừa thêm page) thì bấm nút "Cập nhật trạng
# thái" ở Bảng điều khiển — nó gọi `list_pages(force=True)`.
_PAGES_CACHE: dict = {"at": 0.0, "data": [], "luc": None}
_PAGES_TTL = 900.0  # giây (15 phút)


def pages_cache_luc():
    """Thời điểm (datetime) lần chót thực sự hỏi Pancake. None = chưa lần nào.

    Dùng để hiện "cập nhật lúc ..." cạnh nút bấm — không có mốc này thì người
    dùng không biết số liệu đang xem là mới hay đã cũ 15 phút.
    """
    return _PAGES_CACHE.get("luc")


async def list_pages(force: bool = False) -> list[dict]:
    """Trả về danh sách page mà access token có quyền truy cập.

    Mỗi phần tử là dict đã chuẩn hóa (xem `_normalize`), gắn kèm nhóm
    (đang hoạt động / chưa kích hoạt / ẩn / không quyền).
    Kết quả được nhớ đệm `_PAGES_TTL` giây; `force=True` để lấy mới ngay.
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
    _PAGES_CACHE["luc"] = datetime.now(timezone.utc).astimezone()
    return pages


async def get_page(page_id: str) -> dict | None:
    """Tìm 1 page theo id trong danh sách page token có quyền (best-effort)."""
    for page in await list_pages():
        if page["id"] == str(page_id):
            return page
    return None


# Ghi đè TÊN + MÀU thẻ thủ công — chỉ còn là LƯỚI ĐỠ cho page KHÔNG có quyền
# Admin (không sinh được page_access_token nên không lấy được thẻ thật). Khóa =
# ID thẻ (chính là số "#id" hiện ở tab hội thoại).
#
# ⚠️ Bảng này KHÔNG theo page, mà cùng một số ID ở 2 page là 2 thẻ khác nhau —
# nên nó xếp SAU dữ liệu thật: page nào lấy được thẻ thì luôn hiện tên thật của
# chính page đó, khai báo ở đây không đè lên được (khai đúng cho page A sẽ dán
# nhầm cho page B). Càng ít mục ở đây càng tốt.
TAG_OVERRIDES: dict[int, dict] = {
    175: {"text": "Đã nhận hàng", "color": "#15AFAF"},
    # Thêm thẻ khác theo mẫu: 171: {"text": "Đã chốt đơn", "color": "#16A34A"},
}


def tag_label(tag_id: int, meta: dict | None = None) -> str:
    """Tên hiển thị của 1 thẻ.

    Ưu tiên: tên THẬT của page (`meta` — public API hoặc kho) > TAG_OVERRIDES
    (khai báo tay) > "Thẻ #id".
    """
    if meta and (meta.get(tag_id) or {}).get("text"):
        return meta[tag_id]["text"]
    override = TAG_OVERRIDES.get(tag_id)
    if override and override.get("text"):
        return override["text"]
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
    """Đường dẫn file .env ở gốc project (xem app/core/paths.py)."""
    return ENV_FILE


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


# Tên/màu thẻ lấy theo BA TẦNG, vì mỗi tầng bù đúng chỗ yếu của tầng sau:
#
#   1. RAM (dưới đây)     — thẻ gần như không đổi, khỏi gọi gì mỗi lần render.
#   2. Kho `watcher.the_pancake` — bản sao bền: mất token/Pancake lỗi/vừa restart
#      vẫn có tên thẻ mà hiện, thay vì tụt về "Thẻ #175". Cũng là nguồn DUY NHẤT
#      của hộp thư GỘP (chế độ đó không gọi Pancake lúc render).
#   3. Public API         — nguồn sự thật; gọi được là ghi đè lại tầng 2.
#
# Mỗi mục cache mang theo TTL riêng: bản lấy từ API sống lâu (5 phút), bản đọc
# tạm từ kho sống ngắn (1 phút) để token vừa được cấp lại là thử API lại sớm.
_TAGS_CACHE: dict[str, tuple[float, float, dict[int, dict]]] = {}
_TAGS_TTL = 300.0      # giây — bản lấy được từ public API
_TAGS_DB_TTL = 60.0    # giây — bản đọc tạm từ kho (API đang hỏng)


def _luu_the_vao_kho(page_id: str, tags: dict[int, dict]) -> None:
    """Ghi định nghĩa thẻ xuống kho. Best-effort: DB hỏng KHÔNG được làm hỏng UI."""
    try:
        from app.db.repositories import tag_store

        tag_store.upsert_tags(page_id, tags)
    except Exception:  # noqa: BLE001 — chạy backend supabase/DB chưa lên cũng bỏ qua
        pass


def _doc_the_tu_kho(page_id: str) -> dict[int, dict]:
    """Đọc định nghĩa thẻ đã lưu. Best-effort: lỗi -> {} (UI lùi về 'Thẻ #id')."""
    try:
        from app.db.repositories import tag_store

        return tag_store.load_tags(page_id)
    except Exception:  # noqa: BLE001
        return {}


async def _goi_api_the(page_id: str) -> dict[int, dict]:
    """Hỏi public API định nghĩa thẻ của 1 page. Thiếu token/lỗi/sai shape -> {}."""
    token = await ensure_page_token(page_id)
    if not token:
        return {}

    url = f"{settings.pancake_public_base_url.rstrip('/')}/pages/{page_id}/tags"
    try:
        resp = await http().get(
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
    return tags


async def list_tags(page_id: str) -> dict[int, dict]:
    """Định nghĩa thẻ của 1 page: {tag_id: {'text', 'color'}}. Ba tầng như trên.

    Không bao giờ ném lỗi: hỏng cả ba tầng thì trả {} và màn Tin nhắn tự lùi về
    'Thẻ #id'. KHÔNG cache kết quả rỗng — có vậy page vừa được cấp quyền Admin
    mới hiện thẻ ngay lần render kế tiếp, không phải chờ hết TTL.
    """
    pid = str(page_id)

    now = time.monotonic()
    cached = _TAGS_CACHE.get(pid)
    if cached and now - cached[0] < cached[1]:
        return cached[2]

    tags = await _goi_api_the(pid)
    if tags:
        await asyncio.to_thread(_luu_the_vao_kho, pid, tags)
        _TAGS_CACHE[pid] = (now, _TAGS_TTL, tags)
        return tags

    # API không cho (thiếu quyền/mạng lỗi/429) -> dùng bản đã lưu.
    tags = await asyncio.to_thread(_doc_the_tu_kho, pid)
    if tags:
        _TAGS_CACHE[pid] = (now, _TAGS_DB_TTL, tags)
    return tags


async def refresh_tags_all_pages() -> dict[str, int]:
    """Làm tươi thẻ của mọi page CÓ THỂ lấy được -> {page_id: số thẻ}.

    Worker nền gọi định kỳ. Không có bước này thì kho thẻ chỉ được ghi khi có
    người mở màn Tin nhắn của ĐÚNG page đó — ai chỉ dùng hộp thư GỘP sẽ không
    bao giờ thấy tên thẻ, vì chế độ gộp chỉ đọc kho.

    Chỉ đụng tới page đã có page_access_token sẵn hoặc được phép tự sinh
    (`PANCAKE_TAG_PAGE_IDS`) — page khác gọi cũng chỉ tốn lời gọi vô ích.
    """
    pids = sorted(_tag_page_ids() | set(_page_tokens()))
    out: dict[str, int] = {}
    for pid in pids:
        _TAGS_CACHE.pop(pid, None)      # ép đi đường API, không lấy bản trong RAM
        tags = await list_tags(pid)
        if tags:
            out[pid] = len(tags)
    return out


def _tag_ids(conv: dict) -> list[int]:
    """Lấy danh sách ID thẻ (số nguyên) của 1 hội thoại; bỏ qua giá trị lạ."""
    ids: list[int] = []
    for t in conv.get("tags") or []:
        try:
            ids.append(int(t))
        except (TypeError, ValueError):
            continue
    return ids


def _phones(conv: dict) -> list[str]:
    """Các số điện thoại Pancake bắt được trong hội thoại (đã bỏ trùng, giữ thứ tự).

    Nằm ở `recent_phone_numbers`: mỗi phần tử có `phone_number`/`captured`.
    """
    out: list[str] = []
    for item in conv.get("recent_phone_numbers") or []:
        if not isinstance(item, dict):
            continue
        sdt = str(item.get("phone_number") or item.get("captured") or "").strip()
        if sdt and sdt not in out:
            out.append(sdt)
    return out


def _normalize_conv(conv: dict) -> dict:
    """Rút gọn 1 conversation về các field app dùng, KÈM bản thô để lưu lại.

    Khoá `raw` giữ nguyên object Pancake trả về (32 trường) — webview không đụng
    tới, nhưng kho `watcher.hoi_thoai` lưu lại để sau này cần trường nào cũng moi
    ra được mà không phải gọi lại API (dữ liệu cũ thì gọi lại cũng không có).
    """
    customer = (conv.get("customers") or [{}])[0]
    frm = conv.get("from") or {}
    last_by = conv.get("last_sent_by") or {}
    phones = _phones(conv)
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
        # --- phần thêm để lưu kho (webview cũ không dùng, không ảnh hưởng gì) ---
        "avatar_url": customer.get("avatar_url") or "",
        "loai": conv.get("type") or "",
        "inserted_at": conv.get("inserted_at") or "",
        # Khác `updated_at`: cái kia đổi cả khi PAGE trả lời, cái này chỉ đổi khi
        # KHÁCH nhắn -> dùng để biết ai đang chờ được trả lời.
        "last_customer_at": conv.get("last_customer_interactive_at") or "",
        "last_sent_by_id": str(last_by.get("id") or ""),
        "last_sent_by_name": last_by.get("name") or last_by.get("displayName") or "",
        "phones": phones,
        "has_phone": bool(conv.get("has_phone") or phones),
        "assignee_ids": [str(x) for x in (conv.get("assignee_ids") or [])],
        "is_pinned": bool(conv.get("is_pinned")),
        "raw": conv,
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
                _spawn(_refresh_conversations(key, page_id, msg_type, limit))
            return entry["data"]                      # SWR: trả bản cũ ngay

    # Không có cache hoặc đã quá cũ -> gọi đồng bộ (lần đầu chịu delay).
    items = await _fetch_conversations(page_id, msg_type, limit)
    _CONV_CACHE[key] = {"at": time.monotonic(), "data": items, "refreshing": False}
    return items


async def fetch_conversations_fresh(
    page_id: str, msg_type: str = "INBOX", limit: int = 20
) -> list[dict]:
    """Gọi Pancake THẲNG, bỏ qua cache — dành cho worker poller (app/workers).

    Poller là nguồn ghi duy nhất của kho `watcher.hoi_thoai` nên phải thấy dữ
    liệu thật, không phải bản cũ trong cache. Kết quả được **nạp luôn vào
    `_CONV_CACHE`** để các màn còn lại (Khách hàng, lọc thẻ...) dùng ké, khỏi
    gọi Pancake thêm lần nữa.
    """
    if not is_page_enabled(page_id):
        return []
    items = await _fetch_conversations(page_id, msg_type, limit)
    _CONV_CACHE[(str(page_id), msg_type, limit)] = {
        "at": time.monotonic(), "data": items, "refreshing": False,
    }
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
                _spawn(_refresh_all_conversations(key, msg_type, limit))
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
    resp = await http().request(
        method.upper(), url, params=query,
        headers={"Accept": "application/json"},
        timeout=30,          # dò tay có thể chạm endpoint chậm hơn luồng thường
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
