"""
Unified Response Envelope — standard JSON shape for every API response.

All endpoints should return data wrapped in this envelope for consistency.

Schema
------
.. code-block:: json

    {
        "success": true,
        "data": { ... },
        "error": null
    }

Or on failure:

.. code-block:: json

    {
        "success": false,
        "data": null,
        "error": "Something went wrong"
    }
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class StandardResponse(BaseModel, Generic[T]):
    """Standard API response envelope.

    Attributes
    ----------
    success : bool
        Indicates whether the request was successful.
    data : T | None
        The response payload (if successful).
    error : str | None
        Error message (if unsuccessful).
    """

    success: bool = True
    data: T | None = None
    error: str | None = None


def ok(data: Any = None) -> dict[str, Any]:
    """Return a success envelope."""
    return {"success": True, "data": data, "error": None}


def fail(error: str, data: Any = None) -> dict[str, Any]:
    """Return a failure envelope."""
    return {"success": False, "data": data, "error": error}
