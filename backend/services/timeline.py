"""
Timeline Service — Hermes profile activity timeline.

Scans all profiles for events inferred from file-system modifications,
session records, memory files, and skill directories.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────


class TimelineEvent:
    """A single event on the profile timeline.

    Attributes
    ----------
    timestamp : str
        ISO-8601 datetime string (UTC) of the event.
    profile_name : str
        Name of the profile that generated this event.
    event_type : str
        One of ``code_commit``, ``doc_created``, ``decision_made``,
        ``task_completed``, ``skill_created``.
    title : str
        Short human-readable title for the event.
    description : str
        Longer description or summary of what happened.
    source_path : str
        Absolute filesystem path of the artefact associated with this event.
    """

    def __init__(
        self,
        timestamp: str,
        profile_name: str,
        event_type: str,
        title: str,
        description: str = "",
        source_path: str = "",
    ) -> None:
        self.timestamp = timestamp
        self.profile_name = profile_name
        self.event_type = event_type
        self.title = title
        self.description = description
        self.source_path = source_path

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "profile_name": self.profile_name,
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "source_path": self.source_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimelineEvent:
        return cls(
            timestamp=data["timestamp"],
            profile_name=data["profile_name"],
            event_type=data["event_type"],
            title=data.get("title", ""),
            description=data.get("description", ""),
            source_path=data.get("source_path", ""),
        )

    def __repr__(self) -> str:
        return (
            f"<TimelineEvent {self.event_type} @ {self.timestamp} "
            f"[{self.profile_name}] {self.title}>"
        )


# Valid event types
EVENT_TYPES = [
    "code_commit",
    "doc_created",
    "decision_made",
    "task_completed",
    "skill_created",
]

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _profiles_dir() -> Path:
    """Return the absolute path to the Hermes profiles directory."""
    return settings.hermes_profile_path / "profiles"


def _iso_now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _mtime_iso(path: Path) -> str | None:
    """Return the modification time of *path* as an ISO-8601 string.

    Returns ``None`` if the path does not exist.
    """
    try:
        mtime = os.path.getmtime(path)
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


# ──────────────────────────────────────────────────────────────────────
# Scanning
# ──────────────────────────────────────────────────────────────────────


def _scan_session_events(profile_dir: Path, profile_name: str) -> list[TimelineEvent]:
    """Extract session-based events from JSON/JSONL session files.

    Each session file represents a completed conversation.  We record a
    ``task_completed`` event for every session found.
    """
    events: list[TimelineEvent] = []
    sessions_dir = profile_dir / "sessions"
    if not sessions_dir.is_dir():
        return events

    for fpath in sorted(sessions_dir.iterdir()):
        if not fpath.is_file():
            continue
        try:
            mtime = _mtime_iso(fpath)
            if not mtime:
                continue

            # JSONL format (zhairu style): first line has session_meta
            if fpath.suffix == ".jsonl":
                with open(fpath, encoding="utf-8", errors="replace") as fh:
                    first_line = fh.readline().strip()
                if first_line:
                    try:
                        meta = json.loads(first_line)
                    except json.JSONDecodeError:
                        meta = {}
                else:
                    meta = {}
                title = f"Session: {fpath.stem}"
                desc = meta.get("model", "")
                if isinstance(desc, str) and desc:
                    desc = f"Model: {desc}"
                else:
                    desc = f"Session file: {fpath.name}"

            # JSON format (chainke-dev / hermes-dashboard style)
            elif fpath.suffix == ".json":
                with open(fpath, encoding="utf-8", errors="replace") as fh:
                    data = json.load(fh)
                title = f"Session: {data.get('session_id', fpath.stem)}"
                model = data.get("model", "")
                desc = f"Model: {model}" if model else f"Session file: {fpath.name}"
            else:
                title = f"Session: {fpath.stem}"
                desc = f"Session file: {fpath.name}"

            events.append(
                TimelineEvent(
                    timestamp=mtime,
                    profile_name=profile_name,
                    event_type="task_completed",
                    title=title,
                    description=desc,
                    source_path=str(fpath),
                )
            )
        except Exception as exc:
            logger.debug("Skipping session file %s: %s", fpath, exc)

    return events


def _scan_doc_events(profile_dir: Path, profile_name: str) -> list[TimelineEvent]:
    """Scan markdown documents (SOUL.md, memories, docs) for doc_created events."""
    events: list[TimelineEvent] = []

    # SOUL.md
    soul_path = profile_dir / "SOUL.md"
    if soul_path.is_file():
        mtime = _mtime_iso(soul_path)
        if mtime:
            try:
                text = soul_path.read_text(encoding="utf-8", errors="replace")
                summary = text[:200].replace("\n", " ").strip()
            except Exception:
                summary = ""
            events.append(
                TimelineEvent(
                    timestamp=mtime,
                    profile_name=profile_name,
                    event_type="doc_created",
                    title="SOUL.md updated",
                    description=summary,
                    source_path=str(soul_path),
                )
            )

    # Other .md files in profile root
    for fpath in sorted(profile_dir.glob("*.md")):
        if fpath.name == "SOUL.md":
            continue
        mtime = _mtime_iso(fpath)
        if mtime:
            events.append(
                TimelineEvent(
                    timestamp=mtime,
                    profile_name=profile_name,
                    event_type="doc_created",
                    title=f"Document: {fpath.name}",
                    description=f"Markdown document in profile root — {fpath.stat().st_size} bytes",
                    source_path=str(fpath),
                )
            )

    # Memory files (MEMORY.md, USER.md)
    memories_dir = profile_dir / "memories"
    if memories_dir.is_dir():
        for fpath in sorted(memories_dir.glob("*.md")):
            mtime = _mtime_iso(fpath)
            if mtime:
                events.append(
                    TimelineEvent(
                        timestamp=mtime,
                        profile_name=profile_name,
                        event_type="doc_created",
                        title=f"Memory: {fpath.name}",
                        description=f"Memory document — {fpath.stat().st_size} bytes",
                        source_path=str(fpath),
                    )
                )

    return events


def _scan_code_events(profile_dir: Path, profile_name: str) -> list[TimelineEvent]:
    """Scan for code-related events (Python files, config files)."""
    events: list[TimelineEvent] = []

    # config.yaml
    config_path = profile_dir / "config.yaml"
    if config_path.is_file():
        mtime = _mtime_iso(config_path)
        if mtime:
            events.append(
                TimelineEvent(
                    timestamp=mtime,
                    profile_name=profile_name,
                    event_type="code_commit",
                    title="Config updated",
                    description="Profile configuration (config.yaml) modified",
                    source_path=str(config_path),
                )
            )

    # auth.json
    auth_path = profile_dir / "auth.json"
    if auth_path.is_file():
        mtime = _mtime_iso(auth_path)
        if mtime:
            events.append(
                TimelineEvent(
                    timestamp=mtime,
                    profile_name=profile_name,
                    event_type="code_commit",
                    title="Auth config updated",
                    description="Authentication configuration modified",
                    source_path=str(auth_path),
                )
            )

    # .env
    env_path = profile_dir / ".env"
    if env_path.is_file():
        mtime = _mtime_iso(env_path)
        if mtime:
            events.append(
                TimelineEvent(
                    timestamp=mtime,
                    profile_name=profile_name,
                    event_type="code_commit",
                    title="Environment config updated",
                    description="Environment variables modified",
                    source_path=str(env_path),
                )
            )

    return events


def _scan_skill_events(profile_dir: Path, profile_name: str) -> list[TimelineEvent]:
    """Scan skills directories for skill_created events."""
    events: list[TimelineEvent] = []
    skills_dir = profile_dir / "skills"
    if not skills_dir.is_dir():
        return events

    # Walk one level deep for skill subdirectories
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir():
            mtime = _mtime_iso(entry)
            if mtime:
                # Count files inside the skill
                try:
                    file_count = sum(1 for _ in entry.rglob("*") if _.is_file())
                except Exception:
                    file_count = 0
                events.append(
                    TimelineEvent(
                        timestamp=mtime,
                        profile_name=profile_name,
                        event_type="skill_created",
                        title=f"Skill: {entry.name}",
                        description=f"Skill directory with {file_count} files",
                        source_path=str(entry),
                    )
                )
        elif entry.is_file() and entry.suffix in (".py", ".sh", ".yaml", ".yml"):
            # Standalone skill files
            mtime = _mtime_iso(entry)
            if mtime:
                events.append(
                    TimelineEvent(
                        timestamp=mtime,
                        profile_name=profile_name,
                        event_type="skill_created",
                        title=f"Skill file: {entry.name}",
                        description=f"Skill file — {entry.stat().st_size} bytes",
                        source_path=str(entry),
                    )
                )

    return events


def _scan_decision_events(profile_dir: Path, profile_name: str) -> list[TimelineEvent]:
    """Attempt to detect decision events from memory files.

    Heuristic: scan MEMORY.md for lines matching decision-like patterns
    (e.g. '决定', '决策', 'decided', 'chosen', 'selected').
    """
    events: list[TimelineEvent] = []

    for mem_file in ("MEMORY.md", "USER.md"):
        fpath = profile_dir / "memories" / mem_file
        if not fpath.is_file():
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
            mtime = _mtime_iso(fpath)
            if not mtime:
                continue

            # Look for decision-like keywords
            decision_keywords = ["决定", "决策", "decided", "chosen", "selected", "opted"]
            lines = text.split("\n")
            for i, line in enumerate(lines):
                lower_line = line.lower()
                if any(kw in lower_line or kw in line for kw in decision_keywords):
                    # Found a decision — create event
                    snippet = line.strip()[:150]
                    events.append(
                        TimelineEvent(
                            timestamp=mtime,
                            profile_name=profile_name,
                            event_type="decision_made",
                            title=f"Decision: {snippet[:60]}...",
                            description=snippet,
                            source_path=str(fpath),
                        )
                    )
                    break  # One decision event per memory file is enough
        except Exception:
            continue

    return events


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def scan_all_profiles_timeline() -> list[TimelineEvent]:
    """Scan all profiles and return a unified, time-sorted list of events.

    Checks file modification times, session records, memory files, and
    skill directories for every profile under ``$HERMES_HOME/profiles/``.

    Returns
    -------
    list[TimelineEvent]
        All discovered events sorted descending by timestamp.
    """
    profiles_dir = _profiles_dir()
    if not profiles_dir.is_dir():
        logger.warning("Profiles directory does not exist: %s", profiles_dir)
        return []

    all_events: list[TimelineEvent] = []

    for entry in sorted(profiles_dir.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name

        try:
            all_events.extend(_scan_session_events(entry, name))
            all_events.extend(_scan_doc_events(entry, name))
            all_events.extend(_scan_code_events(entry, name))
            all_events.extend(_scan_skill_events(entry, name))
            all_events.extend(_scan_decision_events(entry, name))
        except Exception as exc:
            logger.warning("Error scanning profile '%s': %s", name, exc)

    # Sort descending by timestamp (newest first)
    all_events.sort(key=lambda e: e.timestamp, reverse=True)
    return all_events


def get_timeline(
    profile: str | None = None,
    days: int = 7,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return a filtered timeline of events.

    Parameters
    ----------
    profile : str or None
        If provided, only events for this profile are returned.
    days : int
        How many days back to include (default: 7).
    limit : int
        Maximum number of events to return (default: 50).

    Returns
    -------
    list[dict[str, Any]]
        Timeline event dictionaries.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    events = scan_all_profiles_timeline()

    filtered: list[TimelineEvent] = []
    for ev in events:
        # Profile filter
        if profile and ev.profile_name != profile:
            continue
        # Time filter
        try:
            ev_dt = datetime.fromisoformat(ev.timestamp)
        except (ValueError, TypeError):
            continue
        if ev_dt < cutoff:
            continue
        filtered.append(ev)

    return [ev.to_dict() for ev in filtered[:limit]]


def get_timeline_by_type(event_type: str) -> list[dict[str, Any]]:
    """Return timeline events filtered by event type.

    Parameters
    ----------
    event_type : str
        One of ``code_commit``, ``doc_created``, ``decision_made``,
        ``task_completed``, ``skill_created``.

    Returns
    -------
    list[dict[str, Any]]
        Matching timeline event dictionaries, newest first.
    """
    if event_type not in EVENT_TYPES:
        logger.warning("Unknown event type: %s", event_type)
        return []

    events = scan_all_profiles_timeline()
    return [ev.to_dict() for ev in events if ev.event_type == event_type]
