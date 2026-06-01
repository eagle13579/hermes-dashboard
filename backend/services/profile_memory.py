"""
Profile Memory — per-profile isolated memory storage service.

Provides an interface to read/write per-profile memory data (conversation
history, SOUL, skill index snapshots) without modifying the global state.db.

Data layout::

    {settings.hermes_profile_path}/data/
        profiles/{profile_name}/
            memory.json           # Profile-specific memory store
            skills_index.json     # Skill index snapshot for this profile
        soul_history/{profile_name}/
            soul.json             # Structured SOUL document (identity, models, caps, etc.)
            evolution/            # Evolution log entries
                {timestamp}.json
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_MEMORY: dict[str, Any] = {
    "conversations": [],
    "facts": [],
    "preferences": {},
    "metadata": {"created_at": None, "updated_at": None},
}
"""Default memory structure for a new profile."""

DEFAULT_SOUL: dict[str, Any] = {
    "identity": {
        "name": "",
        "role": "assistant",
        "positioning": "",
        "description": "",
    },
    "mental_models": [],
    "capabilities": [],
    "mandates": [],
    "personality": {},
    "awakening_marks": [],
    "emotional_anchors": [],
    "evolution_log": [],
}
"""Default SOUL structure for a new profile."""

DEFAULT_SKILLS_INDEX: dict[str, Any] = {
    "profile_name": "",
    "updated_at": None,
    "global_skills": [],
    "enabled_skills": [],
}
"""Default skills index structure for a new profile."""


# ═══════════════════════════════════════════════════════════════════════
# Path helpers
# ═══════════════════════════════════════════════════════════════════════


def _profile_data_dir(profile_name: str) -> Path:
    """Return the per-profile data directory, creating it if needed.

    Path: ``{settings.hermes_profile_path}/data/profiles/{profile_name}/``
    """
    from config import settings

    d = settings.hermes_profile_path / "data" / "profiles" / profile_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _soul_dir(profile_name: str) -> Path:
    """Return the per-profile SOUL directory, creating it if needed.

    Path: ``{settings.hermes_profile_path}/data/soul_history/{profile_name}/``
    """
    from config import settings

    d = settings.hermes_profile_path / "data" / "soul_history" / profile_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _evolution_dir(profile_name: str) -> Path:
    """Return the evolution log directory, creating it if needed.

    Path: ``{settings.hermes_profile_path}/data/soul_history/{profile_name}/evolution/``
    """
    d = _soul_dir(profile_name) / "evolution"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ═══════════════════════════════════════════════════════════════════════
# File I/O helpers
# ═══════════════════════════════════════════════════════════════════════


def _safe_read_json(path: Path, default: Any = None) -> Any:
    """Safely read a JSON file, returning *default* on any error."""
    try:
        if path.is_file():
            raw = path.read_text(encoding="utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else default
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read JSON %s: %s", path, exc)
    return default


def _safe_write_json(path: Path, data: Any) -> None:
    """Atomically write *data* as JSON to *path*."""
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError as exc:
        logger.error("Failed to write JSON %s: %s", path, exc)
        raise


def _get_iso_now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# Public API — Profile Memory
# ═══════════════════════════════════════════════════════════════════════


def get_profile_memory(profile_name: str) -> dict[str, Any]:
    """Return the full memory store for a profile.

    Returns the default memory structure if no stored data exists.
    """
    mem_path = _profile_data_dir(profile_name) / "memory.json"
    data = _safe_read_json(mem_path)
    if data is None:
        data = dict(DEFAULT_MEMORY)
        data["metadata"]["created_at"] = _get_iso_now()
        data["metadata"]["updated_at"] = _get_iso_now()
    return data


def save_profile_memory(profile_name: str, memory: dict[str, Any]) -> None:
    """Persist a memory dict for the given profile.

    Automatically updates ``metadata.updated_at``.
    """
    mem_path = _profile_data_dir(profile_name) / "memory.json"
    memory.setdefault("metadata", {})["updated_at"] = _get_iso_now()
    if "created_at" not in memory.get("metadata", {}):
        memory["metadata"]["created_at"] = _get_iso_now()
    _safe_write_json(mem_path, memory)


def append_conversation_entry(
    profile_name: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a single conversation entry to the profile's memory.

    Parameters
    ----------
    profile_name : str
        Target profile name.
    role : str
        Message role (e.g. ``user``, ``assistant``, ``system``).
    content : str
        Message content.
    metadata : dict or None
        Optional extra metadata attached to this entry.

    Returns
    -------
    dict
        The appended entry.
    """
    entry: dict[str, Any] = {
        "role": role,
        "content": content,
        "timestamp": _get_iso_now(),
    }
    if metadata:
        entry["metadata"] = metadata

    memory = get_profile_memory(profile_name)
    memory.setdefault("conversations", []).append(entry)
    save_profile_memory(profile_name, memory)
    return entry


def add_fact(profile_name: str, fact: str, source: str = "") -> dict[str, Any]:
    """Store a fact in the profile's memory.

    Parameters
    ----------
    profile_name : str
        Target profile name.
    fact : str
        Fact statement to store.
    source : str
        Optional source identifier.

    Returns
    -------
    dict
        The stored fact entry.
    """
    entry: dict[str, Any] = {
        "fact": fact,
        "source": source,
        "timestamp": _get_iso_now(),
    }
    memory = get_profile_memory(profile_name)
    memory.setdefault("facts", []).append(entry)
    save_profile_memory(profile_name, memory)
    return entry


# ═══════════════════════════════════════════════════════════════════════
# Public API — SOUL management
# ═══════════════════════════════════════════════════════════════════════


def get_soul(profile_name: str) -> dict[str, Any]:
    """Return the structured SOUL data for a profile.

    Returns the default SOUL structure if no stored data exists.
    """
    soul_path = _soul_dir(profile_name) / "soul.json"
    data = _safe_read_json(soul_path)
    if data is None:
        data = dict(DEFAULT_SOUL)
        data["identity"]["name"] = profile_name
        data["identity"]["description"] = f"{profile_name} — 自动创建于 {_get_iso_now()}"
    return data


def save_soul(profile_name: str, soul: dict[str, Any]) -> None:
    """Persist the SOUL data for a profile."""
    soul_path = _soul_dir(profile_name) / "soul.json"
    _safe_write_json(soul_path, soul)


def update_soul_identity(
    profile_name: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Update the identity section of a profile's SOUL.

    Parameters
    ----------
    profile_name : str
        Target profile name.
    updates : dict
        Key-value pairs to merge into the identity.

    Returns
    -------
    dict
        The updated identity section.
    """
    soul = get_soul(profile_name)
    soul.setdefault("identity", {})
    soul["identity"].update(updates)
    save_soul(profile_name, soul)
    return soul["identity"]


def add_evolution_entry(
    profile_name: str,
    entry_type: str,
    description: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append an evolution log entry to the profile's SOUL.

    The entry is written into both the main ``soul.json`` (in-memory list)
    and persisted as a standalone JSON file in the ``evolution/`` directory.

    Parameters
    ----------
    profile_name : str
        Target profile name.
    entry_type : str
        Evolution type (e.g. ``awakening``, ``merge``, ``insight``,
        ``skill_acquired``, ``mandate_added``).
    description : str
        Human-readable description of the evolution event.
    details : dict or None
        Optional structured details attached to this entry.

    Returns
    -------
    dict
        The evolution entry dict with ``timestamp``, ``type``, ``description``,
        and optionally ``details``.
    """
    timestamp = _get_iso_now()
    entry: dict[str, Any] = {
        "timestamp": timestamp,
        "type": entry_type,
        "description": description,
    }
    if details:
        entry["details"] = details

    # Update main soul.json
    soul = get_soul(profile_name)
    soul.setdefault("evolution_log", []).append(entry)
    save_soul(profile_name, soul)

    # Persist standalone entry in evolution/ directory
    evo_filename = timestamp.replace(":", "-").replace(".", "-") + ".json"
    evo_path = _evolution_dir(profile_name) / evo_filename
    _safe_write_json(evo_path, entry)

    return entry


def get_evolution_history(profile_name: str) -> list[dict[str, Any]]:
    """Return the full evolution log for a profile.

    Reads from the main ``soul.json`` first, falling back to scanning
    the ``evolution/`` directory if the main entry is missing.
    """
    soul = get_soul(profile_name)
    evo_log = soul.get("evolution_log", [])
    if evo_log:
        return evo_log

    # Fallback: scan evolution/ directory
    evo_dir = _evolution_dir(profile_name)
    if not evo_dir.is_dir():
        return []

    entries: list[dict[str, Any]] = []
    for fpath in sorted(evo_dir.iterdir()):
        if fpath.suffix == ".json":
            entry = _safe_read_json(fpath)
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


# ═══════════════════════════════════════════════════════════════════════
# Public API — Skill Index Snapshots
# ═══════════════════════════════════════════════════════════════════════


def get_skills_index(profile_name: str) -> dict[str, Any]:
    """Return the skill index snapshot for a profile.

    The index contains:
    - ``profile_name``: profile name
    - ``updated_at``: last sync timestamp
    - ``global_skills``: list of known global skills from the Hermes skills/
      directory
    - ``enabled_skills``: list of skills explicitly enabled for this profile

    Returns the default skills index structure if no stored data exists.
    """
    idx_path = _profile_data_dir(profile_name) / "skills_index.json"
    data = _safe_read_json(idx_path)
    if data is None:
        data = dict(DEFAULT_SKILLS_INDEX)
        data["profile_name"] = profile_name
    return data


def sync_skills_index(profile_name: str) -> dict[str, Any]:
    """Synchronise the profile's skill index from the global skills directory.

    Scans ``$HERMES_HOME/skills/`` for all registered skills and updates
    the snapshot.  Preserves any existing ``enabled_skills`` list.

    Returns
    -------
    dict
        The updated skills index.
    """
    from services.skill_studio import list_skills

    idx = get_skills_index(profile_name)
    enabled = idx.get("enabled_skills", [])

    try:
        global_skills = list_skills()
    except OSError as exc:
        logger.warning("Failed to list global skills for sync: %s", exc)
        global_skills = []

    idx["profile_name"] = profile_name
    idx["updated_at"] = _get_iso_now()
    idx["global_skills"] = global_skills
    idx["enabled_skills"] = enabled

    # Save
    idx_path = _profile_data_dir(profile_name) / "skills_index.json"
    _safe_write_json(idx_path, idx)
    return idx


def set_enabled_skills(
    profile_name: str,
    skill_names: list[str],
) -> dict[str, Any]:
    """Set the enabled skills list for a profile.

    Parameters
    ----------
    profile_name : str
        Target profile name.
    skill_names : list[str]
        Names of skills to mark as enabled.

    Returns
    -------
    dict
        The updated skills index.
    """
    idx = get_skills_index(profile_name)
    idx.setdefault("global_skills", [])
    idx["enabled_skills"] = skill_names
    idx["updated_at"] = _get_iso_now()

    idx_path = _profile_data_dir(profile_name) / "skills_index.json"
    _safe_write_json(idx_path, idx)
    return idx
