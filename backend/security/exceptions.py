"""
Global Exception Handlers — wrap all exceptions in unified JSON envelopes.

Registers custom handlers for:
* ``HTTPException`` — passthrough with envelope.
* ``RequestValidationError`` — Pydantic validation → 422 envelope.
* ``Exception`` — catch-all 500 envelope (prevents stack leak).
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from config import settings

logger = logging.getLogger(__name__)


def _envelope(
    success: bool,
    data: Any = None,
    error: str | None = None,
    status_code: int = 200,
) -> dict[str, Any]:
    """Build a standard JSON envelope."""
    payload: dict[str, Any] = {"success": success, "data": data}
    if error:
        payload["error"] = error
    return payload


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Wrap FastAPI's ``HTTPException`` in our standard envelope."""
    from fastapi.exceptions import HTTPException

    he = exc  # type: ignore[assignment]
    return JSONResponse(
        status_code=he.status_code,
        content=_envelope(
            success=False,
            error=he.detail,
            status_code=he.status_code,
        ),
    )


async def _validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Wrap Pydantic validation errors in our standard envelope."""
    errors = exc.errors()
    # Build a human-readable detail
    detail_parts: list[str] = []
    for err in errors:
        loc = " -> ".join(str(p) for p in err.get("loc", []))
        msg = err.get("msg", "")
        detail_parts.append(f"[{loc}] {msg}" if loc else msg)
    detail = "; ".join(detail_parts) or "Validation error"

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_envelope(
            success=False,
            error=detail,
            data={"validation_errors": errors},
            status_code=422,
        ),
    )


async def _generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all — log the traceback and return a safe 500 envelope.

    Never exposes internal stack traces to the client in production.
    """
    logger.exception("Unhandled exception: %s", exc)

    if settings.app_debug:
        detail = str(exc)
        trace = traceback.format_exc()
    else:
        detail = "Internal server error"
        trace = None

    payload = _envelope(
        success=False,
        error=detail,
        status_code=500,
    )
    if trace:
        payload["traceback"] = trace

    return JSONResponse(status_code=500, content=payload)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI application.

    Call this during application startup, before any middleware that
    might suppress exceptions.

    Parameters
    ----------
    app : FastAPI
        The application instance.
    """
    from fastapi.exceptions import HTTPException

    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _generic_exception_handler)

    logger.debug("Global exception handlers registered")
