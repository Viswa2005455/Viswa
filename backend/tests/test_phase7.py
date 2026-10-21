"""Accounts, access control, persistence, history and retention."""

import datetime as dt
import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select, update

from .conftest import PASSWORD, register


def xlsx():
    wb = Workbook()
    ws = wb.active
    ws.append(["Month", "Revenue"])
    for i, v in enumerate([10, 12, 13, 15]):
        ws.append([f"M{i + 1}", v])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def second_client():
    from app import main
    return TestClient(main.app)


def db_session():
    from app.db.session import session_factory
    return session_factory()()


def stored_blobs() -> set[str]:
    """Upload ids whose original bytes are in the database."""
    from app.db.models import UploadBlob
    with db_session() as db:
        return {i.hex for i in db.scalars(select(UploadBlob.upload_id))}


# ---------------------------------------------------------------- authentication

def test_protected_endpoints_require_sign_in(anon_client):
    for method, path in [("get", "/api/uploads"), ("get", "/api/projects"), ("get", "/api/saved"), ("get", "/api/activity"),
                         ("get", "/api/dashboard/sample"), ("get", "/api/ai/status"), ("get", "/api/account/export")]:
        assert getattr(anon_client, method)(path).status_code == 401, path
    r = anon_client.post("/api/finance/appraisal", json={"cash_flows": [-1, 2], "discount_rate": 0.1})
    assert r.status_code == 401
    assert anon_client.get("/api/health").status_code == 200


def test_register_validation(anon_client):
    bad = [("not-an-email", PASSWORD), ("a@example.com", "short"), ("a@example.com", "password123"), ("alice@example.com", "alice-secret-1")]
    for email, pw in bad:
        r = anon_client.post("/api/auth/register", json={"email": email, "password": pw, "display_name": "A"})
        assert r.status_code == 422, (email, pw)
    register(anon_client, "Bob@Example.com")
    other = second_client()
    r = other.post("/api/auth/register", json={"email": "bob@example.COM ", "password": PASSWORD, "display_name": "B"})
    assert r.status_code == 409


def test_session_cookie_is_httponly_and_token_hashed(anon_client):
    r = anon_client.post("/api/auth/register", json={"email": "c@example.com", "password": PASSWORD, "display_name": "C"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "fis_session=" in cookie
    token = anon_client.cookies.get("fis_session")
    from app.db.models import AuthSession, User
    with db_session() as db:
        stored = db.scalars(select(AuthSession.token_hash)).all()
        user = db.scalar(select(User))
    assert token not in stored and len(stored[0]) == 64
    assert user.password_hash.startswith("scrypt$") and PASSWORD not in user.password_hash


def test_login_logout_and_generic_errors(anon_client):
    register(anon_client)
    anon_client.post("/api/auth/logout")
    assert anon_client.get("/api/auth/me").status_code == 401
    wrong = anon_client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong-password-1"})
    unknown = anon_client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-1"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]
    ok = anon_client.post("/api/auth/login", json={"email": "ALICE@example.com", "password": PASSWORD})
    assert ok.status_code == 200 and anon_client.get("/api/auth/me").json()["email"] == "alice@example.com"


def test_logged_out_token_cannot_be_replayed(anon_client):
    register(anon_client)
    token = anon_client.cookies.get("fis_session")
    anon_client.post("/api/auth/logout")
    replay = second_client()
    replay.cookies.set("fis_session", token)
    assert replay.get("/api/auth/me").status_code == 401


def test_expired_session_rejected(client):
    from app.db.models import AuthSession
    with db_session() as db:
        db.execute(update(AuthSession).values(expires_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)))
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_login_rate_limited(anon_client):
    register(anon_client)
    anon_client.post("/api/auth/logout")
    codes = [anon_client.post("/api/auth/login", json={"email": "alice@example.com", "password": "nope-nope-nope"}).status_code
             for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[-1] == 429
    # even the right password is refused while limited
    assert anon_client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 429


def test_change_password_signs_out_other_devices(client):
    other = second_client()
    assert other.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 200
    assert len(client.get("/api/auth/sessions").json()["sessions"]) == 2
    assert client.post("/api/auth/change-password", json={"current_password": "bad-password-1", "new_password": "another-good-pass-7"}).status_code == 403
    assert client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "another-good-pass-7"}).status_code == 200
    assert other.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": "another-good-pass-7"}).status_code == 200


def test_cross_site_post_blocked(client):
    r = client.post("/api/projects", json={"name": "X"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["type"] == "csrf"
    ok = client.post("/api/projects", json={"name": "X"}, headers={"Origin": "http://localhost:5173"})
    assert ok.status_code == 201
    # the website may start on another port if 5173 is busy; still this computer, so allowed
    other_port = client.post("/api/projects", json={"name": "Y"}, headers={"Origin": "http://localhost:5174"})
    assert other_port.status_code == 201
    for bad in ("http://localhost.evil.example", "https://localhost:5174", "http://127.0.0.1.nip.io"):
        assert client.post("/api/projects", json={"name": "Z"}, headers={"Origin": bad}).status_code == 403


def test_other_local_ports_blocked_in_production(monkeypatch):
    from app.config import Settings

    dev = Settings(fis_env="development")
    prod = Settings(fis_env="production", fis_cors_origins="https://studio.example")
    assert dev.origin_allowed("http://localhost:5174") and dev.origin_allowed("http://127.0.0.1:3000")
    assert not prod.origin_allowed("http://localhost:5174")
    assert prod.origin_allowed("https://studio.example")


def test_registration_can_be_disabled(anon_client, monkeypatch):
    monkeypatch.setenv("FIS_ALLOW_REGISTRATION", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    r = anon_client.post("/api/auth/register", json={"email": "z@example.com", "password": PASSWORD, "display_name": "Z"})
    assert r.status_code == 403


def test_production_refuses_dev_database_password(monkeypatch, database_url):
    monkeypatch.setenv("FIS_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://fis_app:fis_dev_password@localhost:5432/x")
    from app.config import get_settings
    get_settings.cache_clear()
    assert get_settings().cookie_secure is True
    from app import main
    with pytest.raises(RuntimeError, match="development database password"):
        with TestClient(main.app):
            pass
    get_settings.cache_clear()


# ---------------------------------------------------------------- isolation between users

def test_users_cannot_see_or_change_each_others_data(client):
    p = client.post("/api/projects", json={"name": "Alice FY26"}).json()
    up = client.post("/api/uploads", files=[("files", ("a.xlsx", xlsx()))], data={"project_id": p["id"]}).json()["results"][0]["upload"]
    item = client.post("/api/saved", json={"kind": "dcf", "name": "Alice DCF", "project_id": p["id"], "data": {"wacc": 0.1}}).json()

    bob = second_client()
    register(bob, "bob@example.com", name="Bob")
    assert bob.get(f"/api/uploads/{up['id']}").status_code == 404
    assert bob.delete(f"/api/uploads/{up['id']}").status_code == 404
    assert bob.get(f"/api/projects/{p['id']}").status_code == 404
    assert bob.patch(f"/api/projects/{p['id']}", json={"name": "pwned"}).status_code == 404
    assert bob.delete(f"/api/projects/{p['id']}").status_code == 404
    assert bob.get(f"/api/projects/{p['id']}/export").status_code == 404
    assert bob.get(f"/api/saved/{item['id']}").status_code == 404
    assert bob.get(f"/api/saved/{item['id']}/versions/1").status_code == 404
    assert bob.put(f"/api/saved/{item['id']}", json={"data": {"x": 1}}).status_code == 404
    assert bob.delete(f"/api/saved/{item['id']}").status_code == 404
    # cannot upload or save into someone else's project
    r = bob.post("/api/uploads", files=[("files", ("b.xlsx", xlsx()))], data={"project_id": p["id"]})
    assert r.status_code == 404
    assert bob.post("/api/saved", json={"kind": "dcf", "name": "x", "project_id": p["id"], "data": {}}).status_code == 404
    assert bob.get(f"/api/uploads?project_id={p['id']}").status_code == 404
    # lists only show the caller's own data
    assert bob.get("/api/uploads").json()["uploads"] == []
    assert bob.get("/api/uploads/series").json()["series"] == []
    assert bob.get("/api/projects").json()["projects"] == []
    assert bob.get("/api/saved").json()["items"] == []
    assert all(a["action"].startswith("account.") for a in bob.get("/api/activity").json()["activity"])
    export = bob.get("/api/account/export").json()
    assert export["projects"] == [] and export["uploads"] == [] and export["saved_items"] == []
    # Alice still has everything
    assert client.get(f"/api/uploads/{up['id']}").status_code == 200
    assert client.get(f"/api/projects/{p['id']}").json()["name"] == "Alice FY26"


# ---------------------------------------------------------------- projects, saved models, history

def test_project_crud_and_delete_cascade(client):
    p = client.post("/api/projects", json={"name": "Valuation", "description": "DCF of X"}).json()
    assert client.post("/api/projects", json={"name": "Valuation"}).status_code == 409
    up = client.post("/api/uploads", files=[("files", ("a.xlsx", xlsx()))], data={"project_id": p["id"]}).json()["results"][0]["upload"]
    client.post("/api/saved", json={"kind": "budget", "name": "Budget v1", "project_id": p["id"], "data": {"lines": []}})
    detail = client.get(f"/api/projects/{p['id']}").json()
    assert detail["uploads"] == 1 and detail["saved_items"] == 1 and detail["upload_list"][0]["id"] == up["id"]
    r = client.patch(f"/api/projects/{p['id']}", json={"name": "Valuation 2026", "archived": True}).json()
    assert r["name"] == "Valuation 2026" and r["archived"] is True
    assert stored_blobs() == {up["id"]}
    assert client.delete(f"/api/projects/{p['id']}").json()["uploads_deleted"] == 1
    assert client.get(f"/api/uploads/{up['id']}").status_code == 404
    assert client.get("/api/saved").json()["items"] == []
    assert stored_blobs() == set()


def test_saved_item_versions(client):
    item = client.post("/api/saved", json={"kind": "dcf", "name": "Base", "data": {"wacc": 0.10}, "note": "first"}).json()
    assert item["latest_version"] == 1
    client.put(f"/api/saved/{item['id']}", json={"data": {"wacc": 0.11}, "note": "raised WACC"})
    full = client.get(f"/api/saved/{item['id']}").json()
    assert full["latest_version"] == 2 and full["data"] == {"wacc": 0.11}
    assert [v["version"] for v in full["versions"]] == [2, 1]
    assert client.get(f"/api/saved/{item['id']}/versions/1").json()["data"] == {"wacc": 0.10}
    assert client.get(f"/api/saved/{item['id']}/versions/9").status_code == 404
    assert client.patch(f"/api/saved/{item['id']}", json={"name": "Base case"}).json()["name"] == "Base case"
    assert [i["name"] for i in client.get("/api/saved?kind=dcf").json()["items"]] == ["Base case"]
    assert client.get("/api/saved?kind=budget").json()["items"] == []
    big = {"x": "a" * (2 * 1024 * 1024 + 10)}
    assert client.put(f"/api/saved/{item['id']}", json={"data": big}).status_code == 413
    assert client.delete(f"/api/saved/{item['id']}").status_code == 200


def test_activity_history(client):
    p = client.post("/api/projects", json={"name": "P"}).json()
    client.post("/api/uploads", files=[("files", ("a.xlsx", xlsx()))], data={"project_id": p["id"]})
    client.post("/api/saved", json={"kind": "dcf", "name": "D", "project_id": p["id"], "data": {}})
    actions = [a["action"] for a in client.get(f"/api/activity?project_id={p['id']}").json()["activity"]]
    assert actions == ["model.saved", "upload.created", "project.created"]
    labels = [a["label"] for a in client.get("/api/activity").json()["activity"]]
    assert "Account created" in labels


def test_upload_rejected_for_bad_project_id(client):
    r = client.post("/api/uploads", files=[("files", ("a.xlsx", xlsx()))], data={"project_id": "not-a-uuid"})
    assert r.status_code == 404


# ---------------------------------------------------------------- retention, export, deletion

def test_retention_purge_removes_expired_uploads_and_files(client):
    up = client.post("/api/uploads", files=[("files", ("a.xlsx", xlsx()))]).json()["results"][0]["upload"]
    fresh = client.post("/api/uploads", files=[("files", ("b.xlsx", xlsx()))]).json()["results"][0]["upload"]
    exp = dt.datetime.fromisoformat(up["expires_at"])
    assert 89 <= (exp - dt.datetime.now(dt.timezone.utc)).days <= 90
    from app.config import get_settings
    from app.db.models import Upload
    from app.files.service import purge_expired
    import uuid
    with db_session() as db:
        db.execute(update(Upload).where(Upload.id == uuid.UUID(up["id"])).values(expires_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)))
        db.commit()
        assert purge_expired(db, get_settings())["uploads_deleted"] == 1
    assert client.get(f"/api/uploads/{up['id']}").status_code == 404
    assert client.get(f"/api/uploads/{fresh['id']}").status_code == 200
    assert stored_blobs() == {fresh["id"]}
    assert "upload.expired" in [a["action"] for a in client.get("/api/activity").json()["activity"]]


def test_export_contains_data_but_no_secrets(client):
    client.post("/api/projects", json={"name": "P"})
    client.post("/api/saved", json={"kind": "ratios", "name": "R", "data": {"revenue": 5}})
    raw = client.get("/api/account/export").text
    data = client.get("/api/account/export").json()
    assert data["account"]["email"] == "alice@example.com"
    assert len(data["projects"]) == 1 and data["saved_items"][0]["versions"][0]["data"] == {"revenue": 5}
    assert "password" not in raw and "scrypt" not in raw and "token" not in raw


def test_delete_all_data_keeps_account(client):
    client.post("/api/projects", json={"name": "P"})
    client.post("/api/uploads", files=[("files", ("a.xlsx", xlsx()))])
    assert client.post("/api/account/delete-data", json={"password": "wrong-pass-123"}).status_code == 403
    assert client.post("/api/account/delete-data", json={"password": PASSWORD}).json()["deleted_uploads"] == 1
    assert client.get("/api/projects").json()["projects"] == [] and client.get("/api/uploads").json()["uploads"] == []
    assert stored_blobs() == set()
    assert client.get("/api/auth/me").status_code == 200


def test_delete_account(client):
    client.post("/api/uploads", files=[("files", ("a.xlsx", xlsx()))])
    client.post("/api/saved", json={"kind": "dcf", "name": "D", "data": {}})
    assert client.post("/api/account/delete", json={"password": "wrong-pass-123"}).status_code == 403
    assert client.post("/api/account/delete", json={"password": PASSWORD}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 401
    assert stored_blobs() == set()
    from app.db.models import SavedItem, Upload, User
    with db_session() as db:
        assert db.scalar(select(User)) is None and db.scalar(select(Upload)) is None and db.scalar(select(SavedItem)) is None


def test_move_upload_between_own_projects_only(client):
    a = client.post("/api/projects", json={"name": "A"}).json()
    b = client.post("/api/projects", json={"name": "B"}).json()
    up = client.post("/api/uploads", files=[("files", ("a.xlsx", xlsx()))], data={"project_id": a["id"]}).json()["results"][0]["upload"]
    r = client.patch(f"/api/uploads/{up['id']}", json={"project_id": b["id"]})
    assert r.status_code == 200 and r.json()["project_id"] == b["id"]
    assert [u["id"] for u in client.get(f"/api/uploads?project_id={b['id']}").json()["uploads"]] == [up["id"]]
    assert client.patch(f"/api/uploads/{up['id']}", json={"project_id": None}).json()["project_id"] is None
    mallory = second_client()
    register(mallory, "mallory@example.com", name="M")
    mp = mallory.post("/api/projects", json={"name": "M"}).json()
    assert mallory.patch(f"/api/uploads/{up['id']}", json={"project_id": mp["id"]}).status_code == 404
    assert client.patch(f"/api/uploads/{up['id']}", json={"project_id": mp["id"]}).status_code == 404


def test_local_sqlite_url_is_anchored_to_backend_folder(monkeypatch):
    from app.config import BACKEND_DIR, Settings
    s = Settings(database_url="sqlite:///storage/finance_studio.db")
    assert s.is_sqlite
    assert s.resolved_database_url == "sqlite:///" + (BACKEND_DIR / "storage" / "finance_studio.db").as_posix()
    pg = Settings(database_url="postgresql+psycopg://u:p@h/db")
    assert pg.resolved_database_url == "postgresql+psycopg://u:p@h/db" and not pg.is_sqlite


def test_production_refuses_sqlite(monkeypatch):
    monkeypatch.setenv("FIS_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///storage/x.db")
    from app.config import get_settings
    get_settings.cache_clear()
    from app import main
    with pytest.raises(RuntimeError, match="SQLite is for local"):
        with TestClient(main.app):
            pass
    get_settings.cache_clear()


def test_legacy_disk_copies_are_removed_once_in_database(client, tmp_path):
    """Pre-0.10 uploads lived on disk; housekeeping deletes a disk copy once its bytes are in the
    database, and orphans whose upload is gone, but leaves files it did not write."""
    from app.config import get_settings
    from app.files.service import purge_expired
    up = client.post("/api/uploads", files=[("files", ("a.xlsx", xlsx()))]).json()["results"][0]["upload"]
    folder = tmp_path / "uploads"
    folder.mkdir()
    (folder / f"{up['id']}.bin").write_bytes(b"old copy")
    (folder / f"{'0' * 32}.bin").write_bytes(b"orphan")
    (folder / "notes.bin").write_bytes(b"not ours")
    with db_session() as db:
        assert purge_expired(db, get_settings())["legacy_files_deleted"] == 2
    assert sorted(p.name for p in folder.iterdir()) == ["notes.bin"]
    assert stored_blobs() == {up["id"]}
