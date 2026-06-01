"""
Dashboard Stats Service — Hermes profile statistics and global aggregations.

Provides data models and scanning functions for per-profile statistics,
global dashboard stats, and timeline trend data for charts.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────


class ProfileStats:
    """Aggregated statistics for a single Hermes profile.

    Attributes
    ----------
    profile_name : str
        Name of the profile directory.
    total_sessions : int
        Number of session files found.
    total_tokens : int
        Estimated total tokens across all sessions (approximate).
    total_code_lines : int
        Total lines of code across skill files and configs.
    total_documents : int
        Number of markdown documents (SOUL.md, memories, docs).
    last_active : str or None
        ISO-8601 timestamp of the most recent modification.
    soul_size : int
        Size of SOUL.md in bytes (0 if missing).
    skill_count : int
        Number of skills (directories + files) in the skills directory.
    """

    def __init__(
        self,
        profile_name: str,
        total_sessions: int = 0,
        total_tokens: int = 0,
        total_code_lines: int = 0,
        total_documents: int = 0,
        last_active: str | None = None,
        soul_size: int = 0,
        skill_count: int = 0,
    ) -> None:
        self.profile_name = profile_name
        self.total_sessions = total_sessions
        self.total_tokens = total_tokens
        self.total_code_lines = total_code_lines
        self.total_documents = total_documents
        self.last_active = last_active
        self.soul_size = soul_size
        self.skill_count = skill_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "total_sessions": self.total_sessions,
            "total_tokens": self.total_tokens,
            "total_code_lines": self.total_code_lines,
            "total_documents": self.total_documents,
            "last_active": self.last_active,
            "soul_size": self.soul_size,
            "skill_count": self.skill_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProfileStats:
        return cls(
            profile_name=data["profile_name"],
            total_sessions=data.get("total_sessions", 0),
            total_tokens=data.get("total_tokens", 0),
            total_code_lines=data.get("total_code_lines", 0),
            total_documents=data.get("total_documents", 0),
            last_active=data.get("last_active"),
            soul_size=data.get("soul_size", 0),
            skill_count=data.get("skill_count", 0),
        )

    def __repr__(self) -> str:
        return (
            f"<ProfileStats {self.profile_name}: "
            f"{self.total_sessions} sessions, {self.total_tokens} tokens, "
            f"{self.skill_count} skills>"
        )


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _profiles_dir() -> Path:
    """Return the absolute path to the Hermes profiles directory."""
    return settings.hermes_profile_path / "profiles"


def _latest_mtime(path: Path) -> str | None:
    """Return the most recent modification time under *path* (recursive)."""
    if not path.exists():
        return None
    try:
        if path.is_file():
            mtime = os.path.getmtime(path)
            return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        # Directory — scan recursively
        latest = 0.0
        for root_str, _dirs, files in os.walk(str(path)):
            for fname in files:
                try:
                    mtime = os.path.getmtime(os.path.join(root_str, fname))
                    if mtime > latest:
                        latest = mtime
                except OSError:
                    continue
        if latest > 0:
            return datetime.fromtimestamp(latest, tz=timezone.utc).isoformat()
        return None
    except OSError:
        return None


def _count_lines(path: Path, extensions: set[str]) -> int:
    """Count total lines in files under *path* with given extensions."""
    total = 0
    if not path.exists():
        return 0
    try:
        for fpath in path.rglob("*"):
            if fpath.is_file() and fpath.suffix in extensions:
                try:
                    with open(fpath, encoding="utf-8", errors="replace") as fh:
                        total += sum(1 for _ in fh)
                except Exception:
                    continue
    except Exception:
        pass
    return total


def _estimate_tokens_from_sessions(profile_dir: Path) -> int:
    """Estimate total tokens from session files.

    Rough heuristic: count characters / 4 (typical token:char ratio).
    """
    total_chars = 0
    sessions_dir = profile_dir / "sessions"
    if not sessions_dir.is_dir():
        return 0
    for fpath in sessions_dir.iterdir():
        if not fpath.is_file():
            continue
        try:
            total_chars += fpath.stat().st_size
        except OSError:
            continue
    return total_chars // 4  # Rough token estimate


# ──────────────────────────────────────────────────────────────────────
# Per-profile scanning
# ──────────────────────────────────────────────────────────────────────


def _scan_profile_stats(profile_dir: Path, name: str) -> ProfileStats:
    """Compute statistics for a single profile directory."""
    # Sessions
    sessions_dir = profile_dir / "sessions"
    total_sessions = 0
    if sessions_dir.is_dir():
        total_sessions = sum(1 for f in sessions_dir.iterdir() if f.is_file())

    # Tokens
    total_tokens = _estimate_tokens_from_sessions(profile_dir)

    # Code lines — count .py, .sh, .yaml, .yml, .json, .toml
    code_extensions: set[str] = {".py", ".sh", ".yaml", ".yml", ".json", ".toml", ".conf"}
    total_code_lines = 0
    # Skills directory
    skills_dir = profile_dir / "skills"
    if skills_dir.is_dir():
        total_code_lines += _count_lines(skills_dir, code_extensions)
    # Home directory
    home_dir = profile_dir / "home"
    if home_dir.is_dir():
        total_code_lines += _count_lines(home_dir, code_extensions)
    # Profile root config files
    for ext in code_extensions:
        for fpath in profile_dir.glob(f"*{ext}"):
            if fpath.is_file():
                try:
                    with open(fpath, encoding="utf-8", errors="replace") as fh:
                        total_code_lines += sum(1 for _ in fh)
                except Exception:
                    continue

    # Documents — markdown files
    total_documents = 0
    # Profile root .md
    total_documents += sum(1 for f in profile_dir.glob("*.md") if f.is_file())
    # Memories .md
    memories_dir = profile_dir / "memories"
    if memories_dir.is_dir():
        total_documents += sum(
            1 for f in memories_dir.glob("*.md") if f.is_file()
        )

    # Last active
    last_active = _latest_mtime(profile_dir)

    # SOUL size
    soul_path = profile_dir / "SOUL.md"
    soul_size = soul_path.stat().st_size if soul_path.is_file() else 0

    # Skill count
    skill_count = 0
    if skills_dir.is_dir():
        for entry in skills_dir.iterdir():
            if entry.is_dir():
                skill_count += 1  # Count subdirectory as one skill
            elif entry.is_file():
                skill_count += 1  # Count standalone skill files too

    return ProfileStats(
        profile_name=name,
        total_sessions=total_sessions,
        total_tokens=total_tokens,
        total_code_lines=total_code_lines,
        total_documents=total_documents,
        last_active=last_active,
        soul_size=soul_size,
        skill_count=skill_count,
    )


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def get_all_stats() -> list[dict[str, Any]]:
    """Return statistics for all profiles.

    Scans every profile directory under ``$HERMES_HOME/profiles/`` and
    returns a list of :class:`ProfileStats` dictionaries.

    Returns
    -------
    list[dict[str, Any]]
        Profile statistics dictionaries, sorted alphabetically.
    """
    profiles_dir = _profiles_dir()
    if not profiles_dir.is_dir():
        logger.warning("Profiles directory does not exist: %s", profiles_dir)
        return []

    results: list[dict[str, Any]] = []
    for entry in sorted(profiles_dir.iterdir()):
        if not entry.is_dir():
            continue
        try:
            stats = _scan_profile_stats(entry, entry.name)
            results.append(stats.to_dict())
        except Exception as exc:
            logger.warning("Failed to scan profile '%s': %s", entry.name, exc)

    return results


def get_profile_stats(name: str) -> dict[str, Any]:
    """Return statistics for a single profile.

    Parameters
    ----------
    name : str
        Profile directory name.

    Returns
    -------
    dict[str, Any]
        Profile statistics dictionary.

    Raises
    ------
    FileNotFoundError
        If the profile directory does not exist.
    """
    profile_dir = _profiles_dir() / name
    if not profile_dir.is_dir():
        raise FileNotFoundError(f"Profile '{name}' not found at {profile_dir}")
    return _scan_profile_stats(profile_dir, name).to_dict()


def get_global_stats() -> dict[str, Any]:
    """Return global dashboard statistics aggregated across all profiles.

    Returns
    -------
    dict[str, Any]
        ``total_profiles``, ``total_sessions``, ``total_tokens``,
        ``total_code_lines``, ``total_documents``, ``total_skills``,
        ``last_updated``, and ``active_trend`` (counts per day for
        the last 7 days).
    """
    all_stats = get_all_stats()

    total_profiles = len(all_stats)
    total_sessions = sum(s.get("total_sessions", 0) for s in all_stats)
    total_tokens = sum(s.get("total_tokens", 0) for s in all_stats)
    total_code_lines = sum(s.get("total_code_lines", 0) for s in all_stats)
    total_documents = sum(s.get("total_documents", 0) for s in all_stats)
    total_skills = sum(s.get("skill_count", 0) for s in all_stats)

    # Last updated = newest last_active across all profiles
    last_updated: str | None = None
    for s in all_stats:
        la = s.get("last_active")
        if la and (last_updated is None or la > last_updated):
            last_updated = la

    # Active trend — how many profiles were active on each of the last 7 days
    active_trend = _compute_active_trend(all_stats, days=7)

    return {
        "total_profiles": total_profiles,
        "total_sessions": total_sessions,
        "total_tokens": total_tokens,
        "total_code_lines": total_code_lines,
        "total_documents": total_documents,
        "total_skills": total_skills,
        "last_updated": last_updated or _iso_now(),
        "active_trend": active_trend,
    }


def get_trend_data(days: int = 30) -> dict[str, Any]:
    """Return activity trend data suitable for chart rendering.

    For each day in the period, count how many profiles were active and
    the total number of sessions / code changes detected.

    Parameters
    ----------
    days : int
        Number of days to look back (default: 30).

    Returns
    -------
    dict[str, Any]
        ``labels`` (ISO date strings), ``active_profiles`` (count per day),
        ``session_counts`` (total session files per day), and
        ``code_changes`` (total code lines added per day, approximated).
    """
    now = datetime.now(timezone.utc)
    all_stats = get_all_stats()

    # Build day buckets
    labels: list[str] = []
    active_profiles: list[int] = []
    session_counts: list[int] = []
    # Code change approximation: we sample per-profile modification recency
    code_changes: list[int] = []

    for i in range(days - 1, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        labels.append(day_start.date().isoformat())

        active_count = 0
        session_count = 0
        code_change_count = 0

        for s in all_stats:
            la = s.get("last_active")
            if la:
                try:
                    la_dt = datetime.fromisoformat(la)
                    if day_start <= la_dt < day_end:
                        active_count += 1
                        # Approximate: each active profile contributed some code
                        code_change_count += max(
                            1, s.get("total_code_lines", 0) // max(1, s.get("total_sessions", 1))
                        )
                except (ValueError, TypeError):
                    continue

            # Sessions created on this day (based on session file timestamps)
            profile_dir = _profiles_dir() / s["profile_name"]
            sessions_dir = profile_dir / "sessions"
            if sessions_dir.is_dir():
                for fpath in sessions_dir.iterdir():
                    if not fpath.is_file():
                        continue
                    try:
                        fmtime = datetime.fromtimestamp(
                            os.path.getmtime(fpath), tz=timezone.utc
                        )
                        if day_start <= fmtime < day_end:
                            session_count += 1
                    except OSError:
                        continue

        active_profiles.append(active_count)
        session_counts.append(session_count)
        code_changes.append(code_change_count)

    return {
        "labels": labels,
        "active_profiles": active_profiles,
        "session_counts": session_counts,
        "code_changes": code_changes,
    }


# ──────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────


def _compute_active_trend(
    all_stats: list[dict[str, Any]], days: int = 7
) -> list[dict[str, Any]]:
    """Compute daily profile activity counts over the last *days* days.

    Returns a list of ``{"date": "YYYY-MM-DD", "active": int}`` entries.
    """
    now = datetime.now(timezone.utc)
    trend: list[dict[str, Any]] = []

    for i in range(days - 1, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        count = 0
        for s in all_stats:
            la = s.get("last_active")
            if la:
                try:
                    la_dt = datetime.fromisoformat(la)
                    if day_start <= la_dt < day_end:
                        count += 1
                except (ValueError, TypeError):
                    continue

        trend.append({
            "date": day_start.date().isoformat(),
            "active": count,
        })

    return trend


def _iso_now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
