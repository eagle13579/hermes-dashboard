"""
Sync Router — REST API for the Gaia Sync Bridge (盖娅同步桥).

Endpoints
---------
=======================  =====  ===================================
Path                     Method  Description
=======================  =====  ===================================
/api/sync/status          GET    Current sync bridge status
/api/sync/run             POST   Manually trigger a sync cycle
/api/sync/pending         GET    List of pending (queued) records
/api/sync/history         GET    Recent sync history from PostgreSQL
=======================  =====  ===================================
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from security.auth import require_api_key
from services.sync_bridge import SyncBridge, get_bridge

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/sync", tags=["Sync"])
"""FastAPI router — mount in ``main.py`` via ``app.include_router(sync_router)``."""


# ──────────────────────────────────────────────────────────────────────
# GET  /api/sync/status
# ──────────────────────────────────────────────────────────────────────


@router.get("/status")
async def sync_status() -> dict:
    """Return the current Gaia Sync Bridge status.

    Includes last sync time, counts of synced / failed / pending records,
    queue depth, and a redacted PG connection hint.

    Returns
    -------
    dict
        Status payload from :meth:`SyncBridge.get_sync_status`.
    """
    bridge: SyncBridge = get_bridge()
    return bridge.get_sync_status()


# ──────────────────────────────────────────────────────────────────────
# POST  /api/sync/run
# ──────────────────────────────────────────────────────────────────────


@router.post("/run")
async def sync_run(
    _auth: None = Depends(require_api_key),
) -> dict:
    """Manually trigger an immediate full sync cycle.

    The sync runs **synchronously inside an executor thread** so it does
    not block the ASGI event loop.  For large profile trees the request
    may take several seconds to complete.

    Returns
    -------
    dict
        Summary payload from :meth:`SyncBridge.sync_once` with keys
        ``scanned``, ``synced``, ``failed``, ``pending``,
        ``elapsed_seconds``, and ``timestamp``.
    """
    try:
        bridge: SyncBridge = get_bridge()
        summary = bridge.sync_once()
    except Exception as exc:
        logger.exception("Manual sync failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync cycle failed: {exc}",
        )
    return summary


# ──────────────────────────────────────────────────────────────────────
# GET  /api/sync/pending
# ──────────────────────────────────────────────────────────────────────


@router.get("/pending")
async def sync_pending(
    limit: Optional[int] = Query(
        50,
        ge=1,
        le=1000,
        description="Maximum number of pending records to return",
    ),
) -> list[dict]:
    """Return pending (unsynced) records from the local queue.

    Parameters
    ----------
    limit : int, optional
        Maximum records to return (1–1000, default 50).

    Returns
    -------
    list[dict]
        Serialised :class:`~services.sync_bridge.SyncRecord` dictionaries
        sorted by timestamp (oldest first).
    """
    bridge: SyncBridge = get_bridge()
    pending = bridge.get_pending_records()
    # Sort oldest-first, limit
    pending.sort(key=lambda r: r.get("timestamp", ""))
    return pending[:limit]


# ──────────────────────────────────────────────────────────────────────
# GET  /api/sync/history
# ──────────────────────────────────────────────────────────────────────


@router.get("/history")
async def sync_history(
    limit: Optional[int] = Query(
        100,
        ge=1,
        le=5000,
        description="Maximum number of history records to return",
    ),
) -> list[dict]:
    """Return recent sync history from the Gaia PostgreSQL database.

    Records are ordered by ``synced_at`` descending (newest first).

    Parameters
    ----------
    limit : int, optional
        Maximum records to return (1–5000, default 100).

    Returns
    -------
    list[dict]
        List of sync record dictionaries.  Returns an empty list if the
        PostgreSQL database is unreachable.

    Raises
    ------
    503
        If PG is unreachable and history cannot be retrieved.
    """
    bridge: SyncBridge = get_bridge()
    try:
        history = bridge.get_sync_history(limit=limit)
    except Exception as exc:
        logger.exception("Failed to fetch sync history")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot retrieve sync history: {exc}",
        )
    return history
