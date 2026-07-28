"""Lưu trữ SQLite cho Pancake Watcher local server.

1 bảng duy nhất `customers`: mỗi khách hàng (hội thoại, khoá `raw_id`) 1 dòng,
chứa đúng tin nhắn cuối cùng gửi đến mà extension quét được — không giữ log
lịch sử từng lần phát hiện, không có cột "thời gian lưu" của server (chỉ dùng
`detected_at` do chính extension gửi lên). Có thêm 3 cột sentiment (quét cảm
xúc tiêu cực, xem `sentiment.py` + worker nền trong `main.py`) — được điền
BẤT ĐỒNG BỘ sau khi lưu, không chặn request `POST /api/messages`.

Chỉ dùng dữ liệu extension tự quét được từ DOM pancake.vn (snippet rút gọn +
metadata hội thoại) — không gọi API Pancake nào, không cần access token, và
hoàn toàn không đụng tới dự án app/ ở thư mục gốc repo.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "pancake_watcher.db"


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # timeout=10: nếu DB đang bị khoá bởi 1 lượt ghi khác, chờ tối đa 10s thay
    # vì ném "database is locked" ngay (mặc định sqlite3 chỉ chờ 5s).
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # WAL cho phép đọc/ghi đồng thời tốt hơn journal mode mặc định (rollback
    # journal) — giảm hẳn khả năng "database is locked" khi nhiều request tới
    # gần như cùng lúc (ví dụ lúc bấm "Cập nhật" quét cả danh sách). Set 1 lần
    # là đủ (lưu trong chính file DB), nhưng gọi lại mỗi connect cũng vô hại.
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                raw_id TEXT PRIMARY KEY,
                platform TEXT,
                kind TEXT,
                page_id TEXT,
                conv_id TEXT,
                name TEXT,
                snippet TEXT,
                time_text TEXT,
                unread_count INTEGER,
                reason TEXT,
                detected_at TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
            """
        )
        _migrate_legacy_schema(conn)


def _migrate_legacy_schema(conn: sqlite3.Connection) -> None:
    """Nâng cấp DB tạo từ bản trước (có bảng `messages` log riêng) sang schema
    gọn hơn hiện tại — KHÔNG xoá dữ liệu: với mỗi khách, lấy dòng log mới nhất
    trong `messages` cũ đổ vào `customers`, rồi mới xoá bảng `messages`. Hàm
    này idempotent — bảng `messages` không còn thì bỏ qua ngay.

    Lưu ý: `CREATE TABLE IF NOT EXISTS` ở init_db() KHÔNG tự thêm cột mới vào
    bảng `customers` đã tồn tại sẵn từ bản cũ — phải ALTER TABLE thủ công ở
    đây trước khi ghi dữ liệu vào các cột đó.
    """
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(customers)")}
    for col, decl in (
        ("snippet", "TEXT"),
        ("time_text", "TEXT"),
        ("unread_count", "INTEGER"),
        ("reason", "TEXT"),
        ("detected_at", "TEXT"),
        ("sentiment", "TEXT"),  # "negative" | "neutral" | "positive" | NULL (chưa quét)
        ("sentiment_method", "TEXT"),  # "keyword" | "llm"
        ("sentiment_checked_at", "TEXT"),
    ):
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE customers ADD COLUMN {col} {decl}")

    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "messages" not in tables:
        return

    latest_rows = conn.execute(
        """
        SELECT m.raw_id, m.snippet, m.time_text, m.unread_count, m.reason, m.detected_at
        FROM messages m
        INNER JOIN (
            SELECT raw_id, MAX(id) AS max_id FROM messages GROUP BY raw_id
        ) latest ON latest.raw_id = m.raw_id AND latest.max_id = m.id
        """
    ).fetchall()

    for row in latest_rows:
        conn.execute(
            """
            UPDATE customers
            SET snippet = ?, time_text = ?, unread_count = ?, reason = ?, detected_at = ?
            WHERE raw_id = ?
            """,
            (
                row["snippet"],
                row["time_text"],
                row["unread_count"],
                row["reason"],
                row["detected_at"],
                row["raw_id"],
            ),
        )

    conn.execute("DROP TABLE messages")


def save_event(ev: dict) -> None:
    """Upsert 1 khách hàng: ghi đè tin nhắn cuối cùng gửi đến bằng dữ liệu mới nhất.

    Dùng `INSERT ... ON CONFLICT DO UPDATE` (upsert nguyên tử trong 1 câu lệnh)
    thay vì "SELECT xem đã có chưa rồi mới UPDATE/INSERT" — kiểu cũ có khoảng hở
    giữa bước đọc và bước ghi, 2 request tới gần như đồng thời cho CÙNG 1 raw_id
    có thể cùng thấy "chưa có" rồi cùng INSERT, gây lỗi UNIQUE constraint và mất
    1 trong 2 lượt ghi. Upsert 1 câu lệnh loại bỏ hẳn khoảng hở đó.
    """
    raw_id = ev.get("rawId")
    if not raw_id:
        return

    detected_at = ev.get("detectedAt")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO customers
                (raw_id, platform, kind, page_id, conv_id, name,
                 snippet, time_text, unread_count, reason, detected_at,
                 first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(raw_id) DO UPDATE SET
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


def get_unanalyzed(limit: int = 10) -> list[sqlite3.Row]:
    """Lấy các khách hàng chưa quét cảm xúc, hoặc có tin mới hơn lần quét gần
    nhất — dùng cho worker nền, KHÔNG chặn request lưu tin của extension."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT raw_id, snippet, name, platform
            FROM customers
            WHERE snippet IS NOT NULL
              AND (sentiment_checked_at IS NULL OR sentiment_checked_at < detected_at)
            ORDER BY detected_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def update_sentiment(raw_id: str, sentiment: str, method: str, checked_at: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE customers
            SET sentiment = ?, sentiment_method = ?, sentiment_checked_at = ?
            WHERE raw_id = ?
            """,
            (sentiment, method, checked_at, raw_id),
        )


def cleanup_scanned(older_than_hours: int = 1, keep_recent: int = 20) -> int:
    """Xoá hội thoại đã quét cảm xúc xong, KHÔNG tiêu cực, và cũ hơn
    `older_than_hours` (theo detected_at) — TRỪ `keep_recent` hội thoại đã
    quét gần nhất, luôn được giữ lại làm "sàn tối thiểu" lịch sử bất kể tuổi
    (kể cả khi 1 trong số đó đã quá 24h vì không có gì mới hơn đẩy nó ra khỏi
    top-`keep_recent`). Hội thoại sentiment='negative' không bao giờ bị hàm
    này xoá — dùng cho worker dọn dẹp định kỳ trong main.py."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=older_than_hours)).isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """
            DELETE FROM customers
            WHERE raw_id IN (
                SELECT raw_id FROM (
                    SELECT raw_id, detected_at,
                           ROW_NUMBER() OVER (ORDER BY detected_at DESC) AS rn
                    FROM customers
                    WHERE sentiment_checked_at IS NOT NULL
                      AND (sentiment IS NULL OR sentiment != 'negative')
                ) ranked
                WHERE rn > ? AND detected_at < ?
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


def get_all_customers(order_by: str = "detected_at", direction: str = "desc") -> list[sqlite3.Row]:
    """Lấy toàn bộ khách hàng cho webview lịch sử (`/history`) — không phân
    trang (dữ liệu chỉ 1 dòng/khách nên số lượng nhỏ). `order_by` được whitelist
    qua SORTABLE_COLUMNS trước khi ghép vào câu SQL (không nhận thẳng từ query
    string) để tránh SQL injection qua tên cột."""
    if order_by not in SORTABLE_COLUMNS:
        order_by = "detected_at"
    direction = "ASC" if direction.lower() == "asc" else "DESC"
    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT raw_id, platform, kind, page_id, conv_id, name,
                   snippet, time_text, unread_count, reason, detected_at,
                   first_seen_at, last_seen_at,
                   sentiment, sentiment_method, sentiment_checked_at
            FROM customers
            ORDER BY {order_by} {direction}
            """
        ).fetchall()


def delete_customer(raw_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM customers WHERE raw_id = ?", (raw_id,))
        return cur.rowcount > 0


def get_recent_sentiments(limit: int = 200) -> list[sqlite3.Row]:
    """Cho extension poll định kỳ để lấy kết quả sentiment mới nhất, gộp vào
    danh sách đang hiển thị trên popup/panel."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT raw_id, sentiment, sentiment_method, sentiment_checked_at
            FROM customers
            WHERE sentiment_checked_at IS NOT NULL
            ORDER BY sentiment_checked_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
