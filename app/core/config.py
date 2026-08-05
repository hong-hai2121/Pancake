"""Đọc file .env và cung cấp cấu hình chung cho toàn app.

Dùng pydantic-settings: mỗi thuộc tính trong `Settings` tự động được nạp từ biến
môi trường cùng tên (không phân biệt hoa/thường). Ví dụ thuộc tính
`pancake_access_token` <- biến `PANCAKE_ACCESS_TOKEN` trong .env.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Toàn bộ cấu hình app, gom theo nhóm. Giá trị mặc định = fallback khi
    biến tương ứng không có trong .env."""

    # Nạp từ file .env; bỏ qua (không báo lỗi) các biến thừa không khai báo ở đây.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Pancake (pages.fm) ---
    pancake_access_token: str = ""                       # JWT lấy từ Pancake POS
    pancake_base_url: str = "https://pages.fm/api/v1"    # gốc API nội bộ, ít khi đổi
    # Public API (để lấy TÊN + MÀU thẻ): cần page_access_token riêng mỗi page.
    pancake_public_base_url: str = "https://pages.fm/api/public_api/v1"
    # JSON map {"page_id": "page_access_token"} — tự sinh & lưu lại, hoặc điền tay.
    # Thiếu page nào thì màn Tin nhắn tự hiện "Thẻ #<id>" cho page đó.
    pancake_page_tokens: str = ""
    # Các page (ID, phân tách bởi dấu phẩy) được phép TỰ SINH page_access_token
    # khi chưa có (cần token Pancake quyền Admin). Để trống = không tự sinh page nào.
    pancake_tag_page_ids: str = ""
    # BRD mục 4 — "Nút mở đúng hội thoại Pancake từ hồ sơ CRM". Chỉ ghép chuỗi,
    # KHÔNG gọi API. Pancake đổi đường dẫn thì sửa .env, không phải sửa code.
    pancake_conversation_url: str = "https://pancake.vn/{page_id}?c_id={conversation_id}"

    # --- Pancake POS (Open API RIÊNG — không dùng chung JWT pages.fm ở trên) ---
    # api_key tạo trong POS: Cấu hình -> Nâng cao -> Tích hợp bên thứ 3 -> API Key.
    # Dò endpoint/shape thật: scripts/do_pos_api.py (bắt buộc trước B7 — đã dò 01/08).
    pancake_pos_api_key: str = ""
    pancake_pos_shop_id: str = ""       # số sau pos.pages.fm/shop/ (= pages.shop_id)
    pancake_pos_base_url: str = "https://pos.pages.fm/api/v1"
    # B7: worker kéo đơn POS về crm.orders. Mặc định TẮT như CRM_SYNC_ENABLED —
    # bật lên là đơn Pancake bắt đầu đổ về CRM thật. Backfill: scripts/backfill_don_pos.py
    pos_sync_enabled: bool = False
    pos_sync_interval: float = 300.0    # giây giữa 2 lượt kéo đơn mới cập nhật

    # --- Quảng cáo (BRD mục 4 phần nguồn quảng cáo) ---
    # Cây campaign/adset/ad + CHI PHÍ lấy từ Pancake POS Ads Manager (không cần
    # Facebook Ads API riêng). Mặc định TẮT như các công tắc đồng bộ khác.
    # Lịch sử: scripts/backfill_quang_cao.py
    ads_sync_enabled: bool = False
    ads_sync_interval: float = 21600.0   # 6 giờ — cấu trúc + chi phí đổi chậm
    ads_sync_tree_days: int = 90         # cửa sổ kéo cây quảng cáo mỗi lượt

    # --- Voucher & hạng thẻ (C1 — port mẫu Kallet voucher.php/hang-the.php) ---
    # 180 ngày ở đây là mốc GIẢM QUYỀN LỢI của hạng thẻ. Hệ thống còn ba con số
    # 180/180/210 khác nghĩa (nhắc cuối · thôi phân công · rời bảng việc) — sửa
    # nhầm là hỏng nghiệp vụ khác, đọc kỹ tên biến trước khi đổi.
    voucher_expiry_days: int = 30
    voucher_warn_days: int = 3
    card_rank_downgrade_days: int = 180
    voucher_expire_scan_enabled: bool = True

    # --- Gửi tin hàng loạt (C3 — chiến dịch 2 tầng) ---
    # 🔴 GIỮ "tat". Bật là tin bay tới khách THẬT và không thu hồi được; đây là
    # bước cuối cùng của quy trình triển khai, không phải mặc định.
    # Đợt 2: BA trạng thái chứ không phải bật/tắt — xem services/cong_tac_gui_tin.
    outbound_messaging_mode: str = "tat"      # tat | nhap | that
    # 🔒 LỚP KHOÁ CỨNG — CỐ Ý chỉ có ở .env, KHÔNG bày ra màn Cài đặt. Còn True
    # thì không ai bấm nút trên web mà gửi được tin thật, kể cả admin bị chiếm
    # tài khoản. Mở lớp này là việc của người có quyền vào máy chủ.
    outbound_hard_lock: bool = True
    # 🔒 Khoá cứng RIÊNG cho LUỒNG TỰ ĐỘNG (Đợt 3), tách khỏi khoá trên: mở
    # đường gửi TAY không được kéo theo việc máy tự bắn hàng loạt. Gửi tay sai
    # một tin thì xin lỗi một khách; luật tự động sai thì sai với cả chục nghìn
    # khách trong một đêm. Đợt 3 mới dựng KHUNG — engine chưa có mã gọi API nào,
    # mở cờ này cũng chưa gửi được gì.
    auto_flow_hard_lock: bool = True
    outbound_messaging_enabled: bool = False  # cũ — chỉ còn để đọc dữ liệu di cư
    campaign_batch_max: int = 500        # trần tin mỗi lượt bấm tay
    campaign_auto_run: bool = False      # tự chạy đợt theo lịch
    meta_door_24h_on: bool = True        # 3 cửa gửi tin của Meta
    meta_door_ads_on: bool = True
    meta_door_out_on: bool = False       # ngoài cửa: cần mẫu Meta đã duyệt

    # --- Vòng đời khách & luật tự động (Đợt 2) ---
    # Thu hồi mặc định TẮT: 30 ngày đầu nhập dữ liệu mà máy đã đi thu hồi thì
    # khách rơi hàng loạt trước khi ai kịp nhận ra.
    luat_thu_hoi_on: bool = False
    luat_giam_quyenloi_on: bool = True
    voucher_first_auto_on: bool = True
    board_chi_inbox: bool = True         # bảng việc Sale chỉ nhận lead inbox
    # Luồng tự động (Đợt 3) — chỉ SINH VIỆC, không gửi tin. Mặc định TẮT.
    auto_flow_task_enabled: bool = False
    af_gio_quet: int = 9                 # giờ VN worker quét một lượt/ngày

    # --- Giám sát & soi tin (C4 — vòng xác minh công) ---
    # Cửa sổ ±1 NGÀY là con số đã chốt của mẫu: nhân viên nhắn buổi sáng, tối
    # mới ngồi tick, soi gọn trong ngày là bác oan hàng loạt.
    verify_scan_enabled: bool = True
    verify_window_days: int = 1
    nhandien_goi_gap: int = 2          # từ lạ cho chèn giữa các từ của mẫu
    verify_reject_hours: int = 72

    # --- Thang bám đuổi Sale (C5 — con trỏ đọc tin nhắn thật) ---
    # 🚩 sale_ladder_start TRỐNG = lấy hôm nay. Đây là chốt chặn: bộ dò chỉ đọc
    # tin TỪ ngày này, nếu không khách nhắn qua lại vài tháng sẽ nhảy thẳng
    # bước cuối rồi rơi khỏi bảng việc.
    sale_ladder_start: str = ""
    sale_scan_enabled: bool = True
    sale_step_rest_hours: int = 6      # nghỉ giữa 2 bước
    sale_step_max_per_day: int = 2     # trần bước/ngày
    sale_step_hour_from: int = 8       # cửa giờ nhắn
    sale_step_hour_to: int = 21
    sale_hot_hours: int = 24           # giai đoạn nóng của khách mới
    sale_hot_max_steps: int = 3
    sale_step_window: int = 2          # mỗi tin nhảy tối đa mấy bước
    sale_step_skip_max: int = 3        # trần nhảy cóc
    sale_stuck_days: int = 3           # kẹt bao lâu thì Quá hạn

    # --- Quy trình CSKH ba giai đoạn (C6 — port mẫu cskh_quy_trinh.php) ---
    # 🔒 cskh_flow_enabled GIỮ False cho tới khi thang mốc đã dựng và mệnh giá
    # voucher đã điền: bật giữa chừng là cả đội thấy khách nhảy cột trong giờ làm.
    cskh_flow_enabled: bool = False
    cskh_first_milestone: int = 45     # mốc chăm định kỳ ĐẦU TIÊN
    cskh_milestone_gap: int = 15       # hai mốc cách nhau
    cskh_leave_days: int = 210         # quá bấy nhiêu ngày thì khách rời bảng
    cskh_overdue_days: int = 3         # mốc mở quá bấy nhiêu ngày chưa chăm = quá hạn
    cskh_safety_days: int = 3          # lưới an toàn: im đủ ngần này vẫn tặng voucher
    cskh_call_after_days: int = 1      # khách im mấy ngày thì sinh việc GỌI
    cskh_promo_days: int = 3           # đợt bám đuổi khuyến mãi dài mấy ngày
    # Nhịp nhắc voucher — số ngày TRƯỚC ngày hết hạn (0 = đúng ngày hết hạn).
    voucher_remind_days: str = "15,7,3,0"
    # 🔴 0 = MÁY KHÔNG TỰ TẶNG. Voucher là tiền: thà không phát còn hơn phát bừa
    # một mệnh giá đoán mò. Điền số ở màn Cài đặt khi đã chốt mệnh giá.
    voucher_first_value: int = 0

    # --- Tích hợp (BRD mục 4): hàng đợi lỗi + cảnh báo token ---
    # Worker chạy lại các bản ghi đồng bộ hỏng (crm.sync_errors) và định kỳ kiểm
    # token còn sống không. Bật mặc định vì nó chỉ dọn dẹp: hàng đợi rỗng thì
    # gần như không tốn gì; tắt thì lỗi tồn đọng không ai xử lý.
    sync_retry_enabled: bool = True
    sync_retry_interval: float = 300.0   # giây giữa 2 lượt quét hàng đợi
    sync_retry_batch: int = 50           # số bản ghi thử lại mỗi lượt
    sync_token_check_hours: float = 6.0  # cách mấy giờ thì kiểm token một lần

    # --- Facebook Messenger (luồng Graph cũ, hiện không dùng) ---
    fb_page_access_token: str = ""      # token page để gọi Send API
    fb_verify_token: str = ""           # chuỗi tự đặt để verify webhook
    fb_app_secret: str = ""             # app secret để check chữ ký X-Hub-Signature

    # --- LLM ("não" sinh câu trả lời) ---
    llm_provider: str = "gemini"        # gemini | openai (hiện dùng openai)
    llm_model: str = "gpt-4o-mini"      # model chat khi provider = openai
    gemini_api_key: str = ""
    openai_api_key: str = ""

    # --- Embedding (vector hóa câu để tìm kiếm ngữ nghĩa) ---
    embedding_provider: str = "gemini"          # gemini | openai (hiện dùng openai)
    embedding_model: str = "text-embedding-004"  # openai: text-embedding-3-small
    # Số chiều vector — PHẢI khớp cột embedding trong DB thật (hiện là vector(1536)).
    embedding_dim: int = 1536

    # --- RAG (tìm kiếm ngữ nghĩa) ---
    rag_top_k: int = 5                  # số kết quả lấy mỗi lần tìm
    # Ngưỡng điểm tương đồng: chỉ nhận dòng có similarity >= ngưỡng.
    # 0.0 = không lọc (luôn trả top-k). Đặt ~0.6 để "không đủ giống thì trả rỗng".
    rag_match_threshold: float = 0.0
    # NGƯỠNG CHẶN (code, trước LLM) cho nút "Gợi ý trả lời": bỏ câu mẫu có
    # similarity < ngưỡng TRƯỚC khi đưa lên GPT. Nếu không câu nào đạt -> trả
    # NO_MATCH luôn, KHÔNG gọi LLM (chặn model "nặn" câu từ mẩu tri thức lạc đề +
    # tiết kiệm tiền). GPT chỉ chọn trong số đã đạt ngưỡng. PHẢI tune trên bộ test
    # thật: xem điểm ở trang "Thử tin nhắn" — quá cao thì hay "chưa có", quá thấp
    # thì lọt câu lạc đề. 0 = tắt (để GPT tự quyết hoàn toàn).
    rag_suggest_threshold: float = 0.55

    # --- Worker nền: kéo hội thoại + quét cảm xúc (app/workers/) ---
    # Chạy suốt vòng đời server, KHÔNG phụ thuộc có ai mở trang hay không.
    inbox_poll_enabled: bool = True      # tắt = không kéo, màn Tin nhắn tự quay về gọi Pancake trực tiếp
    # B2: poller đổ THÊM mỗi hội thoại vào crm.* (khách + định danh + hội thoại
    # + lead tự động — FR-011). Mặc định TẮT: bật lên là CRM bắt đầu sinh
    # khách/lead từ dữ liệu Pancake thật. Backfill kho cũ: scripts/backfill_crm_tu_watcher.py
    crm_sync_enabled: bool = False
    # FR-012: worker riêng kéo NỘI DUNG tin nhắn về crm.messages (crm_sync chỉ
    # có snippet). Tốn 1 lời gọi Pancake/hội thoại nên có nhịp + trần mẻ riêng.
    # Lịch sử cũ: scripts/backfill_tin_nhan.py
    msg_sync_enabled: bool = False
    msg_sync_interval: float = 120.0     # giây giữa 2 vòng quét hội thoại có tin mới
    msg_sync_batch: int = 20             # số hội thoại kéo mỗi vòng
    # Màn 3 — trung tâm thông báo: worker quét 11 nguồn trong DB. BẬT mặc định
    # (chỉ nhặt sự việc đã có sẵn, không sinh dữ liệu nghiệp vụ).
    notify_scan_enabled: bool = True
    notify_scan_interval: float = 300.0  # giây giữa 2 lượt quét
    notify_keep_days: int = 60           # xoá thông báo ĐÃ ĐỌC cũ hơn ngần này
    # NHỊP THÍCH ỨNG theo từng page: page vừa có tin mới -> hỏi lại sau
    # `inbox_poll_interval` giây; im lặng thì giãn GẤP ĐÔI mỗi lượt cho tới trần
    # `inbox_poll_max_interval`. Nhờ vậy page bận vẫn nhanh mà page ế không đốt
    # quota (Pancake trả 429 khá sớm).
    inbox_poll_interval: float = 20.0        # nhịp nhanh nhất (page đang có khách)
    inbox_poll_max_interval: float = 300.0   # trần khi page im lặng liên tục
    # Mỗi lượt chỉ xin `inbox_poll_limit_small` hội thoại; NGHI có sót (mọi dòng
    # trả về đều mới hơn mốc đã biết) thì mới xin thêm theo `inbox_poll_limit` ->
    # `inbox_poll_limit_max`. Xem `_CATCH_UP` trong app/workers/poller.py.
    inbox_poll_limit_small: int = 5
    inbox_poll_limit: int = 20
    inbox_poll_limit_max: int = 50
    # NGẮT MẠCH: page lỗi liên tiếp ngần này lượt (page bị Pancake vô hiệu hoá,
    # mất quyền...) thì nghỉ hẳn `inbox_poll_error_backoff` giây mới thử lại.
    inbox_poll_error_threshold: int = 3
    inbox_poll_error_backoff: float = 1800.0
    sentiment_enabled: bool = True       # tắt = không quét cảm xúc (kho vẫn được cập nhật)
    sentiment_interval: float = 8.0      # giây giữa 2 mẻ quét
    sentiment_batch: int = 10            # số hội thoại tối đa mỗi mẻ (llm: canh chi phí ở đây)
    # Model dùng khi cách quét = "llm". Để RIÊNG với `llm_model` (model viết câu
    # trả lời): phân loại 1 nhãn thì model rẻ là đủ, không cần con đắt tiền.
    sentiment_llm_model: str = "gpt-4o-mini"

    # --- Báo Telegram khi phát hiện tiêu cực ---
    # Thiếu 1 trong 2 = TẮT hẳn (không gửi gì, cũng không báo lỗi).
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- Đăng nhập / JWT (A2 — docs/A2-DANG-NHAP.md) ---
    # BẮT BUỘC có trong .env khi bật đăng nhập. Đổi secret = mọi phiên cũ mất
    # hiệu lực ngay (access token cũ không giải mã được nữa).
    jwt_secret: str = ""
    access_token_ttl_minutes: int = 30   # JWT sống ngắn; hết hạn tự lấy lại bằng refresh
    refresh_token_ttl_days: int = 14     # = thời hạn "Ghi nhớ đăng nhập"
    login_max_failed: int = 5            # FR-001: sai liên tiếp ngần này lần thì khoá tạm
    login_lock_minutes: int = 15
    cookie_secure: bool = False          # bật True khi chạy sau HTTPS (tunnel/domain)
    # Chỉ scripts/seed_auth.py đọc 2 biến này để tạo tài khoản admin đầu tiên.
    admin_bootstrap_password: str = ""
    admin_bootstrap_email: str = "admin@pancakebot.local"

    # --- Chọn nơi lưu dữ liệu ---
    # postgres = Postgres + pgvector cài trên máy này (mặc định).
    # supabase = Postgres trên cloud của Supabase (REST + pgvector).
    # Đổi backend KHÔNG đổi code: mọi hàm trong app/db/repositories/queries.py giữ nguyên
    # chữ ký, chỉ định tuyến sang lớp cài đặt tương ứng (xem app/db/backends/).
    db_backend: str = "postgres"            # postgres | supabase

    # --- Postgres local (dùng khi db_backend=postgres) ---
    # Chuỗi kết nối tới Postgres ĐÃ CÀI extension pgvector. Bảng + index HNSW tự
    # tạo ở lần chạy đầu (xem app/db/backends/postgres_be.py).
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:5432/pancakebot"
    pg_pool_min: int = 1                # số connection giữ sẵn trong pool
    pg_pool_max: int = 10               # trần connection (đủ cho uvicorn 1 tiến trình)
    pg_connect_timeout: float = 10.0    # giây chờ xin connection từ pool

    # --- Supabase (dùng khi db_backend=supabase) ---
    supabase_url: str = ""      # https://<project>.supabase.co
    supabase_key: str = ""      # SECRET key (chạy phía server, bỏ qua RLS)


@lru_cache
def get_settings() -> Settings:
    """Trả về đối tượng Settings dùng chung.

    Bọc `lru_cache` để file .env chỉ được đọc & parse MỘT lần cho cả vòng đời
    tiến trình (các lần gọi sau trả lại cùng một instance).
    """
    return Settings()


# Import sẵn để mọi nơi chỉ cần `from app.core.config import settings`.
settings = get_settings()
