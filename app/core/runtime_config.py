"""Cài đặt CHỈNH ĐƯỢC LÚC ĐANG CHẠY — công tắc bật/tắt + nhịp chạy của worker.

Vì sao có file này: `.env` chỉ được đọc MỘT lần lúc khởi động (pydantic-settings
+ `lru_cache`), nên trước đây muốn bật/tắt đồng bộ hay đổi nhịp là phải sửa file
rồi restart server. Ở đây giá trị nằm trong bảng `crm.app_settings`, worker đọc
lại MỖI vòng lặp → bấm nút trên màn Cài đặt là có tác dụng ngay.

Thứ tự ưu tiên:  bảng app_settings  →  .env  →  mặc định trong code.
Bảng chỉ giữ phần NGƯỜI ĐÃ ĐỔI; xoá dòng đi là quay về đúng .env.

Danh mục `MUC` bên dưới là NGUỒN SỰ THẬT về nhãn/kiểu/khoảng hợp lệ — thêm một
cài đặt mới chỉ cần thêm một dòng ở đây, không phải sửa DB lẫn giao diện.

Đọc rẻ: cache toàn bảng trong RAM `_TTL` giây (worker gọi rất dày), ghi thì xoá
cache ngay nên người bấm nút thấy hiệu lực tức thì trong tiến trình của mình;
tiến trình khác chậm nhất `_TTL` giây.
"""

import time
from dataclasses import dataclass, field

from app.core.config import settings

_TTL = 10.0
_cache: dict = {"luc": 0.0, "data": {}}


@dataclass(frozen=True)
class Muc:
    """Một cài đặt: mã .env viết thường, kiểu, nhãn tiếng Việt, khoảng hợp lệ."""

    code: str
    nhom: str
    ten: str
    kieu: str                      # bool | int | float | str
    mo_ta: str = ""
    nho_nhat: float | None = None
    lon_nhat: float | None = None
    don_vi: str = ""
    chon: tuple = field(default_factory=tuple)   # str: danh sách giá trị cho phép
    # Cài đặt đã có cơ chế lưu riêng từ trước (công tắc file JSON) — trỏ vào đó
    # thay vì đẻ ra nguồn sự thật thứ hai.
    dac_biet: str = ""


NHOM = {
    "dong_bo": "Đồng bộ Pancake → CRM",
    "quang_cao": "Quảng cáo & chi phí",
    "bot": "Bot Pancake (poller & cảm xúc)",
}

# Danh mục cài đặt bày ra màn Cài đặt. CỐ Ý không đưa token/mật khẩu/chuỗi kết
# nối vào đây: những thứ đó thuộc .env, không phơi lên web (xem docs A2).
MUC: tuple[Muc, ...] = (
    # --- Đồng bộ Pancake → CRM ---
    Muc("crm_sync_enabled", "dong_bo", "Đổ hội thoại Pancake vào CRM", "bool",
        "Tắt = poller vẫn chạy cho bot nhưng CRM không sinh khách/hội thoại mới"),
    Muc("pos_sync_enabled", "dong_bo", "Đổ đơn Pancake POS vào CRM", "bool",
        "Bật là đơn mới cập nhật tự về crm.orders. Đơn cũ: scripts/backfill_don_pos.py"),
    Muc("pos_sync_interval", "dong_bo", "Nhịp kéo đơn POS", "float",
        "Bao lâu hỏi POS một lần", 30, 86400, "giây"),
    Muc("sync_retry_enabled", "dong_bo", "Tự chạy lại bản ghi đồng bộ lỗi", "bool",
        "Hàng đợi lỗi ở màn Tích hợp → tab Danh sách lỗi"),
    Muc("sync_retry_interval", "dong_bo", "Nhịp quét hàng đợi lỗi", "float",
        "", 30, 86400, "giây"),
    Muc("sync_retry_batch", "dong_bo", "Số bản ghi thử lại mỗi lượt", "int",
        "", 1, 500, "bản ghi"),
    Muc("sync_token_check_hours", "dong_bo", "Nhịp kiểm tra token Pancake", "float",
        "Token lỗi/hết hạn sẽ báo đỏ ở màn Tích hợp", 0.5, 168, "giờ"),

    # --- Quảng cáo ---
    Muc("ads_sync_enabled", "quang_cao", "Đồng bộ cây quảng cáo & chi phí", "bool",
        "Nguồn: Pancake POS Ads Manager. Lịch sử: scripts/backfill_quang_cao.py"),
    Muc("ads_sync_interval", "quang_cao", "Nhịp đồng bộ quảng cáo", "float",
        "Mỗi lượt làm tươi chi phí hôm nay + hôm qua", 300, 604800, "giây"),
    Muc("ads_sync_tree_days", "quang_cao", "Cửa sổ kéo cây quảng cáo", "int",
        "Lấy campaign/adset/ad chạy trong ngần này ngày gần nhất", 1, 365, "ngày"),

    # --- Bot Pancake ---
    Muc("inbox_poll_enabled", "bot", "Poller kéo hội thoại Pancake", "bool",
        "Tắt = màn Tin nhắn gọi thẳng Pancake, kho hội thoại ngừng cập nhật"),
    Muc("inbox_poll_interval", "bot", "Nhịp hỏi nhanh nhất (page đang có khách)",
        "float", "", 5, 3600, "giây"),
    Muc("inbox_poll_max_interval", "bot", "Trần nhịp khi page im lặng", "float",
        "Page ế thì giãn dần gấp đôi tới mức này", 10, 7200, "giây"),
    Muc("inbox_poll_error_threshold", "bot", "Số lần lỗi liên tiếp thì ngắt mạch",
        "int", "", 1, 50, "lượt"),
    Muc("inbox_poll_error_backoff", "bot", "Nghỉ bao lâu sau khi ngắt mạch", "float",
        "", 60, 86400, "giây"),
    Muc("sentiment_enabled", "bot", "Quét cảm xúc tiêu cực", "bool",
        "Dùng chung công tắc với màn Cảm xúc", dac_biet="sentiment_bat"),
    Muc("sentiment_method", "bot", "Cách quét cảm xúc", "str",
        "keyword = miễn phí · llm = gọi OpenAI, chính xác hơn",
        chon=("keyword", "llm"), dac_biet="sentiment_cach"),
    Muc("sentiment_interval", "bot", "Nhịp quét cảm xúc", "float", "", 1, 3600, "giây"),
    Muc("sentiment_batch", "bot", "Số hội thoại mỗi mẻ quét", "int",
        "Quét bằng LLM thì đây là chỗ canh chi phí", 1, 100, "hội thoại"),
)

THEO_MA: dict[str, Muc] = {m.code: m for m in MUC}


# ------------------------------------------------------------------ đọc
def _mac_dinh(muc: Muc):
    """Giá trị nền: lấy từ .env (đối tượng Settings) — thiếu thì None."""
    return getattr(settings, muc.code, None)


def _ep_kieu(muc: Muc, raw):
    """Chuỗi trong DB -> đúng kiểu Python. Hỏng thì lùi về mặc định .env."""
    try:
        if muc.kieu == "bool":
            return str(raw).strip().lower() in ("1", "true", "on", "bat", "yes")
        if muc.kieu == "int":
            return int(float(raw))
        if muc.kieu == "float":
            return float(raw)
        return str(raw)
    except (TypeError, ValueError):
        return _mac_dinh(muc)


def _nap() -> dict:
    """Bảng ghi đè trong DB (cache `_TTL` giây). DB hỏng -> coi như chưa đổi gì."""
    if time.monotonic() - _cache["luc"] < _TTL:
        return _cache["data"]
    data: dict = {}
    try:
        from app.db.client import get_pg_pool

        pool = get_pg_pool()
        with pool.connection() as conn:
            rows = conn.execute("select code, value from crm.app_settings").fetchall()
        data = {r["code"]: r["value"] for r in rows}
    except Exception:  # noqa: BLE001 — mất DB thì chạy theo .env, không được vỡ worker
        data = _cache["data"]
    _cache.update(luc=time.monotonic(), data=data)
    return data


def _dac_biet_doc(muc: Muc):
    """Cài đặt có cơ chế lưu riêng (công tắc cảm xúc trong file JSON)."""
    from app.workers import switch

    if muc.dac_biet == "sentiment_bat":
        return switch.is_on()
    if muc.dac_biet == "sentiment_cach":
        return switch.cach_quet()
    return None


def lay(code: str):
    """Giá trị đang có hiệu lực của một cài đặt (DB → .env → None)."""
    muc = THEO_MA.get(code)
    if muc is None:
        return getattr(settings, code, None)
    if muc.dac_biet:
        return _dac_biet_doc(muc)
    raw = _nap().get(code)
    return _mac_dinh(muc) if raw is None else _ep_kieu(muc, raw)


def bat(code: str) -> bool:
    """Đọc công tắc (dùng ở worker: `if not runtime_config.bat('pos_sync_enabled')`)."""
    return bool(lay(code))


def so(code: str, mac_dinh: float = 0.0) -> float:
    """Đọc một con số, luôn trả về số (None/rác -> `mac_dinh`)."""
    v = lay(code)
    try:
        return float(v)
    except (TypeError, ValueError):
        return mac_dinh


def da_doi(code: str) -> bool:
    """Cài đặt này đang bị ghi đè so với .env hay không (để giao diện đánh dấu)."""
    return code in _nap()


# ------------------------------------------------------------------ ghi
def dat(code: str, value, user_id: int | None = None):
    """Ghi đè một cài đặt. Trả về giá trị đã ép kiểu đang có hiệu lực."""
    muc = THEO_MA[code]
    if muc.dac_biet:
        from app.workers import switch

        if muc.dac_biet == "sentiment_bat":
            return switch.set_on(bool(value))
        return switch.set_cach_quet(str(value))

    from app.db.client import get_pg_pool

    chuoi = "true" if (muc.kieu == "bool" and value) else \
            "false" if muc.kieu == "bool" else str(value)
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            insert into crm.app_settings (code, value, updated_by)
            values (%s, %s, %s)
            on conflict (code) do update set
                value = excluded.value, updated_by = excluded.updated_by
            """,
            (code, chuoi, user_id),
        )
    xoa_cache()
    return lay(code)


def dat_lai_mac_dinh(code: str):
    """Xoá phần ghi đè -> quay về đúng giá trị trong .env."""
    if THEO_MA[code].dac_biet:
        return lay(code)
    from app.db.client import get_pg_pool

    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("delete from crm.app_settings where code = %s", (code,))
    xoa_cache()
    return lay(code)


def xoa_cache() -> None:
    """Ép lượt đọc kế tiếp lấy lại từ DB (gọi sau mỗi lần ghi)."""
    _cache.update(luc=0.0, data=_cache["data"])
    _cache["luc"] = 0.0


# ------------------------------------------------------------------ cho giao diện
def danh_sach() -> list[dict]:
    """Toàn bộ cài đặt kèm giá trị hiện tại + mặc định — dựng màn Cài đặt / API."""
    ra = []
    for muc in MUC:
        ra.append({
            "code": muc.code, "nhom": muc.nhom, "nhom_ten": NHOM.get(muc.nhom, muc.nhom),
            "ten": muc.ten, "kieu": muc.kieu, "mo_ta": muc.mo_ta,
            "don_vi": muc.don_vi, "chon": list(muc.chon),
            "nho_nhat": muc.nho_nhat, "lon_nhat": muc.lon_nhat,
            "gia_tri": lay(muc.code),
            "mac_dinh": None if muc.dac_biet else _mac_dinh(muc),
            "da_doi": bool(muc.dac_biet) is False and da_doi(muc.code),
            "rieng": bool(muc.dac_biet),
        })
    return ra


def theo_nhom() -> list[dict]:
    """Cài đặt gom theo nhóm, giữ đúng thứ tự khai báo trong `MUC`."""
    ds = danh_sach()
    ra = []
    for ma, ten in NHOM.items():
        muc = [x for x in ds if x["nhom"] == ma]
        if muc:
            ra.append({"ma": ma, "ten": ten, "muc": muc})
    return ra
