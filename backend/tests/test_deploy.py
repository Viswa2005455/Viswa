"""Hosting: the API serves the built website, limits request size, and reads hosting-style settings."""

import pytest


@pytest.fixture()
def site(tmp_path, monkeypatch, anon_client):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Finance Intelligence Studio</title>")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside the build folder")
    monkeypatch.setenv("FIS_FRONTEND_DIR", str(dist))
    from app.config import get_settings
    get_settings.cache_clear()
    return anon_client


def test_website_files_and_client_side_routes(site):
    home = site.get("/")
    assert home.status_code == 200 and "Finance Intelligence Studio" in home.text
    assert "default-src 'self'" in home.headers["content-security-policy"]
    deep = site.get("/red-flags")  # a React route, not a file
    assert deep.status_code == 200 and deep.text == home.text
    asset = site.get("/assets/index-abc123.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    assert site.get("/favicon.svg").text == "<svg/>"
    assert site.get("/assets/missing.js").status_code == 404
    api = site.get("/api/health")
    assert api.headers["cache-control"] == "no-store" and "content-security-policy" not in api.headers
    assert site.get("/api/nope").status_code == 404


def test_website_never_serves_files_outside_build(site):
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/..%2f..%2fsecret.txt"):
        r = site.get(path)
        assert "outside the build folder" not in r.text


def test_without_a_build_the_api_explains(anon_client, tmp_path, monkeypatch):
    monkeypatch.setenv("FIS_FRONTEND_DIR", str(tmp_path / "not-built"))
    from app.config import get_settings
    get_settings.cache_clear()
    r = anon_client.get("/some-page")
    assert r.status_code == 404 and "npm run dev" in r.json()["detail"]


def test_request_body_limit(anon_client, monkeypatch):
    monkeypatch.setenv("FIS_MAX_REQUEST_MB", "1")
    monkeypatch.setenv("FIS_MAX_UPLOAD_MB", "1")
    from app.config import get_settings
    get_settings.cache_clear()
    big = b"x" * (1024 * 1024 + 10)
    r = anon_client.post("/api/auth/login", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["type"] == "too_large"

    def chunks():  # no Content-Length: counted as it streams
        for _ in range(3):
            yield b"y" * (512 * 1024)
    r = anon_client.post("/api/auth/login", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert anon_client.post("/api/auth/login", json={"email": "a@b.co", "password": "x"}).status_code in (401, 422)


def test_hosting_settings(monkeypatch):
    from app.config import Settings
    for given in ("postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"):
        assert Settings(_env_file=None, database_url=given).database_url == "postgresql+psycopg://u:p@h:5432/d"
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://fis.onrender.com/")
    s = Settings(_env_file=None, fis_env="production", fis_cors_origins="")
    assert "https://fis.onrender.com" in s.cors_origins and s.origin_allowed("https://fis.onrender.com")
    assert not s.origin_allowed("http://localhost:5173")
