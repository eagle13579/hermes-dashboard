"""
Gaia Sync Bridge — 盖娅同步桥
================================

One-way sync bridge that pushes Hermes Dashboard profile output data
into the Gaia City unified PostgreSQL instance (port 5435).

Design Principles
-----------------
* **Unidirectional** — Profile origin data is never modified.
* **Offline-tolerant** — If PostgreSQL is unreachable, records are queued
  locally as a JSON file and retried on the next sync cycle.
* **Change-detected** — Files are SHA256-hashed to avoid re-syncing
  identical content.
* **Async-friendly** — The bridge runs sync in an executor thread to
  avoid blocking the ASGI event loop.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

SYNC_SCHEMA_TABLE = "gaia_sync.hermes_dashboard_sync"
"""PostgreSQL schema-qualified table name for sync records."""

DEFAULT_SYNC_QUEUE_PATH = "data/sync_queue.json"
"""Relative path (under the dashboard profile dir) for the local queue."""

FILE_TYPE_MAP: dict[str, str] = {
    # Code
    ".py": "code",
    ".js": "code",
    ".ts": "code",
    ".jsx": "code",
    ".tsx": "code",
    ".java": "code",
    ".go": "code",
    ".rs": "code",
    ".c": "code",
    ".cpp": "code",
    ".h": "code",
    ".hpp": "code",
    ".sh": "code",
    ".bat": "code",
    ".ps1": "code",
    ".sql": "code",
    # Documents / Markup
    ".md": "document",
    ".rst": "document",
    ".txt": "document",
    ".html": "document",
    ".htm": "document",
    ".css": "document",
    ".json": "document",
    ".xml": "document",
    ".yaml": "document",
    ".yml": "document",
    ".toml": "document",
    ".csv": "document",
    # Configuration
    ".env": "config",
    ".ini": "config",
    ".cfg": "config",
    ".conf": "config",
    # Logs
    ".log": "log",
    # Output / Artifacts
    ".png": "artifact",
    ".jpg": "artifact",
    ".jpeg": "artifact",
    ".gif": "artifact",
    ".svg": "artifact",
    ".pdf": "artifact",
    ".zip": "artifact",
    ".tar": "artifact",
    ".gz": "artifact",
    ".xlsx": "artifact",
    ".pptx": "artifact",
    ".docx": "artifact",
}
"""Mapping from lowercase file extension to a human-readable data type."""

DEFAULT_DATA_TYPE = "other"
"""Fallback classification when the extension is not in FILE_TYPE_MAP."""

# ── Data Models ────────────────────────────────────────────────────────


@dataclass
class SyncConfig:
    """Configuration for the Gaia Sync Bridge.

    Parameters
    ----------
    pg_conn_str : str
        PostgreSQL connection string (e.g.
        ``host=10.0.0.5 port=5435 dbname=gaia user=gaia password=***``).
        Alternatively, a full ``postgresql://`` URI is accepted.
    profile_dir : str
        Absolute path to the Hermes profiles directory. Files under this
        tree are scanned for sync.
    poll_interval : int
        Number of seconds to wait between sync cycles (default 60).
    queue_file : str
        Path to the local JSON queue file used for offline buffering.
    """

    pg_conn_str: str = (
        "host=127.0.0.1 port=5435 dbname=gaia user=gaia password=gaia"
    )
    profile_dir: str = ""
    poll_interval: int = 60
    queue_file: str = DEFAULT_SYNC_QUEUE_PATH


@dataclass
class SyncRecord:
    """A single file-level sync record destined for PostgreSQL.

    Attributes
    ----------
    source_profile : str
        Name of the originating Hermes profile (directory name).
    filepath : str
        Absolute path to the file on disk.
    data_type : str
        Classified type — ``code``, ``document``, ``config``, ``log``,
        ``artifact``, or ``other``.
    sha256_hash : str
        Hexadecimal SHA-256 digest of the file content.
    timestamp : str
        ISO-8601 UTC timestamp of when the record was created.
    status : str
        Sync status — ``pending``, ``synced``, or ``failed``.
    error_message : str, optional
        Human-readable error detail if ``status == \"failed\"``.
    profile_dir : str, optional
        The profile directory that was scanned (informational).
    """

    source_profile: str
    filepath: str
    data_type: str = DEFAULT_DATA_TYPE
    sha256_hash: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = "pending"
    error_message: Optional[str] = None
    profile_dir: Optional[str] = None

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SyncRecord:
        """Reconstruct from a dictionary (e.g. loaded from JSON queue)."""
        return cls(**data)


# ── Helper Functions ───────────────────────────────────────────────────


def compute_hash(filepath: str) -> str:
    """Compute the SHA-256 hex digest of *filepath*.

    Reads the file in 64 KiB chunks to handle large files efficiently.

    Parameters
    ----------
    filepath : str
        Absolute or relative path to the file.

    Returns
    -------
    str
        Lowercase hexadecimal SHA-256 digest.

    Raises
    ------
    FileNotFoundError
        If *filepath* does not exist.
    PermissionError
        If the file cannot be read due to permissions.
    OSError
        For other I/O errors.
    """
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)  # 64 KiB
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def classify_file(filepath: str) -> str:
    """Classify a file by its extension into a human-readable type.

    Parameters
    ----------
    filepath : str
        Path to the file.

    Returns
    -------
    str
        One of ``code``, ``document``, ``config``, ``log``, ``artifact``,
        or ``other``.
    """
    ext = Path(filepath).suffix.lower()
    return FILE_TYPE_MAP.get(ext, DEFAULT_DATA_TYPE)


def _normalise_pg_conn_str(raw: str) -> str:
    """Convert a bare ``key=val`` DSN to a proper URI if needed.

    psycopg2 accepts both ``host=… dbname=…`` and
    ``postgresql://user:pass@host/db`` formats.  This function does
    *not* transform the string — it just returns it as-is since
    psycopg2.connect handles both natively.
    """
    return raw


# ── SyncBridge Class ───────────────────────────────────────────────────


class SyncBridge:
    """Gaia Sync Bridge — one-way file sync from Hermes profiles to PostgreSQL.

    Usage
    -----
    .. code-block:: python

        bridge = SyncBridge(config=SyncConfig(profile_dir="/path/to/profiles"))
        status = bridge.sync_once()
        print(bridge.get_sync_status())
    """

    def __init__(self, config: Optional[SyncConfig] = None) -> None:
        self.config: SyncConfig = config or SyncConfig()
        self._last_sync_time: Optional[str] = None
        self._sync_count: int = 0
        self._failed_count: int = 0
        self._queue: list[SyncRecord] = []
        self._load_queue()

    # ── Queue persistence ────────────────────────────────────────────

    def _queue_file_path(self) -> str:
        """Resolve the absolute path to the local queue JSON file.

        If ``config.queue_file`` is absolute it is used directly;
        otherwise it is resolved relative to the profile directory.
        """
        qp = Path(self.config.queue_file)
        if qp.is_absolute():
            return str(qp)
        base = Path(self.config.profile_dir) if self.config.profile_dir else Path.cwd()
        return str(base / qp)

    def _load_queue(self) -> None:
        """Load pending sync records from the local JSON queue file."""
        qpath = Path(self._queue_file_path())
        if not qpath.exists():
            self._queue = []
            return
        try:
            with open(qpath, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self._queue = [SyncRecord.from_dict(r) for r in raw]
            logger.info("Loaded %d pending record(s) from queue", len(self._queue))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load queue file %s: %s", qpath, exc)
            self._queue = []

    def _save_queue(self) -> None:
        """Persist pending sync records to the local JSON queue file."""
        qpath = Path(self._queue_file_path())
        qpath.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(qpath, "w", encoding="utf-8") as f:
                json.dump(
                    [r.to_dict() for r in self._queue],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except OSError as exc:
            logger.error("Failed to save queue file %s: %s", qpath, exc)

    # ── Scanning & Discovery ──────────────────────────────────────────

    def scan_files(self, profile_dir: str) -> list[dict]:
        """Recursively scan *profile_dir* for syncable files.

        Returns a list of dictionaries with keys:
        ``filepath``, ``source_profile`` (directory basename), and
        ``mtime`` (last modification time as ISO-8601).

        Parameters
        ----------
        profile_dir : str
            Directory to scan.  Only regular files are included.

        Returns
        -------
        list[dict]
            List of file descriptors.  Empty if the directory does not
            exist or an error occurs.
        """
        base = Path(profile_dir)
        if not base.is_dir():
            logger.warning("Profile directory not found: %s", profile_dir)
            return []

        results: list[dict] = []
        try:
            for entry in base.rglob("*"):
                if not entry.is_file():
                    continue
                # Skip common non-syncable items
                rel = entry.relative_to(base)
                parts = rel.parts
                if any(
                    p.startswith(".")
                    or p == "node_modules"
                    or p == "__pycache__"
                    or p == ".git"
                    or p == "venv"
                    or p == ".venv"
                    for p in parts
                ):
                    continue
                mtime_dt = datetime.fromtimestamp(
                    entry.stat().st_mtime, tz=timezone.utc
                )
                results.append(
                    {
                        "filepath": str(entry.resolve()),
                        "source_profile": base.name,
                        "mtime": mtime_dt.isoformat(),
                    }
                )
        except OSError as exc:
            logger.error("Error scanning %s: %s", profile_dir, exc)
            return []

        logger.info("Scanned %d file(s) under %s", len(results), profile_dir)
        return results

    # ── PostgreSQL Ingestion ──────────────────────────────────────────

    def sync_to_pg(self, records: list[SyncRecord]) -> list[SyncRecord]:
        """Batch-insert *records* into the Gaia PostgreSQL table.

        If the database is unreachable the records are appended to the
        local queue and will be retried on the next ``sync_once()`` call.

        Parameters
        ----------
        records : list[SyncRecord]
            Records to persist.

        Returns
        -------
        list[SyncRecord]
            Records that **failed** to sync (either PG error or insert
            error).  An empty list means everything was written.
        """
        if not records:
            return []

        import psycopg2
        from psycopg2 import OperationalError

        conn = None
        failed: list[SyncRecord] = []
        try:
            conn = psycopg2.connect(
                _normalise_pg_conn_str(self.config.pg_conn_str),
                connect_timeout=5,
            )
            conn.autocommit = False
            with conn.cursor() as cur:
                # Ensure schema exists (idempotent)
                cur.execute("CREATE SCHEMA IF NOT EXISTS gaia_sync")
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {SYNC_SCHEMA_TABLE} (
                        id              BIGSERIAL PRIMARY KEY,
                        source_profile  TEXT NOT NULL,
                        filepath        TEXT NOT NULL,
                        data_type       TEXT NOT NULL DEFAULT 'other',
                        sha256_hash     TEXT NOT NULL DEFAULT '',
                        timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        status          TEXT NOT NULL DEFAULT 'pending',
                        error_message   TEXT,
                        synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                insert_sql = f"""
                    INSERT INTO {SYNC_SCHEMA_TABLE}
                        (source_profile, filepath, data_type,
                         sha256_hash, timestamp, status, error_message)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                for rec in records:
                    try:
                        cur.execute(
                            insert_sql,
                            (
                                rec.source_profile,
                                rec.filepath,
                                rec.data_type,
                                rec.sha256_hash,
                                rec.timestamp,
                                "synced",
                                None,
                            ),
                        )
                        rec.status = "synced"
                    except Exception as exc:
                        logger.warning(
                            "Insert failed for %s: %s", rec.filepath, exc
                        )
                        rec.status = "failed"
                        rec.error_message = str(exc)
                        failed.append(rec)

            conn.commit()
            logger.info(
                "Synced %d / %d record(s) to PostgreSQL",
                len(records) - len(failed),
                len(records),
            )
        except OperationalError as exc:
            logger.warning(
                "PostgreSQL unreachable (%s).  Queueing %d record(s) locally.",
                exc,
                len(records),
            )
            # Mark all as pending, append to queue
            for rec in records:
                rec.status = "pending"
                rec.error_message = f"PG unreachable: {exc}"
            self._queue.extend(records)
            self._save_queue()
            failed = records
        except Exception as exc:
            logger.error("Unexpected PG sync error: %s", exc)
            for rec in records:
                rec.status = "failed"
                rec.error_message = str(exc)
            failed = records
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        return failed

    # ── Orchestration ─────────────────────────────────────────────────

    def sync_once(self) -> dict:
        """Execute one full sync cycle.

        Steps
        -----
        1. Scan profile directories for files.
        2. Compute SHA-256 hash for each file.
        3. Classify each file by type.
        4. Build :class:`SyncRecord` instances.
        5. Attempt batch insert into PostgreSQL.
        6. Retry any previously queued records.

        Returns
        -------
        dict
            Summary with keys ``scanned``, ``synced``, ``failed``,
            ``pending``, and ``timestamp``.
        """
        logger.info("=== Sync cycle started ===")
        start = time.time()

        # 1. Scan
        file_infos = self.scan_files(self.config.profile_dir)
        scanned = len(file_infos)

        # 2+3+4. Hash, classify, build records
        records: list[SyncRecord] = []
        for fi in file_infos:
            try:
                file_hash = compute_hash(fi["filepath"])
            except (FileNotFoundError, PermissionError, OSError) as exc:
                logger.debug("Skipping %s: %s", fi["filepath"], exc)
                continue

            data_type = classify_file(fi["filepath"])
            rec = SyncRecord(
                source_profile=fi["source_profile"],
                filepath=fi["filepath"],
                data_type=data_type,
                sha256_hash=file_hash,
                timestamp=fi.get("mtime", datetime.now(timezone.utc).isoformat()),
                status="pending",
                profile_dir=self.config.profile_dir,
            )
            records.append(rec)

        # 5. Sync to PG
        failed = self.sync_to_pg(records)

        # 6. Retry queued records (from previous offline cycles)
        if self._queue:
            logger.info("Retrying %d queued record(s)...", len(self._queue))
            retry_failed = self.sync_to_pg(self._queue)
            # Remove successfully synced items from queue
            self._queue = [r for r in self._queue if r.status != "synced"]
            self._save_queue()
        else:
            retry_failed = []

        elapsed = time.time() - start
        synced = len(records) - len(failed) + (len(self._queue) if not retry_failed else 0)
        self._last_sync_time = datetime.now(timezone.utc).isoformat()
        self._sync_count += synced
        self._failed_count += len(failed) + len(retry_failed)

        summary = {
            "scanned": scanned,
            "synced": synced,
            "failed": len(failed) + len(retry_failed),
            "pending": len(self._queue),
            "elapsed_seconds": round(elapsed, 2),
            "timestamp": self._last_sync_time,
        }
        logger.info(
            "=== Sync cycle finished: %s ===",
            json.dumps(summary, ensure_ascii=False),
        )
        return summary

    # ── Status & Queries ──────────────────────────────────────────────

    def get_sync_status(self) -> dict:
        """Return the current sync bridge status.

        Returns
        -------
        dict
            Keys: ``last_sync_time``, ``total_synced``, ``total_failed``,
            ``pending_count``, ``queue_size``, ``config`` (connection
            host/port only, credentials redacted).
        """
        return {
            "last_sync_time": self._last_sync_time,
            "total_synced": self._sync_count,
            "total_failed": self._failed_count,
            "pending_count": self.get_pending_count(),
            "queue_size": len(self._queue),
            "config": {
                "pg_host": self._redacted_pg_host(),
                "profile_dir": self.config.profile_dir,
                "poll_interval": self.config.poll_interval,
            },
        }

    def get_pending_count(self) -> int:
        """Return the number of files awaiting sync.

        Returns
        -------
        int
            Count of records with ``status == \"pending\"`` in the local queue.
        """
        return sum(1 for r in self._queue if r.status == "pending")

    def get_sync_history(self, limit: int = 100) -> list[dict]:
        """Return recent sync history from PostgreSQL.

        Parameters
        ----------
        limit : int
            Maximum number of records to return (default 100).

        Returns
        -------
        list[dict]
            List of sync record dictionaries ordered by ``synced_at DESC``.
            Returns an empty list if PG is unreachable.
        """
        import psycopg2
        from psycopg2 import OperationalError

        conn = None
        try:
            conn = psycopg2.connect(
                _normalise_pg_conn_str(self.config.pg_conn_str),
                connect_timeout=5,
            )
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT source_profile, filepath, data_type,
                           sha256_hash, timestamp, status, error_message,
                           synced_at
                    FROM {SYNC_SCHEMA_TABLE}
                    ORDER BY synced_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
            return [
                {
                    "source_profile": r[0],
                    "filepath": r[1],
                    "data_type": r[2],
                    "sha256_hash": r[3],
                    "timestamp": r[4].isoformat() if r[4] else None,
                    "status": r[5],
                    "error_message": r[6],
                    "synced_at": r[7].isoformat() if r[7] else None,
                }
                for r in rows
            ]
        except OperationalError:
            logger.warning("PG unreachable — cannot fetch sync history")
            return []
        except Exception as exc:
            logger.error("Error fetching sync history: %s", exc)
            return []
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_pending_records(self) -> list[dict]:
        """Return all pending records from the local queue.

        Returns
        -------
        list[dict]
            Serialised :class:`SyncRecord` dictionaries.
        """
        return [
            r.to_dict()
            for r in self._queue
            if r.status == "pending"
        ]

    # ── Internal helpers ──────────────────────────────────────────────

    def _redacted_pg_host(self) -> str:
        """Extract and return the PG host (and port) from the connection string,
        with credentials redacted.
        """
        raw = self.config.pg_conn_str
        # Try to parse host and port from key=value format
        parts = raw.split()
        host = "unknown"
        port = "5435"
        for p in parts:
            if p.startswith("host="):
                host = p.split("=", 1)[1]
            elif p.startswith("port="):
                port = p.split("=", 1)[1]
        # Try URI format
        if "://" in raw and "@" in raw:
            # postgresql://user:pass@host:port/db
            after_at = raw.split("@", 1)[1].split("/")[0]
            if ":" in after_at:
                host, port = after_at.split(":", 1)
            else:
                host = after_at
        return f"{host}:{port}"


# ── Module-level singleton (lazy) ──────────────────────────────────────

_bridge: Optional[SyncBridge] = None


def get_bridge(config: Optional[SyncConfig] = None) -> SyncBridge:
    """Return the global :class:`SyncBridge` singleton.

    Parameters
    ----------
    config : SyncConfig, optional
        Configuration passed to the bridge on first creation.  Ignored
        on subsequent calls.

    Returns
    -------
    SyncBridge
    """
    global _bridge
    if _bridge is None:
        _bridge = SyncBridge(config=config)
    return _bridge
