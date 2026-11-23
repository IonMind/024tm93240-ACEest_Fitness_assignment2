import csv
import io
from contextlib import closing

import pytest

from app import database_connection


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