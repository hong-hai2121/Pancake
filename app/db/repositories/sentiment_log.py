"""Nhật ký phát hiện tiêu cực — bảng `watcher.canh_bao_tieu_cuc`.

VÌ SAO CẦN BẢNG RIÊNG: cột `sentiment` trong `watcher.hoi_thoai` là **trạng thái
HIỆN TẠI** của hội thoại, không phải lịch sử. Mỗi hội thoại chỉ có đúng một ô đó,
mà worker lại quét lại mỗi khi có tin mới (`sentiment_updated_at <> updated_at`)
rồi UPDATE đè lên. Nên hội thoại hôm nay bị gắn `negative`, mai khách nhắn "dạ
vâng ạ" là ô đó thành `neutral` — **mất sạch dấu vết từng tiêu cực**, dù không ai
xoá dòng nào cả.

Bảng này giải quyết đúng chỗ đó: mỗi lần worker phát hiện tiêu cực thì ghi thêm
MỘT dòng, và dòng đó không bao giờ bị sửa hay xoá. Nhờ vậy:

  * Hội thoại đã "nguội" vẫn tra được là từng tiêu cực lúc nào, vì chuyện gì.
  * Một hội thoại tiêu cực nhiều lần thì có nhiều dòng — đếm được số lần.
  * `snippet` được CHỤP LẠI tại thời điểm phát hiện, không trỏ sang kho: kho bị
    tin mới ghi đè `snippet` liên tục, đọc lại sau vài ngày sẽ ra nội dung khác
    hẳn với cái đã làm bung cảnh báo.

Khoá duy nhất `(page_id, conv_id, updated_at)` — `updated_at` đổi theo từng tin
nhắn nên mỗi tin tiêu cực chỉ vào sổ đúng một lần, dù worker có quét lại bao
nhiêu lượt (bấm "Quét lại theo từ khoá mới" là một trường hợp như vậy).
"""

import json

from app.db.client import get_pg_pool

SCHEMA = "watcher"
TABLE = f"{SCHEMA}.canh_bao_tieu_cuc"

_COLS = """
    id, page_id, page_name, conv_id, customer_id, name, snippet,
    updated_at, cach_quet, tu_khoa_khop, phat_hien_luc
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
                    id            bigint generated always as identity primary key,
                    page_id       text        not null,
                    conv_id       text        not null,
                    page_name     text,
                    customer_id   text,
                    name          text,
                    -- Nội dung ĐÚNG LÚC bung cảnh báo, giữ nguyên vĩnh viễn.
                    snippet       text,
                    -- Mốc tin nhắn lúc đó (chuỗi Pancake trả về, giữ nguyên dạng).
                    updated_at    text        not null,
                    cach_quet     text,       -- keyword | llm
                    phat_hien_luc timestamptz not null default now(),
                    unique (page_id, conv_id, updated_at)
                )
                """
            )
            # Thêm bằng ALTER: bảng có thể đã tồn tại từ trước (CREATE TABLE IF
            # NOT EXISTS ở trên KHÔNG đụng tới bảng đã có). Dòng cũ để '[]' —
            # cố ý KHÔNG dò lại: danh sách từ khoá có thể đã đổi kể từ lúc đó,
            # dò lại dễ hiện ra lý do khác hẳn lý do thật đã bung cảnh báo.
            conn.execute(
                f"alter table {TABLE}"
                f" add column if not exists tu_khoa_khop jsonb not null default '[]'::jsonb"
            )
            conn.execute(
                f"create index if not exists idx_canh_bao_moi"
                f" on {TABLE} (phat_hien_luc desc)"
            )
            # Tra "hội thoại này từng tiêu cực mấy lần" khi mở 1 hội thoại cụ thể.
            conn.execute(
                f"create index if not exists idx_canh_bao_hoi_thoai"
                f" on {TABLE} (page_id, conv_id)"
            )
        _ready = True
    return pool.connection()


def ghi(row: dict, cach_quet: str, tu_khoa_khop: list[str] | None = None) -> bool:
    """Vào sổ 1 lần phát hiện tiêu cực. True = dòng mới, False = đã có sẵn.

    `row` là dòng worker lấy từ `inbox_store.take_unscanned` (đã có sẵn page/khách
    /snippet/updated_at). Trùng khoá thì bỏ qua im lặng — quét lại cùng một tin
    nhắn không được phép sinh thêm dòng.

    `tu_khoa_khop` = các từ khoá đã làm bung cảnh báo, lưu lại để sau này còn
    truy được VÌ SAO câu đó bị bắt (quan trọng nhất khi báo nhầm). Cách quét
    `llm` không có từ khoá nào -> để rỗng.
    """
    with _conn() as conn:
        cur = conn.execute(
            f"""
            insert into {TABLE}
                (page_id, conv_id, page_name, customer_id, name, snippet,
                 updated_at, cach_quet, tu_khoa_khop)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (page_id, conv_id, updated_at) do nothing
            """,
            (
                str(row.get("page_id") or ""), str(row.get("conv_id") or ""),
                row.get("page_name") or "", row.get("customer_id") or "",
                row.get("name") or "", row.get("snippet") or "",
                row.get("updated_at") or "", cach_quet or "",
                json.dumps(tu_khoa_khop or [], ensure_ascii=False),
            ),
        )
        return cur.rowcount > 0


def liet_ke(limit: int = 50) -> list[dict]:
    """Các lần phát hiện gần đây nhất, mới -> cũ."""
    with _conn() as conn:
        return conn.execute(
            f"select {_COLS} from {TABLE} order by phat_hien_luc desc limit %s",
            (limit,),
        ).fetchall()


def so_lieu() -> dict:
    """Đếm cho trang Cảm xúc: tổng số lần, số hội thoại riêng biệt, lần gần nhất."""
    with _conn() as conn:
        row = conn.execute(
            f"""
            select count(*)                                  as tong,
                   count(distinct (page_id, conv_id))        as so_hoi_thoai,
                   max(phat_hien_luc)                        as gan_nhat
            from {TABLE}
            """
        ).fetchone()
    return row or {"tong": 0, "so_hoi_thoai": 0, "gan_nhat": None}
