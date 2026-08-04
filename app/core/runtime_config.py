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
    "uu_dai": "Voucher & hạng thẻ",
    "gui_tin": "Gửi tin hàng loạt (chiến dịch)",
    "giam_sat": "Giám sát & soi tin xác minh công",
    "sale": "Thang bám đuổi Sale",
    "cskh": "Quy trình CSKH (3 giai đoạn)",
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
    Muc("msg_sync_enabled", "dong_bo", "Kéo nội dung tin nhắn về CRM", "bool",
        "FR-012: tab Hội thoại của hồ sơ khách. Lịch sử cũ: scripts/backfill_tin_nhan.py"),
    Muc("msg_sync_interval", "dong_bo", "Nhịp kéo tin nhắn", "float",
        "Mỗi vòng chỉ kéo hội thoại CÓ TIN MỚI từ lần trước", 30, 86400, "giây"),
    Muc("msg_sync_batch", "dong_bo", "Số hội thoại kéo mỗi vòng", "int",
        "Mỗi hội thoại tốn 1 lời gọi Pancake — canh quota ở đây", 1, 200, "hội thoại"),
    Muc("notify_scan_enabled", "dong_bo", "Quét sinh thông báo (màn Thông báo)",
        "bool", "11 nguồn: lead mới · việc quá hạn · đơn giao/hoàn · lỗi đồng bộ…"),
    Muc("notify_scan_interval", "dong_bo", "Nhịp quét thông báo", "float",
        "", 30, 86400, "giây"),
    Muc("notify_keep_days", "dong_bo", "Giữ thông báo đã đọc", "int",
        "Cũ hơn ngần này thì tự xoá; CHƯA đọc thì không bao giờ xoá", 1, 3650, "ngày"),
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

    # --- Voucher & hạng thẻ (C1 — màn /crm/voucher · /crm/hang-the) ---
    Muc("voucher_expiry_days", "uu_dai", "Hạn mặc định của voucher", "int",
        "Số ngày tính từ hôm tặng khi người tặng không gõ hạn riêng",
        1, 3650, "ngày"),
    Muc("voucher_warn_days", "uu_dai", "Báo 'sắp hết hạn' trước", "int",
        "Dưới ngần này ngày thì màn Voucher tô đỏ + kèm chữ 'sắp hết'",
        1, 90, "ngày"),
    Muc("card_rank_downgrade_days", "uu_dai",
        "Không nhận hàng bao lâu thì giảm quyền lợi ngầm", "int",
        "Hạng HIỂN THỊ giữ nguyên, chỉ quyền lợi tụt 1 bậc — và KHÔNG báo khách",
        30, 3650, "ngày"),
    Muc("voucher_expire_scan_enabled", "uu_dai",
        "Tự chuyển voucher quá hạn sang 'hết hạn không dùng'", "bool",
        "Chạy mỗi ngày; tắt thì trạng thái voucher phải sửa tay"),

    # --- Gửi tin hàng loạt (C3 — chiến dịch 2 tầng) ---
    # 🔴 CÔNG TẮC AN TOÀN. Mặc định TẮT và phải giữ TẮT suốt lúc đang dựng:
    # bật là tin bay thẳng tới khách thật, KHÔNG thu hồi được. Mẫu Kallet để
    # đây là BƯỚC CUỐI CÙNG của quy trình triển khai — làm xong hết mọi thứ
    # khác rồi mới bật.
    Muc("outbound_messaging_enabled", "gui_tin",
        "🔴 CHO PHÉP GỬI TIN THẬT tới khách", "bool",
        "TẮT = chạy chế độ NHÁP: mọi thứ diễn ra như thật nhưng không tin nào "
        "rời hệ thống, và khách KHÔNG bị đánh dấu 'đã gửi'"),
    Muc("campaign_batch_max", "gui_tin", "Trần số tin mỗi đợt chạy tay", "int",
        "Chặn tai nạn bấm nhầm gửi cả tệp trong một lượt", 1, 5000, "tin"),
    Muc("campaign_auto_run", "gui_tin", "Tự chạy đợt theo lịch chiến dịch",
        "bool", "Tắt thì mỗi đợt phải bấm tay ở màn Chiến dịch"),

    # --- Giám sát & soi tin (C4) ---
    Muc("verify_scan_enabled", "giam_sat", "Tự soi tin xác minh công", "bool",
        "Máy đọc tin Pancake tìm bằng chứng nhân viên đã nhắn/gọi"),
    Muc("verify_window_days", "giam_sat", "Cửa sổ soi mỗi phía", "int",
        "Nhân viên hay nhắn buổi sáng, tối mới tick — soi đúng trong ngày là "
        "bác oan hàng loạt", 0, 7, "ngày"),
    Muc("verify_reject_hours", "giam_sat", "Quá bao lâu không thấy tin thì bác",
        "int", "Trưởng nhóm vẫn vớt tay được ở màn Giám sát", 1, 720, "giờ"),

    # --- Thang bám đuổi Sale (C5) ---
    # 🚩 `sale_ladder_start` là CHỐT CHẶN QUAN TRỌNG NHẤT: bộ dò chỉ đọc tin TỪ
    # ngày này. Để trống/lùi quá xa thì khách nhắn qua lại vài tháng sẽ nhảy
    # thẳng bước cuối, "hết thang", rơi khỏi bảng việc — cả bảng Sale trống.
    Muc("sale_ladder_start", "sale", "🚩 Ngày bật thang (YYYY-MM-DD)", "str",
        "Bộ dò CHỈ đọc tin từ ngày này. Trống = hôm nay. Đừng lùi quá xa"),
    Muc("sale_scan_enabled", "sale", "Tự dò con trỏ bước từ tin nhắn", "bool",
        "Tắt thì con trỏ chỉ đổi khi nhân viên kéo thẻ tay"),
    Muc("sale_step_rest_hours", "sale", "Nghỉ giữa 2 bước", "int",
        "Đáp khách xong, khách im ngần này giờ thì bước kế hiện ngay",
        0, 168, "giờ"),
    Muc("sale_step_max_per_day", "sale", "Trần số bước mỗi ngày", "int",
        "Chặn nhân viên bắn 8 tin liền một lúc cho xong việc", 1, 20, "bước"),
    Muc("sale_step_hour_from", "sale", "Cửa giờ nhắn — từ", "int",
        "Hai đầu bằng nhau = mở cả ngày", 0, 23, "giờ"),
    Muc("sale_step_hour_to", "sale", "Cửa giờ nhắn — đến", "int", "", 0, 23, "giờ"),
    Muc("sale_hot_hours", "sale", "Giai đoạn NÓNG của khách mới", "int",
        "Trong ngần này giờ đầu: bỏ cửa giờ, cho đi nhiều bước hơn",
        0, 168, "giờ"),
    Muc("sale_hot_max_steps", "sale", "Trần bước trong giai đoạn nóng", "int",
        "", 1, 20, "bước"),
    Muc("sale_step_window", "sale", "Mỗi tin nhảy tối đa mấy bước", "int",
        "Chặn một cụm chữ lạc đẩy khách thẳng tới bước cuối rồi bị buông oan",
        1, 8, "bước"),
    Muc("sale_step_skip_max", "sale", "Trần NHẢY CÓC khi khách nói toạc", "int",
        "Đích xa hơn trần thì KHÔNG nhảy tí nào — nhảy nửa vời còn tệ hơn đứng "
        "yên", 0, 8, "bước"),
    Muc("sale_stuck_days", "sale", "Kẹt bao lâu thì vào cột Quá hạn", "int",
        "", 1, 90, "ngày"),

    # --- Quy trình CSKH 3 giai đoạn (C6 — màn /crm/bang-viec-cskh) ---
    # 🔒 Công tắc tổng. TẮT = bảng việc chạy luật dải ngày cũ (30/60/150), đội
    # đang làm việc không thấy gì lạ. Chỉ bật khi thang mốc đã dựng xong.
    Muc("cskh_flow_enabled", "cskh", "Bật quy trình CSKH 3 giai đoạn", "bool",
        "Cảm ơn → tặng voucher → nhắc hạn → thang mua lại. Tắt thì bảng việc "
        "xếp cột theo dải ngày cũ"),
    Muc("cskh_first_milestone", "cskh", "Mốc chăm định kỳ ĐẦU TIÊN", "int",
        "Số ngày kể từ ngày nhận hàng. Trước mốc này là giai đoạn 1-2 "
        "(cảm ơn · voucher)", 1, 365, "ngày"),
    Muc("cskh_milestone_gap", "cskh", "Hai mốc định kỳ cách nhau", "int",
        "Đổi số này là cả thang mốc sinh lại — nhớ bấm 'Dựng lại thang'",
        1, 180, "ngày"),
    Muc("cskh_leave_days", "cskh", "Bao lâu không nhận hàng thì khách RỜI bảng",
        "int", "⚠️ 210 này KHÁC ba con số 180 (giảm quyền lợi hạng thẻ · nhắc "
        "cuối thang mua lại · thôi phân công)", 30, 3650, "ngày"),
    Muc("cskh_overdue_days", "cskh", "Mốc mở quá bao lâu chưa chăm thì Quá hạn",
        "int", "Nguồn quá hạn THỨ HAI, cộng thêm nguồn cũ (khách nhắn chưa ai "
        "đáp)", 1, 90, "ngày"),
    Muc("cskh_safety_days", "cskh", "Lưới an toàn — im mấy ngày vẫn tặng voucher",
        "int", "Khách nhận hàng rồi im lặng: đủ ngần này ngày là tặng, không "
        "chờ nữa", 1, 90, "ngày"),
    Muc("cskh_call_after_days", "cskh", "Khách im mấy ngày thì sinh việc GỌI",
        "int", "Mỗi khách chỉ gọi 1 LẦN trong một đợt", 1, 90, "ngày"),
    Muc("cskh_promo_days", "cskh", "Đợt bám đuổi khuyến mãi kéo dài", "int",
        "Ngày 1 gửi ưu đãi · ngày 2-3 gọi push · hết đợt thì hẹn dịp sau",
        1, 30, "ngày"),
    Muc("voucher_remind_days", "cskh", "Nhịp nhắc hạn voucher", "str",
        "Số ngày TRƯỚC ngày hết hạn, cách nhau dấu phẩy. 0 = nhắc đúng ngày "
        "hết hạn. Ví dụ: 15,7,3,0"),
    # 🔴 Mệnh giá máy tặng. 0 = KHÔNG tặng — xem luật 4 ở services/cskh_service.
    Muc("voucher_first_value", "cskh", "🔴 Mệnh giá voucher MÁY tự tặng", "int",
        "0 = máy KHÔNG tặng, để nhân viên tặng tay. Voucher là tiền: thà không "
        "phát còn hơn phát bừa một mệnh giá đoán mò", 0, 100_000_000, "đ"),

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
