"""Route màn hình Cảm xúc: xem kết quả quét + BẬT/TẮT worker.

Gắn ở prefix /cam-xuc. Mọi thao tác đổi trạng thái đều POST rồi redirect 303 về
lại trang (tránh gửi lại form khi F5).
"""

import asyncio
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.cam_xuc.webview import render_cam_xuc
from app.db import inbox_store
from app.workers import switch

router = APIRouter(prefix="/cam-xuc", tags=["cam-xuc"])

_SO_TIEU_CUC = 50    # số hội thoại tiêu cực hiện tối đa
_SO_NHAT_KY = 25     # số dòng nhật ký quét gần đây


def _back(ok: str = "", error: str = "") -> RedirectResponse:
    """Redirect 303 về /cam-xuc kèm thông báo."""
    params = {k: v for k, v in (("ok", ok), ("error", error)) if v}
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"/cam-xuc{query}", status_code=303)


async def _form(request: Request) -> dict[str, str]:
    """Đọc body form -> dict giá trị đầu tiên."""
    raw = parse_qs((await request.body()).decode("utf-8"))
    return {k: (v[0] if v else "").strip() for k, v in raw.items()}


def _telegram_chat() -> str:
    """Chat id Telegram đang cấu hình ("" = chưa bật báo Telegram).

    Đọc từ `os.environ` chứ không đọc file: worker nạp `.env` lúc khởi động, nên
    đây đúng là giá trị mà tiến trình ĐANG chạy sẽ dùng — sửa `.env` mà chưa
    khởi động lại thì trang này vẫn báo "chưa cấu hình", đúng thực tế.
    """
    import os

    from app.workers import sentiment  # noqa: F401 — import để chắc chắn .env đã nạp

    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        return ""
    return (os.getenv("TELEGRAM_CHAT_ID") or "").strip()


def _tu_khoa() -> list[str]:
    """Danh sách từ khoá tiêu cực hiện hành (dùng chung với ZPancake).

    Import trong hàm: `app.workers.sentiment` kéo theo module của ZPancake, không
    nên nạp lúc import route (trang vẫn phải mở được kể cả khi phần đó lỗi).
    """
    try:
        from app.workers.sentiment import zp_sentiment

        return list(zp_sentiment.get_keywords())
    except Exception:  # noqa: BLE001 — thiếu file/lỗi import thì coi như chưa có
        return []


@router.get("", response_class=HTMLResponse)
async def trang_cam_xuc(ok: str = "", error: str = "") -> HTMLResponse:
    """Trang chính: công tắc, số liệu, hội thoại tiêu cực, nhật ký quét."""
    so_lieu: dict = {}
    tieu_cuc: list[dict] = []
    nhat_ky: list[dict] = []
    loi_kho = ""
    try:
        # Đọc DB là lời gọi đồng bộ -> đẩy sang thread cho khỏi chặn event loop
        # (worker nền vẫn phải chạy mượt trong lúc render trang này).
        so_lieu, tieu_cuc, nhat_ky = await asyncio.gather(
            asyncio.to_thread(inbox_store.stats),
            asyncio.to_thread(inbox_store.list_recent, _SO_TIEU_CUC, None, True),
            asyncio.to_thread(inbox_store.list_scanned_recent, _SO_NHAT_KY),
        )
    except Exception as exc:  # noqa: BLE001 — Postgres chưa bật: vẫn cho xem công tắc
        loi_kho = str(exc)

    return HTMLResponse(
        render_cam_xuc(
            bat=switch.is_on(), cach_quet=switch.cach_quet(), so_lieu=so_lieu,
            tieu_cuc=tieu_cuc, nhat_ky=nhat_ky, tu_khoa=_tu_khoa(),
            telegram_chat=_telegram_chat(), loi_kho=loi_kho, ok=ok, error=error,
        )
    )


@router.post("/bat-tat")
async def bat_tat() -> RedirectResponse:
    """Lật công tắc quét cảm xúc — có tác dụng ở vòng lặp kế tiếp (≤ 8 giây)."""
    bat = switch.toggle()
    return _back(
        ok="Đã BẬT quét cảm xúc — worker sẽ quét mẻ đầu trong vài giây."
        if bat else
        "Đã TẮT quét cảm xúc. Hội thoại vẫn được kéo về kho, chỉ không quét nữa."
    )


@router.post("/cach-quet")
async def doi_cach_quet(request: Request) -> RedirectResponse:
    """Đổi cách quét giữa `keyword` (miễn phí) và `llm` (gọi OpenAI, có phí)."""
    form = await _form(request)
    moi = switch.set_cach_quet(form.get("cach_quet", ""))
    if moi == "llm":
        return _back(ok="Đã chuyển sang LLM — mỗi hội thoại mới tốn 1 lượt gọi OpenAI.")
    return _back(ok="Đã chuyển sang quét bằng từ khoá — miễn phí, chạy tại máy.")


def _zp_sentiment():
    """Module sentiment của ZPancake — nơi giữ `keywords.json` dùng chung."""
    from app.workers.sentiment import zp_sentiment

    return zp_sentiment


_NHAC_QUET_LAI = (
    " Từ khoá có hiệu lực ngay với tin mới; muốn áp cho hội thoại đã quét thì bấm"
    " \"Quét lại theo từ khoá mới\"."
)


@router.post("/tu-khoa/them")
async def them_tu_khoa(request: Request) -> RedirectResponse:
    """Thêm 1 từ khoá vào `keywords.json` (tự bỏ qua nếu đã có)."""
    kw = (await _form(request)).get("tu_khoa", "").strip()
    if not kw:
        return _back(error="Chưa nhập từ khoá.")
    zp = _zp_sentiment()
    truoc = zp.get_keywords()
    if kw.lower() in [k.lower() for k in truoc]:
        return _back(error=f'Từ khoá "{kw}" đã có trong danh sách.')
    zp.add_keyword(kw)
    return _back(ok=f'Đã thêm "{kw.lower()}".{_NHAC_QUET_LAI}')


@router.post("/tu-khoa/xoa")
async def xoa_tu_khoa(request: Request) -> RedirectResponse:
    """Xoá 1 từ khoá khỏi `keywords.json`."""
    kw = (await _form(request)).get("tu_khoa", "").strip()
    zp = _zp_sentiment()
    if kw not in zp.get_keywords():
        return _back(error=f'Không thấy từ khoá "{kw}" trong danh sách.')
    zp.remove_keyword(kw)
    return _back(ok=f'Đã xoá "{kw}". Hội thoại đã đánh dấu tiêu cực trước đó giữ nguyên.')


@router.post("/tu-khoa/luu")
async def luu_tu_khoa(request: Request) -> RedirectResponse:
    """Thay TOÀN BỘ danh sách bằng nội dung ô sửa hàng loạt (mỗi dòng 1 từ)."""
    raw = (await _form(request)).get("danh_sach", "")
    # Bỏ dòng trống + trùng, hạ chữ thường cho khớp cách `add_keyword` vẫn làm.
    ds: list[str] = []
    for dong in raw.splitlines():
        kw = dong.strip().lower()
        if kw and kw not in ds:
            ds.append(kw)
    if not ds:
        return _back(error="Danh sách trống — cần ít nhất 1 từ khoá "
                           "(để trống thì cách quét `keyword` sẽ không bắt được gì).")
    _zp_sentiment().set_keywords(ds)
    return _back(ok=f"Đã lưu {len(ds)} từ khoá.{_NHAC_QUET_LAI}")


@router.post("/thu-telegram")
async def thu_telegram() -> RedirectResponse:
    """Gửi 1 tin THỬ tới Telegram để kiểm tra token/chat id + định dạng tin.

    Dựng tin bằng chính `send_negative_alert` của ZPancake (cùng bố cục, cùng
    escape MarkdownV2) nhưng KHÔNG gọi thẳng hàm đó: nó cố tình nuốt mọi lỗi để
    worker không chết — trong khi nút bấm thì phải nói rõ sai ở đâu.
    """
    import os

    import httpx

    from app.workers.sentiment import zp_telegram

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return _back(error="Chưa cấu hình TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID "
                           "trong .env gốc (khởi động lại app sau khi điền).")

    esc = zp_telegram._escape_markdown          # noqa: SLF001 — dùng lại đúng bộ escape
    text = "\n".join([
        "⚠️ *Phát hiện khách hàng có cảm xúc tiêu cực*",
        f"*Khách:* {esc('Tin THỬ từ trang Cảm xúc')}",
        f"*Nền tảng:* {esc('pancake')}",
        f"*Nội dung:* {esc('Đây là tin nhắn thử — đường dây Telegram hoạt động bình thường.')}",
        f"*Raw ID:* {esc('THU-NGHIEM:0')}",
    ])
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{zp_telegram.TELEGRAM_API_BASE}/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"},
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as err:
        # Telegram trả JSON kèm lý do rất rõ (sai token, chat_id lạ, bot bị chặn...).
        return _back(error=f"Telegram từ chối: {err.response.text[:200]}")
    except Exception as err:  # noqa: BLE001 — mất mạng, timeout...
        return _back(error=f"Không gửi được: {type(err).__name__}: {err}")
    return _back(ok=f"Đã gửi tin thử tới chat {chat_id} — kiểm tra Telegram.")


@router.post("/quet-lai")
async def quet_lai() -> RedirectResponse:
    """Đặt lại dấu đã quét (trừ hội thoại đã tiêu cực) để quét lại theo từ khoá mới."""
    try:
        so = await asyncio.to_thread(inbox_store.reset_sentiment, True)
    except Exception as exc:  # noqa: BLE001
        return _back(error=f"Không đặt lại được: {exc}")
    if not so:
        return _back(ok="Không có hội thoại nào cần quét lại.")
    return _back(ok=f"Đã xếp {so} hội thoại vào hàng đợi quét lại.")
