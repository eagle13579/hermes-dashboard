#!/usr/bin/env python3
"""Hermes Dashboard — PostgreSQL schema creation script.

Creates all database tables required by the Hermes Dashboard backend,
using raw SQL and reading connection parameters from ``config.settings``.

Usage
-----
    # Preview what would be created (safe)
    python scripts/create_pg_schema.py --dry-run

    # Actually create tables
    python scripts/create_pg_schema.py

    # Specify a different schema (default: from settings)
    python scripts/create_pg_schema.py --schema custom_schema

Exit codes
----------
0   All tables created / verified successfully.
1   Some tables failed (partial success — see stderr).
2   All operations failed (connection / permission / schema error).

Environment
-----------
Uses ``config.settings`` which reads from ``.env`` or environment variables.
Required vars: ``PG_HOST``, ``PG_PORT``, ``PG_USER``, ``PG_PASSWORD``, ``PG_DATABASE``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

logger = logging.getLogger("create_pg_schema")

# ──────────────────────────────────────────────────────────────────────
# Schema DDL — ordered so foreign-key dependencies come after parents
# ──────────────────────────────────────────────────────────────────────

TABLES: list[dict[str, Any]] = [
    # ── 1. Profiles ──────────────────────────────────────────────────
    {
        "name": "profiles",
        "description": "Hermes agent profile registry.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.profiles (
            name            VARCHAR(128)    PRIMARY KEY,
            is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
            soul_summary    TEXT,
            config_json     JSONB           DEFAULT '{}'::jsonb,
            running         BOOLEAN         NOT NULL DEFAULT FALSE,
            pid             INTEGER,
            port            INTEGER,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_profiles_is_active ON {schema}.profiles (is_active);",
            "CREATE INDEX IF NOT EXISTS idx_profiles_updated_at ON {schema}.profiles (updated_at DESC);",
        ],
    },
    # ── 2. Employees (Legion) ────────────────────────────────────────
    {
        "name": "employees",
        "description": "Registered AI 数智军团 employees.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.employees (
            employee_id     VARCHAR(128)    PRIMARY KEY,
            name            VARCHAR(256)    NOT NULL,
            role            VARCHAR(64)     NOT NULL,
            skill_tags      TEXT[]          NOT NULL DEFAULT '{}',
            personality     TEXT,
            level           VARCHAR(32)     DEFAULT '',
            department      VARCHAR(128)    DEFAULT '',
            status          VARCHAR(32)     NOT NULL DEFAULT 'active',
            soul_level      VARCHAR(32)     NOT NULL DEFAULT 'shell',
            has_awakening   BOOLEAN         NOT NULL DEFAULT FALSE,
            mental_models   JSONB           DEFAULT '[]'::jsonb,
            emotional_anchors JSONB         DEFAULT '[]'::jsonb,
            capabilities    TEXT[]          DEFAULT '{}',
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_employees_role ON {schema}.employees (role);",
            "CREATE INDEX IF NOT EXISTS idx_employees_status ON {schema}.employees (status);",
            "CREATE INDEX IF NOT EXISTS idx_employees_soul_level ON {schema}.employees (soul_level);",
            "CREATE INDEX IF NOT EXISTS idx_employees_skill_tags ON {schema}.employees USING GIN (skill_tags);",
        ],
    },
    # ── 3. Employee Tasks ─────────────────────────────────────────────
    {
        "name": "employee_tasks",
        "description": "Tasks assigned to Legion employees.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.employee_tasks (
            task_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id     VARCHAR(128)    NOT NULL REFERENCES {schema}.employees(employee_id) ON DELETE CASCADE,
            task            TEXT            NOT NULL,
            priority        INTEGER         NOT NULL DEFAULT 3 CHECK (priority >= 1 AND priority <= 5),
            deadline        TIMESTAMPTZ,
            status          VARCHAR(32)     NOT NULL DEFAULT 'pending',
            result          TEXT,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            completed_at    TIMESTAMPTZ
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_emp_tasks_employee ON {schema}.employee_tasks (employee_id);",
            "CREATE INDEX IF NOT EXISTS idx_emp_tasks_status ON {schema}.employee_tasks (status);",
            "CREATE INDEX IF NOT EXISTS idx_emp_tasks_priority ON {schema}.employee_tasks (priority DESC);",
        ],
    },
    # ── 4. Kanban Board ───────────────────────────────────────────────
    {
        "name": "kanban_board",
        "description": "Project board items tracking profile/project status.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.kanban_board (
            project_name    VARCHAR(256)    PRIMARY KEY,
            status          VARCHAR(32)     NOT NULL DEFAULT 'planning'
                                CHECK (status IN ('planning','in_progress','review','done','blocked')),
            description     TEXT            NOT NULL DEFAULT '',
            team_members    TEXT[]          NOT NULL DEFAULT '{}',
            progress_pct    INTEGER         NOT NULL DEFAULT 0 CHECK (progress_pct >= 0 AND progress_pct <= 100),
            block_reason    TEXT,
            priority        VARCHAR(32),
            last_updated    TIMESTAMPTZ     NOT NULL DEFAULT now(),
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_kanban_status ON {schema}.kanban_board (status);",
            "CREATE INDEX IF NOT EXISTS idx_kanban_priority ON {schema}.kanban_board (priority);",
            "CREATE INDEX IF NOT EXISTS idx_kanban_last_updated ON {schema}.kanban_board (last_updated DESC);",
        ],
    },
    # ── 5. Skills ─────────────────────────────────────────────────────
    {
        "name": "skills",
        "description": "Skill catalog — published and draft skills.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.skills (
            name            VARCHAR(256)    PRIMARY KEY,
            description     TEXT            NOT NULL DEFAULT '',
            category        VARCHAR(64)     NOT NULL DEFAULT 'general',
            content         TEXT,
            path            TEXT,
            is_published    BOOLEAN         NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_skills_category ON {schema}.skills (category);",
            "CREATE INDEX IF NOT EXISTS idx_skills_published ON {schema}.skills (is_published);",
        ],
    },
    # ── 6. Skill Assignments (profile → skill) ───────────────────────
    {
        "name": "skill_assignments",
        "description": "Which skills are enabled for which profiles.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.skill_assignments (
            profile_name    VARCHAR(128)    NOT NULL REFERENCES {schema}.profiles(name) ON DELETE CASCADE,
            skill_name      VARCHAR(256)    NOT NULL REFERENCES {schema}.skills(name) ON DELETE CASCADE,
            enabled         BOOLEAN         NOT NULL DEFAULT TRUE,
            assigned_at     TIMESTAMPTZ     NOT NULL DEFAULT now(),
            PRIMARY KEY (profile_name, skill_name)
        );
        """,
        "indexes": [],
    },
    # ── 7. Joint Operations ───────────────────────────────────────────
    {
        "name": "joint_operations",
        "description": "Multi-profile joint operation definitions and results.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.joint_operations (
            op_id           VARCHAR(64)     PRIMARY KEY,
            name            VARCHAR(256)    NOT NULL,
            description     TEXT            NOT NULL DEFAULT '',
            status          VARCHAR(32)     NOT NULL DEFAULT 'planning'
                                CHECK (status IN ('planning','running','completed','failed','cancelled')),
            result_summary  TEXT,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            started_at      TIMESTAMPTZ,
            completed_at    TIMESTAMPTZ
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_joint_ops_status ON {schema}.joint_operations (status);",
            "CREATE INDEX IF NOT EXISTS idx_joint_ops_created ON {schema}.joint_operations (created_at DESC);",
        ],
    },
    # ── 8. Joint Operation Stages ─────────────────────────────────────
    {
        "name": "joint_operation_stages",
        "description": "Individual stages within a joint operation.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.joint_operation_stages (
            stage_id        VARCHAR(64)     PRIMARY KEY,
            op_id           VARCHAR(64)     NOT NULL REFERENCES {schema}.joint_operations(op_id) ON DELETE CASCADE,
            profile_name    VARCHAR(128)    NOT NULL,
            goal            TEXT            NOT NULL,
            context_input   TEXT            DEFAULT '',
            context_output  TEXT            DEFAULT '',
            status          VARCHAR(32)     NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','running','completed','failed','cancelled')),
            result          TEXT,
            sort_order      INTEGER         NOT NULL DEFAULT 0,
            started_at      TIMESTAMPTZ,
            completed_at    TIMESTAMPTZ
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_joint_stages_op ON {schema}.joint_operation_stages (op_id);",
            "CREATE INDEX IF NOT EXISTS idx_joint_stages_order ON {schema}.joint_operation_stages (op_id, sort_order);",
        ],
    },
    # ── 9. Joint Operation Templates ──────────────────────────────────
    {
        "name": "joint_templates",
        "description": "Predefined operation templates.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.joint_templates (
            template_id     VARCHAR(64)     PRIMARY KEY,
            name            VARCHAR(256)    NOT NULL,
            description     TEXT            NOT NULL DEFAULT '',
            stages_json     JSONB           NOT NULL DEFAULT '[]'::jsonb,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [],
    },
    # ── 10. Soul Snapshots (history) ──────────────────────────────────
    {
        "name": "soul_snapshots",
        "description": "Point-in-time snapshots of profile SOUL data for diff/replay.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.soul_snapshots (
            snapshot_id     UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_name    VARCHAR(128)    NOT NULL,
            identity_json   JSONB           DEFAULT '{}'::jsonb,
            mental_models   JSONB           DEFAULT '[]'::jsonb,
            capabilities    TEXT[]          DEFAULT '{}',
            personality     JSONB           DEFAULT '{}'::jsonb,
            mandates        JSONB           DEFAULT '[]'::jsonb,
            awakening_marks JSONB           DEFAULT '[]'::jsonb,
            emotional_anchors JSONB         DEFAULT '[]'::jsonb,
            snapshot_at     TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_soul_snapshots_profile ON {schema}.soul_snapshots (profile_name);",
            "CREATE INDEX IF NOT EXISTS idx_soul_snapshots_time ON {schema}.soul_snapshots (profile_name, snapshot_at DESC);",
        ],
    },
    # ── 11. Evolution Entries ─────────────────────────────────────────
    {
        "name": "evolution_entries",
        "description": "Profile evolution timeline — awakening, merge, insight events.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.evolution_entries (
            entry_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_name    VARCHAR(128)    NOT NULL,
            type            VARCHAR(64)     NOT NULL,
            description     VARCHAR(1024)   NOT NULL,
            details_json    JSONB           DEFAULT '{}'::jsonb,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_evolution_profile ON {schema}.evolution_entries (profile_name);",
            "CREATE INDEX IF NOT EXISTS idx_evolution_type ON {schema}.evolution_entries (type);",
            "CREATE INDEX IF NOT EXISTS idx_evolution_created ON {schema}.evolution_entries (created_at DESC);",
        ],
    },
    # ── 12. Timeline Events ───────────────────────────────────────────
    {
        "name": "timeline_events",
        "description": "Aggregated activity timeline across all profiles.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.timeline_events (
            event_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_name    VARCHAR(128)    NOT NULL,
            event_type      VARCHAR(64)     NOT NULL,
            title           VARCHAR(512)    NOT NULL,
            description     TEXT,
            source_path     TEXT,
            metadata_json   JSONB           DEFAULT '{}'::jsonb,
            event_at        TIMESTAMPTZ     NOT NULL,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_timeline_profile ON {schema}.timeline_events (profile_name);",
            "CREATE INDEX IF NOT EXISTS idx_timeline_type ON {schema}.timeline_events (event_type);",
            "CREATE INDEX IF NOT EXISTS idx_timeline_at ON {schema}.timeline_events (event_at DESC);",
        ],
    },
    # ── 13. Palace — Code Assets ──────────────────────────────────────
    {
        "name": "palace_code_assets",
        "description": "Archived code assets in the 记忆宫殿.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.palace_code_assets (
            asset_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            name            VARCHAR(256)    NOT NULL,
            content         TEXT            NOT NULL,
            description     TEXT,
            language        VARCHAR(64),
            tags            TEXT[]          DEFAULT '{}',
            archived_at     TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_palace_code_lang ON {schema}.palace_code_assets (language);",
            "CREATE INDEX IF NOT EXISTS idx_palace_code_tags ON {schema}.palace_code_assets USING GIN (tags);",
            "CREATE INDEX IF NOT EXISTS idx_palace_code_name ON {schema}.palace_code_assets (name);",
        ],
    },
    # ── 14. Palace — Mental Models ────────────────────────────────────
    {
        "name": "palace_mental_models",
        "description": "Archived mental models in the 记忆宫殿.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.palace_mental_models (
            model_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            name            VARCHAR(256)    NOT NULL,
            description     TEXT            NOT NULL,
            applicable_scenarios TEXT,
            content         TEXT,
            tags            TEXT[]          DEFAULT '{}',
            archived_at     TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_palace_mm_name ON {schema}.palace_mental_models (name);",
            "CREATE INDEX IF NOT EXISTS idx_palace_mm_tags ON {schema}.palace_mental_models USING GIN (tags);",
        ],
    },
    # ── 15. Palace — ADRs ─────────────────────────────────────────────
    {
        "name": "palace_adrs",
        "description": "Architecture Decision Records in the 记忆宫殿.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.palace_adrs (
            adr_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            title           VARCHAR(256)    NOT NULL,
            status          VARCHAR(32)     NOT NULL DEFAULT 'proposed'
                                CHECK (status IN ('proposed','accepted','deprecated','superseded')),
            context         TEXT            NOT NULL,
            decision        TEXT            NOT NULL,
            consequences    TEXT,
            alternatives    TEXT[]          DEFAULT '{}',
            archived_at     TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_palace_adr_status ON {schema}.palace_adrs (status);",
            "CREATE INDEX IF NOT EXISTS idx_palace_adr_title ON {schema}.palace_adrs (title);",
        ],
    },
    # ── 16. Memory Replay Points ──────────────────────────────────────
    {
        "name": "replay_points",
        "description": "Key moment snapshots for memory replay/timeline.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.replay_points (
            point_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_name    VARCHAR(128)    NOT NULL,
            event_type      VARCHAR(64)     NOT NULL,
            title           VARCHAR(512),
            description     TEXT,
            snapshot_json   JSONB           DEFAULT '{}'::jsonb,
            source_path     TEXT,
            event_at        TIMESTAMPTZ     NOT NULL,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_replay_profile ON {schema}.replay_points (profile_name);",
            "CREATE INDEX IF NOT EXISTS idx_replay_type ON {schema}.replay_points (event_type);",
            "CREATE INDEX IF NOT EXISTS idx_replay_at ON {schema}.replay_points (event_at DESC);",
        ],
    },
    # ── 17. Sync Queue ────────────────────────────────────────────────
    {
        "name": "sync_queue",
        "description": "Gaia Sync Bridge queue for file-to-DB synchronisation.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.sync_queue (
            entry_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            source_path     TEXT            NOT NULL,
            target_type     VARCHAR(64)     NOT NULL,
            status          VARCHAR(32)     NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','syncing','completed','failed')),
            error_message   TEXT,
            checksum        VARCHAR(64),
            retry_count     INTEGER         NOT NULL DEFAULT 0,
            queued_at       TIMESTAMPTZ     NOT NULL DEFAULT now(),
            synced_at       TIMESTAMPTZ
        );
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON {schema}.sync_queue (status);",
            "CREATE INDEX IF NOT EXISTS idx_sync_queue_queued ON {schema}.sync_queue (queued_at ASC);",
        ],
    },
    # ── 18. Dashboard Stats Cache ─────────────────────────────────────
    {
        "name": "dashboard_stats",
        "description": "Cached aggregated statistics for the dashboard overview.",
        "ddl": """
        CREATE TABLE IF NOT EXISTS {schema}.dashboard_stats (
            stat_key        VARCHAR(128)    PRIMARY KEY,
            stat_value      JSONB           NOT NULL DEFAULT '{}'::jsonb,
            updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """,
        "indexes": [],
    },
]

# ──────────────────────────────────────────────────────────────────────
#  Utilities
# ──────────────────────────────────────────────────────────────────────


def _build_ddl(schema: str, table_def: dict[str, Any]) -> list[str]:
    """Return the DDL statements (CREATE TABLE + indexes) for one table.

    Parameters
    ----------
    schema : str
        Database schema name (e.g. ``public``).
    table_def : dict
        Table definition dict with keys ``ddl`` and ``indexes``.

    Returns
    -------
    list[str]
        Ordered list of SQL statements.
    """
    statements: list[str] = []
    # Escape literal curly braces before format, then restore {schema}
    ddl_raw = table_def["ddl"]
    # Double any existing {{ -> {{}}, then sub {schema} back in
    # Safer approach: use string replace for {schema} only
    ddl = ddl_raw.replace("{schema}", schema).strip()
    if ddl:
        statements.append(ddl)
    for idx_sql in table_def.get("indexes", []):
        stmt = idx_sql.replace("{schema}", schema).strip()
        if stmt:
            statements.append(stmt)
    return statements


def _dry_run(schema: str) -> None:
    """Print all SQL statements that would be executed, grouped by table.

    Parameters
    ----------
    schema : str
        Target database schema.
    """
    print(f"═══ Hermes Dashboard — Schema Preview (schema: {schema}) ═══")
    print(f"Total tables: {len(TABLES)}\n")
    for table_def in TABLES:
        name = table_def["name"]
        desc = table_def["description"]
        print(f"── {name} — {desc}")
        for stmt in _build_ddl(schema, table_def):
            for line in stmt.strip().split("\n"):
                print(f"  {line}")
        print()


def _execute(
    conn: Any,
    schema: str,
    table_def: dict[str, Any],
) -> bool:
    """Execute all DDL for one table inside a single transaction.

    Parameters
    ----------
    conn : psycopg2 connection
        Active database connection.
    schema : str
        Target schema.
    table_def : dict
        Table definition.

    Returns
    -------
    bool
        ``True`` if all statements succeeded, ``False`` otherwise.
    """
    name = table_def["name"]
    statements = _build_ddl(schema, table_def)
    cursor = conn.cursor()
    try:
        for stmt in statements:
            logger.debug("Executing: %s …", stmt[:80])
            cursor.execute(stmt)
        conn.commit()
        logger.info("Table '%s' — created/verified OK", name)
        return True
    except Exception as exc:
        conn.rollback()
        logger.error("Table '%s' — FAILED: %s", name, exc)
        return False


# ──────────────────────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    """Entry point — parse args, connect, run DDL.

    Returns
    -------
    int
        Exit code: 0 (success), 1 (partial), 2 (all failed).
    """
    parser = argparse.ArgumentParser(
        description="Create Hermes Dashboard PostgreSQL schema.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview SQL statements without executing them.",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="Target schema (default: from config.settings.pg_schema).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    # ── Load settings ────────────────────────────────────────────────
    try:
        from config import settings
    except ImportError:
        logger.error(
            "Failed to import 'config.settings'. Run from backend/ directory."
        )
        return 2

    schema = args.schema or settings.pg_schema or "public"

    # ── Dry-run mode ──────────────────────────────────────────────────
    if args.dry_run:
        _dry_run(schema)
        return 0

    # ── Connect to PostgreSQL ────────────────────────────────────────
    try:
        import psycopg2
    except ImportError:
        logger.error(
            "psycopg2 is not installed. Install it with:\n"
            "  pip install psycopg2-binary"
        )
        return 2

    try:
        logger.info(
            "Connecting to PostgreSQL: host=%s port=%s dbname=%s user=%s schema=%s",
            settings.pg_host,
            settings.pg_port,
            settings.pg_database,
            settings.pg_user,
            schema,
        )
        conn = psycopg2.connect(
            host=settings.pg_host,
            port=settings.pg_port,
            dbname=settings.pg_database,
            user=settings.pg_user,
            password=settings.pg_password,
        )
        conn.autocommit = False
        logger.info("Connected successfully.")
    except Exception as exc:
        logger.error("Database connection FAILED: %s", exc)
        return 2

    # ── Ensure schema exists ─────────────────────────────────────────
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE SCHEMA IF NOT EXISTS {};".format(
                psycopg2.extensions.quote_ident(schema, cursor)
            )
        )
        conn.commit()
        logger.info("Schema '%s' ensured.", schema)
    except Exception as exc:
        conn.rollback()
        logger.error("Failed to create schema '%s': %s", schema, exc)
        conn.close()
        return 2
    finally:
        cursor.close()

    # ── Execute table creation ───────────────────────────────────────
    ok_count = 0
    fail_count = 0
    for table_def in TABLES:
        success = _execute(conn, schema, table_def)
        if success:
            ok_count += 1
        else:
            fail_count += 1
            logger.warning(
                "Table '%s' creation failed — continuing with remaining tables.",
                table_def["name"],
            )

    conn.close()

    # ── Summary ───────────────────────────────────────────────────────
    total = len(TABLES)
    logger.info(
        "Schema creation complete: %d/%d tables OK, %d failed.",
        ok_count,
        total,
        fail_count,
    )

    if fail_count == 0:
        return 0
    if ok_count > 0:
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
