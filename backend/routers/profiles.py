"""
Profiles Router — REST API for Hermes profile management.

Endpoints
---------
=======================  =====  ====================================
Path                     Method  Description
=======================  =====  ====================================
/api/profiles             GET    List all profiles
/api/profiles/{name}      GET    Single profile detail
/api/profiles             POST   Create a new profile
/api/profiles/{name}      DELETE  Delete a profile
/api/profiles/{name}/start POST  Start a profile process
/api/profiles/{name}/stop  POST  Stop a running profile
/api/profiles/{name}/status GET   Get profile status (running / not)
=======================  =====  ====================================
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from models.request import CreateProfileRequest
from security.auth import require_api_key
from services.profile_manager import ProfileManager

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/profiles", tags=["Profiles"])


# ──────────────────────────────────────────────────────────────────────
# GET  /api/profiles — list
# ──────────────────────────────────────────────────────────────────────


@router.get("")
async def list_profiles() -> list[dict]:
    """Return a summary of every profile under ``$HERMES_HOME/profiles/``.

    Each entry includes the profile name, a SOUL.md excerpt, parsed
    ``config.yaml`` keys, and live status (running / not).

    Returns
    -------
    list[dict]
        List of :class:`~services.profile_manager.ProfileInfo` dictionaries.
    """
    try:
        profiles = await ProfileManager.list_profiles()
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return [p.to_dict() for p in profiles]


# ──────────────────────────────────────────────────────────────────────
# GET  /api/profiles/{name} — detail
# ──────────────────────────────────────────────────────────────────────


@router.get("/{name}")
async def get_profile(name: str) -> dict:
    """Return full details for a single profile.

    Parameters
    ----------
    name : str
        Profile directory name.

    Returns
    -------
    dict
        :class:`~services.profile_manager.ProfileDetail` dictionary.

    Raises
    ------
    404
        If the profile does not exist.
    """
    try:
        detail = await ProfileManager.get_profile(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return detail.to_dict()


# ──────────────────────────────────────────────────────────────────────
# POST  /api/profiles — create
# ──────────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: CreateProfileRequest,
    _auth: None = Depends(require_api_key),
) -> dict:
    """Create a new Hermes profile.

    Delegates to ``hermes profile create`` CLI.

    Parameters
    ----------
    body : CreateProfileRequest
        Request body with ``name`` and optional ``clone_from``.

    Returns
    -------
    dict
        ``{"message": "...", "name": "<name>"}`` on success.

    Raises
    ------
    400
        If the CLI command fails (e.g. invalid name, duplicate).
    """
    try:
        output = await ProfileManager.create_profile(body.name, clone_from=body.clone_from)
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"message": f"Profile '{body.name}' created", "name": body.name, "detail": output}


# ──────────────────────────────────────────────────────────────────────
# DELETE  /api/profiles/{name}
# ──────────────────────────────────────────────────────────────────────


@router.delete("/{name}")
async def delete_profile(
    name: str,
    _auth: None = Depends(require_api_key),
) -> dict:
    """Delete a Hermes profile.

    Delegates to ``hermes profile delete`` CLI.  If the profile is running
    it will be stopped first.

    Parameters
    ----------
    name : str
        Profile to delete.

    Returns
    -------
    dict
        ``{"message": "...", "name": "<name>"}`` on success.

    Raises
    ------
    404
        If the CLI reports the profile does not exist.
    400
        If deletion fails for other reasons.
    """
    try:
        output = await ProfileManager.delete_profile(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (RuntimeError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"message": f"Profile '{name}' deleted", "name": name, "detail": output}


# ──────────────────────────────────────────────────────────────────────
# POST  /api/profiles/{name}/start
# ──────────────────────────────────────────────────────────────────────


@router.post("/{name}/start")
async def start_profile(
    name: str,
    _auth: None = Depends(require_api_key),
) -> dict:
    """Start a profile as a background subprocess.

    The profile must exist under ``$HERMES_HOME/profiles/`` and must not
    already be running.

    Parameters
    ----------
    name : str
        Profile to start.

    Returns
    -------
    dict
        ``{"message": "...", "name": "<name>", "pid": <int>}`` on success.

    Raises
    ------
    404
        If the profile directory does not exist.
    409
        If the profile is already running.
    500
        If the process exited immediately after launch.
    """
    try:
        pid = await ProfileManager.start_profile(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        # Distinguish "already running" (409) from other errors (500)
        if "already running" in str(exc):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return {"message": f"Profile '{name}' started", "name": name, "pid": pid}


# ──────────────────────────────────────────────────────────────────────
# POST  /api/profiles/{name}/stop
# ──────────────────────────────────────────────────────────────────────


@router.post("/{name}/stop")
async def stop_profile(
    name: str,
    _auth: None = Depends(require_api_key),
) -> dict:
    """Stop a running profile.

    Sends the ``/exit`` command to the profile process and waits for it
    to terminate gracefully.  Falls back to ``SIGTERM`` / ``SIGKILL`` if
    the process does not exit within 5 seconds.

    Parameters
    ----------
    name : str
        Profile to stop.

    Returns
    -------
    dict
        ``{"message": "...", "name": "<name>"}`` on success.

    Raises
    ------
    409
        If the profile is not currently tracked as running.
    """
    try:
        await ProfileManager.stop_profile(name)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return {"message": f"Profile '{name}' stopped", "name": name}


# ──────────────────────────────────────────────────────────────────────
# GET  /api/profiles/{name}/status
# ──────────────────────────────────────────────────────────────────────


@router.get("/{name}/status")
async def get_profile_status(name: str) -> dict:
    """Return the current runtime status of a profile.

    Status is determined by:
    - Checking the in-memory process registry for a live PID.
    - Scanning the profile's configured gateway port (or common ports).

    Parameters
    ----------
    name : str
        Profile name.

    Returns
    -------
    dict
        :class:`~services.profile_manager.ProfileInfo` dictionary with
        ``name``, ``running``, ``pid`` and ``port`` fields.

    Raises
    ------
    404
        If the profile directory does not exist.
    """
    try:
        status_info = await ProfileManager.get_profile_status(name)
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return status_info.to_dict()
