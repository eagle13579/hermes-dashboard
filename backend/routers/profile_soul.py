"""
Profile Soul Router — REST API for per-profile SOUL, memory, and skills index.

Endpoints
---------
====================================  =====  ====================================
Path                                  Method  Description
====================================  =====  ====================================
/api/profiles/{name}/soul              GET    Get the profile's SOUL data
/api/profiles/{name}/soul/evolve      POST   Add an evolution entry to SOUL
/api/profiles/{name}/memory            GET    Get the profile's memory store
/api/profiles/{name}/skills            GET    Get the profile's skill index snapshot
/api/profiles/{name}/skills/sync      POST   Sync skills index from global directory
/api/profiles/{name}/skills/enabled   PUT    Set enabled skills for a profile
====================================  =====  ====================================
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from models.request import AddEvolutionRequest, SetEnabledSkillsRequest
from security.auth import require_api_key
from services.profile_memory import (
    add_evolution_entry,
    get_evolution_history,
    get_profile_memory,
    get_skills_index,
    get_soul,
    set_enabled_skills,
    sync_skills_index,
)

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/profiles", tags=["Profile Soul"])


# ══════════════════════════════════════════════════════════════════════
# GET  /api/profiles/{name}/soul — get SOUL data
# ══════════════════════════════════════════════════════════════════════


@router.get("/{name}/soul")
async def get_profile_soul(name: str) -> dict[str, Any]:
    """Return the structured SOUL data for a profile.

    Reads from ``data/soul_history/{name}/soul.json``.  If no soul file
    exists yet, returns a default structure populated with the profile name.

    Parameters
    ----------
    name : str
        Profile name.

    Returns
    -------
    dict
        Soul document with keys: ``identity``, ``mental_models``,
        ``capabilities``, ``mandates``, ``personality``,
        ``awakening_marks``, ``emotional_anchors``, ``evolution_log``.

    Raises
    ------
    404
        If the profile directory does not exist.
    500
        On I/O errors.
    """
    # Verify the profile exists
    _ensure_profile_exists(name)

    try:
        soul_data = get_soul(name)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read SOUL for '{name}': {exc}",
        )
    return soul_data


# ══════════════════════════════════════════════════════════════════════
# POST  /api/profiles/{name}/soul/evolve — add evolution entry
# ══════════════════════════════════════════════════════════════════════


@router.post("/{name}/soul/evolve", status_code=status.HTTP_201_CREATED)
async def evolve_soul(
    name: str,
    body: AddEvolutionRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Append an evolution log entry to the profile's SOUL.

    Request body::

        {
            "type": "awakening",
            "description": "Awareness of autonomous code generation",
            "details": {"trigger": "discovered codebase-audit skill"}
        }

    Parameters
    ----------
    name : str
        Profile name.
    body : AddEvolutionRequest
        Evolution entry with ``type``, ``description``, and optional ``details``.

    Returns
    -------
    dict
        The evolution entry that was added, including the generated timestamp.

    Raises
    ------
    404
        If the profile directory does not exist.
    422
        If the request body is invalid.
    500
        On I/O errors.
    """
    _ensure_profile_exists(name)

    try:
        entry = add_evolution_entry(
            profile_name=name,
            entry_type=body.type,
            description=body.description,
            details=body.details,
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add evolution entry: {exc}",
        )

    return {
        "message": f"Evolution entry added to '{name}'",
        "profile": name,
        "entry": entry,
    }


# ══════════════════════════════════════════════════════════════════════
# GET  /api/profiles/{name}/soul/evolution — get evolution history
# ══════════════════════════════════════════════════════════════════════


@router.get("/{name}/soul/evolution")
async def get_evolution(name: str) -> list[dict[str, Any]]:
    """Return the full evolution log for a profile.

    Parameters
    ----------
    name : str
        Profile name.

    Returns
    -------
    list[dict]
        Chronological list of evolution entries.
    """
    _ensure_profile_exists(name)

    try:
        history = get_evolution_history(name)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read evolution history: {exc}",
        )
    return history


# ══════════════════════════════════════════════════════════════════════
# GET  /api/profiles/{name}/memory — get memory store
# ══════════════════════════════════════════════════════════════════════


@router.get("/{name}/memory")
async def get_profile_memory_endpoint(name: str) -> dict[str, Any]:
    """Return the memory store for a profile.

    Contains conversations, facts, and preferences scoped to this profile.

    Parameters
    ----------
    name : str
        Profile name.

    Returns
    -------
    dict
        Memory document with keys: ``conversations``, ``facts``,
        ``preferences``, ``metadata``.
    """
    _ensure_profile_exists(name)

    try:
        memory = get_profile_memory(name)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read memory for '{name}': {exc}",
        )
    return memory


# ══════════════════════════════════════════════════════════════════════
# GET  /api/profiles/{name}/skills — get skill index snapshot
# ══════════════════════════════════════════════════════════════════════


@router.get("/{name}/skills")
async def get_profile_skills_index(name: str) -> dict[str, Any]:
    """Return the skill index snapshot for a profile.

    The snapshot contains:
    - ``profile_name``: profile name
    - ``updated_at``: last sync timestamp
    - ``global_skills``: list of all known global skills
    - ``enabled_skills``: list of skills enabled for this profile

    Parameters
    ----------
    name : str
        Profile name.

    Returns
    -------
    dict
        Skill index document.
    """
    _ensure_profile_exists(name)

    try:
        idx = get_skills_index(name)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read skills index for '{name}': {exc}",
        )
    return idx


# ══════════════════════════════════════════════════════════════════════
# POST  /api/profiles/{name}/skills/sync — sync global skills
# ══════════════════════════════════════════════════════════════════════


@router.post("/{name}/skills/sync")
async def sync_profile_skills(name: str, _auth: None = Depends(require_api_key)) -> dict[str, Any]:
    """Synchronise the profile's skill index from the global skills directory.

    Scans ``$HERMES_HOME/skills/`` for all registered skills and updates
    the snapshot, preserving any existing ``enabled_skills``.

    Parameters
    ----------
    name : str
        Profile name.

    Returns
    -------
    dict
        Updated skill index with message, profile name, and timestamp.
    """
    _ensure_profile_exists(name)

    try:
        idx = sync_skills_index(name)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync skills for '{name}': {exc}",
        )

    return {
        "message": f"Skills index synced for '{name}'",
        "profile": name,
        "updated_at": idx.get("updated_at"),
        "global_count": len(idx.get("global_skills", [])),
        "enabled_count": len(idx.get("enabled_skills", [])),
    }


# ══════════════════════════════════════════════════════════════════════
# PUT  /api/profiles/{name}/skills/enabled — set enabled skills
# ══════════════════════════════════════════════════════════════════════


@router.put("/{name}/skills/enabled")
async def set_profile_enabled_skills(
    name: str,
    body: SetEnabledSkillsRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Set the list of enabled skills for a profile.

    Request body::

        {
            "skill_names": ["codebase-audit", "basic-skill"]
        }

    Parameters
    ----------
    name : str
        Profile name.
    body : SetEnabledSkillsRequest
        Must contain ``skill_names`` list.

    Returns
    -------
    dict
        Updated skill index with the new enabled skills list.
    """
    _ensure_profile_exists(name)

    try:
        idx = set_enabled_skills(name, body.skill_names)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set enabled skills for '{name}': {exc}",
        )

    return {
        "message": f"Enabled skills updated for '{name}'",
        "profile": name,
        "enabled_skills": idx.get("enabled_skills", []),
    }


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _ensure_profile_exists(name: str) -> None:
    """Raise ``404`` if the profile directory does not exist.

    Checks the ``$HERMES_HOME/profiles/{name}`` directory.  This is the
    authoritative "does the profile exist" check used across the codebase.
    """
    raw = os.environ.get("HERMES_HOME")
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="HERMES_HOME environment variable is not set",
        )
    profile_dir = Path(raw).expanduser().resolve() / "profiles" / name
    if not profile_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{name}' not found at {profile_dir}",
        )
