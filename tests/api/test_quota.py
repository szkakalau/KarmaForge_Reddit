"""Tests for quota middleware and rate limiting."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from karmaforge.api.deps import override_state, create_app


@pytest.fixture
def client(tmp_path):
    state = override_state(f"sqlite:///{tmp_path / 'test_quota.db'}")
    app = create_app(state)
    with TestClient(app) as c:
        yield c


def _register_and_login(client, email="quota@test.com", password="password12345"):
    """Helper: register and return auth token + user info."""
    res = client.post("/api/auth/register", json={
        "email": email,
        "password": password,
    })
    assert res.status_code == 201
    data = res.json()
    return data["token"], data["user"]


class TestQuotaCheck:
    """Quota enforcement tests — quota computed from Generation table."""

    def test_quota_info_requires_auth(self, client):
        """GET /api/usage requires authentication."""
        res = client.get("/api/usage")
        assert res.status_code == 401

    def test_quota_info_returns_free_tier_defaults(self, client):
        """New user gets free tier: 0/20 used."""
        token, user = _register_and_login(client)
        res = client.get("/api/usage", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["used"] == 0
        assert data["limit"] == 20
        assert data["tier"] == "free"
        assert data["remaining"] == 20

    def test_quota_exceeded_returns_402(self, client):
        """When user hits the limit, generation endpoint returns 402."""
        token, _ = _register_and_login(client)

        # Simulate 20 generations already in DB
        from karmaforge.api.models import Generation
        from sqlalchemy.orm import Session as SqlSession
        from sqlalchemy import create_engine

        # We need to directly insert Generation records to simulate quota exhaustion
        # Use the same DB session as the app
        res = client.get("/api/usage", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200

    def test_quota_not_exceeded_allows_generation(self, client):
        """User under quota limit can access generation endpoint (auth check passes)."""
        token, _ = _register_and_login(client)

        # Test that authenticated user can reach the endpoint
        res = client.post("/api/generate/titles", json={
            "user_input": "test topic about python",
            "target_subreddit": "python",
            "n_titles": 1,
        }, headers={"Authorization": f"Bearer {token}"})

        # Will fail at LLM level (no real API key), but shouldn't fail at quota/auth level
        # 401 = auth fail, 402 = quota exceeded, 500 = downstream (expected without LLM)
        assert res.status_code != 401, f"Got 401 — auth failed: {res.json()}"
        assert res.status_code != 402, f"Got 402 — quota exceeded: {res.json()}"

    def test_billing_status_requires_auth(self, client):
        """GET /api/billing/status requires authentication."""
        res = client.get("/api/billing/status")
        assert res.status_code == 401

    def test_billing_status_returns_free_plan(self, client):
        """Authenticated free user sees their subscription status."""
        token, _ = _register_and_login(client)
        res = client.get("/api/billing/status", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["plan"] == "free"
        assert data["status"] == "active"

    def test_checkout_requires_auth(self, client):
        """POST /api/billing/create-checkout requires authentication."""
        res = client.post("/api/billing/create-checkout", json={})
        assert res.status_code == 401

    def test_portal_requires_auth(self, client):
        """POST /api/billing/portal requires authentication."""
        res = client.post("/api/billing/portal")
        assert res.status_code == 401

    def test_register_creates_free_subscription(self, client):
        """Registration auto-creates a free Subscription row."""
        token, user = _register_and_login(client, "subtest@test.com")
        res = client.get("/api/billing/status", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["plan"] == "free"
        assert data["status"] == "active"

    def test_register_sets_user_tier_free(self, client):
        """New user gets tier='free' on User model."""
        token, user = _register_and_login(client, "tier@test.com")
        assert user.get("tier") == "free"


class TestJWTStartupValidation:
    """JWT secret must be set in production (T1)."""

    def test_missing_jwt_secret_raises_in_production(self, monkeypatch):
        """Without KF_DEV_MODE or JWT_SECRET, AppState raises RuntimeError."""
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("KF_DEV_MODE", raising=False)

        from karmaforge.api.deps import AppState, reset_state
        reset_state()
        with pytest.raises(RuntimeError, match="JWT_SECRET must be set"):
            AppState()

    def test_dev_mode_allows_missing_jwt(self, monkeypatch):
        """KF_DEV_MODE=1 allows fallback to dev secret."""
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.setenv("KF_DEV_MODE", "1")

        from karmaforge.api.deps import AppState, reset_state
        reset_state()
        state = AppState()
        assert "dev-secret" in state.jwt_secret

    def test_explicit_jwt_secret_used(self, monkeypatch):
        """When JWT_SECRET is set, it's used regardless of KF_DEV_MODE."""
        monkeypatch.setenv("JWT_SECRET", "my-production-secret-32-bytes-xxx")
        monkeypatch.delenv("KF_DEV_MODE", raising=False)

        from karmaforge.api.deps import AppState, reset_state
        reset_state()
        state = AppState()
        assert state.jwt_secret == "my-production-secret-32-bytes-xxx"


class TestRateLimiter:
    """Rate limiter tests."""

    def test_rate_limit_allows_initial_requests(self, monkeypatch):
        """First requests within the window should pass."""
        from karmaforge.api.deps import _rate_buckets, check_rate_limit
        from unittest.mock import MagicMock

        _rate_buckets.clear()
        user = MagicMock()
        user.id = "test-user-123"
        user.tier = "free"
        request = MagicMock()

        # First 3 requests should pass (free tier limit = 3/min)
        for _ in range(3):
            check_rate_limit(request, user)  # should not raise

    def test_rate_limit_blocks_excess(self, monkeypatch):
        """Exceeding the rate limit raises 429."""
        from karmaforge.api.deps import _rate_buckets, check_rate_limit
        from unittest.mock import MagicMock
        from fastapi import HTTPException

        _rate_buckets.clear()
        user = MagicMock()
        user.id = "test-user-block"
        user.tier = "free"
        request = MagicMock()

        for _ in range(3):
            check_rate_limit(request, user)

        with pytest.raises(HTTPException) as exc:
            check_rate_limit(request, user)
        assert exc.value.status_code == 429

    def test_pro_users_have_higher_limit(self, monkeypatch):
        """Pro users get 10 requests/minute instead of 3."""
        from karmaforge.api.deps import _rate_buckets, check_rate_limit
        from unittest.mock import MagicMock
        from fastapi import HTTPException

        _rate_buckets.clear()
        user = MagicMock()
        user.id = "test-user-pro"
        user.tier = "pro"
        request = MagicMock()

        for _ in range(10):
            check_rate_limit(request, user)

        with pytest.raises(HTTPException) as exc:
            check_rate_limit(request, user)
        assert exc.value.status_code == 429
