"""
pytest fixtures for Hermes Dashboard API tests.

Design
------
- Sets ``HERMES_HOME`` to a temporary directory **at module load time**
  so all service-level path resolution goes to temp space, not real data.
- Overrides ``settings.hermes_profile_path`` per-test via an autouse
  fixture, so no test writes to the real profile database.
- Leaves ``settings.api_key`` at its default (empty = dev mode) — auth
  tests are responsible for setting their own key via ``monkeypatch``
  or the ``auth_header`` fixture + ``_set_api_key``.
- Provides a ``test_client`` fixture bound to the real FastAPI app.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ── Temp HERMES_HOME (set before any downstream import touches config) ────
_HERMES_HOME_TMP = Path(tempfile.mkdtemp())
os.environ["HERMES_HOME"] = str(_HERMES_HOME_TMP)

# Safe to import now — config.settings will pick up the env var above
from config import settings  # noqa: E402
from main import app  # noqa: E402


# ── Helpers used by multiple test files ─────────────────────────────────


@pytest.fixture
def tmp_profile_dir() -> Path:
    """Create an isolated temporary profile data directory.

    Every call returns a **new** empty directory, so tests never share
    state through the filesystem.
    """
    return Path(tempfile.mkdtemp())


@pytest.fixture(autouse=True)
def _redirect_profile_path(tmp_profile_dir: Path) -> None:
    """Redirect ``settings.hermes_profile_path`` to a temp directory.

    This runs **before every test** (autouse) and restores the original
    value afterwards, guaranteeing zero side-effects on real data.
    """
    original = settings.hermes_profile_path
    settings.hermes_profile_path = tmp_profile_dir
    yield
    settings.hermes_profile_path = original


@pytest.fixture
def test_client() -> TestClient:
    """Return a :class:`TestClient` bound to the real application.

    Because ``settings.api_key`` is empty by default (dev mode), no
    authentication is required.  Auth tests should override this fixture
    or use the :func:`_set_api_key` helper.
    """
    return TestClient(app)


@pytest.fixture
def auth_header() -> dict[str, str]:
    """Return a valid ``X-API-Key`` header dict for use in requests.

    Combine with :func:`_set_api_key` to enable auth in a test class::

        @pytest.fixture(autouse=True)
        def _enable_auth(self, _set_api_key):
            pass

        def test_something(self, auth_header):
            client.get("/protected", headers=auth_header)
    """
    return {"X-API-Key": "test-key-123"}


# ── Auth helpers (used by test_security/test_auth.py) ──────────────────


@pytest.fixture
def _set_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Set ``config.settings.api_key`` to a known value.

    Yield the key so tests can use it in expectations::

        key = _set_api_key  # "test-key-123"
    """
    key = "test-key-123"
    monkeypatch.setattr("config.settings.api_key", key)
    return key


@pytest.fixture
def _clear_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set ``config.settings.api_key`` to empty string (dev mode)."""
    monkeypatch.setattr("config.settings.api_key", "")
