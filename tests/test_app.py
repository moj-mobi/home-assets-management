import logging
import sqlite3

from alembic import command
from alembic.config import Config

from conftest import TEST_PASSWORD, csrf_from, login


def test_existing_database_migrates_without_losing_asset(tmp_path, monkeypatch):
    db_path = tmp_path / "existing.db"
    monkeypatch.setenv("HAM_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("HAM_DATA_DIR", str(tmp_path))
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "20260824_01")
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO assets (id,name) VALUES (1,'existing asset')")
        db.commit()
    command.upgrade(cfg, "head")
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT name FROM assets WHERE id=1").fetchone() == ("existing asset",)
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("20260824_02",)


def test_health_is_public_and_data_page_is_protected(app_client):
    _, client = app_client
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].startswith("/login")


def test_successful_and_failed_login_without_secret_logging(app_client, caplog):
    _, client = app_client
    with caplog.at_level(logging.INFO, logger="ham.security"):
        failed = login(client, "wrong-password")
        success = login(client)
    assert failed.status_code == 401
    assert success.status_code == 303
    assert client.get("/").status_code == 200
    logs = caplog.text
    assert TEST_PASSWORD not in logs and "wrong-password" not in logs
    assert "login_failed" in logs and "login_success" in logs


def test_logout_invalidates_session(app_client):
    _, client = app_client
    login(client)
    page = client.get("/")
    response = client.post("/logout", data={"csrf_token": csrf_from(page)}, follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 303


def test_account_locks_after_repeated_failures(app_client):
    _, client = app_client
    for _ in range(5):
        assert login(client, "wrong-password").status_code == 401
    assert login(client).status_code == 401


def test_mutation_requires_csrf_and_htmx_accepts_valid_token(app_client):
    _, client = app_client
    login(client)
    assert client.post("/assets", data={"name": "blocked"}).status_code == 403
    page = client.get("/")
    response = client.post("/assets", data={"name": "HTMX asset", "csrf_token": csrf_from(page)}, headers={"HX-Request": "true"})
    assert response.status_code == 200 and "HTMX asset" in response.text


def test_open_redirect_is_rejected(app_client):
    _, client = app_client
    page = client.get("/login?next=//evil.example")
    response = client.post("/login", data={"username": "local-test-user", "password": TEST_PASSWORD, "csrf_token": csrf_from(page), "next_path": "//evil.example"}, follow_redirects=False)
    assert response.headers["location"] == "/"

def test_untrusted_host_is_rejected(app_client):
    _, client = app_client
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/health", headers={"host": "127.0.0.1"}).status_code == 200

def test_favicon_does_not_invalidate_anonymous_login_csrf(app_client):
    _, client = app_client
    page = client.get("/login")
    token = csrf_from(page)
    assert client.get("/favicon.ico").status_code == 204
    response = client.post("/login", data={"username": "invalid-test-user", "password": "invalid-test-password", "csrf_token": token, "next_path": "/"})
    assert response.status_code == 401
    assert "Neveljavna zahteva" not in response.text