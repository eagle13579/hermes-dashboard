"""
Session Manager — Hermes dashboard terminal session service.

Manages multiple interactive terminal sessions, each tied to a specific
Hermes profile.  Sessions are persisted as JSON files under
``<data-dir>/sessions/`` so they survive backend restarts.

Architecture
------------
*L2 — Session Manager*: 会话切换 + 持久化
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

SESSION_DIR_NAME: str = "sessions"
"""Sub-directory under the dashboard data dir where session files live."""


# ──────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────


@dataclass
class Session:
    """An interactive terminal session bound to a Hermes profile.

    Attributes
    ----------
    session_id : str
        Unique UUID4 identifier for this session.
    profile_name : str
        The Hermes profile this session is connected to.
    label : str
        Human-friendly label for display purposes.
    created_at : str
        ISO-8601 timestamp of creation.
    last_active : str
        ISO-8601 timestamp of the most recent activity.
    command_history : list[str]
        Commands that have been executed in this session.
    meta : dict[str, Any]
        Extensible metadata key-value store.
    """

    session_id: str
    profile_name: str
    label: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_active: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    command_history: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        """Create an instance from a dictionary (e.g. loaded from JSON)."""
        return cls(**data)


# ──────────────────────────────────────────────────────────────────────
# Persistence helpers
# ──────────────────────────────────────────────────────────────────────


def _data_dir() -> Path:
    """Return the data directory for sessions (creates if absent)."""
    this_file = Path(__file__).resolve()
    # backend/services/session_manager.py -> go up to backend/, then ../data/
    data_dir = this_file.parent.parent.parent / "data"
    return data_dir


def _sessions_dir() -> Path:
    """Return the sessions sub-directory (creates if absent)."""
    sdir = _data_dir() / SESSION_DIR_NAME
    sdir.mkdir(parents=True, exist_ok=True)
    return sdir


def _session_path(session_id: str) -> Path:
    """Return the JSON file path for a given session ID."""
    return _sessions_dir() / f"{session_id}.json"


# ──────────────────────────────────────────────────────────────────────
# In-memory cache
# ──────────────────────────────────────────────────────────────────────

_session_cache: dict[str, Session] | None = None
"""In-memory cache of all sessions, lazy-loaded from disk on first access."""


def _load_sessions() -> dict[str, Session]:
    """Load all session files from disk into the in-memory cache.

    Returns
    -------
    dict[str, Session]
        Mapping of ``session_id -> Session``.
    """
    global _session_cache
    sessions: dict[str, Session] = {}
    sdir = _sessions_dir()
    if not sdir.is_dir():
        _session_cache = sessions
        return sessions

    for fpath in sorted(sdir.iterdir()):
        if fpath.suffix != ".json":
            continue
        try:
            raw = fpath.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(raw)
            session = Session.from_dict(data)
            sessions[session.session_id] = session
        except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
            logger.warning("Skipping malformed session file %s: %s", fpath.name, exc)

    _session_cache = sessions
    return sessions


def _save_session(session: Session) -> None:
    """Persist a single session to its JSON file.

    Parameters
    ----------
    session : Session
        The session to save.
    """
    path = _session_path(session.session_id)
    try:
        path.write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.error("Failed to save session %s: %s", session.session_id, exc)
        raise


def _delete_session_file(session_id: str) -> None:
    """Remove a session's JSON file from disk.

    Parameters
    ----------
    session_id : str
        ID of the session whose file should be removed.
    """
    path = _session_path(session_id)
    try:
        if path.is_file():
            path.unlink()
    except OSError as exc:
        logger.error("Failed to delete session file %s: %s", session_id, exc)
        raise


def _ensure_cache() -> dict[str, Session]:
    """Return the in-memory cache, loading from disk if needed."""
    if _session_cache is None:
        return _load_sessions()
    return _session_cache


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


class SessionManager:
    """Manages terminal sessions — create, switch, list, delete, persist.

    All methods are synchronous (operate on local JSON files).  They are
    safe to call from FastAPI route handlers either directly or wrapped
    in ``run_in_executor``.
    """

    # ── Create ───────────────────────────────────────────────────────

    @staticmethod
    def create_session(
        profile_name: str,
        label: str = "",
        meta: dict[str, Any] | None = None,
    ) -> Session:
        """Create a new session bound to the given profile.

        Parameters
        ----------
        profile_name : str
            Hermes profile name this session is for.
        label : str
            Optional human-friendly display label.
        meta : dict[str, Any] or None
            Optional metadata to attach to the session.

        Returns
        -------
        Session
            The newly created session.
        """
        session = Session(
            session_id=uuid.uuid4().hex,
            profile_name=profile_name,
            label=label or profile_name,
            meta=meta or {},
        )
        cache = _ensure_cache()
        cache[session.session_id] = session
        _save_session(session)
        logger.info(
            "Created session %s for profile '%s'",
            session.session_id,
            profile_name,
        )
        return session

    # ── Read / List ──────────────────────────────────────────────────

    @staticmethod
    def list_sessions() -> list[Session]:
        """Return all known sessions, sorted by ``last_active`` descending.

        Returns
        -------
        list[Session]
            All sessions, most recently active first.
        """
        cache = _ensure_cache()
        return sorted(
            cache.values(),
            key=lambda s: s.last_active,
            reverse=True,
        )

    @staticmethod
    def get_session(session_id: str) -> Session:
        """Return a single session by its ID.

        Parameters
        ----------
        session_id : str
            Session identifier.

        Returns
        -------
        Session
            The matching session.

        Raises
        ------
        KeyError
            If the session ID is not found.
        """
        cache = _ensure_cache()
        if session_id not in cache:
            raise KeyError(f"Session '{session_id}' not found.")
        return cache[session_id]

    @staticmethod
    def get_sessions_for_profile(profile_name: str) -> list[Session]:
        """Return all sessions belonging to a given profile.

        Parameters
        ----------
        profile_name : str
            Profile name to filter by.

        Returns
        -------
        list[Session]
            Matching sessions, sorted by ``last_active`` descending.
        """
        cache = _ensure_cache()
        return sorted(
            (s for s in cache.values() if s.profile_name == profile_name),
            key=lambda s: s.last_active,
            reverse=True,
        )

    # ── Update / Touch ───────────────────────────────────────────────

    @staticmethod
    def touch_session(session_id: str) -> Session:
        """Update the ``last_active`` timestamp of a session.

        Parameters
        ----------
        session_id : str
            Session identifier.

        Returns
        -------
        Session
            The updated session.

        Raises
        ------
        KeyError
            If the session ID is not found.
        """
        cache = _ensure_cache()
        if session_id not in cache:
            raise KeyError(f"Session '{session_id}' not found.")
        session = cache[session_id]
        session.last_active = datetime.now(timezone.utc).isoformat()
        _save_session(session)
        return session

    @staticmethod
    def append_command(session_id: str, command: str) -> Session:
        """Append a command to a session's history and touch last_active.

        Parameters
        ----------
        session_id : str
            Session identifier.
        command : str
            Command string to append.

        Returns
        -------
        Session
            The updated session.

        Raises
        ------
        KeyError
            If the session ID is not found.
        """
        cache = _ensure_cache()
        if session_id not in cache:
            raise KeyError(f"Session '{session_id}' not found.")
        session = cache[session_id]
        session.command_history.append(command)
        session.last_active = datetime.now(timezone.utc).isoformat()
        _save_session(session)
        return session

    # ── Delete ───────────────────────────────────────────────────────

    @staticmethod
    def delete_session(session_id: str) -> None:
        """Delete a session by its ID (removes from cache and disk).

        Parameters
        ----------
        session_id : str
            Session identifier.

        Raises
        ------
        KeyError
            If the session ID is not found.
        """
        cache = _ensure_cache()
        if session_id not in cache:
            raise KeyError(f"Session '{session_id}' not found.")
        del cache[session_id]
        _delete_session_file(session_id)
        logger.info("Deleted session %s", session_id)

    # ── Maintenance ──────────────────────────────────────────────────

    @staticmethod
    def reload() -> None:
        """Force a full reload of all sessions from disk."""
        global _session_cache
        _session_cache = None
        _ensure_cache()
        logger.debug("Session cache reloaded from disk.")
