"""
Tests for the ``/health`` readiness endpoint.

The health check is an unauthenticated route that simply returns
``{\"status\": \"ok\"}``.  These tests use the ``test_client`` fixture
from ``conftest.py`` (which points to the real FastAPI ``app``).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """``/health`` should always return 200 with status ok."""

    def test_health_returns_200_and_status_ok(
        self, test_client: TestClient
    ) -> None:
        """GET /health → 200 {\"status\": \"ok\"}."""
        resp = test_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_method_not_allowed(self, test_client: TestClient) -> None:
        """POST /health should not be allowed (GET only)."""
        resp = test_client.post("/health")
        assert resp.status_code in (405, 404)

    def test_health_content_type(self, test_client: TestClient) -> None:
        """Response content-type should be JSON."""
        resp = test_client.get("/health")
        assert resp.headers.get("content-type", "").startswith("application/json")
