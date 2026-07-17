"""Đọc .env và cung cấp cấu hình chung cho toàn app."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Pancake ---
    pancake_access_token: str = ""
    pancake_base_url: str = "https://pages.fm/api/v1"

    # --- Facebook ---
    fb_page_access_token: str = ""
    fb_verify_token: str = ""
    fb_app_secret: str = ""

    # --- LLM ---
    llm_provider: str = "gemini"          # gemini | openai
    gemini_api_key: str = ""
    openai_api_key: str = ""

    # --- Embedding ---
    embedding_provider: str = "gemini"    # gemini | openai
    embedding_model: str = "text-embedding-004"

    # --- Supabase / Postgres ---
    supabase_url: str = ""
    supabase_key: str = ""
    database_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
