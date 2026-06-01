"""
Hermes Dashboard — FastAPI Application Entry Point.

Exposes a FastAPI ASGI application configured with CORS middleware and
a ``/health`` readiness endpoint.  Starts via Uvicorn when run directly.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from services.sync_bridge import SyncConfig, get_bridge
from routers.profiles import router as profiles_router
from routers.sync import router as sync_router
from routers.kanban import router as kanban_router
from routers.timeline import router as timeline_router
from routers.dashboard import router as dashboard_router
from routers.legion import router as legion_router
from routers.knowledge import router as knowledge_router
from routers.soul_diff import router as soul_diff_router
from routers.memory_replay import router as memory_replay_router
from routers.skill_studio import router as skill_studio_router
from routers.joint_ops import router as joint_ops_router
from routers.profile_soul import router as profile_soul_router
from routers.palace import router as palace_router
from routers.skill_import import router as skill_import_router
from routers.log_stream import router as log_stream_router
from routers.session import router as session_router
from routers.health_router import router as health_router
from security.auth import require_api_key
from security.exceptions import register_exception_handlers
from security.rate_limit import RateLimitMiddleware
logger = logging.getLogger(__name__)

# ── Application lifecycle ─────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup / shutdown lifecycle.

    Startup
    -------
    * Configure logging level from settings.
    * (Future) initialise database engine, connection pools, etc.

    Shutdown
    --------
    * (Future) dispose database engine, close connections, etc.
    """
    # ── Startup ──────────────────────────────────────────────────────
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    # Inject HERMES_HOME so background processes (legion, kanban, etc.)
    # can discover profile directories even when the env var is not
    # inherited from the shell (e.g. launched as a Windows service).
    hermes_home_str = str(settings.hermes_home)
    os.environ.setdefault("HERMES_HOME", hermes_home_str)
    logger.debug("HERMES_HOME set to %s", os.environ["HERMES_HOME"])

    # ── Initialize Gaia Sync Bridge ──────────────────────────────
    bridge_config = SyncConfig(
        pg_conn_str=(
            f"host={settings.pg_host} port={settings.pg_port} "
            f"dbname={settings.pg_database} "
            f"user={settings.pg_user} password={settings.pg_password}"
        ),
        profile_dir=str(settings.hermes_profile_path),
        poll_interval=300,
    )
    bridge = get_bridge(config=bridge_config)
    try:
        summary = bridge.sync_once()
        logger.info(
            "Gaia Sync Bridge — initial sync: scanned=%d synced=%d failed=%d pending=%d",
            summary.get("scanned", 0),
            summary.get("synced", 0),
            summary.get("failed", 0),
            summary.get("pending", 0),
        )
    except Exception as exc:
        logger.warning(
            "Gaia Sync Bridge — initial sync skipped (%s). "
            "Files will be queued and retried on next cycle.",
            exc,
        )

    logger.info(
        "Starting %s v%s", settings.app_title, settings.app_version
    )
    yield
    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("Application shutdown complete")


# ── FastAPI instance ──────────────────────────────────────────────────

app: FastAPI = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    debug=settings.app_debug,
    lifespan=lifespan,
)

# ── CORS middleware ───────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate-limit middleware ────────────────────────────────────────────

app.add_middleware(RateLimitMiddleware)  # type: ignore[arg-type]

# ── Exception handlers ───────────────────────────────────────────────

register_exception_handlers(app)


# ── Routes ────────────────────────────────────────────────────────────


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Readiness probe — returns API status.

    Returns
    -------
    dict[str, str]
        ``{"status": "ok"}`` when the application is running.
    """
    return {"status": "ok"}


# ── Mount routers ─────────────────────────────────────────────────────

app.include_router(profiles_router)
app.include_router(sync_router)
app.include_router(kanban_router)
app.include_router(knowledge_router)
app.include_router(joint_ops_router)
app.include_router(legion_router)
app.include_router(timeline_router)
app.include_router(dashboard_router)
app.include_router(memory_replay_router)
app.include_router(skill_studio_router)
app.include_router(soul_diff_router)
app.include_router(profile_soul_router)
app.include_router(palace_router)
app.include_router(skill_import_router)
app.include_router(log_stream_router)
app.include_router(session_router)
app.include_router(health_router)

# ── Static files (frontend SPA) ──────────────────────────────────────────

_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
    logger.info("Frontend SPA mounted from %s", _frontend_dist)
else:
    logger.warning("Frontend dist not found at %s — run 'cd frontend && npx vite build'", _frontend_dist)


# ── Entry point ───────────────────────────────────────────────────────────


def main() -> None:
    """Launch the Uvicorn server with settings from config."""
    uvicorn.run(
        "main:app",
        timeout_keep_alive=120,
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
