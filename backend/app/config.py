"""Application settings, read from environment variables or backend/.env (never committed)."""

import os
import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
_LOCAL_ORIGIN = re.compile(r"http://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d{1,5})?")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8-sig", extra="ignore")

    fis_env: str = "development"
    fis_cors_origins: str = "http://localhost:5173"
    fis_storage_dir: Path = BACKEND_DIR / "storage"

    fis_max_upload_mb: int = 25
    # Whole-request limit, checked before the body is read (an online copy has no Nginx in front).
    fis_max_request_mb: int = 60
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

    # Built website (npm run build). When it exists, the API also serves it, so one process hosts
    # the whole app on one address (how the Docker image and the Render blueprint run it).
    fis_frontend_dir: Path = BACKEND_DIR.parent / "frontend" / "dist"

    # Live share prices (optional): eodhd | twelvedata | none. The key stays on the server.
    fis_market_provider: str = "none"
    fis_market_api_key: SecretStr | None = None

    fis_ai_provider: str = "none"
    anthropic_api_key: SecretStr | None = None
    fis_ai_model: str = "claude-opus-5-5"
    fis_ai_timeout_seconds: float = Field(default=120.0, ge=5, le=600)  # per API attempt
    fis_ai_max_retries: int = Field(default=2, ge=0, le=5)  # SDK retries 429, 5xx and connection errors
    fis_ai_deadline_seconds: float = Field(default=300.0, ge=10, le=1800)  # whole answer, across tool rounds

    @field_validator("database_url")
    @classmethod
    def _driver(cls, url: str) -> str:
        """Hosting providers hand out postgres:// or postgresql:// URLs; use the installed psycopg 3 driver."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def resolved_database_url(self) -> str:
        """DATABASE_URL with relative SQLite paths anchored to the backend folder.

        SQLite (e.g. sqlite:///storage/finance_studio.db) is the one-click local mode for a
        single user on one computer; PostgreSQL is required for anything shared or deployed.
        """
        url = self.database_url
        prefix = "sqlite:///"
        if url.startswith(prefix) and not url.startswith(prefix + "/") and ":memory:" not in url:
            path = Path(url[len(prefix):])
            if not path.is_absolute():
                path = BACKEND_DIR / path
            path.parent.mkdir(parents=True, exist_ok=True)
            url = prefix + path.as_posix()
        return url

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.fis_env.lower() == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.is_production if self.fis_cookie_secure is None else self.fis_cookie_secure

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.fis_cors_origins.split(",") if o.strip()]
        hosted = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")  # set by Render to the site's https address
        return origins + [hosted] if hosted and hosted not in origins else origins

    def origin_allowed(self, origin: str) -> bool:
        """Configured origins are always allowed. Outside production, any port on this computer
        (localhost) is too, so the app keeps working when the website starts on another port."""
        if origin in self.cors_origins:
            return True
        return not self.is_production and _LOCAL_ORIGIN.fullmatch(origin) is not None

    @property
    def max_request_bytes(self) -> int:
        return max(self.fis_max_request_mb, self.fis_max_upload_mb) * 1024 * 1024

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
