"""Lưu trữ Postgres (schema `watcher`) cho Pancake Watcher local server.

Trước đây là 1 file SQLite riêng; nay dùng CHUNG Postgres trong Docker với dự án
gốc (`docker-compose.yml` ở thư mục gốc repo) — cùng database `pancakebot`, khác
**schema**:

    pancakebot (database)
    ├── public.kich_ban / hoi_thoai_mau / trang_thai_khach   <- bot ở app/
    └── watcher.customers                                    <- ZPancake (file này)

Vì sao tách schema chứ không tách database: 1 volume, `pg_dump` 1 lệnh ra cả hai,
Adminer xem chung mà không lẫn tên bảng, và sau này muốn JOIN dữ liệu 2 bên là
làm được ngay. Mọi câu SQL ở đây ghi rõ `watcher.customers` (không dựa vào
`search_path`) vì pool dùng chung với app/ — app/ vẫn phải thấy `public`.

1 bảng duy nhất `customers`: mỗi khách hàng (hội thoại, khoá `raw_id`) 1 dòng,
chứa đúng tin nhắn cuối cùng gửi đến mà extension quét được — không giữ log lịch
sử từng lần phát hiện. Có thêm 3 cột sentiment (xem `sentiment.py` + worker nền
trong `main.py`) — điền BẤT ĐỒNG BỘ sau khi lưu, không chặn `POST /api/messages`.

Các cột thời gian cố ý giữ kiểu **text ISO-8601 UTC** y như bản SQLite (không đổi
sang `timestamptz`): toàn bộ logic so sánh `sentiment_checked_at < detected_at`,
dữ liệu extension gửi lên và JSON trả về giữ nguyên hành vi cũ, không phải sửa
một dòng nào ở `main.py` / `gui.py` / extension.

Chỉ dùng dữ liệu extension tự quét được từ DOM pancake.vn — không gọi API Pancake
nào, không cần access token.
"""

import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# --- nối vào dự án gốc để dùng CHUNG connection pool -------------------------
# ZPancake chạy với thư mục làm việc là chính `ZPancake/server` (shortcut GUI,
# `python main.py`), nên phải tự thêm gốc repo vào sys.path mới import được app/.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Nạp .env GỐC trước (lấy DATABASE_URL), rồi .env riêng của ZPancake đè lên —
# phải xong TRƯỚC khi import app.config (settings được dựng ngay lúc import).
load_dotenv(_ROOT / ".env")
load_dotenv(Path(__file__).parent / ".env", override=True)

from app.db.client import get_pg_pool  # noqa: E402 — buộc phải sau load_dotenv

SCHEMA = "watcher"
TABLE = f"{SCHEMA}.customers"

# Cột trả về cho webview lịch sử / API (giữ đúng thứ tự cũ).
_ALL_COLS = """
    raw_id, platform, kind, page_id, conv_id, name,
    snippet, time_text, unread_count, reason, detected_at,
    first_seen_at, last_seen_at,
    sentiment, sentiment_method, sentiment_checked_at
"""


@contextmanager
def get_conn():
    """Mượn 1 connection từ pool dùng chung với app/ (autocommit, dict_row).

    Không tự mở/đóng kết nối như bản SQLite: pool giữ sẵn connection nên mỗi
    truy vấn không phải bắt tay TCP lại từ đầu, và an toàn khi FastAPI chạy
    handler trong nhiều thread.
    """
    with get_pg_pool().connection() as conn:
        yield conn


def init_db() -> None:
    """Tạo schema + bảng nếu chưa có. Chạy lại nhiều lần vô hại.

    Gọi ở `main.on_startup` và ở `gui.KeywordsDialog._save` — nơi nào cũng phải
    bắt lỗi, vì Postgres có thể chưa bật (xem `db_status`).
    """
    with get_conn() as conn:
        conn.execute(f"create schema if not exists {SCHEMA}")
        conn.execute(
            f"""
            create table if not exists {TABLE} (
                raw_id               text primary key,
                platform             text,
                kind                 text,
                page_id              text,
                conv_id              text,
                name                 text,
                snippet              text,
                time_text            text,
                unread_count         integer,
                reason               text,
                detected_at          text,
                first_seen_at        text not null,
                last_seen_at         text not null,
                sentiment            text,   -- negative | neutral | positive | NULL (chưa quét)
                sentiment_method     text,   -- keyword | llm
                sentiment_checked_at text
            )
            """
        )
        # Phục vụ ORDER BY detected_at ở /history, get_unanalyzed và cleanup.
        conn.execute(
            f"create index if not exists idx_watcher_customers_detected"
            f" on {TABLE} (detected_at desc)"
        )


def db_status(timeout: float = 0.5) -> tuple[bool, str]:
    """(còn sống?, mô tả lỗi) — cho `/health` và đèn trạng thái trên GUI.

    `timeout` NGẮN có chủ đích: GUI poll `/health` mỗi 2 giây với timeout 0.6s,
    nên phép thử phải trả lời trong vòng dưới 1s. Dùng thẳng timeout mặc định của
    pool (10s) thì lúc Postgres tắt, `/health` treo lâu hơn cả GUI chịu chờ —
    GUI sẽ tưởng SERVER chết (đèn đỏ) thay vì báo đúng "server sống, DB chưa lên"
    (đèn vàng).
    """
    try:
        with get_pg_pool().connection(timeout=timeout) as conn:
            conn.execute("select 1")
        return True, ""
    except Exception as err:  # noqa: BLE001 — mọi lỗi đều quy về "DB không sẵn sàng"
        return False, str(err)


def save_event(ev: dict) -> None:
    """Upsert 1 khách hàng: ghi đè tin nhắn cuối cùng gửi đến bằng dữ liệu mới nhất.

    Dùng `INSERT ... ON CONFLICT DO UPDATE` (upsert nguyên tử trong 1 câu lệnh)
    thay vì "SELECT xem đã có chưa rồi mới UPDATE/INSERT" — kiểu cũ có khoảng hở
    giữa bước đọc và bước ghi, 2 request tới gần như đồng thời cho CÙNG 1 raw_id
    có thể cùng thấy "chưa có" rồi cùng INSERT, gây lỗi khoá trùng và mất 1 trong
    2 lượt ghi. Upsert 1 câu lệnh loại bỏ hẳn khoảng hở đó.
    """
    raw_id = ev.get("rawId")
    if not raw_id:
        return

    detected_at = ev.get("detectedAt")
    with get_conn() as conn:
        conn.execute(
            f"""
            INSERT INTO {TABLE}
                (raw_id, platform, kind, page_id, conv_id, name,
                 snippet, time_text, unread_count, reason, detected_at,
                 first_seen_at, last_seen_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (raw_id) DO UPDATE SET
                platform = excluded.platform,
                kind = excluded.kind,
                page_id = excluded.page_id,
                conv_id = excluded.conv_id,
                name = excluded.name,
                snippet = excluded.snippet,
                time_text = excluded.time_text,
                unread_count = excluded.unread_count,
                reason = excluded.reason,
                detected_at = excluded.detected_at,
                last_seen_at = excluded.last_seen_at
            """,
            (
                raw_id,
                ev.get("platform"),
                ev.get("kind"),
                ev.get("pageId"),
                ev.get("convId"),
                ev.get("name"),
                ev.get("snippet"),
                ev.get("time"),
                ev.get("unreadCount"),
                ev.get("reason"),
                detected_at,
                detected_at,  # first_seen_at: chỉ dùng nếu là INSERT mới, giữ nguyên nếu conflict
                detected_at,  # last_seen_at
            ),
        )
        # Chú ý: upsert ở trên KHÔNG đụng tới sentiment/sentiment_method/
        # sentiment_checked_at — nhờ vậy get_unanalyzed() bên dưới tự nhận ra
        # hội thoại này "có tin mới hơn lần quét cảm xúc gần nhất" (detected_at
        # mới hơn sentiment_checked_at) và sẽ được worker quét lại.


def get_unanalyzed(limit: int = 10) -> list[dict]:
    """Lấy các khách hàng chưa quét cảm xúc, hoặc có tin mới hơn lần quét gần
    nhất — dùng cho worker nền, KHÔNG chặn request lưu tin của extension."""
    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT raw_id, snippet, name, platform, page_id, conv_id
            FROM {TABLE}
            WHERE snippet IS NOT NULL
              AND (sentiment_checked_at IS NULL OR sentiment_checked_at < detected_at)
            ORDER BY detected_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()


def update_sentiment(raw_id: str, sentiment: str, method: str, checked_at: str) -> None:
    with get_conn() as conn:
        conn.execute(
            f"""
            UPDATE {TABLE}
            SET sentiment = %s, sentiment_method = %s, sentiment_checked_at = %s
            WHERE raw_id = %s
            """,
            (sentiment, method, checked_at, raw_id),
        )


def reset_non_negative_sentiment() -> int:
    """Đặt lại sentiment/sentiment_method/sentiment_checked_at về NULL cho mọi
    hội thoại CHƯA từng bị đánh dấu 'negative' — gọi khi danh sách từ khoá tiêu
    cực vừa được sửa (gui.py, KeywordsDialog._save), vì get_unanalyzed() chỉ quét
    lại tin có sentiment_checked_at NULL hoặc cũ hơn detected_at: nếu không reset,
    1 tin đã quét "neutral" TRƯỚC khi từ khoá mới được thêm sẽ không bao giờ được
    quét lại dù giờ đã khớp từ khoá, nên không bao giờ được báo tiêu cực + báo
    Telegram dù thực sự trùng từ khoá.

    Hội thoại đã 'negative' giữ nguyên, không reset — đã báo Telegram rồi, quét
    lại chỉ tổ tốn công (và với method="llm" còn tốn phí gọi lại vô ích)."""
    with get_conn() as conn:
        cur = conn.execute(
            f"""
            UPDATE {TABLE}
            SET sentiment = NULL, sentiment_method = NULL, sentiment_checked_at = NULL
            WHERE sentiment_checked_at IS NOT NULL
              AND (sentiment IS NULL OR sentiment != 'negative')
            """
        )
        return cur.rowcount


def cleanup_scanned(older_than_hours: int = 1, keep_recent: int = 20) -> int:
    """Xoá hội thoại đã quét cảm xúc xong, KHÔNG tiêu cực, và cũ hơn
    `older_than_hours` (theo detected_at) — TRỪ `keep_recent` hội thoại đã quét
    gần nhất, luôn được giữ lại làm "sàn tối thiểu" lịch sử bất kể tuổi (kể cả
    khi 1 trong số đó đã quá 24h vì không có gì mới hơn đẩy nó ra khỏi
    top-`keep_recent`). Hội thoại sentiment='negative' không bao giờ bị hàm này
    xoá — dùng cho worker dọn dẹp định kỳ trong main.py."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=older_than_hours)).isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            f"""
            DELETE FROM {TABLE}
            WHERE raw_id IN (
                SELECT raw_id FROM (
                    SELECT raw_id, detected_at,
                           ROW_NUMBER() OVER (ORDER BY detected_at DESC) AS rn
                    FROM {TABLE}
                    WHERE sentiment_checked_at IS NOT NULL
                      AND (sentiment IS NULL OR sentiment != 'negative')
                ) ranked
                WHERE rn > %s AND detected_at < %s
            )
            """,
            (keep_recent, cutoff),
        )
        return cur.rowcount


SORTABLE_COLUMNS = {
    "name",
    "platform",
    "detected_at",
    "first_seen_at",
    "last_seen_at",
    "sentiment",
    "sentiment_checked_at",
    "unread_count",
}


def get_all_customers(order_by: str = "detected_at", direction: str = "desc") -> list[dict]:
    """Lấy toàn bộ khách hàng cho webview lịch sử (`/history`) — không phân trang
    (dữ liệu chỉ 1 dòng/khách nên số lượng nhỏ). `order_by` được whitelist qua
    SORTABLE_COLUMNS trước khi ghép vào câu SQL (không nhận thẳng từ query string)
    để tránh SQL injection qua tên cột."""
    if order_by not in SORTABLE_COLUMNS:
        order_by = "detected_at"
    direction = "ASC" if direction.lower() == "asc" else "DESC"
    with get_conn() as conn:
        return conn.execute(
            f"SELECT {_ALL_COLS} FROM {TABLE} ORDER BY {order_by} {direction}"
        ).fetchall()


def delete_customer(raw_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(f"DELETE FROM {TABLE} WHERE raw_id = %s", (raw_id,))
        return cur.rowcount > 0


def get_recent_sentiments(limit: int = 200) -> list[dict]:
    """Cho extension poll định kỳ để lấy kết quả sentiment mới nhất, gộp vào danh
    sách đang hiển thị trên popup/panel."""
    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT raw_id, sentiment, sentiment_method, sentiment_checked_at
            FROM {TABLE}
            WHERE sentiment_checked_at IS NOT NULL
            ORDER BY sentiment_checked_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
