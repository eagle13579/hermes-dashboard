"""
Memory Replay Router — REST API for time-travel profile replay.

Endpoints
---------
====================================  =====  =====================================
Path                                  Method  Description
====================================  =====  =====================================
/api/replay/{profile}/timeline         GET    Build profile replay timeline
/api/replay/{profile}/at               GET    Snapshot at a given timestamp
/api/replay/{profile}/evolution        GET    Evolution summary (earliest→latest)
/api/replay/{profile}/compare         POST    Compare two timestamps
====================================  =====  =====================================
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from models.request import CompareTimeframesRequest
from security.auth import require_api_key
from services.memory_replay import (
    compare_timeframes,
    get_evolution_summary,
    get_replay_at,
    get_replay_timeline,
)

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/replay", tags=["Memory Replay"])


# ──────────────────────────────────────────────────────────────────────
# GET  /api/replay/{profile}/timeline — build replay timeline
# ──────────────────────────────────────────────────────────────────────


@router.get("/{profile}/timeline")
async def list_replay_timeline(
    profile: str,
) -> list[dict[str, Any]]:
    """Return a complete timeline of replay points for a profile.

    Scans memories, sessions, data outputs, and MEMORY.md to build a
    chronological history of every key moment in the profile's life.

    Parameters
    ----------
    profile : str
        Name of the profile to replay.

    Returns
    -------
    list[dict[str, Any]]
        Chronologically-ordered list of :class:`ReplayPoint` dictionaries,
        newest first.
    """
    try:
        return get_replay_timeline(profile)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build replay timeline: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# GET  /api/replay/{profile}/at — snapshot at a timestamp
# ──────────────────────────────────────────────────────────────────────


@router.get("/{profile}/at")
async def replay_at_timestamp(
    profile: str,
    timestamp: Annotated[
        str,
        Query(description="ISO-8601 timestamp to replay at"),
    ],
) -> dict[str, Any]:
    """Return a profile state snapshot as it existed at a given timestamp.

    Gathers all replay points that occurred *at or before* the requested
    time, presenting a "snapshot" of the profile's state at that moment.

    Parameters
    ----------
    profile : str
        Name of the profile.
    timestamp : str
        ISO-8601 datetime string (e.g. ``2025-06-01T12:00:00+00:00``).

    Returns
    -------
    dict[str, Any]
        Snapshot with events up to and including the requested timestamp.
    """
    try:
        return get_replay_at(profile, timestamp)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid timestamp format: {exc}",
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to replay at timestamp: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# GET  /api/replay/{profile}/evolution — evolution summary
# ──────────────────────────────────────────────────────────────────────


@router.get("/{profile}/evolution")
async def profile_evolution(
    profile: str,
) -> dict[str, Any]:
    """Generate an evolution summary showing how a profile changed over time.

    Compares the earliest known state against the current state and
    provides before/after snapshots, event counts, and a human-readable
    summary.

    Parameters
    ----------
    profile : str
        Name of the profile.

    Returns
    -------
    dict[str, Any]
        Evolution summary with earliest/latest events, date span, and
        event type breakdown.
    """
    try:
        return get_evolution_summary(profile)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build evolution summary: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# POST  /api/replay/{profile}/compare — compare two timestamps
# ──────────────────────────────────────────────────────────────────────


@router.post("/{profile}/compare")
async def compare_profile_timeframes(
    profile: str,
    body: CompareTimeframesRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Compare the profile state between two timestamps.

    Accepts a JSON body with ``ts_a`` and ``ts_b`` keys (ISO-8601
    timestamps) and returns a difference analysis showing what changed.

    Parameters
    ----------
    profile : str
        Name of the profile.
    body : CompareTimeframesRequest
        Must contain ``ts_a`` (before) and ``ts_b`` (after) keys with
        ISO-8601 timestamp values.

    Returns
    -------
    dict[str, Any]
        Comparison result with both snapshots and a list of events between
        the two timestamps.
    """
    try:
        return compare_timeframes(profile, body.ts_a, body.ts_b)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid timestamp format: {exc}",
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare timeframes: {exc}",
        )
