"""
Dashboard Router — REST API for the Hermes global dashboard.

Endpoints
---------
============================  =====  ====================================
Path                          Method  Description
============================  =====  ====================================
/api/dashboard/stats           GET    Global aggregated statistics
/api/dashboard/stats/{profile} GET    Single profile statistics
/api/dashboard/trends          GET    Activity trend data for charts
============================  =====  ====================================
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from services.dashboard_stats import (
    get_all_stats,
    get_global_stats,
    get_profile_stats,
    get_trend_data,
)

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# ──────────────────────────────────────────────────────────────────────
# GET  /api/dashboard/stats — global statistics
# ──────────────────────────────────────────────────────────────────────


@router.get("/stats")
async def global_stats() -> dict[str, Any]:
    """Return aggregated global statistics across all profiles.

    Provides total counts for profiles, sessions, tokens, code lines,
    documents, and skills.  Also includes a 7-day active trend.

    Returns
    -------
    dict[str, Any]
        Global statistics (see :func:`~services.dashboard_stats.get_global_stats`).
    """
    try:
        stats = get_global_stats()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute global stats: {exc}",
        )
    return stats


# ──────────────────────────────────────────────────────────────────────
# GET  /api/dashboard/stats/{profile} — single profile statistics
# ──────────────────────────────────────────────────────────────────────


@router.get("/stats/{profile}")
async def profile_stats(profile: str) -> dict[str, Any]:
    """Return aggregated statistics for a single Hermes profile.

    Parameters
    ----------
    profile : str
        Profile directory name.

    Returns
    -------
    dict[str, Any]
        Profile statistics dictionary (see :class:`~services.dashboard_stats.ProfileStats`).

    Raises
    ------
    404
        If the profile does not exist.
    """
    try:
        stats = get_profile_stats(profile)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read profile stats: {exc}",
        )
    return stats


# ──────────────────────────────────────────────────────────────────────
# GET  /api/dashboard/trends — trend data
# ──────────────────────────────────────────────────────────────────────


@router.get("/trends")
async def dashboard_trends(
    days: Annotated[
        int,
        Query(description="Number of days to include in the trend"),
    ] = 30,
) -> dict[str, Any]:
    """Return activity trend data suitable for chart rendering.

    Provides daily counts of active profiles, session counts, and
    approximated code changes over the specified lookback period.

    Parameters
    ----------
    days : int
        Lookback period in days (default: 30, max: 365).

    Returns
    -------
    dict[str, Any]
        Trend data (see :func:`~services.dashboard_stats.get_trend_data`).
    """
    days = max(1, min(365, days))

    try:
        trend = get_trend_data(days=days)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute trend data: {exc}",
        )
    return trend


# ──────────────────────────────────────────────────────────────────────
# GET  /api/dashboard/all — all profiles (helper for frontend)
# ──────────────────────────────────────────────────────────────────────


@router.get("/all")
async def all_profiles_stats() -> list[dict[str, Any]]:
    """Return statistics for every profile.

    Convenience endpoint that returns all profile stats without the
    aggregation wrapper.  Useful for populating per-profile cards in
    the dashboard UI.

    Returns
    -------
    list[dict[str, Any]]
        List of :class:`~services.dashboard_stats.ProfileStats` dictionaries.
    """
    try:
        all_stats = get_all_stats()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list profile stats: {exc}",
        )
    return all_stats
