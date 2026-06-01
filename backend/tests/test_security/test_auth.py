"""
Tests for the API Key authentication dependency.

Uses an isolated mini FastAPI app so we can test ``require_api_key``
in isolation without being coupled to the real router structure.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from security.auth import require_api_key

# ── Isolated test app ────────────────────────────────────────────────

_test_app = FastAPI()


@_test_app.get("/protected")
async def _protected_route(_auth: None = Depends(require_api_key)):
    """A single protected endpoint for testing auth behaviour."""
    return {"message": "authenticated"}


_protected_client = TestClient(_test_app)


# ═══════════════════════════════════════════════════════════════════════
# Dev mode (empty API key) — auth should be a no-op
# ═══════════════════════════════════════════════════════════════════════


class TestDevModeNoAuth:
    """When ``settings.api_key`` is empty, all requests pass through."""

    @pytest.fixture(autouse=True)
    def _dev_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("config.settings.api_key", "")

    def test_missing_key_allowed(self) -> None:
        """No key at all → 200."""
        resp = _protected_client.get("/protected")
        assert resp.status_code == 200
        assert resp.json() == {"message": "authenticated"}

    def test_with_any_key_allowed(self) -> None:
        """Even a bogus key → 200 (dev mode ignores auth)."""
        resp = _protected_client.get(
            "/protected", headers={"X-API-Key": "whatever"}
        )
        assert resp.status_code == 200

    def test_dev_mode_query_param_ignored(self) -> None:
        """Query param key also passes in dev mode."""
        resp = _protected_client.get("/protected?api_key=anything")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# Auth enabled — API key must match
# ═══════════════════════════════════════════════════════════════════════


class TestAuthEnabled:
    """When ``settings.api_key`` is set, the dependency enforces it."""

    VALID_KEY = "test-key-123"

    @pytest.fixture(autouse=True)
    def _enable_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("config.settings.api_key", self.VALID_KEY)

    def test_missing_key_returns_403(self) -> None:
        """No ``X-API-Key`` header → 403."""
        resp = _protected_client.get("/protected")
        assert resp.status_code == 403
        detail = resp.json().get("detail", "")
        assert "Missing API key" in detail

    def test_wrong_key_header_returns_403(self) -> None:
        """Wrong key in header → 403."""
        resp = _protected_client.get(
            "/protected", headers={"X-API-Key": "wrong-key"}
        )
        assert resp.status_code == 403
        detail = resp.json().get("detail", "")
        assert "Invalid API key" in detail

    def test_wrong_key_query_param_returns_403(self) -> None:
        """Wrong key as query param → 403."""
        resp = _protected_client.get("/protected?api_key=wrong-key")
        assert resp.status_code == 403

    def test_correct_key_header_passes(self) -> None:
        """Correct key in ``X-API-Key`` header → 200."""
        resp = _protected_client.get(
            "/protected", headers={"X-API-Key": self.VALID_KEY}
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "authenticated"}

    def test_correct_key_query_param_passes(self) -> None:
        """Correct key as ``?api_key=`` query parameter → 200."""
        resp = _protected_client.get(
            f"/protected?api_key={self.VALID_KEY}"
        )
        assert resp.status_code == 200

    def test_header_takes_precedence_over_query(self) -> None:
        """When both header and query are present, header is used.

        If header is valid and query is wrong → pass.
        If header is wrong and query is valid → fail.
        """
        # Valid header, invalid query → pass
        resp = _protected_client.get(
            "/protected?api_key=wrong-key",
            headers={"X-API-Key": self.VALID_KEY},
        )
        assert resp.status_code == 200

        # Invalid header, valid query → fail (header checked first)
        resp = _protected_client.get(
            "/protected?api_key=test-key-123",
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 403

    def test_empty_key_header_returns_403(self) -> None:
        """Empty key in header → 403."""
        resp = _protected_client.get(
            "/protected", headers={"X-API-Key": ""}
        )
        assert resp.status_code == 403
