"""
Session Router — REST API for terminal session management.

Endpoints
---------
=========================  =====  ========================================
Path                       Method  Description
=========================  =====  ========================================
/api/sessions               GET    List all sessions
/api/sessions               POST   Create a new session
/api/sessions/{id}          GET    Get session details
/api/sessions/{id}          DELETE Delete a session
/api/sessions/{id}/touch    POST   Update session last-active timestamp
/api/sessions/{id}/exec     POST   Execute a command in a session
=========================  =====  ========================================
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from security.auth import require_api_key
from services.command_router import command_router
from services.session_manager import SessionManager, Session

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/sessions", tags=["Sessions"])


# ──────────────────────────────────────────────────────────────────────
# Pydantic request models (inline — avoids touching models/request.py)
# ──────────────────────────────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    """Request body for ``POST /api/sessions``."""

    profile_name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Hermes profile name to bind this session to",
    )
    label: str | None = Field(
        None,
        max_length=256,
        description="Optional human-friendly display label",
    )
    meta: dict[str, Any] | None = Field(
        None,
        description="Optional metadata key-value pairs",
    )


class ExecuteCommandRequest(BaseModel):
    """Request body for ``POST /api/sessions/{id}/exec``."""

    command: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Command string to execute",
    )
    context: dict[str, Any] | None = Field(
        None,
        description="Optional execution context overrides",
    )


# ──────────────────────────────────────────────────────────────────────
# GET  /api/sessions — list all
# ──────────────────────────────────────────────────────────────────────


@router.get("")
async def list_sessions(
    profile: Annotated[str | None, Query(description="Filter by profile name")] = None,
) -> list[dict[str, Any]]:
    """Return all terminal sessions, optionally filtered by profile.

    Sessions are sorted by ``last_active`` descending (most recent first).

    Parameters
    ----------
    profile : str or None
        Optional profile name to filter by.

    Returns
    -------
    list[dict[str, Any]]
        List of session dictionaries.
    """
    try:
        if profile:
            sessions: list[Session] = SessionManager.get_sessions_for_profile(profile)
        else:
            sessions = SessionManager.list_sessions()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load sessions: {exc}",
        )
    return [s.to_dict() for s in sessions]


# ──────────────────────────────────────────────────────────────────────
# POST  /api/sessions — create
# ──────────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Create a new terminal session for a Hermes profile.

    Parameters
    ----------
    body : CreateSessionRequest
        Session creation payload (profile_name, optional label and meta).

    Returns
    -------
    dict[str, Any]
        The newly created session dictionary.

    Raises
    ------
    422
        If required fields are missing or invalid.
    """
    try:
        session: Session = SessionManager.create_session(
            profile_name=body.profile_name,
            label=body.label or "",
            meta=body.meta or {},
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist session: {exc}",
        )
    return session.to_dict()


# ──────────────────────────────────────────────────────────────────────
# GET  /api/sessions/{id} — single session
# ──────────────────────────────────────────────────────────────────────


@router.get("/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    """Return a single session by its ID.

    Parameters
    ----------
    session_id : str
        Session UUID identifier.

    Returns
    -------
    dict[str, Any]
        Session dictionary.

    Raises
    ------
    404
        If the session is not found.
    """
    try:
        session: Session = SessionManager.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load session: {exc}",
        )
    return session.to_dict()


# ──────────────────────────────────────────────────────────────────────
# DELETE  /api/sessions/{id} — delete session
# ──────────────────────────────────────────────────────────────────────


@router.delete("/{session_id}", status_code=status.HTTP_200_OK)
async def delete_session(
    session_id: str,
    _auth: None = Depends(require_api_key),
) -> None:
    """Delete a session by its ID.

    Parameters
    ----------
    session_id : str
        Session identifier to delete.

    Raises
    ------
    404
        If the session is not found.
    """
    try:
        SessionManager.delete_session(session_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# POST  /api/sessions/{id}/touch — update last-active
# ──────────────────────────────────────────────────────────────────────


@router.post("/{session_id}/touch")
async def touch_session(
    session_id: str,
) -> dict[str, Any]:
    """Update the ``last_active`` timestamp of a session.

    Parameters
    ----------
    session_id : str
        Session identifier.

    Returns
    -------
    dict[str, Any]
        The updated session dictionary.

    Raises
    ------
    404
        If the session is not found.
    """
    try:
        session: Session = SessionManager.touch_session(session_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session: {exc}",
        )
    return session.to_dict()


# ──────────────────────────────────────────────────────────────────────
# POST  /api/sessions/{id}/exec — execute command
# ──────────────────────────────────────────────────────────────────────


@router.post("/{session_id}/exec")
async def execute_command(
    session_id: str,
    body: ExecuteCommandRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Execute a terminal command in the context of a session.

    The command is routed through the :class:`CommandRouter` which applies
    whitelist/blacklist rules, registered handlers, and falls back to
    session-level execution.

    Parameters
    ----------
    session_id : str
        Session identifier to execute in.
    body : ExecuteCommandRequest
        Command payload with optional context overrides.

    Returns
    -------
    dict[str, Any]
        Result dictionary with at least ``"output"`` and ``"success"`` keys.

    Raises
    ------
    404
        If the session is not found.
    """
    # Resolve the session to get its profile
    try:
        session: Session = SessionManager.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load session: {exc}",
        )

    # Build execution context
    ctx: dict[str, Any] = {
        "profile": session.profile_name,
        "session_id": session.session_id,
    }
    if body.context:
        ctx.update(body.context)

    try:
        result: dict[str, Any] = command_router.route(body.command, ctx)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Command execution failed: {exc}",
        )

    return result


# ──────────────────────────────────────────────────────────────────────
# POST  /api/sessions/reload — force reload from disk (admin)
# ──────────────────────────────────────────────────────────────────────


@router.post("/reload")
async def reload_sessions(
    _auth: None = Depends(require_api_key),
) -> dict[str, str]:
    """Force a full reload of all sessions from disk (admin operation).

    This is useful when sessions have been modified externally.

    Returns
    -------
    dict[str, str]
        Confirmation message.
    """
    try:
        SessionManager.reload()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload sessions: {exc}",
        )
    return {"status": "ok", "message": "Session cache reloaded from disk."}
