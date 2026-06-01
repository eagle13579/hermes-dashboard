"""
Soul Diff Router — REST API for SOUL comparison and merge.

Endpoints
---------
============================  =====  ====================================
Path                           Method  Description
============================  =====  ====================================
/api/soul/{profile}            GET    Read a profile's structured SOUL
/api/soul/diff                 GET    Diff two profiles' SOUL data
/api/soul/merge                POST   Merge SOUL fields into a profile
/api/soul/{profile}/history    GET    Historical SOUL snapshots
/api/soul/{profile}/snapshot   POST   Save a SOUL snapshot
============================  =====  ====================================
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from models.request import MergeSoulRequest
from security.auth import require_api_key

# isort: split
from services.soul_diff import (
    SoulSnapshot,
    diff_souls,
    get_soul_history,
    merge_souls,
    save_snapshot,
    take_snapshot,
)

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/soul", tags=["Soul"])


# ══════════════════════════════════════════════════════════════════════
# GET  /api/soul/diff?a={profile_a}&b={profile_b} — diff two SOULs
# ══════════════════════════════════════════════════════════════════════
# NOTE: static routes MUST be declared BEFORE parameterised routes
#       ({profile}) to avoid FastAPI path-matching ambiguity.


@router.get("/diff")
async def soul_diff(
    a: Annotated[str, Query(description="First profile name")],
    b: Annotated[str, Query(description="Second profile name")],
) -> dict:
    """Compare the structured SOUL data of two profiles.

    Produces a list of ``SoulDiffItem`` entries highlighting additions,
    removals, and modifications across all SOUL categories.

    Parameters
    ----------
    a : str
        Name of the first profile.
    b : str
        Name of the second profile.

    Returns
    -------
    dict
        ``{"profile_a": ..., "profile_b": ..., "common_items": [...], "diff_items": [...]}``

    Raises
    ------
    404
        If either profile does not exist.
    """
    try:
        result = diff_souls(a, b)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        )
    return result.to_dict()


# ══════════════════════════════════════════════════════════════════════
# POST  /api/soul/merge — merge SOUL fields into a profile
# ══════════════════════════════════════════════════════════════════════


@router.post("/merge", status_code=status.HTTP_200_OK)
async def soul_merge(
    body: MergeSoulRequest,
    _auth: None = Depends(require_api_key),
) -> dict:
    """Merge specified SOUL fields from *source* profile into *target* profile.

    Request body::

        {
            "target": "profile-name-a",   // receives the merged data
            "source": "profile-name-b",   // provides the data
            "fields": ["identity", "capabilities", ...]
        }

    Supported *fields* values:
      - ``identity``
      - ``mental_models``
      - ``capabilities``
      - ``personality``
      - ``mandates``
      - ``awakening_marks``
      - ``emotional_anchors``

    Returns
    -------
    dict
        The post-merge :class:`SoulSnapshot` of the target profile.

    Raises
    ------
    400
        If required fields are missing or invalid.
    404
        If either profile does not exist.
    """
    # ── Execute merge ────────────────────────────────────────────────
    try:
        updated_snapshot: SoulSnapshot = merge_souls(
            target_profile=body.target,
            source_profile=body.source,
            merge_fields=body.fields,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        )

    return {
        "message": f"Merged [{', '.join(body.fields)}] from '{body.source}' into '{body.target}'",
        "target": body.target,
        "source": body.source,
        "fields": body.fields,
        "snapshot": updated_snapshot.to_dict(),
    }


# ══════════════════════════════════════════════════════════════════════
# GET  /api/soul/{profile} — read structured SOUL
# ══════════════════════════════════════════════════════════════════════


@router.get("/{profile}")
async def read_soul(profile: str) -> dict:
    """Return the structured SOUL data for a single profile.

    Parses ``soul-injection.yaml`` + ``employee.yaml`` / ``identity.yaml``
    from the profile directory and returns a :class:`SoulSnapshot` dictionary.

    Parameters
    ----------
    profile : str
        Profile name (directory under ``$HERMES_HOME/profiles/``).

    Returns
    -------
    dict
        SoulSnapshot fields: ``profile_name``, ``identity``, ``mental_models``,
        ``capabilities``, ``personality``, ``mandates``, ``awakening_marks``,
        ``emotional_anchors``.

    Raises
    ------
    404
        If the profile directory does not exist.
    """
    try:
        snapshot: SoulSnapshot = take_snapshot(profile)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        )
    return snapshot.to_dict()


# ══════════════════════════════════════════════════════════════════════
# GET  /api/soul/{profile}/history — historical snapshots
# ══════════════════════════════════════════════════════════════════════


@router.get("/{profile}/history")
async def soul_history(profile: str) -> list[dict]:
    """Return the SOUL snapshot history for a profile.

    Snapshots are persisted as timestamped JSON files under
    ``$HERMES_HOME/profiles/hermes-dashboard/data/soul_history/<profile>/``.

    Parameters
    ----------
    profile : str
        Profile name.

    Returns
    -------
    list[dict]
        Chronological list of snapshot metadata entries (oldest first).
        An empty list if no history exists.
    """
    try:
        entries = get_soul_history(profile)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        )
    return entries


# ══════════════════════════════════════════════════════════════════════
# POST  /api/soul/{profile}/snapshot — save a snapshot
# ══════════════════════════════════════════════════════════════════════


@router.post("/{profile}/snapshot", status_code=status.HTTP_201_CREATED)
async def soul_snapshot(
    profile: str,
    _auth: None = Depends(require_api_key),
) -> dict:
    """Take a point-in-time snapshot of the profile's SOUL and persist it.

    The snapshot is saved as a timestamped JSON file in the history
    directory.  This is useful for tracking SOUL evolution over time.

    Parameters
    ----------
    profile : str
        Profile name.

    Returns
    -------
    dict
        Metadata about the saved snapshot:
        ``{"profile": ..., "timestamp": ..., "path": ...}``

    Raises
    ------
    404
        If the profile directory does not exist.
    """
    try:
        result = save_snapshot(profile)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        )
    return result
