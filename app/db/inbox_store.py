"""Kho hội thoại đã poll từ Pancake — bảng `watcher.hoi_thoai`.

VÌ SAO CẦN KHO NÀY: trước đây màn Tin nhắn gọi thẳng Pancake mỗi lần render và
chỉ giữ **20 hội thoại mới nhất toàn cục**. Với 22 page đang BẬT, page ít khách
bị page đông khách đẩy văng khỏi danh sách, và hội thoại nào rơi ra khỏi top-20
giữa 2 lần gọi thì **mất luôn**, không ai biết. Lưu lại vào Postgres giải quyết
cả hai:

  * Mỗi lượt poll chỉ *bổ sung/cập nhật*, không xoá — hội thoại cũ vẫn nằm đó,
    nên không bỏ sót tin của khách.
  * Đọc danh sách từ DB thì hiện được **mọi page**, sắp theo thời gian thật, và
    không tốn lời gọi Pancake nào lúc render.

Khoá chính `(page_id, conv_id)` — 1 hội thoại 1 dòng, giống cách Pancake định
danh. KHÔNG dùng chung `raw_id` với `watcher.customers` (bảng của extension
ZPancake) để hai luồng ghi không giẫm chân nhau; cùng schema `watcher` nên vẫn
JOIN/xem chung thoải mái.

Cột `updated_at` giữ NGUYÊN chuỗi Pancake trả về ("2026-07-30T10:54:08.907000",
không kèm múi giờ) để so sánh/sắp xếp đúng như dữ liệu gốc. Việc "đã quét cảm
xúc cho bản nào rồi" theo dõi bằng `sentiment_updated_at` và so **bằng nhau**
(chứ không so lớn/bé) — khỏi phụ thuộc định dạng thời gian của hai nguồn.
"""

import json

from app.db.client import get_pg_pool

SCHEMA = "watcher"
TABLE = f"{SCHEMA}.hoi_thoai"

# Cột trả về cho giao diện (khớp shape của `_normalize_conv` trong pancake/client
# + phần cảm xúc), để webview dùng lại y nguyên không phải sửa.
# CỐ Ý không có `raw` ở đây: cột đó ~5 KB/dòng, chỉ đọc khi thật sự cần moi
# trường hiếm — để trong danh sách này thì mỗi lần liệt kê 100–500 hội thoại là
# kéo thêm vài MB vô ích.
_COLS = """
    page_id, page_name, conv_id, customer_id, name, fb_id, snippet,
    updated_at, message_count, unread_count, seen, tags,
    avatar_url, phones, has_phone, last_customer_at, is_pinned,
    sentiment, sentiment_method, sentiment_checked_at
"""

_ready = False


def _conn():
    """Mượn connection từ pool dùng chung, tạo bảng ở lần dùng đầu của tiến trình."""
    global _ready
    pool = get_pg_pool()
    if not _ready:
        with pool.connection() as conn:
            conn.execute(f"create schema if not exists {SCHEMA}")
            conn.execute(
                f"""
                create table if not exists {TABLE} (
                    page_id              text not null,
                    conv_id              text not null,
                    page_name            text,
                    customer_id          text,
                    name                 text,
                    fb_id                text,
                    snippet              text,
                    updated_at           text not null,
                    message_count        int,
                    unread_count         int,
                    seen                 boolean,
                    tags                 jsonb       not null default '[]'::jsonb,
                    first_seen_at        timestamptz not null default now(),
                    last_seen_at         timestamptz not null default now(),
                    sentiment            text,   -- negative | neutral | positive | NULL
                    sentiment_method     text,   -- keyword | llm
                    sentiment_updated_at text,   -- updated_at TẠI LÚC quét gần nhất
                    sentiment_checked_at timestamptz,
                    primary key (page_id, conv_id)
                )
                """
            )
            # Cột bổ sung: thêm bằng ALTER vì bảng đã tồn tại từ trước (CREATE
            # TABLE IF NOT EXISTS ở trên KHÔNG đụng tới bảng đã có).
            # `raw` giữ NGUYÊN object 32 trường Pancake trả về (~5 KB/dòng, được
            # Postgres nén + đẩy ra TOAST) — bảo hiểm để không mất dữ liệu mà
            # bản rút gọn bỏ qua; KHÔNG nằm trong `_COLS` nên các câu liệt kê
            # không đọc tới, không làm chậm giao diện.
            conn.execute(
                f"""
                alter table {TABLE}
                    add column if not exists avatar_url        text,
                    add column if not exists loai              text,
                    add column if not exists inserted_at       text,
                    add column if not exists last_customer_at  text,
                    add column if not exists last_sent_by_id   text,
                    add column if not exists last_sent_by_name text,
                    add column if not exists phones            jsonb not null default '[]'::jsonb,
                    add column if not exists has_phone         boolean,
                    add column if not exists assignee_ids      jsonb not null default '[]'::jsonb,
                    add column if not exists is_pinned         boolean,
                    add column if not exists raw               jsonb
                """
            )
            conn.execute(
                f"create index if not exists idx_hoi_thoai_moi"
                f" on {TABLE} (updated_at desc)"
            )
            # Lọc nhanh "hội thoại đã có số điện thoại" — việc hay dùng nhất với
            # dữ liệu bán hàng.
            conn.execute(
                f"create index if not exists idx_hoi_thoai_co_sdt on {TABLE}"
                f" (updated_at desc) where has_phone"
            )
            # Hàng đợi quét cảm xúc: chỉ những dòng chưa quét bản mới nhất.
            conn.execute(
                f"create index if not exists idx_hoi_thoai_can_quet on {TABLE}"
                f" (updated_at desc) where sentiment_updated_at is distinct from updated_at"
            )
        _ready = True
    return pool.connection()


def upsert_conversations(page_id: str, page_name: str, convs: list[dict]) -> list[dict]:
    """Ghi/cập nhật 1 mẻ hội thoại của 1 page. Trả về các hội thoại LẦN ĐẦU thấy.

    Trả về nguyên dict (không phải con số) để poller in được tên khách + snippet
    của tin mới ra log, thay vì chỉ "1 mới" chẳng biết là ai.

    Dòng đã có: cập nhật nội dung mới, giữ nguyên `first_seen_at` và **giữ
    nguyên phần cảm xúc** — worker quét sẽ tự nhận ra `updated_at` đã khác
    `sentiment_updated_at` và quét lại bản mới.
    """
    if not convs:
        return []
    rows = [
        (
            str(page_id), str(c.get("conv_id") or ""), page_name,
            c.get("customer_id") or "", c.get("name") or "", c.get("fb_id") or "",
            c.get("snippet") or "", c.get("updated_at") or "",
            int(c.get("message_count") or 0), int(c.get("unread_count") or 0),
            bool(c.get("seen")), json.dumps(c.get("tags") or []),
            c.get("avatar_url") or "", c.get("loai") or "",
            c.get("inserted_at") or "", c.get("last_customer_at") or "",
            c.get("last_sent_by_id") or "", c.get("last_sent_by_name") or "",
            json.dumps(c.get("phones") or []), bool(c.get("has_phone")),
            json.dumps(c.get("assignee_ids") or []), bool(c.get("is_pinned")),
            json.dumps(c.get("raw") or {}, ensure_ascii=False),
        )
        for c in convs
        if c.get("conv_id") and c.get("updated_at")
    ]
    if not rows:
        return []

    ids = [r[1] for r in rows]
    with _conn() as conn, conn.cursor() as cur:
        # Hỏi "đã có những conv_id nào" TRƯỚC khi ghi: sau upsert thì không phân
        # biệt được dòng nào vừa insert, dòng nào chỉ update.
        cur.execute(
            f"select conv_id from {TABLE} where page_id = %s and conv_id = any(%s)",
            (str(page_id), ids),
        )
        da_co = {r["conv_id"] for r in cur.fetchall()}

        cur.executemany(
            f"""
            insert into {TABLE}
                (page_id, conv_id, page_name, customer_id, name, fb_id, snippet,
                 updated_at, message_count, unread_count, seen, tags,
                 avatar_url, loai, inserted_at, last_customer_at,
                 last_sent_by_id, last_sent_by_name, phones, has_phone,
                 assignee_ids, is_pinned, raw)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                    %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s::jsonb)
            on conflict (page_id, conv_id) do update set
                page_name         = excluded.page_name,
                customer_id       = excluded.customer_id,
                name              = excluded.name,
                fb_id             = excluded.fb_id,
                snippet           = excluded.snippet,
                updated_at        = excluded.updated_at,
                message_count     = excluded.message_count,
                unread_count      = excluded.unread_count,
                seen              = excluded.seen,
                tags              = excluded.tags,
                avatar_url        = excluded.avatar_url,
                loai              = excluded.loai,
                inserted_at       = excluded.inserted_at,
                last_customer_at  = excluded.last_customer_at,
                last_sent_by_id   = excluded.last_sent_by_id,
                last_sent_by_name = excluded.last_sent_by_name,
                phones            = excluded.phones,
                has_phone         = excluded.has_phone,
                assignee_ids      = excluded.assignee_ids,
                is_pinned         = excluded.is_pinned,
                raw               = excluded.raw,
                last_seen_at      = now()
            where {TABLE}.updated_at is distinct from excluded.updated_at
               or {TABLE}.snippet    is distinct from excluded.snippet
               -- Dòng cũ (lưu trước khi có cột `raw`) được lấp đầy ngay lần
               -- poller gặp lại nó, khỏi phải chạy lệnh backfill riêng.
               or {TABLE}.raw is null
            """,
            rows,
        )
    return [c for c in convs if str(c.get("conv_id") or "") not in da_co and c.get("conv_id")]


def list_recent(
    limit: int = 100, page_id: str | None = None, only_negative: bool = False
) -> list[dict]:
    """Hội thoại mới nhất trong kho (mọi page, hoặc 1 page), mới -> cũ."""
    where, params = [], []
    if page_id:
        where.append("page_id = %s")
        params.append(str(page_id))
    if only_negative:
        where.append("sentiment = 'negative'")
    clause = f"where {' and '.join(where)}" if where else ""
    params.append(limit)
    with _conn() as conn:
        return conn.execute(
            f"select {_COLS} from {TABLE} {clause} order by updated_at desc limit %s",
            tuple(params),
        ).fetchall()


def max_updated_at_by_page() -> dict[str, str]:
    """`updated_at` mới nhất đang có trong kho, theo từng page.

    Poller nạp bảng này lúc khởi động để biết "đã thấy tới đâu" mà không phải hỏi
    Pancake một mẻ lớn. Không có nó thì mỗi lần restart (chạy `--reload` là restart
    liên tục) worker lại phải leo thang limit 5→20→50 cho cả 22 page.
    """
    with _conn() as conn:
        rows = conn.execute(
            f"select page_id, max(updated_at) as moc from {TABLE} group by page_id"
        ).fetchall()
    return {r["page_id"]: r["moc"] or "" for r in rows}


def take_unscanned(limit: int = 10) -> list[dict]:
    """Các hội thoại cần quét cảm xúc: chưa quét, hoặc đã có tin mới hơn bản đã quét."""
    with _conn() as conn:
        return conn.execute(
            f"""
            select page_id, page_name, conv_id, customer_id, name, snippet, updated_at
            from {TABLE}
            where coalesce(snippet, '') <> ''
              and sentiment_updated_at is distinct from updated_at
            order by updated_at desc
            limit %s
            """,
            (limit,),
        ).fetchall()


def list_scanned_recent(limit: int = 20) -> list[dict]:
    """Các hội thoại vừa được quét cảm xúc gần đây nhất (mọi kết quả).

    Dùng cho khung "nhật ký quét" ở trang /cam-xuc — nhìn là biết worker có đang
    chạy hay không, chứ không phải đoán qua con số.
    """
    with _conn() as conn:
        return conn.execute(
            f"""
            select page_name, name, snippet, sentiment, sentiment_method,
                   sentiment_checked_at, page_id, conv_id, customer_id
            from {TABLE}
            where sentiment_checked_at is not null
            order by sentiment_checked_at desc
            limit %s
            """,
            (limit,),
        ).fetchall()


def reset_sentiment(chi_khong_tieu_cuc: bool = True) -> int:
    """Xoá dấu đã quét để worker quét LẠI. Trả về số dòng bị đặt lại.

    Dùng sau khi sửa danh sách từ khoá: hội thoại đã quét "neutral" TRƯỚC lúc
    thêm từ khoá mới sẽ không bao giờ được quét lại (vì `sentiment_updated_at`
    vẫn khớp `updated_at`), nên phải chủ động đặt lại.

    `chi_khong_tieu_cuc=True` giữ nguyên các dòng đã 'negative' — đã báo Telegram
    rồi, quét lại chỉ tốn công (với cách quét llm còn tốn tiền).
    """
    dieu_kien = (
        "where sentiment_updated_at is not null"
        + (" and (sentiment is null or sentiment <> 'negative')" if chi_khong_tieu_cuc else "")
    )
    with _conn() as conn:
        cur = conn.execute(
            f"""
            update {TABLE}
            set sentiment = null, sentiment_method = null,
                sentiment_updated_at = null, sentiment_checked_at = null
            {dieu_kien}
            """
        )
        return cur.rowcount


def save_sentiment(
    page_id: str, conv_id: str, sentiment: str, method: str, updated_at: str
) -> None:
    """Ghi kết quả quét. `updated_at` = bản vừa quét, để lần sau biết đã quét tới đâu."""
    with _conn() as conn:
        conn.execute(
            f"""
            update {TABLE}
            set sentiment = %s, sentiment_method = %s,
                sentiment_updated_at = %s, sentiment_checked_at = now()
            where page_id = %s and conv_id = %s
            """,
            (sentiment, method, updated_at, str(page_id), str(conv_id)),
        )


def stats_raw() -> dict:
    """Đếm dòng đã có `raw` — cho script lấp dữ liệu cũ biết còn thiếu bao nhiêu."""
    with _conn() as conn:
        row = conn.execute(
            f"select count(*) as tong, count(raw) as co_raw,"
            f" count(*) filter (where has_phone) as co_sdt from {TABLE}"
        ).fetchone()
    return dict(row or {"tong": 0, "co_raw": 0, "co_sdt": 0})


def stats() -> dict:
    """Số liệu cho Bảng điều khiển: tổng hội thoại, đã quét, tiêu cực, còn chờ."""
    with _conn() as conn:
        row = conn.execute(
            f"""
            select
                count(*)                                          as tong,
                count(*) filter (where sentiment is not null)      as da_quet,
                count(*) filter (where sentiment = 'negative')     as tieu_cuc,
                count(*) filter (where coalesce(snippet,'') <> ''
                    and sentiment_updated_at is distinct from updated_at) as cho_quet,
                max(last_seen_at)                                  as lan_cuoi
            from {TABLE}
            """
        ).fetchone()
    return dict(row or {})
