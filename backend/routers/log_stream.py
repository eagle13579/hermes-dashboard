"""
Log Stream Router — SSE-based real-time log streaming for profiles.

Endpoints
=========
================================  =====  ======================================
Path                               Method  Description
================================  =====  ======================================
/api/profiles/{name}/logs          GET    Return recent log lines (history)
/api/profiles/{name}/logs/stream   GET    SSE stream of live log entries
================================  =====  ======================================
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from services.log_stream import read_recent_lines, watch_log_file

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/profiles/{name}/logs", tags=["Logs"])


# ──────────────────────────────────────────────────────────────────────
# GET  /api/profiles/{name}/logs — historical log lines
# ──────────────────────────────────────────────────────────────────────


@router.get("")
async def get_logs(
    name: str,
    lines: Annotated[
        int,
        Query(description="Number of recent lines to return (max 5000)", ge=1, le=5000),
    ] = 50,
) -> JSONResponse:
    """Return the last *lines* from the profile's latest log file.

    Parameters
    ----------
    name : str
        Profile directory name.
    lines : int
        Number of lines to retrieve (default 50, max 5000).

    Returns
    -------
    JSONResponse
        ``{"profile": "<name>", "log_file": "<filename or null>",
           "total": <int>, "lines": [...]}``
    """
    try:
        log_entries = read_recent_lines(name, lines=lines)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return JSONResponse(
        content={
            "profile": name,
            "total": len(log_entries),
            "lines": log_entries,
        }
    )


# ──────────────────────────────────────────────────────────────────────
# GET  /api/profiles/{name}/logs/stream — SSE live log stream
# ──────────────────────────────────────────────────────────────────────


@router.get("/stream")
async def stream_logs(
    name: str,
    request: Request,
) -> StreamingResponse:
    """SSE endpoint that pushes new log lines as they are written.

    The client connects via ``EventSource`` (or a plain ``fetch`` with
    streaming) and receives ``data:`` frames containing JSON-encoded log
    entries.  A keepalive comment is sent every 15 seconds when idle.

    Parameters
    ----------
    name : str
        Profile directory name.
    request : Request
        Used to detect client disconnection.

    Returns
    -------
    StreamingResponse
        ``text/event-stream`` response.
    """

    async def event_generator() -> AsyncIterator[str]:
        """Yield SSE-formatted log events."""
        try:
            async for entry in watch_log_file(name):
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.debug("SSE client disconnected for profile '%s'", name)
                    break

                yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"

        except Exception:
            logger.exception("SSE stream error for profile '%s'", name)
            yield f"data: {json.dumps({'error': 'Stream error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
