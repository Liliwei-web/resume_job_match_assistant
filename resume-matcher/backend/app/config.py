"""Application settings, all overridable through environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://resume:resume@db:5432/resume_matcher"

    jwt_secret: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 1440

    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout_seconds: int = 90
    llm_max_retries: int = 2

    seed_demo_data: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080"

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
