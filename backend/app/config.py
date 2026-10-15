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

    # PostgreSQL connection. The default points at the local development database created in
    # README step 2; production must override it (startup refuses the dev password in production).
    database_url: str = "postgresql+psycopg://fis_app:fis_dev_password@localhost:5432/finance_studio"

    fis_session_days: int = 14
    fis_upload_retention_days: int = 90
    fis_allow_registration: bool = True
    fis_cookie_secure: bool | None = None  # None = secure cookies automatically in production

    fis_ai_provider: str = "none"
    anthropic_api_key: SecretStr | None = None
    fis_ai_model: str = "claude-sonnet-5-5"

    @property
    def is_production(self) -> bool:
        return self.fis_env.lower() == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.is_production if self.fis_cookie_secure is None else self.fis_cookie_secure

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
