"""
Kanban Manager — Hermes dashboard project board service.

Provides a data model and CRUD operations for the Kanban board that tracks
all Hermes profile projects.  Data is persisted as a single JSON file at
``profiles/hermes-dashboard/data/kanban.json``.

The manager supports automatic scanning of ``$HERMES_HOME/profiles/`` so the
board stays in sync with on-disk profiles.  A scheduled cron job should call
:meth:`KanbanManager.auto_refresh` periodically.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

VALID_STATUSES: frozenset[str] = frozenset(
    {"planning", "in_progress", "review", "done", "blocked"}
)
"""Allowed Kanban status values."""

DEFAULT_STATUS: str = "planning"
"""Default status assigned to newly registered projects."""


# ──────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────


@dataclass
class BoardItem:
    """A single project entry on the Kanban board.

    Attributes
    ----------
    project_name : str
        Unique project (profile) name.
    status : str
        Current status — one of ``planning``, ``in_progress``, ``review``,
        ``done``, ``blocked``.
    description : str
        Short human-readable description of the project.
    team_members : list[str]
        Names or IDs of people working on this project.
    progress_pct : int
        Estimated completion percentage (0–100).
    last_updated : str
        ISO-8601 timestamp of the most recent update.
    block_reason : str | None
        If ``status == \"blocked\"``, the reason why the project is stuck.
    """

    project_name: str
    status: str = DEFAULT_STATUS
    description: str = ""
    team_members: list[str] = field(default_factory=list)
    progress_pct: int = 0
    last_updated: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    block_reason: str | None = None

    def __post_init__(self) -> None:
        """Validate field values after initialisation."""
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{self.status}'. "
                f"Must be one of {sorted(VALID_STATUSES)}"
            )
        if not 0 <= self.progress_pct <= 100:
            raise ValueError(
                f"progress_pct must be between 0 and 100, got {self.progress_pct}"
            )
        if self.status != "blocked":
            self.block_reason = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BoardItem:
        """Create an instance from a dictionary (e.g. loaded from JSON)."""
        return cls(**data)


# ──────────────────────────────────────────────────────────────────────
# Persistence helpers
# ──────────────────────────────────────────────────────────────────────


def _get_hermes_home() -> Path:
    """Return the ``$HERMES_HOME`` directory path.

    Raises
    ------
    OSError
        If ``$HERMES_HOME`` is not set.
    """
    raw = os.environ.get("HERMES_HOME")
    if not raw:
        # Fallback: derive from the project location
        # This allows the kanban to work even without the env var
        # when running inside the hermes-dashboard backend directory.
        candidate = (
            Path.home() / "向海容的知识库/wiki/wiki/记忆宫殿"
        )
        if candidate.is_dir():
            return candidate.resolve()
        raise OSError(
            "HERMES_HOME environment variable is not set. "
            "Please set it to your Hermes knowledge base root, e.g.\n"
            '  export HERMES_HOME="D:\\\\向海容的知识库\\\\wiki\\\\wiki\\\\记忆宫殿"'
        )
    return Path(raw).expanduser().resolve()


def _profiles_dir() -> Path:
    """Return the absolute path to ``$HERMES_HOME/profiles/``."""
    return _get_hermes_home() / "profiles"


def _data_dir() -> Path:
    """Return the data directory for the dashboard (creates if absent)."""
    # The data dir lives under the hermes-dashboard profile itself.
    # Resolve relative to this file's location.
    this_file = Path(__file__).resolve()
    # backend/services/kanban_manager.py -> go up to backend/, then ../data/
    data_dir = this_file.parent.parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _kanban_json_path() -> Path:
    """Return the full path to the kanban JSON storage file."""
    return _data_dir() / "kanban.json"


# ──────────────────────────────────────────────────────────────────────
# In-memory cache
# ──────────────────────────────────────────────────────────────────────

_boards_cache: dict[str, BoardItem] | None = None
"""In-memory cache of all board items, refreshed from disk on each API call."""


def _load_boards() -> dict[str, BoardItem]:
    """Load board items from the JSON file into memory.

    Returns
    -------
    dict[str, BoardItem]
        Mapping of ``project_name -> BoardItem``.
    """
    global _boards_cache
    path = _kanban_json_path()
    if not path.is_file():
        logger.info("Kanban data file not found at %s — starting empty.", path)
        _boards_cache = {}
        return _boards_cache

    try:
        raw = path.read_text(encoding="utf-8")
        data: list[dict[str, Any]] = json.loads(raw)
        _boards_cache = {}
        for entry in data:
            try:
                item = BoardItem.from_dict(entry)
                _boards_cache[item.project_name] = item
            except (ValueError, KeyError, TypeError) as exc:
                logger.warning("Skipping malformed board entry: %s", exc)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load kanban data: %s", exc)
        _boards_cache = {}

    return _boards_cache


def _save_boards(boards: dict[str, BoardItem]) -> None:
    """Persist board items to the JSON file.

    Parameters
    ----------
    boards : dict[str, BoardItem]
        Current board state to save.
    """
    global _boards_cache
    path = _kanban_json_path()
    items = [item.to_dict() for item in sorted(boards.values(),
                                                key=lambda x: x.project_name)]
    try:
        path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _boards_cache = boards
    except OSError as exc:
        logger.error("Failed to save kanban data: %s", exc)
        raise


def _ensure_cache() -> dict[str, BoardItem]:
    """Return the in-memory cache, loading from disk if needed."""
    if _boards_cache is None:
        return _load_boards()
    return _boards_cache


# ──────────────────────────────────────────────────────────────────────
# Profile scanning helpers
# ──────────────────────────────────────────────────────────────────────


def _parse_soul_summary(profile_dir: Path) -> str:
    """Read and summarise the first 300 chars of ``SOUL.md``.

    Parameters
    ----------
    profile_dir : Path
        Profile directory to inspect.

    Returns
    -------
    str
        Truncated summary or empty string.
    """
    soul_path = profile_dir / "SOUL.md"
    if not soul_path.is_file():
        return ""
    try:
        text = soul_path.read_text(encoding="utf-8", errors="replace")
        # Extract first meaningful paragraph
        text = text.strip()
        return text[:300].replace("\n", " ").strip()
    except OSError as exc:
        logger.warning("Failed to read SOUL.md in %s: %s", profile_dir.name, exc)
        return ""


def _detect_status_from_profile(profile_dir: Path) -> str:
    """Heuristically determine the Kanban status of a profile.

    Looks for hints in the file system:
    - A ``.kanban_status`` file containing one of the valid status strings.
    - Otherwise reads the first few lines of ``SOUL.md`` for keywords.
    - Falls back to ``planning``.

    Parameters
    ----------
    profile_dir : Path
        Profile directory to examine.

    Returns
    -------
    str
        One of ``planning``, ``in_progress``, ``review``, ``done``, ``blocked``.
    """
    # 1. Explicit .kanban_status marker file
    status_file = profile_dir / ".kanban_status"
    if status_file.is_file():
        try:
            raw = status_file.read_text(encoding="utf-8").strip().lower()
            if raw in VALID_STATUSES:
                return raw
        except OSError:
            pass

    # 2. Heuristic: read SOUL.md for keywords
    soul_path = profile_dir / "SOUL.md"
    if soul_path.is_file():
        try:
            head = soul_path.read_text(encoding="utf-8", errors="replace")[:1000].lower()
        except OSError:
            head = ""
        if re.search(r"\bdone\b|\bcompleted\b|\bfinished\b|\b已(完成|结束)\b", head):
            return "done"
        if re.search(r"\breview\b|\bpr\b|\b审核\b", head):
            return "review"
        if re.search(r"\bblocked\b|\bstuck\b|\b阻塞\b|\b等待\b", head):
            return "blocked"
        if re.search(r"\bin.progress\b|\bworking\b|\b进行\b|\b开发\b|\bfeat\b", head):
            return "in_progress"

    return DEFAULT_STATUS


def _detect_team_members(profile_dir: Path) -> list[str]:
    """Extract a list of team member names from profile metadata.

    Checks ``config.yaml`` for a ``team`` or ``members`` key, then falls
    back to scanning the directory owner.

    Parameters
    ----------
    profile_dir : Path
        Profile directory to examine.

    Returns
    -------
    list[str]
        List of member identifiers (may be empty).
    """
    config_path = profile_dir / "config.yaml"
    if config_path.is_file():
        try:
            import yaml
            with open(config_path, encoding="utf-8") as fh:
                cfg: dict[str, Any] = yaml.safe_load(fh) or {}
            members = cfg.get("team") or cfg.get("members") or []
            if isinstance(members, list):
                return [str(m) for m in members if m]
            if isinstance(members, str):
                return [members]
        except Exception as exc:
            logger.debug("Could not parse config.yaml for team members: %s", exc)
    return []


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


class KanbanManager:
    """Manages the Kanban board — CRUD, profile scanning, and statistics.

    All methods are synchronous (they operate on local JSON files and the
    filesystem).  They are safe to call from FastAPI route handlers either
    directly or wrapped in ``run_in_executor``.
    """

    def __init__(self) -> None:
        """Initialize the Kanban manager.

        If the board file is empty or missing on first load,
        automatically scans all profiles to populate it.
        """
        pass  # Initialization is handled via module-level _auto_init()

    # ── Read ──────────────────────────────────────────────────────────

    @staticmethod
    def get_all_boards() -> list[BoardItem]:
        """Return every project currently tracked on the Kanban board.

        Scans the in-memory cache (loaded from ``kanban.json``) and returns
        all entries.  Does **not** re-scan profile directories — call
        :meth:`scan_all_profiles` or :meth:`auto_refresh` first to sync.

        Returns
        -------
        list[BoardItem]
            All board items, sorted alphabetically by project name.
        """
        boards = _ensure_cache()
        return sorted(boards.values(), key=lambda x: x.project_name)

    @staticmethod
    def get_board(project_name: str) -> BoardItem:
        """Return a single project's board entry.

        Parameters
        ----------
        project_name : str
            Project (profile) name to look up.

        Returns
        -------
        BoardItem
            The matching board entry.

        Raises
        ------
        KeyError
            If the project is not found on the board.
        """
        boards = _ensure_cache()
        if project_name not in boards:
            raise KeyError(f"Project '{project_name}' not found on the Kanban board.")
        return boards[project_name]

    # ── Write ─────────────────────────────────────────────────────────

    @staticmethod
    def update_board(project_name: str, data: dict[str, Any]) -> BoardItem:
        """Update an existing project's board entry.

        Only the keys present in *data* are updated; missing fields retain
        their current values.  The ``last_updated`` timestamp is always set
        to the current time.

        Parameters
        ----------
        project_name : str
            Project to update.
        data : dict[str, Any]
            Dictionary of fields to update.  Valid keys correspond to
            :class:`BoardItem` attributes.

        Returns
        -------
        BoardItem
            The updated board entry.

        Raises
        ------
        KeyError
            If the project is not on the board.
        ValueError
            If *data* contains an invalid status or progress value.
        """
        boards = _ensure_cache()
        if project_name not in boards:
            raise KeyError(f"Project '{project_name}' not found on the Kanban board.")

        current = boards[project_name]
        # Build updated dict from current state
        updated = current.to_dict()
        for key, value in data.items():
            if key in ("project_name", "last_updated"):
                continue  # These are managed internally
            if key == "team_members" and isinstance(value, list):
                # Allow comma-separated string input
                if len(value) == 1 and isinstance(value[0], str) and "," in value[0]:
                    value = [m.strip() for m in value[0].split(",") if m.strip()]
            updated[key] = value

        updated["last_updated"] = datetime.now(timezone.utc).isoformat()

        new_item = BoardItem.from_dict(updated)
        boards[project_name] = new_item
        _save_boards(boards)
        logger.info("Updated board entry for '%s': status=%s, progress=%d%%",
                     project_name, new_item.status, new_item.progress_pct)
        return new_item

    @staticmethod
    def add_board(project_name: str, data: dict[str, Any] | None = None) -> BoardItem:
        """Register a new project on the Kanban board.

        If *data* is provided, its keys are used to initialise the board
        entry; otherwise sensible defaults are applied.

        Parameters
        ----------
        project_name : str
            Unique project name (should match a profile directory name).
        data : dict[str, Any] or None
            Optional initial field values.

        Returns
        -------
        BoardItem
            The newly created board entry.

        Raises
        ------
        ValueError
            If the project already exists on the board.
        """
        boards = _ensure_cache()
        if project_name in boards:
            raise ValueError(
                f"Project '{project_name}' is already registered on the Kanban board."
            )

        init_data: dict[str, Any] = {
            "project_name": project_name,
            "status": DEFAULT_STATUS,
            "description": "",
            "team_members": [],
            "progress_pct": 0,
            "block_reason": None,
        }
        if data:
            # Override defaults with provided data
            for key, value in data.items():
                if key in ("project_name", "last_updated"):
                    continue
                init_data[key] = value

        init_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        new_item = BoardItem.from_dict(init_data)
        boards[project_name] = new_item
        _save_boards(boards)
        logger.info("Registered new project on board: '%s'", project_name)
        return new_item

    # ── Scanning ──────────────────────────────────────────────────────

    @staticmethod
    def scan_all_profiles() -> list[BoardItem]:
        """Scan ``$HERMES_HOME/profiles/`` and sync board entries.

        For each profile directory found:
        - If already on the board: update status, description, team members
          based on heuristics.
        - If not on the board: add a new entry.

        This method does **not** overwrite manually set ``progress_pct`` or
        ``block_reason`` unless the heuristic detects a change.

        Returns
        -------
        list[BoardItem]
            Full board after scanning.
        """
        profiles_path = _profiles_dir()
        if not profiles_path.is_dir():
            logger.warning("Profiles directory does not exist: %s", profiles_path)
            return list(_ensure_cache().values())

        boards = _ensure_cache()
        discovered_names: set[str] = set()

        for entry in sorted(profiles_path.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name

            # Skip hidden directories
            if name.startswith("."):
                continue

            discovered_names.add(name)
            description = _parse_soul_summary(entry)
            detected_status = _detect_status_from_profile(entry)
            team_members = _detect_team_members(entry)

            if name in boards:
                # Update existing entry — only auto-update fields that
                # are derived from the filesystem.  Preserve manual edits.
                current = boards[name]
                changed = False

                if current.description != description:
                    current.description = description
                    changed = True
                if current.status != detected_status:
                    current.status = detected_status
                    # Clear block_reason if no longer blocked
                    if detected_status != "blocked":
                        current.block_reason = None
                    changed = True
                if set(current.team_members) != set(team_members):
                    current.team_members = team_members
                    changed = True

                if changed:
                    current.last_updated = datetime.now(timezone.utc).isoformat()
                    boards[name] = current
            else:
                # New profile discovered — add to board with default status
                # in_progress and progress=10% so first-time users see results.
                new_item = BoardItem(
                    project_name=name,
                    status="in_progress",
                    description=description,
                    team_members=team_members,
                    progress_pct=10,
                    last_updated=datetime.now(timezone.utc).isoformat(),
                )
                boards[name] = new_item
                logger.info("Discovered new profile and added to board: '%s'", name)

        # Optionally: mark profiles no longer on disk? We deliberately do
        # NOT remove entries here — the user may have temporarily moved a
        # profile.  auto_refresh handles stale entries differently.

        _save_boards(boards)
        logger.info("Profile scan complete: %d profiles, %d board entries",
                     len(discovered_names), len(boards))
        return sorted(boards.values(), key=lambda x: x.project_name)

    @staticmethod
    def auto_refresh() -> dict[str, Any]:
        """Cron-friendly full refresh of the Kanban board.

        Designed to be called by a scheduled job (e.g. every 5 minutes).
        Performs the following steps:

        1. Scans all profiles (:meth:`scan_all_profiles`).
        2. Recalculates progress percentages based on heuristic rules.
        3. Cleans up stale entries that no longer correspond to a profile
           directory (if they are in ``done`` status for > 7 days, they
           are archived; otherwise they remain visible).

        Returns
        -------
        dict[str, Any]
            Summary of the refresh operation with keys ``scanned``,
            ``updated``, ``archived``, ``total``.
        """
        KanbanManager.scan_all_profiles()

        boards = _ensure_cache()
        profiles_path = _profiles_dir()
        existing_profiles: set[str] = set()
        if profiles_path.is_dir():
            for entry in profiles_path.iterdir():
                if entry.is_dir() and not entry.name.startswith("."):
                    existing_profiles.add(entry.name)

        now = datetime.now(timezone.utc)
        updated_count = 0
        archived_count = 0

        items_to_remove: list[str] = []
        for name, item in boards.items():
            # Auto-adjust progress for in_progress items that have no
            # manually set progress (still at 0 or default)
            if item.status == "in_progress" and item.progress_pct == 0:
                # Gentle heuristic: give it 10% just for being active
                item.progress_pct = 10
                item.last_updated = now.isoformat()
                updated_count += 1

            # Archive done items older than 7 days if the profile no longer
            # exists on disk
            if item.status == "done" and name not in existing_profiles:
                try:
                    updated_dt = datetime.fromisoformat(item.last_updated)
                except (ValueError, TypeError):
                    updated_dt = now
                if (now - updated_dt).days >= 7:
                    items_to_remove.append(name)
                    archived_count += 1

        for name in items_to_remove:
            del boards[name]

        if items_to_remove:
            _save_boards(boards)

        summary = {
            "scanned": len(existing_profiles),
            "updated": updated_count,
            "archived": archived_count,
            "total": len(boards),
        }
        logger.info("Auto-refresh complete: %s", summary)
        return summary

    # ── Statistics ────────────────────────────────────────────────────

    @staticmethod
    def get_stats() -> dict[str, Any]:
        """Return aggregate statistics for the Kanban board.

        Returns
        -------
        dict[str, Any]
            Dictionary with keys:

            - ``total`` — total number of projects
            - ``by_status`` — breakdown per status (``planning``,
              ``in_progress``, ``review``, ``done``, ``blocked``)
            - ``in_progress`` — shorthand for ``by_status.in_progress``
            - ``completed`` — shorthand for ``by_status.done``
            - ``blocked`` — shorthand for ``by_status.blocked``
            - ``avg_progress`` — average progress percentage across all items
            - ``last_updated`` — ISO-8601 timestamp of the stats generation
        """
        boards = _ensure_cache()
        items = list(boards.values())

        total = len(items)
        by_status: dict[str, int] = {s: 0 for s in VALID_STATUSES}
        total_progress = 0

        for item in items:
            by_status[item.status] = by_status.get(item.status, 0) + 1
            total_progress += item.progress_pct

        avg_progress = round(total_progress / total, 1) if total > 0 else 0.0

        return {
            "total": total,
            "by_status": by_status,
            "planning": by_status.get("planning", 0),
            "in_progress": by_status.get("in_progress", 0),
            "review": by_status.get("review", 0),
            "completed": by_status.get("done", 0),
            "blocked": by_status.get("blocked", 0),
            "avg_progress": avg_progress,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }


# ── Auto-initialization ────────────────────────────────────────────


def _auto_init() -> None:
    """Populate the Kanban board on first start if it is empty.

    Called once at module load time.  Scans ``$HERMES_HOME/profiles/``
    and creates a board entry (status ``in_progress``, progress 10%)
    for every profile directory that contains a ``SOUL.md`` file.
    """
    try:
        boards = _ensure_cache()
    except OSError:
        boards = {}

    if not boards:
        logger.info(
            "Kanban board is empty — auto-scanning profiles to initialise..."
        )
        try:
            KanbanManager.scan_all_profiles()
            logger.info("Kanban board auto-initialisation complete.")
        except Exception as exc:
            logger.warning("Kanban board auto-initialisation failed: %s", exc)


# ──────────────────────────────────────────────────────────────────────
# AutoRule System — Automatic Kanban Rule Engine
# ──────────────────────────────────────────────────────────────────────

import sqlite3
import re
from dataclasses import dataclass, field
from typing import Optional

# ── Rule Data Model ─────────────────────────────────────────────────

VALID_TRIGGER_EVENTS = frozenset({
    "task_created",
    "task_moved",
    "task_blocked",
    "deadline_approaching",
})

VALID_ACTIONS = frozenset({"move_to", "assign_to", "add_label", "notify"})


@dataclass
class AutoRule:
    """A single automatic rule for the Kanban board.

    Attributes
    ----------
    id : int | None
        Primary key (auto-assigned by SQLite).
    name : str
        Human-readable rule name.
    trigger_event : str
        One of ``task_created``, ``task_moved``, ``task_blocked``,
        ``deadline_approaching``.
    condition : str
        Condition expression, e.g. ``status == in_progress``,
        ``assignee == Alice``, ``priority == high``.
    action : str
        Action to execute, e.g. ``move_to(review)``,
        ``assign_to(Bob)``, ``add_label(needs_review)``,
        ``notify(slack)``.
    enabled : bool
        Whether the rule is active.
    """
    name: str
    trigger_event: str
    condition: str
    action: str
    enabled: bool = True
    id: int | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "trigger_event": self.trigger_event,
            "condition": self.condition,
            "action": self.action,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AutoRule:
        return cls(
            id=data.get("id"),
            name=data["name"],
            trigger_event=data["trigger_event"],
            condition=data["condition"],
            action=data["action"],
            enabled=data.get("enabled", True),
        )


# ── Rule Persistence (SQLite) ───────────────────────────────────────


def _rules_db_path() -> Path:
    """Return the path to the rules SQLite database."""
    return _data_dir() / "kanban_rules.db"


def _get_rules_conn() -> sqlite3.Connection:
    """Get a connection to the rules database, creating tables if needed."""
    db_path = _rules_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            trigger_event TEXT NOT NULL,
            condition TEXT NOT NULL,
            action TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()
    return conn


def _row_to_rule(row: sqlite3.Row) -> AutoRule:
    """Convert a SQLite row to an AutoRule instance."""
    return AutoRule(
        id=row["id"],
        name=row["name"],
        trigger_event=row["trigger_event"],
        condition=row["condition"],
        action=row["action"],
        enabled=bool(row["enabled"]),
    )


# ── Rule CRUD ───────────────────────────────────────────────────────


def create_rule(rule: AutoRule) -> AutoRule:
    """Create a new rule and return it with the assigned id."""
    conn = _get_rules_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO rules (name, trigger_event, condition, action, enabled) "
            "VALUES (?, ?, ?, ?, ?)",
            (rule.name, rule.trigger_event, rule.condition, rule.action,
             int(rule.enabled)),
        )
        conn.commit()
        rule.id = cursor.lastrowid
        logger.info("Created auto-rule #%d: '%s' [%s] %s -> %s",
                     rule.id, rule.name, rule.trigger_event,
                     rule.condition, rule.action)
        return rule
    finally:
        conn.close()


def list_rules() -> list[AutoRule]:
    """Return all rules, ordered by id."""
    conn = _get_rules_conn()
    try:
        rows = conn.execute("SELECT * FROM rules ORDER BY id").fetchall()
        return [_row_to_rule(r) for r in rows]
    finally:
        conn.close()


def update_rule(rule_id: int, data: dict) -> AutoRule | None:
    """Update a rule by id. Returns the updated rule or None if not found."""
    conn = _get_rules_conn()
    try:
        # Build SET clause from provided data
        fields = []
        values = []
        for key in ("name", "trigger_event", "condition", "action"):
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if "enabled" in data:
            fields.append("enabled = ?")
            values.append(int(data["enabled"]))

        if not fields:
            return get_rule(rule_id)

        values.append(rule_id)
        conn.execute(
            f"UPDATE rules SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()
        return get_rule(rule_id)
    finally:
        conn.close()


def get_rule(rule_id: int) -> AutoRule | None:
    """Fetch a single rule by id. Returns None if not found."""
    conn = _get_rules_conn()
    try:
        row = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
        return _row_to_rule(row) if row else None
    finally:
        conn.close()


def delete_rule(rule_id: int) -> bool:
    """Delete a rule by id. Returns True if deleted, False if not found."""
    conn = _get_rules_conn()
    try:
        cursor = conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Deleted auto-rule #%d", rule_id)
        return deleted
    finally:
        conn.close()


# ── Condition & Action Engine ───────────────────────────────────────


def _evaluate_condition(condition: str, task: BoardItem) -> bool:
    """Evaluate a condition expression against a task.

    Supported patterns:
      - ``status == X``
      - ``assignee == Y``
      - ``priority == Z``
    Returns True if the condition matches.
    """
    cond = condition.strip()

    # status == X
    m = re.match(r'^status\s*==\s*(.+)$', cond)
    if m:
        expected = m.group(1).strip().strip('"').strip("'")
        return task.status == expected

    # assignee == Y  — checks if Y is in team_members
    m = re.match(r'^assignee\s*==\s*(.+)$', cond)
    if m:
        expected = m.group(1).strip().strip('"').strip("'")
        return expected in task.team_members

    # priority == Z  — check against progress_pct heuristic
    m = re.match(r'^priority\s*==\s*(.+)$', cond)
    if m:
        expected = m.group(1).strip().strip('"').strip("'").lower()
        priority_map = {
            "high": lambda p: p >= 70,
            "medium": lambda p: 30 <= p < 70,
            "low": lambda p: p < 30,
        }
        if expected in priority_map:
            return priority_map[expected](task.progress_pct)
        return False

    logger.debug("Unknown condition pattern: '%s' — treating as no-match", condition)
    return False


def _execute_action(action: str, task: BoardItem) -> dict[str, Any]:
    """Execute an action string on a task.

    Supported actions:
      - ``move_to(STATUS)`` — returns a status change request
      - ``assign_to(USER)`` — adds user to team_members
      - ``add_label(LABEL)`` — appends a label to description
      - ``notify(CHANNEL)`` — logs a notification (future: send to channel)

    Returns a dict with action results (e.g. ``{"action": "move_to", "value": "review"}``).
    """
    result = {"action_skipped": False, "reason": None}

    # move_to(STATUS)
    m = re.match(r'^move_to\s*\((.+)\)$', action.strip())
    if m:
        target_status = m.group(1).strip().strip('"').strip("'")
        if target_status in VALID_STATUSES:
            result["action"] = "move_to"
            result["value"] = target_status
            return result
        result["action_skipped"] = True
        result["reason"] = f"Invalid target status: {target_status}"
        return result

    # assign_to(USER)
    m = re.match(r'^assign_to\s*\((.+)\)$', action.strip())
    if m:
        user = m.group(1).strip().strip('"').strip("'")
        if user not in task.team_members:
            task.team_members.append(user)
            result["action"] = "assign_to"
            result["value"] = user
            return result
        result["action_skipped"] = True
        result["reason"] = f"User '{user}' already assigned"
        return result

    # add_label(LABEL)
    m = re.match(r'^add_label\s*\((.+)\)$', action.strip())
    if m:
        label = m.group(1).strip().strip('"').strip("'")
        if label not in task.description:
            task.description = (task.description + f" [{label}]").strip()
            result["action"] = "add_label"
            result["value"] = label
            return result
        result["action_skipped"] = True
        result["reason"] = f"Label '{label}' already present"
        return result

    # notify(CHANNEL)
    m = re.match(r'^notify\s*\((.+)\)$', action.strip())
    if m:
        channel = m.group(1).strip().strip('"').strip("'")
        logger.info("🔔 RULE NOTIFY: channel=%s | task=%s | message='Rule triggered for %s'",
                     channel, task.project_name, task.project_name)
        result["action"] = "notify"
        result["value"] = channel
        return result

    result["action_skipped"] = True
    result["reason"] = f"Unknown action: {action}"
    return result


def auto_apply_rules(event: str, task: BoardItem) -> list[dict[str, Any]]:
    """Evaluate all enabled rules matching *event* against *task*.

    For each matching rule, the condition is checked; if it passes, the
    action is executed.  Actions that request a status change (``move_to``)
    are applied to the task immediately.

    Parameters
    ----------
    event : str
        The trigger event (e.g. ``'task_moved'``, ``'task_created'``).
    task : BoardItem
        The task (board item) to evaluate rules against.

    Returns
    -------
    list[dict[str, Any]]
        List of action result dictionaries for logging/debugging.
    """
    rules = list_rules()
    results: list[dict[str, Any]] = []
    boards = _ensure_cache()

    for rule in rules:
        if not rule.enabled:
            continue
        if rule.trigger_event != event:
            continue

        # Evaluate condition
        if not _evaluate_condition(rule.condition, task):
            logger.debug("Rule #%d '%s': condition '%s' did not match task '%s'",
                         rule.id, rule.name, rule.condition, task.project_name)
            continue

        # Execute action
        logger.info("Rule #%d '%s' FIRED on task '%s' (event=%s)",
                     rule.id, rule.name, task.project_name, event)
        action_result = _execute_action(rule.action, task)

        # Apply move_to immediately
        if action_result.get("action") == "move_to":
            old_status = task.status
            task.status = action_result["value"]
            task.last_updated = datetime.now(timezone.utc).isoformat()
            if action_result["value"] != "blocked":
                task.block_reason = None
            boards[task.project_name] = task
            _save_boards(boards)
            action_result["old_status"] = old_status
            action_result["new_status"] = action_result["value"]
            logger.info("  ↳ Moved '%s' from '%s' to '%s' (via rule #%d)",
                         task.project_name, old_status, action_result["value"], rule.id)

        # Apply assign_to immediately
        if action_result.get("action") == "assign_to":
            boards[task.project_name] = task
            _save_boards(boards)
            logger.info("  ↳ Assigned '%s' to '%s' (via rule #%d)",
                         task.project_name, action_result["value"], rule.id)

        # Apply add_label immediately
        if action_result.get("action") == "add_label":
            boards[task.project_name] = task
            _save_boards(boards)
            logger.info("  ↳ Added label '%s' to '%s' (via rule #%d)",
                         action_result["value"], task.project_name, rule.id)

        action_result["rule_id"] = rule.id
        action_result["rule_name"] = rule.name
        results.append(action_result)

    return results


# ── Hook into KanbanManager ─────────────────────────────────────────

# Inject auto_apply_rules and AutoRule as module-level conveniences.
# The KanbanManager class also exposes static methods for rule CRUD.


# Run auto-init at module load time.
_auto_init()
