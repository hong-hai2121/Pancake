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

    # --- Supabase / Postgres ---
    supabase_url: str = ""      # https://<project>.supabase.co
    supabase_key: str = ""      # SECRET key (chạy phía server, bỏ qua RLS)
    database_url: str = ""      # chuỗi kết nối Postgres trực tiếp (hiện chưa dùng)


@lru_cache
def get_settings() -> Settings:
    """Trả về đối tượng Settings dùng chung.

    Bọc `lru_cache` để file .env chỉ được đọc & parse MỘT lần cho cả vòng đời
    tiến trình (các lần gọi sau trả lại cùng một instance).
    """
    return Settings()


# Import sẵn để mọi nơi chỉ cần `from app.config import settings`.
settings = get_settings()
