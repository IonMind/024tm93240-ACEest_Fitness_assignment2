import csv
import io
import os
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest

from app import database_connection


def test_database_connection_closes_and_rolls_back(app):
    with database_connection() as connection:
        connection.execute("CREATE TABLE example (value TEXT)")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")

    with pytest.raises(ValueError):
        with database_connection() as connection:
            connection.execute("INSERT INTO example VALUES ('temporary')")
            raise ValueError("rollback")

    with database_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM example").fetchone()[0] == 0


def test_health_and_readiness(client, app, tmp_path):
    assert client.get("/healthz").get_json() == {"status": "ok"}
    assert client.get("/readyz").get_json() == {"status": "ready"}
    app.config["DATABASE"] = str(tmp_path / "missing" / "test.db")
    assert client.get("/readyz").status_code == 503
    assert client.get("/healthz").status_code == 200


def test_existing_administrator_is_not_recreated(client, monkeypatch):
    assert client.get("/readyz").status_code == 200
    monkeypatch.setenv("ACEEST_ADMIN_USERNAME", "another-admin")
    assert client.get("/readyz").status_code == 200
    with database_connection() as connection:
        usernames = [row[0] for row in connection.execute("SELECT username FROM users")]
    assert usernames == ["test-admin"]


def test_production_requires_explicit_safe_configuration(tmp_path):
    environment = os.environ.copy()
    for name in ("ACEEST_SECRET_KEY", "ACEEST_DB_PATH", "ACEEST_ADMIN_USERNAME", "ACEEST_ADMIN_PASSWORD"):
        environment.pop(name, None)
    environment["ACEEST_ENV"] = "production"
    command = [sys.executable, "-c", "import app"]
    missing = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert missing.returncode != 0
    assert "Missing production configuration" in missing.stderr

    environment.update(
        ACEEST_SECRET_KEY="test-production-secret",
        ACEEST_DB_PATH=str(tmp_path / "production.db"),
        ACEEST_ADMIN_USERNAME="test-admin",
        ACEEST_ADMIN_PASSWORD="admin",
    )
    unsafe = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert unsafe.returncode != 0
    assert "must not use development defaults" in unsafe.stderr

    environment["ACEEST_ADMIN_PASSWORD"] = "test-password"
    configured = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert configured.returncode == 0, configured.stderr


def test_protected_route_redirects_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_login_rejects_invalid_password(client):
    response = client.post(
        "/login", data={"username": "test-admin", "password": "incorrect"}
    )
    assert response.status_code == 200
    assert b"Invalid username or password." in response.data
    assert client.get("/").status_code == 302


def test_login_and_logout(authenticated_client):
    assert authenticated_client.get("/").status_code == 200
    assert authenticated_client.post("/logout").status_code == 302
    assert authenticated_client.get("/").status_code == 302


def test_client_creation_and_loading(authenticated_client):
    response = authenticated_client.post(
        "/client",
        data={"name": "Alex", "age": "30", "weight": "70", "program": "Beginner (BG)"},
    )
    assert response.status_code == 200
    assert b"Client data saved." in response.data
    response = authenticated_client.post("/client/load", data={"name": "Alex"})
    assert response.status_code == 200
    assert b"Client loaded." in response.data
    assert b"Alex" in response.data


def test_client_requires_name_and_program(authenticated_client):
    response = authenticated_client.post("/client", data={"name": ""})
    assert response.status_code == 400
    assert b"Client name and program are required." in response.data


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"name": "Alex", "program": "Unknown"}, b"Select a valid program."),
        (
            {"name": "Alex", "program": "Beginner (BG)", "membership_expiry": "bad-date"},
            b"Membership expiry must be a valid date.",
        ),
    ],
)
def test_client_validation(authenticated_client, data, message):
    response = authenticated_client.post("/client", data=data)
    assert response.status_code == 400
    assert message in response.data


def test_missing_client_returns_not_found(authenticated_client):
    assert authenticated_client.post("/client/load", data={"name": "Missing"}).status_code == 404
    assert authenticated_client.get("/client/Missing/report.pdf").status_code == 404


def test_progress_workout_and_metrics_are_recorded(saved_client, app):
    assert saved_client.post("/progress", data={"name": "Alex", "adherence": "80"}).status_code == 200
    assert saved_client.post(
        "/workouts",
        data={"client_name": "Alex", "date": "2026-01-01", "workout_type": "Strength", "exercise_name": "Squat", "sets": "3", "reps": "8"},
    ).status_code == 200
    assert saved_client.post(
        "/metrics", data={"client_name": "Alex", "date": "2026-01-01", "weight": "68"}
    ).status_code == 200
    with closing(database_connection()) as connection:
        assert connection.execute("SELECT adherence FROM progress").fetchone()[0] == 80
        assert connection.execute("SELECT name FROM exercises").fetchone()[0] == "Squat"
        assert connection.execute("SELECT weight FROM clients WHERE name = ?", ("Alex",)).fetchone()[0] == 68


def test_bmi_and_exports(saved_client):
    bmi = saved_client.get("/client/Alex/bmi")
    assert bmi.status_code == 200
    assert b"22.9" in bmi.data
    response = saved_client.get("/clients/export.csv")
    assert response.mimetype == "text/csv"
    rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
    assert rows[0]["Name"] == "Alex"
    assert rows[0]["Program"] == "Beginner (BG)"
    pdf = saved_client.get("/client/Alex/report.pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF-")


def test_program_generation_and_membership(saved_client):
    response = saved_client.post("/client/Alex/generate-program", data={"experience": "beginner"})
    assert response.status_code == 200
    assert b"Workout program generated for Alex." in response.data
    assert saved_client.post("/client/Alex/generate-program", data={"experience": "invalid"}).status_code == 400
    assert saved_client.post("/client/Alex/generate-random-program").status_code == 200
    assert saved_client.get("/client/Alex/membership").status_code == 200