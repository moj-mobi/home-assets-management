import re

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Base
from app.main import create_app
from app.models import LocalUser
from app.security import hash_password

TEST_USERNAME = "local-test-user"
TEST_PASSWORD = "Correct horse battery staple!"


def csrf_from(response):
    return re.search(r'name="csrf_token" value="([^"]+)"', response.text).group(1)


@pytest.fixture
def app_client(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        session_secret="test-session-secret-that-is-long-enough-12345",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as db:
        db.add(LocalUser(username=TEST_USERNAME, password_hash=hash_password(TEST_PASSWORD)))
        db.commit()
    with TestClient(app) as client:
        yield app, client


def login(client, password=TEST_PASSWORD, follow=False):
    page = client.get("/login")
    return client.post("/login", data={
        "username": TEST_USERNAME, "password": password,
        "csrf_token": csrf_from(page), "next_path": "/",
    }, follow_redirects=follow)