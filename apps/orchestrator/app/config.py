from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Receipt AI Orchestrator"
    database_url: str = "postgresql+psycopg2://postgres:postgres@db:5432/receipts_db"
    agent_url: str = "http://agent-analyzer:8100/rpc"
    upload_dir: str = "/data/uploads"
    cors_origins: str = "http://localhost:3000"

    max_upload_bytes: int = 8 * 1024 * 1024
    allowed_mime_types: str = "application/pdf,image/png,image/jpeg,image/jpg,text/plain,text/csv,application/octet-stream"
    allowed_extensions: str = ".pdf,.png,.jpg,.jpeg,.txt,.csv"

    agent_timeout_seconds: float = 25.0
    agent_retries: int = 2
    agent_backoff_seconds: float = 0.5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_mime_types_list(self) -> list[str]:
        return [value.strip().lower() for value in self.allowed_mime_types.split(",") if value.strip()]

    @property
    def allowed_extensions_set(self) -> set[str]:
        return {value.strip().lower() for value in self.allowed_extensions.split(",") if value.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

