from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    github_token: str = Field(..., alias="GITHUB_TOKEN")
    github_webhook_secret: str = Field(..., alias="GITHUB_WEBHOOK_SECRET")
    llm_api_key: str = Field(..., alias="LLM_API_KEY")

    llm_provider: str = Field("gemini", alias="LLM_PROVIDER")
    llm_model: str = Field("gemini-1.5-flash", alias="LLM_MODEL")
    github_api_base_url: str = Field("https://api.github.com", alias="GITHUB_API_BASE_URL")
    github_request_timeout_seconds: float = Field(30.0, alias="GITHUB_REQUEST_TIMEOUT_SECONDS")
    github_max_retries: int = Field(3, alias="GITHUB_MAX_RETRIES")
    github_retry_backoff_seconds: float = Field(1.0, alias="GITHUB_RETRY_BACKOFF_SECONDS")
    github_retry_max_backoff_seconds: float = Field(8.0, alias="GITHUB_RETRY_MAX_BACKOFF_SECONDS")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
