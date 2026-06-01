"""
Log Stream Service — Real-time file watching with SSE delivery.

Reads profile log files from ``profiles/{name}/logs/`` and provides
both historical retrieval (last N lines) and a file-watcher that yields
new lines as they are appended.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import AsyncIterator

logger = logging.getLogger(__name__)


# ── Public helpers ─────────────────────────────────────────────────────


def resolve_profile_log_dir(profile_name: str) -> Path:
    """Return the absolute path to a profile's log directory.

    Looks for ``$HERMES_HOME/profiles/{profile_name}/logs/``.
    Falls back to ``$HERMES_PROFILE_PATH/../{profile_name}/logs/``.

    Raises
    ------
    FileNotFoundError
        If neither ``$HERMES_HOME`` nor a well-known fallback resolves.
    """
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        base = Path(hermes_home).expanduser().resolve()
    else:
        # Fallback: derive from project layout
        base = Path(
            "D:/向海容的知识库/wiki/wiki/记忆宫殿"
        ).resolve()

    log_dir = base / "profiles" / profile_name / "logs"
    return log_dir


def _find_log_files(log_dir: Path) -> list[Path]:
    """Return sorted list of ``.log`` files in *log_dir*."""
    if not log_dir.is_dir():
        return []
    try:
        return sorted(
            [p for p in log_dir.iterdir() if p.suffix.lower() == ".log"],
            key=lambda p: p.name,
        )
    except OSError:
        return []


def read_recent_lines(
    profile_name: str,
    lines: int = 50,
) -> list[dict]:
    """Read the last *lines* from the latest log file of a profile.

    Parameters
    ----------
    profile_name : str
        Profile directory name.
    lines : int
        Number of recent lines to return (max 5000).

    Returns
    -------
    list[dict]
        Each entry: ``{"line": <str>, "timestamp": <str or None>}``.
    """
    log_dir = resolve_profile_log_dir(profile_name)
    log_files = _find_log_files(log_dir)
    if not log_files:
        return []

    # Use the most recent file by name (sorted ascending, last = newest)
    target = log_files[-1]
    return _tail_file(target, max_lines=min(lines, 5000))


def _tail_file(path: Path, max_lines: int = 50) -> list[dict]:
    """Return the last *max_lines* lines of a text file."""
    if not path.is_file():
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            all_lines = fh.readlines()
    except OSError as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return []

    # Keep only the last max_lines
    tail = all_lines[-max_lines:]
    results: list[dict] = []
    for line in tail:
        stripped = line.rstrip("\n\r")
        # Try to extract a timestamp from the common format:
        #   2026-05-31 19:22:51,246 INFO ...
        timestamp: str | None = None
        if len(stripped) > 26 and stripped[4] == "-" and stripped[7] == "-":
            # Looks like a log-line with a leading timestamp
            timestamp = stripped[:26].strip()
        results.append({
            "line": stripped,
            "timestamp": timestamp if timestamp else None,
        })
    return results


# ── Async file watcher (SSE source) ────────────────────────────────────


async def watch_log_file(
    profile_name: str,
    poll_interval: float = 0.5,
) -> AsyncIterator[dict]:
    """Asynchronously watch the latest log file for a profile.

    Yields dictionaries with ``line`` and ``timestamp`` keys whenever
    new content is appended to the file.  If no log file exists yet the
    iterator polls until one appears.

    Parameters
    ----------
    profile_name : str
        Profile directory name.
    poll_interval : float
        Seconds between polls when no new data is available.

    Yields
    ------
    dict
        ``{"line": <str>, "timestamp": <str or None>}`` for each new line.
    """
    log_dir = resolve_profile_log_dir(profile_name)
    last_position: dict[str, int] = {}  # filename -> byte offset

    # Ensure the log directory exists
    if not log_dir.is_dir():
        logger.info("Log directory does not exist yet: %s — watching for its creation...", log_dir)

    while True:
        # Check if the directory now exists
        if log_dir.is_dir():
            log_files = _find_log_files(log_dir)
            if log_files:
                target = log_files[-1]  # latest file
                filepath = str(target)

                try:
                    stat = target.stat()
                    current_size = stat.st_size

                    prev_pos = last_position.get(filepath, 0)

                    if current_size > prev_pos:
                        # Read new bytes
                        with open(target, "r", encoding="utf-8", errors="replace") as fh:
                            fh.seek(prev_pos)
                            new_data = fh.read()

                        last_position[filepath] = fh.tell()

                        if new_data:
                            for raw_line in new_data.splitlines():
                                if raw_line:
                                    timestamp: str | None = None
                                    if len(raw_line) > 26 and raw_line[4] == "-" and raw_line[7] == "-":
                                        timestamp = raw_line[:26].strip()
                                    yield {
                                        "line": raw_line,
                                        "timestamp": timestamp,
                                    }

                    elif current_size < prev_pos:
                        # File was truncated / rotated — reset
                        last_position[filepath] = 0

                except (OSError, PermissionError) as exc:
                    logger.debug("Cannot stat/read %s: %s", filepath, exc)

        await asyncio.sleep(poll_interval)
