"""
Authentication & Authorisation — API Key (with JWT upgrade path).

Design
------
* Uses FastAPI ``Depends`` injection — no middleware on every router.
* API key is passed via ``X-API-Key`` header.
* Falls back to ``api_key`` query parameter for WebSocket/SSE use-cases.
* The key is validated against ``settings.api_key`` (loaded from ``.env``).
* If ``api_key`` is empty/None the dependency becomes a no-op (development).

JWT Upgrade Path
----------------
When a JWT upgrade is required:
1. Add a ``/api/auth/login`` endpoint that returns a signed JWT.
2. Replace ``require_api_key`` with a ``require_jwt`` dependency.
3. Both can co-exist via a union type — the dependency checks header
   format to decide which strategy to apply.

Usage
-----
.. code-block:: python

    from security import require_api_key
    from fastapi import Depends

    @router.post("/resource")
    async def create(payload: Model, _auth: None = Depends(require_api_key)):
        ...
"""

from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import APIKeyHeader

from config import settings

logger = logging.getLogger(__name__)

# ── API Key header scheme ──────────────────────────────────────────────

API_KEY_HEADER = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,  # We raise our own error for control
    description="API key for authentication. Obtain from the admin.",
)

# ── Dependency ─────────────────────────────────────────────────────────


async def require_api_key(
    header_key: Annotated[str | None, Depends(API_KEY_HEADER)],
    query_key: Annotated[
        str | None,
        Query(
            alias="api_key",
            description="API key as query parameter (alternative to header)",
        ),
    ] = None,
) -> None:
    """FastAPI dependency that validates the API key.

    Checks the ``X-API-Key`` header first, then falls back to the
    ``api_key`` query parameter.

    When ``settings.api_key`` is empty (development mode) this check
    is **skipped** — all requests pass through.

    Raises
    ------
    HTTPException(403)
        If the provided key does not match the configured key.
    """
    # Skip auth when no API key is configured (dev mode)
    if not settings.api_key:
        return None

    key = header_key or query_key

    if not key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing API key. Provide via X-API-Key header or ?api_key=...",
        )

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(key, settings.api_key):
        logger.warning("Rejected request with invalid API key (len=%d)", len(key))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    return None
