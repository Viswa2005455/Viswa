"""Test fixtures.

The suite runs against PostgreSQL (TEST_DATABASE_URL, default: the local
finance_studio_test database from the README) and builds the schema with the real Alembic
migrations. If PostgreSQL is unreachable it falls back to SQLite so formula tests still run,
and prints a warning.
"""

import os
import warnings

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

DEFAULT_TEST_DB = "postgresql+psycopg://fis_app:fis_dev_password@localhost:5432/finance_studio_test"
TABLES = ["activity", "saved_item_versions", "saved_items", "uploads", "sessions", "projects", "users"]
PASSWORD = "correct-horse-battery-9"


def _postgres_available(url: str) -> bool:
    try:
        with create_engine(url).connect() as c:
            c.execute(text("select 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def database_url(tmp_path_factory):
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB)
    if url.startswith("postgresql") and _postgres_available(url):
        from alembic import command
        from alembic.config import Config
        cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.downgrade(cfg, "base")   # proves the downgrade path works
        command.upgrade(cfg, "head")
        return url
    warnings.warn("PostgreSQL test database unavailable; falling back to SQLite.")
    path = tmp_path_factory.mktemp("db") / "test.sqlite"
    url = f"sqlite:///{path}"
    from app.db.models import Base
    Base.metadata.create_all(create_engine(url))
    return url


def _reset(url: str) -> None:
    eng = create_engine(url)
    with eng.begin() as c:
        if url.startswith("postgresql"):
            c.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
        else:
            for t in TABLES:
                c.execute(text(f"DELETE FROM {t}"))
    eng.dispose()


@pytest.fixture()
def anon_client(tmp_path, monkeypatch, database_url):
    monkeypatch.setenv("FIS_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", database_url)
    from app.auth.security import limiter
    from app.config import get_settings
    from app.db.session import get_engine
    get_settings.cache_clear()
    get_engine.cache_clear()
    limiter.reset()
    _reset(database_url)
    from app import main
    with TestClient(main.app) as c:
        yield c
    get_settings.cache_clear()
    get_engine.cache_clear()


def register(client, email="alice@example.com", password=PASSWORD, name="Alice"):
    r = client.post("/api/auth/register", json={"email": email, "password": password, "display_name": name})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def client(anon_client):
    register(anon_client)
    return anon_client


def make_pdf(lines: list[str]) -> bytes:
    """Build a minimal valid one-page PDF with the given text lines (no extra dependencies)."""
    content = "BT /F1 12 Tf 50 750 Td 14 TL " + " ".join(f"({l}) Tj T*" for l in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out
