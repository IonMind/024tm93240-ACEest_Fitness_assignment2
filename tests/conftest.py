import pytest

from app import app as flask_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ACEEST_ADMIN_USERNAME", "test-admin")
    monkeypatch.setenv("ACEEST_ADMIN_PASSWORD", "test-password")
    monkeypatch.setitem(flask_app.config, "TESTING", True)
    monkeypatch.setitem(flask_app.config, "SECRET_KEY", "test-secret")
    monkeypatch.setitem(flask_app.config, "DATABASE", str(tmp_path / "test.db"))
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def authenticated_client(client):
    response = client.post(
        "/login", data={"username": "test-admin", "password": "test-password"}
    )
    assert response.status_code == 302
    return client


@pytest.fixture
def saved_client(authenticated_client):
    response = authenticated_client.post(
        "/client",
        data={
            "name": "Alex",
            "age": "30",
            "height": "175",
            "weight": "70",
            "program": "Beginner (BG)",
        },
    )
    assert response.status_code == 200
    return authenticated_client