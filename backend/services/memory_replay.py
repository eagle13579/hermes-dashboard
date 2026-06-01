"""
Memory Replay Service — Time-travel through profile memory snapshots.

Provides the ability to:
- Build a timeline of all key moments in a profile's history.
- "Replay" the profile state as it existed at a given timestamp.
- Generate evolution summaries showing how a profile changed over time.
- Compare specific timeframes for detailed diff analysis.

Data sources scanned:
  * profile/memories/          — memory documents (MEMORY.md, USER.md, etc.)
  * profile/sessions/          — JSON/JSONL session conversation files
  * profile/data/              — any production output files (logs, reports)
  * MEMORY.md                  — key memory document in the profile root
  * File modification timestamps are used as event timestamps.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────


@dataclass
class ReplayPoint:
    """A single key moment in a profile's history timeline.

    Attributes
    ----------
    timestamp : str
        ISO-8601 datetime string (UTC) when this event occurred.
    profile_name : str
        Name of the profile this event belongs to.
    event_type : str
        Type of event — one of ``session``, ``memory_updated``,
        ``file_created``, ``milestone``, ``config_changed``.
    title : str
        Short human-readable title for the replay point.
    description : str
        Longer description or summary of what happened.
    snapshot_path : str
        Absolute filesystem path to the snapshot artefact associated
        with this event (memory file, session file, data file, etc.).
    """

    timestamp: str
    profile_name: str
    event_type: str
    title: str
    description: str = ""
    snapshot_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReplayPoint:
        return cls(**data)

    def __repr__(self) -> str:
        return (
            f"<ReplayPoint {self.event_type} @ {self.timestamp} "
            f"[{self.profile_name}] {self.title}>"
        )


# ──────────────────────────────────────────────────────────────────────
# Path helpers
# ──────────────────────────────────────────────────────────────────────


def _get_hermes_home() -> Path:
    """Return the ``$HERMES_HOME`` directory path.

    Raises
    ------
    OSError
        If ``$HERMES_HOME`` is not set and no fallback is found.
    """
    raw = os.environ.get("HERMES_HOME")
    if not raw:
        candidate = Path.home() / "向海容的知识库/wiki/wiki/记忆宫殿"
        if candidate.is_dir():
            return candidate.resolve()
        raise OSError(
            "HERMES_HOME environment variable is not set. "
            "Please set it to your Hermes knowledge base root, e.g.\n"
            '  export HERMES_HOME="D:\\\\\\\\向海容的知识库\\\\\\\\wiki\\\\\\\\wiki\\\\\\\\记忆宫殿"'
        )
    return Path(raw).expanduser().resolve()


def _profiles_dir() -> Path:
    """Return the absolute path to ``$HERMES_HOME/profiles/``."""
    return _get_hermes_home() / "profiles"


def _profile_dir(profile_name: str) -> Path:
    """Return the directory for a specific profile."""
    return _profiles_dir() / profile_name


def _iso_now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _mtime_iso(path: Path) -> str | None:
    """Return the modification time of *path* as ISO-8601 string.

    Returns ``None`` if the path does not exist.
    """
    try:
        mtime = os.path.getmtime(path)
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


# ──────────────────────────────────────────────────────────────────────
# Scanning helpers
# ──────────────────────────────────────────────────────────────────────


def _scan_memories_dir(profile_dir: Path, profile_name: str) -> list[ReplayPoint]:
    """Scan profile/memories/ directory for memory documents.

    Yields a ``memory_updated`` event for each Markdown file found.
    """
    points: list[ReplayPoint] = []
    memories_dir = profile_dir / "memories"
    if not memories_dir.is_dir():
        return points

    for fpath in sorted(memories_dir.glob("*.md")):
        mtime = _mtime_iso(fpath)
        if not mtime:
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
            preview = text[:200].replace("\n", " ").strip()
        except Exception:
            preview = ""
        points.append(
            ReplayPoint(
                timestamp=mtime,
                profile_name=profile_name,
                event_type="memory_updated",
                title=f"Memory: {fpath.name}",
                description=preview or f"Memory document — {fpath.stat().st_size} bytes",
                snapshot_path=str(fpath),
            )
        )

    return points


def _scan_sessions_dir(profile_dir: Path, profile_name: str) -> list[ReplayPoint]:
    """Scan profile/sessions/ directory for conversation session records.

    Yields a ``session`` event for each JSON/JSONL session file.
    """
    points: list[ReplayPoint] = []
    sessions_dir = profile_dir / "sessions"
    if not sessions_dir.is_dir():
        return points

    for fpath in sorted(sessions_dir.iterdir()):
        if not fpath.is_file():
            continue
        mtime = _mtime_iso(fpath)
        if not mtime:
            continue

        title = f"Session: {fpath.stem}"
        description = f"Session file: {fpath.name}"

        try:
            if fpath.suffix == ".jsonl":
                with open(fpath, encoding="utf-8", errors="replace") as fh:
                    first_line = fh.readline().strip()
                if first_line:
                    try:
                        meta = json.loads(first_line)
                    except json.JSONDecodeError:
                        meta = {}
                    model = meta.get("model", "")
                    if model:
                        description = f"Model: {model}"
            elif fpath.suffix == ".json":
                with open(fpath, encoding="utf-8", errors="replace") as fh:
                    data = json.load(fh)
                model = data.get("model", "")
                if model:
                    description = f"Model: {model}"
        except Exception:
            pass

        points.append(
            ReplayPoint(
                timestamp=mtime,
                profile_name=profile_name,
                event_type="session",
                title=title,
                description=description,
                snapshot_path=str(fpath),
            )
        )

    return points


def _scan_data_dir(profile_dir: Path, profile_name: str) -> list[ReplayPoint]:
    """Scan profile/data/ directory for produced output files.

    Yields a ``file_created`` event for each file found.
    """
    points: list[ReplayPoint] = []
    data_dir = profile_dir / "data"
    if not data_dir.is_dir():
        return points

    for fpath in sorted(data_dir.rglob("*")):
        if not fpath.is_file():
            continue
        mtime = _mtime_iso(fpath)
        if not mtime:
            continue
        points.append(
            ReplayPoint(
                timestamp=mtime,
                profile_name=profile_name,
                event_type="file_created",
                title=f"Output: {fpath.name}",
                description=f"Data output file — {fpath.stat().st_size} bytes | {fpath.suffix}",
                snapshot_path=str(fpath),
            )
        )

    return points


def _scan_memory_md(profile_dir: Path, profile_name: str) -> list[ReplayPoint]:
    """Extract relevant paragraphs from MEMORY.md in the profile root.

    Scans the profile root for ``MEMORY.md`` and produces a ``milestone``
    event for each section or key decision paragraph found.
    """
    points: list[ReplayPoint] = []
    memory_md = profile_dir / "MEMORY.md"
    if not memory_md.is_file():
        return points

    mtime = _mtime_iso(memory_md)
    if not mtime:
        return points

    try:
        text = memory_md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return points

    # Split into sections by markdown headings
    sections = re.split(r"\n(?=#+\s)", text)

    for section in sections:
        section = section.strip()
        if not section:
            continue
        # Use first line as title
        lines = section.split("\n")
        heading = lines[0].strip().lstrip("#").strip()
        body = " ".join(l.strip() for l in lines[1:] if l.strip())[:300]

        if not heading:
            heading = f"Section from MEMORY.md"

        points.append(
            ReplayPoint(
                timestamp=mtime,
                profile_name=profile_name,
                event_type="milestone",
                title=f"Memory Section: {heading[:60]}",
                description=body or "Paragraph from MEMORY.md",
                snapshot_path=str(memory_md),
            )
        )

    # If no sections found, add a single event for the whole file
    if not points:
        preview = text[:200].replace("\n", " ").strip()
        points.append(
            ReplayPoint(
                timestamp=mtime,
                profile_name=profile_name,
                event_type="milestone",
                title="MEMORY.md",
                description=preview,
                snapshot_path=str(memory_md),
            )
        )

    return points


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def get_replay_timeline(profile_name: str) -> list[dict[str, Any]]:
    """Build a complete timeline of replay points for a profile.

    Scans all available data sources (memories, sessions, data, MEMORY.md)
    and returns a unified, time-sorted list of replay points.

    Parameters
    ----------
    profile_name : str
        Name of the profile to scan.

    Returns
    -------
    list[dict[str, Any]]
        All discovered replay points sorted chronologically (newest first).

    Raises
    ------
    FileNotFoundError
        If the profile directory does not exist.
    """
    pdir = _profile_dir(profile_name)
    if not pdir.is_dir():
        raise FileNotFoundError(
            f"Profile '{profile_name}' not found at {pdir}"
        )

    all_points: list[ReplayPoint] = []

    try:
        all_points.extend(_scan_memories_dir(pdir, profile_name))
        all_points.extend(_scan_sessions_dir(pdir, profile_name))
        all_points.extend(_scan_data_dir(pdir, profile_name))
        all_points.extend(_scan_memory_md(pdir, profile_name))
    except Exception as exc:
        logger.error("Error scanning profile '%s': %s", profile_name, exc)
        raise

    # Sort descending by timestamp (newest first)
    all_points.sort(key=lambda p: p.timestamp, reverse=True)

    return [p.to_dict() for p in all_points]


def get_replay_at(profile_name: str, timestamp: str) -> dict[str, Any]:
    """Replay the profile state as it existed at (or just before) a given timestamp.

    Gathers all replay points that occurred *at or before* the given
    timestamp, returning a snapshot of the profile's state at that moment.

    Parameters
    ----------
    profile_name : str
        Name of the profile.
    timestamp : str
        ISO-8601 datetime string to replay at.

    Returns
    -------
    dict[str, Any]
        A snapshot containing:
        - ``snapshot_time``: the requested timestamp
        - ``profile_name``: the profile name
        - ``total_events_so_far``: count of events up to this point
        - ``events``: list of replay points at or before the timestamp
        - ``latest_event``: the most recent event (or None)
    """
    timeline = get_replay_timeline(profile_name)

    # Filter to events at or before the given timestamp
    try:
        target_dt = datetime.fromisoformat(timestamp)
    except (ValueError, TypeError):
        target_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    before: list[dict[str, Any]] = []
    for ev in timeline:
        try:
            ev_dt = datetime.fromisoformat(ev["timestamp"])
        except (ValueError, TypeError):
            continue
        if ev_dt <= target_dt:
            before.append(ev)

    # Sort ascending for chronological view
    before.sort(key=lambda e: e["timestamp"])

    latest = before[-1] if before else None

    return {
        "snapshot_time": timestamp,
        "profile_name": profile_name,
        "total_events_so_far": len(before),
        "events": before,
        "latest_event": latest,
    }


def get_evolution_summary(profile_name: str) -> dict[str, Any]:
    """Generate an evolution summary showing how the profile changed.

    Compares the earliest known state against the current state,
    providing before/after snapshots and a list of changes.

    Parameters
    ----------
    profile_name : str
        Name of the profile.

    Returns
    -------
    dict[str, Any]
        A summary containing:
        - ``profile_name``
        - ``days_span``: number of days between earliest and latest
        - ``earliest_event``: the first event recorded
        - ``latest_event``: the most recent event
        - ``total_events``: total number of replay points
        - ``event_type_counts``: breakdown by event type
        - ``summary``: human-readable summary text
    """
    timeline = get_replay_timeline(profile_name)

    if not timeline:
        return {
            "profile_name": profile_name,
            "days_span": 0,
            "earliest_event": None,
            "latest_event": None,
            "total_events": 0,
            "event_type_counts": {},
            "summary": f"No replay data found for profile '{profile_name}'.",
        }

    # Timeline is sorted newest-first; reverse for chronological
    chronological = list(reversed(timeline))

    earliest = chronological[0] if chronological else None
    latest = chronological[-1] if chronological else None

    # Calculate date span
    days_span = 0
    if earliest and latest:
        try:
            earliest_dt = datetime.fromisoformat(earliest["timestamp"])
            latest_dt = datetime.fromisoformat(latest["timestamp"])
            days_span = (latest_dt - earliest_dt).days
        except (ValueError, TypeError):
            days_span = 0

    # Count by event type
    type_counts: dict[str, int] = {}
    for ev in timeline:
        etype = ev.get("event_type", "unknown")
        type_counts[etype] = type_counts.get(etype, 0) + 1

    # Build summary text
    summary_parts = [
        f"Profile '{profile_name}' has **{len(timeline)}** replay points spanning "
        f"**{days_span}** day(s).",
    ]
    if earliest:
        summary_parts.append(
            f"Earliest activity: **{earliest['title']}** @ {earliest['timestamp']}"
        )
    if latest:
        summary_parts.append(
            f"Most recent activity: **{latest['title']}** @ {latest['timestamp']}"
        )
    summary_parts.append(
        f"Breakdown: {', '.join(f'{k}={v}' for k, v in type_counts.items())}"
    )

    return {
        "profile_name": profile_name,
        "days_span": days_span,
        "earliest_event": earliest,
        "latest_event": latest,
        "total_events": len(timeline),
        "event_type_counts": type_counts,
        "summary": "\n".join(summary_parts),
    }


def compare_timeframes(
    profile_name: str,
    ts_a: str,
    ts_b: str,
) -> dict[str, Any]:
    """Compare the profile state between two timestamps.

    Builds two snapshots (one for each timestamp) and computes a
    high-level difference between them.

    Parameters
    ----------
    profile_name : str
        Name of the profile.
    ts_a : str
        First timestamp (ISO-8601) — the "before" snapshot.
    ts_b : str
        Second timestamp (ISO-8601) — the "after" snapshot.

    Returns
    -------
    dict[str, Any]
        A comparison containing:
        - ``profile_name``
        - ``snapshot_a``: replay state at ts_a
        - ``snapshot_b``: replay state at ts_b
        - ``events_between``: events that occurred between ts_a and ts_b
        - ``new_event_types``: event types introduced between the two
        - ``summary``: human-readable comparison text
    """
    snap_a = get_replay_at(profile_name, ts_a)
    snap_b = get_replay_at(profile_name, ts_b)

    events_a = snap_a.get("events", [])
    events_b = snap_b.get("events", [])

    # Events between ts_a and ts_b are those in snap_b but not in snap_a
    timestamps_a = {e["timestamp"] for e in events_a}
    events_between = [e for e in events_b if e["timestamp"] not in timestamps_a]

    # Types introduced between the two
    types_a = {e["event_type"] for e in events_a}
    types_b = {e["event_type"] for e in events_b}
    new_types = types_b - types_a

    # Summary
    summary_parts = [
        f"Comparing **{profile_name}** at:\n"
        f"  A (before): {ts_a} — {len(events_a)} events\n"
        f"  B (after):  {ts_b} — {len(events_b)} events\n"
        f"  **{len(events_between)}** new events occurred between the two timestamps.",
    ]
    if new_types:
        summary_parts.append(
            f"New event types introduced: {', '.join(sorted(new_types))}."
        )
    if events_between:
        summary_parts.append("Notable events between:")
        for ev in events_between[:10]:  # Show top 10
            summary_parts.append(f"  • {ev['title']} @ {ev['timestamp']}")

    return {
        "profile_name": profile_name,
        "snapshot_a": snap_a,
        "snapshot_b": snap_b,
        "events_between": events_between,
        "new_event_types": sorted(new_types),
        "summary": "\n".join(summary_parts),
    }
