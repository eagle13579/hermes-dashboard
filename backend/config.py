"""
Configuration management for Hermes Dashboard backend.

Reads settings from environment variables (and a .env file if present)
using Pydantic v2 Settings. All values have sensible defaults.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import ClassVar

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# ── Well-known fallback paths ────────────────────────────────────────
_HERMES_HOME_FALLBACK = Path(
    "D:/向海容的知识库/wiki/wiki/记忆宫殿"
)
"""Fallback path used when ``$HERMES_HOME`` is not set."""


class Settings(BaseSettings):
    """Application-level configuration loaded from environment / .env file.

    Attributes
    ----------
    app_host : str
        Host address the Uvicorn server binds to (default: ``"0.0.0.0"``).
    app_port : int
        Port the Uvicorn server listens on (default: ``8090``).
    app_debug : bool
        Enable / disable FastAPI debug mode.
    app_title : str
        Application title exposed via the OpenAPI docs.
    app_version : str
        Application version string.

    hermes_home : Path
        Resolved ``$HERMES_HOME`` path, injected into ``os.environ`` on
        startup so background processes can discover profile directories.
    hermes_profile_path : Path
        Filesystem path to the Hermes profile knowledge base.

    pg_host : str
        PostgreSQL host address.
    pg_port : int
        PostgreSQL port.
    pg_user : str
        PostgreSQL user.
    pg_password : str
        PostgreSQL password.
    pg_database : str
        PostgreSQL database name.
    pg_schema : str
        Database schema to use (default: ``"public"``).
    pg_pool_size : int
        SQLAlchemy connection pool size.
    pg_max_overflow : int
        SQLAlchemy pool max overflow.
    pg_echo : bool
        Log all SQL statements when ``True``.

    cors_origins : list[str]
        List of allowed CORS origins.
    log_level : str
        Logging level (e.g. ``"INFO"``, ``"DEBUG"``).
    """

    # ── App ──────────────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8091
    app_debug: bool = True
    app_title: str = "Hermes Dashboard API"
    app_version: str = "0.1.0"

    # ── Profile ──────────────────────────────────────────────────────
    hermes_home: Path = _HERMES_HOME_FALLBACK
    hermes_profile_path: Path = Path(
        os.getenv(
            "HERMES_PROFILE_PATH",
            str(
                Path.home()
                / "向海容的知识库/wiki/wiki/记忆宫殿/profiles/hermes-dashboard"
            ),
        )
    )

    # ── Security ─────────────────────────────────────────────────────
    api_key: str = ""
    """API key for X-API-Key authentication. Empty = no auth (dev mode)."""

    api_key_name: str = "X-API-Key"
    """Header name for API key."""

    rate_limit_per_minute: int = 0
    """Max requests per minute per client IP. 0 = disabled."""

    # ── PostgreSQL ───────────────────────────────────────────────────
    pg_host: str = "localhost"
    pg_port: int = 5435
    pg_user: str = "postgres"
    pg_password: str = ""
    """PostgreSQL password. **Must** be set via .env or environment variable."""
    pg_database: str = "hermes_dashboard"
    pg_schema: str = "public"
    pg_pool_size: int = 10
    pg_max_overflow: int = 20
    pg_echo: bool = False

    # ── CORS ─────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ── Logging ──────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Pydantic config ──────────────────────────────────────────────
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Derived properties ───────────────────────────────────────────

    @property
    def pg_dsn(self) -> str:
        """Return a DSN string suitable for SQLAlchemy async engines.

        Example
        -------
        ``postgresql+psycopg2://user:pass@localhost:5435/hermes_dashboard``
        """
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg2",
                username=self.pg_user,
                password=self.pg_password,
                host=self.pg_host,
                port=self.pg_port,
                path=self.pg_database,
            )
        )

    @property
    def pg_dsn_async(self) -> str:
        """Async variant using ``asyncpg`` (commented preference) — currently
        returns the sync DSN since we depend on psycopg2-binary.
        """
        # Replace with async driver when ready:
        #   postgresql+asyncpg://...
        # For now return sync DSN.
        return self.pg_dsn.replace("+psycopg2", "+psycopg2")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse ``CORS_ORIGINS`` from a comma-separated string into a list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("hermes_profile_path", mode="before")
    @classmethod
    def _expand_profile_path(cls, v: str | Path) -> Path:
        """Expand ``~`` / ``%USERPROFILE%`` in the profile path."""
        return Path(v).expanduser().resolve()

    @field_validator("hermes_home", mode="before")
    @classmethod
    def _resolve_hermes_home(cls, v: str | Path) -> Path:
        """Resolve ``$HERMES_HOME`` — env var first, then fallback path.

        Priority
        --------
        1. ``$HERMES_HOME`` environment variable.
        2. Hard-coded fallback ``D:\\向海容的知识库\\wiki\\wiki\\记忆宫殿``
           (checked for existence).
        """
        env_val = os.environ.get("HERMES_HOME")
        if env_val:
            resolved = Path(env_val).expanduser().resolve()
            logger.debug("HERMES_HOME resolved to: %s (from env)", resolved)
            return resolved

        # Fallback: use the hard-coded constant if it exists
        fallback = Path(v).expanduser().resolve() if v else _HERMES_HOME_FALLBACK
        if fallback.is_dir():
            logger.debug("HERMES_HOME resolved to: %s (fallback)", fallback)
            return fallback

        logger.debug(
            "HERMES_HOME resolved to: %s (fallback — directory not verified)",
            fallback,
        )
        return fallback


# ── Module-level singleton ──────────────────────────────────────────
settings: Settings = Settings()  # type: ignore[call-arg]
"""Pre-loaded settings singleton. Import ``config.settings`` anywhere."""
