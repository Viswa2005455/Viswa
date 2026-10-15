"""Application settings, read from environment variables or backend/.env (never committed)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    fis_env: str = "development"
    fis_cors_origins: str = "http://localhost:5173"
    fis_storage_dir: Path = BACKEND_DIR / "storage"

    fis_max_upload_mb: int = 25
    fis_max_files_per_request: int = 10
    fis_zip_max_entries: int = 200
    fis_zip_max_uncompressed_mb: int = 100

    fis_ai_provider: str = "none"
    anthropic_api_key: SecretStr | None = None
    fis_ai_model: str = "claude-sonnet-5-5"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.fis_cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.fis_max_upload_mb * 1024 * 1024

    @property
    def upload_dir(self) -> Path:
        d = Path(self.fis_storage_dir)
        if not d.is_absolute():
            d = BACKEND_DIR / d
        return d / "uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()
