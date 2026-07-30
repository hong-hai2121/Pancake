"""Worker nền: quét cảm xúc TIÊU CỰC cho hội thoại mới trong kho.

Dùng LẠI đúng bộ não của ZPancake (`ZPancake/server/sentiment.py` +
`telegram.py`) thay vì viết lại: danh sách từ khoá vẫn là `keywords.json` duy
nhất, sửa bằng GUI "Quản lý từ khoá tiêu cực" là cả hai bên cùng ăn theo, và
tin báo Telegram giữ nguyên định dạng.

Chạy TÁCH HẲN khỏi vòng poll và khỏi request của trình duyệt:

  * Không làm chậm màn Tin nhắn — trang chỉ đọc kho, không chờ quét.
  * Không phụ thuộc việc có ai mở trang hay không: server còn chạy là còn quét.
  * 1 hội thoại lỗi (LLM timeout, Telegram lỗi) chỉ bỏ qua hội thoại đó.

Hội thoại nào được quét: `sentiment_updated_at <> updated_at` — tức chưa quét
lần nào, hoặc khách đã nhắn thêm kể từ lần quét trước (xem `take_unscanned`).
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from app.config import settings
from app.db import inbox_store
from app.workers import switch

# --- mượn sentiment/telegram của ZPancake ------------------------------------
# Hai module đó đọc cấu hình lúc import (SENTIMENT_METHOD) nên phải nạp .env của
# ZPancake TRƯỚC. `override=False` để .env gốc (đã nạp qua app.config) vẫn thắng
# ở những biến trùng tên, ví dụ OPENAI_API_KEY.
_ROOT = Path(__file__).resolve().parents[2]
_ZP = _ROOT / "ZPancake" / "server"
if str(_ZP) not in sys.path:
    sys.path.insert(0, str(_ZP))
# Nạp CẢ HAI .env vào os.environ: `telegram.py` và `sentiment.py` của ZPancake đọc
# cấu hình bằng `os.getenv`, mà pydantic-settings (app/config.py) chỉ đọc file
# chứ KHÔNG xuất biến ra môi trường. Không nạp .env gốc thì ai điền
# TELEGRAM_BOT_TOKEN vào đó sẽ thấy thông báo im lặng không chạy mà chẳng có lỗi.
# .env riêng của ZPancake nạp sau + override để nó vẫn là nơi ưu tiên.
load_dotenv(_ROOT / ".env")
load_dotenv(_ZP / ".env", override=True)

import sentiment as zp_sentiment  # noqa: E402 — buộc phải sau load_dotenv
import telegram as zp_telegram    # noqa: E402

# Thống kê + chi tiết vòng gần nhất — xem qua `GET /poller`.
_KEEP_DETAIL = 50
last_run: dict = {
    "luc": "", "quet": 0, "tieu_cuc": 0, "loi": 0,
    "tieu_cuc_chi_tiet": [], "loi_chi_tiet": [],
}


def _log(msg: str) -> None:
    """In kèm flush — không flush thì log bị đệm khi chạy nền/ghi ra file."""
    print(msg, flush=True)


async def scan_once(limit: int) -> dict:
    """Quét tối đa `limit` hội thoại đang chờ. Trả về thống kê của lượt đó."""
    rows = await asyncio.to_thread(inbox_store.take_unscanned, limit)
    quet = 0
    tieu_cuc_ct: list[dict] = []
    loi_ct: list[dict] = []

    for row in rows:
        try:
            ket_qua, cach = await zp_sentiment.analyze(row["snippet"])
            await asyncio.to_thread(
                inbox_store.save_sentiment,
                row["page_id"], row["conv_id"], ket_qua, cach, row["updated_at"],
            )
            quet += 1
            if ket_qua == "negative":
                tieu_cuc_ct.append({
                    "page": row.get("page_name") or row["page_id"],
                    "khach": row.get("name") or "",
                    "snippet": (row.get("snippet") or "")[:120],
                    "cach_quet": cach,
                    "conv_id": row["conv_id"],
                })
                _log(
                    f"[sentiment] ⚠ TIÊU CỰC · {row.get('page_name') or row['page_id']}"
                    f" · {row.get('name')}: {(row['snippet'] or '')[:80]}"
                )
                # Best-effort: thiếu cấu hình Telegram thì hàm tự bỏ qua, lỗi
                # mạng cũng không được phép chặn việc quét các hội thoại sau.
                try:
                    await zp_telegram.send_negative_alert(
                        name=row.get("name"),
                        snippet=row.get("snippet"),
                        platform="pancake",
                        raw_id=f"{row['page_id']}:{row['conv_id']}",
                        page_id=row["page_id"],
                        conv_id=row["conv_id"],
                    )
                except Exception as err:  # noqa: BLE001
                    _log(f"[sentiment] Telegram lỗi: {err}")
        except Exception as err:  # noqa: BLE001 — 1 hội thoại lỗi không chặn cả mẻ
            loi_ct.append({
                "page": row.get("page_name") or row.get("page_id"),
                "conv_id": row.get("conv_id"),
                "loi": f"{type(err).__name__}: {err}",
            })
            _log(f"[sentiment]   ✗ LỖI quét {row.get('conv_id')}: {err}")

    if quet or loi_ct:
        last_run.update(
            luc=datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S %d/%m/%Y"),
            quet=quet, tieu_cuc=len(tieu_cuc_ct), loi=len(loi_ct),
            tieu_cuc_chi_tiet=(tieu_cuc_ct + last_run["tieu_cuc_chi_tiet"])[:_KEEP_DETAIL],
            loi_chi_tiet=loi_ct[:_KEEP_DETAIL],
        )
    return {"quet": quet, "tieu_cuc": len(tieu_cuc_ct), "loi": len(loi_ct)}


async def sentiment_loop() -> None:
    """Vòng lặp vô hạn: cứ `sentiment_interval` giây lại quét 1 mẻ.

    Công tắc BẬT/TẮT và cách quét được đọc lại MỖI vòng (`app/workers/switch.py`)
    nên bấm nút ở trang /cam-xuc là có tác dụng ngay, không phải restart server.
    TẮT thì vòng lặp vẫn sống nhưng không quét gì — bật lại là chạy tiếp.
    """
    _log(
        f"[sentiment] Worker sẵn sàng — {'ĐANG QUÉT' if switch.is_on() else 'ĐANG TẮT'},"
        f" cách quét = {switch.cach_quet()}"
    )
    dang_bat = switch.is_on()
    while True:
        try:
            if switch.is_on() != dang_bat:      # đổi trạng thái -> ghi 1 dòng log
                dang_bat = switch.is_on()
                _log(f"[sentiment] {'BẬT lại' if dang_bat else 'TẮT'} theo công tắc giao diện")
            if not switch.is_on():
                await asyncio.sleep(settings.sentiment_interval)
                continue
            # `analyze()` của ZPancake đọc biến module này để chọn keyword/llm.
            zp_sentiment.SENTIMENT_METHOD = switch.cach_quet()
            await scan_once(settings.sentiment_batch)
        except Exception as err:  # noqa: BLE001
            _log(f"[sentiment] Lỗi vòng lặp: {type(err).__name__}: {err}")
        await asyncio.sleep(settings.sentiment_interval)
