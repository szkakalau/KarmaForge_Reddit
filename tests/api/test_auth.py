"""Tests for auth endpoints."""

import pytest
from fastapi.testclient import TestClient

from karmaforge.api.deps import override_state, create_app


@pytest.fixture
def client(tmp_path):
    state = override_state(f"sqlite:///{tmp_path / 'test.db'}")
    app = create_app(state)
    with TestClient(app) as c:
        yield c


class TestAuth:
    def test_register(self, client):
        res = client.post("/api/auth/register", json={
            "email": "test@example.com",
            "password": "password12345",
        })
        assert res.status_code == 201
        data = res.json()
        assert "token" in data
        assert data["user"]["email"] == "test@example.com"

    def test_register_duplicate(self, client):
        client.post("/api/auth/register", json={
            "email": "dup@example.com",
            "password": "password12345",
        })
        res = client.post("/api/auth/register", json={
            "email": "dup@example.com",
            "password": "password12345",
        })
        assert res.status_code == 409

    def test_login(self, client):
        client.post("/api/auth/register", json={
            "email": "login@example.com",
            "password": "password12345",
        })
        res = client.post("/api/auth/login", json={
            "email": "login@example.com",
            "password": "password12345",
        })
        assert res.status_code == 200
        assert "token" in res.json()

    def test_login_invalid(self, client):
        res = client.post("/api/auth/login", json={
            "email": "nope@example.com",
            "password": "wrongpassword",
        })
        assert res.status_code == 401

    def test_health(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["service"] == "karmaforge-api"
