"""
Timeline Router — REST API for the Hermes profile activity timeline.

Endpoints
---------
=======================  =====  ====================================
Path                     Method  Description
=======================  =====  ====================================
/api/timeline             GET    List timeline events (filtered)
/api/timeline/types       GET    List valid event types
=======================  =====  ====================================
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from security.auth import require_api_key
from services.timeline import (
    EVENT_TYPES,
    get_timeline,
    get_timeline_by_type,
    scan_all_profiles_timeline,
)

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/timeline", tags=["Timeline"])


# ──────────────────────────────────────────────────────────────────────
# GET  /api/timeline — list timeline events
# ──────────────────────────────────────────────────────────────────────


@router.get("")
async def list_timeline(
    profile: Annotated[
        str | None,
        Query(description="Filter by profile name"),
    ] = None,
    days: Annotated[
        int,
        Query(description="Number of days back to include"),
    ] = 7,
    limit: Annotated[
        int,
        Query(description="Maximum number of events to return"),
    ] = 50,
) -> list[dict[str, Any]]:
    """Return a filtered timeline of all profile activity.

    Events are sorted newest-first.  Supports optional filtering by
    profile name, lookback window (days), and result count limit.

    Parameters
    ----------
    profile : str, optional
        If provided, only events for this profile are returned.
    days : int
        How many days back to include (default: 7, max: 365).
    limit : int
        Maximum number of events (default: 50, max: 500).

    Returns
    -------
    list[dict[str, Any]]
        List of :class:`~services.timeline.TimelineEvent` dictionaries.
    """
    # Sanity-clamp parameters
    days = max(1, min(365, days))
    limit = max(1, min(500, limit))

    try:
        events = get_timeline(profile=profile, days=days, limit=limit)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to scan timeline: {exc}",
        )
    return events


# ──────────────────────────────────────────────────────────────────────
# GET  /api/timeline/types — list valid event types
# ──────────────────────────────────────────────────────────────────────


@router.get("/types")
async def list_event_types() -> dict[str, list[str]]:
    """Return the list of valid timeline event types.

    These map to the ``event_type`` field in timeline entries and can
    be used to filter the timeline via the ``type`` query parameter.

    Returns
    -------
    dict[str, list[str]]
        ``{"event_types": ["code_commit", "doc_created", ...]}``
    """
    return {"event_types": list(EVENT_TYPES)}


# ──────────────────────────────────────────────────────────────────────
# GET  /api/timeline/by-type — filter by event type
# ──────────────────────────────────────────────────────────────────────


@router.get("/by-type")
async def list_timeline_by_type(
    event_type: Annotated[
        str,
        Query(description="Event type to filter by"),
    ],
) -> list[dict[str, Any]]:
    """Return timeline events filtered by a specific event type.

    Parameters
    ----------
    event_type : str
        One of the valid event types returned by ``/api/timeline/types``.

    Returns
    -------
    list[dict[str, Any]]
        Matching timeline event dictionaries.

    Raises
    ------
    422
        If the event type is not recognised.
    """
    if event_type not in EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid event type '{event_type}'. "
            f"Valid types: {', '.join(EVENT_TYPES)}",
        )

    try:
        events = get_timeline_by_type(event_type)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query timeline: {exc}",
        )
    return events


# ──────────────────────────────────────────────────────────────────────
# GET  /api/timeline/scan — force re-scan (debug / admin)
# ──────────────────────────────────────────────────────────────────────


@router.post("/scan")
async def trigger_scan(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Force a full re-scan of all profiles and return event counts.

    Useful for manually refreshing the timeline cache when profiles
    have been updated externally.

    Returns
    -------
    dict[str, Any]
        ``{"total_events": <int>, "scanned_profiles": <int>}``
    """
    try:
        events = scan_all_profiles_timeline()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scan failed: {exc}",
        )

    # Count unique profiles
    seen_profiles: set[str] = set()
    for ev in events:
        seen_profiles.add(ev.profile_name)

    return {
        "total_events": len(events),
        "scanned_profiles": len(seen_profiles),
    }
