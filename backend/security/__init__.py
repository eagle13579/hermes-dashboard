"""
Hermes Dashboard — Security Package

Provides authentication, authorisation, rate-limiting, exception handling,
and unified response envelope support for the Hermes Dashboard API.

Exports
-------
* ``require_api_key`` — FastAPI dependency for API-key authentication.
* ``ApiKeyHeader`` — auto-documented header model.
* ``setup_security`` — one-call setup that registers all middleware.
* ``StandardResponse`` — Pydantic response envelope model.
* ``register_exception_handlers`` — global HTTP exception → envelope.
* ``rate_limit_middleware`` — optional in-process rate limiter.
"""

from security.auth import API_KEY_HEADER, require_api_key
from security.exceptions import register_exception_handlers
from security.rate_limit import RateLimitMiddleware
from security.response import StandardResponse

__all__ = [
    "API_KEY_HEADER",
    "RateLimitMiddleware",
    "StandardResponse",
    "register_exception_handlers",
    "require_api_key",
]
