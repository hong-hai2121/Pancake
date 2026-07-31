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
